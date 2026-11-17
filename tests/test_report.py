import pytest

from runcoach.analysis.run_report import build_report, render_markdown
from runcoach.config import Profile

from .fixtures import OCT8_EASY, OCT11_LONG, rest_laps, streams_for


def _activity(rows, name, date, distance, moving, hr, max_hr, cad_rpm, gain):
    return {"name": name, "start_date_local": f"{date}T07:22:25Z", "distance": distance,
            "moving_time": moving, "average_heartrate": hr, "max_heartrate": max_hr,
            "average_cadence": cad_rpm, "total_elevation_gain": gain}


def test_easy_run_report_uses_stream_grade_and_cadence():
    act = _activity(OCT8_EASY, "Afternoon Run", "2026-10-08", 5740.6, 2396, 143.528, 154, 83.88, 3)
    rep = build_report(act, rest_laps(OCT8_EASY), streams_for(OCT8_EASY), Profile(), kind="easy")
    assert len(rep["laps"]) == 6
    assert rep["laps"][4]["pace"] == pytest.approx(411, abs=0.5)
    assert rep["laps"][0]["cadence_spm"] == pytest.approx(168.3, abs=0.1)
    assert rep["decoupling_raw"]["pct"] == pytest.approx(4.02, abs=0.1)
    assert rep["efficiency"] == pytest.approx(16.69, abs=0.02)
    assert not any("outside the Easy band" in f for f in rep["flags"])   # every lap 6:51-7:03
    assert any("[4, 5, 6]" in f for f in rep["flags"])                    # HR 147-152 on laps 4-6 exceeds the 145 guide


def test_long_run_flags_hr_over_guide():
    act = _activity(OCT11_LONG, "Morning Run", "2026-10-11", 10030.5, 4185, 140.655, 158, 85.1, 56)
    rep = build_report(act, rest_laps(OCT11_LONG), streams_for(OCT11_LONG), Profile(), kind="long")
    over = [f for f in rep["flags"] if "HR above" in f][0]
    assert "[6, 7, 8, 9, 10]" in over
    assert rep["laps"][9]["gap"] == pytest.approx(374, abs=1)    # 6:14
    assert rep["decoupling_gap"]["pct"] < 0 < rep["decoupling_raw"]["pct"]
    md = render_markdown(rep)
    assert "| 10 |" in md and "FLAG" in md


def test_missing_laps_falls_back_to_splits():
    act = _activity(OCT8_EASY, "Run", "2026-10-08", 5000, 2100, 140, 150, 84, 10)
    act["splits_metric"] = [{"distance": 1000, "moving_time": 420, "average_heartrate": 140,
                             "elevation_difference": 2.0} for _ in range(5)]
    rep = build_report(act, [], None, Profile())
    assert len(rep["laps"]) == 5 and rep["laps"][0]["grade_pct"] == pytest.approx(0.2)


def test_trailing_tiny_lap_is_ignored_but_short_work_laps_are_kept():
    laps = rest_laps(OCT11_LONG)
    last_end = laps[-1]["end_index"]
    tail = {"distance": 25.09, "moving_time": 12, "elapsed_time": 12, "average_heartrate": 155.5,
            "average_cadence": 83.5, "start_index": last_end + 1, "end_index": last_end + 12}
    act = _activity(OCT11_LONG, "Morning Run", "2026-10-11", 10030.5, 4185, 140.655, 158, 85.1, 56)
    rep = build_report(act, laps + [tail], streams_for(OCT11_LONG), Profile(), kind="long")
    assert len(rep["laps"]) == 10                                  # the 25 m lap 11 is dropped
    assert rep["decoupling_raw"]["pct"] == pytest.approx(6.92, abs=0.1)
    strides = [dict(tail, distance=90.0, moving_time=20, end_index=last_end + 20) for _ in range(3)]
    rep2 = build_report(act, laps[:1] + strides, None, Profile(), kind="strides")
    assert len(rep2["laps"]) == 4                                  # 90 m laps are real work, not artefacts


def test_report_includes_time_in_zone_and_the_easy_guide_split():
    """Roadmap P1.3: zones and the guide check come from the 1 Hz heartrate stream."""
    from runcoach.analysis.run_report import build_report, render_markdown
    from runcoach.config import Profile
    from tests.fixtures import OCT11_LONG, rest_laps, streams_for

    rep = build_report({"name": "Long", "start_date_local": "2026-10-11T07:00:00Z"},
                       rest_laps(OCT11_LONG), streams_for(OCT11_LONG), Profile(), kind="long")
    assert rep["time_in_zone"] == {"Z1": 2131, "Z2": 1658, "Z3": 397, "Z4": 0, "Z5": 0}
    assert rep["easy_guide"] == {"guide": 145, "at_or_below_s": 2131, "above_s": 2055}
    md = render_markdown(rep)
    assert "- Time in zone: Z1 35:31 Z2 27:38 Z3 6:37 Z4 0:00 Z5 0:00" in md
    assert "- HR at or below the 145 guide: 35:31 of 1:09:46 (51%)" in md


def test_report_omits_zones_without_a_heartrate_stream():
    from runcoach.analysis.run_report import build_report, render_markdown
    from runcoach.config import Profile
    from tests.fixtures import OCT11_LONG, rest_laps

    rep = build_report({"name": "Long", "start_date_local": "2026-10-11T07:00:00Z"},
                       rest_laps(OCT11_LONG), None, Profile(), kind="long")
    assert rep["time_in_zone"] is None and rep["easy_guide"] is None
    assert "Time in zone" not in render_markdown(rep)
