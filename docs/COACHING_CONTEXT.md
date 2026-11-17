# Coaching context (domain knowledge the code must respect)

This file captures what was agreed during the coaching sessions this project grew out of. It is the "why"
behind thresholds and wording. Personal training data: do not publish the repository.

## 1. Analysis conventions (standing instructions)
1. **Decoupling:** exclude the first km, split the rest in halves, compare efficiency (speed / HR). Report raw and
   grade-adjusted; above about 5% on a flat steady run deserves a comment. Not meaningful for structured
   sessions (intervals, strides) or stop-start runs.
2. **Per-lap breakdown:** always show pace, **cadence** and average HR per lap. **Cadence is always included.**
3. **GAP:** Minetti polynomial. Show overall GAP and per-lap GAP; explain terrain effects, never over-claim.
4. **Cadence:** steps per minute (rpm x 2). Easy-day plateau is about 168 spm; strides target 181-191 spm.
5. **Efficiency:** speed per heartbeat x 1000. Compare like with like (same terrain, similar conditions).
6. **Be honest about bases:** moving vs elapsed time, Strava best-effort window, official chip time.
7. **Interpretation style:** flag what the data shows, say what it cannot show, no hype, no invented claims.
   Distinguish "plan" from "result".

## 2. Athlete profile values (defaults in `config.Profile`, overridable in `profile.toml`)
| Item | Value |
|---|---|
| Easy pace band | 6:39-7:16 /km |
| Goal pace band | 5:55-6:07 /km |
| Tempo band | 5:36-5:48 /km |
| Stride cadence | 181-191 spm |
| Easy/long HR guide | about 145 bpm or lower |
| HR zones (standing) | Z1 < 144, Z2 144-150, Z3 152-159, Z4 161-167, Z5 169+ |
| HR zones as coded | `Profile.hr_zones` holds the lower bounds (144, 152, 161, 169). The table above leaves 151, 160 and 168 bpm in no zone; the code assigns each to **the zone below**, confirmed by the owner 2026-11-17, so the seconds always add up. Change `hr_zones` in `profile.toml` to override. |
| LTHR estimate | about 168-170 (default 169). The watch's own setting is 165; the watch max HR is 193 but the highest observed is about 177. Set `hr_rest`/`hr_max` to real values before trusting TRIMP. |

## 3. Training plan context (Summarecon block, 9 weeks to Nov 22, 2026)
- Races: **RTG 5K** (Sun Oct 25) and **Summarecon Bandung Run Fest half marathon** (Sun Nov 22, target 2:07:00 = 6:01/km;
  good day 2:05:30-2:06:30; repeat-September baseline 2:08:38).
- 5K record to beat: 26:17 (Apr 26, from a threshold run). Cards: solid 27:00, target 26:40, PR attempt 26:10.
- Gate session (Wed Oct 14): 4 x 1 km; reps 3-4 at 5:02 or faster with HR <= 172 -> PR card; 5:03-5:10 -> target
  card; slower or HR above 172 -> solid card.
- Weeks run Monday to Sunday. Typical week: 4-5 runs, one quality session, a long run, strides, and (from Week 2)
  strength A/B in the evening.
- Readiness rules, and their status (do not present a proposal as an agreed rule):
  - **Confirmed (Oct 7 intervals):** run all 3 reps only if the sleep score is >= 60 and Garmin's HRV status is
    not Unbalanced, otherwise 2 reps; stop at 2 reps if HR passes 172 before rep 3.
  - **In the plan:** Friday strides can be shortened to Strides 30 if the legs feel flat.
  - **Suggested, not objected to (Oct 11 long run):** if the sleep score is < 60 or HRV reads Unbalanced, cut the
    long run to 60 minutes; keep easy/long HR near or below about 145.
  - **Proposed, NOT confirmed (Oct 14 gate session):** run 3 reps instead of 4 under the same sleep/HRV condition.
  - **Confirmed 2026-11-17:** a night counts as weak for `runcoach trends` when the sleep score is below 60,
    HRV status reads Unbalanced, or HRV is below the balanced range; **3 consecutive weak nights** raise the
    alert. The three conditions come from the rules above; the streak length was proposed by the tool and
    agreed by the owner, and stays adjustable with `--weak-nights`.
  - All four are coded in `analysis/readiness.py` (`runcoach readiness --kind ...`), each tagged with the
    status above. The thresholds live in that module (`SLEEP_FLOOR = 60`, `INTERVALS_HR_CAP = 172`). The
    HR-172 rule is reported as an in-session watch item, not a pre-session decision, because last night's
    data cannot settle it. The strides rule needs `--legs-flat`: there is no data source for how legs feel.
- Load model: CTL/ATL from Strava Relative Effort (42/7-day exponential), TSB = CTL - ATL.
  Strength sessions add almost nothing to this model and were excluded.

## 4. Things never to claim
- A "big negative split" when the second half was only about even.
- That a one-off session proves a fitness change.
- Strava best-effort windows, moving time and chip time are interchangeable.
- Sleep-stage minutes are exact (they are an estimate, see FIT notes).

## 5. Golden numbers (used in tests; keep reproducing them)
| Case | Value | Where |
|---|---|---|
| Oct 8 easy run decoupling (first km excluded) | 4.02% | `test_metrics`, `test_report` |
| Oct 11 long run decoupling raw / grade-adjusted | 6.92% / -1.33% | `test_metrics`, `test_report` |
| Oct 11 long run lap 10: pace 6:37, GAP 6:14 | `gap_pace(397, 1.1022)` | `test_metrics` |
| Efficiency (10030.5 m, 4185 s, 140.655 bpm) | 17.04 (live Strava run: 17.03) | `test_metrics` |
| Live Strava, Oct 11 long run, before the tail-lap rule | raw 7.01%, grade-adjusted -1.46% (tail lap + stream grade) | owner's run, 2026-10-12; reproduced exactly from the recorded response on 2026-11-17 |
| Oct 11 long run **with** the tail-lap rule, from the recorded response | raw 6.91%, grade-adjusted -1.54%, efficiency 17.03 | `test_recorded_strava`. The rule shifts raw 7.01 -> 6.91 and grade-adjusted -1.46 -> -1.54; only the raw effect had been recorded before |
| VDOT of 26:17 for 5 km / 2:08:21 for a half | 36.1 / 33.7 | `test_metrics` |
| CTL step from (17.94, 18.55) with load 19 | (17.96, 18.61) | `test_metrics` |
| Rest-day step from (18.20, 19.78) | (17.77, 17.15), TSB +0.62 | `test_metrics` |
| Banister TRIMP, 40 min at 143 bpm, rest 55, max 180 | about 69.7 | `test_metrics` |
| Wellness night Oct 11-12 | score 75, **370 min asleep / 377 in bed**, HRV 30 (7-day 27, balanced 27-34), BB +51 | validated by hand; the 377 originally recorded here is time in bed. Since 2026-11-17 `duration_min` follows Garmin Connect and excludes the 7 min awake |
| Wellness night Oct 18-19 | score 79, stages deep 109 / light 244 / REM 76 / awake 18, HRV 31, RHR 56, stress 19, BB +51 | matches the Garmin Connect export exactly (2026-11-17); Connect's Sleep Duration 7h09 excludes awake |

## 6. Data quirks learned the hard way
- Strava streams: the `resolution` parameter downsamples **differently per request**. Never mix arrays from separate
  calls. Laps index into full-resolution streams.
- Cadence streams contain glitch samples (0, 41, 55, 57). Drop values below 60 rpm.
- The chat connector used `avg_hr`, `relative_effort`; the REST API uses `average_heartrate`, `suffer_score`.
- Shoe mileage: trust Strava gear totals, not running tallies.
- A race lap can include a stop (a prayer stop cost about 1:34 in one race): say so instead of calling it a fade.
