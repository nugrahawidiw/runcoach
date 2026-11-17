import datetime as dt

import pytest

from runcoach.analysis.run_report import build_report
from runcoach.config import Profile
from runcoach.fit.activity import activity_from_messages, cache_id, grade_stream
from runcoach.fit.reader import iter_path

from .fitwriter import synthetic_run

START = dt.datetime(2026, 10, 11, 0, 22, 25, tzinfo=dt.UTC)      # 07:22:25 local (+7)


@pytest.fixture()
def run(tmp_path):
    path = tmp_path / "run.fit"
    path.write_bytes(synthetic_run(START))
    return activity_from_messages(list(iter_path(path)))


def test_real_fit_parsing_summary(run):
    a = run.activity
    assert a["distance"] == pytest.approx(1890, abs=1) and a["moving_time"] == pytest.approx(600)
    assert a["average_heartrate"] == 145 and a["max_heartrate"] == 160
    assert a["start_date_local"] == "2026-10-11T07:22:25Z"                   # UTC + device offset
    assert cache_id(run) == "fit-20261011072225"


def test_streams_and_laps_line_up(run):
    assert len(run.streams["time"]["data"]) == 600
    assert run.laps[0]["start_index"] == 0 and run.laps[0]["end_index"] == 299
    assert run.laps[1]["start_index"] == 300 and run.laps[1]["end_index"] == 599
    assert run.laps[0]["distance"] == pytest.approx(900) and run.laps[1]["average_heartrate"] == 152
    assert run.laps[0]["average_cadence"] == 86                         # avg_running_cadence, strides/min of one foot
    assert run.activity["average_cadence"] == 86


def test_grade_from_altitude(run):
    g = run.streams["grade_smooth"]["data"]
    assert g[150] == pytest.approx(3.0, abs=0.3)      # first lap +3%
    assert g[450] == pytest.approx(0.0, abs=0.3)      # second lap flat


def test_grade_stream_handles_gaps():
    assert grade_stream([None] * 30, [None] * 30) == [None] * 30


def test_report_from_fit_matches_expected_paces(run):
    rep = build_report(run.activity, run.laps, run.streams, Profile(), kind="easy")
    lap1, lap2 = rep["laps"]
    assert lap1["pace"] == pytest.approx(333.3, abs=0.5) and lap2["pace"] == pytest.approx(303.0, abs=0.5)
    assert lap1["grade_pct"] == pytest.approx(3.0, abs=0.3)
    assert lap1["gap"] < lap1["pace"]                 # uphill: flat-equivalent pace is faster
    assert lap1["cadence_spm"] == pytest.approx(172.0)
    assert lap1["avg_hr"] == 138 and lap2["avg_hr"] == 152
    assert rep["avg_cadence_spm"] == pytest.approx(172.0)


def test_activity_without_session_is_rejected():
    from runcoach.fit.reader import Message
    with pytest.raises(ValueError):
        activity_from_messages([Message("record", {"timestamp": START})])
