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
    assert results[("baseline_wheelchair", "door_main")].status == "DO NOT USE"  # 30 in < 32 in
    assert results[("baseline_wheelchair", "door_closet")].status == "PASS"


def test_wheelchair_reach_is_checked_against_measured_users(results):
    # Above seated shoulder height, but most measured wheelchair users could still reach 48 in from the side.
    r = results[("baseline_wheelchair", "switch_door")]
    assert r.status == "PASS" and r.population_pct >= 75 and "IDeA Center" in r.reason
    # A 1.70 m shelf: the avatar reaches it, almost no measured wheelchair user could.
    r = results[("baseline_wheelchair", "shelf_high")]
    assert r.status == "REACH CAUTION" and r.population_pct < 25


def test_counter_outlet_needs_the_side_approach(results):
    # Facing the counter, the fingertip stops well short; parked alongside it, the arm reaches out over it.
    r = results[("baseline_wheelchair", "outlet_counter")]
    forward = [a for a in r.attempts if a["approach"] == "forward"]
    assert forward and not any(a["reached"] for a in forward) and min(a["error_m"] for a in forward) > 0.05
    assert r.approach == "side" and r.status == "REACH CAUTION"  # reached, but few measured wheelchair users could


def test_stroke_uses_the_unaffected_arm(results):
    r = results[("stroke_R_severe", "shelf_high")]
    assert r.status == "PASS" and r.arm == "L"


def test_placeholders_make_passes_not_checked_yet(results):
    assert results[("arthritis_both", "outlet_low")].status == "NOT CHECKED YET"
    assert results[("arthritis_both", "outlet_low")].held_because == "not checked yet"
    assert results[("kafo_L", "door_closet")].status == "NOT CHECKED YET"
    assert results[("kafo_L", "switch_door")].status == "PASS"  # the brace doesn't touch the arm chain


def test_every_attempt_is_recorded(results):
    r = results[("baseline_wheelchair", "outlet_counter")]
    forward = [a for a in r.attempts if a["approach"] == "forward"]
    assert {a["arm"] for a in forward} == {"R", "L"}  # both arms tried head-on before trying the side
    last = results[("stroke_R_severe", "shelf_high")].attempts[-1]
    assert last["reached"] and last["arm"] == "L"  # the attempt that passed is the last one tried


def test_reach_paths_never_pass_through_a_surface(results, library):
    """Every successful reach comes with a path from rest, and every step of it clears the wall by the arm's thickness."""
    import numpy as np
    from accesspath.kinematics import load_body, arm_chain, joint_positions
    from accesspath.profiles import compose
    from accesspath.verify import _allowed
    room = {f["id"]: f for f in load_json(DATA / "rooms" / "test_bathroom.json")["fixtures"]}
    checked = 0
    for (pid, fid), r in results.items():
        for a in r.attempts:
            if not a["reached"]:
                continue
            profile = compose(library, pid)
            body = load_body(DATA / "body.json", profile.posture)
            chain = arm_chain(body, profile, a["arm"])
            obst = room[fid].get("obstruction")
            axis = 1 if a["approach"] == "forward" else 0
            ok = _allowed(axis, a["target_local"][axis], obst["depth_m"] if obst else 0.0, obst, body.limb_clearance)
            idx = [i for i, m in enumerate(chain.active_links_mask) if m]
            assert len(a["path_deg"]) >= 2
            for w0, w1 in zip(a["path_deg"], a["path_deg"][1:]):
                for t in np.linspace(0, 1, 30):
                    ang = np.zeros(len(chain.links))
                    for i in idx:
                        n = chain.links[i].name
                        ang[i] = np.radians(w0[n] + (w1[n] - w0[n]) * t)
                    assert ok(joint_positions(chain, ang)), f"{pid} {fid}: path enters a surface"
            checked += 1
    assert checked >= 5


def test_walking_aid_door_widths(results):
    # ADAAG A4.2.1(2): walking-aid users get through 32 in (0.815 m); the 30 in door is too narrow.
    assert results[("crutches_wet_floor", "door_main")].status == "DO NOT USE"
    assert results[("crutches_wet_floor", "door_closet")].status == "PASS"  # 0.86 m clears 0.84 m too


def test_crutches_between_the_two_sources_is_caution(library):
    from accesspath.verify import check_doorway
    from accesspath.kinematics import load_body
    from accesspath.profiles import compose
    p = compose(library, "crutches_wet_floor")
    r = check_doorway(p, load_body(DATA / "body.json", p.posture), {"task_id": "clear_doorway", "joints": []}, {"id": "d", "clear_width_m": 0.83})
    assert r.status == "REACH CAUTION" and "0.840" in r.reason


def test_every_reach_result_lists_the_values_it_rests_on(results):
    r = results[("stroke_R_severe", "shelf_high")]
    names = {i["input"] for i in r.inputs}
    assert {"shoulder_L flexion", "elbow_L flexion", "trunk flexion", "body height"} <= names
    shoulder = next(i for i in r.inputs if i["input"] == "shoulder_L flexion")
    assert shoulder["card_id"] == "base-shoulder_L-flex" and shoulder["evidence"] == "contested"
    wc = results[("baseline_wheelchair", "shelf_high")]
    lean = next(i for i in wc.inputs if i["input"] == "trunk lean allowed")
    assert lean["status"] == "interpolated"  # an estimate, and the result says so


# ---- Safe to Build Now, Nov 15, 2026 (Heather: GO) ----

REACH_TASKS = ("outlet_low", "outlet_counter", "switch_door", "shelf_high")


def test_crutch_user_standing_is_never_given_a_reach(results):
    """Stall -> Pivot (Nov 14): no study measured reach on crutches, so no distance, no angles, no attempts;
    the Balance layer takes over with a caution and its reason. This must never become a pass."""
    for fx in REACH_TASKS:
        r = results[("crutches_wet_floor", fx)]
        assert r.status == "SAFETY CAUTION" and r.came_from == "both"
        assert r.attempts == [] and r.angles_deg == {} and r.arm is None and r.error_m is None
        reach = next(l for l in r.layers if l["layer"] == "reach")
        balance = next(l for l in r.layers if l["layer"] == "balance")
        assert reach["status"] == "NOT CHECKED YET" and "No reach is given" in reach["reason"]
        assert balance["status"] == "SAFETY CAUTION" and "Both hands" in balance["reason"]
        assert "Do not walk on a wet floor with crutches" in balance["reason"]
        assert balance["basis"]
        assert "PASS" not in r.status and "may offer" not in r.label


def test_every_result_has_a_layer_a_source_tag_and_a_held_reason(results):
    for r in results.values():
        assert r.layers and r.layers[0]["layer"] == "reach"
        assert r.came_from in ("reach", "safety", "both")
        if r.status == "DO NOT USE":
            assert r.held_because == "fails the test"
        elif r.status == "NOT CHECKED YET":
            assert r.held_because == "not checked yet"
        else:
            assert r.held_because is None


def test_reach_only_results_list_the_safety_checks_not_run_yet(results):
    r = results[("baseline_wheelchair", "door_closet")]
    assert r.came_from == "reach" and set(r.safety_not_run) == {"balance", "slip", "transfer", "clearance", "layout"}
    r = results[("crutches_wet_floor", "outlet_low")]
    assert "balance" not in r.safety_not_run


def test_json_carries_the_label_and_layers(library):
    import json
    from accesspath.verify import to_json
    rs = run(library, load_json(DATA / "rooms" / "test_bathroom.json"), load_json(DATA / "tasks.json")["tasks"],
             DATA / "body.json", ["crutches_wet_floor"], ["reach_outlet"])
    d = json.loads(to_json(rs))[0]
    assert d["label"] == "SAFETY CAUTION" and "_extra_layers" not in d and len(d["layers"]) == 2
