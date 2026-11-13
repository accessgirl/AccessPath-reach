import pytest

from accesspath import population
from accesspath.cards import load_library
from accesspath.verify import run, load_json
from conftest import DATA

POP = population.load(DATA / "idea_reach.json")


def test_grid_matches_the_charts():
    # Spot checks against IDeA Center DR #20, Figures 1 and 2.
    assert population.share(POP, "forward", 1.25, 0.0).pct_measured == 62  # ADA 48 in, straight ahead
    assert population.share(POP, "side", 1.25, 0.0).pct_measured == 99  # ADA 48 in, from the side
    assert population.share(POP, "forward", 1.25, 0.3).pct_measured == 16  # over a 12 in counter
    assert population.share(POP, "side", 1.05, 0.7).pct_measured == 11
    for way in ("forward", "side"):
        grid = POP[way]
        assert len(grid["pct"]) == len(POP["rows_mm"])
        assert all(len(row) == len(grid["offsets_mm"]) for row in grid["pct"])


def test_cautious_reading():
    s = population.share(POP, "side", 1.25, 0.0)
    assert s.pct == round(99 * 235 / 276)  # the 41 left out count as unable
    # Between columns, the farther one (fewer people) is used.
    assert population.share(POP, "side", 1.25, 0.15).pct_measured == 97  # the 200 mm column, not 100 mm


def test_outside_the_data():
    assert population.share(POP, "side", 0.30, 0.0).note == "below"  # not measured under 400 mm
    assert population.share(POP, "forward", 1.0, 0.6).note == "beyond"  # forward chart stops at 300 mm out
    assert population.share(POP, "side", 2.1, 0.0).pct == 0


@pytest.fixture(scope="module")
def results():
    lib = load_library(DATA / "card_library.xlsx")
    room = load_json(DATA / "rooms" / "test_bathroom.json")
    tasks = load_json(DATA / "tasks.json")["tasks"]
    return {(r.profile, r.fixture): r for r in run(lib, room, tasks, DATA / "body.json",
                                                   profile_ids=["baseline_wheelchair", "baseline_standing"])}


def test_avatar_pass_needs_measured_users_too(results):
    shelf = results[("baseline_wheelchair", "shelf_high")]
    assert shelf.status == "CAUTION" and shelf.population_pct == 5
    switch = results[("baseline_wheelchair", "switch_door")]
    assert switch.status == "PASS" and switch.population_pct == 83
    low = results[("baseline_wheelchair", "outlet_low")]
    assert low.status == "CAUTION" and "below 16 in" in low.reason


def test_standing_profiles_are_not_judged_by_wheelchair_data(results):
    assert results[("baseline_standing", "shelf_high")].population_pct is None
