"""The typed REST shapes describe the real recorded response (roadmap P2).

A TypedDict is not enforced at runtime, so on its own it could drift away from reality without anyone
noticing. These tests check it against tests/data/strava_long_run.json, the response actually recorded from
Strava, so the annotations stay true rather than decorative.
"""

import json
from pathlib import Path
from typing import get_type_hints

import pytest

from runcoach.strava.types import (
    REQUIRED_ACTIVITY,
    REQUIRED_LAP,
    REQUIRED_STREAMS,
    Activity,
    Lap,
    Split,
    StreamBlock,
    Streams,
    missing_keys,
)

RECORDED = json.loads((Path(__file__).parent / "data" / "strava_long_run.json").read_text(encoding="utf-8"))


def test_every_recorded_activity_key_is_declared():
    declared = set(get_type_hints(Activity))
    undeclared = set(RECORDED["activity"]) - declared - {"_note"}
    assert not undeclared, f"recorded activity has keys the type does not declare: {sorted(undeclared)}"


def test_every_recorded_lap_key_is_declared():
    declared = set(get_type_hints(Lap))
    undeclared = set(RECORDED["laps"][0]) - declared
    assert not undeclared, f"recorded lap has keys the type does not declare: {sorted(undeclared)}"


def test_every_recorded_stream_and_block_key_is_declared():
    assert not set(RECORDED["streams"]) - set(get_type_hints(Streams))
    block = RECORDED["streams"]["time"]
    assert not set(block) - set(get_type_hints(StreamBlock))


def test_every_recorded_split_key_is_declared():
    undeclared = set(RECORDED["activity"]["splits_metric"][0]) - set(get_type_hints(Split))
    assert not undeclared, f"recorded split has undeclared keys: {sorted(undeclared)}"


def test_the_recorded_response_has_everything_the_project_requires():
    assert missing_keys(RECORDED["activity"], REQUIRED_ACTIVITY) == []
    assert missing_keys(RECORDED["laps"][0], REQUIRED_LAP) == []
    assert missing_keys(RECORDED["streams"], REQUIRED_STREAMS) == []


def test_missing_keys_names_what_is_absent_and_keeps_the_given_order():
    assert missing_keys({}, REQUIRED_ACTIVITY) == list(REQUIRED_ACTIVITY)
    assert missing_keys({"distance": 1.0}, REQUIRED_ACTIVITY) == ["moving_time", "start_date_local"]
    assert missing_keys({"distance": 1.0, "moving_time": 2, "start_date_local": "x"}, REQUIRED_ACTIVITY) == []


@pytest.mark.parametrize("connector_name", ["avg_hr", "avg_cadence", "relative_effort", "summary"])
def test_connector_names_are_not_declared_as_rest_names(connector_name):
    """COACHING_CONTEXT 6: the chat connector and the REST API disagree; the types follow REST."""
    assert connector_name not in get_type_hints(Activity)
    assert connector_name not in get_type_hints(Lap)
