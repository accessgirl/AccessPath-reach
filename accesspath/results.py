"""Result words, layers and how a task's overall result is worked out. One place for all of it.

The words (Heather's decisions, Nov 15, 2026):
  PASS             passed the test, so the designer may offer it. It never means "safe".
  REACH CAUTION    the Reach Envelope's own caution: the person can do it, but measured data says many
                   people in their group can't (or a sourced limit is close).
  SAFETY CAUTION   a safety check found no safe value, or a known hazard applies. No number is given.
  DO NOT USE       a measured value fails the test.
  NOT CHECKED YET  the number this rests on isn't sourced or checked yet. Never merged with DO NOT USE.

Layers: Reach is layer 1 and runs first. The safety layers (Balance, Slip, Transfer, Clearance, Layout)
run where they're built. A pass in one layer never cancels a caution in another, so a task's overall
result is its worst layer. Results from different layers are never added together.

To change a word later (for example after Legal and IP's review), change LABEL below; nothing else.
"""
from dataclasses import dataclass, asdict

PASS = "PASS"
REACH_CAUTION = "REACH CAUTION"
SAFETY_CAUTION = "SAFETY CAUTION"
DO_NOT_USE = "DO NOT USE"
NOT_CHECKED_YET = "NOT CHECKED YET"

STATUSES = (PASS, REACH_CAUTION, SAFETY_CAUTION, NOT_CHECKED_YET, DO_NOT_USE)  # display order

LABEL = {
    PASS: "PASS: may offer",
    REACH_CAUTION: "REACH CAUTION",
    SAFETY_CAUTION: "SAFETY CAUTION",
    DO_NOT_USE: "DO NOT USE",
    NOT_CHECKED_YET: "NOT CHECKED YET",
}

MEANING = {
    PASS: "Passed the test, so the designer may offer it. This does not say it is safe.",
    REACH_CAUTION: "The person can do it, but measured data says many people in their group can't.",
    SAFETY_CAUTION: "A safety check found no safe value, or a known hazard. No number is given.",
    DO_NOT_USE: "A measured value fails the test.",
    NOT_CHECKED_YET: "The number this rests on isn't sourced or checked yet. Not a pass, and not a fail.",
}

# Worst first wins. NOT CHECKED YET ranks above PASS: a gap is never a pass.
RANK = {PASS: 0, NOT_CHECKED_YET: 1, REACH_CAUTION: 2, SAFETY_CAUTION: 3, DO_NOT_USE: 4}

REACH = "reach"
SAFETY_LAYERS = ("balance", "slip", "transfer", "clearance", "layout")
LAYERS = (REACH,) + SAFETY_LAYERS

# Why a result is held out of a design package. The two reasons must never be merged.
HELD_FAILS = "fails the test"
HELD_NOT_CHECKED = "not checked yet"


@dataclass
class LayerResult:
    layer: str
    status: str
    reason: str
    basis: str = ""  # what it rests on: a source, a rule with its date, or the gap, stated plainly

    def __post_init__(self):
        if self.layer not in LAYERS:
            raise ValueError(f"Unknown layer '{self.layer}'. Layers: {', '.join(LAYERS)}")
        if self.status not in STATUSES:
            raise ValueError(f"Unknown result '{self.status}'. Results: {', '.join(STATUSES)}")
        if self.status == REACH_CAUTION and self.layer != REACH:
            raise ValueError("REACH CAUTION belongs to the Reach layer; a safety layer uses SAFETY CAUTION.")
        if self.status == SAFETY_CAUTION and self.layer == REACH:
            raise ValueError("SAFETY CAUTION belongs to a safety layer; the Reach layer uses REACH CAUTION.")

    def to_dict(self):
        return asdict(self)


def worst(statuses):
    return max(statuses, key=RANK.__getitem__)


def came_from(layers):
    """Which kind of test the overall result came from: reach, safety, or both."""
    kinds = {REACH if l.layer == REACH else "safety" for l in layers}
    return "both" if len(kinds) > 1 else kinds.pop()


def held_because(status):
    """Why a result is held out of a design package, or None if it isn't held."""
    return {DO_NOT_USE: HELD_FAILS, NOT_CHECKED_YET: HELD_NOT_CHECKED}.get(status)


def combine(layers):
    """(overall status, came_from, held_because) for a task's layer results. Never an average."""
    if not layers:
        raise ValueError("A result needs at least one layer.")
    status = worst(l.status for l in layers)
    return status, came_from(layers), held_because(status)


# ---- Steps (Heather's step-by-step rule, Nov 15): the structure only, no numbers yet. ----

STEP_FIELDS = {
    "step": "what happens, in plain words (e.g. 'pivot to sit on the bench')",
    "movement": "e.g. step across, pivot, sit down, stand up, straight walking, turning, reach",
    "surface": "the surface underfoot or underneath (e.g. 'shower floor', 'bench seat')",
    "wet_condition": "dry, water, soapy water / shampoo, or another named liquid",
    "contact": "bare feet, shoe, sock, crutch tip, seated skin or clothing",
    "support": "what the person can hold or lean on (e.g. 'grab bar', 'bench edge', 'none')",
    "direction": "e.g. 'down to sit' vs 'after standing up'; the same movement in another direction is another step",
}


def check_steps(task):
    """A task's steps, checked: each step may only use the STEP_FIELDS names, and must say what happens."""
    steps = task.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError(f"Task '{task.get('task_id')}': 'steps' must be a list.")
    for i, s in enumerate(steps, 1):
        unknown = set(s) - set(STEP_FIELDS)
        if unknown:
            raise ValueError(f"Task '{task.get('task_id')}' step {i}: unknown field(s) {sorted(unknown)}. "
                             f"Allowed: {', '.join(STEP_FIELDS)}")
        if not str(s.get("step", "")).strip():
            raise ValueError(f"Task '{task.get('task_id')}' step {i}: say what happens in 'step'.")
    return steps


# ---- Old words, for the videos rendered before Nov 15. ----

_LEGACY = {PASS: "PASS", REACH_CAUTION: "CAUTION", SAFETY_CAUTION: "CAUTION",
           NOT_CHECKED_YET: "UNVERIFIED", DO_NOT_USE: "FAIL"}


def legacy_status(status):
    """The pre-Nov 15 word for a result, so the old video scripts still run. Old words pass through."""
    return _LEGACY.get(status, status)
