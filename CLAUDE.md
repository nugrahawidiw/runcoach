# runcoach: project guide for Claude Code

## What this is
A personal Python tool that automates running-coaching analysis that was previously done by hand in a chat.
It reads **Strava API** data and **Garmin FIT files** and produces: per-lap pace, grade-adjusted pace (GAP),
aerobic decoupling, cadence, efficiency, VDOT, CTL/ATL/TSB, and Garmin wellness (sleep, HRV, resting HR,
stress, body battery). Single user, single machine. No web server, no database.

## About the owner (adjust how you work)
- Windows (Command Prompt). The project path contains a space, so always quote paths.
- Explain in plain language. Give exact Windows commands. Say what you are about to change and why before
  large edits. Ask before adding dependencies or restructuring modules.
- Training context (race targets, pace bands, readiness rules) lives in `docs/COACHING_CONTEXT.md`.

## Commands
```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest                          # must stay green; 34 tests; all offline
python -m runcoach --help
python -m runcoach auth | sync --days 7 | analyze latest --kind long | load | vdot 26:17 5000
python -m runcoach fit-analyze "path\run.fit" | fit-import "path\run.fit"
python -m runcoach wellness "path\2026-10-12.zip" [--csv nights.csv]
python -m runcoach readiness "path\2026-10-12.zip" --kind intervals|long|strides|gate [--legs-flat]
python -m runcoach weekly [--weeks 9] [--ctl0 17.13 --atl0 12.98] [--plan plan.toml]
python -m runcoach plan plan.toml [--ics plan.ics]
python -m runcoach analyze latest --kind long --chart long.svg   # inline SVG, no dependency
python -m runcoach trends "path\Garmin" [--window 7] [--weak-nights 3]
python -m runcoach dedupe [--prefer strava|garmin]
python scripts/gen_api_docs.py            # regenerate docs/API_REFERENCE.md after changing signatures
```
Use `python -m runcoach ...` rather than a bare `runcoach` (Windows PATH issues). Secrets live in `.env`
(git-ignored); config in `profile.toml` (optional).

## Layout
```
runcoach/
  cli.py                  argparse commands; thin, calls the layers below
  config.py               Profile (pace bands, HR guide ...), .env loader, data dir
  strava/                 auth.py (OAuth), client.py (REST), cache.py (JSON files), sync.py, errors.py
  fit/                    reader.py (fitdecode -> Message), wellness.py (nights), activity.py (runs)
  metrics/                pace, gap, decoupling, cadence, load (TRIMP, CTL), vdot, zones  (pure functions)
  analysis/run_report.py  build_report(activity, laps, streams, profile) -> dict ; render_markdown
  analysis/readiness.py   evaluate(night, kind) -> dict ; render_markdown (rule status is carried through)
  analysis/weekly.py      summarize_weeks(activities, daily_loads, weeks, plan) -> list[dict] ; render_markdown
  analysis/plan.py        load_plan(plan.toml) ; compare(plan, activities) ; to_ics (needs the 'ics' extra)
  analysis/charts.py      pace_cadence_svg(report, profile) -> str  (inline SVG, no dependency)
  analysis/wellness_trends.py  summarize(nights, window, weak_nights) -> dict ; render_markdown
  analysis/session.py     detect_structure(laps, profile, kind) -> reps/recoveries for intervals & strides
  analysis/dedupe.py      find_duplicate_groups / resolve: one run cached from Strava and a FIT import
                          (load, weekly and plan go through cli._cached_activities, so it counts once)
tests/                    pytest; fixtures.py has REAL laps from the coaching sessions; fitwriter.py writes FIT files
  data/                   sanitized recorded Strava REST responses (P0.1); see test_recorded_strava.py
docs/                     ARCHITECTURE, COACHING_CONTEXT, FIT_AND_WELLNESS_NOTES, ROADMAP, API_REFERENCE (generated)
```
Data flow: Strava API or FIT file -> (activity dict, laps list, streams dict) in Strava REST shape ->
`build_report` -> markdown/JSON. Both sources are converted to the **same shapes** so metrics are written once.

## Rules that matter
- **Units:** pace = seconds per km everywhere; cadence from Strava/FIT is ONE foot (rpm), report steps/min
  = rpm x 2 (`metrics/cadence.py`); distances in metres; times in seconds; grade in percent.
- **Never hand-type data** (arrays, laps) into code or docs. Earlier transcription slips caused real errors.
  Load from files/API; tests may use `tests/fixtures.py`.
- **Units, continued:** sleep `duration_min` is deep + light + REM, as Garmin Connect reports it; the whole
  sleep window is `time_in_bed_min`. The two differ by the awake minutes.
- **Do not change a formula without its test.** `tests/test_metrics.py` pins values from real sessions
  (decoupling 4.02% / 6.92% / -1.33%, VDOT 36.1 / 33.7, CTL steps, TRIMP 69.7). If a change moves them, say so.
- **Tests stay offline.** No real network calls, no real tokens. Mock the session (see `tests/test_client.py`).
  FIT behaviour is tested by writing real FIT bytes (`tests/fitwriter.py`).
- **Secrets:** never print, log, commit or paste `.env`, tokens or the client secret. If one leaks, rotate it.
- **Label time bases:** moving vs elapsed vs Strava best-effort window vs chip time are different numbers.
- Keep dependencies minimal (`requests`, `fitdecode`; `pytest`/`ruff`/`pre-commit` for dev; `icalendar`
  only for `plan --ics`, in the `ics` extra and imported lazily). Python >= 3.11 (uses `tomllib`).
- Style: type hints, `from __future__ import annotations`, one-line docstring minimum on public functions,
  small functions. Lint with `ruff check .` (configured in `pyproject.toml`); `pre-commit install`
  runs it plus the test suite on every commit.

## Before coding
- State your assumptions. If the request has two possible readings, present both rather than silently
  picking one. If something is unclear, stop and name what is confusing.
- Turn the task into a verifiable goal first: "fix the bug" -> "write a test that reproduces it, then make
  it pass". For multi-step work, give the plan with the check for each step.
- (These three points are adapted from a public Karpathy post, via `multica-ai/andrej-karpathy-skills`.)

## Do not do these
Scope and output discipline. These are the failure modes that cost the most to undo.
- **No files nobody asked for.** No `SUMMARY.md`, `NOTES.md`, `MIGRATION.md`, refactor plans or scratch
  scripts. Answer in the chat instead. Edit existing `docs/*.md` only when behaviour or assumptions changed.
- **No comments that restate the code.** A comment earns its place by explaining *why*, a unit, or a gotcha.
- **Let it fail loudly.** No `try/except` that swallows an error, and no silent fallback or default that
  invents a number. In this project a wrong pace is far worse than a traceback.
- **No unrequested abstraction.** No new base classes, config options, CLI flags, caching layers or
  "while I was in there" generalisations. The metrics are plain functions; keep them that way.
- **One roadmap item at a time.** Do not widen the task. Note anything else you spot and move on.
- **Mention unrelated dead code; do not delete it.** Remove only the imports and variables that *your* change
  orphaned. Pre-existing dead code is the owner's call, not yours: report it and move on.
- **No error handling for impossible scenarios.** And if you wrote 200 lines where 50 would do, rewrite it.
- **Do not reformat or reorder code you did not change.** The owner reviews diffs by reading them; a diff
  with 200 cosmetic lines cannot be reviewed.
- **No emoji** in code, docs, commit messages or CLI output.
- **Do not tell the owner a number is right because the code looks right.** Run it.

## Working cheaply (this project is small; keep context small too)
- Start with this file plus `docs/API_REFERENCE.md`, which lists every function. Do not sweep the tree with
  `grep` or read whole modules to find one signature.
- Read the line range you need, not the whole file. Re-reading a file you already read in this session is
  pure waste.
- `reference/CHAT_CONTEXT.md` (187 lines) is history, not a prerequisite. Read it only when the task turns on
  a past decision or a mistake already made, not at the start of every session.
- If the `codebase-memory` MCP server is connected, `search_graph` / `get_file_outline` / `trace_path` answer
  "where is X" and "what calls X" far more cheaply than reading files.
- Long command output: pipe to `tail`, or ask for the one number you need.

## Verified vs not verified (be honest about this in reports)
- Verified: all metric formulas (against real sessions); wellness reader on 8 real nights (score, duration,
  HRV, low HR, body battery); FIT activity path on a synthetic FIT file; **live Strava path on 2026-10-12**
  (`auth`, `sync`, `analyze`, `load`, `vdot` all worked on the owner's real account; see `docs/ROADMAP.md`).
- NOT verified: FIT **run** files from a real watch (no real run file was available); sleep-stage minutes
  (an assumption, see `docs/FIT_AND_WELLNESS_NOTES.md`).
- First task in any new session about data: run the real thing and compare with known numbers, then add a
  sanitized fixture test for whatever differed.

## Where to look
- Architecture and data shapes: `docs/ARCHITECTURE.md`
- Coaching rules, thresholds, golden numbers: `docs/COACHING_CONTEXT.md`
- FIT message mappings and gotchas: `docs/FIT_AND_WELLNESS_NOTES.md`
- Backlog with acceptance criteria: `docs/ROADMAP.md`
- Every function: `docs/API_REFERENCE.md` (generated)
- Conversation history, decisions, standing instructions, mistakes to avoid, current state: `reference/CHAT_CONTEXT.md`
  (git-ignored, personal data)

## Definition of done
No step here is satisfied by inspection. Run the thing.
1. `python -m pytest` actually run, and the real count reported (162 passed today). Never write "tests pass"
   without the output in front of you. If you did not run them, say so.
2. New behaviour has a test. A changed formula shows the pinned numbers before and after.
3. Docs updated: `python scripts/gen_api_docs.py` after signature changes; edit `docs/*.md` if behaviour or
   assumptions changed.
4. No secrets in the diff.
5. State plainly what you did **not** test, and give the owner the exact command to try it.
