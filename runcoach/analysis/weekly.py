"""Weekly training summary: distance, time, runs and the CTL/ATL/TSB line at each week's end.

Weeks run Monday to Sunday (docs/COACHING_CONTEXT.md section 3).

Deliberately NOT included: planned vs actual. The roadmap lists it under this item, but the plan exists only
as prose in COACHING_CONTEXT ("4-5 runs, one quality session, a long run, strides"), not as data this code
can read. Comparing against a plan invented here would be worse than omitting it. Roadmap P1.7 ("plan as
data") is the item that unblocks it; once a plan file exists, add the planned columns here.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping

from ..metrics.load import load_series
from ..metrics.pace import fmt_pace, fmt_time

WEEK_DAYS = 7


def week_start(day: dt.date) -> dt.date:
    """The Monday of the week containing `day`."""
    return day - dt.timedelta(days=day.weekday())


def summarize_weeks(activities: Iterable[dict], daily_loads: Mapping[dt.date, float], weeks: int = 4,
                    ctl0: float = 0.0, atl0: float = 0.0) -> list[dict]:
    """The last `weeks` Monday-to-Sunday weeks, newest last. Empty when there are no activities.

    `activities` are Strava-shaped (`start_date_local`, `distance`, `moving_time`). Load numbers come from
    `load_series` over the whole of `daily_loads`, so CTL accumulates over all cached history rather than
    only the weeks shown.
    """
    runs: list[tuple[dt.date, dict]] = []
    for act in activities:
        stamp = act.get("start_date_local")
        if not stamp:
            continue
        runs.append((dt.date.fromisoformat(stamp[:10]), act))
    if not runs:
        return []

    last_week = week_start(max(day for day, _ in runs))
    first_week = last_week - dt.timedelta(days=WEEK_DAYS * (weeks - 1))

    points = {}
    if daily_loads:
        points = {p.day: p for p in load_series(daily_loads, min(daily_loads), max(daily_loads), ctl0, atl0)}

    out = []
    for i in range(weeks):
        start = first_week + dt.timedelta(days=WEEK_DAYS * i)
        end = start + dt.timedelta(days=WEEK_DAYS - 1)
        in_week = [act for day, act in runs if start <= day <= end]
        distance = sum(float(a.get("distance") or 0.0) for a in in_week)
        moving = sum(int(a.get("moving_time") or 0) for a in in_week)
        # The load line is read at the week's end; if the cache stops earlier, use the last day it has.
        day_keys = [d for d in points if d <= end]
        point = points[max(day_keys)] if day_keys else None
        out.append({
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "runs": len(in_week),
            "distance_m": distance,
            "moving_s": moving,
            "avg_pace": moving / (distance / 1000.0) if distance and moving else None,
            "longest_m": max((float(a.get("distance") or 0.0) for a in in_week), default=0.0),
            "ctl": point.ctl if point else None,
            "atl": point.atl if point else None,
            "tsb": point.tsb if point else None,
        })
    return out


def render_markdown(summaries: list[dict]) -> str:
    """One row per week. Load columns are blank for a week with no cached load data."""
    if not summaries:
        return "No cached runs. Run `runcoach sync` first."
    lines = [
        "| Week (Mon-Sun) | Runs | Distance | Time | Avg pace | Longest | CTL | ATL | TSB |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for w in summaries:
        pace = fmt_pace(w["avg_pace"]) if w["avg_pace"] else "-"
        ctl = f"{w['ctl']:.1f}" if w["ctl"] is not None else "-"
        atl = f"{w['atl']:.1f}" if w["atl"] is not None else "-"
        tsb = f"{w['tsb']:+.1f}" if w["tsb"] is not None else "-"
        lines.append(f"| {w['week_start']} | {w['runs']} | {w['distance_m'] / 1000.0:.2f} km "
                     f"| {fmt_time(w['moving_s'])} | {pace} | {w['longest_m'] / 1000.0:.2f} km "
                     f"| {ctl} | {atl} | {tsb} |")
    lines.append("")
    lines.append("Planned vs actual is not shown: the plan is not yet available as data (roadmap P1.7).")
    return "\n".join(lines)
