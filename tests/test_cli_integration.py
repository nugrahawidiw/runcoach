"""End-to-end CLI runs and awkward path handling (roadmap P2).

Every command is exercised through `main()` with a temporary data directory, so argument wiring, exit codes
and output are covered rather than just the functions underneath.

The path cases are the ones that bite on Windows, where this project runs: folders and files whose names
contain spaces, a path given as a relative string, a zip inside a nested folder, and a wrong path producing
a clear message rather than a traceback. The project's own directory contains a space (CLAUDE.md), so this
is not hypothetical.
"""

import datetime as dt
import json
import zipfile

import pytest

from runcoach.cli import main
from runcoach.strava.cache import Cache
from tests.fitwriter import synthetic_run
from tests.fixtures import OCT8_EASY, OCT11_LONG, activity_for, rest_laps, streams_for

START = dt.datetime(2026, 10, 11, 0, 22, 25, tzinfo=dt.UTC)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNCOACH_DATA", str(tmp_path))
    return tmp_path


@pytest.fixture
def cached(data_dir):
    cache = Cache(data_dir / "cache")
    for aid, rows, day in ((1, OCT8_EASY, "2026-10-08"), (2, OCT11_LONG, "2026-10-11")):
        act = activity_for(rows, day, "Run", suffer=22) | {"id": aid}
        cache.put("activity", aid, act)
        cache.put("laps", aid, rest_laps(rows))
        cache.put("streams", aid, streams_for(rows))
    return cache


def run_fit(directory, name="run.fit"):
    """A real activity FIT on disk, with real FIT bytes rather than a stub."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(synthetic_run(START))
    return path


def run_zip(directory, name="export.zip"):
    """The same run, inside a zip, which is how Garmin Connect hands activities over."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ACTIVITY.fit", synthetic_run(START))
    return path


# ---- every command runs ---------------------------------------------------------------------
def test_vdot_prints_equivalents(capsys):
    assert main(["vdot", "26:17", "5000"]) == 0
    out = capsys.readouterr().out
    assert "VDOT 36.1" in out and "Half" in out          # COACHING_CONTEXT golden number


def test_analyze_latest_picks_the_newest_cached_run(cached, capsys):
    assert main(["analyze", "latest", "--kind", "long"]) == 0
    assert "2026-10-11" in capsys.readouterr().out       # the later of the two cached runs


def test_analyze_json_is_machine_readable(cached, capsys):
    assert main(["analyze", "2", "--kind", "long", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["distance_km"] == pytest.approx(10.0)


def test_analyze_reports_an_uncached_activity_clearly(cached):
    with pytest.raises(SystemExit) as exc:
        main(["analyze", "999"])
    assert "not cached" in str(exc.value)


def test_load_weekly_and_dedupe_all_run(cached, capsys):
    assert main(["load", "--days", "7", "--ctl0", "10", "--atl0", "10"]) == 0
    assert main(["weekly", "--weeks", "2"]) == 0
    assert main(["dedupe"]) == 0
    out = capsys.readouterr().out
    assert "CTL" in out and "Week (Mon-Sun)" in out and "No duplicates found" in out


def test_fit_analyze_reads_a_real_fit_file(data_dir, tmp_path, capsys):
    assert main(["fit-analyze", str(run_fit(tmp_path / "g"))]) == 0
    assert "2026-10-11" in capsys.readouterr().out


def test_fit_import_caches_a_run_that_analyze_can_then_read(data_dir, tmp_path, capsys):
    assert main(["fit-import", str(run_fit(tmp_path / "g2"))]) == 0
    assert "imported" in capsys.readouterr().out
    assert main(["analyze", "latest"]) == 0
    assert "2026-10-11" in capsys.readouterr().out


def test_fit_analyze_writes_a_chart_beside_the_report(data_dir, tmp_path, capsys):
    out_svg = tmp_path / "chart.svg"
    assert main(["fit-analyze", str(run_fit(tmp_path / "g3")), "--chart", str(out_svg)]) == 0
    assert out_svg.read_text(encoding="utf-8").startswith("<svg")


def test_unknown_command_exits_two(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["nonsense"])
    assert exc.value.code == 2


# ---- awkward paths --------------------------------------------------------------------------
def test_a_folder_with_a_space_in_its_name(data_dir, tmp_path, capsys):
    """The project's own path contains a space; so do most Windows data folders."""
    run_zip(tmp_path / "Garmin Export 2026")
    assert main(["fit-analyze", str(tmp_path / "Garmin Export 2026")]) == 0
    assert "2026-10-11" in capsys.readouterr().out


def test_a_file_with_spaces_and_punctuation_in_its_name(data_dir, tmp_path, capsys):
    path = run_zip(tmp_path / "exports", name="morning run 2026-10-11 (1).zip")
    assert main(["fit-analyze", str(path)]) == 0
    assert "2026-10-11" in capsys.readouterr().out


def test_a_folder_name_with_non_ascii_characters(data_dir, tmp_path, capsys):
    run_zip(tmp_path / "Lari Pagi \u2013 Bandung")
    assert main(["fit-analyze", str(tmp_path / "Lari Pagi \u2013 Bandung")]) == 0
    assert "2026-10-11" in capsys.readouterr().out


def test_a_relative_path_works_from_the_working_directory(data_dir, tmp_path, monkeypatch, capsys):
    run_zip(tmp_path / "rel")
    monkeypatch.chdir(tmp_path)
    assert main(["fit-analyze", "rel"]) == 0
    assert "2026-10-11" in capsys.readouterr().out


def test_a_zip_nested_several_folders_deep_is_found(data_dir, tmp_path, capsys):
    run_zip(tmp_path / "top" / "2026" / "october")
    assert main(["fit-analyze", str(tmp_path / "top")]) == 0
    assert "2026-10-11" in capsys.readouterr().out


def test_a_path_that_is_not_fit_zip_or_folder_says_so(data_dir, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("not a fit file", encoding="utf-8")
    with pytest.raises(ValueError, match="Not a .fit, .zip or folder"):
        main(["fit-analyze", str(bad)])


def test_a_missing_path_is_reported_not_swallowed(data_dir, tmp_path):
    with pytest.raises((SystemExit, ValueError, FileNotFoundError)):
        main(["fit-analyze", str(tmp_path / "does-not-exist")])
