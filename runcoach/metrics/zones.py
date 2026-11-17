"""Heart-rate time-in-zone and the easy-HR guide check.

The standing zones in docs/COACHING_CONTEXT.md are written with gaps:
Z1 < 144, Z2 144-150, Z3 152-159, Z4 161-167, Z5 169+. That leaves 151, 160
and 168 bpm in no zone at all. Zones here are therefore defined by their
*lower* bounds only (144, 152, 161, 169), which makes the partition total:
every sample falls in exactly one zone and the seconds always sum to the
number of measured samples. The effect is that each published gap bpm joins
the zone below it (151 -> Z2, 160 -> Z3, 168 -> Z4).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

ZONE_NAMES = ("Z1", "Z2", "Z3", "Z4", "Z5")


def zone_for(hr: float, lowers: Sequence[int]) -> str:
    """Zone name for one heart-rate sample, given the four lower bounds of Z2..Z5."""
    zone = ZONE_NAMES[0]
    for name, lower in zip(ZONE_NAMES[1:], lowers, strict=True):
        if hr >= lower:
            zone = name
    return zone


def time_in_zone(hr_data: Iterable[float | None], lowers: Sequence[int]) -> dict[str, int]:
    """Seconds per zone from a 1 Hz heart-rate stream. Missing samples are skipped."""
    seconds = dict.fromkeys(ZONE_NAMES, 0)
    for hr in hr_data:
        if hr is None:
            continue
        seconds[zone_for(hr, lowers)] += 1
    return seconds


def easy_guide_split(hr_data: Iterable[float | None], guide: int) -> tuple[int, int]:
    """Seconds at or below the easy-HR guide, and seconds above it. The guide is inclusive."""
    at_or_below = above = 0
    for hr in hr_data:
        if hr is None:
            continue
        if hr <= guide:
            at_or_below += 1
        else:
            above += 1
    return at_or_below, above
