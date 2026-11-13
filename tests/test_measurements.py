import pytest

from accesspath.cards import load_library, LibraryError
from accesspath.kinematics import load_body
from accesspath.profiles import compose
from accesspath.verify import check_reach, check_knee_space
from conftest import DATA

TASK = {"task_id": "t", "joints": ["trunk", "shoulder", "elbow", "wrist", "hand"]}


def body_for(library, pid):
    p = compose(library, pid)
    return p, load_body(DATA / "body.json", p.posture, p.height_m, p.measured)


def highest_reach_cm(library, pid):
    p, b = body_for(library, pid)
    best = None
    for cm in range(150, 230, 2):
        fx = {"id": "x", "type": "shelf", "position": [0, 0, cm / 100], "approach": ["side"]}
        if check_reach(p, b, TASK, fx, [], None).status in ("PASS", "CAUTION"):
            best = cm
    return best


def test_measurements_replace_the_height_estimate(library):
    _, b = body_for(library, "wheelchair_long_trunk")
    assert b.hip_height == pytest.approx(20 * 0.0254)
    assert b.trunk == pytest.approx(23.5 * 0.0254)
    assert b.arm_length == pytest.approx(29 * 0.0254)
    assert b.knee_height == pytest.approx(22 * 0.0254)


def test_same_height_different_trunk_reaches_differently(library):
    """Heather's body-shape point: height alone hides trunk length. Same height and arms, 3.5 in more trunk."""
    long_, short = highest_reach_cm(library, "wheelchair_long_trunk"), highest_reach_cm(library, "wheelchair_short_trunk")
    assert long_ - short >= 6


def test_results_say_which_values_were_measured(library):
    p, b = body_for(library, "wheelchair_short_trunk")
    fx = {"id": "x", "type": "shelf", "position": [0, 0, 1.2], "approach": ["side"]}
    r = check_reach(p, b, TASK, fx, [], None)
    measured = {i["input"] for i in r.inputs if i["status"] == "measured"}
    assert {"seat (hip) height", "trunk (seat to shoulder)", "arm length"} <= measured


def test_personal_knee_height_drives_the_knee_check(library):
    p, b = body_for(library, "wheelchair_long_trunk")  # knee 22 in = 55.9 cm, allowance 5 cm
    def status(under_m):
        return check_knee_space(p, {"task_id": "k"}, {"id": "s", "knee_clearance_m": under_m}, None, b).status
    assert status(0.55) == "FAIL" and status(0.58) == "CAUTION" and status(0.62) == "PASS"


def test_centimetres_are_caught_as_a_typo(tmp_path):
    with pytest.raises(LibraryError, match="centimetres"):
        load_library(edited_profile(tmp_path, "wheelchair_long_trunk", seated_shoulder_in=60))


def test_seat_measures_only_for_seated_profiles(tmp_path):
    with pytest.raises(LibraryError, match="seated profile"):
        load_library(edited_profile(tmp_path, "baseline_standing", seat_height_in=20))


def edited_profile(tmp_path, pid, **changes):
    import openpyxl
    wb = openpyxl.load_workbook(DATA / "card_library.xlsx")
    ws = wb["Profiles"]
    head = [c.value for c in ws[1]]
    for row in ws.iter_rows(min_row=2):
        if row[0].value == pid:
            for col, v in changes.items():
                row[head.index(col)].value = v
    path = tmp_path / "lib.xlsx"
    wb.save(path)
    return path
