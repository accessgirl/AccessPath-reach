"""Give every missed reach attempt in a results file the closest pose the arm can get to, so a clip can show it.

  python3 video/fill_poses.py out/results.json

The verifier skips posing an arm when a target is plainly out of reach. This only adds a picture: status,
reason and error_m are left exactly as the verifier wrote them.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from accesspath.cards import load_library  # noqa: E402
from accesspath.kinematics import load_body, arm_chain, reach  # noqa: E402
from accesspath.profiles import compose  # noqa: E402
from accesspath.verify import _allowed, load_json  # noqa: E402


def main(path):
    results = json.loads(Path(path).read_text())
    lib = load_library(ROOT / "data" / "card_library.xlsx")
    room = {f["id"]: f for f in load_json(ROOT / "data" / "rooms" / "test_bathroom.json")["fixtures"]}
    for r in results:
        missing = [a for a in r.get("attempts", []) if not a["angles_deg"]]
        if not missing:
            continue
        profile = compose(lib, r["profile"])
        body = load_body(ROOT / "data" / "body.json", profile.posture, profile.height_m)
        fx = room[r["fixture"]]
        obst = fx.get("obstruction")
        depth = obst["depth_m"] if obst else 0.0
        for a in missing:
            t = np.array(a["target_local"])
            axis = 1 if a["approach"] == "forward" else 0
            got = reach(arm_chain(body, profile, a["arm"]), t, _allowed(axis, t[axis], depth, obst, body.limb_clearance), pose_on_miss=True)
            a["angles_deg"] = got.angles_deg
            a["pose_note"] = "closest pose, for pictures only"
            print(f"{r['fixture']} {a['arm']} {a['approach']}: posed, fingertip {got.error_m * 100:.0f} cm from target")
    Path(path).write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
