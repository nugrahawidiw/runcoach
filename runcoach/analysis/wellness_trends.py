"""Wellness trends: rolling HRV against Garmin's balanced range, resting-HR trend, and weak-night runs.

The roadmap asks for a "weak markers for N nights" detector but does not define weak. Rather than invent
thresholds, a night counts as weak when any of these holds, each already established elsewhere:

  * sleep score below SLEEP_FLOOR (60), the confirmed threshold in COACHING_CONTEXT section 3
  * Garmin's HRV status reads Unbalanced, the same signal the confirmed readiness rule uses
  * last night's HRV sits below Garmin's own balanced range for this athlete (hrv_baseline[1])

How many consecutive weak nights raise the alert was the one free choice here. It was proposed as 3 and
agreed by the owner on 2026-11-17, so 3 is the agreed default; `--weak-nights` still changes it.

Nothing is inferred from missing data: a night with no sleep score and no HRV is simply not weak, and the
reasons list says what was actually seen.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..fit.wellness import Night
from .readiness import SLEEP_FLOOR

DEFAULT_WINDOW = 7          # nights in the rolling HRV mean; matches Garmin's own 7-day average
DEFAULT_WEAK_NIGHTS = 3     # agreed with the owner 2026-11-17; see the module docstring


def _band(night: Night) -> str | None:
    """Where last night's HRV sits against Garmin's balanced range: below, in, above, or None."""
    value, lo, hi = night.hrv_last_night, night.hrv_baseline[1], night.hrv_baseline[2]
    if value is None or lo is None or hi is None:
        return None
    if value < lo:
        return "below"
    return "above" if value > hi else "in"


def _reasons(night: Night, band: str | None) -> list[str]:
    out = []
    if night.score is not None and night.score < SLEEP_FLOOR:
        out.append(f"sleep score {night.score} < {SLEEP_FLOOR}")
    if (night.hrv_status or "").strip().lower() == "unbalanced":
        out.append("HRV status Unbalanced")
    if band == "below":
        out.append("HRV below the balanced range")
    return out


def summarize(nights: Sequence[Night], window: int = DEFAULT_WINDOW,
              weak_nights: int = DEFAULT_WEAK_NIGHTS) -> dict:
    """Per-night rows oldest first, plus the trailing weak-night streak and the resting-HR trend."""
    ordered = sorted(nights, key=lambda n: n.wake_date)
    rows = []
    for i, night in enumerate(ordered):
        seen = [n.hrv_last_night for n in ordered[max(0, i - window + 1):i + 1] if n.hrv_last_night is not None]
        band = _band(night)
        reasons = _reasons(night, band)
        rows.append({
            "wake_date": night.wake_date.isoformat(),
            "sleep_score": night.score,
            "hrv": night.hrv_last_night,
            "hrv_rolling": sum(seen) / len(seen) if seen else None,
            "hrv_band": band,
            "hrv_status": night.hrv_status,
            "rhr": night.garmin_rhr,
            "weak": bool(reasons),
            "reasons": reasons,
        })

    streak = 0
    for row in reversed(rows):
        if not row["weak"]:
            break
        streak += 1

    rhr_values = [(r["wake_date"], r["rhr"]) for r in rows if r["rhr"] is not None]
    rhr_trend = None
    if len(rhr_values) >= 2:
        rhr_trend = {
            "first": rhr_values[0][1], "first_date": rhr_values[0][0],
            "last": rhr_values[-1][1], "last_date": rhr_values[-1][0],
            "delta": rhr_values[-1][1] - rhr_values[0][1],
            "mean": sum(v for _, v in rhr_values) / len(rhr_values),
        }

    return {
        "window": window,
        "weak_nights_threshold": weak_nights,
        "nights": rows,
        "weak_streak": streak,
        "alert": streak >= weak_nights and streak > 0,
        "rhr_trend": rhr_trend,
    }


def render_markdown(result: dict) -> str:
    rows = result["nights"]
    if not rows:
        return "No nights found."
    lines = [
        f"| Wake date | Sleep | HRV | HRV {result['window']}-night mean | vs balanced | Status | RHR | Weak |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        roll = f"{r['hrv_rolling']:.1f}" if r["hrv_rolling"] is not None else "-"
        hrv = f"{r['hrv']:.0f}" if r["hrv"] is not None else "-"
        lines.append(f"| {r['wake_date']} | {r['sleep_score'] if r['sleep_score'] is not None else '-'} "
                     f"| {hrv} | {roll} | {r['hrv_band'] or '-'} | {r['hrv_status'] or '-'} "
                     f"| {r['rhr'] if r['rhr'] is not None else '-'} | {'yes' if r['weak'] else ''} |")
    lines.append("")
    t = result["rhr_trend"]
    if t:
        lines.append(f"- Resting HR: {t['first']} ({t['first_date']}) -> {t['last']} ({t['last_date']}), "
                     f"{t['delta']:+d} bpm, mean {t['mean']:.1f}")
    else:
        lines.append("- Resting HR: not enough nights with a Garmin resting HR to show a trend")
    if result["alert"]:
        last = rows[-1]["reasons"]
        lines.append(f"- ALERT: {result['weak_streak']} weak nights in a row "
                     f"(threshold {result['weak_nights_threshold']}); latest: {'; '.join(last)}")
    else:
        lines.append(f"- Weak-night streak: {result['weak_streak']} "
                     f"(alert at {result['weak_nights_threshold']})")
    lines.append(f"- 'Weak' = sleep score < {SLEEP_FLOOR}, HRV Unbalanced, or HRV below the balanced range; "
                 f"{result['weak_nights_threshold']} in a row raises the alert (--weak-nights to change).")
    return "\n".join(lines)
