
from runcoach.cli import main
from runcoach.strava.cache import Cache


def _put_run(cache, aid, day, suffer):
    cache.put("activity", aid, {"id": aid, "start_date_local": f"{day}T07:00:00Z", "suffer_score": suffer})


def test_load_warns_when_history_is_short_and_seed_silences_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RUNCOACH_DATA", str(tmp_path))
    cache = Cache(tmp_path / "cache")
    _put_run(cache, 1, "2026-10-06", 22)
    _put_run(cache, 2, "2026-10-11", 33)
    assert main(["load", "--days", "5"]) == 0
    assert "understated" in capsys.readouterr().out
    assert main(["load", "--days", "5", "--ctl0", "17.13", "--atl0", "12.98"]) == 0
    out = capsys.readouterr().out
    assert "understated" not in out and "2026-10-06" in out
