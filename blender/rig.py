"""Blender side of the verifier: build the baseline skeleton and write card limits onto its bones.

Runs inside Blender (uses bpy only, not the accesspath package). Bone names match the card joint_ids;
each bone is named for the joint it rotates at (shoulder_R is the upper arm, rotating at the shoulder).

Frame: metres, origin on the floor under the hip centre, +X to the avatar's right, +Y forward, +Z up.
Every bone's local X axis is the flexion axis, so the Limit Rotation constraints read like the cards.
"""
import json
import math

import bpy
from mathutils import Vector

ARMATURE = "AccessPath_Baseline"

# joint -> motion pair -> (bone local axis, sign). sign -1 means the card's positive direction is a negative
# rotation about that axis (knees bend backwards; a right arm abducts by rotating the other way from a left).
AXIS_MAP = {
    "trunk": {"flex": ("x", 1)},
    "shoulder_R": {"flex": ("x", 1), "abd": ("z", -1)},
    "shoulder_L": {"flex": ("x", 1), "abd": ("z", 1)},
    "elbow": {"flex": ("x", 1)},
    "wrist": {"flex": ("x", 1)},
    "hip_R": {"flex": ("x", 1), "abd": ("z", -1)},
    "hip_L": {"flex": ("x", 1), "abd": ("z", 1)},
    "knee": {"flex": ("x", -1)},
    "ankle": {"dorsi": ("x", 1)},
}


def body_dims(body_path, posture):
    d = json.load(open(body_path))
    h, r = d["height_m"], d["segment_ratios"]
    p = d["postures"][posture]
    hip_h = p["hip_height_m"] if p["hip_height_m"] is not None else r["hip_height"] * h
    return {
        "hip_h": hip_h, "hip_h_standing": r["hip_height"] * h, "trunk": (r["shoulder_height"] - r["hip_height"]) * h,
        "half_sh": r["shoulder_width"] * h / 2, "half_hip": r["hip_width"] * h / 2,
        "upper_arm": r["upper_arm"] * h, "forearm": r["forearm"] * h, "hand": r["hand"] * h,
        "thigh": (r["hip_height"] - r["knee_height"]) * h, "shank": (r["knee_height"] - r["ankle_height"]) * h,
        "foot": r["foot"] * h,
    }


def build_armature(dims, name=ARMATURE):
    """One bone per joint card, in anatomical neutral (standing, arms hanging) so card angles apply as-is."""
    arm_data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, arm_data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    fwd, up = Vector((0, 1, 0)), Vector((0, 0, 1))

    def bone(name, head, tail, parent=None, z_axis=fwd):
        b = eb.new(name)
        b.head, b.tail = Vector(head), Vector(tail)
        b.align_roll(z_axis)
        if parent:
            b.parent = eb[parent]
            b.use_connect = (b.parent.tail - b.head).length < 1e-6
        return b

    d, z0 = dims, dims["hip_h_standing"]
    bone("pelvis", (0, 0, z0 - 0.1), (0, 0, z0))
    # Trunk points up; with Z forward its X axis is -X, so +X rotation leans forward like the cards.
    bone("trunk", (0, 0, z0), (0, 0, z0 + d["trunk"]), "pelvis")
    top = z0 + d["trunk"]
    for s, sx in (("R", 1), ("L", -1)):
        x = sx * d["half_sh"]
        bone(f"clavicle_{s}", (0, 0, top), (x, 0, top), "trunk", up)
        z1 = top - d["upper_arm"]
        z2 = z1 - d["forearm"]
        bone(f"shoulder_{s}", (x, 0, top), (x, 0, z1), f"clavicle_{s}")
        bone(f"elbow_{s}", (x, 0, z1), (x, 0, z2), f"shoulder_{s}")
        bone(f"wrist_{s}", (x, 0, z2), (x, 0, z2 - d["hand"]), f"elbow_{s}")

        hx = sx * d["half_hip"]
        z3 = z0 - d["thigh"]
        z4 = z3 - d["shank"]
        bone(f"hip_socket_{s}", (0, 0, z0 - 0.1), (hx, 0, z0), "pelvis", up)
        bone(f"hip_{s}", (hx, 0, z0), (hx, 0, z3), f"hip_socket_{s}")
        bone(f"knee_{s}", (hx, 0, z3), (hx, 0, z4), f"hip_{s}")
        bone(f"ankle_{s}", (hx, 0, z4), (hx, d["foot"] * 0.75, 0.0), f"knee_{s}", up)
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in obj.pose.bones:
        # Ball joints: flexion first, then abduction in the flexed frame. Same order as the IKPy reach
        # chain, so a pose here puts the fingertip where the verifier computed it.
        pb.rotation_mode = "ZXY" if pb.name.startswith(("shoulder_", "hip_")) else "XYZ"
    return obj


def pose_seated(obj, dims):
    """Sit the rig: hips and knees at 90 degrees, pelvis lowered to the wheelchair hip height."""
    for s in "RL":
        obj.pose.bones[f"hip_{s}"].rotation_euler.x = math.radians(90)
        obj.pose.bones[f"knee_{s}"].rotation_euler.x = math.radians(-90)
    obj.location.z = dims["hip_h"] - dims["hip_h_standing"]


def apply_limits(obj, composed):
    """Write a composed profile's limits (from `python -m accesspath compose`) as Limit Rotation constraints.

    Axes with no card are locked at 0 so nothing moves that the cards don't allow.
    """
    for joint, dofs in composed["limits"].items():
        pb = obj.pose.bones.get(joint)
        if pb is None:
            continue
        base = joint if joint in AXIS_MAP else joint.rsplit("_", 1)[0]
        mapping = AXIS_MAP.get(base, {})
        for c in [c for c in pb.constraints if c.type == "LIMIT_ROTATION"]:
            pb.constraints.remove(c)
        con = pb.constraints.new("LIMIT_ROTATION")
        con.name = "AccessPath card limits"
        con.owner_space = "LOCAL"
        for ax in "xyz":
            setattr(con, f"use_limit_{ax}", True)
            setattr(con, f"min_{ax}", 0.0)
            setattr(con, f"max_{ax}", 0.0)
        for dof, (lo, hi) in dofs.items():
            if dof not in mapping:
                continue
            ax, sign = mapping[dof]
            lo, hi = (lo, hi) if sign > 0 else (-hi, -lo)
            setattr(con, f"min_{ax}", math.radians(lo))
            setattr(con, f"max_{ax}", math.radians(hi))
    obj["accesspath_profile"] = composed["profile_id"]
    obj["accesspath_flags"] = json.dumps([f["message"] for f in composed["flags"]])


def duplicate(obj, new_name):
    new = obj.copy()
    new.data = obj.data.copy()
    new.name = new.data.name = new_name
    bpy.context.scene.collection.objects.link(new)
    return new
