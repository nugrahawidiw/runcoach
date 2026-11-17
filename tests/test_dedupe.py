"""Dedupe Strava vs Garmin copies of the same run (roadmap P1.5)."""

from runcoach.analysis.dedupe import find_duplicate_groups, resolve, source_of
from tests.fixtures import OCT11_LONG, activity_for


def entry(key, day="2026-10-11", hour="07:00:00", distance=None, **extra):
    act = activity_for(OCT11_LONG, day, "Long") | extra
    act["start_date_local"] = f"{day}T{hour}Z"
    if distance is not None:
        act["distance"] = distance
    return (key, act)


STRAVA = entry("1234", distance=10000.0)
GARMIN = entry("fit-20261011070000", distance=10000.0)


def test_source_is_read_from_the_cache_key():
    assert source_of("1234") == "strava"
    assert source_of("fit-20261011070000") == "garmin"


def test_same_start_and_distance_across_sources_is_one_group():
    (group,) = find_duplicate_groups([STRAVA, GARMIN])
    assert {source_of(k) for k, _ in group} == {"strava", "garmin"}


def test_two_minutes_apart_still_matches_but_three_does_not():
    assert find_duplicate_groups([STRAVA, entry("fit-x", hour="07:02:00", distance=10000.0)])
    assert not find_duplicate_groups([STRAVA, entry("fit-x", hour="07:03:01", distance=10000.0)])


def test_small_distance_differences_match_and_large_ones_do_not():
    assert find_duplicate_groups([STRAVA, entry("fit-x", distance=10060.0)])      # 60 m apart
    assert not find_duplicate_groups([STRAVA, entry("fit-x", distance=12000.0)])  # 2 km apart


def test_the_distance_tolerance_scales_with_distance():
    """100 m absolute, or 1% on longer runs, whichever is more generous."""
    half = entry("1", distance=21000.0)
    near = entry("fit-y", distance=21180.0)                                       # 180 m on 21 km is under 1%
    assert find_duplicate_groups([half, near])


def test_two_runs_from_the_same_source_are_never_deduped():
    """Only Strava vs Garmin. Two Strava rows at one time are a cache problem, not a duplicate import."""
    assert not find_duplicate_groups([entry("1", distance=10000.0), entry("2", distance=10000.0)])
    assert not find_duplicate_groups([entry("fit-a", distance=10000.0), entry("fit-b", distance=10000.0)])


def test_different_days_are_not_duplicates():
    assert not find_duplicate_groups([STRAVA, entry("fit-x", day="2026-10-12", distance=10000.0)])


def test_resolve_keeps_strava_by_default_and_reports_what_it_dropped():
    kept, dropped, groups = resolve([STRAVA, GARMIN])
    assert [k for k, _ in kept] == ["1234"]
    assert [k for k, _ in dropped] == ["fit-20261011070000"]
    assert len(groups) == 1


def test_resolve_can_prefer_garmin():
    kept, dropped, _ = resolve([STRAVA, GARMIN], prefer="garmin")
    assert [k for k, _ in kept] == ["fit-20261011070000"]
    assert [k for k, _ in dropped] == ["1234"]


def test_resolve_leaves_unmatched_runs_alone():
    other = entry("5678", day="2026-10-08", distance=5738.15)
    kept, dropped, groups = resolve([STRAVA, GARMIN, other])
    assert sorted(k for k, _ in kept) == ["1234", "5678"]
    assert dropped and not groups[1:] if groups else False


def test_resolve_is_deterministic_whatever_the_input_order():
    assert resolve([STRAVA, GARMIN])[0] == resolve([GARMIN, STRAVA])[0]


def test_an_activity_without_a_start_time_is_passed_through_untouched():
    broken = ("9", {"distance": 10000.0})
    kept, dropped, _ = resolve([STRAVA, GARMIN, broken])
    assert "9" in [k for k, _ in kept] and not any(k == "9" for k, _ in dropped)


def test_load_does_not_double_count_a_duplicated_run(tmp_path, monkeypatch, capsys):
    """The reason this matters: a run cached twice would otherwise inflate CTL."""
    from runcoach.cli import main
    from runcoach.strava.cache import Cache

    monkeypatch.setenv("RUNCOACH_DATA", str(tmp_path))
    cache = Cache(tmp_path / "cache")
    cache.put("activity", "1234", STRAVA[1] | {"suffer_score": 33})
    cache.put("activity", "fit-20261011070000", GARMIN[1] | {"suffer_score": 33})
    assert main(["load", "--days", "3", "--ctl0", "10", "--atl0", "10"]) == 0
    out = capsys.readouterr().out
    assert "duplicate" in out.lower()
    load_line = [ln for ln in out.splitlines() if ln.startswith("2026-10-11")][0]
    assert " 33.0 " in load_line                       # counted once, not 66


def test_dedupe_command_reports_the_pair_and_which_copy_is_kept(tmp_path, monkeypatch, capsys):
    from runcoach.cli import main
    from runcoach.strava.cache import Cache

    monkeypatch.setenv("RUNCOACH_DATA", str(tmp_path))
    cache = Cache(tmp_path / "cache")
    cache.put("activity", "1234", STRAVA[1])
    cache.put("activity", "fit-20261011070000", GARMIN[1])
    assert main(["dedupe"]) == 0
    out = capsys.readouterr().out
    assert "1 duplicated run(s)" in out
    assert "strava" in out and "garmin" in out
    assert "Nothing was deleted" in out


def test_dedupe_command_says_so_when_there_is_nothing_to_do(tmp_path, monkeypatch, capsys):
    from runcoach.cli import main
    from runcoach.strava.cache import Cache

    monkeypatch.setenv("RUNCOACH_DATA", str(tmp_path))
    Cache(tmp_path / "cache").put("activity", "1234", STRAVA[1])
    assert main(["dedupe"]) == 0
    assert "No duplicates found" in capsys.readouterr().out
