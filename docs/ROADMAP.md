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
   Still open: add a **sanitized recorded-response fixture** from `data/cache/` (remove names, locations, ids) so the
   REST shapes are pinned by a test.
2. **Validate the FIT run reader on a real watch file.** Compare with Strava/Garmin Connect (distance, time, HR,
   cadence, lap paces). Add a small sanitized fixture or a synthetic file that reproduces any difference found.
3. **Settle sleep stages** against Garmin Connect (`FIT_AND_WELLNESS_NOTES.md` section 4). Update `stage_minutes` and
   its test, or remove stage output if it cannot be made reliable.
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
2. **Session-structure detection** for intervals and strides from laps/streams (work vs recovery blocks, rep pace,
   rep HR, rep cadence, fade between reps, first-minute overshoot). Acceptance: reproduces the Oct 7 intervals
   numbers (reps 5:23 / 5:27 / 5:27; cadence 172.9 / 170.8 / 170.0) and the Oct 9 strides table (5 of 6 in band).
3. **DONE 2026-11-17: HR zone time-in-zone.** `metrics/zones.py` (`zone_for`, `time_in_zone`,
   `easy_guide_split`); `build_report` adds `time_in_zone` and `easy_guide` when a `heartrate` stream is
   present, and `render_markdown` prints both. Verified on OCT11_LONG: Z1 35:31, Z2 27:38, Z3 6:37, and
   35:31 of 1:09:46 (51%) at or below the 145 guide. The standing zones have gaps (151, 160, 168 bpm), so
   zones are defined by lower bounds and each gap bpm joins the zone below; see `metrics/zones.py`.
   Open question for the owner: if a gap bpm should instead count to the zone *above*, change `hr_zones`.
4. **DONE 2026-11-17: charts.** `analysis/charts.py` + `--chart OUT.svg` on `analyze` and `fit-analyze`,
   taking the report dict, so the chart has the same inputs as the report. Pace (left axis, faster upwards)
   and cadence (right axis, dashed) per lap, with the easy/goal/tempo bands shaded behind them.
   **Inline SVG, not matplotlib**, which the acceptance allows: no dependency at all, renders in any browser,
   diffs as text. No PNG as a result; open the SVG and export if a raster is needed, or swap the module for
   matplotlib behind the same signature. Output is self-contained (no external fonts, scripts or images).
   13 tests, including XML validity, inverted pace axis, escaping, and that axis labels stay inside the
   canvas -- a screenshot showed "Cadence spm" clipped at the right edge, which no other test caught.
5. **Dedupe Strava vs Garmin runs** when both are cached (match on start time +/- 2 min and distance).
6. **MOSTLY DONE 2026-11-17: weekly summary.** `analysis/weekly.py` + `runcoach weekly [--weeks N]
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
8. **Wellness trends:** rolling HRV vs balanced range, resting-HR trend, a "weak markers for N nights" detector.

## P2: later
- Dashboard generator (static HTML) fed by the cache; the previous hand-made dashboard is a design reference.
- Strava webhooks instead of polling; SQLite instead of JSON files; typed models (dataclasses/TypedDict) for REST shapes.
- Packaging for easier install; CLI integration tests; Windows path edge cases.

## Known issues and risks
- Real FIT run files are untested (see P0 item 2). Live Strava calls were verified on 2026-10-12.
- `load` starts the series `--days` before the last activity and seeds it with `--ctl0/--atl0`; without long history
  CTL is understated. Use a long `sync` (in rate-limit-sized chunks) or seed from a known value.
- `load --source suffer` silently falls back to TRIMP for activities without `suffer_score`; mixing scales gives
  misleading CTL. Consider failing loudly or marking mixed series.
- `analyze --kind strides|intervals` has no special logic yet; decoupling is meaningless for those.
- Wellness `stress_export_*` window semantics are loose; `sleep_start/end` use the watch's offset.
- `.env` parser is minimal (no inline comments or multi-line values).
- Tokens are stored unencrypted; `chmod 0600` has no effect on Windows.
- The sleep-window and body-battery messages are undocumented and may change with firmware.
- Rate limits for the owner's app: overall 200 per 15 minutes / 2,000 per day; read 100 per 15 minutes / 1,000 per day
  (from the Strava API page). A sync used about 2 counted requests per run in practice, less than the 3 calls made.
