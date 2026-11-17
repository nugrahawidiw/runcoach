"""Grade-adjusted pace using the Minetti et al. (2002) running-cost polynomial."""
from __future__ import annotations


def minetti_cost(grade: float) -> float:
    """Metabolic cost (J/kg/m) at a gradient given as a fraction (+0.05 = +5%)."""
    i = grade
    return 155.4 * i**5 - 30.4 * i**4 - 43.3 * i**3 + 46.3 * i**2 + 19.5 * i + 3.6


_FLAT = minetti_cost(0.0)


def gap_factor(grade_pct: float) -> float:
    """Cost relative to flat ground. >1 uphill, <1 gentle downhill."""
    return minetti_cost(grade_pct / 100.0) / _FLAT


def gap_pace(pace_s_per_km: float, grade_pct: float) -> float:
    """Flat-equivalent pace (s/km) for the effort at this grade."""
    return pace_s_per_km / gap_factor(grade_pct)
