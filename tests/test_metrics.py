from datetime import date

import pytest

from runcoach.metrics.cadence import mean_spm, to_spm
from runcoach.metrics.decoupling import decoupling, efficiency
from runcoach.metrics.gap import gap_factor, gap_pace
from runcoach.metrics.load import banister_trimp, load_series, step
from runcoach.metrics.pace import fmt_pace, fmt_time, parse_time
from runcoach.metrics.vdot import riegel, time_for_vdot, vdot

from .fixtures import OCT8_EASY, OCT11_LONG, laps_for_decoupling


def test_pace_formatting_and_parsing():
    assert fmt_pace(417.4) == "6:57"
    assert fmt_time(7701) == "2:08:21"
    assert parse_time("2:08:21") == 7701
    assert parse_time("26:17") == 1577


def test_gap_matches_session_values():
    assert gap_factor(0.0) == pytest.approx(1.0)
    assert fmt_pace(gap_pace(397, 1.1022)) == "6:14"      # long run km 10, +1.1%
    assert fmt_pace(gap_pace(392, -1.90228)) == "7:15"    # long run km 3, -1.9%
    assert fmt_pace(gap_pace(421, 1.04156)) == "6:38"     # km 8


def test_decoupling_easy_run_matches_session():
    d = decoupling(laps_for_decoupling(OCT8_EASY))
    assert d.pct == pytest.approx(4.02, abs=0.1)


def test_decoupling_long_run_raw_vs_grade_adjusted():
    laps = laps_for_decoupling(OCT11_LONG)
    assert decoupling(laps).pct == pytest.approx(6.92, abs=0.1)
    assert decoupling(laps, use_gap=True).pct == pytest.approx(-1.33, abs=0.1)


def test_efficiency():
    assert efficiency(10030.5, 4185, 140.655) == pytest.approx(17.04, abs=0.01)


def test_cadence_glitches_removed_and_doubled():
    assert to_spm([0, 55, 57, 83, 85]) == [None, None, None, 166.0, 170.0]
    assert mean_spm([0, 84, 86, 57], 0, 3) == pytest.approx(170.0)


def test_vdot_matches_session():
    assert vdot(1577, 5000) == pytest.approx(36.1, abs=0.1)          # April 26 5K 26:17
    assert vdot(7701, 21097.5) == pytest.approx(33.7, abs=0.1)       # Pocari best-effort half
    v = vdot(7701, 21097.5)
    assert time_for_vdot(v, 21097.5) == pytest.approx(7701, abs=1)
    assert riegel(3439, 10000, 5000) < 1700


def test_ctl_step_matches_session():
    ctl, atl = step(17.94, 18.55, 19)           # Oct 8 easy run, RE 19
    assert (round(ctl, 2), round(atl, 2)) == (17.96, 18.61)


def test_load_series_rest_day():
    pts = load_series({}, date(2026, 10, 12), date(2026, 10, 12), 18.20, 19.78)
    assert (round(pts[0].ctl, 2), round(pts[0].atl, 2), round(pts[0].tsb, 2)) == (17.77, 17.15, 0.62)


def test_banister_trimp_constant_hr():
    t = list(range(0, 2401))                    # 40 minutes at 1 Hz
    hr = [143] * len(t)
    assert banister_trimp(hr, t, 55, 180) == pytest.approx(69.7, abs=0.5)
