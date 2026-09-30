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


def test_counter_outlet_needs_the_side_approach(results):
    # Facing the counter, the fingertip stops well short; parked alongside it, the arm reaches out over it.
    r = results[("baseline_wheelchair", "outlet_counter")]
    forward = [a for a in r.attempts if a["approach"] == "forward"]
    assert forward and not any(a["reached"] for a in forward) and min(a["error_m"] for a in forward) > 0.05
    assert r.approach == "side" and r.status == "CAUTION"  # reached, but above seated shoulder height


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
