import pytest

from accesspath.verify import run, load_json
from conftest import DATA


@pytest.fixture(scope="module")
def results(library):
    rs = run(library, load_json(DATA / "rooms" / "test_bathroom.json"), load_json(DATA / "tasks.json")["tasks"],
             DATA / "body.json",
             ["baseline_wheelchair", "stroke_R_severe", "arthritis_both", "crutches_wet_floor", "kafo_L"])
    return {(r.profile, r.fixture): r for r in rs}


def test_wheelchair_doors(results):
    assert results[("baseline_wheelchair", "door_main")].status == "FAIL"  # 30 in < 32 in
    assert results[("baseline_wheelchair", "door_closet")].status == "PASS"


def test_wheelchair_above_shoulder_is_caution(results):
    r = results[("baseline_wheelchair", "switch_door")]
    assert r.status == "CAUTION" and "21%" in r.reason


def test_counter_outlet_out_of_reach_from_wheelchair(results):
    r = results[("baseline_wheelchair", "outlet_counter")]
    assert r.status == "FAIL" and r.error_m > 0.05


def test_stroke_uses_the_unaffected_arm(results):
    r = results[("stroke_R_severe", "shelf_high")]
    assert r.status == "PASS" and r.arm == "L"


def test_placeholders_make_passes_unverified(results):
    assert results[("arthritis_both", "outlet_low")].status == "UNVERIFIED"
    assert results[("crutches_wet_floor", "door_main")].status == "UNVERIFIED"
    assert results[("kafo_L", "door_closet")].status == "UNVERIFIED"
    assert results[("kafo_L", "switch_door")].status == "PASS"  # the brace doesn't touch the arm chain


def test_every_attempt_is_recorded(results):
    r = results[("baseline_wheelchair", "outlet_counter")]
    assert len(r.attempts) == 2 and not any(a["reached"] for a in r.attempts)  # both arms tried, both short
    assert {a["arm"] for a in r.attempts} == {"R", "L"}
    last = results[("stroke_R_severe", "shelf_high")].attempts[-1]
    assert last["reached"] and last["arm"] == "L"  # the attempt that passed is the last one tried
