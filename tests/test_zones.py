"""Time-in-zone and the easy-HR guide check (roadmap P1.3)."""

from runcoach.config import Profile
from runcoach.metrics.zones import easy_guide_split, time_in_zone, zone_for
from tests.fixtures import OCT11_LONG

LOWERS = Profile().hr_zones


def test_zone_boundaries_are_contiguous():
    """Every bpm lands in exactly one zone; the published gaps (151, 160, 168) go to the lower zone."""
    assert zone_for(100, LOWERS) == "Z1"
    assert zone_for(143, LOWERS) == "Z1"
    assert zone_for(144, LOWERS) == "Z2"
    assert zone_for(150, LOWERS) == "Z2"
    assert zone_for(151, LOWERS) == "Z2"      # gap in the standing table
    assert zone_for(152, LOWERS) == "Z3"
    assert zone_for(159, LOWERS) == "Z3"
    assert zone_for(160, LOWERS) == "Z3"      # gap
    assert zone_for(161, LOWERS) == "Z4"
    assert zone_for(167, LOWERS) == "Z4"
    assert zone_for(168, LOWERS) == "Z4"      # gap
    assert zone_for(169, LOWERS) == "Z5"
    assert zone_for(200, LOWERS) == "Z5"


def test_time_in_zone_counts_one_second_per_sample():
    got = time_in_zone([140, 140, 150, 170], LOWERS)
    assert got == {"Z1": 2, "Z2": 1, "Z3": 0, "Z4": 0, "Z5": 1}


def test_time_in_zone_skips_missing_samples():
    assert time_in_zone([None, 140, None], LOWERS)["Z1"] == 1
    assert time_in_zone([], LOWERS) == {"Z1": 0, "Z2": 0, "Z3": 0, "Z4": 0, "Z5": 0}


def test_time_in_zone_on_the_oct11_long_run():
    """Each lap's real average HR held for its real moving time."""
    hr = []
    for secs, _dist, _grade, lap_hr, _cad in OCT11_LONG:
        hr += [lap_hr] * secs
    got = time_in_zone(hr, LOWERS)
    assert got == {"Z1": 2131, "Z2": 1658, "Z3": 397, "Z4": 0, "Z5": 0}
    assert sum(got.values()) == 4186


def test_easy_guide_split_on_the_oct11_long_run():
    hr = []
    for secs, _dist, _grade, lap_hr, _cad in OCT11_LONG:
        hr += [lap_hr] * secs
    at_or_below, above = easy_guide_split(hr, Profile().easy_hr_guide)
    assert (at_or_below, above) == (2131, 2055)


def test_easy_guide_split_treats_the_guide_as_inclusive():
    assert easy_guide_split([144, 145, 146], 145) == (2, 1)
