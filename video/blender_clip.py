"""Animated clip for the demo video: avatars reach out to each fixture while the camera swings round.

  python3 video/blender_clip.py -- --blend out/avatar.blend --results out/results.json \
      --profile stroke_R_moderate_wheelchair --out out/frames/clip_ [--frames 120] [--style careful]

The movement is staged to read as a person, not a machine (ideas from the "Builder design help - look and
movement guide", Drive -> Builder help): the head turns to the target first; the reach starts at the trunk
and shoulder, the elbow follows and the hand arrives last; the hand holds on the target, then the arm returns,
hand first; a slow breath runs underneath on its own animation layer. Only the timing changes: the reach pose
itself is the verifier's, unchanged.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
import rig  # noqa: E402
import show_results as sr  # noqa: E402

REACH_BONES = ["trunk", "shoulder_R", "shoulder_L", "elbow_R", "elbow_L", "wrist_R", "wrist_L"]

# Timing as fractions of the clip. "careful" is slow and held back (a guarded reach, e.g. after a stroke or with
# pain); "confident" is quicker. Per bone: when it starts moving out; the hand comes back first.
STYLES = {
    "careful": {"look": (0.03, 0.14), "start": {"trunk": 0.10, "shoulder": 0.12, "elbow": 0.17, "wrist": 0.22},
                "reach_end": 0.50, "hold_end": 0.64, "return_end": 0.93, "look_back": (0.68, 0.90)},
    "confident": {"look": (0.03, 0.10), "start": {"trunk": 0.08, "shoulder": 0.09, "elbow": 0.12, "wrist": 0.15},
                  "reach_end": 0.38, "hold_end": 0.52, "return_end": 0.80, "look_back": (0.56, 0.76)},
}
RETURN_LAG = {"wrist": 0.0, "elbow": 0.02, "shoulder": 0.04, "trunk": 0.04}  # hand leaves first on the way back
LOOK_STRENGTH = 0.75  # the eyes do the rest; a full head turn (or a chin on the chest for a low outlet) looks forced
BREATH_FRAMES = 72    # one breath every 3 s at 24 fps
BREATH_DEG = {"trunk": 1.2, "clavicle": 1.5}


def _joint(bone_name):
    return bone_name.split("_")[0]


def _style(profile_id, choice):
    if choice != "auto":
        return STYLES[choice]
    return STYLES["confident" if profile_id.startswith("baseline") else "careful"]


def head_with_face(obj, coll, mat, face_mat):
    """Head on a neck pivot (so it can turn), with a nose so the turn shows. Returns the pivot."""
    trunk = obj.pose.bones["trunk"]
    neck = bpy.data.objects.new(f"{obj.name}_neck", None)
    neck.empty_display_size = 0.05
    coll.objects.link(neck)
    neck.location = obj.matrix_world @ (trunk.tail + Vector((0, 0, 0.13)))
    neck.rotation_euler = (0, 0, obj.rotation_euler.z)  # local +Y = the way the avatar faces
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.11, location=neck.location)
    head = bpy.context.active_object
    head.data.materials.append(mat)
    sr._move(head, coll)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.035, location=(0, 0, 0))
    nose = bpy.context.active_object
    nose.scale = (0.8, 1.3, 0.8)
    nose.data.materials.append(face_mat)
    sr._move(nose, coll)
    for child in (head, nose):
        child.parent = neck
        child.matrix_parent_inverse.identity()
    head.location = (0, 0, 0)
    nose.location = (0, 0.11, -0.01)
    _parent(neck, obj, "trunk")
    return neck


def animate_look(neck, target, st, frames, coll):
    """Damped Track on the neck: off at rest, on (eased) just before the arm moves, off again on the way back."""
    aim = bpy.data.objects.new(f"{neck.name}_target", None)
    aim.location = target
    coll.objects.link(aim)
    con = neck.constraints.new("DAMPED_TRACK")
    con.target = aim
    con.track_axis = "TRACK_Y"
    for frac, value in ((st["look"][0], 0.0), (st["look"][1], LOOK_STRENGTH),
                        (st["look_back"][0], LOOK_STRENGTH), (st["look_back"][1], 0.0)):
        con.influence = value
        con.keyframe_insert("influence", frame=_f(frac, frames))


def animate_reach(av, pose, st, frames):
    """Rest -> reach pose -> hold -> rest, staggered from the trunk out to the hand."""
    for n in REACH_BONES:
        pb = av.pose.bones[n]
        j = _joint(n)
        keys = ((st["start"][j], (0, 0, 0)), (st["reach_end"], pose[n]),
                (st["hold_end"] + RETURN_LAG[j], pose[n]), (st["return_end"], (0, 0, 0)))
        for frac, value in keys:
            pb.rotation_euler = value
            pb.keyframe_insert("rotation_euler", frame=_f(frac, frames))


def animate_breath(av, frames):
    """A slow breath (chest and shoulders rise a little), looped, added on top of the reach."""
    for frame, amount in ((1, 0.0), (1 + BREATH_FRAMES // 2, 1.0), (1 + BREATH_FRAMES, 0.0)):
        # Positive: the trunk card allows no backward lean, so a negative value would be clamped to nothing.
        av.pose.bones["trunk"].rotation_euler = (math.radians(BREATH_DEG["trunk"] * amount), 0, 0)
        av.pose.bones["trunk"].keyframe_insert("rotation_euler", frame=frame)
        for s, sign in (("R", 1), ("L", -1)):
            pb = av.pose.bones[f"clavicle_{s}"]
            pb.rotation_euler = (0, 0, math.radians(sign * BREATH_DEG["clavicle"] * amount))
            pb.keyframe_insert("rotation_euler", frame=frame)


def hold_breath(strip, st, frames):
    """Fade the breath out during the reach and back in after, as people do. It also keeps the touch frame
    exactly on the verifier's pose (a breath on top would move the fingertip about 1.5 cm)."""
    strip.use_animated_influence = True
    for frac, value in ((st["look"][1], 1.0), (st["start"]["shoulder"] + 0.08, 0.0),
                        (st["hold_end"] + 0.04, 0.0), (st["return_end"], 1.0)):
        strip.influence = value
        strip.keyframe_insert("influence", frame=_f(frac, frames))


def push_to_layer(av, name, blend, repeat=1.0):
    """Move the active action onto its own NLA track, so layers combine instead of overwriting."""
    ad = av.animation_data
    action = ad.action
    action.name = f"{av.name}_{name}"
    ad.action = None
    track = ad.nla_tracks.new()
    track.name = name
    strip = track.strips.new(name, 1, action)
    strip.blend_type = blend
    strip.repeat = repeat
    strip.extrapolation = "HOLD_FORWARD" if blend == "REPLACE" else "NOTHING"
    return strip


def _f(frac, frames):
    return max(1, round(frac * frames))


def parented_stick_figure(obj, coll, mat):
    """Limbs parented to bones, so they follow the animated pose."""
    bpy.context.view_layer.update()
    for pb in obj.pose.bones:
        a, b = obj.matrix_world @ pb.head, obj.matrix_world @ pb.tail
        d = b - a
        if d.length < 1e-4 or pb.name == "pelvis":
            continue
        bpy.ops.mesh.primitive_cylinder_add(radius=0.028, depth=d.length, location=(a + b) / 2)
        c = bpy.context.active_object
        c.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        c.data.materials.append(mat)
        sr._move(c, coll)
        _parent(c, obj, pb.name)


def _parent(child, arm, bone):
    bpy.context.view_layer.update()
    world = child.matrix_world.copy()
    child.parent = arm
    child.parent_type = "BONE"
    child.parent_bone = bone
    bpy.context.view_layer.update()
    child.matrix_world = world


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--room", default=os.path.join(ROOT, "data", "rooms", "test_bathroom.json"))
    ap.add_argument("--out", required=True, help="frame path prefix")
    ap.add_argument("--frames", type=int, default=120)
    ap.add_argument("--samples", type=int, default=12)
    ap.add_argument("--only-frame", type=int)
    ap.add_argument("--style", choices=["auto", *STYLES], default="auto",
                    help="movement timing; auto = confident for baseline profiles, careful for the rest")
    a = ap.parse_args(argv)
    st = _style(a.profile, a.style)

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.blend))
    room = json.load(open(a.room))
    results = [r for r in json.load(open(a.results)) if r["profile"] == a.profile]
    base = bpy.data.objects[f"AccessPath_{a.profile}"]
    coll = bpy.data.collections.new("clip")
    bpy.context.scene.collection.children.link(coll)
    for o in bpy.data.objects:
        if o.type == "ARMATURE":
            o.hide_render = o.hide_viewport = True

    centre = Vector((1.2, 1.5, 0.0))
    cam_xy = Vector((1.2 + 3.6, 1.5 - 4.2))
    cutaway = [i for i, w in enumerate(room["walls"]) if sr._faces_away(*w, room, cam_xy)]
    sr.build_room(room, results, coll, cutaway)
    for o in coll.objects:
        if o.type == "FONT":
            d = Vector((cam_xy.x, cam_xy.y, 0)) - Vector((o.location.x, o.location.y, 0))
            o.rotation_euler.z = math.atan2(d.x, -d.y)
            o.data.size = 0.1

    fixtures = {f["id"]: f for f in room["fixtures"]}
    mat = sr.material("avatar", (0.2, 0.35, 0.75, 1))
    face_mat = sr.material("avatar_face", (0.1, 0.18, 0.42, 1))
    for r in results:
        if not (r["task"].startswith("reach") and r["angles_deg"] and r["target_local"]):
            continue
        fx = fixtures[r["fixture"]]
        av = sr.place_avatar(base, r, fx, coll)
        pose = {n: tuple(av.pose.bones[n].rotation_euler) for n in REACH_BONES}
        for n in REACH_BONES:
            av.pose.bones[n].rotation_euler = (0, 0, 0)
        parented_stick_figure(av, coll, mat)
        neck = head_with_face(av, coll, mat, face_mat)
        if av.location.z < -0.01:
            sr.wheelchair(av, coll, rig.body_dims(os.path.join(ROOT, "data", "body.json"), "seated_wheelchair"))
        animate_reach(av, pose, st, a.frames)
        push_to_layer(av, "reach", "REPLACE")
        animate_breath(av, a.frames)
        hold_breath(push_to_layer(av, "breath", "ADD", repeat=a.frames / BREATH_FRAMES + 1), st, a.frames)
        for n in REACH_BONES + ["clavicle_R", "clavicle_L"]:
            av.pose.bones[n].rotation_euler = (0, 0, 0)
        animate_look(neck, Vector(fx["position"]), st, a.frames, coll)

    # Camera on a turntable around the room centre.
    pivot = bpy.data.objects.new("pivot", None)
    pivot.location = centre
    coll.objects.link(pivot)
    bpy.ops.object.camera_add(location=(cam_xy.x, cam_xy.y, 3.6))
    cam = bpy.context.active_object
    cam.rotation_euler = (Vector((1.2, 1.5, 0.8)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 28
    _parent_obj(cam, pivot)
    scene = bpy.context.scene
    scene.camera = cam
    pivot.rotation_euler.z = math.radians(-12)
    pivot.keyframe_insert("rotation_euler", frame=1)
    pivot.rotation_euler.z = math.radians(14)
    pivot.keyframe_insert("rotation_euler", frame=a.frames)

    bpy.ops.object.light_add(type="SUN", location=(0, 0, 5))
    sun = bpy.context.active_object
    sun.data.energy = 3.5
    sun.rotation_euler = (math.radians(35), math.radians(15), math.radians(-30))
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.93, 0.93, 0.95, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = a.samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.frame_start, scene.frame_end = 1, a.frames
    scene.render.image_settings.file_format = "PNG"
    frames = [a.only_frame] if a.only_frame else range(1, a.frames + 1)
    for f in frames:
        scene.frame_set(f)
        scene.render.filepath = os.path.abspath(f"{a.out}{f:04d}.png")
        bpy.ops.render.render(write_still=True)
    print("done")


def _parent_obj(child, parent):
    bpy.context.view_layer.update()
    world = child.matrix_world.copy()
    child.parent = parent
    bpy.context.view_layer.update()
    child.matrix_world = world


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
