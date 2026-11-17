"""Training load: TRIMP and the CTL / ATL / TSB model."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta


def banister_trimp(hr_samples, time_samples, hr_rest: float, hr_max: float, sex: str = "male") -> float:
    """Banister TRIMP from an HR stream. Scale differs from Strava Relative Effort."""
    a, b = (0.64, 1.92) if sex == "male" else (0.86, 1.67)
    total = 0.0
    for i in range(1, len(time_samples)):
        hr = hr_samples[i]
        if hr is None:
            continue
        dt_min = (time_samples[i] - time_samples[i - 1]) / 60.0
        if dt_min <= 0 or dt_min > 1.0:      # skip pauses and gaps
            continue
        ratio = min(max((hr - hr_rest) / (hr_max - hr_rest), 0.0), 1.0)
        total += dt_min * ratio * a * math.exp(b * ratio)
    return total


def step(ctl: float, atl: float, load: float, ctl_days: int = 42, atl_days: int = 7):
    """Advance one day. Exponential weighting: alpha = 1 - exp(-1/N)."""
    ctl += (1 - math.exp(-1 / ctl_days)) * (load - ctl)
    atl += (1 - math.exp(-1 / atl_days)) * (load - atl)
    return ctl, atl


@dataclass(frozen=True)
class LoadPoint:
    day: date
    load: float
    ctl: float
    atl: float

    @property
    def tsb(self) -> float:
        return self.ctl - self.atl


def load_series(daily_loads: dict[date, float], start: date, end: date,
                ctl0: float = 0.0, atl0: float = 0.0):
    """Daily CTL/ATL/TSB from start to end inclusive (days without data = rest)."""
    ctl, atl = ctl0, atl0
    day = start
    out = []
    while day <= end:
        load = daily_loads.get(day, 0.0)
        ctl, atl = step(ctl, atl, load)
        out.append(LoadPoint(day, load, ctl, atl))
        day += timedelta(days=1)
    return out
