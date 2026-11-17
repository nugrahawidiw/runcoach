"""Plan as data: load, compare with actuals, export .ics (roadmap P1.7)."""

import datetime as dt

import pytest

from runcoach.analysis.plan import compare, load_plan, render_markdown, to_ics
from tests.fixtures import OCT8_EASY, OCT11_LONG, activity_for

PLAN_TOML = """
[[session]]
date = 2026-10-08
kind = "easy"
title = "Easy 6 km"
distance_km = 6.0

[[session]]
date = 2026-10-11
kind = "long"
title = "Long run"
distance_km = 16.0
target_pace = "6:58"
"""


def write_plan(tmp_path, text=PLAN_TOML):
    p = tmp_path / "plan.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_plan_reads_dates_kinds_and_paces(tmp_path):
    plan = load_plan(write_plan(tmp_path))
    assert [s.date for s in plan] == [dt.date(2026, 10, 8), dt.date(2026, 10, 11)]
    assert [s.kind for s in plan] == ["easy", "long"]
    assert plan[1].distance_km == 16.0
    assert plan[1].target_pace == 418.0            # 6:58 in seconds per km


def test_load_plan_sorts_by_date(tmp_path):
    reversed_toml = "\n".join(PLAN_TOML.strip().split("\n\n")[::-1])
    assert [s.date for s in load_plan(write_plan(tmp_path, reversed_toml))][0] == dt.date(2026, 10, 8)


def test_load_plan_rejects_an_unknown_key_rather_than_ignoring_it(tmp_path):
    bad = '[[session]]\ndate = 2026-10-08\nkind = "easy"\npaec = "6:58"\n'
    with pytest.raises(ValueError, match="unknown key"):
        load_plan(write_plan(tmp_path, bad))


def test_load_plan_requires_date_and_kind(tmp_path):
    with pytest.raises(ValueError, match="required"):
        load_plan(write_plan(tmp_path, '[[session]]\ndate = 2026-10-08\n'))


def test_load_plan_reports_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_plan(tmp_path / "nope.toml")


def test_compare_marks_done_missed_and_unplanned(tmp_path):
    plan = load_plan(write_plan(tmp_path))
    acts = [activity_for(OCT8_EASY, "2026-10-08", "Easy"), activity_for(OCT8_EASY, "2026-10-10", "Bonus")]
    c = compare(plan, acts)
    assert (c.done, c.missed, c.unplanned) == (1, 1, 1)
    by_date = {r["date"]: r for r in c.rows}
    assert by_date["2026-10-08"]["status"] == "done"
    assert by_date["2026-10-11"]["status"] == "missed"
    assert by_date["2026-10-10"]["status"] == "unplanned"


def test_compare_reports_planned_and_actual_distance_without_judging_the_match(tmp_path):
    plan = load_plan(write_plan(tmp_path))
    c = compare(plan, [activity_for(OCT11_LONG, "2026-10-11", "Long")])
    row = next(r for r in c.rows if r["date"] == "2026-10-11")
    assert row["planned_km"] == 16.0 and row["actual_km"] == 10.0     # short of plan, still "done"
    assert row["status"] == "done"


def test_compare_is_deterministic(tmp_path):
    plan = load_plan(write_plan(tmp_path))
    acts = [activity_for(OCT8_EASY, "2026-10-08"), activity_for(OCT11_LONG, "2026-10-11")]
    assert compare(plan, acts).rows == compare(plan, acts[::-1]).rows


def test_render_lists_every_row_and_the_totals(tmp_path):
    plan = load_plan(write_plan(tmp_path))
    md = render_markdown(compare(plan, [activity_for(OCT8_EASY, "2026-10-08", "Easy")]))
    assert "DONE" in md and "MISSED" in md and "1 done, 1 missed, 0 unplanned." in md


def test_ics_export_is_valid_and_has_one_all_day_event_per_session(tmp_path):
    ics = to_ics(load_plan(write_plan(tmp_path))).decode()
    assert ics.startswith("BEGIN:VCALENDAR") and ics.rstrip().endswith("END:VCALENDAR")
    assert ics.count("BEGIN:VEVENT") == 2
    assert "DTSTART;VALUE=DATE:20261011" in ics                      # all-day, not a timed event
    assert "SUMMARY:long: Long run" in ics
    assert "target 6:58/km" in ics


def test_ics_folds_long_lines_so_no_line_exceeds_75_octets(tmp_path):
    """The reason the roadmap asks for the icalendar library: a hand-built .ics broke on folding."""
    long_toml = ('[[session]]\ndate = 2026-10-11\nkind = "long"\ntitle = "'
                 + "Long run with a deliberately very long description " * 4 + '"\n')
    for line in to_ics(load_plan(write_plan(tmp_path, long_toml))).decode().split("\r\n"):
        assert len(line.encode()) <= 75


def test_plan_command_compares_against_the_cache(tmp_path, monkeypatch, capsys):
    from runcoach.cli import main
    from runcoach.strava.cache import Cache

    monkeypatch.setenv("RUNCOACH_DATA", str(tmp_path))
    Cache(tmp_path / "cache").put("activity", 1, activity_for(OCT8_EASY, "2026-10-08", "Easy") | {"id": 1})
    assert main(["plan", str(write_plan(tmp_path))]) == 0
    out = capsys.readouterr().out
    assert "DONE" in out and "1 done, 1 missed, 0 unplanned." in out


def test_plan_command_writes_an_ics_file(tmp_path, capsys):
    from runcoach.cli import main

    out_file = tmp_path / "plan.ics"
    assert main(["plan", str(write_plan(tmp_path)), "--ics", str(out_file)]) == 0
    assert "wrote" in capsys.readouterr().out
    assert out_file.read_bytes().startswith(b"BEGIN:VCALENDAR")
