# FIT and Garmin wellness notes

Everything here was learned from the owner's real exports (Forerunner 165, daily zips, July-October 2026)
and from the FIT library's behaviour. Treat the "empirical" items as assumptions that need re-checking
after firmware updates.

## 1. What is in a daily export zip
File names are `<12-digit id>_<TYPE>.fit`. The description below comes from 81 nights of exports (July to October 2026).

| Type | Contents | Used for |
|---|---|---|
| `WELLNESS` | monitoring HR samples, stress, respiration, resting HR, body battery events | HR in sleep window, stress, respiration, RHR |
| `SLEEP_DATA` | sleep assessment (score + parts), sleep stages, sleep window | score, duration, stages |
| `HRV_STATUS` | `hrv_status_summary` | HRV, baseline, status |
| `SLEEP_DISRUPTIONS` | unknown messages (470/471) | not used |
| `METRICS` | unknown messages (241/339) | not used |
| `NAP` | nap windows | skipped (nights need >= 120 min) |
| `ACTIVITY` | only one file in all zips, and it was a 2-minute "Health Snapshot", not a run | not a run source |

A daily zip usually contains one night. A folder of zips is handled one export at a time (`iter_groups`).

## 2. Message mapping (fitdecode names)
| Message | Fields used | Notes |
|---|---|---|
| `sleep_assessment` | `overall_sleep_score`, `sleep_quality_score`, `sleep_duration_score`, `deep_sleep_score`, `light_sleep_score`, `awake_time_score`, `awakenings_count_score`, `combined_awake_score`, `average_stress_during_sleep` | one per night |
| `sleep_level` | `timestamp`, `sleep_level` (`light`, `deep`, `rem`, `awake`) | timestamp semantics are an assumption (section 4) |
| `hrv_status_summary` | `weekly_average`, `last_night_average`, `last_night_5_min_high`, `baseline_low_upper`, `baseline_balanced_lower`, `baseline_balanced_upper`, `status` (`balanced`, ...) | status follows the 7-day average against the balanced range, so one low night can still read `balanced` |
| `hrv_value` | `timestamp`, `value` | 5-minute values during sleep; not read (the summary message is enough) |
| `monitoring` | `heart_rate`, `timestamp` or `timestamp_16` | most rows carry **only** the low 16 bits; see section 3 |
| `monitoring_info` | `timestamp`, `local_timestamp` | local offset = local - UTC |
| `monitoring_hr_data` | `resting_heart_rate`, `current_day_resting_heart_rate` | Garmin's own RHR; the last message in the export is used |
| `stress_level` | `stress_level_time`, `stress_level_value` | negative values = not measurable, ignored |
| `respiration_rate` | `timestamp`, `respiration_rate` | values <= 0 ignored |

### Empirical (unknown) messages
| Message | Field -> meaning | Evidence |
|---|---|---|
| `unknown_521` (sleep window) | `unknown_3` start (FIT s), `unknown_5` end, `unknown_9` awake seconds (summary), `unknown_1` score, `unknown_253` record time (end + ~76 s), `unknown_0` local time | duration matched the app on 8 nights; score matched `sleep_assessment` |
| `unknown_407` (body battery event) | `unknown_253` start (FIT s), `unknown_1` minutes, `unknown_2` change, `unknown_7` end | change matched earlier hand-extracted values on 8 nights |
| `unknown_408` | similar shape to 407; meaning not established | not used |

## 3. Timestamps
- FIT epoch is 1989-12-31 00:00:00 UTC. Known fields arrive as aware datetimes; unknown fields arrive as epoch seconds
  (`reader.fit_time` handles both).
- `timestamp_16` expansion (`wellness.monitoring_samples`): keep the last full timestamp **per file**;
  `ts = (last & ~0xFFFF) | ts16`, add `0x10000` if `ts < last` (16-bit rollover).
- Local time uses the watch's own offset from `monitoring_info`. Nights spent in another time zone follow the
  watch setting, not the location.

## 4. Open assumptions to verify
1. **Sleep stages: SETTLED 2026-11-17, the assumption was right.** Each `sleep_level` timestamp marks the
   **end** of that stage. Checked against a Garmin Connect export for the night of 2026-10-19: Connect shows
   deep 1h49, light 4h04, REM 1h16, awake 18m, and `stage_minutes` gives 109 / 244 / 76 / 18. All four match
   exactly. Score, HRV, resting HR, stress and body battery matched that night too.
   **But `duration_min` does not match Connect's "Sleep Duration".** Connect reports 7h09 (429 min) and
   runcoach reports 7h27 (447 min); the difference is exactly the 18 minutes awake. Connect's Sleep Duration
   is deep + light + REM and **excludes awake**, while `duration_min` is the whole sleep window. A second
   night (Nov 15: 1h25 + 4h24 + 22m = 6h11, awake 49m shown separately) confirms the same rule.
   **Open decision for the owner, not changed unilaterally:** `COACHING_CONTEXT.md` records 377 min for the
   night of 2026-10-11/12 as validated by hand, and that figure includes awake (103 + 206 + 61 + 7). Under
   Connect's definition the same night is 370 min. Changing `duration_min` would move a pinned golden number,
   so it needs the owner to say which number the reports should carry.
2. `awake_min_summary` (summary field, 29.4 min on that night) differs from the stage-derived awake minutes (7).
   They probably measure different things; confirm in the app. Connect's "Awake Time" matches the
   stage-derived value (18 min on 2026-10-19), so `stage_min["awake"]` is the one that lines up with the app.
3. `stress_export_avg/max` cover everything in that export (roughly the day before the morning of export), not a
   calendar day. Prefer `stress_sleep_avg` for night-to-night comparisons.
4. `sleep_low_hr` (median of the 5 lowest HR samples in the sleep window) and Garmin's `resting_heart_rate` differ
   by design; pick one for trends.
5. HRV status strings other than `balanced` have not been seen in the data.

## 5. Activity (run) FIT files
- Messages: `session` (summary), `lap`, `record` (1 Hz), `activity` (UTC to local offset).
- Record fields used: `timestamp`, `distance`, `enhanced_speed` (else `speed`), `heart_rate`, `cadence`,
  `enhanced_altitude` (else `altitude`).
- **Cadence naming trap:** for `sport = running` the FIT library renames `avg_cadence` to `avg_running_cadence`
  on `lap` and `session`. Both names are handled. Cadence is strides per minute of one foot; multiply by 2 for spm.
- Laps use `total_timer_time` as moving time and `total_elapsed_time` for index ranges.
- Grade comes from smoothed altitude over +/- 10 s of travel (watch barometer). It will differ slightly from
  Strava's `grade_smooth`.
- Untested on a real run file. First real test: export the run from Garmin Connect (activity > gear icon > Export
  Original), run `fit-analyze`, and compare distance, moving time, average HR, average cadence and lap paces with
  Strava or the watch.

## 6. Watch settings seen in a file
`zones_target` held max HR 193 and threshold HR 165 (watch settings). The coaching estimate of threshold is about
168-170 and the highest observed HR is about 177; set `hr_max` and `hr_rest` in `profile.toml` accordingly.
