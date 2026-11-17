"""Garmin wellness: sleep, HRV, resting HR, stress, body battery from daily FIT exports.

Message names come from the FIT library where it knows them (sleep_assessment, hrv_status_summary,
monitoring, stress_level ...). Two messages are not in the public profile and are read by their
observed numbers: unknown_521 (sleep window) and unknown_407 (body battery event). Those two are
empirical; if a firmware update changes them the related columns come back empty, not wrong.
"""
from __future__ import annotations

import datetime as dt
import statistics
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

from .reader import FIT_EPOCH, Message, fit_seconds, fit_time

MIN_NIGHT_MINUTES = 120          # shorter windows are naps


@dataclass
class Night:
    wake_date: dt.date
    sleep_start: dt.datetime            # local time
    sleep_end: dt.datetime              # local time
    duration_min: float
    score: int | None = None
    score_parts: dict = field(default_factory=dict)
    awake_min_summary: float | None = None
    stage_min: dict = field(default_factory=dict)      # ESTIMATE, see stage_minutes()
    hrv_last_night: float | None = None
    hrv_weekly: float | None = None
    hrv_status: str | None = None
    hrv_baseline: tuple[float | None, float | None, float | None] = (None, None, None)  # low_upper, bal_lower, bal_upper
    hrv_5min_high: float | None = None
    sleep_low_hr: int | None = None                    # median of the 5 lowest HR samples in the sleep window
    garmin_rhr: int | None = None                      # Garmin's resting_heart_rate in the export
    garmin_rhr_today: int | None = None
    stress_sleep_avg: float | None = None
    stress_export_avg: float | None = None
    stress_export_max: int | None = None
    resp_avg: float | None = None
    body_battery_delta: int | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["wake_date"] = self.wake_date.isoformat()
        d["sleep_start"] = self.sleep_start.isoformat(timespec="minutes")
        d["sleep_end"] = self.sleep_end.isoformat(timespec="minutes")
        return d


# ---- timestamps -----------------------------------------------------------------------------
def monitoring_samples(messages: Iterable[Message]):
    """Yield (utc_datetime, heart_rate) for monitoring messages, expanding 16-bit timestamps."""
    last_full: dict[str, int] = {}
    for m in messages:
        ts = m.fields.get("timestamp")
        if ts is not None:
            last_full[m.file] = fit_seconds(fit_time(ts))
        if m.name != "monitoring":
            continue
        hr = m.fields.get("heart_rate")
        if not hr:
            continue
        if ts is not None:
            secs = fit_seconds(fit_time(ts))
        else:
            ts16 = m.fields.get("timestamp_16")
            base = last_full.get(m.file)
            if ts16 is None or base is None:
                continue
            secs = (base & ~0xFFFF) | int(ts16)
            if secs < base:
                secs += 0x10000
            last_full[m.file] = secs
        yield FIT_EPOCH + dt.timedelta(seconds=secs), int(hr)


def local_offset(messages: Iterable[Message]) -> dt.timedelta:
    """Device clock offset from monitoring_info (local_timestamp - timestamp)."""
    offset = None
    for m in messages:
        if m.name == "monitoring_info":
            a, b = fit_time(m.fields.get("timestamp")), fit_time(m.fields.get("local_timestamp"))
            if a and b:
                offset = b - a
    return offset if offset is not None else dt.timedelta(0)


# ---- stages (estimate) -------------------------------------------------------------------------
def stage_minutes(levels, start: dt.datetime, end: dt.datetime) -> dict:
    """Minutes per sleep stage from sleep_level messages.

    ASSUMPTION: each message's timestamp marks the END of that stage (so the stage lasted from the
    previous timestamp, or the sleep start, to this one). That reading fits one night's totals and
    scores but is not documented; verify one night against Garmin Connect before relying on it.
    """
    out: dict[str, float] = {}
    seg_start = start
    for ts, level in sorted(levels):
        out[level] = out.get(level, 0.0) + max(0.0, (ts - seg_start).total_seconds() / 60.0)
        seg_start = max(seg_start, ts)
    tail = (end - seg_start).total_seconds() / 60.0
    if tail > 1:
        out["unassigned"] = tail
    return {k: round(v, 1) for k, v in out.items()}


# ---- main entry ---------------------------------------------------------------------------------
def summarize_messages(messages: list[Message]) -> list[Night]:
    """Summaries for every full night found in one export (usually exactly one)."""
    offset = local_offset(messages)
    hr_samples = list(monitoring_samples(messages))

    stress = [(fit_time(m.fields.get("stress_level_time")), m.fields.get("stress_level_value"))
              for m in messages if m.name == "stress_level"]
    stress_vals = [v for _, v in stress if v is not None and v >= 0]
    resp = [m.fields["respiration_rate"] for m in messages
            if m.name == "respiration_rate" and (m.fields.get("respiration_rate") or 0) > 0]
    hrv_summaries = sorted(
        [(fit_time(m.fields.get("timestamp")), m.fields) for m in messages if m.name == "hrv_status_summary"],
        key=lambda x: x[0] or FIT_EPOCH)
    rhr_msgs = sorted(
        [(fit_time(m.fields.get("timestamp")), m.fields) for m in messages if m.name == "monitoring_hr_data"],
        key=lambda x: x[0] or FIT_EPOCH)
    bb_events = [m.fields for m in messages if m.name == "unknown_407"]
    levels_by_file: dict[str, list] = {}
    for m in messages:
        if m.name == "sleep_level" and m.fields.get("timestamp") is not None:
            levels_by_file.setdefault(m.file, []).append((fit_time(m.fields["timestamp"]), m.fields.get("sleep_level")))
    assessments = {m.file: m.fields for m in messages if m.name == "sleep_assessment"}

    nights: list[Night] = []
    for m in messages:
        if m.name != "unknown_521":
            continue
        start, end = fit_time(m.fields.get("unknown_3")), fit_time(m.fields.get("unknown_5"))
        if not start or not end:
            continue
        minutes = (end - start).total_seconds() / 60.0
        if minutes < MIN_NIGHT_MINUTES:
            continue
        night = Night(wake_date=(end + offset).date(),
                      sleep_start=(start + offset).replace(tzinfo=None),
                      sleep_end=(end + offset).replace(tzinfo=None),
                      duration_min=round(minutes, 1))
        if m.fields.get("unknown_9") is not None:
            night.awake_min_summary = round(m.fields["unknown_9"] / 60.0, 1)

        assess = assessments.get(m.file) or {}
        night.score = assess.get("overall_sleep_score", m.fields.get("unknown_1"))
        night.score_parts = {k: assess[k] for k in (
            "sleep_quality_score", "sleep_duration_score", "deep_sleep_score", "light_sleep_score",
            "awake_time_score", "awakenings_count_score", "combined_awake_score") if assess.get(k) is not None}
        night.stress_sleep_avg = assess.get("average_stress_during_sleep")
        if levels_by_file.get(m.file):
            night.stage_min = stage_minutes(levels_by_file[m.file], start, end)

        later = [f for ts, f in hrv_summaries if ts and end - dt.timedelta(hours=3) <= ts <= end + dt.timedelta(hours=36)]
        if later:
            f = later[0]
            night.hrv_last_night = f.get("last_night_average")
            night.hrv_weekly = f.get("weekly_average")
            night.hrv_status = f.get("status")
            night.hrv_5min_high = f.get("last_night_5_min_high")
            night.hrv_baseline = (f.get("baseline_low_upper"), f.get("baseline_balanced_lower"),
                                  f.get("baseline_balanced_upper"))

        window = sorted(hr for ts, hr in hr_samples if start <= ts <= end)
        if len(window) >= 5:
            night.sleep_low_hr = int(statistics.median(window[:5]))
        if rhr_msgs:
            night.garmin_rhr = rhr_msgs[-1][1].get("resting_heart_rate")
            night.garmin_rhr_today = rhr_msgs[-1][1].get("current_day_resting_heart_rate")

        if stress_vals:
            night.stress_export_avg = round(sum(stress_vals) / len(stress_vals), 1)
            night.stress_export_max = int(max(stress_vals))
        if resp:
            night.resp_avg = round(sum(resp) / len(resp), 1)

        start_secs = fit_seconds(start)
        for bb in bb_events:
            t = bb.get("unknown_253")
            if t is not None and abs(int(t) - start_secs) <= 300 and bb.get("unknown_2") is not None:
                night.body_battery_delta = int(bb["unknown_2"])
                break
        nights.append(night)
    return nights
