"""Typed shapes for the Strava REST responses this project reads (roadmap P2).

These are `TypedDict`s, not dataclasses, because the cache stores the API's JSON verbatim and converting it
into objects would mean a translation layer on every read. A TypedDict describes the dict that is already
there, so a type checker can catch a wrong key with no runtime cost and no change to how data is stored.

`total=False` throughout: Strava omits fields rather than sending nulls (no `suffer_score` on a run with no
Relative Effort, no `average_heartrate` without a strap), so every key is genuinely optional.

The names here are the REST names. COACHING_CONTEXT section 6 records the trap: the chat connector used
`avg_hr` and `relative_effort` where REST uses `average_heartrate` and `suffer_score`. `REQUIRED_*` below
lists what this project actually needs, and `missing_keys` reports what a response lacks, so a shape change
is caught where it happens instead of surfacing later as an odd number.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypedDict


class Split(TypedDict, total=False):
    distance: float
    elapsed_time: int
    moving_time: int
    elevation_difference: float
    split: int
    average_speed: float
    average_grade_adjusted_speed: float
    average_heartrate: float
    pace_zone: int


class Activity(TypedDict, total=False):
    id: int
    name: str
    start_date_local: str
    distance: float
    moving_time: int
    elapsed_time: int
    type: str
    sport_type: str
    workout_type: int
    total_elevation_gain: float
    average_speed: float
    max_speed: float
    average_cadence: float
    average_heartrate: float
    max_heartrate: float
    has_heartrate: bool
    average_watts: float
    max_watts: float
    device_watts: bool
    kilojoules: float
    calories: float
    suffer_score: float
    gear_id: str
    elev_high: float
    elev_low: float
    average_temp: int
    splits_metric: list[Split]


class Lap(TypedDict, total=False):
    name: str
    distance: float
    moving_time: int
    elapsed_time: int
    average_speed: float
    max_speed: float
    average_heartrate: float
    max_heartrate: float
    average_cadence: float
    average_watts: float
    device_watts: bool
    total_elevation_gain: float
    start_index: int
    end_index: int
    lap_index: int
    split: int
    pace_zone: int


class StreamBlock(TypedDict, total=False):
    data: list[float | None]
    series_type: str
    original_size: int
    resolution: str


class Streams(TypedDict, total=False):
    time: StreamBlock
    distance: StreamBlock
    velocity_smooth: StreamBlock
    heartrate: StreamBlock
    cadence: StreamBlock
    altitude: StreamBlock
    grade_smooth: StreamBlock


# What this project genuinely needs, as opposed to everything Strava sends.
REQUIRED_ACTIVITY = ("distance", "moving_time", "start_date_local")
REQUIRED_LAP = ("distance", "moving_time")
REQUIRED_STREAMS = ("time", "distance")


def missing_keys(obj: dict, required: Iterable[str]) -> list[str]:
    """Required keys absent from `obj`, in the order given. Empty means the shape is usable."""
    return [key for key in required if key not in obj]
