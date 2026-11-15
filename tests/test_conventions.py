import openpyxl
import pytest

from accesspath.cards import load_library, LibraryError
from accesspath.isncsci import parse_sci_name, sci_name, key_muscles_below
from conftest import DATA


def test_every_card_has_an_isb_term(library):
    assert all(c.ISB_term for c in library.cards.values())


@pytest.mark.parametrize("name, parsed", [
    ("SCI_C6_AIS_A", ("C6", "A")),
    ("SCI_T10_AIS_C_wheelchair", ("T10", "C")),
    ("SCI_S4-5_AIS_D", ("S4-5", "D")),
])
def test_sci_names_parse(name, parsed):
    assert parse_sci_name(name) == parsed


@pytest.mark.parametrize("name, why", [
    ("SCI_C6", "should be named"),
    ("SCI_C9_AIS_A", "not an ISNCSCI level"),
    ("SCI_C6_AIS_F", "AIS grade 'F'"),
])
def test_bad_sci_names_say_what_is_wrong(name, why):
    with pytest.raises(ValueError, match=why):
        parse_sci_name(name)


def test_sci_name_round_trips():
    assert sci_name("C6", "A", "wheelchair") == "SCI_C6_AIS_A_wheelchair"


def test_key_muscles_below_c6():
    below = [k["muscle"] for k in key_muscles_below("C6")]
    assert below[:3] == ["Elbow extensors", "Finger flexors", "Finger abductors (little finger)"]
    assert "Elbow flexors" not in below and "Wrist extensors" not in below


def test_library_rejects_a_malformed_sci_profile(tmp_path):
    wb = openpyxl.load_workbook(DATA / "card_library.xlsx")
    wb["Profiles"].append(["SCI_C6", "C6 injury", "seated_wheelchair", "wheelchair", "none", None])
    path = tmp_path / "lib.xlsx"
    wb.save(path)
    with pytest.raises(LibraryError, match="Profiles row .*SCI_<level>_AIS_<grade>"):
        load_library(path)


def test_isb_frame_round_trip():
    from accesspath.isb import to_isb, from_isb
    right, forward, up = [1, 0, 0], [0, 1, 0], [0, 0, 1]
    assert list(to_isb(forward)) == [1, 0, 0]  # ISB X = forward
    assert list(to_isb(up)) == [0, 1, 0]       # ISB Y = up
    assert list(to_isb(right)) == [0, 0, 1]    # ISB Z = right
    p = [0.3, -0.2, 1.1]
    assert list(from_isb(to_isb(p))) == pytest.approx(p)


@pytest.mark.parametrize("arm_dir, side, plane, elev", [
    ([0, 0, -1], "R", 0, 0),      # hanging
    ([0, 1, 0], "R", 90, 90),     # flexed 90: forward
    ([1, 0, 0], "R", 0, 90),      # abducted 90: out to the right
    ([-1, 0, 0], "L", 0, 90),     # left arm abducted: same ISB numbers
    ([0, 0, 1], "R", 0, 180),     # straight up
])
def test_shoulder_elevation(arm_dir, side, plane, elev):
    from accesspath.isb import shoulder_elevation
    assert shoulder_elevation(arm_dir, side) == pytest.approx((plane, elev))
