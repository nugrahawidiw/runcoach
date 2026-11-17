"""Session-structure detection for intervals and strides (roadmap P1.2).

The fixtures are real Strava laps. These tests reproduce the numbers recorded in COACHING_CONTEXT, so a
transcription slip in tests/fixtures.py fails here rather than going unnoticed.
"""

from runcoach.analysis.session import detect_structure, render_markdown
from runcoach.config import Profile
from runcoach.metrics.pace import fmt_pace
from tests.fixtures import OCT7_INTERVALS, OCT8_EASY, OCT9_STRIDES, OCT11_LONG, rest_laps


def structure(rows, kind=None, **kw):
    return detect_structure(rest_laps(rows), Profile(), kind=kind, **kw)


# ---- the documented acceptance numbers --------------------------------------------------------
def test_oct7_intervals_reproduces_the_three_rep_paces():
    """COACHING_CONTEXT: reps 5:23 / 5:27 / 5:27."""
    reps = structure(OCT7_INTERVALS)["reps"]
    assert [fmt_pace(r["pace"]) for r in reps] == ["5:23", "5:27", "5:27"]


def test_oct7_intervals_reproduces_the_three_rep_cadences():
    """COACHING_CONTEXT: cadence 172.9 / 170.8 / 170.0."""
    reps = structure(OCT7_INTERVALS)["reps"]
    assert [round(r["cadence_spm"], 1) for r in reps] == [172.9, 170.8, 170.0]


def test_oct9_strides_has_five_of_six_in_the_cadence_band():
    """COACHING_CONTEXT: 5 of 6 in band (181-191 spm)."""
    result = structure(OCT9_STRIDES, kind="strides")
    assert len(result["reps"]) == 6
    assert result["in_band"] == 5
    assert [r["cadence_in_band"] for r in result["reps"]] == [True, False, True, True, True, True]
    assert round(result["reps"][1]["cadence_spm"], 1) == 193.7          # the one above the band


# ---- how the reps are found -------------------------------------------------------------------
def test_a_six_minute_rep_split_across_two_laps_is_one_rep():
    """Strava auto-splits at 1 km, so each 6:00 block is a 1000 m lap plus a remainder."""
    reps = structure(OCT7_INTERVALS)["reps"]
    assert [r["laps"] for r in reps] == [[3, 4], [6, 7], [9, 10]]
    assert all(r["moving_s"] == 360 for r in reps)                      # exactly 6:00 each


def test_recoveries_are_reported_separately():
    result = structure(OCT7_INTERVALS)
    assert [r["laps"] for r in result["recoveries"]] == [[1, 2], [5], [8], [11, 12]]


def test_each_stride_is_its_own_rep():
    assert [r["laps"] for r in structure(OCT9_STRIDES)["reps"]] == [[4], [6], [8], [10], [12], [14]]


def test_rep_heart_rate_is_time_weighted_across_merged_laps():
    rep = structure(OCT7_INTERVALS)["reps"][0]
    assert round(rep["avg_hr"], 1) == round((324 * 153.613 + 36 * 158.029) / 360, 1)


def test_fade_between_reps_is_the_pace_difference():
    fade = structure(OCT7_INTERVALS)["fade"]
    assert len(fade) == 2
    assert fade[0] > 0                                                  # rep 2 slower than rep 1


# ---- not inventing structure ------------------------------------------------------------------
def test_a_steady_long_run_has_no_structure():
    result = structure(OCT11_LONG)
    assert result["structured"] is False and result["reps"] == []
    assert "no clear work/recovery split" in result["reason"]


def test_a_steady_easy_run_has_no_structure():
    assert structure(OCT8_EASY)["structured"] is False


def test_too_few_laps_is_reported_not_guessed():
    assert structure(OCT7_INTERVALS[:2])["reason"] == "fewer than three usable laps"


def test_the_gap_guard_can_be_tightened_to_reject_a_real_session():
    assert structure(OCT7_INTERVALS, min_gap_pct=50.0)["structured"] is False


# ---- output ------------------------------------------------------------------------------------
def test_render_lists_each_rep_and_the_band_count():
    md = render_markdown(structure(OCT9_STRIDES, kind="strides"))
    assert "| 1 | 4 |" in md and "Cadence in the stride band (181-191 spm): 5 of 6" in md
    assert "First-minute overshoot: not available" in md          # no streams passed here


def test_render_says_so_when_there_is_no_structure():
    assert "No interval structure detected" in render_markdown(structure(OCT11_LONG))


def test_the_stride_cadence_band_is_not_applied_to_intervals():
    """181-191 spm is a strides target; counting an interval session against it would mislead."""
    intervals = structure(OCT7_INTERVALS, kind="intervals")
    assert intervals["in_band"] is None and intervals["cadence_band"] is None
    assert all(r["cadence_in_band"] is None for r in intervals["reps"])
    assert "stride band" not in render_markdown(intervals)


# ---- first-minute overshoot ---------------------------------------------------------------------
def _streams_with_fast_opening(rows, fast_s=60, fast_factor=1.08):
    """1 Hz streams where the first `fast_s` of every fast lap run `fast_factor` quicker."""
    speed, hr, idx = [], [], 0
    for secs, dist, _grade, lap_hr, _cad in rows:
        base = (dist / secs) if secs else 0.0
        quick = base * fast_factor
        for t in range(int(secs)):
            speed.append(quick if (base > 3.0 and t < fast_s) else base)
            hr.append(lap_hr)
        idx += int(secs)
    return {"velocity_smooth": {"data": speed}, "heartrate": {"data": hr}}


def test_overshoot_is_none_without_streams():
    assert all(r["overshoot"] is None for r in structure(OCT7_INTERVALS)["reps"])


def test_overshoot_flags_a_fast_first_minute():
    st = detect_structure(rest_laps(OCT7_INTERVALS), Profile(), kind="intervals",
                          streams=_streams_with_fast_opening(OCT7_INTERVALS))
    o = st["reps"][0]["overshoot"]
    assert o["pace_first"] < o["pace_rest"]            # first minute quicker
    assert o["pace_delta"] < -5.0 and o["overshot"] is True
    assert "OVERSHOT" in render_markdown(st)


def test_an_even_rep_is_not_flagged():
    st = detect_structure(rest_laps(OCT7_INTERVALS), Profile(), kind="intervals",
                          streams=_streams_with_fast_opening(OCT7_INTERVALS, fast_factor=1.0))
    o = st["reps"][0]["overshoot"]
    assert abs(o["pace_delta"]) < 1.0 and o["overshot"] is False


def test_overshoot_reports_heart_rate_alongside_pace():
    st = detect_structure(rest_laps(OCT7_INTERVALS), Profile(), kind="intervals",
                          streams=_streams_with_fast_opening(OCT7_INTERVALS))
    o = st["reps"][0]["overshoot"]
    assert o["hr_first"] is not None and o["hr_rest"] is not None and o["hr_delta"] is not None


def test_short_reps_get_no_overshoot_because_there_is_nothing_to_compare():
    """A 20 s stride cannot be split into a first minute and a remainder."""
    st = detect_structure(rest_laps(OCT9_STRIDES), Profile(), kind="strides",
                          streams=_streams_with_fast_opening(OCT9_STRIDES))
    assert all(r["overshoot"] is None for r in st["reps"])
    assert "First-minute overshoot: not available" in render_markdown(st)


def test_detection_is_deterministic():
    assert structure(OCT7_INTERVALS) == structure(OCT7_INTERVALS)
