"""Profile composer: baseline cards, then a profile's condition cards on top, giving joint limits per axis.

Limits are signed degrees per joint and motion pair:
  flex  : +flexion / -extension
  abd   : +abduction / -adduction
  dorsi : +dorsiflexion / -plantarflexion
A direction with no card stays at 0 (the joint cannot move that way from neutral).
"""
from dataclasses import dataclass, field, asdict

from .cards import Library, Card

AXES = {
    "flexion": ("flex", +1), "extension": ("flex", -1),
    "abduction": ("abd", +1), "adduction": ("abd", -1),
    "dorsiflexion": ("dorsi", +1), "plantarflexion": ("dorsi", -1),
}


@dataclass
class Flag:
    card_id: str
    joints: list[str]
    level: str  # "placeholder": results that use these joints are UNVERIFIED; "note": context only
    message: str


@dataclass
class ComposedProfile:
    profile_id: str
    description: str
    posture: str
    mobility_aid: str
    affected_sides: list[str]
    limits: dict[str, dict[str, list[float]]]
    applied: list[str] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)

    def placeholder_flags(self, joints):
        """Placeholder flags that touch any of these joints (e.g. the joints in a task chain)."""
        joints = set(joints)
        return [f for f in self.flags if f.level == "placeholder" and joints & set(f.joints)]

    def to_dict(self):
        return asdict(self)


def compose(library: Library, profile_id: str) -> ComposedProfile:
    if profile_id not in library.profiles:
        raise KeyError(f"No profile '{profile_id}'. Profiles: {', '.join(library.profiles)}")
    p = library.profiles[profile_id]
    sides = {"R": ["R"], "L": ["L"], "both": ["R", "L"], "none": []}[p.affected_side]
    out = ComposedProfile(p.profile_id, p.description, p.posture, p.mobility_aid, sides, {})

    for card in library.cards.values():
        if card.is_baseline:
            _set(out.limits, card.joint_id, card.DOF_axis, card.ROM_max_deg)

    touched: dict[str, set[str]] = {}  # joint -> motion pairs that got condition data
    affected: set[str] = set()  # every joint a condition card names, applied or not
    for cid in p.card_ids:
        card = library.cards[cid]
        joints = [card.joint_id.replace("_affected", f"_{s}") for s in sides] if "_affected" in card.joint_id \
            else [card.joint_id]
        axis = AXES.get(card.DOF_axis)
        affected.update(joints)

        if card.status == "placeholder":
            out.flags.append(Flag(cid, joints, "placeholder",
                                  f"{card.condition} {card.DOF_axis} is not sourced yet ({card.joint_id}). "
                                  "Results that depend on it use baseline values and are marked UNVERIFIED."))
            continue
        if axis is None or card.range_kind not in ("joint_limits", "score_band"):
            out.flags.append(Flag(cid, joints, "note",
                                  f"{card.condition} {card.DOF_axis} ({card.range_kind}) is recorded "
                                  "but not applied as a joint limit." + (f" {card.notes}" if card.notes else "")))
            continue

        if card.range_kind == "score_band":
            value = card.ROM_min_deg if card.ROM_min_deg is not None else card.ROM_max_deg
            out.flags.append(Flag(cid, joints, "note",
                                  f"{card.severity} is a scoring band ({_fmt(card.ROM_min_deg)} to "
                                  f"{_fmt(card.ROM_max_deg)} degrees); using its lower edge, {_fmt(value)} degrees, "
                                  "so the design has to work for everyone in the band."))
        else:
            value = card.ROM_max_deg
        for j in joints:
            _set(out.limits, j, card.DOF_axis, value)
            touched.setdefault(j, set()).add(axis[0])
        out.applied.append(cid)

    # A condition that affects a joint but gives no number for one of its motions leaves that motion at
    # able-bodied values. That's a gap, same as a placeholder: results relying on it are UNVERIFIED.
    placeheld = {j for f in out.flags if f.level == "placeholder" for j in f.joints}
    for j in sorted(affected - placeheld):
        dofs = touched.get(j, set())
        rest = sorted(set(out.limits.get(j, {})) - dofs)
        if rest:
            have = f"only {', '.join(sorted(dofs))} has condition data" if dofs else "no card gives it a usable limit"
            out.flags.append(Flag("", [j], "placeholder",
                                  f"{j}: {have}; {', '.join(rest)} still uses able-bodied values."))
    return out


def _set(limits, joint, axis_name, value):
    if axis_name not in AXES or value is None:
        return
    dof, sign = AXES[axis_name]
    lo, hi = limits.setdefault(joint, {}).setdefault(dof, [0.0, 0.0])
    limits[joint][dof] = [lo, float(value)] if sign > 0 else [-float(value), hi]


def _fmt(v):
    return "?" if v is None else f"{v:g}"
