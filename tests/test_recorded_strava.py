"""Recorded Strava REST responses, pinned (roadmap P0.1).

`tests/data/strava_long_run.json` holds a real sync of the Oct 11 long run: the activity detail, the laps
list and the full-resolution streams, exactly as the REST API returned them, with everything identifying a
person, place or account removed. The numbers are untouched, so the golden figures still reproduce.

The point is the field *names*. COACHING_CONTEXT section 6 records the trap: the chat connector used
`avg_hr` and `relative_effort` while the REST API uses `average_heartrate` and `suffer_score`. Pinning a
real response means a rename or a shape change in the client fails here instead of silently producing
plausible-looking numbers.
"""

import json
from pathlib import Path

import pytest

from runcoach.analysis import run_report
from runcoach.analysis.run_report import build_report
from runcoach.config import Profile

FIXTURE = Path(__file__).parent / "data" / "strava_long_run.json"


@pytest.fixture(scope="module")
def recorded():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ---- the REST shapes themselves -----------------------------------------------------------------
def test_activity_uses_rest_field_names_not_connector_ones(recorded):
    act = recorded["activity"]
    for key in ("distance", "moving_time", "elapsed_time", "start_date_local", "average_heartrate",
                "max_heartrate", "average_cadence", "total_elevation_gain", "suffer_score", "gear_id"):
        assert key in act, f"REST activity lost {key}"
    for connector_name in ("avg_hr", "relative_effort", "avg_cadence", "summary"):
        assert connector_name not in act, f"{connector_name} is a connector name, not REST"


def test_laps_use_rest_field_names_and_carry_stream_indices(recorded):
    lap = recorded["laps"][0]
    for key in ("distance", "moving_time", "elapsed_time", "average_heartrate", "average_cadence",
                "start_index", "end_index"):
        assert key in lap, f"REST lap lost {key}"
    assert "avg_hr" not in lap


def test_streams_are_keyed_by_type_with_a_data_list(recorded):
    streams = recorded["streams"]
    for key in ("time", "distance", "velocity_smooth", "heartrate", "cadence", "altitude", "grade_smooth"):
        assert isinstance(streams[key]["data"], list) and streams[key]["data"], f"stream {key} missing"
    lengths = {len(streams[k]["data"]) for k in streams}
    assert len(lengths) == 1, "streams must share one resolution; never mix calls (COACHING_CONTEXT 6)"


# ---- the golden numbers, from the real response -------------------------------------------------
def test_report_reproduces_the_recorded_run(recorded):
    rep = build_report(recorded["activity"], recorded["laps"], recorded["streams"], Profile(), kind="long")
    assert round(rep["distance_km"], 2) == 10.03
    assert rep["moving"] == "1:09:45"
    assert rep["avg_hr"] == 140.7
    assert round(rep["efficiency"], 2) == 17.03              # COACHING_CONTEXT: 17.03 live


def test_the_trailing_lap_rule_drops_the_25_metre_lap(recorded):
    rep = build_report(recorded["activity"], recorded["laps"], recorded["streams"], Profile(), kind="long")
    assert len(recorded["laps"]) == 11 and len(rep["laps"]) == 10
    assert recorded["laps"][-1]["distance"] < 50


def test_decoupling_matches_the_live_run_once_the_tail_lap_is_accounted_for(recorded, monkeypatch):
    """COACHING_CONTEXT records raw 7.01% / gap -1.46% live on 2026-10-12, before the tail-lap rule."""
    monkeypatch.setattr(run_report, "MIN_TAIL_M", 0.0)
    rep = build_report(recorded["activity"], recorded["laps"], recorded["streams"], Profile(), kind="long")
    assert round(rep["decoupling_raw"]["pct"], 2) == 7.01
    assert round(rep["decoupling_gap"]["pct"], 2) == -1.46


def test_decoupling_with_the_rule_in_place(recorded):
    rep = build_report(recorded["activity"], recorded["laps"], recorded["streams"], Profile(), kind="long")
    assert round(rep["decoupling_raw"]["pct"], 2) == 6.91    # hand analysis recorded 6.92
    assert round(rep["decoupling_gap"]["pct"], 2) == -1.54


# ---- the fixture must stay sanitized -------------------------------------------------------------
def test_the_fixture_contains_no_personal_data():
    """Fails if a future refresh of this fixture reintroduces identifying fields."""
    raw = FIXTURE.read_text(encoding="utf-8")
    for leak in ("latlng", "polyline", "embed_token", "athlete", "segment_efforts", "upload_id",
                 "external_id", "photos", "location_city", "device_name", "description"):
        assert leak not in raw, f"fixture leaks {leak}"
