"""Pace and time helpers. Pace is seconds per km everywhere in this package."""
from __future__ import annotations

import math


def pace_from_speed(speed_mps: float | None, min_speed: float = 0.8) -> float | None:
    """Seconds per km from m/s; None for stops or missing data."""
    if speed_mps is None or speed_mps < min_speed:
        return None
    return 1000.0 / speed_mps


def fmt_pace(sec_per_km: float | None) -> str:
    if sec_per_km is None or (isinstance(sec_per_km, float) and math.isnan(sec_per_km)):
        return "-"
    s = int(round(sec_per_km))
    return f"{s // 60}:{s % 60:02d}"


def fmt_time(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def parse_time(text: str) -> float:
    """'2:08:21' or '26:17' -> seconds."""
    parts = [int(p) for p in text.strip().split(":")]
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0, parts[0], parts[1]
    else:
        raise ValueError(f"Cannot parse time: {text!r}")
    return h * 3600 + m * 60 + s
