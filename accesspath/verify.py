"""Floor-plan test: every profile x task x fixture in a room gets one result (words in results.py).

Reach layer (the Reach Envelope, unchanged):
PASS             the avatar can do it, using only sourced or interpolated data; the designer may offer it
REACH CAUTION    the avatar can do it, but a population statistic says many real people in this group can't
NOT CHECKED YET  the avatar can do it only because a placeholder card fell back to baseline (baseline is
                 optimistic, so the real answer may be DO NOT USE); or a needed number isn't sourced yet
DO NOT USE       the avatar can't do it, even with baseline standing in for any placeholders

Safety layers run where they're built (so far: Balance, for a person standing on crutches). Each result keeps
every layer's own answer; the overall result is the worst layer, and says which kind of test it came from.
"""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

from .cards import Library
from .kinematics import load_body, arm_chain, reach
from .profiles import compose, ComposedProfile
from .privacy import check_tree
from . import population, seated_size
from .results import (PASS, REACH_CAUTION, SAFETY_CAUTION, DO_NOT_USE, NOT_CHECKED_YET, LABEL, STATUSES,
                      SAFETY_LAYERS, REACH, LayerResult, combine, check_steps)

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
    population_pct: int | None = None  # share of measured wheelchair users who could reach it (IDeA Center)
    inputs: list[dict] = field(default_factory=list)  # every value the result rests on, with its card and status
    layers: list[dict] = field(default_factory=list)  # each layer's own result, reason and basis
    came_from: str = ""  # reach, safety, or both
    held_because: str | None = None  # "fails the test" or "not checked yet"; never merged
    steps: list[dict] = field(default_factory=list)  # the task's steps, if it has them (structure only so far)
    safety_not_run: list[str] = field(default_factory=list)  # safety layers not built yet, so not in the result
    _extra_layers: list = field(default_factory=list, repr=False)  # safety layers found while checking

    @property
    def label(self):
        return LABEL[self.status]


def load_json(path):
    return json.loads(Path(path).read_text())


def run(library: Library, room: dict, tasks: list[dict], body_path, profile_ids=None, task_ids=None,
        population_path=None):
    check_tree(room, f"room {room.get('room_id', '?')}")
    pop = population.load(population_path or Path(body_path).with_name("idea_reach.json"))
    size = seated_size.load(Path(body_path).with_name("wheelchair_size.json"))
    results = []
    for pid in profile_ids or list(library.profiles):
        profile = compose(library, pid)
        body = load_body(body_path, profile.posture, profile.height_m, profile.measured)
        caps = [c for c in library.caps if c.applies_to_posture == profile.posture]
        for task in tasks:
            if task_ids and task["task_id"] not in task_ids:
                continue
            for fx in room["fixtures"]:
                if fx["type"] not in task["fixture_types"]:
                    continue
                if task["kind"] == "reach":
                    r = check_reach(profile, body, task, fx, caps,
                                    pop if profile.mobility_aid == "wheelchair" else None)
                elif task["kind"] == "knee_clearance":
                    if profile.mobility_aid != "wheelchair":
                        continue  # knee space is about pulling in seated
                    r = check_knee_space(profile, task, fx, size, body)
                else:
                    r = check_doorway(profile, body, task, fx)
                r.room = room["room_id"]
                r.body = profile.height_note or "default body (body.json)"
                _finish(r, task)
                results.append(r)
    return results


def _finish(r: Result, task):
    """Put the Reach answer in as layer 1, add any safety layers, and work out the overall result."""
    layers = [LayerResult(REACH, r.status, r.reason)] + r._extra_layers
    r.layers = [l.to_dict() for l in layers]
    r.status, r.came_from, r.held_because = combine(layers)
    if r._extra_layers:
        r.reason = " ".join(f"{l.layer.capitalize()}: {l.reason}" for l in layers)
    ran = {l.layer for l in layers}
    r.safety_not_run = [l for l in SAFETY_LAYERS if l not in ran]
    r.steps = check_steps(task)
    del r._extra_layers[:]


def _side_joints(names, side):
    return [n if n == "trunk" else f"{n}_{side}" for n in names]


CRUTCH_NO_REACH = ("No reach is given. No study has measured reach while a person stands on crutches, on any "
                   "floor (searched Nov 14, 2026), so an able-bodied reach can't stand in for it.")
CRUTCH_BALANCE = ("Both hands are on the crutches for support, so reaching while standing isn't shown to be safe. "
                  "Bring the item to the person, or test the task seated.")
CRUTCH_WET = " Do not walk on a wet floor with crutches."
CRUTCH_BASIS = ("Stall → Pivot rule and worst-case rule (Heather, Nov 14, 2026); Safety Envelope Definition "
                "(Nov 14, 2026); no reach-on-crutches study found (Crutches: Standing Reach and Gait, Nov 14, 2026).")


def _crutch_user_standing(profile: ComposedProfile):
    return profile.mobility_aid == "crutches" and profile.posture == "standing"


def check_reach(profile: ComposedProfile, body, task, fx, caps, pop=None) -> Result:
    if _crutch_user_standing(profile):
        # Reach stalls (no study), so the Balance layer takes over: a caution with its reason, never a distance.
        r = Result("", profile.profile_id, task["task_id"], fx["id"], NOT_CHECKED_YET, CRUTCH_NO_REACH)
        wet = "wet" in profile.description.lower()
        r._extra_layers.append(LayerResult("balance", SAFETY_CAUTION, CRUTCH_BALANCE + (CRUTCH_WET if wet else ""),
                                           CRUTCH_BASIS))
        r.flags += [f.message for f in profile.placeholder_flags(_side_joints(task["joints"], "R") +
                                                                 _side_joints(task["joints"], "L"))]
        return r
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
        base.status, base.reason = PASS, f"Reached with the {_arm(arm)} arm, {a} approach."
    elif ok:
        a, arm, r = ok[0]
        base.status = NOT_CHECKED_YET
        base.reason = (f"Reached with the {_arm(arm)} arm, {a} approach, but only by using able-bodied values "
                       "where this condition has no data yet. The real answer may be DO NOT USE.")
        base.flags += [f.message for f in blocked(arm)]
    else:
        a, arm, r = min(attempts, key=lambda t: t[2].error_m)
        base.status = DO_NOT_USE
        miss = "cannot reach without passing through the wall or counter" if r.error_m == float("inf") \
            else f"fingertip stops {r.error_m * 100:.0f} cm short"
        base.reason = f"Out of reach at {h:.2f} m: best try ({_arm(arm)} arm, {a} approach) {miss}."
    base.arm, base.approach = arm, a
    base.inputs = _inputs(profile, body, arm)
    base.error_m = None if r.error_m == float("inf") else r.error_m
    base.angles_deg = r.angles_deg
    base.target_local = r.target
    base.attempts = [{"arm": arm_, "approach": a_, "reached": r_.reached,
                      "error_m": None if r_.error_m == float("inf") else round(float(r_.error_m), 3),
                      "angles_deg": r_.angles_deg, "target_local": r_.target, "path_deg": r_.path or []}
                     for a_, arm_, r_ in attempts]

    if pop is not None:
        _population_check(base, pop, fx, h, obst)
        return base
    if base.status == PASS:
        for cap in caps:
            if cap.rule == "target_above_shoulder_height" and h > body.shoulder_height:
                base.status = REACH_CAUTION
                base.reason += (f" The target ({h:.2f} m) is above seated shoulder height ({body.shoulder_height:.2f} m): "
                                f"{cap.notes}")
    return base


def _inputs(profile: ComposedProfile, body, arm):
    """The values a reach result rests on: each joint limit on the arm used, and the body estimates."""
    rows = [{"input": k, **v} for k, v in profile.provenance.items()
            if k.split()[0] in _side_joints(["trunk", "shoulder", "elbow", "wrist"], arm)]
    m = profile.measured
    rows.append({"input": "body height", "value_m": round(body.height, 3), "status": "sourced" if profile.height_m
                 else "interpolated", "source": profile.height_note or "default body (data/body.json)"})
    rows.append({"input": "seat (hip) height", "value_m": round(body.hip_height, 3),
                 "status": "measured" if "seat_height_in" in m
                 else "interpolated" if profile.posture == "seated_wheelchair" else "sourced",
                 "source": "profile measurement" if "seat_height_in" in m else "data/body.json"})
    rows.append({"input": "trunk (seat to shoulder)", "value_m": round(body.trunk, 3),
                 "status": "measured" if "seated_shoulder_in" in m else "sourced",
                 "source": "profile measurement" if "seated_shoulder_in" in m
                 else "height x Drillis & Contini ratio (data/body.json)"})
    rows.append({"input": "arm length", "value_m": round(body.arm_length, 3),
                 "status": "measured" if "arm_length_in" in m else "sourced",
                 "source": "profile measurement" if "arm_length_in" in m
                 else "height x Drillis & Contini ratios (data/body.json)"})
    if body.trunk_lean_max is not None:
        rows.append({"input": "trunk lean allowed", "value_deg": body.trunk_lean_max, "status": "interpolated",
                     "source": "data/body.json (estimate)"})
    return rows


def _population_check(base, pop, fx, h, obst):
    """Compare the avatar's answer with measured wheelchair users (IDeA Center). A PASS that fewer than
    75% of them could manage becomes CAUTION; the share is recorded on every result."""
    s = population.best_share(pop, fx["approach"], h, obst["depth_m"] if obst else 0.0)
    base.population_pct = s.pct
    if base.status != PASS:
        return
    who = (f"{s.pct_measured}% of the {pop['measured']} measured manual wheelchair users who could reach above "
           f"shoulder height, counting the {pop['recruited'] - pop['measured']} who couldn't as unable "
           "(IDeA Center, Design Resource #20)")
    if s.note == "below":
        base.status = REACH_CAUTION
        base.reason += (f" But {h * 39.37:.0f} in is below 16 in, the lowest height the IDeA Center study measured. "
                        "It found many wheelchair users couldn't safely reach the ADA's 15 in low limit and "
                        "recommends 28 in instead.")
    elif s.pct is None:
        base.status = REACH_CAUTION
        base.reason += " But that's farther from the chair than the IDeA Center study measured anyone reaching."
    elif s.pct < pop["good_design_pct"]:
        base.status = REACH_CAUTION
        base.reason += (f" But only about {s.pct}% of measured wheelchair users could reach this spot "
                        f"(best case, reaching {_way(s.approach)}): {who}. The study's own line for good design is "
                        f"{pop['good_design_pct']}%.")
    else:
        base.reason += (f" About {s.pct}% of measured wheelchair users could reach it too (reaching {_way(s.approach)}): "
                        f"{who}.")


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
        r.status = NOT_CHECKED_YET
        r.reason = f"No sourced clear width for '{profile.mobility_aid}' yet."
        if need:
            r.flags.append(need["source"])
        return r
    if width < need["value"]:
        r.status = DO_NOT_USE
        r.reason = f"Clear width {width:.3f} m is under the {need['value']:.3f} m needed ({need['source']})."
        return r
    r.status = PASS
    r.reason = f"Clear width {width:.3f} m meets the {need['value']:.3f} m needed ({need['source']})."
    if need.get("caution_below") and width < need["caution_below"]:
        r.status = REACH_CAUTION
        why = need.get("caution_why") or f"the width of a person using {profile.mobility_aid} in another source"
        r.reason += f" But it is under {need['caution_below']:.3f} m, {why} ({need['caution_source']})."
    legs = _side_joints(task["joints"], "R") + _side_joints(task["joints"], "L")
    flags = profile.placeholder_flags(legs)
    if flags:
        r.status = NOT_CHECKED_YET
        r.reason += " But the leg data this depends on isn't sourced yet."
        r.flags += [f.message for f in flags]
    return r


def check_knee_space(profile: ComposedProfile, task, fx, size, body=None) -> Result:
    r = Result("", profile.profile_id, task["task_id"], fx["id"], "", "")
    if body is not None and body.knee_height is not None and fx.get("knee_clearance_m") is not None:
        under, knee, allow = fx["knee_clearance_m"], body.knee_height, body.knee_allowance
        if under < knee:
            r.status = DO_NOT_USE
            r.reason = (f"Knee space {under * 100:.1f} cm high is lower than this person's measured knee height "
                        f"({knee * 100:.1f} cm).")
        elif under < knee + allow:
            r.status = REACH_CAUTION
            r.reason = (f"Knee space {under * 100:.1f} cm high clears this person's measured knee height "
                        f"({knee * 100:.1f} cm) by less than {allow * 100:.0f} cm, the allowance for clothing and "
                        "moving in (an estimate).")
        else:
            r.status = PASS
            r.reason = (f"Knee space {under * 100:.1f} cm high clears this person's measured knee height "
                        f"({knee * 100:.1f} cm) with room to spare.")
        r.inputs = [{"input": "knee height", "value_m": round(knee, 3), "status": "measured",
                     "source": "profile measurement (knee_height_in)"},
                    {"input": "knee allowance", "value_m": allow, "status": "interpolated",
                     "source": "data/body.json (estimate)"}]
        return r
    if size is None:
        r.status, r.reason = NOT_CHECKED_YET, "No measured wheelchair-user sizes loaded (data/wheelchair_size.json)."
    elif fx.get("knee_clearance_m") is None:
        r.status = NOT_CHECKED_YET
        r.reason = "The room file doesn't give the height of the knee space under this fixture."
    else:
        old, r.reason = seated_size.knee_check(size, fx["knee_clearance_m"])
        r.status = {"PASS": PASS, "CAUTION": REACH_CAUTION, "FAIL": DO_NOT_USE}[old]
    return r


def _way(approach):
    return "from the side" if approach == "side" else "straight ahead"


def _arm(side):
    return "right" if side == "R" else "left"


def summary_table(results):
    rows = [("profile", "task", "fixture", "result", "from", "why")]
    for r in results:
        rows.append((r.profile, r.task, r.fixture, r.label, r.came_from, r.reason))
    widths = [max(len(row[i]) for row in rows) for i in range(5)]
    out = []
    for row in rows:
        out.append("  ".join(c.ljust(w) for c, w in zip(row[:5], widths)) + "  " + row[5])
    return "\n".join(out)


def to_json(results):
    out = []
    for r in results:
        d = asdict(r)
        d.pop("_extra_layers", None)
        d["label"] = r.label
        out.append(d)
    return json.dumps(out, indent=2)
