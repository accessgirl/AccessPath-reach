from accesspath.profiles import compose


def test_baseline_limits(library):
    p = compose(library, "baseline_standing")
    assert p.limits["shoulder_R"] == {"flex": [-60.0, 180.0], "abd": [0.0, 180.0]}
    assert p.limits["knee_L"] == {"flex": [0.0, 135.0]}
    assert p.flags == []


def test_stroke_band_uses_lower_edge_on_affected_side_only(library):
    p = compose(library, "stroke_R_moderate")
    assert p.limits["shoulder_R"]["abd"] == [0.0, 45.0]  # band 45-90 -> 45
    assert p.limits["shoulder_L"]["abd"] == [0.0, 180.0]


def test_missing_axis_on_affected_joint_is_a_gap(library):
    p = compose(library, "stroke_R_moderate")
    gaps = p.placeholder_flags(["shoulder_R"])
    assert gaps and "flex still uses able-bodied values" in gaps[0].message
    assert not p.placeholder_flags(["shoulder_L"])


def test_task_threshold_is_not_a_limit(library):
    p = compose(library, "hemiplegia_R_mild")
    assert p.limits["shoulder_R"]["flex"] == [-60.0, 180.0]
    assert p.placeholder_flags(["elbow_R"])  # no usable elbow limit -> results using it are UNVERIFIED


def test_placeholders_flag_both_sides(library):
    p = compose(library, "arthritis_both")
    for j in ["shoulder_R", "shoulder_L", "knee_R", "knee_L", "hand_L"]:
        assert p.placeholder_flags([j]), j


def test_kafo_locks_one_knee(library):
    p = compose(library, "kafo_L")
    assert p.limits["knee_L"]["flex"] == [0.0, 0.0]
    assert p.limits["knee_R"]["flex"] == [0.0, 135.0]
