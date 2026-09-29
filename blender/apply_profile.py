"""Step 3: duplicate the baseline skeleton and constrain it for one profile. No manual constraint editing.

  python -m accesspath compose stroke_R_moderate -o out/stroke_R_moderate.json
  blender out/avatar.blend --background --python blender/apply_profile.py -- --profile out/stroke_R_moderate.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import rig  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, help="profile JSON from `python -m accesspath compose`")
    ap.add_argument("--body", default=os.path.join(ROOT, "data", "body.json"))
    ap.add_argument("--x", type=float, default=None, help="where to place the copy along X (default: beside the others)")
    a = ap.parse_args(argv)

    composed = json.load(open(a.profile))
    base = bpy.data.objects.get(rig.ARMATURE)
    if base is None:
        sys.exit(f"No '{rig.ARMATURE}' armature in this file. Run build_rig.py first.")
    name = f"AccessPath_{composed['profile_id']}"
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old)
    obj = rig.duplicate(base, name)
    rig.apply_limits(obj, composed)
    if composed["posture"] == "seated_wheelchair":
        rig.pose_seated(obj, rig.body_dims(a.body, "seated_wheelchair"))
    others = [o for o in bpy.data.objects if o.type == "ARMATURE" and o is not obj]
    obj.location.x = a.x if a.x is not None else 0.8 * len(others)
    bpy.ops.wm.save_mainfile()
    print(f"Added '{name}' ({len(composed['flags'])} data flags; see the object's custom properties)")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
