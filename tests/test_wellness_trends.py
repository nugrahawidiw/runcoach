"""Wellness trends: rolling HRV, resting-HR trend, weak-night streak (roadmap P1.8)."""

import datetime as dt

from runcoach.analysis.wellness_trends import render_markdown, summarize
from runcoach.fit.wellness import Night

BASELINE = (25.0, 27.0, 34.0)          # low_upper, balanced_lower, balanced_upper (the real Oct 11-12 values)


def night(day, score=75, hrv=30.0, status="balanced", rhr=58, baseline=BASELINE):
    start = dt.datetime(2026, 10, day, 22, 0)
    return Night(wake_date=dt.date(2026, 10, day + 1), sleep_start=start,
                 sleep_end=start + dt.timedelta(minutes=400), duration_min=400.0, score=score,
                 hrv_last_night=hrv, hrv_status=status, hrv_baseline=baseline, garmin_rhr=rhr)


def test_hrv_is_placed_against_garmins_own_balanced_range():
    rows = summarize([night(8, hrv=26.0), night(9, hrv=30.0), night(10, hrv=36.0)])["nights"]
    assert [r["hrv_band"] for r in rows] == ["below", "in", "above"]


def test_rolling_hrv_mean_respects_the_window():
    rows = summarize([night(8, hrv=30.0), night(9, hrv=20.0), night(10, hrv=10.0)], window=2)["nights"]
    assert [r["hrv_rolling"] for r in rows] == [30.0, 25.0, 15.0]


def test_nights_are_ordered_oldest_first_whatever_the_input_order():
    ns = [night(10), night(8), night(9)]
    assert [r["wake_date"] for r in summarize(ns)["nights"]] == ["2026-10-09", "2026-10-10", "2026-10-11"]


def test_a_low_sleep_score_makes_a_night_weak():
    (row,) = summarize([night(8, score=59)])["nights"]
    assert row["weak"] and "sleep score 59 < 60" in row["reasons"]


def test_sleep_score_of_exactly_60_is_not_weak():
    assert summarize([night(8, score=60)])["nights"][0]["weak"] is False


def test_unbalanced_hrv_status_makes_a_night_weak():
    (row,) = summarize([night(8, status="Unbalanced")])["nights"]
    assert row["weak"] and "HRV status Unbalanced" in row["reasons"]


def test_hrv_below_the_balanced_range_makes_a_night_weak():
    (row,) = summarize([night(8, hrv=26.0)])["nights"]
    assert row["weak"] and "HRV below the balanced range" in row["reasons"]


def test_a_night_with_no_sleep_score_and_no_hrv_is_not_weak():
    (row,) = summarize([night(8, score=None, hrv=None, status=None)])["nights"]
    assert row["weak"] is False and row["reasons"] == [] and row["hrv_band"] is None


def test_the_streak_counts_only_trailing_weak_nights():
    result = summarize([night(8, score=50), night(9, score=75), night(10, score=50), night(11, score=50)])
    assert result["weak_streak"] == 2                      # the early weak night does not count


def test_alert_fires_at_the_threshold_and_not_before():
    weak = [night(8, score=50), night(9, score=50), night(10, score=50)]
    assert summarize(weak, weak_nights=3)["alert"] is True
    assert summarize(weak, weak_nights=4)["alert"] is False
    assert summarize([night(8)], weak_nights=3)["alert"] is False


def test_no_alert_when_there_are_no_weak_nights_even_with_threshold_zero():
    assert summarize([night(8)], weak_nights=0)["alert"] is False


def test_resting_hr_trend_reports_first_last_and_delta():
    t = summarize([night(8, rhr=58), night(9, rhr=60), night(10, rhr=63)])["rhr_trend"]
    assert (t["first"], t["last"], t["delta"]) == (58, 63, 5)
    assert t["mean"] == (58 + 60 + 63) / 3


def test_resting_hr_trend_needs_two_nights():
    assert summarize([night(8, rhr=58)])["rhr_trend"] is None
    assert summarize([night(8, rhr=None), night(9, rhr=None)])["rhr_trend"] is None


def test_render_shows_the_alert_and_names_what_weak_means():
    md = render_markdown(summarize([night(8, score=50), night(9, score=50), night(10, score=50)]))
    assert "ALERT: 3 weak nights in a row" in md
    assert "3 in a row raises the alert" in md
    assert "Resting HR: 58" in md


def test_render_without_an_alert_still_reports_the_streak():
    md = render_markdown(summarize([night(8), night(9)]))
    assert "Weak-night streak: 0" in md and "ALERT" not in md


def test_summary_is_deterministic():
    ns = [night(8, score=50), night(9), night(10, hrv=26.0)]
    assert summarize(ns) == summarize(ns[::-1])


def test_trends_command_reads_a_wellness_path(monkeypatch, capsys):
    from runcoach import cli
    from tests.test_fit_wellness import night_messages

    monkeypatch.setattr(cli, "iter_groups", lambda path: [("SLEEP.fit", night_messages())])
    assert cli.main(["trends", "unused-path"]) == 0
    out = capsys.readouterr().out
    assert "2026-10-12" in out and "Weak-night streak: 0" in out
