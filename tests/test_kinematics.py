import numpy as np

from accesspath.kinematics import load_body, arm_chain, reach, envelope
from accesspath.profiles import compose
from conftest import DATA


def test_straight_arm_hangs_to_fingertip(library):
    body = load_body(DATA / "body.json", "standing")
    chain = arm_chain(body, compose(library, "baseline_standing"), "R")
    tip = chain.forward_kinematics([0] * len(chain.links))[:3, 3]
    assert np.allclose(tip, [body.half_shoulder, 0, body.shoulder_height - body.arm_length])


def test_reach_in_and_out_of_range(library):
    body = load_body(DATA / "body.json", "standing")
    chain = arm_chain(body, compose(library, "baseline_standing"), "R")
    assert reach(chain, np.array([body.half_shoulder, 0.3, 1.8])).reached
    far = reach(chain, np.array([body.half_shoulder, 0.3, 3.0]))
    assert not far.reached and far.error_m > 0.5


def test_no_abduction_means_no_sideways_reach(library):
    body = load_body(DATA / "body.json", "standing")
    side = np.array([body.half_shoulder + 0.6, 0.0, body.shoulder_height])
    assert reach(arm_chain(body, compose(library, "baseline_standing"), "R"), side).reached
    assert not reach(arm_chain(body, compose(library, "stroke_R_severe"), "R"), side).reached


def test_envelope_respects_limits(library):
    body = load_body(DATA / "body.json", "standing")
    pts = envelope(arm_chain(body, compose(library, "stroke_R_severe"), "R"), n=500)
    # With abduction locked the fingertip never moves outward past the shoulder line.
    assert pts[:, 0].max() <= body.half_shoulder + 1e-4  # locked joints keep a 0.001 degree sliver
