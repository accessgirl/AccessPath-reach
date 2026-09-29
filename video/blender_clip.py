"""Animated clip for the demo video: avatars reach out to each fixture while the camera swings round.

  python3 video/blender_clip.py -- --blend out/avatar.blend --results out/results.json \
      --profile stroke_R_moderate_wheelchair --out out/frames/clip_ [--frames 120]
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
    trunk = obj.pose.bones["trunk"]
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.11, location=obj.matrix_world @ (trunk.tail + Vector((0, 0, 0.13))))
    head = bpy.context.active_object
    head.data.materials.append(mat)
    sr._move(head, coll)
    _parent(head, obj, "trunk")


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
    a = ap.parse_args(argv)

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
    reach_end = int(a.frames * 0.45)
    for r in results:
        if not (r["task"].startswith("reach") and r["angles_deg"] and r["target_local"]):
            continue
        av = sr.place_avatar(base, r, fixtures[r["fixture"]], coll)
        pose = {n: tuple(av.pose.bones[n].rotation_euler) for n in REACH_BONES}
        for n in REACH_BONES:
            av.pose.bones[n].rotation_euler = (0, 0, 0)
        parented_stick_figure(av, coll, mat)
        if av.location.z < -0.01:
            sr.wheelchair(av, coll, rig.body_dims(os.path.join(ROOT, "data", "body.json"), "seated_wheelchair"))
        for n in REACH_BONES:
            pb = av.pose.bones[n]
            pb.keyframe_insert("rotation_euler", frame=8)
            pb.rotation_euler = pose[n]
            pb.keyframe_insert("rotation_euler", frame=reach_end)

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
