"""Work/recovery structure for intervals and strides, from laps (roadmap P1.2).

Finding the reps: lap paces in a structured session are bimodal, so the laps are sorted by pace and split at
the single largest gap. That is parameter-free and far steadier than a fixed threshold -- on the Oct 7
intervals the gap is 75 s/km and on the Oct 9 strides 159 s/km, while a percentage threshold would have come
within a second of misclassifying a rep. A steady run has no such gap, so `min_gap_pct` (15% of the median
pace) guards against inventing structure where there is none: the Oct 11 long run's largest gap is about 8%.

Consecutive fast laps are then merged into one rep, which is what makes a 6:00 work block spanning a 1 km
auto-split and its remainder come out as a single rep rather than two.

NOT implemented: first-minute overshoot, which the roadmap lists for this item. It needs the heart-rate and
pace streams inside each rep, not lap averages. The laps alone cannot answer it, and guessing from a lap
average would be worse than leaving it out.
"""

from __future__ import annotations

from ..config import Profile
from ..metrics.pace import fmt_pace

MIN_REPS = 2
DEFAULT_MIN_GAP_PCT = 15.0


def _pace(lap: dict) -> float | None:
    dist, secs = lap.get("distance"), lap.get("moving_time")
    if not dist or not secs:
        return None
    return secs / (dist / 1000.0)


def _merge(laps: list[dict]) -> dict:
    """Combine consecutive laps into one block, time-weighting heart rate and cadence."""
    secs = sum(lap["moving_time"] for lap in laps)
    dist = sum(lap["distance"] for lap in laps)
    hr = [(lap["moving_time"], lap.get("average_heartrate")) for lap in laps]
    cad = [(lap["moving_time"], lap.get("average_cadence")) for lap in laps]

    def weighted(pairs):
        usable = [(t, v) for t, v in pairs if v is not None]
        total = sum(t for t, _ in usable)
        return sum(t * v for t, v in usable) / total if total else None

    cadence = weighted(cad)
    return {
        "laps": [lap["lap"] for lap in laps],
        "moving_s": secs,
        "distance_m": dist,
        "pace": secs / (dist / 1000.0) if dist else None,
        "avg_hr": weighted(hr),
        "cadence_spm": cadence * 2.0 if cadence is not None else None,
    }


def detect_structure(laps: list[dict], profile: Profile | None = None,
                     min_gap_pct: float = DEFAULT_MIN_GAP_PCT, kind: str | None = None) -> dict:
    """Split laps into work reps and recoveries. `structured` is False when there is no clear split.

    `kind` only controls the cadence band: the 181-191 spm target is a strides target, so counting
    intervals against it would be misleading.
    """
    profile = profile or Profile()
    numbered = []
    for i, lap in enumerate(laps or [], 1):
        pace = _pace(lap)
        if pace is not None:
            numbered.append(dict(lap, lap=lap.get("lap", i), _pace=pace))

    band_applies = kind == "strides"
    result = {"structured": False, "reason": "", "reps": [], "recoveries": [], "fade": [],
              "cadence_band": list(profile.stride_cadence) if band_applies else None, "in_band": None}
    if len(numbered) < 3:
        result["reason"] = "fewer than three usable laps"
        return result

    paces = sorted(lap["_pace"] for lap in numbered)
    gaps = [(paces[i + 1] - paces[i], i) for i in range(len(paces) - 1)]
    gap, idx = max(gaps)
    median = paces[len(paces) // 2]
    if gap < median * min_gap_pct / 100.0:
        result["reason"] = (f"no clear work/recovery split: largest pace gap {gap:.0f} s/km is under "
                            f"{min_gap_pct:g}% of the median lap pace ({median:.0f} s/km)")
        return result

    cutoff = paces[idx]
    blocks, current = [], []
    for lap in numbered:
        fast = lap["_pace"] <= cutoff
        if current and current[-1][1] != fast:
            blocks.append(current)
            current = []
        current.append((lap, fast))
    if current:
        blocks.append(current)

    reps = [_merge([lap for lap, _ in b]) for b in blocks if b[0][1]]
    recoveries = [_merge([lap for lap, _ in b]) for b in blocks if not b[0][1]]
    if len(reps) < MIN_REPS:
        result["reason"] = f"only {len(reps)} fast block(s) found"
        return result

    for i, rep in enumerate(reps, 1):
        rep["rep"] = i
    lo, hi = profile.stride_cadence
    for rep in reps:
        rep["cadence_in_band"] = (None if not band_applies or rep["cadence_spm"] is None
                                  else lo <= rep["cadence_spm"] <= hi)

    result.update({
        "structured": True,
        "reps": reps,
        "recoveries": [r for r in recoveries if r["laps"]],
        "fade": [reps[i]["pace"] - reps[i - 1]["pace"] for i in range(1, len(reps))],
        "in_band": sum(1 for r in reps if r["cadence_in_band"]) if band_applies else None,
    })
    return result


def render_markdown(structure: dict) -> str:
    if not structure["structured"]:
        return f"No interval structure detected ({structure['reason']})."
    lines = ["| Rep | Laps | Distance | Time | Pace | HR | Cadence | In band |", "|---|---|---|---|---|---|---|---|"]
    for rep in structure["reps"]:
        hr = f"{rep['avg_hr']:.1f}" if rep["avg_hr"] is not None else "-"
        cad = f"{rep['cadence_spm']:.1f}" if rep["cadence_spm"] is not None else "-"
        band = "-" if rep["cadence_in_band"] is None else ("yes" if rep["cadence_in_band"] else "no")
        lines.append(f"| {rep['rep']} | {','.join(str(n) for n in rep['laps'])} "
                     f"| {rep['distance_m']:.0f} m | {rep['moving_s']:.0f} s | {fmt_pace(rep['pace'])} "
                     f"| {hr} | {cad} | {band} |")
    lines.append("")
    if structure["cadence_band"]:
        lo, hi = structure["cadence_band"]
        lines.append(f"- Cadence in the stride band ({lo}-{hi} spm): {structure['in_band']} of "
                     f"{len(structure['reps'])}")
    if structure["fade"]:
        fade = ", ".join(f"{d:+.1f} s/km" for d in structure["fade"])
        lines.append(f"- Fade between reps: {fade}")
    lines.append("- First-minute overshoot is not computed: it needs the HR and pace streams inside each rep.")
    return "\n".join(lines)
