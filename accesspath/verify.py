"""Floor-plan test: every profile x task x fixture in a room gets PASS / FAIL / UNVERIFIED / CAUTION.

PASS        the avatar can do it, using only sourced or interpolated data
CAUTION     the avatar can do it, but a population statistic says many real people in this group can't
UNVERIFIED  the avatar can do it only because a placeholder card fell back to baseline (baseline is
            optimistic, so the real answer may be FAIL); or a needed number isn't sourced yet
FAIL        the avatar can't do it, even with baseline standing in for any placeholders
"""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

from .cards import Library
from .kinematics import load_body, arm_chain, reach
from .profiles import compose, ComposedProfile

RANK = {"FAIL": 3, "UNVERIFIED": 2, "CAUTION": 1, "PASS": 0}
TOUCH_TOL = 0.01  # the fingertip may touch the wall surface
STEP_BACK = [0.0, 0.15, 0.3, 0.45]  # the avatar may stand further back to lean in
SLIDE = [0.0, 0.15, 0.3]  # side approach: where the fixture sits along the avatar's body


@dataclass
class Result:
    room: str
    profile: str
    task: str
    fixture: str
    status: str
    reason: str
    arm: str | None = None
    approach: str | None = None
    error_m: float | None = None
    angles_deg: dict = field(default_factory=dict)
    target_local: list | None = None
    flags: list[str] = field(default_factory=list)
    attempts: list[dict] = field(default_factory=list)  # every arm/approach tried, in order
    body: str = ""  # which body size was tested (default, a body band, or a measured height)


def load_json(path):
    return json.loads(Path(path).read_text())


def run(library: Library, room: dict, tasks: list[dict], body_path, profile_ids=None, task_ids=None):
    results = []
    for pid in profile_ids or list(library.profiles):
        profile = compose(library, pid)
        body = load_body(body_path, profile.posture, profile.height_m)
        caps = [c for c in library.caps if c.applies_to_posture == profile.posture]
        for task in tasks:
            if task_ids and task["task_id"] not in task_ids:
                continue
            for fx in room["fixtures"]:
                if fx["type"] not in task["fixture_types"]:
                    continue
                if task["kind"] == "reach":
                    r = check_reach(profile, body, task, fx, caps)
                else:
                    r = check_doorway(profile, body, task, fx)
                r.room = room["room_id"]
                r.body = profile.height_note or "default body (body.json)"
                results.append(r)
    return results


def _side_joints(names, side):
    return [n if n == "trunk" else f"{n}_{side}" for n in names]


def check_reach(profile: ComposedProfile, body, task, fx, caps) -> Result:
    h = fx["position"][2]
    obst = fx.get("obstruction")
    chains = {arm: arm_chain(body, profile, arm) for arm in ("R", "L")}

    def blocked(arm):
        return profile.placeholder_flags(_side_joints(task["joints"], arm))

    # Arms backed by real data first, so we can stop at the first verified pass.
    order = sorted([(a, arm) for a in fx["approach"] for arm in ("R", "L")], key=lambda t: bool(blocked(t[1])))
    attempts = []
    for approach, arm in order:
        r = _try_arm(chains[arm], body, approach, arm, h, obst)
        attempts.append((approach, arm, r))
        if r.reached and not blocked(arm):
            break

    ok = [(a, arm, r) for a, arm, r in attempts if r.reached]
    verified = [(a, arm, r) for a, arm, r in ok if not blocked(arm)]
    base = Result("", profile.profile_id, task["task_id"], fx["id"], "", "")

    if verified:
        a, arm, r = verified[0]
        base.status, base.reason = "PASS", f"Reached with the {_arm(arm)} arm, {a} approach."
    elif ok:
        a, arm, r = ok[0]
        base.status = "UNVERIFIED"
        base.reason = (f"Reached with the {_arm(arm)} arm, {a} approach, but only by using able-bodied values "
                       "where this condition has no data yet. The real answer may be FAIL.")
        base.flags += [f.message for f in blocked(arm)]
    else:
        a, arm, r = min(attempts, key=lambda t: t[2].error_m)
        base.status = "FAIL"
        miss = "cannot reach without passing through the wall or counter" if r.error_m == float("inf") \
            else f"fingertip stops {r.error_m * 100:.0f} cm short"
        base.reason = f"Out of reach at {h:.2f} m: best try ({_arm(arm)} arm, {a} approach) {miss}."
    base.arm, base.approach = arm, a
    base.error_m = None if r.error_m == float("inf") else r.error_m
    base.angles_deg = r.angles_deg
    base.target_local = r.target
    base.attempts = [{"arm": arm_, "approach": a_, "reached": r_.reached,
                      "error_m": None if r_.error_m == float("inf") else round(float(r_.error_m), 3),
                      "angles_deg": r_.angles_deg, "target_local": r_.target, "path_deg": r_.path or []}
                     for a_, arm_, r_ in attempts]

    if base.status == "PASS":
        for cap in caps:
            if cap.rule == "target_above_shoulder_height" and h > body.shoulder_height:
                base.status = "CAUTION"
                base.reason += (f" The target ({h:.2f} m) is above seated shoulder height ({body.shoulder_height:.2f} m): "
                                f"{cap.notes}")
    return base


def _try_arm(chain, body, approach, arm, h, obst):
    sx = 1 if arm == "R" else -1
    depth = obst["depth_m"] if obst else 0.0
    best = None
    if approach == "forward":
        # Facing the wall, reaching shoulder lined up with the fixture.
        for back in STEP_BACK:
            wall = body.approach["forward"] + depth + back
            target = np.array([sx * body.half_shoulder, wall, h])
            r = reach(chain, target, _allowed(1, wall, depth, obst, body.limb_clearance))
            r.target = [round(float(v), 3) for v in target]
            best = _better(best, r)
            if r.reached:
                break
    else:
        # Wall on the reaching arm's side; the fixture can be anywhere along the body.
        wall = body.approach["side"] + depth
        for slide in SLIDE:
            target = np.array([sx * wall, slide, h])
            r = reach(chain, target, _allowed(0, sx * wall, depth, obst, body.limb_clearance))
            r.target = [round(float(v), 3) for v in target]
            best = _better(best, r)
            if r.reached:
                break
    return best


def _better(a, b):
    return b if a is None or b.error_m < a.error_m else a


def _allowed(axis, wall, depth, obst, clear=0.0):
    """No part of the arm or body may pass through the wall, or into the counter below its top.

    The arm has thickness: its centre line (shoulder to wrist) keeps `clear` metres from any surface.
    Only the hand may come right up to the wall to touch the target.
    """
    sign = 1 if wall >= 0 else -1
    lim = abs(wall)

    def dense(pts):
        return np.concatenate([pts[:-1] + (pts[1:] - pts[:-1]) * t for t in np.linspace(0, 1, 6)])

    def clear_of(points, margin):
        d = points[:, axis] * sign
        if np.any(d > lim + TOUCH_TOL - margin):
            return False
        if obst and np.any((d > lim - depth - margin) & (points[:, 2] < obst["height_m"] + margin)):
            return False
        return True

    def ok(pts):
        return clear_of(dense(pts[:-1]), clear) and clear_of(dense(pts[-2:]), 0.0)
    return ok


def check_doorway(profile: ComposedProfile, body, task, fx) -> Result:
    need = body.doorway.get(profile.mobility_aid)
    width = fx["clear_width_m"]
    r = Result("", profile.profile_id, task["task_id"], fx["id"], "", "")
    if need is None or need["value"] is None:
        r.status = "UNVERIFIED"
        r.reason = f"No sourced clear width for '{profile.mobility_aid}' yet."
        if need:
            r.flags.append(need["source"])
        return r
    if width < need["value"]:
        r.status = "FAIL"
        r.reason = f"Clear width {width:.3f} m is under the {need['value']:.3f} m needed ({need['source']})."
        return r
    r.status = "PASS"
    r.reason = f"Clear width {width:.3f} m meets the {need['value']:.3f} m needed ({need['source']})."
    legs = _side_joints(task["joints"], "R") + _side_joints(task["joints"], "L")
    flags = profile.placeholder_flags(legs)
    if flags:
        r.status = "UNVERIFIED"
        r.reason += " But the leg data this depends on isn't sourced yet."
        r.flags += [f.message for f in flags]
    return r


def _arm(side):
    return "right" if side == "R" else "left"


def summary_table(results):
    rows = [("profile", "task", "fixture", "result", "why")]
    for r in results:
        rows.append((r.profile, r.task, r.fixture, r.status, r.reason))
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    out = []
    for row in rows:
        out.append("  ".join(c.ljust(w) for c, w in zip(row[:4], widths)) + "  " + row[4])
    return "\n".join(out)


def to_json(results):
    return json.dumps([asdict(r) for r in results], indent=2)
