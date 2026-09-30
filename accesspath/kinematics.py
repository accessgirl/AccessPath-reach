"""Arm reach chain (trunk lean + shoulder + elbow + wrist) built with IKPy from a composed profile.

Avatar frame, metres: origin on the floor under the hip centre, +x to the avatar's right, +y forward, +z up.
The arm hangs straight down at zero angles; the fingertip is the end of the chain.
"""
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from ikpy.chain import Chain
from ikpy.link import OriginLink, URDFLink

from .profiles import ComposedProfile

ARM_JOINTS = ["trunk", "shoulder", "elbow", "wrist"]


@dataclass
class Body:
    height: float
    hip_height: float
    trunk: float  # hip pivot to shoulder height
    half_shoulder: float
    upper_arm: float
    forearm: float
    hand: float
    trunk_lean_max: float | None
    approach: dict
    doorway: dict
    limb_clearance: float = 0.0  # the arm's centre line must stay this far from surfaces

    @property
    def arm_length(self):
        return self.upper_arm + self.forearm + self.hand

    @property
    def shoulder_height(self):
        return self.hip_height + self.trunk


def load_body(path, posture, height_m=None) -> Body:
    """`height_m` overrides the default height (a body band or a measured client); segments scale with it."""
    d = json.loads(Path(path).read_text())
    h, r = (height_m or d["height_m"]), d["segment_ratios"]
    p = d["postures"][posture]
    return Body(
        height=h,
        hip_height=p["hip_height_m"] if p["hip_height_m"] is not None else r["hip_height"] * h,
        trunk=(r["shoulder_height"] - r["hip_height"]) * h,
        half_shoulder=r["shoulder_width"] * h / 2,
        upper_arm=r["upper_arm"] * h, forearm=r["forearm"] * h, hand=r["hand"] * h,
        trunk_lean_max=p["trunk_lean_max_deg"],
        approach=d["approach"][posture],
        doorway=d["doorway_clear_width_m"],
        limb_clearance=d.get("limb_clearance_m", {}).get("value", 0.0),
    )


def _rad(lim):
    lo, hi = lim
    if hi - lo < 1e-3:  # a locked joint; the optimiser needs a range that isn't empty
        hi = lo + 1e-3
    return tuple(np.radians([lo, hi]))


def arm_chain(body: Body, profile: ComposedProfile, side: str) -> Chain:
    """Chain for one arm. Joint limits come from the composed profile's cards."""
    L = profile.limits
    lean = list(L["trunk"]["flex"])
    if body.trunk_lean_max is not None:
        lean[1] = min(lean[1], body.trunk_lean_max)
    sx = 1 if side == "R" else -1
    sh, el, wr = L[f"shoulder_{side}"], L[f"elbow_{side}"], L[f"wrist_{side}"]
    links = [
        OriginLink(),
        URDFLink("hip_pivot", origin_translation=[0, 0, body.hip_height], origin_orientation=[0, 0, 0],
                 joint_type="fixed"),
        # Positive trunk flexion leans the shoulders forward (+y).
        URDFLink("trunk_flex", origin_translation=[0, 0, 0], origin_orientation=[0, 0, 0],
                 rotation=[-1, 0, 0], bounds=_rad(lean)),
        # Positive shoulder flexion swings the hanging arm forward (+y).
        URDFLink(f"shoulder_{side}_flex", origin_translation=[sx * body.half_shoulder, 0, body.trunk],
                 origin_orientation=[0, 0, 0], rotation=[1, 0, 0], bounds=_rad(sh["flex"])),
        # Positive abduction swings the arm out to its own side.
        URDFLink(f"shoulder_{side}_abd", origin_translation=[0, 0, 0], origin_orientation=[0, 0, 0],
                 rotation=[0, -sx, 0], bounds=_rad(sh.get("abd", [0, 0]))),
        URDFLink(f"elbow_{side}_flex", origin_translation=[0, 0, -body.upper_arm], origin_orientation=[0, 0, 0],
                 rotation=[1, 0, 0], bounds=_rad(el["flex"])),
        URDFLink(f"wrist_{side}_flex", origin_translation=[0, 0, -body.forearm], origin_orientation=[0, 0, 0],
                 rotation=[1, 0, 0], bounds=_rad(wr["flex"])),
        URDFLink("fingertip", origin_translation=[0, 0, -body.hand], origin_orientation=[0, 0, 0],
                 joint_type="fixed"),
    ]
    mask = [lk.joint_type != "fixed" and not isinstance(lk, OriginLink) for lk in links]
    return Chain(links, active_links_mask=mask, name=f"arm_{side}")


def _bounds(chain):
    return np.array([lk.bounds if m else (0.0, 0.0) for lk, m in zip(chain.links, chain.active_links_mask)])


def sample_angles(chain, n, rng):
    b = _bounds(chain)
    return rng.uniform(b[:, 0], b[:, 1], size=(n, len(b)))


def joint_positions(chain, angles):
    return np.array([f[:3, 3] for f in chain.forward_kinematics(angles, full_kinematics=True)])


def envelope(chain, n=4000, seed=0):
    """Fingertip positions sampled across the whole allowed range: the reach envelope as a point cloud."""
    rng = np.random.default_rng(seed)
    return np.array([chain.forward_kinematics(a)[:3, 3] for a in sample_angles(chain, n, rng)])


@dataclass
class Reach:
    reached: bool
    error_m: float
    angles_deg: dict
    fingertip: list
    target: list | None = None  # avatar frame; lets Blender place the avatar in the room
    path: list | None = None  # joint-angle waypoints from rest to the pose, none passing through a surface


def _max_lean_reach_gap(chain, target):
    """Lower bound on how far the target is beyond the arm's straight-line length, over every trunk lean."""
    hip = chain.links[1].origin_translation
    trunk_link, shoulder = chain.links[2], chain.links[3].origin_translation
    arm = sum(abs(lk.origin_translation[2]) for lk in chain.links[5:])
    gaps = []
    for lean in np.linspace(*trunk_link.bounds, 19):
        sh = hip + np.array([shoulder[0], np.sin(lean) * shoulder[2], np.cos(lean) * shoulder[2]])
        gaps.append(np.linalg.norm(target - sh) - arm)
    # Sampled leans can miss the closest one; 2 cm covers the gap between samples.
    return min(gaps) - 0.02


def reach(chain, target, allowed=lambda pts: True, tol=0.02, seeds=8, seed=0, pose_on_miss=False) -> Reach:
    """Can the fingertip touch `target`? Tries several starting poses because IK only finds a nearby answer.

    `allowed(joint_points)` rejects poses that pass through a wall or counter. A pose that touches the target
    only counts if the arm can also get there from rest without passing through anything (`find_path`).
    `pose_on_miss` still solves for the closest pose when the target is plainly out of reach (for pictures).
    """
    gap = _max_lean_reach_gap(chain, target)
    if gap > tol and not pose_on_miss:  # farther than a straight arm at any lean: skip the optimiser
        return Reach(False, round(float(gap), 3), {}, [])
    rng = np.random.default_rng(seed)
    b = _bounds(chain)
    starts = [np.clip(np.zeros(len(b)), b[:, 0], b[:, 1]), b.mean(axis=1)] + list(sample_angles(chain, seeds, rng))
    best = None
    for start in starts:
        a = chain.inverse_kinematics(target, initial_position=start)
        pts = joint_positions(chain, a)
        if not allowed(pts):
            continue
        err = float(np.linalg.norm(pts[-1] - target))
        path = find_path(chain, a, allowed) if err <= tol else None
        if err <= tol and path is None:
            continue  # the pose touches the target, but no arm could get there without going through a surface
        if best is None or err < best[0]:
            best = (err, a, pts[-1], path)
        if err <= tol:
            break
    if best is None:
        return Reach(False, float("inf"), {}, [])
    err, a, tip, path = best
    r = Reach(err <= tol, round(err, 3), _named(chain, a), [round(float(v), 3) for v in tip])
    r.path = [_named(chain, w) for w in path] if path else []
    return r


def _named(chain, a):
    names = [lk.name for lk, m in zip(chain.links, chain.active_links_mask) if m]
    return {n: round(float(np.degrees(v)), 1) for n, v in zip(names, a[chain.active_links_mask])}


def rest_pose(chain):
    """Arm hanging at the side, trunk upright (clipped into each joint's allowed range)."""
    b = _bounds(chain)
    return np.clip(np.zeros(len(b)), b[:, 0], b[:, 1])


def find_path(chain, final, allowed, steps=24):
    """Waypoints from rest to `final` that never pass through a surface, or None.

    Tries the straight move first, then the way a person clears a wall beside them: lean, raise the arm
    forward with the elbow bent, then move it into place ("forward, up, then over").
    """
    rest = rest_pose(chain)
    b = _bounds(chain)
    names = [lk.name for lk in chain.links]
    i_trunk = names.index("trunk_flex")
    i_flex = next(i for i, n in enumerate(names) if n.startswith("shoulder_") and n.endswith("_flex"))
    i_abd = next(i for i, n in enumerate(names) if n.endswith("_abd"))
    i_elbow = next(i for i, n in enumerate(names) if n.startswith("elbow_"))

    candidates = [[rest, final]]
    for raise_deg in (60, 90, 120, 150, 180):
        via = rest.copy()
        via[i_trunk] = final[i_trunk]
        via[i_flex] = np.radians(raise_deg)
        via[i_elbow] = np.radians(90)
        via = np.clip(via, b[:, 0], b[:, 1])
        up = via.copy()
        up[i_abd] = final[i_abd]
        candidates.append([rest, via, final])
        candidates.append([rest, via, up, final])
    for wps in candidates:
        if all(_segment_clear(chain, p, q, allowed, steps) for p, q in zip(wps, wps[1:])):
            return wps
    return None


def _segment_clear(chain, p, q, allowed, steps):
    return all(allowed(joint_positions(chain, p + (q - p) * t)) for t in np.linspace(0, 1, steps))
