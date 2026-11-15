"""The result words, layers and steps (Heather's decisions, Nov 14-15, 2026)."""
import pytest

from accesspath import results as R
from accesspath.results import LayerResult, combine


def test_the_five_words_and_never_safe():
    assert set(R.STATUSES) == {"PASS", "REACH CAUTION", "SAFETY CAUTION", "NOT CHECKED YET", "DO NOT USE"}
    assert R.LABEL["PASS"] == "PASS: may offer"
    for word in R.LABEL.values():  # no result is ever called "safe"
        assert "SAFE" not in word.upper().replace("SAFETY CAUTION", "")
    assert "does not say it is safe" in R.MEANING["PASS"]


def test_worst_layer_wins_and_a_gap_is_never_a_pass():
    reach_pass = LayerResult("reach", "PASS", "reached")
    assert combine([reach_pass]) == ("PASS", "reach", None)
    gap = LayerResult("slip", "NOT CHECKED YET", "no wet number")
    assert combine([reach_pass, gap]) == ("NOT CHECKED YET", "both", "not checked yet")
    caution = LayerResult("balance", "SAFETY CAUTION", "both hands on crutches")
    assert combine([reach_pass, gap, caution])[0] == "SAFETY CAUTION"
    fail = LayerResult("transfer", "DO NOT USE", "fails")
    assert combine([reach_pass, caution, fail]) == ("DO NOT USE", "both", "fails the test")
    assert combine([LayerResult("reach", "REACH CAUTION", "few can"), caution])[0] == "SAFETY CAUTION"


def test_each_caution_belongs_to_its_own_kind_of_layer():
    with pytest.raises(ValueError):
        LayerResult("slip", "REACH CAUTION", "x")
    with pytest.raises(ValueError):
        LayerResult("reach", "SAFETY CAUTION", "x")
    with pytest.raises(ValueError):
        LayerResult("reach", "SAFE", "x")
    with pytest.raises(ValueError):
        LayerResult("comfort", "PASS", "x")


def test_not_checked_yet_and_do_not_use_are_never_merged():
    assert R.held_because("DO NOT USE") != R.held_because("NOT CHECKED YET")
    assert R.held_because("PASS") is None and R.held_because("REACH CAUTION") is None


def test_steps_structure_only():
    wet_shower = {"task_id": "shower_to_wheelchair", "steps": [
        {"step": "step out of the shower", "movement": "step across", "surface": "shower floor to bathroom floor",
         "wet_condition": "water", "contact": "bare feet", "support": "grab bar", "direction": "out"},
        {"step": "pivot to sit on the bench", "movement": "pivot", "surface": "bench seat",
         "wet_condition": "water", "contact": "bare feet; seated skin", "support": "bench edge", "direction": "down to sit"},
        {"step": "stand up from the bench", "movement": "stand up", "direction": "up"},
        {"step": "pivot to the wheelchair", "movement": "pivot", "direction": "after standing up"},
    ]}
    assert len(R.check_steps(wet_shower)) == 4
    assert R.check_steps({"task_id": "t"}) == []
    with pytest.raises(ValueError, match="unknown field"):
        R.check_steps({"task_id": "t", "steps": [{"step": "x", "friction": 0.4}]})  # no numbers in steps yet
    with pytest.raises(ValueError, match="say what happens"):
        R.check_steps({"task_id": "t", "steps": [{"movement": "pivot"}]})


def test_old_videos_still_get_their_old_words():
    assert R.legacy_status("DO NOT USE") == "FAIL" and R.legacy_status("NOT CHECKED YET") == "UNVERIFIED"
    assert R.legacy_status("REACH CAUTION") == "CAUTION" and R.legacy_status("PASS") == "PASS"
