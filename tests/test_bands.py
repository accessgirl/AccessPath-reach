import openpyxl
import pytest

from accesspath.cards import load_library, LibraryError
from accesspath.profiles import compose
from accesspath.kinematics import load_body, arm_chain, reach
from conftest import DATA


def with_profile(tmp_path, card_ids, band=None, height=None, pid="test_person"):
    """Copy of the real library with one extra profile row."""
    wb = openpyxl.load_workbook(DATA / "card_library.xlsx")
    ws = wb["Profiles"]
    head = [c.value for c in ws[1]]
    row = {"profile_id": pid, "description": "test", "posture": "seated_wheelchair", "mobility_aid": "wheelchair",
           "affected_side": "R", "card_ids": card_ids, "body_band": band, "body_height_in": height}
    ws.append([row.get(h) for h in head])
    path = tmp_path / "lib.xlsx"
    wb.save(path)
    return load_library(path)


def test_bands_cover_the_cdc_5th_to_95th(library):
    bands = sorted(library.bands.values(), key=lambda b: b.stature_min_in)
    assert [b.band_id for b in bands] == ["A", "B", "C", "D"]
    assert bands[0].stature_min_in <= 59.0 and bands[-1].stature_max_in >= 73.8
    assert all(b.stature_max_in - b.stature_min_in == 4 for b in bands)


def test_dial_inside_the_band(tmp_path):
    lib = with_profile(tmp_path, "stroke-shoulder-abd-1@60")
    assert compose(lib, "test_person").limits["shoulder_R"]["abd"] == [0.0, 60.0]


def test_no_dial_uses_the_cautious_edge(tmp_path):
    lib = with_profile(tmp_path, "stroke-shoulder-abd-1")
    assert compose(lib, "test_person").limits["shoulder_R"]["abd"] == [0.0, 45.0]


def test_dial_outside_the_band_is_rejected(tmp_path):
    with pytest.raises(LibraryError, match="outside its range"):
        with_profile(tmp_path, "stroke-shoulder-abd-1@120")


def test_placeholder_cannot_be_dialled(tmp_path):
    with pytest.raises(LibraryError, match="can't be dialled"):
        with_profile(tmp_path, "arthritis-shoulder-abd@90")


def test_band_tests_reach_at_its_shortest_height(tmp_path):
    lib = with_profile(tmp_path, "", band="B")
    p = compose(lib, "test_person")
    assert p.height_m == pytest.approx(63 * 0.0254, abs=1e-4)
    assert "shortest" in p.height_note


def test_measured_height_must_fit_its_band(tmp_path):
    with pytest.raises(LibraryError, match="outside band B"):
        with_profile(tmp_path, "", band="B", height=70)


def test_taller_body_reaches_higher(tmp_path):
    lib = with_profile(tmp_path, "", band="A", pid="short")
    lib2 = with_profile(tmp_path, "", band="D", pid="tall")
    short, tall = compose(lib, "short"), compose(lib2, "tall")
    target = [-0.33, 0.0, 1.75]
    r_short = reach(arm_chain(load_body(DATA / "body.json", "seated_wheelchair", short.height_m), short, "L"), target)
    r_tall = reach(arm_chain(load_body(DATA / "body.json", "seated_wheelchair", tall.height_m), tall, "L"), target)
    assert r_tall.error_m < r_short.error_m


def test_stroke_arm_lift_cards_use_the_lower_edge(tmp_path):
    lib = with_profile(tmp_path, "stroke-shoulder-flex-weak, stroke-shoulder-flex-milder@127")
    weak, milder = lib.cards["stroke-shoulder-flex-weak"], lib.cards["stroke-shoulder-flex-milder"]
    assert (weak.ROM_min_deg, weak.ROM_max_deg) == (48.4, 71.6)  # Taketomi 2023: 60.0 ± 11.6
    assert (milder.ROM_min_deg, milder.ROM_max_deg) == (116.4, 137.8)  # Yim & Kim 2024: 127.1 ± 10.7
    assert weak.status == milder.status == "sourced"
    lib2 = with_profile(tmp_path, "stroke-shoulder-flex-weak", pid="weak_only")
    assert compose(lib2, "weak_only").limits["shoulder_R"]["flex"][1] == 48.4
    assert compose(lib2, "weak_only").limits["shoulder_L"]["flex"][1] == 180.0
    assert compose(lib, "test_person").limits["shoulder_R"]["flex"][1] == 127.0  # last card wins, dialled
