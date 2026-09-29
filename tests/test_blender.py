"""Blender rig agrees with the reach chain. Skipped unless Blender's Python module (pip install bpy) is present."""
import json
import math
import sys

import numpy as np
import pytest

from accesspath.kinematics import load_body, arm_chain
from accesspath.profiles import compose
from conftest import DATA, ROOT

bpy = pytest.importorskip("bpy")
sys.path.insert(0, str(ROOT / "blender"))
import rig  # noqa: E402


@pytest.fixture(scope="module")
def built(library):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = rig.build_armature(rig.body_dims(DATA / "body.json", "standing"))
    rig.apply_limits(obj, json.loads(json.dumps(compose(library, "stroke_R_severe").to_dict())))
    return obj


def tip(obj, side):
    bpy.context.view_layer.update()
    return np.array(obj.matrix_world @ obj.pose.bones[f"wrist_{side}"].tail)


@pytest.mark.parametrize("side", ["R", "L"])
def test_bones_match_card_names(built, side):
    for j in ["trunk", f"shoulder_{side}", f"elbow_{side}", f"wrist_{side}", f"hip_{side}", f"knee_{side}", f"ankle_{side}"]:
        assert j in built.pose.bones


def test_blender_pose_matches_reach_chain(built, library):
    body = load_body(DATA / "body.json", "standing")
    chain = arm_chain(body, compose(library, "baseline_standing"), "L")
    rng = np.random.default_rng(1)
    for _ in range(10):
        lean, fl, ab, el, wr = rng.uniform([0, -50, 0, 0, -60], [60, 170, 170, 140, 70])
        for pb in built.pose.bones:
            pb.rotation_euler = (0, 0, 0)
        built.pose.bones["trunk"].rotation_euler.x = math.radians(lean)
        built.pose.bones["shoulder_L"].rotation_euler = (math.radians(fl), 0, math.radians(ab))
        built.pose.bones["elbow_L"].rotation_euler.x = math.radians(el)
        built.pose.bones["wrist_L"].rotation_euler.x = math.radians(wr)
        want = chain.forward_kinematics([0, 0] + list(np.radians([lean, fl, ab, el, wr])) + [0])[:3, 3]
        assert np.allclose(tip(built, "L"), want, atol=1e-4)


def test_limit_constraint_locks_affected_abduction(built):
    for pb in built.pose.bones:
        pb.rotation_euler = (0, 0, 0)
    rest = tip(built, "R")
    built.pose.bones["shoulder_R"].rotation_euler.z = math.radians(-90)
    assert np.allclose(tip(built, "R"), rest)
