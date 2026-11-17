"""Aerobic decoupling and efficiency."""
from __future__ import annotations

from dataclasses import dataclass

from .gap import gap_factor


@dataclass(frozen=True)
class Decoupling:
    first_pace: float   # s/km
    first_hr: float
    second_pace: float
    second_hr: float
    pct: float          # positive = efficiency fell in the second half


def efficiency(distance_m: float, moving_s: float, avg_hr: float) -> float:
    """Speed per heartbeat x1000 (m/s per bpm x 1000). Higher is better."""
    return (distance_m / moving_s) / avg_hr * 1000.0


def _after_skip(laps, skip_m):
    out = []
    acc = 0.0
    for time_s, dist_m, hr, factor in laps:
        if acc >= skip_m:
            out.append((time_s, dist_m, hr, factor))
        elif acc + dist_m > skip_m:
            frac = (acc + dist_m - skip_m) / dist_m
            out.append((time_s * frac, dist_m * frac, hr, factor))
        acc += dist_m
    return out


def decoupling(laps, skip_first_m: float = 1000.0, use_gap: bool = False) -> Decoupling | None:
    """Half-split decoupling (efficiency factor = speed / HR), first km excluded.

    laps: iterable of dicts with moving_time, distance, avg_hr and optional grade_pct.
    use_gap=True splits and measures on grade-adjusted distance.
    """
    rows = []
    for lap in laps:
        if lap.get("avg_hr") is None or not lap.get("distance"):
            continue
        factor = gap_factor(lap.get("grade_pct") or 0.0) if use_gap else 1.0
        rows.append((lap["moving_time"], lap["distance"], lap["avg_hr"], factor))
    rows = _after_skip(rows, skip_first_m)
    if len(rows) < 2:
        return None

    total = sum(d * f for _, d, _, f in rows)
    half = total / 2.0
    a_t = a_d = a_hr = b_t = b_d = b_hr = 0.0
    acc = 0.0
    for t, d, hr, f in rows:
        eff_d = d * f
        if acc + eff_d <= half:
            a_t += t; a_d += eff_d; a_hr += hr * t
        elif acc < half:
            frac = (half - acc) / eff_d
            a_t += t * frac; a_d += eff_d * frac; a_hr += hr * t * frac
            b_t += t * (1 - frac); b_d += eff_d * (1 - frac); b_hr += hr * t * (1 - frac)
        else:
            b_t += t; b_d += eff_d; b_hr += hr * t
        acc += eff_d
    if not a_t or not b_t:
        return None
    hr1, hr2 = a_hr / a_t, b_hr / b_t
    sp1, sp2 = a_d / a_t, b_d / b_t
    ef1, ef2 = sp1 / hr1, sp2 / hr2
    return Decoupling(
        first_pace=1000.0 / sp1, first_hr=hr1,
        second_pace=1000.0 / sp2, second_hr=hr2,
        pct=100.0 * (ef1 - ef2) / ef1,
    )
