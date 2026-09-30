"""Command line: python -m accesspath <command>. Run with -h for help."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .cards import load_library, LibraryError
from .kinematics import load_body, arm_chain, envelope
from .profiles import compose
from .verify import run, load_json, summary_table, to_json

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="accesspath", description="AccessPath Verifier")
    ap.add_argument("--library", default=DATA / "card_library.xlsx", help="card library spreadsheet")
    ap.add_argument("--body", default=DATA / "body.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check-cards", help="check the card spreadsheet and list what is still unsourced")

    c = sub.add_parser("compose", help="joint limits for a profile, as JSON (Blender's apply_profile.py reads this)")
    c.add_argument("profile")
    c.add_argument("-o", "--out")

    e = sub.add_parser("envelope", help="reach envelope point cloud for one arm, as a .ply file Blender can import")
    e.add_argument("profile")
    e.add_argument("--arm", choices=["R", "L"], default="R")
    e.add_argument("-n", type=int, default=4000, help="number of sampled poses")
    e.add_argument("-o", "--out", required=True)

    v = sub.add_parser("verify", help="pass/fail for every profile x task in a room")
    v.add_argument("--room", default=DATA / "rooms" / "test_bathroom.json")
    v.add_argument("--tasks", default=DATA / "tasks.json")
    v.add_argument("--profile", action="append", help="only this profile (repeatable)")
    v.add_argument("--task", action="append", help="only this task (repeatable)")
    v.add_argument("-o", "--out", help="also write the full results as JSON")

    a = ap.parse_args(argv)
    try:
        lib = load_library(a.library)
    except LibraryError as err:
        print(f"Card library problem: {err}", file=sys.stderr)
        return 2

    if a.cmd == "check-cards":
        counts = Counter(c.status for c in lib.cards.values())
        print(f"{len(lib.cards)} cards: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())))
        print(f"{len(lib.profiles)} profiles, {len(lib.caps)} population cap(s), {len(lib.bands)} body band(s). "
              "No problems found.")
        todo = [c for c in lib.cards.values() if c.status == "placeholder"]
        if todo:
            print("\nStill needs a source:")
            for c in todo:
                print(f"  {c.card_id}: {c.condition}, {c.joint_id} {c.DOF_axis}")
        return 0

    if a.cmd == "compose":
        text = json.dumps(compose(lib, a.profile).to_dict(), indent=2)
        _write_or_print(text, a.out)
        return 0

    if a.cmd == "envelope":
        p = compose(lib, a.profile)
        pts = envelope(arm_chain(load_body(a.body, p.posture, p.height_m), p, a.arm), n=a.n)
        Path(a.out).write_text(_ply(pts))
        print(f"Wrote {len(pts)} points to {a.out} (avatar frame: metres, x right, y forward, z up, "
              "origin on the floor under the hip).")
        return 0

    if a.cmd == "verify":
        room = load_json(a.room)
        results = run(lib, room, load_json(a.tasks)["tasks"], a.body, a.profile, a.task)
        print(summary_table(results))
        counts = Counter(r.status for r in results)
        print("\n" + ", ".join(f"{counts[s]} {s}" for s in ["PASS", "CAUTION", "UNVERIFIED", "FAIL"]))
        if a.out:
            Path(a.out).write_text(to_json(results))
            print(f"Full results: {a.out}")
        return 1 if counts["FAIL"] else 0


def _write_or_print(text, out):
    if out:
        Path(out).write_text(text)
        print(f"Wrote {out}")
    else:
        print(text)


def _ply(pts):
    head = f"ply\nformat ascii 1.0\nelement vertex {len(pts)}\nproperty float x\nproperty float y\nproperty float z\nend_header\n"
    return head + "\n".join(f"{x:.4f} {y:.4f} {z:.4f}" for x, y, z in pts) + "\n"


if __name__ == "__main__":
    sys.exit(main())
