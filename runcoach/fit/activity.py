"""Turn a Garmin activity FIT file into the same structures the Strava path produces."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .reader import Message, fit_time

GAP_FILL_S = 10          # fill short sensor gaps; longer gaps (pauses) stay empty
GRADE_HALF_WINDOW = 10   # seconds either side for the grade estimate


@dataclass
class FitRun:
    activity: dict
    laps: list[dict]
    streams: dict


def _fill(values: list, max_gap: int = GAP_FILL_S) -> list:
    out = list(values)
    last_i = None
    for i, v in enumerate(out):
        if v is None:
            continue
        if last_i is not None and 1 < i - last_i <= max_gap:
            for j in range(last_i + 1, i):
                out[j] = out[last_i]
        last_i = i
    return out


def _smooth(values: list, half: int) -> list:
    out = []
    for i in range(len(values)):
        window = [v for v in values[max(0, i - half): i + half + 1] if v is not None]
        out.append(sum(window) / len(window) if window else None)
    return out


def grade_stream(altitude: list, distance: list, half: int = GRADE_HALF_WINDOW) -> list:
    """Percent grade from smoothed altitude over +/- half seconds of travel."""
    alt = _smooth(altitude, 3)
    grade = []
    for i in range(len(alt)):
        a, b = max(0, i - half), min(len(alt) - 1, i + half)
        if None in (alt[a], alt[b], distance[a], distance[b]):
            grade.append(None)
            continue
        d = distance[b] - distance[a]
        grade.append(None if d < 5 else max(-30.0, min(30.0, (alt[b] - alt[a]) / d * 100.0)))
    return grade


def activity_from_messages(msgs: list[Message]) -> FitRun:
    sessions = [m for m in msgs if m.name == "session"]
    if not sessions:
        raise ValueError("No session message found: is this an activity FIT file?")
    session = sessions[0].fields
    records = [m.fields for m in msgs if m.name == "record" and m.fields.get("timestamp") is not None]
    if not records:
        raise ValueError("No record messages found: the activity has no time series.")

    act_msg = next((m.fields for m in msgs if m.name == "activity"), {})
    start = fit_time(session.get("start_time") or records[0]["timestamp"])
    local_ts, utc_ts = fit_time(act_msg.get("local_timestamp")), fit_time(act_msg.get("timestamp"))
    offset = (local_ts - utc_ts) if (local_ts and utc_ts) else dt.timedelta(0)

    last = fit_time(records[-1]["timestamp"])
    n = int((last - start).total_seconds()) + 1
    cols = {k: [None] * n for k in ("distance", "speed", "heartrate", "cadence", "altitude")}
    for rec in records:
        i = int(round((fit_time(rec["timestamp"]) - start).total_seconds()))
        if not 0 <= i < n:
            continue
        cols["distance"][i] = rec.get("distance")
        cols["speed"][i] = rec.get("enhanced_speed", rec.get("speed"))
        cols["heartrate"][i] = rec.get("heart_rate")
        cols["cadence"][i] = rec.get("cadence")
        cols["altitude"][i] = rec.get("enhanced_altitude", rec.get("altitude"))
    for k in cols:
        cols[k] = _fill(cols[k])
    grade = grade_stream(cols["altitude"], cols["distance"])

    streams = {
        "time": {"data": list(range(n))},
        "distance": {"data": cols["distance"]},
        "velocity_smooth": {"data": cols["speed"]},
        "heartrate": {"data": cols["heartrate"]},
        "cadence": {"data": cols["cadence"]},
        "altitude": {"data": cols["altitude"]},
        "grade_smooth": {"data": grade},
    }

    laps = []
    for m in (x for x in msgs if x.name == "lap"):
        f = m.fields
        lap_start = fit_time(f.get("start_time"))
        if lap_start is None or not f.get("total_distance"):
            continue
        s = int(round((lap_start - start).total_seconds()))
        elapsed = f.get("total_elapsed_time") or f.get("total_timer_time") or 0
        laps.append({
            "distance": f["total_distance"],
            "moving_time": f.get("total_timer_time") or elapsed,
            "elapsed_time": elapsed,
            "average_heartrate": f.get("avg_heart_rate"),
            "average_cadence": f.get("avg_running_cadence", f.get("avg_cadence")),
            "start_index": max(0, s),
            "end_index": min(n - 1, s + int(round(elapsed)) - 1),
        })

    sport = str(session.get("sport") or "running")
    activity = {
        "name": f"{sport.capitalize()} {(start + offset).date().isoformat()}",
        "sport_type": "Run" if sport == "running" else sport,
        "start_date_local": (start + offset).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "distance": session.get("total_distance"),
        "moving_time": session.get("total_timer_time"),
        "elapsed_time": session.get("total_elapsed_time"),
        "average_heartrate": session.get("avg_heart_rate"),
        "max_heartrate": session.get("max_heart_rate"),
        "average_cadence": session.get("avg_running_cadence", session.get("avg_cadence")),
        "total_elevation_gain": session.get("total_ascent"),
        "source": "garmin-fit",
    }
    return FitRun(activity, laps, streams)


def cache_id(run: FitRun) -> str:
    """Stable cache key from the start time, e.g. fit-20261011072225."""
    stamp = run.activity["start_date_local"].replace("-", "").replace(":", "").replace("T", "").rstrip("Z")
    return f"fit-{stamp}"
