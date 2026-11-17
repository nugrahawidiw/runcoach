"""Weekly summary (roadmap P1.6). Weeks run Monday to Sunday, per COACHING_CONTEXT section 3."""

import datetime as dt

from runcoach.analysis.weekly import render_markdown, summarize_weeks, week_start
from runcoach.metrics.load import load_series
from tests.fixtures import OCT8_EASY, OCT11_LONG, activity_for

EASY = activity_for(OCT8_EASY, "2026-10-08", "Easy", suffer=22)
LONG = activity_for(OCT11_LONG, "2026-10-11", "Long", suffer=33)
LOADS = {dt.date(2026, 10, 6): 22.0, dt.date(2026, 10, 8): 22.0, dt.date(2026, 10, 11): 33.0}


def test_week_start_is_the_monday():
    assert week_start(dt.date(2026, 10, 5)) == dt.date(2026, 10, 5)      # Monday itself
    assert week_start(dt.date(2026, 10, 8)) == dt.date(2026, 10, 5)      # Thursday
    assert week_start(dt.date(2026, 10, 11)) == dt.date(2026, 10, 5)     # Sunday
    assert week_start(dt.date(2026, 10, 12)) == dt.date(2026, 10, 12)    # next Monday


def test_two_runs_in_one_week_are_aggregated():
    (w,) = summarize_weeks([EASY, LONG], LOADS, weeks=1)
    assert (w["week_start"], w["week_end"]) == ("2026-10-05", "2026-10-11")
    assert w["runs"] == 2
    assert w["distance_m"] == 15738.15                 # 5738.15 + 10000, summed from the real laps
    assert w["moving_s"] == 6585                       # 2399 + 4186
    assert w["longest_m"] == 10000
    assert w["avg_pace"] == 6585 / (15738.15 / 1000.0)


def test_runs_in_different_weeks_are_not_merged():
    monday = activity_for(OCT8_EASY, "2026-10-12", "Easy")
    weeks = summarize_weeks([EASY, LONG, monday], LOADS | {dt.date(2026, 10, 12): 20.0}, weeks=2)
    assert [w["week_start"] for w in weeks] == ["2026-10-05", "2026-10-12"]
    assert [w["runs"] for w in weeks] == [2, 1]


def test_a_gap_week_between_runs_is_reported_with_zeros_and_a_decayed_load():
    later = activity_for(OCT8_EASY, "2026-10-25", "Easy", suffer=30)   # Sunday, two weeks after the long run
    weeks = summarize_weeks([EASY, LONG, later], LOADS | {dt.date(2026, 10, 25): 30.0}, weeks=3)
    assert [w["week_start"] for w in weeks] == ["2026-10-05", "2026-10-12", "2026-10-19"]
    rest = weeks[1]
    assert rest["runs"] == 0 and rest["distance_m"] == 0 and rest["avg_pace"] is None
    assert rest["longest_m"] == 0
    assert rest["tsb"] > weeks[0]["tsb"]               # a week off raises TSB
    assert rest["ctl"] < weeks[0]["ctl"]               # and lowers CTL


def test_load_numbers_match_load_series_for_the_same_day():
    (w,) = summarize_weeks([EASY, LONG], LOADS, weeks=1)
    points = {p.day: p for p in load_series(LOADS, min(LOADS), max(LOADS), 0.0, 0.0)}
    p = points[dt.date(2026, 10, 11)]
    assert (w["ctl"], w["atl"], w["tsb"]) == (p.ctl, p.atl, p.tsb)


def test_seeded_ctl_is_passed_through():
    (plain,) = summarize_weeks([EASY, LONG], LOADS, weeks=1)
    (seeded,) = summarize_weeks([EASY, LONG], LOADS, weeks=1, ctl0=17.13, atl0=12.98)
    assert seeded["ctl"] > plain["ctl"]


def test_summary_is_deterministic():
    assert summarize_weeks([EASY, LONG], LOADS, weeks=2) == summarize_weeks([LONG, EASY], LOADS, weeks=2)


def test_render_shows_distance_time_runs_and_the_load_line():
    md = render_markdown(summarize_weeks([EASY, LONG], LOADS, weeks=1))
    assert "2026-10-05" in md and "15.74 km" in md and "1:49:45" in md and "| 2 |" in md
    assert "CTL" in md and "ATL" in md and "TSB" in md


def test_weeks_argument_limits_how_many_weeks_are_returned():
    assert len(summarize_weeks([EASY, LONG], LOADS, weeks=1)) == 1
    assert len(summarize_weeks([EASY, LONG], LOADS, weeks=4)) == 4


def test_no_activities_gives_no_weeks():
    assert summarize_weeks([], {}, weeks=4) == []


def test_weekly_command_reads_the_cache_and_prints_the_table(tmp_path, monkeypatch, capsys):
    """End to end through the CLI, including the shared daily-load helper."""
    from runcoach.cli import main
    from runcoach.strava.cache import Cache

    monkeypatch.setenv("RUNCOACH_DATA", str(tmp_path))
    cache = Cache(tmp_path / "cache")
    cache.put("activity", 1, EASY | {"id": 1})
    cache.put("activity", 2, LONG | {"id": 2})
    assert main(["weekly", "--weeks", "1"]) == 0
    out = capsys.readouterr().out
    assert "| 2026-10-05 | 2 | 15.74 km | 1:49:45 |" in out
    assert "Planned vs actual needs a plan file" in out


def test_weekly_command_exits_cleanly_with_an_empty_cache(tmp_path, monkeypatch):
    import pytest

    from runcoach.cli import main

    monkeypatch.setenv("RUNCOACH_DATA", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        main(["weekly"])
    assert "sync" in str(exc.value)


def test_weekly_shows_planned_columns_when_a_plan_is_given():
    """Closes the gap left in P1.6: planned vs actual, now that P1.7 provides the plan as data."""
    from runcoach.analysis.plan import PlannedSession

    plan = [PlannedSession(dt.date(2026, 10, 8), "easy", distance_km=6.0),
            PlannedSession(dt.date(2026, 10, 11), "long", distance_km=16.0)]
    (w,) = summarize_weeks([EASY, LONG], LOADS, weeks=1, plan=plan)
    assert w["planned_runs"] == 2 and w["planned_km"] == 22.0
    md = render_markdown([w])
    assert "Runs (plan)" in md and "| 2 (2) |" in md and "15.74 (22) km" in md
    assert "Planned figures in brackets." in md


def test_weekly_omits_planned_columns_without_a_plan():
    (w,) = summarize_weeks([EASY, LONG], LOADS, weeks=1)
    assert w["planned_runs"] is None and w["planned_km"] is None
    assert "Runs (plan)" not in render_markdown([w])
