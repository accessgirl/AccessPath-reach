"""How big real wheelchair users are, seated in their own chairs (data/wheelchair_size.json, Paquet & Feathers 2004).

Used to check the avatar's seated shoulder height and the knee space under sinks and counters.
"""
import json
from dataclasses import dataclass
from pathlib import Path

SEXES = ("women", "men")


def load(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def _sides(data, dim, sex):
    return list(data[dim][sex].values()) if "left" in data[dim][sex] else [data[dim][sex]]


def _range(data, dim):
    """Widest 5th-95th and the medians, across both sexes and both sides."""
    cells = [c for s in SEXES for c in _sides(data, dim, s) if isinstance(c, dict)]
    return min(c["p5"] for c in cells), [c["p50"] for c in cells], max(c["p95"] for c in cells)


@dataclass
class Placement:
    sex: str
    where: str  # "below 5th", "5th-50th", "50th-95th" or "above 95th"


def place(data, dim, sex, value_cm):
    """Where a value falls among the measured users of one sex (left and right averaged)."""
    sides = _sides(data, dim, sex)
    p5, p50, p95 = (sum(c[k] for c in sides) / len(sides) for k in ("p5", "p50", "p95"))
    if value_cm < p5:
        return Placement(sex, "below 5th")
    if value_cm < p50:
        return Placement(sex, "5th-50th")
    if value_cm <= p95:
        return Placement(sex, "50th-95th")
    return Placement(sex, "above 95th")


def shoulder_report(data, shoulder_m):
    """Where the avatar's seated shoulder sits among measured wheelchair users, in words."""
    cm = shoulder_m * 100
    parts = [f"{p.sex} {p.where} percentile" for p in (place(data, "acromion_height_cm", s, cm) for s in SEXES)]
    return f"Seated shoulder {cm:.1f} cm off the floor: " + ", ".join(parts) + f" (Paquet & Feathers 2004)."


def knee_check(data, underside_m):
    """(status, reason) for pulling in with knees under a sink or counter whose underside is `underside_m` high."""
    _, medians, p95 = _range(data, "knee_height_cm")
    cm = underside_m * 100
    ada = data["ada_knee_clearance_top_m"]
    meets_ada = (f" It meets the ADA's {ada * 39.37:.0f} in knee-clearance height, but"
                 if underside_m >= ada else f" It is also under the ADA's {ada * 39.37:.0f} in knee-clearance height, and")
    measured = (f" Measured wheelchair users' seated knee height: median {min(medians):.1f}-{max(medians):.1f} cm, "
                f"95th percentile up to {p95:.1f} cm (Paquet & Feathers 2004).")
    if cm >= p95:
        return "PASS", f"Knee space {cm:.1f} cm high clears the knees of at least 95% of measured wheelchair users." + measured
    if cm < min(medians):
        return "FAIL", (f"Knee space {cm:.1f} cm high is lower than the knees of more than half of measured "
                        "wheelchair users." + measured)
    return "CAUTION", (f"Knee space {cm:.1f} cm high fits a typical wheelchair user's knees.{meets_ada} "
                       "taller users won't fit under it." + measured)
