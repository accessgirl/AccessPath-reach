"""One short clip per reach attempt, for the walkthrough video: one avatar, one fixture, nothing else moving.

  python3 video/test_clips.py -- --blend out/avatar.blend --results out/results.json \
      --profile stroke_R_moderate_wheelchair --out out/tests [--frames 30]

Writes out/tests/<fixture>_<attempt>_<frame>.png for every attempt the verifier made, in the order it made them.
The arm moves from resting to the pose the verifier found (or its closest try, for a miss).
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
import rig  # noqa: E402
import show_results as sr  # noqa: E402
from blender_clip import parented_stick_figure, REACH_BONES, _parent_obj  # noqa: E402

HIGHLIGHT = (0.1, 0.45, 0.95, 1)
TARGET = (1.0, 0.8, 0.0, 1)


def room_centre(room):
    xs = [v for w in room["walls"] for v in (w[0], w[2])]
    ys = [v for w in room["walls"] for v in (w[1], w[3])]
    return Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0))


def camera_for(fx, room):
    """Side-on view from the nearer end of the wall, so the avatar's body doesn't hide the fixture."""
    p = Vector(fx["position"])
    n = Vector((*fx["wall_normal"], 0)).normalized()
    along = Vector((-n.y, n.x, 0))
    xs = [v for w in room["walls"] for v in (w[0], w[2])]
    ys = [v for w in room["walls"] for v in (w[1], w[3])]

    def room_left(d):  # distance to the room edge going along d
        lim = [((max(xs) if d.x > 0 else min(xs)) - p.x) / d.x] if abs(d.x) > 1e-6 else []
        lim += [((max(ys) if d.y > 0 else min(ys)) - p.y) / d.y] if abs(d.y) > 1e-6 else []
        return min(lim)
    if room_left(-along) < room_left(along):
        along = -along
    look = Vector((p.x, p.y, 0)) + n * 0.45 + Vector((0, 0, min(max(p.z, 0.6), 1.3)))
    loc = look + n * 1.5 + along * 2.6 + Vector((0, 0, 0.55))
    return loc, look


def clip(a, room, result, attempt, index):
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.blend))
    base = bpy.data.objects[f"AccessPath_{a.profile}"]
    for o in bpy.data.objects:
        if o.type == "ARMATURE":
            o.hide_render = o.hide_viewport = True
    coll = bpy.data.collections.new("test")
    bpy.context.scene.collection.children.link(coll)
    fx = next(f for f in room["fixtures"] if f["id"] == result["fixture"])

    cam_loc, look = camera_for(fx, room)
    cutaway = [i for i, w in enumerate(room["walls"]) if sr._faces_away(*w, room, cam_loc.to_2d())]
    sr.build_room(room, [], coll, cutaway)
    for o in list(coll.objects):
        if o.type == "FONT":  # no status labels: the video says the result
            bpy.data.objects.remove(o)
    for other in room["fixtures"]:  # doors aren't part of a reach test, and can block the camera
        if other["type"] == "door" and other["id"] != fx["id"]:
            bpy.data.objects.remove(bpy.data.objects[other["id"]])
    tested = bpy.data.objects[fx["id"]]
    tested.data.materials[0] = sr.material("highlight", HIGHLIGHT)
    if fx["type"] != "shelf":
        tested.scale *= 1.4
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.035, location=Vector(fx["position"]) + Vector((*fx["wall_normal"], 0)) * 0.04)
    target = bpy.context.active_object
    target.data.materials.append(sr.material("target", TARGET))
    sr._move(target, coll)

    av = sr.place_avatar(base, {**attempt, "arm": attempt["arm"], "approach": attempt["approach"]}, fx, coll)
    pose = {n: tuple(av.pose.bones[n].rotation_euler) for n in REACH_BONES}
    for n in REACH_BONES:
        av.pose.bones[n].rotation_euler = (0, 0, 0)
    parented_stick_figure(av, coll, sr.material("avatar", (0.2, 0.35, 0.75, 1)))
    if av.location.z < -0.01:
        sr.wheelchair(av, coll, rig.body_dims(os.path.join(ROOT, "data", "body.json"), "seated_wheelchair"))
    for n in REACH_BONES:
        pb = av.pose.bones[n]
        pb.keyframe_insert("rotation_euler", frame=1)
        pb.rotation_euler = pose[n]
        pb.keyframe_insert("rotation_euler", frame=a.frames)

    bpy.ops.object.camera_add(location=cam_loc)
    cam = bpy.context.active_object
    cam.rotation_euler = (look - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 28
    scene = bpy.context.scene
    scene.camera = cam
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
    scene.render.image_settings.file_format = "PNG"
    for f in range(1, a.frames + 1):
        scene.frame_set(f)
        scene.render.filepath = os.path.abspath(os.path.join(a.out, f"{result['fixture']}_{index}_{f:04d}.png"))
        bpy.ops.render.render(write_still=True)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--room", default=os.path.join(ROOT, "data", "rooms", "test_bathroom.json"))
    ap.add_argument("--out", required=True, help="folder for the frames")
    ap.add_argument("--frames", type=int, default=30, help="frames for the arm to move from rest to the reach")
    ap.add_argument("--samples", type=int, default=12)
    ap.add_argument("--fixture", action="append", help="only this fixture (repeatable)")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    room = json.load(open(a.room))
    for r in json.load(open(a.results)):
        if r["profile"] != a.profile or not r.get("attempts") or (a.fixture and r["fixture"] not in a.fixture):
            continue
        for i, att in enumerate(r["attempts"]):
            if att["angles_deg"] and att["target_local"]:
                clip(a, room, r, att, i)
                print(f"rendered {r['fixture']} attempt {i}")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
