# Roadmap and known issues

Order matters: P0 items verify what is already built; build new features on verified ground.

## P0: verify and harden
1. **DONE 2026-10-12: Strava path run live.** `auth`, `sync --days 7`, `sync --days 21`, `analyze latest --kind long`,
   `load`, `vdot` all worked against the owner's real account (13 runs cached). Results matched the hand analysis:
   10.03 km, 1:09:45 moving, 6:57/km, HR 140.7/158, cadence 170.2 spm, +56 m; Relative Effort per day 22, 47, 19, 26,
   33 (identical to the values used earlier). Differences found and handled:
   - A 25 m trailing "lap 11" nudged raw decoupling from 6.92% to 7.01%: trailing laps under 50 m are now ignored.
   - Grade is averaged from the `grade_smooth` stream, not Strava's lap grade (lap 1: -1.0% vs -1.2%); grade-adjusted
     decoupling is -1.46% live vs -1.33% in the hand analysis. Both are fine; neither is "wrong".
   - Strava reports **read** limits separately (100 per 15 min, 1,000 per day on this app); the client now tracks them.
   - `load` over a short history starts from zero and understates CTL; it now prints a NOTE (seed with `--ctl0/--atl0`).
   **DONE 2026-11-17: recorded-response fixture.** `tests/data/strava_long_run.json` holds the real synced
   activity, laps and full-resolution streams for the Oct 11 long run, sanitized by whitelist: ids, athlete,
   title, description, GPS points, map data, segment and place names, gear, images, tokens and upload ids
   are gone; the numbers are untouched. `tests/test_recorded_strava.py` pins the REST field names (so the
   `avg_hr` vs `average_heartrate` trap in section 6 below cannot regress), the stream shape and single
   resolution, the tail-lap rule dropping the 25 m lap, and the golden numbers. One test fails if a future
   refresh of the fixture reintroduces anything identifying.
2. **DONE 2026-11-17: FIT run reader validated on a real watch file.** `24633064698_ACTIVITY.fit`, the
   Oct 7 intervals run, read with `fit-analyze` and compared against the same run from Strava:
   distance 6993.3 m vs 6.99 km, moving 2642 s vs 44:02, HR 150.6/166 vs 151.0/166, cadence 168.4 vs 168.0
   spm, elevation 21 m vs +21 m, and all 12 laps the same distances and paces (lap 3: 5:24, HR 153.6 vs
   154.0, cadence 173.0 vs 172.9). The sub-bpm and 0.4 spm gaps are Strava averaging from higher-precision
   samples than the integer streams in the FIT file. No fixture added: the file is 189 KB and the laps are
   already pinned by OCT7_INTERVALS in `tests/fixtures.py`.
3. **DONE 2026-11-17: sleep stages settled, and the assumption was correct.** A Garmin Connect export for
   2026-10-19 gives deep 1h49, light 4h04, REM 1h16, awake 18m; `stage_minutes` produces 109 / 244 / 76 / 18.
   Exact match on all four, so the "timestamp marks the end of the stage" reading is right and no change was
   needed. Score 79, HRV 31, RHR 56, stress 19 and BB +51 all matched as well.
   **Also fixed 2026-11-17, on the owner's decision:** `duration_min` now follows Connect and excludes
   awake (deep + light + REM), with the whole window kept as the new `time_in_bed_min`. Oct 19 reports 7h09,
   matching Connect. This moved the Oct 11-12 golden number from 377 to 370 min; 377 is now time in bed, and
   COACHING_CONTEXT records both. Without stage data `duration_min` falls back to the window.
4. **DONE 2026-11-17: tooling.** git initialized (`nugrahawidiw/runcoach`), `ruff` configured in
   `pyproject.toml` (line-length 135, `E,F,I,UP`; `E702`/`E741` ignored as house style), a pre-commit hook
   runs ruff on staged files plus the full suite, and `.github/workflows/ci.yml` runs ruff and pytest on
   ubuntu + windows for Python 3.11 and 3.13. `ruff check` and `pytest` both pass.

## P1: features (each needs tests)
1. **DONE 2026-11-17: readiness command.** `analysis/readiness.py` + `runcoach readiness PATH --kind
   {intervals,long,strides,gate} [--legs-flat] [--json]`. All four rules from COACHING_CONTEXT section 3 are
   coded and each output line carries the rule id and its status, so a proposal is never shown as agreed.
   Deterministic: no clock, no randomness, no network. 17 tests in `tests/test_readiness.py`, one per rule
   plus both missing-input paths. Missing sleep score or HRV status gives CANNOT DECIDE, naming the input.
   Open: the HR-172 rule is only a watch item (it needs in-session HR, which this command does not see), and
   `--legs-flat` is a manual flag because nothing in the data says how the legs feel.
2. **DONE 2026-11-17: session-structure detection.** `analysis/session.py`; `analyze`/`fit-analyze`
   with `--kind intervals|strides` now print the rep table, and decoupling is suppressed for those kinds
   (it is meaningless there, COACHING_CONTEXT 1.1). Reps are found by sorting lap paces and splitting at the
   single largest gap -- parameter-free, and far steadier than a threshold: the gap is 75 s/km on Oct 7 and
   159 s/km on Oct 9, while a percentage cut came within a second of misclassifying a rep. `min_gap_pct`
   (15% of median pace) stops it inventing structure on a steady run: the Oct 11 long run's largest gap is
   8%. Consecutive fast laps merge, so a 6:00 block spanning a 1 km auto-split and its remainder is one rep.
   The stride cadence band is applied only to strides.
   **Acceptance met**: reps 5:23 / 5:27 / 5:27, cadence 172.9 / 170.8 / 170.0, and 5 of 6 strides in band,
   all reproduced in `tests/test_session.py` from real Strava laps (`OCT7_INTERVALS`, `OCT9_STRIDES`).
   **DONE 2026-11-17: first-minute overshoot**, from the 1 Hz streams: the opening 60 s of each rep against
   the remainder, in pace and HR. Both sources name the streams the same way (`heartrate`,
   `velocity_smooth`), so one implementation covers Strava and FIT. A rep is flagged when its first minute
   is more than 5 s/km quicker than the rest -- that threshold is a choice, not from the docs. Reps under
   90 s (strides) get None rather than a meaningless split, as does a report with no streams. On the real
   Oct 7 watch file: rep 1 ran 5:13 then 5:29 (-16 s/km, OVERSHOT), reps 2 and 3 started conservatively.
   21 tests.
3. **DONE 2026-11-17: HR zone time-in-zone.** `metrics/zones.py` (`zone_for`, `time_in_zone`,
   `easy_guide_split`); `build_report` adds `time_in_zone` and `easy_guide` when a `heartrate` stream is
   present, and `render_markdown` prints both. Verified on OCT11_LONG: Z1 35:31, Z2 27:38, Z3 6:37, and
   35:31 of 1:09:46 (51%) at or below the 145 guide. The standing zones have gaps (151, 160, 168 bpm), so
   zones are defined by lower bounds and each gap bpm joins the zone below; see `metrics/zones.py`.
   **Confirmed by the owner 2026-11-17:** a gap bpm joins the zone below, as coded. No longer open.
4. **DONE 2026-11-17: charts.** `analysis/charts.py` + `--chart OUT.svg` on `analyze` and `fit-analyze`,
   taking the report dict, so the chart has the same inputs as the report. Pace (left axis, faster upwards)
   and cadence (right axis, dashed) per lap, with the easy/goal/tempo bands shaded behind them.
   **Inline SVG, not matplotlib**, which the acceptance allows: no dependency at all, renders in any browser,
   diffs as text. No PNG as a result; open the SVG and export if a raster is needed, or swap the module for
   matplotlib behind the same signature. Output is self-contained (no external fonts, scripts or images).
   13 tests, including XML validity, inverted pace axis, escaping, and that axis labels stay inside the
   canvas -- a screenshot showed "Cadence spm" clipped at the right edge, which no other test caught.
5. **DONE 2026-11-17: dedupe Strava vs Garmin.** `analysis/dedupe.py` + `runcoach dedupe [--minutes 2]
   [--tolerance-m 100] [--prefer strava|garmin] [--json]`. The source is read from the cache key
   (`fit-...` is a FIT import). More importantly, `load`, `weekly` and `plan` now go through
   `cli._cached_activities`, so a run cached from both sources is no longer counted twice -- which
   previously inflated CTL and weekly distance -- and those commands print a NOTE naming what they ignored.
   Two choices the roadmap left open: the distance tolerance is 100 m or 1% of the longer run, whichever is
   more generous (Garmin and Strava routinely differ by tens of metres); and Strava wins by default because
   it carries `suffer_score`, which `load` prefers. **Nothing is deleted from the cache** -- the functions
   only report and filter -- so a wrong match costs a line of output, not data. Same-source pairs are
   deliberately never merged: two Strava rows at one time are a cache problem that should stay visible.
   15 tests.
6. **DONE 2026-11-17: weekly summary.** `analysis/weekly.py` + `runcoach weekly [--weeks N]
   [--source suffer|trimp] [--ctl0 X --atl0 Y] [--json]`. One row per Monday-to-Sunday week (weeks run
   Mon-Sun per section 3 above): runs, distance, moving time, average pace, longest run, and CTL/ATL/TSB read
   at the week's end. Weeks with no runs are still listed so a rest week and its rising TSB show up; load
   columns are blank for weeks before the cache starts rather than guessed. 12 tests.
   Planned vs actual was added once P1.7 landed: `runcoach weekly --plan plan.toml` shows planned runs and
   km in brackets. Without `--plan` the planned columns are omitted rather than guessed.
7. **DONE 2026-11-17: plan as data.** `analysis/plan.py` + `runcoach plan plan.toml [--ics OUT] [--json]`,
   and `runcoach weekly --plan plan.toml` adds planned runs/km per week (this closes the gap left in P1.6).
   **TOML, not YAML**: `tomllib` is stdlib and `profile.toml` already uses it, so the plan costs no new
   dependency. See `plan.example.toml`. Unknown keys and a missing date/kind raise rather than being ignored.
   Matching is by date only: a planned session with a run that day is DONE, without one MISSED, and a run on
   an unplanned day UNPLANNED. Distance short of plan is reported, not judged -- deciding whether a run
   *satisfied* a session needs P1.2. `.ics` export uses `icalendar` (the `ics` extra, imported lazily, so the
   core install stays requests + fitdecode); a test asserts no line exceeds 75 octets, which is the folding
   bug the roadmap warned about. 13 tests.
8. **DONE 2026-11-17: wellness trends.** `analysis/wellness_trends.py` + `runcoach trends PATH
   [--window 7] [--weak-nights 3] [--json]`. Per night: sleep score, HRV, a rolling HRV mean over `--window`
   nights, where that HRV sits against Garmin's own balanced range (below / in / above), status and resting
   HR. Plus the resting-HR trend (first, last, delta, mean) and the trailing weak-night streak.
   **"Weak" was not defined anywhere**, so it is built only from thresholds that already exist: sleep score
   below 60 (the confirmed rule in COACHING_CONTEXT section 3), HRV status Unbalanced (the same signal the
   confirmed readiness rule uses), or HRV below Garmin's balanced range for this athlete. The one free
   choice was how many consecutive weak nights raise the alert; **3 was agreed by the owner 2026-11-17** and
   remains adjustable with `--weak-nights`. 17 tests.

## P2
1. **DONE 2026-11-17: dashboard generator.** `analysis/dashboard.py` + `runcoach dashboard [--out
   dashboard.html] [--weeks 8]`. Summary cards, a CTL/ATL/TSB chart, the weekly table and the latest run's
   chart, reusing `analysis/charts.py`. One self-contained file: inline CSS and SVG, no scripts, no fonts,
   no network, asserted by a test. `generated` is passed in rather than read from the clock, so output is
   reproducible. The previous hand-made dashboard is not in the repository, so this was built from what the
   code produces; if that page still exists and differs in ways that matter, adjust here. 11 tests.
2. **DONE 2026-11-17: typed models.** `runcoach/strava/types.py` declares Activity, Lap, Split, StreamBlock
   and Streams as `TypedDict`s and the client is annotated with them. TypedDict rather than dataclasses
   because the cache stores the API's JSON verbatim, so describing the dict that is already there costs
   nothing at runtime. All `total=False`, since Strava omits fields rather than sending nulls. `REQUIRED_*`
   and `missing_keys()` report what a response lacks. 10 tests check the types against the recorded response
   so they cannot drift into decoration. 
3. **DONE 2026-11-17: CLI integration tests and Windows path edge cases.**
   `tests/test_cli_integration.py`: 16 end-to-end runs through `main()` with a temporary data directory,
   plus folders and files with spaces, punctuation and non-ASCII names, a relative path, a zip nested
   several folders deep, a non-FIT file, and a missing path. Real FIT bytes from `fitwriter`, not stubs.
   The project's own directory contains a space, so these are the cases that actually occur.
4. **DONE 2026-11-17: packaging.** readme, keywords, classifiers and repository URL in `pyproject.toml`,
   plus a `Private :: Do Not Upload` classifier so an accidental PyPI upload fails. A wheel was built and
   installed into a clean venv, where `runcoach vdot 26:17 5000` gives VDOT 36.1 with only `requests` and
   `fitdecode`. README documents both install routes. **No licence is declared**, by the owner's decision on
   2026-11-17: the repository stays unlicensed and private, and the `Private :: Do Not Upload` classifier
   guards against publishing it by accident.
5. **NOT DONE, and recommended against: Strava webhooks instead of polling.** Strava pushes events to a
   public HTTPS callback that it validates when the subscription is created. This runs on one Windows
   laptop with no server, so it would need a tunnel or a hosted endpoint: permanent infrastructure, for a
   tool that polls well inside its limits (about 3 calls per run against 100 reads per 15 minutes).
   Reconsider only if syncing ever becomes a real constraint.
6. **NOT DONE, deferred on purpose: SQLite instead of JSON files.** Buildable, but the JSON cache works, is
   one file per resource, and is readable with a text editor -- which is how the P0.1 recorded-response
   fixture was made. SQLite would buy faster queries over a few hundred files and cost direct inspection.
   Worth doing when something is measurably slow; if it is done, keep a JSON export so the cache stays
   inspectable.

## P3: nothing queued
Everything the roadmap listed is either done or explicitly deferred above. New work starts here.

## Known issues and risks
- Real FIT run files were untested until 2026-11-17; the reader now matches Strava on a real watch file (P0.2).
  Live Strava calls were verified on 2026-10-12 and the responses are pinned as a fixture (P0.1).
- `load` starts the series `--days` before the last activity and seeds it with `--ctl0/--atl0`; without long history
  CTL is understated. Use a long `sync` (in rate-limit-sized chunks) or seed from a known value.
- **FIXED 2026-11-17:** `load --source suffer` used to fall back to TRIMP for activities without
  `suffer_score`, summing two different scales into one CTL series. `load`, `weekly` and `dashboard` now
  refuse, naming the activities, and `--allow-mixed-load` accepts the mix deliberately. A run with neither
  a Relative Effort nor heart-rate streams counts as zero, which understates CTL rather than corrupting it,
  so that is reported as a NOTE instead of a refusal.
- `analyze --kind strides|intervals` now detects reps (P1.2) and suppresses decoupling, which is meaningless there.
- Wellness `stress_export_*` window semantics are loose; `sleep_start/end` use the watch's offset.
- `.env` parser is minimal (no inline comments or multi-line values).
- Tokens are stored unencrypted; `chmod 0600` has no effect on Windows.
- The sleep-window and body-battery messages are undocumented and may change with firmware.
- Rate limits for the owner's app: overall 200 per 15 minutes / 2,000 per day; read 100 per 15 minutes / 1,000 per day
  (from the Strava API page). A sync used about 2 counted requests per run in practice, less than the 3 calls made.
