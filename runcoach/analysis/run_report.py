"""Build a 'deep dive' for one run from Strava API data (activity + laps + streams)."""
from __future__ import annotations

from dataclasses import asdict

from ..config import Profile
from ..metrics.cadence import mean_spm
from ..metrics.decoupling import decoupling, efficiency
from ..metrics.gap import gap_factor
from ..metrics.pace import fmt_pace, fmt_time


def _stream(streams: dict | None, key: str):
    if not streams:
        return None
    block = streams.get(key)
    if isinstance(block, dict):
        return block.get("data")
    return block


def normalize_lap(lap: dict) -> dict:
    """Accept Strava REST lap keys (average_heartrate ...) and the shorter names (avg_hr ...)."""
    return {
        "distance": lap.get("distance"),
        "moving_time": lap.get("moving_time") or lap.get("elapsed_time"),
        "avg_hr": lap.get("average_heartrate", lap.get("avg_hr")),
        "cad_rpm": lap.get("average_cadence", lap.get("avg_cadence")),
        "grade_pct": lap.get("avg_grade"),
        "start_index": lap.get("start_index"),
        "end_index": lap.get("end_index"),
    }


def laps_from_splits(activity: dict) -> list[dict]:
    """Fallback when an activity has no laps: Strava's 1 km metric splits."""
    out = []
    for sp in activity.get("splits_metric") or []:
        dist = sp.get("distance") or 0
        out.append({
            "distance": dist,
            "moving_time": sp.get("moving_time") or sp.get("elapsed_time"),
            "average_heartrate": sp.get("average_heartrate"),
            "avg_grade": (sp.get("elevation_difference", 0) / dist * 100.0) if dist else 0.0,
        })
    return out


MIN_TAIL_M = 50.0     # a trailing lap shorter than this is a recording artefact (e.g. a 25 m "lap 11")


def _mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def build_report(activity: dict, laps: list[dict], streams: dict | None,
                 profile: Profile, kind: str = "easy") -> dict:
    grade_stream = _stream(streams, "grade_smooth")
    cad_stream = _stream(streams, "cadence")
    raw_laps = laps or laps_from_splits(activity)

    rows = []
    for n, raw in enumerate(raw_laps, 1):
        lap = normalize_lap(raw)
        dist, secs = lap["distance"], lap["moving_time"]
        if not dist or not secs:
            continue
        if n == len(raw_laps) and len(raw_laps) > 1 and dist < MIN_TAIL_M:
            continue                      # keeps real short laps such as 85-98 m strides
        s, e = lap["start_index"], lap["end_index"]
        have_idx = s is not None and e is not None
        grade = lap["grade_pct"]
        if grade_stream and have_idx:
            grade = _mean(grade_stream[s:e + 1])
        grade = grade if grade is not None else 0.0
        cad = None
        if cad_stream and have_idx:
            cad = mean_spm(cad_stream, s, e)
        if cad is None and lap["cad_rpm"]:
            cad = lap["cad_rpm"] * 2.0
        pace = secs / (dist / 1000.0)
        rows.append({
            "lap": n, "distance_m": dist, "moving_s": secs, "pace": pace,
            "gap": pace / gap_factor(grade), "grade_pct": grade,
            "avg_hr": lap["avg_hr"], "cadence_spm": cad,
        })

    total_s = sum(r["moving_s"] for r in rows)
    total_m = sum(r["distance_m"] for r in rows)
    geq_m = sum(r["distance_m"] * gap_factor(r["grade_pct"]) for r in rows)
    dec_inputs = [{"moving_time": r["moving_s"], "distance": r["distance_m"],
                   "avg_hr": r["avg_hr"], "grade_pct": r["grade_pct"]} for r in rows]

    dist_m = activity.get("distance") or total_m
    mov_s = activity.get("moving_time") or total_s
    avg_hr = activity.get("average_heartrate")
    report = {
        "name": activity.get("name"),
        "date": (activity.get("start_date_local") or "")[:10],
        "kind": kind,
        "distance_km": dist_m / 1000.0,
        "moving": fmt_time(mov_s),
        "avg_pace": mov_s / (dist_m / 1000.0) if dist_m else None,
        "overall_gap": total_s / (geq_m / 1000.0) if geq_m else None,
        "avg_hr": avg_hr,
        "max_hr": activity.get("max_heartrate"),
        "avg_cadence_spm": (activity.get("average_cadence") or 0) * 2.0 or None,
        "elevation_m": activity.get("total_elevation_gain"),
        "gear_id": activity.get("gear_id"),
        "suffer_score": activity.get("suffer_score"),
        "efficiency": efficiency(dist_m, mov_s, avg_hr) if avg_hr else None,
        "laps": rows,
        "decoupling_raw": None,
        "decoupling_gap": None,
        "flags": [],
    }
    d_raw = decoupling(dec_inputs, use_gap=False)
    d_gap = decoupling(dec_inputs, use_gap=True)
    report["decoupling_raw"] = asdict(d_raw) if d_raw else None
    report["decoupling_gap"] = asdict(d_gap) if d_gap else None

    if kind in ("easy", "long"):
        lo, hi = profile.easy_band
        outside = [r["lap"] for r in rows if not (lo <= r["pace"] <= hi) and r["distance_m"] >= 500]
        if outside:
            report["flags"].append(f"Laps outside the Easy band ({fmt_pace(lo)}-{fmt_pace(hi)}): {outside}")
        over = [r for r in rows if r["avg_hr"] and r["avg_hr"] > profile.easy_hr_guide]
        if over:
            minutes = sum(r["moving_s"] for r in over) / 60.0
            report["flags"].append(
                f"HR above the {profile.easy_hr_guide} guide on laps {[r['lap'] for r in over]} (~{minutes:.0f} min)")
    return report


def render_markdown(rep: dict) -> str:
    lines = [
        f"## {rep['name']} ({rep['date']}, {rep['kind']})",
        "",
        f"{rep['distance_km']:.2f} km, {rep['moving']} moving, {fmt_pace(rep['avg_pace'])}/km "
        f"(GAP {fmt_pace(rep['overall_gap'])}), HR {rep['avg_hr'] or 0:.1f} avg / {rep['max_hr'] or 0:.0f} max, "
        f"cadence {rep['avg_cadence_spm'] or 0:.1f} spm, +{rep['elevation_m'] or 0:.0f} m",
        "",
        "| Lap | Dist | Pace | GAP | Grade | HR | Cadence |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rep["laps"]:
        hr = f"{r['avg_hr']:.1f}" if r["avg_hr"] else "-"
        cad = f"{r['cadence_spm']:.1f}" if r["cadence_spm"] else "-"
        lines.append(f"| {r['lap']} | {r['distance_m']:.0f} m | {fmt_pace(r['pace'])} | {fmt_pace(r['gap'])} "
                     f"| {r['grade_pct']:+.1f}% | {hr} | {cad} |")
    lines.append("")
    for label, key in (("Decoupling (raw pace)", "decoupling_raw"), ("Decoupling (grade-adjusted)", "decoupling_gap")):
        d = rep[key]
        if d:
            lines.append(f"- {label}: {d['pct']:.2f}% ({fmt_pace(d['first_pace'])} @ {d['first_hr']:.1f} -> "
                         f"{fmt_pace(d['second_pace'])} @ {d['second_hr']:.1f})")
    if rep["efficiency"]:
        lines.append(f"- Efficiency (speed per heartbeat x1000): {rep['efficiency']:.2f}")
    for flag in rep["flags"]:
        lines.append(f"- FLAG: {flag}")
    return "\n".join(lines)
