"""Cadence handling. Strava run cadence is one foot (rpm); double it for steps/min."""
from __future__ import annotations


def to_spm(rpm_samples, min_rpm: float = 60.0):
    """Steps/min per sample; None for sensor glitches (0, 41, 55, 57 ...)."""
    return [None if (c is None or c < min_rpm) else c * 2.0 for c in rpm_samples]


def mean_spm(rpm_samples, start: int, end: int, min_rpm: float = 60.0) -> float | None:
    """Mean steps/min over stream indices start..end inclusive, ignoring glitches."""
    vals = [c * 2.0 for c in rpm_samples[start:end + 1] if c is not None and c >= min_rpm]
    return sum(vals) / len(vals) if vals else None
