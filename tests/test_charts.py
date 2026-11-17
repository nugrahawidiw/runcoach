"""Pace/cadence chart as inline SVG (roadmap P1.4)."""

import xml.etree.ElementTree as ET

from runcoach.analysis.charts import pace_cadence_svg
from runcoach.analysis.run_report import build_report
from runcoach.config import Profile
from tests.fixtures import OCT11_LONG, rest_laps, streams_for

ACT = {"name": "Long run", "start_date_local": "2026-10-11T07:00:00Z"}


def report(rows=OCT11_LONG, streams=True):
    return build_report(ACT, rest_laps(rows), streams_for(rows) if streams else None, Profile(), kind="long")


def test_chart_is_valid_self_contained_svg():
    svg = pace_cadence_svg(report(), Profile())
    root = ET.fromstring(svg)                               # raises if malformed
    assert root.tag.endswith("svg") and root.get("viewBox") == "0 0 900 440"
    for forbidden in ("<image", "<script", "http://", "https://www.", "@import"):
        assert forbidden not in svg.replace('xmlns="http://www.w3.org/2000/svg"', "")


def test_chart_draws_one_point_per_lap_and_both_series():
    svg = pace_cadence_svg(report(), Profile())
    assert svg.count("<circle") == len(OCT11_LONG)           # a marker per lap
    assert svg.count("<polyline") == 2                       # pace and cadence


def test_chart_shades_the_three_pace_bands_and_labels_them():
    svg = pace_cadence_svg(report(), Profile())
    for label in ("Easy", "Goal", "Tempo"):
        assert f">{label}</text>" in svg
    assert svg.count("<rect") == 4                           # background plus three bands


def test_chart_names_the_run_and_the_date():
    assert "Long run - 2026-10-11" in pace_cadence_svg(report(), Profile())


def test_chart_omits_the_cadence_line_when_no_lap_has_cadence():
    """Without streams build_report still falls back to lap cadence, so this needs laps with none at all."""
    rep = {"name": "No cadence", "date": "2026-10-11",
           "laps": [{"lap": i, "pace": 400.0 + i, "cadence_spm": None} for i in (1, 2, 3)]}
    svg = pace_cadence_svg(rep, Profile())
    assert svg.count("<polyline") == 1                       # pace only
    assert "Cadence spm" in svg                              # the axis label still explains the empty series


def test_chart_keeps_the_cadence_line_from_lap_data_when_streams_are_absent():
    assert pace_cadence_svg(report(streams=False), Profile()).count("<polyline") == 2


def test_faster_pace_is_drawn_higher():
    """Pace axis is inverted: lap 10 (6:37) must sit above lap 2 (7:43)."""
    svg = pace_cadence_svg(report(), Profile())
    ys = [float(p.split(",")[1]) for p in svg.split('<polyline points="')[1].split('"')[0].split()]
    assert ys[9] < ys[1]


def test_chart_handles_a_single_lap():
    svg = pace_cadence_svg(report(OCT11_LONG[:1]), Profile())
    ET.fromstring(svg)
    assert svg.count("<circle") == 1


def test_chart_handles_no_laps_without_crashing():
    svg = pace_cadence_svg({"name": "Empty", "date": "2026-10-11", "laps": []}, Profile())
    ET.fromstring(svg)
    assert "No laps with pace data" in svg


def test_chart_is_deterministic():
    assert pace_cadence_svg(report(), Profile()) == pace_cadence_svg(report(), Profile())


def test_chart_escapes_a_run_name_with_markup():
    svg = pace_cadence_svg({"name": "<Run & Co>", "date": "2026-10-11",
                            "laps": [{"lap": 1, "pace": 400.0, "cadence_spm": 170.0}]}, Profile())
    ET.fromstring(svg)
    assert "&lt;Run &amp; Co&gt;" in svg


def test_analyze_chart_flag_writes_a_file(tmp_path, monkeypatch, capsys):
    from runcoach import cli
    from runcoach.strava.cache import Cache

    monkeypatch.setenv("RUNCOACH_DATA", str(tmp_path))
    cache = Cache(tmp_path / "cache")
    cache.put("activity", 7, ACT | {"id": 7, "distance": 10000, "moving_time": 4186})
    cache.put("laps", 7, rest_laps(OCT11_LONG))
    cache.put("streams", 7, streams_for(OCT11_LONG))
    out_file = tmp_path / "chart.svg"
    assert cli.main(["analyze", "7", "--kind", "long", "--chart", str(out_file)]) == 0
    assert "wrote" in capsys.readouterr().out
    assert out_file.read_text(encoding="utf-8").startswith("<svg")


def test_axis_labels_stay_inside_the_canvas():
    """A screenshot showed 'Cadence spm' clipped at the right edge; this pins the fix."""
    svg = pace_cadence_svg(report(), Profile())
    block = svg.split(">Cadence spm<")[0].rsplit("<text", 1)[1]
    assert 'text-anchor="end"' in block
    x = float(block.split('x="')[1].split('"')[0])
    assert x <= 900                                          # inside the 900-wide viewBox
