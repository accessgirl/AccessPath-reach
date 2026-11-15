"""How many real wheelchair users could reach a spot, from measured data (data/idea_reach.json).

The avatar answers "can this person reach it?". This answers "how many measured manual wheelchair users
could?", so a room isn't passed on the strength of one long-armed avatar.
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Share:
    approach: str
    pct: int | None  # share of everyone recruited (cautious), or None if outside the measured data
    pct_measured: int | None  # the chart's own figure: share of those who could reach above shoulder height
    note: str = ""  # why there's no figure


def load(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def share(data, approach, height_m, offset_m) -> Share:
    """Share of manual wheelchair users who could reach `height_m` above the floor, `offset_m` past the front
    (forward) or side (side) of their chair. Between chart cells, the farther column is used (the cautious one).
    """
    if height_m < data["lowest_measured_m"]:
        return Share(approach, None, None, "below")
    grid = data[approach]
    if height_m >= 2.0:
        return Share(approach, 0, 0)
    row = data["rows_mm"].index(max(300, min(1900, int(math.floor(height_m * 10)) * 100)))
    off_mm = offset_m * 1000
    cols = [i for i, o in enumerate(grid["offsets_mm"]) if o >= off_mm - 1]
    if not cols:
        return Share(approach, None, None, "beyond")
    col = min(cols, key=lambda i: grid["offsets_mm"][i])
    measured = grid["pct"][row][col]
    return Share(approach, int(round(measured * data["measured"] / data["recruited"])), measured)


def best_share(data, approaches, height_m, depth_m) -> Share:
    """The approach most people could manage, the way a real person would pick it."""
    shares = [share(data, a, height_m, data["chair_edge_to_wall_m"][a] + depth_m) for a in approaches]
    known = [s for s in shares if s.pct is not None]
    if known:
        return max(known, key=lambda s: s.pct)
    return shares[0]
