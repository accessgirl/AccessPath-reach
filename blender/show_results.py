"""Step 6 view: the room, each fixture colored by its result, and the avatar posed reaching each fixture.

  python -m accesspath verify --profile stroke_R_moderate -o out/results.json
  blender out/avatar.blend --python blender/show_results.py -- --room data/rooms/test_bathroom.json \
      --results out/results.json --profile stroke_R_moderate [--render out/view.png]

Needs the profile's rig in the file (apply_profile.py). Green PASS, amber CAUTION, grey UNVERIFIED, red FAIL.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector, Matrix  # noqa: E402
import rig  # noqa: E402

COLORS = {"PASS": (0.15, 0.6, 0.3, 1), "CAUTION": (0.95, 0.65, 0.1, 1),
          "UNVERIFIED": (0.55, 0.55, 0.6, 1), "FAIL": (0.85, 0.15, 0.15, 1)}


def material(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = rgba
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = rgba
    return m


def box(name, center, size, mat, coll):
    bpy.ops.mesh.primitive_cube_add(location=center)
    o = bpy.context.active_object
    o.name = name
    o.scale = [s / 2 for s in size]
    o.data.materials.append(mat)
    _move(o, coll)
    return o


def label(text, loc, coll, size=0.07):
    bpy.ops.object.text_add(location=loc, rotation=(math.radians(90), 0, 0))
    o = bpy.context.active_object
    o.data.body = text
    o.data.size = size
    o.data.align_x = "CENTER"
    o.data.materials.append(material("label", (0.05, 0.05, 0.05, 1)))
    _move(o, coll)
    return o


def _move(o, coll):
    for c in o.users_collection:
        c.objects.unlink(o)
    coll.objects.link(o)


def build_room(room, results, coll, cutaway=()):
    """`cutaway` walls are drawn knee-high so a still image can see into the room."""
    wall_mat = material("wall", (0.85, 0.85, 0.82, 1))
    xs = [v for w in room["walls"] for v in (w[0], w[2])]
    ys = [v for w in room["walls"] for v in (w[1], w[3])]
    centre = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0))
    for i, (x1, y1, x2, y2) in enumerate(room["walls"]):
        h = 0.3 if i in cutaway else room.get("wall_height", 2.4)
        a, b = Vector((x1, y1, 0)), Vector((x2, y2, 0))
        # The wall's inside face sits on the wall line, where the verifier puts it; its thickness goes outward.
        out = Vector((-(b - a).y, (b - a).x, 0)).normalized()
        if out.dot((a + b) / 2 - centre) < 0:
            out = -out
        o = box(f"wall_{i}", (a + b) / 2 + out * 0.025 + Vector((0, 0, h / 2)), ((b - a).length, 0.05, h), wall_mat, coll)
        o.rotation_euler.z = math.atan2(y2 - y1, x2 - x1)
    floor = box("floor", (1.2, 1.5, -0.01), (2.6, 3.2, 0.02), material("floor", (0.6, 0.58, 0.55, 1)), coll)
    floor.name = "floor"

    by_fixture = {r["fixture"]: r for r in results}
    for fx in room["fixtures"]:
        r = by_fixture.get(fx["id"])
        status = r["status"] if r else "UNVERIFIED"
        mat = material(f"status_{status}", COLORS[status])
        x, y, z = fx["position"]
        n = Vector((*fx["wall_normal"], 0))
        if fx["type"] == "door":
            w = fx["clear_width_m"]
            o = box(fx["id"], Vector((x, y, 1.0)) + n * 0.04, (w, 0.02, 2.0), mat, coll)
            o.rotation_euler.z = math.atan2(n.y, n.x) + math.pi / 2
            z = 2.1
        else:
            size = (0.3, 0.3, 0.03) if fx["type"] == "shelf" else (0.08, 0.02, 0.12)
            o = box(fx["id"], Vector((x, y, z)) + n * 0.02, size, mat, coll)
            o.rotation_euler.z = math.atan2(n.y, n.x) + math.pi / 2
            if "obstruction" in fx:
                ob = fx["obstruction"]
                along = Vector((-n.y, n.x, 0))
                c = Vector((x, y, ob["height_m"] / 2)) + n * ob["depth_m"] / 2
                counter = box(f"{fx['id']}_counter", c, (0.9, ob["depth_m"], ob["height_m"]),
                              material("counter", (0.75, 0.7, 0.62, 1)), coll)
                counter.rotation_euler.z = math.atan2(along.y, along.x)
        t = label(f"{fx['id']}: {status}", Vector((x, y, z + 0.15)) + n * 0.1, coll)
        t.rotation_euler.z = math.atan2(n.y, n.x) + math.pi / 2


def wheelchair(obj, coll, dims):
    """Simple seat and wheels under a seated avatar, for the still image."""
    mat = material("wheelchair", (0.2, 0.2, 0.22, 1))
    m = obj.matrix_world
    seat_h = dims["hip_h"] - 0.09
    parts = [box("seat", m @ Vector((0, 0.18, seat_h - obj.location.z)), (0.45, 0.45, 0.04), mat, coll)]
    for sx in (1, -1):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.3, depth=0.03,
                                            location=m @ Vector((sx * 0.26, 0.05, 0.3 - obj.location.z)))
        w = bpy.context.active_object
        w.rotation_euler = (0, math.radians(90), obj.rotation_euler.z)
        w.data.materials.append(mat)
        _move(w, coll)
        parts.append(w)
    parts[0].rotation_euler.z = obj.rotation_euler.z
    return parts


def place_avatar(base, result, fx, coll):
    """Copy the profile's rig, move it to where the verifier stood it, and set the reach pose."""
    obj = rig.duplicate(base, f"{base.name}@{fx['id']}")
    obj.hide_viewport = obj.hide_render = False
    _move(obj, coll)
    arm = result["arm"]
    toward_wall = {"forward": Vector((0, 1)), "side": Vector((1, 0)) if arm == "R" else Vector((-1, 0))}[result["approach"]]
    n = Vector(fx["wall_normal"]).normalized()
    ang = math.atan2(-n.y, -n.x) - math.atan2(toward_wall.y, toward_wall.x)
    rot = Matrix.Rotation(ang, 3, "Z")
    t = Vector(result["target_local"])
    fx_pos = Vector(fx["position"])
    base_xy = fx_pos - rot @ Vector((t.x, t.y, 0))
    obj.location = (base_xy.x, base_xy.y, base.location.z)
    obj.rotation_euler = (0, 0, ang)
    pose_arm(obj, arm, result["angles_deg"])
    return obj


def pose_arm(obj, arm, angles_deg):
    """Set the trunk and one arm to joint angles named as the reach chain names them."""
    a = {k: math.radians(v) for k, v in angles_deg.items()}
    obj.pose.bones["trunk"].rotation_euler.x = a.get("trunk_flex", 0)
    sh = obj.pose.bones[f"shoulder_{arm}"]
    sh.rotation_euler.x = a.get(f"shoulder_{arm}_flex", 0)
    sh.rotation_euler.z = a.get(f"shoulder_{arm}_abd", 0) * (-1 if arm == "R" else 1)
    obj.pose.bones[f"elbow_{arm}"].rotation_euler.x = a.get(f"elbow_{arm}_flex", 0)
    obj.pose.bones[f"wrist_{arm}"].rotation_euler.x = a.get(f"wrist_{arm}_flex", 0)


def stick_figure(obj, coll, mat):
    """Armatures don't render; give the posed rig simple limbs so a still image shows it."""
    bpy.context.view_layer.update()
    for pb in obj.pose.bones:
        if pb.name == "pelvis":
            continue
        a, b = obj.matrix_world @ pb.head, obj.matrix_world @ pb.tail
        d = b - a
        if d.length < 1e-4:
            continue
        bpy.ops.mesh.primitive_cylinder_add(radius=0.025, depth=d.length, location=(a + b) / 2)
        c = bpy.context.active_object
        c.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        c.data.materials.append(mat)
        _move(c, coll)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.11, location=obj.matrix_world @ (obj.pose.bones["trunk"].tail + Vector((0, 0, 0.13))))
    head = bpy.context.active_object
    head.data.materials.append(mat)
    _move(head, coll)


def _faces_away(x1, y1, x2, y2, room, cam):
    xs = [v for w in room["walls"] for v in (w[0], w[2])]
    ys = [v for w in room["walls"] for v in (w[1], w[3])]
    centre = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
    mid = Vector(((x1 + x2) / 2, (y1 + y2) / 2))
    return (mid - centre).dot(cam - centre) > 0


def render(path, room):
    scene = bpy.context.scene
    cx, cy = 1.2, 1.5
    bpy.ops.object.camera_add(location=(cx + 3.6, cy - 4.2, 3.9))
    cam = bpy.context.active_object
    cam.rotation_euler = (Vector((cx, cy, 0.7)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 26
    scene.camera = cam
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 5))
    bpy.context.active_object.data.energy = 3.5
    bpy.context.active_object.rotation_euler = (math.radians(35), math.radians(15), math.radians(-30))
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.9, 0.9, 0.92, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.render.resolution_x, scene.render.resolution_y = 1400, 1000
    scene.render.filepath = os.path.abspath(path)
    bpy.ops.render.render(write_still=True)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--render", help="also render a still image to this .png")
    ap.add_argument("--body", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                   "data", "body.json"))
    a = ap.parse_args(argv)

    room = json.load(open(a.room))
    results = [r for r in json.load(open(a.results)) if r["profile"] == a.profile]
    if not results:
        sys.exit(f"No results for '{a.profile}' in {a.results}.")
    base = bpy.data.objects.get(f"AccessPath_{a.profile}")
    if base is None:
        sys.exit(f"No 'AccessPath_{a.profile}' rig in this file. Run apply_profile.py for it first.")

    coll = bpy.data.collections.new(f"Results {a.profile}")
    bpy.context.scene.collection.children.link(coll)
    for o in bpy.data.objects:  # hide the rigs parked outside the room
        if o.type == "ARMATURE":
            o.hide_render = o.hide_viewport = True
    cam = Vector((1.2 + 3.6, 1.5 - 4.2))
    # For a still image, lower the walls whose inside faces away from the camera.
    cutaway = [i for i, (x1, y1, x2, y2) in enumerate(room["walls"])
               if a.render and _faces_away(x1, y1, x2, y2, room, cam)]
    build_room(room, results, coll, cutaway)
    fixtures = {f["id"]: f for f in room["fixtures"]}
    body_mat = material("avatar", (0.2, 0.35, 0.75, 1))
    for r in results:
        if r["task"].startswith("reach") and r["angles_deg"] and r["target_local"]:
            fx = fixtures[r["fixture"]]
            av = place_avatar(base, r, fx, coll)
            if a.render:
                stick_figure(av, coll, body_mat)
                if av.location.z < -0.01:
                    wheelchair(av, coll, rig.body_dims(a.body, "seated_wheelchair"))
    if a.render:
        for o in coll.objects:  # turn labels toward the camera so none read backwards
            if o.type == "FONT":
                d = Vector((cam.x, cam.y, 0)) - Vector((o.location.x, o.location.y, 0))
                o.rotation_euler.z = math.atan2(d.x, -d.y)
                o.data.size = 0.09
        render(a.render, room)
        print(f"Rendered {a.render}")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
