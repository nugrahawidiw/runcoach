# Architecture

## 1. Purpose and scope
`runcoach` turns raw training data into the analysis a coach would write: per-lap tables, grade-adjusted
pace, decoupling, cadence, efficiency, VDOT, training load and Garmin wellness trends. It is a **command-line
tool for one athlete**. It has no server, database or UI; outputs are markdown, JSON and CSV.

Two data sources feed the same analysis:

| Source | What it provides | Entry points |
|---|---|---|
| Strava API (REST v3) | activities, laps, full-resolution streams, gear | `runcoach auth`, `sync`, `analyze`, `load` |
| Garmin FIT files | run files (laps + 1 Hz records) and daily wellness exports | `fit-analyze`, `fit-import`, `wellness` |

## 2. Data flow
```
Strava API ──► StravaClient ──► Cache (JSON files) ──┐
                                                     ├──► (activity, laps, streams) ──► build_report ──► markdown / JSON
Garmin run .fit ──► fit.reader ──► fit.activity ─────┘                │
                                                                      └─► metrics/*  (gap, decoupling, cadence, efficiency, zones)

cached runs ──► metrics.load (suffer_score or TRIMP) ──► CTL / ATL / TSB table

Garmin wellness zips ──► fit.reader (groups per export) ──► fit.wellness.summarize_messages ──► Night rows (table / JSON / CSV)
```
Design rule: **convert every source to Strava's REST shapes first**, then run one set of metric code.

## 3. Layers
1. **I/O layers** (`strava/`, `fit/reader.py`): talk to the outside world; return plain dicts or `Message`s.
2. **Converters** (`fit/activity.py`, `fit/wellness.py`): normalize into the shared shapes or `Night` records.
3. **Metrics** (`metrics/*`): pure functions, no I/O, easiest to test. Prefer adding logic here.
4. **Analysis** (`analysis/run_report.py`): joins laps + streams + profile into a report dict.
   `analysis/readiness.py` turns one wellness Night plus a planned session kind into a recommendation,
   carrying each rule's status (confirmed / in_plan / suggested / proposed_not_confirmed) into the output.
   `analysis/weekly.py` groups cached activities into Monday-to-Sunday weeks and reads CTL/ATL/TSB at each
   week's end. `cli._daily_loads` is shared by `load` and `weekly` so the two cannot disagree.
5. **CLI** (`cli.py`): argument parsing and printing only.

## 4. Data shapes (the contract between layers)

### Activity (Strava `DetailedActivity` subset, also produced from FIT)
`name`, `sport_type`, `start_date_local` (`YYYY-MM-DDTHH:MM:SSZ`, local wall time), `distance` (m),
`moving_time` (s), `elapsed_time`, `average_heartrate`, `max_heartrate`, `average_cadence` (rpm, one foot),
`total_elevation_gain` (m), `gear_id`, `suffer_score` (Strava Relative Effort, may be absent),
`splits_metric` (optional fallback), `source` (`garmin-fit` for FIT imports).

### Lap (Strava `/activities/{id}/laps`; FIT laps are mapped to the same keys)
`distance`, `moving_time`, `elapsed_time`, `average_heartrate`, `average_cadence` (rpm),
`start_index`, `end_index` (inclusive indices into the 1 Hz streams).
`run_report.normalize_lap` also accepts the shorter names `avg_hr`, `avg_cadence`, `avg_grade` (used by
the chat connector the project started from).

### Streams (Strava `key_by_type=true` shape)
`{"time": {"data": [...]}, "velocity_smooth": {...}, "heartrate": {...}, "cadence": {...},
"altitude": {...}, "grade_smooth": {...}, "distance": {...}}`. All arrays have the same length; index = sample.
FIT streams are resampled to **1 Hz** (index = seconds since start); short gaps (<= 10 s) are forward-filled,
longer gaps (pauses) stay `None`.

### Report (`build_report` output)
Top level: `name, date, kind, distance_km, moving, avg_pace (s/km), overall_gap (s/km), avg_hr, max_hr,
avg_cadence_spm, elevation_m, gear_id, suffer_score, efficiency, laps, decoupling_raw, decoupling_gap,
time_in_zone, easy_guide, flags`. `time_in_zone` is `{Z1..Z5: seconds}` and `easy_guide` is
`{guide, at_or_below_s, above_s}`; both are `None` when the activity has no `heartrate` stream.
Lap row: `lap, distance_m, moving_s, pace (s/km), gap (s/km), grade_pct, avg_hr, cadence_spm`.
Decoupling dict: `first_pace, first_hr, second_pace, second_hr, pct`.

### Night (`fit/wellness.py`, one per sleep)
`wake_date, sleep_start, sleep_end (local), duration_min, score, score_parts, awake_min_summary, stage_min
(estimate), duration_min (deep+light+REM, as Garmin Connect; awake excluded), time_in_bed_min (whole window),
hrv_last_night, hrv_weekly, hrv_status, hrv_baseline (low_upper, balanced_lower, balanced_upper),
hrv_5min_high, sleep_low_hr, garmin_rhr, garmin_rhr_today, stress_sleep_avg, stress_export_avg,
stress_export_max, resp_avg, body_battery_delta`.

## 4b. Files on disk
```
.env                          secrets (git-ignored): STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REDIRECT_URI, RUNCOACH_DATA
profile.toml                  optional athlete profile (see profile.example.toml)
data/tokens.json              Strava tokens (plain JSON; chmod 0600 only effective on Linux/macOS)
data/cache/activity/<id>.json
data/cache/laps/<id>.json
data/cache/streams/<id>.json  cache ids: Strava numeric id, or fit-YYYYMMDDHHMMSS for imported FIT runs
```

## 5. Key modules and decisions

**`strava/auth.py`** OAuth2 authorization-code flow with a one-shot local HTTP server on the redirect port
(default `http://localhost:8765/callback`; Strava app callback domain must be `localhost`). Scope
`read,activity:read_all`. Strava issues a **new refresh token on every refresh**, so tokens are always saved
after refresh. The flow verifies the granted scope contains `activity:read`.

**`strava/client.py`** `StravaClient` takes an injectable `session` and `clock` (for tests). `_get` refreshes an
expired token before the call, retries once on 401 after a forced refresh, raises `RateLimitError` on 429,
returns `None` on 404, and logs a warning at 80% of the overall or the read rate limit (headers `X-RateLimit-Limit/Usage` and `X-ReadRateLimit-Limit/Usage`).
Streams are requested with `key_by_type=true` at full resolution (laps index into them).

**`strava/sync.py`** `sync_recent(client, cache, days)` lists activities after now - days, keeps `Run`,
`TrailRun`, `VirtualRun`, and for each new run stores activity + laps + streams (3 calls). On a 429 it stops
cleanly (`stopped_by_rate_limit`) and the next run resumes because finished runs are cached.

**`metrics/gap.py`** Minetti et al. (2002) cost polynomial; `gap_factor(grade_pct)` is cost(grade)/cost(0).
GAP pace = pace / factor. Least reliable on small downhill grades (the model over-credits them), so reports
show both raw and grade-adjusted decoupling and treat disagreement as a caution, not a verdict.

**`metrics/decoupling.py`** Skip the first 1000 m (cumulative, partial laps prorated), split the remainder in
two halves by distance (grade-adjusted distance when `use_gap`), efficiency factor = speed / HR per half,
`pct = (EF1 - EF2) / EF1 * 100`. Positive = efficiency fell.

**`metrics/load.py`** `step()` uses exponential weights `alpha = 1 - exp(-1/N)` with N = 42 (CTL) and 7 (ATL);
TSB = CTL - ATL. Load per day is Strava `suffer_score` when present, otherwise Banister TRIMP from the HR
stream. **The two scales differ**: a 40-minute easy run is about 19 in Relative Effort but about 70 in TRIMP.
Pick one source and keep it; do not mix. `runcoach load` prints a NOTE when under 42 days of history are cached and
no seed is given, because CTL then starts from zero.

**`metrics/vdot.py`** Daniels/Gilbert VDOT, bisection for equivalent times, Riegel projection (exponent 1.06).

**`metrics/zones.py`** Time in zone from the 1 Hz `heartrate` stream, one second per measured sample, plus the
easy-HR guide split. Zones come from `Profile.hr_zones`, the **lower** bounds of Z2..Z5. The standing table in
`COACHING_CONTEXT.md` has gaps (151, 160, 168 bpm belong to no zone); using lower bounds only makes the
partition total, so each gap bpm joins the zone below it and the seconds sum to the measured samples.
Approximate by design; used for context, not prescription.

**`fit/reader.py`** Thin wrapper over `fitdecode`. `Message(name, fields, file)`; unknown messages arrive as
`unknown_<n>` with `unknown_<field>` keys. Accepts a `.fit`, a `.zip` of `.fit` files, or a folder. `iter_groups`
groups messages **per export (zip)** so a folder of daily zips yields one group per day.

**`fit/wellness.py`** See `FIT_AND_WELLNESS_NOTES.md`. Uses named messages where the FIT profile knows them and
two empirical unknown messages (sleep window = 521, body battery = 407).

**`fit/activity.py`** Builds 1 Hz streams from `record` messages, derives `grade_smooth` from smoothed altitude
and distance (+/- 10 s), maps `lap`/`session` to REST-shaped dicts. On running files the cadence fields are named
`avg_running_cadence` (handled), otherwise `avg_cadence`.

**`analysis/run_report.py`** Per lap: pace, grade (mean of the `grade_smooth` stream over the lap's index range,
else the lap's own grade, else 0), cadence (stream mean ignoring glitches, else lap average x 2), GAP.
Overall GAP = total time / grade-equivalent distance. A trailing lap shorter than 50 m is ignored (recording artefact; strides of 85-98 m are kept). Flags for `easy`/`long`:
laps outside the Easy band (laps >= 500 m only) and minutes above the HR guide. `strides`/`intervals` kinds currently get no special handling.

## 6. Error handling
`StravaError` > `AuthError`, `RateLimitError`. The CLI catches `StravaError` and prints `error: ...` with exit
code 1. Unreadable FIT files are skipped with a logged warning (`fitdecode.ErrorHandling.IGNORE`); a FIT activity
without `session` or `record` messages raises `ValueError`.

## 7. Security
Secrets only in `.env` and `data/tokens.json`, both git-ignored. Tokens are not encrypted. Do not log request
headers. The Strava client secret was once pasted into a chat during setup: rotate any secret that leaks.

## 8. Testing strategy
- `tests/test_metrics.py`: formulas pinned to real session numbers.
- `tests/test_report.py`: report building from real laps with synthetic 1 Hz streams.
- `tests/test_client.py`: auth/refresh/429/pagination/sync using a fake session (no network).
- `tests/test_fit_activity.py`: writes a real FIT file (`tests/fitwriter.py`) and parses it back.
- `tests/test_fit_wellness.py`: synthetic `Message` lists shaped like real Garmin exports.
Real private data (the owner's zips) is deliberately **not** in the repo; sanitize before adding fixtures.

## 9. Known limitations
See `ROADMAP.md` ("Known issues"). Highlights: live API untested, FIT run files untested on real data, `load`
needs long history for meaningful CTL, `stress_export_avg` window is "everything in that export".
