"""Translate between the verifier's frame and the ISB standard (Wu et al. 2005), so results can move to other software.

Verifier frame: +x right, +y forward, +z up (same as Blender).
ISB frame:      +X forward, +Y up, +Z right (same as OpenSim's ground frame).
Both are right-handed, so it is a relabelling of axes, not a mirror.
"""
import numpy as np


def to_isb(p):
    """Point or direction(s) in the verifier frame -> ISB frame. Works on (3,) or (N, 3)."""
    p = np.asarray(p, dtype=float)
    return p[..., [1, 2, 0]]


def from_isb(p):
    """Point or direction(s) in the ISB frame -> verifier frame."""
    p = np.asarray(p, dtype=float)
    return p[..., [2, 0, 1]]


def shoulder_elevation(arm_dir, side):
    """ISB thoracohumeral (plane of elevation, elevation) in degrees for an upper-arm direction in the verifier frame.

    arm_dir points from the shoulder to the elbow. Plane of elevation: 0 = out to the side, 90 = forward
    (the same for both arms, as ISB mirrors the left). Elevation: 0 = hanging, 90 = horizontal, reported as
    the clinical positive angle (ISB's rotation itself is negative). Assumes an upright thorax.
    """
    d = np.asarray(arm_dir, dtype=float)
    d = d / np.linalg.norm(d)
    elevation = np.degrees(np.arccos(np.clip(-d[2], -1, 1)))
    lateral = d[0] if side == "R" else -d[0]
    plane = np.degrees(np.arctan2(d[1], lateral)) if elevation > 1e-6 else 0.0
    return float(plane), float(elevation)
