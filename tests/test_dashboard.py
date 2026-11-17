"""Static HTML dashboard (roadmap P2)."""

import datetime as dt

import pytest

from runcoach.analysis.dashboard import load_svg, render_html
from runcoach.analysis.run_report import build_report
from runcoach.analysis.weekly import summarize_weeks
from runcoach.config import Profile
from runcoach.metrics.load import load_series
from tests.fixtures import OCT8_EASY, OCT11_LONG, activity_for, rest_laps, streams_for

LOADS = {dt.date(2026, 10, 6): 22.0, dt.date(2026, 10, 8): 22.0, dt.date(2026, 10, 11): 33.0}
ACTS = [activity_for(OCT8_EASY, "2026-10-08", "Easy", suffer=22),
        activity_for(OCT11_LONG, "2026-10-11", "Long", suffer=33)]
GENERATED = dt.date(2026, 11, 17)


@pytest.fixture(scope="module")
def page():
    weeks = summarize_weeks(ACTS, LOADS, weeks=3, ctl0=17.13, atl0=12.98)
    points = list(load_series(LOADS, min(LOADS), max(LOADS), 17.13, 12.98))
    report = build_report({"name": "Long run", "start_date_local": "2026-10-11T07:00:00Z"},
                          rest_laps(OCT11_LONG), streams_for(OCT11_LONG), Profile(), kind="long")
    return render_html(weeks, points, report, Profile(), generated=GENERATED)


def test_page_is_self_contained(page):
    """No scripts, no external styles, no images, no network: it must open from a file or an email."""
    body = page.replace('xmlns="http://www.w3.org/2000/svg"', "")
    for forbidden in ("<script", "<link", "<img", "http://", "https://", "@import"):
        assert forbidden not in body, f"dashboard reaches outside itself: {forbidden}"


def test_page_has_the_expected_sections(page):
    assert page.startswith("<!doctype html>")
    for heading in ("Training load", "Weeks", "Latest run"):
        assert f">{heading}</h2>" in page
    assert page.rstrip().endswith("</html>")


def test_summary_cards_show_the_latest_week_and_load(page):
    assert "This week" in page and "15.74" in page.replace("15.7 km", "15.74")
    for label in ("CTL", "ATL", "TSB"):
        assert f">{label}</div>" in page


def test_weeks_table_lists_every_week_including_empty_ones(page):
    for week in ("2026-09-28", "2026-10-05"):
        assert week in page
    assert "0.00 km" in page                                   # a week with no runs is still listed


def test_the_latest_run_chart_is_embedded(page):
    assert page.count("<svg") == 2                             # load chart plus the run chart
    assert "Long run - 2026-10-11" in page


def test_output_is_deterministic():
    weeks = summarize_weeks(ACTS, LOADS, weeks=2)
    points = list(load_series(LOADS, min(LOADS), max(LOADS)))
    first = render_html(weeks, points, None, Profile(), generated=GENERATED)
    second = render_html(weeks, points, None, Profile(), generated=GENERATED)
    assert first == second                                     # no clock, no randomness


def test_the_zero_line_is_only_drawn_when_zero_is_in_range():
    """A screenshot showed the zero line outside the plot, striking through the legend."""
    class P:
        def __init__(self, day, ctl, atl, tsb):
            self.day, self.ctl, self.atl, self.tsb = day, ctl, atl, tsb

    all_positive = [P(dt.date(2026, 10, d), 15.0 + d, 11.0 + d, 3.0 + d) for d in (1, 2, 3)]
    spans_zero = [P(dt.date(2026, 10, d), 15.0, 11.0, -4.0 + d * 4) for d in (1, 2, 3)]
    assert 'stroke-dasharray="4 4"' not in load_svg(all_positive)
    assert 'stroke-dasharray="4 4"' in load_svg(spans_zero)


def test_load_chart_handles_no_points():
    assert "No load data" in load_svg([])


def test_page_escapes_a_run_name_containing_markup():
    report = build_report({"name": "<b>Run</b> & co", "start_date_local": "2026-10-11T07:00:00Z"},
                          rest_laps(OCT11_LONG), streams_for(OCT11_LONG), Profile(), kind="long")
    out = render_html([], [], report, Profile(), generated=GENERATED)
    assert "<b>Run</b>" not in out and "&lt;b&gt;Run&lt;/b&gt;" in out


def test_dashboard_command_writes_a_file(tmp_path, monkeypatch, capsys):
    from runcoach.cli import main
    from runcoach.strava.cache import Cache

    monkeypatch.setenv("RUNCOACH_DATA", str(tmp_path))
    cache = Cache(tmp_path / "cache")
    for aid, rows, day in ((1, OCT8_EASY, "2026-10-08"), (2, OCT11_LONG, "2026-10-11")):
        cache.put("activity", aid, activity_for(rows, day, "Run", suffer=22) | {"id": aid})
        cache.put("laps", aid, rest_laps(rows))
        cache.put("streams", aid, streams_for(rows))
    out_file = tmp_path / "dash.html"
    assert main(["dashboard", "--out", str(out_file), "--weeks", "2", "--kind", "long"]) == 0
    assert "wrote" in capsys.readouterr().out
    assert out_file.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_dashboard_command_needs_a_cache(tmp_path, monkeypatch):
    import pytest as _pytest

    from runcoach.cli import main
    monkeypatch.setenv("RUNCOACH_DATA", str(tmp_path))
    with _pytest.raises(SystemExit) as exc:
        main(["dashboard", "--out", str(tmp_path / "x.html")])
    assert "sync" in str(exc.value)
