import pytest

from accesspath import seated_size
from accesspath.kinematics import load_body
from accesspath.verify import run, load_json, check_doorway, check_knee_space
from accesspath.profiles import compose
from conftest import DATA

SIZE = seated_size.load(DATA / "wheelchair_size.json")


def test_values_are_the_papers_and_in_order():
    # Spot checks against Paquet & Feathers 2004, Tables 4 and 5 (overall sample).
    assert SIZE["acromion_height_cm"]["women"]["left"] == {"p5": 91.3, "p50": 100.5, "p95": 106.9}
    assert SIZE["acromion_height_cm"]["men"]["left"]["p95"] == 114.0
    assert SIZE["overall_breadth_cm"]["women"]["p95"] == 85.2
    assert SIZE["knee_height_cm"]["men"]["right"]["p95"] == 74.8
    for dim in ("acromion_height_cm", "knee_height_cm"):
        for sex in seated_size.SEXES:
            for c in SIZE[dim][sex].values():
                if isinstance(c, dict):
                    assert c["p5"] <= c["p50"] <= c["p95"]


def body_heights(library):
    return [None] + [b.stature_min_in * 0.0254 for b in library.bands.values()]


def test_avatar_shoulder_is_within_measured_wheelchair_users(library):
    """The business plan's check: the seated avatar against measured wheelchair users.

    Every body size the tool tests puts the seated shoulder inside the measured 5th-95th percentile range.
    But even the shortest band sits at the median woman, so the avatar reaches high for the shorter
    half of women in chairs; the IDeA population check is what covers them.
    """
    lo, _, hi = seated_size._range(SIZE, "acromion_height_cm")
    for h in body_heights(library):
        cm = load_body(DATA / "body.json", "seated_wheelchair", h).shoulder_height * 100
        assert lo <= cm <= hi, f"height {h}: shoulder {cm:.1f} cm outside {lo}-{hi} cm"
    shortest = min(h for h in body_heights(library) if h)
    cm = load_body(DATA / "body.json", "seated_wheelchair", shortest).shoulder_height * 100
    assert seated_size.place(SIZE, "acromion_height_cm", "women", cm).where == "50th-95th"


def test_shoulder_report_reads_plainly():
    text = seated_size.shoulder_report(SIZE, 1.06)
    assert "106.0 cm" in text and "women 50th-95th" in text and "Paquet & Feathers" in text


@pytest.mark.parametrize("width,status", [(0.80, "FAIL"), (0.83, "CAUTION"), (0.86, "PASS")])
def test_wheelchair_door_widths(library, width, status):
    p = compose(library, "baseline_wheelchair")
    r = check_doorway(p, load_body(DATA / "body.json", p.posture), {"task_id": "clear_doorway", "joints": []},
                      {"id": "d", "clear_width_m": width})
    assert r.status == status
    if status == "CAUTION":
        assert "1 in 20" in r.reason and "Paquet & Feathers" in r.reason


@pytest.mark.parametrize("underside,status", [(0.60, "FAIL"), (0.69, "CAUTION"), (0.75, "PASS")])
def test_knee_space(library, underside, status):
    r = check_knee_space(compose(library, "baseline_wheelchair"), {"task_id": "pull_under"},
                         {"id": "s", "knee_clearance_m": underside}, SIZE)
    assert r.status == status


def test_ada_height_knee_space_is_caution_not_pass(library):
    # 27 in meets the ADA, but taller users' knees (95th percentile up to 74.8 cm) won't fit.
    r = check_knee_space(compose(library, "baseline_wheelchair"), {"task_id": "pull_under"},
                         {"id": "s", "knee_clearance_m": 0.69}, SIZE)
    assert "meets the ADA's 27 in" in r.reason


def test_knee_space_missing_from_room_is_unverified(library):
    r = check_knee_space(compose(library, "baseline_wheelchair"), {"task_id": "pull_under"}, {"id": "s"}, SIZE)
    assert r.status == "UNVERIFIED"


def test_knee_space_only_checked_for_wheelchair_users(library):
    rs = run(library, load_json(DATA / "rooms" / "test_bathroom.json"), load_json(DATA / "tasks.json")["tasks"],
             DATA / "body.json", ["baseline_wheelchair", "baseline_standing"], ["pull_under"])
    assert [(r.profile, r.fixture, r.status) for r in rs] == [("baseline_wheelchair", "sink_vanity", "CAUTION")]
