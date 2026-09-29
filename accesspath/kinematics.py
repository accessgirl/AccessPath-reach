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

    @property
    def arm_length(self):
        return self.upper_arm + self.forearm + self.hand

    @property
    def shoulder_height(self):
        return self.hip_height + self.trunk


def load_body(path, posture) -> Body:
    d = json.loads(Path(path).read_text())
    h, r = d["height_m"], d["segment_ratios"]
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

    `allowed(joint_points)` rejects poses that pass through a wall or counter.
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
        if best is None or err < best[0]:
            best = (err, a, pts[-1])
        if err <= tol:
            break
    if best is None:
        return Reach(False, float("inf"), {}, [])
    err, a, tip = best
    names = [lk.name for lk, m in zip(chain.links, chain.active_links_mask) if m]
    return Reach(err <= tol, round(err, 3),
                 {n: round(float(np.degrees(v)), 1) for n, v in zip(names, a[chain.active_links_mask])},
                 [round(float(v), 3) for v in tip])
