"""Spinal cord injury profiles are named the way a clinical exam (ISNCSCI) writes them: SCI_C6_AIS_A.

Only the naming and the key-muscle list live here. Joint limits still come from sourced cards.
"""
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "isncsci.json"
_REF = json.loads(DATA.read_text())
LEVELS: list[str] = _REF["levels"]
AIS_GRADES = set(_REF["ais_grades"])
KEY_MUSCLES: list[dict] = _REF["key_muscles"]

_NAME = re.compile(r"^SCI_(?P<level>[CTLS][0-9]+(?:-5)?)_AIS_(?P<ais>[A-Z])(?:_.+)?$")


def parse_sci_name(name: str) -> tuple[str, str]:
    """'SCI_C6_AIS_A_wheelchair' -> ('C6', 'A'). Raises ValueError saying what is wrong."""
    m = _NAME.match(name)
    if not m:
        raise ValueError(f"'{name}' should be named SCI_<level>_AIS_<grade>, e.g. SCI_C6_AIS_A.")
    level, ais = m["level"], m["ais"]
    if level not in LEVELS:
        raise ValueError(f"'{name}': '{level}' is not an ISNCSCI level ({LEVELS[0]} to {LEVELS[-1]}).")
    if ais not in AIS_GRADES:
        raise ValueError(f"'{name}': AIS grade '{ais}' should be one of {', '.join(sorted(AIS_GRADES))}.")
    return level, ais


def sci_name(level: str, ais: str, suffix: str | None = None) -> str:
    """The profile name for a level and AIS grade, e.g. sci_name('C6', 'A', 'wheelchair')."""
    name = f"SCI_{level}_AIS_{ais}" + (f"_{suffix}" if suffix else "")
    parse_sci_name(name)
    return name


def key_muscles_below(level: str) -> list[dict]:
    """Key muscles caudal to a neurological level: the ones an injury at that level can weaken."""
    i = LEVELS.index(level)
    return [k for k in KEY_MUSCLES if LEVELS.index(k["level"]) > i]
