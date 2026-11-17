"""Daniels/Gilbert VDOT and Riegel race-time projection (approximate by design)."""
from __future__ import annotations

import math


def vdot(time_s: float, dist_m: float) -> float:
    t = time_s / 60.0
    v = dist_m / t
    vo2 = -4.60 + 0.182258 * v + 0.000104 * v * v
    pct = 0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t)
    return vo2 / pct


def time_for_vdot(v: float, dist_m: float) -> float:
    """Equivalent race time (s) at a distance for a VDOT (bisection)."""
    lo, hi = 60.0, 30000.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if vdot(mid, dist_m) > v:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def riegel(time_s: float, from_m: float, to_m: float, exponent: float = 1.06) -> float:
    return time_s * (to_m / from_m) ** exponent
