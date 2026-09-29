"""Step 1: build the baseline skeleton and put the baseline card limits on it.

  python -m accesspath compose baseline_standing -o out/baseline_standing.json
  blender --background --python blender/build_rig.py -- --profile out/baseline_standing.json --out out/avatar.blend
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
    ap.add_argument("--profile", required=True, help="baseline profile JSON from `python -m accesspath compose`")
    ap.add_argument("--body", default=os.path.join(ROOT, "data", "body.json"))
    ap.add_argument("--out", required=True, help=".blend file to save")
    a = ap.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    composed = json.load(open(a.profile))
    obj = rig.build_armature(rig.body_dims(a.body, "standing"))
    rig.apply_limits(obj, composed)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print(f"Saved {a.out}: armature '{obj.name}' with {len(obj.data.bones)} bones")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
