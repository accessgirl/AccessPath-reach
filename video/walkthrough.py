"""Slow, narrated walkthrough of how the verifier checks a room: the library, the person, the room, then each test
one at a time. Words are on screen and spoken, with subtitles.

  python -m accesspath verify --profile stroke_R_moderate_wheelchair -o out/results.json
  python3 video/fill_poses.py out/results.json
  python3 video/test_clips.py -- --blend out/avatar.blend --results out/results.json \
      --profile stroke_R_moderate_wheelchair --out out/tests
  python3 video/walkthrough.py --clips out/tests --voice-model kokoro-v1.0.onnx --voices voices-v1.0.bin \
      --out out/AccessPath_walkthrough.mp4

Needs pillow, matplotlib, imageio-ffmpeg, and for the voice kokoro-onnx + soundfile with its two model files
(github.com/thewh1teagle/kokoro-onnx releases). Every number shown comes from the library, the room and results.json.
"""
import argparse
import hashlib
import io
import json
import subprocess
import sys
import textwrap
import wave
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_video import (W, H, FPS, BG, INK, MUTED, ACCENT, STATUS, font, text, rrect, appear, blank,  # noqa: E402
                        kicker, fade)
from accesspath.cards import load_library  # noqa: E402
from accesspath.profiles import compose  # noqa: E402
from accesspath.kinematics import load_body, arm_chain, envelope  # noqa: E402

PROFILE = "stroke_R_moderate_wheelchair"
SR = 24000
GAP = 0.9        # silence after each spoken line
LEAD, TAIL = 0.8, 1.6
CLIP_FPS = 12    # the 3D clips play at half speed
WHITE = (255, 255, 255)
CARD_COLORS = {"sourced": (221, 239, 227), "interpolated": (255, 243, 205), "placeholder": (248, 215, 218)}


def inches(m):
    return round(m / 0.0254)


def feet_in(m):
    i = inches(m)
    return f"{i // 12} ft {i % 12} in"


# ---------------------------------------------------------------- drawing helpers


def para(img, xy, s, size, color=INK, alpha=1.0, width=40, bold=False, gap=1.3):
    """Wrapped text; returns the y below it."""
    x, y = xy
    for line in textwrap.wrap(s, width):
        text(img, (x, y), line, size, color, bold=bold, alpha=alpha)
        y += int(size * gap)
    return y


def subtitle(img, s):
    lines = textwrap.wrap(s, 62)[:3]
    h = 30 + 40 * len(lines)
    rrect(img, (50, H - h - 16, W - 50, H - 16), (20, 26, 24), 0.9, radius=14)
    for i, line in enumerate(lines):
        text(img, (W // 2, H - h + 4 + 40 * i), line, 29, WHITE, anchor="ma")


def chip(img, xy, status, alpha=1.0, size=30):
    x, y = xy
    w = int(size * 0.72 * len(status)) + 40
    rrect(img, (x, y, x + w, y + int(size * 1.7)), STATUS[status], alpha, radius=int(size * 0.85))
    text(img, (x + w // 2, y + int(size * 0.85)), status, size, WHITE, bold=True, alpha=alpha, anchor="mm")
    return x + w


def mark(img, xy, ok, alpha=1.0, size=40):
    text(img, xy, "✓" if ok else "✗", size, STATUS["PASS"] if ok else STATUS["FAIL"], bold=True, alpha=alpha)


# ---------------------------------------------------------------- scenes


class Scene:
    """Narrated lines, spoken one after another; `draw(img, t, on)` builds the picture, `on(i)` fades in with line i."""

    def __init__(self, lines, draw, holds=None):
        self.lines = [(l, l) if isinstance(l, str) else l for l in lines]  # (spoken, subtitle)
        self.draw = draw
        self.holds = holds or {}  # extra seconds after line i (e.g. while a clip plays)

    def layout(self, durs):
        self.starts, t = [], LEAD
        for i, d in enumerate(durs):
            self.starts.append(t)
            t += d + GAP + self.holds.get(i, 0.0)
        self.ends = self.starts[1:] + [t]
        self.duration = t + TAIL

    def frame(self, t):
        img = blank()
        self.draw(img, t, lambda i, dur=0.5: appear(t, self.starts[i], dur) if i < len(self.starts) else 0.0)
        cur = [i for i, s in enumerate(self.starts) if s <= t < self.ends[i]]
        if cur:
            subtitle(img, self.lines[cur[-1]][1])
        return fade(img, t, self.duration)


class Story:
    def __init__(self, a):
        self.lib = load_library(ROOT / "data" / "card_library.xlsx")
        self.profile = compose(self.lib, PROFILE)
        self.body = load_body(ROOT / "data" / "body.json", self.profile.posture)
        self.room = json.loads((ROOT / "data" / "rooms" / "test_bathroom.json").read_text())
        self.fx = {f["id"]: f for f in self.room["fixtures"]}
        self.results = [r for r in json.loads(Path(a.results).read_text()) if r["profile"] == PROFILE]
        self.clips = Path(a.clips)
        self.bodyjson = json.loads((ROOT / "data" / "body.json").read_text())

    # -------------------------------------------------------- intro

    def title(self):
        def draw(img, t, on):
            rrect(img, (80, 230, 92, 420), ACCENT, on(0), radius=4)
            text(img, (120, 225), "AccessPath", 92, INK, bold=True, alpha=on(0))
            text(img, (124, 345), "How it checks a room, step by step", 38, MUTED, alpha=on(0))
            text(img, (124, 420), "Every number shown comes from the tool's own output.", 28, ACCENT, alpha=on(1))
        return Scene(["This is AccessPath. This video shows how it checks a room, one step at a time.",
                      "Nothing here is staged. Every number on the screen comes straight from the tool's own output."],
                     draw)

    def question(self):
        def draw(img, t, on):
            kicker(img, "The question", on(0))
            text(img, (80, 120), "Can this person use this room?", 54, INK, bold=True, alpha=on(0))
            text(img, (80, 250), "A building code:", 34, MUTED, bold=True, alpha=on(1))
            text(img, (80, 300), "the same numbers for everyone.", 34, MUTED, alpha=on(1))
            text(img, (80, 390), "AccessPath:", 34, ACCENT, bold=True, alpha=on(2))
            text(img, (80, 440), "one specific person: what they can reach,", 34, INK, alpha=on(2))
            text(img, (80, 490), "and what they need to get through a door.", 34, INK, alpha=on(2))
        return Scene(["The question is simple. Can this particular person use this room?",
                      "A building code checks every room against the same numbers, for everyone.",
                      "AccessPath checks the room against one specific person: what they can reach, and what they "
                      "need to get through a door."], draw)

    def steps(self):
        names = ["The library", "The person", "The room", "The tests"]

        def draw(img, t, on):
            kicker(img, "Four steps", on(0))
            text(img, (80, 110), "How it works", 54, INK, bold=True, alpha=on(0))
            for i, s in enumerate(names):
                a = on(i + 1)
                x = 80 + i * 285
                rrect(img, (x, 280, x + 250, 420), WHITE, a, outline=ACCENT, width=3)
                text(img, (x + 125, 320), str(i + 1), 44, ACCENT, bold=True, alpha=a, anchor="mm")
                text(img, (x + 125, 380), s, 28, INK, bold=True, alpha=a, anchor="mm")
        return Scene(["It works in four steps.", "First, a library of research.", "Second, choosing the person.",
                      "Third, the room.", "And fourth, the tests, one at a time."], draw)

    # -------------------------------------------------------- step 1

    def library(self):
        counts = Counter(c.status for c in self.lib.cards.values())
        n = len(self.lib.cards)
        card = self.lib.cards["base-shoulder_R-flex"]
        rows = [("sourced", counts["sourced"], "from published research"),
                ("interpolated", counts["interpolated"], "careful estimates, labelled as estimates"),
                ("placeholder", counts["placeholder"], "known gaps: no number until research exists")]

        def draw(img, t, on):
            kicker(img, "Step 1 · The library", on(0))
            text(img, (80, 100), f"{n} joint cards", 54, INK, bold=True, alpha=on(0))
            a = on(1)
            rrect(img, (720, 110, 1200, 420), WHITE, a, outline=(210, 210, 205))
            rrect(img, (720, 110, 1200, 170), ACCENT, a, radius=18)
            text(img, (745, 124), "One card", 28, WHITE, bold=True, alpha=a)
            text(img, (745, 190), "Joint: shoulder (right)", 26, INK, alpha=a)
            text(img, (745, 235), f"Movement: {card.DOF_axis}, arm forward", 26, INK, alpha=a)
            text(img, (745, 280), f"Range: {card.ROM_min_deg:.0f}° to {card.ROM_max_deg:.0f}°", 26, INK, alpha=a)
            text(img, (745, 325), "Source: Norkin & White;", 22, MUTED, alpha=a)
            text(img, (745, 355), "AAOS reference ranges", 22, MUTED, alpha=a)
            for i, (st, k, label) in enumerate(rows):
                a = on(2 + min(i, 1))
                y = 230 + i * 95
                rrect(img, (80, y, 180, y + 70), CARD_COLORS[st], a, radius=14)
                text(img, (130, y + 35), str(k), 38, INK, bold=True, alpha=a, anchor="mm")
                para(img, (200, y + 6), label, 26, INK, alpha=a, width=30)
        return Scene([
            f"Step one: the library. The tool holds {n} facts about how the joints of the body move. "
            "Each one is called a card.",
            "A card says which joint, which movement, how many degrees, and the research it came from.",
            f"{counts['sourced']} cards come straight from published research. {counts['interpolated']} are careful "
            "estimates, and they are labelled as estimates.",
            f"And {counts['placeholder']} are gaps, where good research doesn't exist yet. The tool keeps track of "
            "those, and never fills them in with a guess."], draw)

    # -------------------------------------------------------- step 2

    SHORT = {"baseline_standing": "No limitations, standing", "baseline_wheelchair": "No arm limits, wheelchair",
             "stroke_R_severe": "Stroke, right side, severe", "stroke_R_moderate": "Stroke, right side, moderate",
             "stroke_R_mild": "Stroke, right side, mild",
             "stroke_R_moderate_wheelchair": "Stroke, right side, moderate + wheelchair",
             "hemiplegia_R_mild": "Hemiplegia, right side, with neglect", "kafo_L": "Locked leg brace (KAFO), left",
             "arthritis_both": "Arthritis, both sides", "crutches_wet_floor": "Crutches on a wet floor"}

    def person(self):
        profs = list(self.lib.profiles.values())

        def draw(img, t, on):
            kicker(img, "Step 2 · The person", on(0))
            text(img, (80, 100), "A person is a mix of cards", 50, INK, bold=True, alpha=on(0))
            for i, p in enumerate(profs):
                col, row = divmod(i, 5)
                x, y = 80 + col * 570, 200 + row * 72
                chosen = p.profile_id == PROFILE
                a = on(0)
                hl = on(1) if chosen else 0
                rrect(img, (x, y, x + 540, y + 60), WHITE, a, radius=12,
                      outline=ACCENT if hl > 0.5 else (222, 220, 214), width=4 if hl > 0.5 else 2)
                text(img, (x + 18, y + 15), self.SHORT.get(p.profile_id, p.description), 23, INK if chosen else MUTED, bold=chosen and hl > 0.5,
                     alpha=a)
        return Scene([
            f"Step two: choose the person. A person is built by combining cards. There are {len(profs)} ready-made "
            "people so far.",
            "For this video, we'll use someone who has had a stroke affecting the right side, of moderate severity, "
            "and who uses a manual wheelchair."], draw)

    def choice(self):
        stroke = self.lib.cards["stroke-shoulder-abd-1"]
        seated = self.bodyjson["postures"]["seated_wheelchair"]
        fwd = self.bodyjson["approach"]["seated_wheelchair"]["forward"]

        def draw(img, t, on):
            kicker(img, "What that choice changes", on(0))
            boxes = [
                ("Stroke card", [f"Right shoulder, arm out to the side:",
                                 f"{stroke.ROM_min_deg:.0f}° to {stroke.ROM_max_deg:.0f}° after a moderate stroke.",
                                 "Uses the low end: 45°.", "Source: Chino et al. 1996"], 1),
                ("Wheelchair", [f"Hip {inches(seated['hip_height_m'])} in off the floor.",
                                f"Leans forward at most {seated['trunk_lean_max_deg']}°.",
                                f"Hip {inches(fwd)} in from a wall it faces.", "Marked as estimates."], 3),
                ("Everything else", ["Normal published ranges", "for every other joint.", "",
                                     "Source: Norkin & White; AAOS"], 4),
            ]
            for i, (head, body, li) in enumerate(boxes):
                a = on(li)
                x = 60 + i * 395
                rrect(img, (x, 110, x + 370, 470), WHITE, a, outline=(210, 210, 205))
                rrect(img, (x, 110, x + 370, 170), ACCENT, a, radius=18)
                text(img, (x + 22, 124), head, 28, WHITE, bold=True, alpha=a)
                for j, s in enumerate(body):
                    text(img, (x + 22, 195 + j * 62), s, 21, MUTED if s.startswith(("Source", "Marked")) else INK,
                         bold=j == 2 and i == 0, alpha=on(li + 1) if (i == 0 and j == 2) else a)
        return Scene([
            "Here is what that choice changes.",
            "The stroke card comes from a 1996 study by Chino and colleagues. After a moderate stroke, the right arm "
            "can lift out to the side somewhere between 45 and 90 degrees.",
            "The tool uses 45, the low end of that range, so the room has to work for everyone in that group.",
            "The wheelchair sets how high the person sits, keeps them from leaning forward more than 30 degrees for "
            "balance, and sets how close the chair can get to a wall. Those numbers are marked as estimates for now.",
            "Every other joint starts from normal, published ranges."], draw)

    def gap(self):
        def draw(img, t, on):
            kicker(img, "An honest gap", on(0))
            text(img, (80, 100), "What the data covers for the right arm", 44, INK, bold=True, alpha=on(0))
            mark(img, (90, 210), True, on(1))
            text(img, (150, 215), "Lifting it out to the side: stroke research exists", 30, INK, alpha=on(1))
            mark(img, (90, 290), False, on(1))
            text(img, (150, 295), "Lifting it forward: no stroke research yet", 30, INK, alpha=on(1))
            a = on(2)
            rrect(img, (80, 380, W - 80, 520), (255, 248, 230), a, outline=STATUS["CAUTION"])
            text(img, (110, 400), "So the tool tries the left arm first.", 32, INK, bold=True, alpha=a)
            text(img, (110, 455), "If only the right arm could do a task, the answer is", 28, INK, alpha=a)
            chip(img, (835, 445), "UNVERIFIED", a, 24)
        return Scene([
            "There is one gap in this person's data, and the tool is open about it.",
            "We have stroke research for lifting the right arm out to the side, but not for lifting it forward.",
            "So the tool doesn't fully trust the right arm. It tries the left arm first. If only the right arm could "
            "do a task, the answer would be unverified, not pass."], draw)

    def clouds(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        pts = {s: envelope(arm_chain(self.body, self.profile, s), n=3000, seed=4) for s in ("L", "R")}
        b = self.body
        out = {s: float(np.max(pts[s][:, 0] * (1 if s == "R" else -1))) for s in pts}
        self.outward = out
        fig, ax = plt.subplots(figsize=(10.0, 4.1), dpi=100, facecolor=np.array(BG) / 255)
        ax.set_facecolor(np.array(BG) / 255)
        for s, c in (("L", "#2F5D50"), ("R", "#C0392B")):
            p = pts[s]
            ax.scatter(p[:, 0], p[:, 2], s=9, c=c, alpha=0.35, linewidths=0)
        hip, sh = b.hip_height, b.shoulder_height
        ax.plot([0, 0], [hip, sh], color="#1C2421", lw=5)
        ax.plot([-b.half_shoulder, b.half_shoulder], [sh, sh], color="#1C2421", lw=5)
        ax.add_patch(plt.Circle((0, sh + 0.14), 0.1, color="#1C2421"))
        ax.plot([-0.25, 0.25], [hip - 0.09, hip - 0.09], color="#555", lw=6)
        ax.text(-1.25, 1.85, "LEFT arm", color="#2F5D50", fontsize=22, weight="bold")
        ax.text(0.75, 1.85, "RIGHT arm", color="#C0392B", fontsize=22, weight="bold")
        for s, sign, c in (("L", -1, "#2F5D50"), ("R", 1, "#C0392B")):
            ax.annotate("", xy=(sign * out[s], 0.62), xytext=(0, 0.62),
                        arrowprops=dict(arrowstyle="->", color=c, lw=3))
            ax.text(sign * (out[s] + 0.06), 0.58, f"{inches(out[s])} in", color=c, fontsize=22, weight="bold",
                    ha="right" if sign < 0 else "left")
        ax.set_xlim(-1.45, 1.45)
        ax.set_ylim(0.45, 2.0)
        ax.set_aspect("equal")
        ax.axis("off")
        fig.subplots_adjust(0, 0, 1, 1)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
        plt.close(fig)
        plot = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")

        def draw(img, t, on):
            kicker(img, "What each hand can touch", on(0))
            text(img, (80, 95), "Seen from the front, sitting in the chair", 34, INK, bold=True, alpha=on(0))
            if on(0) > 0:
                img.paste(Image.blend(Image.new("RGB", plot.size, BG), plot, on(0)), (140, 140))
        o = {s: inches(v) for s, v in out.items()}
        return Scene([
            "These clouds show every point each hand can touch, from the chair, seen from the front.",
            f"The left hand reaches about {o['L']} inches out to the side. The right hand reaches only about "
            f"{o['R']}, because of the stroke card. That difference shapes the results that follow."], draw)

    # -------------------------------------------------------- step 3

    def plan(self, img, a, highlight=None, origin=(360, 120), scale=150):
        """Top-down floor plan of the room, fixtures numbered in test order."""
        ox, oy = origin
        d = ImageDraw.Draw(img)

        def P(x, y):
            return ox + x * scale, oy + (3.0 - y) * scale
        for x1, y1, x2, y2 in self.room["walls"]:
            d.line([P(x1, y1), P(x2, y2)], fill=INK if a > 0.5 else BG, width=8)
        for i, fid in enumerate(self.order()):
            f = self.fx[fid]
            x, y = f["position"][:2]
            if f["type"] == "door":
                w = f["clear_width_m"]
                n = f["wall_normal"]
                along = (-n[1], n[0])
                d.line([P(x - along[0] * w / 2, y - along[1] * w / 2), P(x + along[0] * w / 2, y + along[1] * w / 2)],
                       fill=BG, width=10)
            if "obstruction" in f:
                ob = f["obstruction"]["depth_m"]
                cx, cy = P(x - 0.45, y)
                d.rectangle([cx, cy, cx + 0.9 * scale, cy + ob * scale], fill=(220, 214, 200))
            n = f["wall_normal"]
            px, py = P(x + n[0] * 0.22, y + n[1] * 0.22)
            col = ACCENT if highlight in (None, fid) else (200, 200, 196)
            d.ellipse([px - 22, py - 22, px + 22, py + 22], fill=col)
            text(img, (px, py), str(i + 1), 24, WHITE, bold=True, alpha=a, anchor="mm")

    def order(self):
        return [r["fixture"] for r in self.results]

    NAMES = {"outlet_low": "Outlet near the floor", "outlet_counter": "Outlet above the counter",
             "switch_door": "Light switch", "shelf_high": "Linen shelf",
             "door_main": "Main door", "door_closet": "Closet door"}

    def room_scene(self):
        def draw(img, t, on):
            kicker(img, "Step 3 · The room", on(0))
            text(img, (80, 95), "A test bathroom", 44, INK, bold=True, alpha=on(0))
            self.plan(img, on(0), origin=(80, 170), scale=150)
            for i, fid in enumerate(self.order()):
                a = on(1)
                text(img, (560, 190 + i * 62), f"{i + 1}.  {self.NAMES[fid]}", 30, INK, alpha=a)
        return Scene([
            "Step three: the room. This is a small test bathroom, drawn up for trying the tool out.",
            "It has six things to check: two outlets, a light switch, a linen shelf, and two doors."], draw)

    def answers(self):
        items = [("PASS", "This person can do it, and the data behind it is solid."),
                 ("CAUTION", "This person can do it, but research says many people in their group can't."),
                 ("UNVERIFIED", "It only works by filling a gap with normal values. It might really be a fail."),
                 ("FAIL", "This person can't do it.")]

        def draw(img, t, on):
            kicker(img, "Four possible answers", on(0))
            for i, (st, s) in enumerate(items):
                a = on(i + 1)
                y = 130 + i * 110
                chip(img, (80, y), st, a, 26)
                para(img, (330, y + 4), s, 28, INK, alpha=a, width=48)
        return Scene([
            "Every check ends with one of four answers.",
            "Pass: this person can do it, and the data behind that is solid.",
            "Caution: this person can do it, but research shows many people in their group can't.",
            "Unverified: it only works if a gap is filled with normal values. The real answer might be fail.",
            "Fail: this person can't do it."], draw)

    # -------------------------------------------------------- step 4

    def tests_intro(self):
        def draw(img, t, on):
            kicker(img, "Step 4 · The tests", on(0))
            text(img, (80, 250), "Now the tests,", 60, INK, bold=True, alpha=on(0))
            text(img, (80, 340), "one at a time.", 60, ACCENT, bold=True, alpha=on(0))
        return Scene(["Step four. Now the tests, one at a time."], draw)

    def test_intro(self, k, r):
        f = self.fx[r["fixture"]]
        n = len(self.results)
        name = self.NAMES[r["fixture"]]
        if f["type"] == "door":
            what = f"Clear opening: {inches(f['clear_width_m'])} in"
            ask = "Is the opening wide enough for the wheelchair?"
            said = [f"Test {k} of {n}: the {name.lower()}. This check is about width, not reaching."]
        else:
            h = f["position"][2]
            what = f"Height: {inches(h)} in ({feet_in(h)})" if h > 1.5 else f"Height: {inches(h)} in"
            ask = "Can the person touch it with a fingertip, from the wheelchair?"
            said = [f"Test {k} of {n}: the {name.lower()}, {inches(h)} inches off the floor.", ask]
            if "obstruction" in f:
                ob = f["obstruction"]
                said.append(f"There's a counter in front of it, {inches(ob['depth_m'])} inches deep, and the chair "
                            "can't roll under it.")
            if r["fixture"] == "switch_door":
                said.append("Forty-eight inches is the highest the A D A allows for a switch.")

        def draw(img, t, on):
            kicker(img, f"Test {k} of {n}", on(0))
            text(img, (80, 100), name, 54, INK, bold=True, alpha=on(0))
            text(img, (80, 190), what, 36, ACCENT, bold=True, alpha=on(0))
            para(img, (80, 260), ask, 30, INK, alpha=on(0), width=34)
            if "obstruction" in f:
                text(img, (80, 380), f"Counter in front: {inches(f['obstruction']['depth_m'])} in deep", 28, MUTED,
                     alpha=on(0))
            self.plan(img, on(0), highlight=r["fixture"], origin=(820, 150), scale=120)
        return Scene([(x, x.replace("A D A", "ADA")) for x in said], draw)

    def attempt(self, k, r, i, att):
        frames = sorted(self.clips.glob(f"{r['fixture']}_{i}_*.png"))
        motion = len(frames) / CLIP_FPS
        side = "left" if att["arm"] == "L" else "right"
        what = "counter" if "obstruction" in self.fx[r["fixture"]] else "wall"
        how = f"facing the {what}" if att["approach"] == "forward" else f"parked sideways along the {what}"
        label = f"Try {i + 1}: {side} arm, chair {how}"
        if att["reached"]:
            outcome, short = "The fingertip touches it.", "✓ Touches it"
        else:
            cm = att["error_m"] * 100
            outcome = (f"The fingertip stops {cm:.0f} centimetres short, about {cm / 2.54:.0f} "
                       f"inch{'es' if round(cm / 2.54) != 1 else ''}.")
            short = f"✗ {cm:.0f} cm ({cm / 2.54:.0f} in) short"
        first = ""
        if i == 0 and k == 1:
            first = " The tool starts with the left arm, because its data is complete."
        if att["arm"] == "R":
            first = " Now it tries the right arm too."
        said = f"Try {i + 1}: the {side} arm, with the chair {how}.{first}"

        def draw(img, t, on):
            if frames:
                start = self.cur.starts[0]
                idx = int(max(0.0, t - start) * CLIP_FPS)
                img.paste(Image.open(frames[min(idx, len(frames) - 1)]).convert("RGB").resize((W, H)))
            box_w = max(560, int(font(30, True).getlength(label)) + 60)
            rrect(img, (30, 24, 30 + box_w, 130), (20, 26, 24), 0.85, radius=12)
            text(img, (50, 36), f"Test {k} · {self.NAMES[r['fixture']]}", 24, (200, 210, 205))
            text(img, (50, 76), label, 30, WHITE, bold=True)
            a = on(1)
            if a > 0:
                col = STATUS["PASS"] if att["reached"] else STATUS["FAIL"]
                rrect(img, (W - 470, 150, W - 30, 230), col, a, radius=16)
                text(img, (W - 250, 190), short, 32, WHITE, bold=True, alpha=a, anchor="mm")
        s = Scene([said, outcome], draw, holds={0: max(0.0, motion - 2.0)})
        return s

    def door_scene(self, k, r):
        f = self.fx[r["fixture"]]
        need = self.bodyjson["doorway_clear_width_m"]["wheelchair"]["value"]
        w = f["clear_width_m"]
        ok = w >= need

        def draw(img, t, on):
            kicker(img, f"Test {k} · {self.NAMES[r['fixture']]}", on(0))
            text(img, (80, 95), "Seen from above", 34, INK, bold=True, alpha=on(0))
            s = 700  # px per metre
            cx, y = W // 2, 330
            a = on(0)
            d = ImageDraw.Draw(img)
            left, right = cx - w * s / 2, cx + w * s / 2
            if a > 0.5:
                d.rectangle([80, y - 14, left, y + 14], fill=INK)
                d.rectangle([right, y - 14, W - 80, y + 14], fill=INK)
            text(img, (cx, y - 70), f"Opening: {inches(w)} in", 34, INK, bold=True, alpha=a, anchor="mm")
            if a > 0.5:
                d.line([left, y - 40, right, y - 40], fill=INK, width=3)
            b = on(1)
            nl, nr = cx - need * s / 2, cx + need * s / 2
            if b > 0.5:
                col = STATUS["PASS"] if ok else STATUS["FAIL"]
                for x0 in range(int(nl), int(nr), 24):
                    d.line([x0, y + 60, min(x0 + 12, nr), y + 60], fill=col, width=5)
                d.line([nl, y + 45, nl, y + 75], fill=col, width=4)
                d.line([nr, y + 45, nr, y + 75], fill=col, width=4)
            text(img, (cx, y + 110), f"Needed for a wheelchair: {inches(need)} in", 32,
                 STATUS["PASS"] if ok else STATUS["FAIL"], bold=True, alpha=b, anchor="mm")
            text(img, (cx, y + 160), "ADA 2010 Standards, section 404.2.3", 24, MUTED, alpha=b, anchor="mm")
        said2 = (f"The A D A requires at least {inches(need)} inches for a wheelchair. "
                 + ("This opening is wider than that." if ok else f"This one is {inches(need) - inches(w)} inches too narrow."))
        return Scene([f"The door's clear opening is {inches(w)} inches.",
                      (said2, said2.replace("A D A", "ADA"))], draw)

    def verdict(self, k, r):
        f = self.fx[r["fixture"]]
        st = r["status"]
        sh = self.body.shoulder_height
        cap = next(c for c in self.lib.caps if c.rule == "target_above_shoulder_height")
        side = "left" if r.get("arm") == "L" else "right"
        what = "counter" if "obstruction" in f else "wall"
        how = {"forward": f"with the chair facing the {what}", "side": f"with the chair parked alongside the {what}"}
        if f["type"] == "door":
            lines = [f"Result: {st.lower()}."]
            why = f"{inches(f['clear_width_m'])} in opening; a wheelchair needs 32 in."
        elif st == "FAIL":
            lines = [f"Result: fail. From this wheelchair, neither arm can reach it. The closest try stops "
                     f"{r['error_m'] * 100:.0f} centimetres short.",
                     "A designer would know to move it before it's built."]
            why = f"Best try stops {r['error_m'] * 100:.0f} cm ({r['error_m'] * 100 / 2.54:.0f} in) short."
        elif st == "CAUTION":
            lines = [f"Result: caution. The {side} hand does reach it, {how[r['approach']]}.",
                     f"But it's above this person's seated shoulder height, about {inches(sh)} inches. A study funded "
                     f"by the U.S. Access Board found that about one in five wheelchair users can't reach above "
                     "shoulder height.",
                     "So instead of a plain pass, the tool flags it."]
            why = (f"Reached ({side} arm), but it's above seated shoulder height ({inches(sh)} in). "
                   f"~{cap.value:.0%} of wheelchair users can't reach that high.")
        else:
            lines = [f"Result: pass. The {side} hand reaches it, {how[r['approach']]}."]
            why = f"Reached with the {side} arm, chair {'facing the wall' if r['approach'] == 'forward' else 'alongside'}."
        src = {"CAUTION": "Source: " + (cap.source or ""),
               "FAIL": "", "PASS": ""}[st] if f["type"] != "door" else "Source: ADA 2010 Standards 404.2.3"

        def draw(img, t, on):
            kicker(img, f"Test {k} · {self.NAMES[r['fixture']]}", on(0))
            text(img, (80, 110), "Result", 40, MUTED, bold=True, alpha=on(0))
            chip(img, (80, 175), st, on(0), 48)
            y = para(img, (80, 300), why, 32, INK, alpha=on(min(1, len(lines) - 1)), width=58)
            if src:
                para(img, (80, y + 20), src, 22, MUTED, alpha=on(len(lines) - 1), width=90)
        return Scene(lines, draw)

    # -------------------------------------------------------- wrap-up

    def summary(self):
        c = Counter(r["status"] for r in self.results)

        def draw(img, t, on):
            kicker(img, "The full report", on(0))
            for i, r in enumerate(self.results):
                a = on(0)
                y = 110 + i * 78
                rrect(img, (80, y, W - 80, y + 66), WHITE, a, radius=12, outline=(222, 220, 214))
                chip(img, (96, y + 12), r["status"], a, 20)
                text(img, (300, y + 18), f"{i + 1}. {self.NAMES[r['fixture']]}", 28, INK, bold=True, alpha=a)
        return Scene([f"Here is the full report for this person: {c['PASS']} passes, {c['CAUTION']} cautions, and "
                      f"{c['FAIL']} fails. Every one comes with its reason and its source."], draw)

    def limits(self):
        items = [f"One body size so far: an average adult, {feet_in(self.bodyjson['height_m'])} tall.",
                 "Wheelchair seat height and distances are estimates, and marked that way.",
                 "Not in the library yet: post-polio, canes, crutches and walkers, and many other conditions.",
                 "The room is a test room. Importing real floor plans (AutoCAD) comes next."]

        def draw(img, t, on):
            kicker(img, "What it doesn't claim yet", on(0))
            for i, s in enumerate(items):
                a = on(i + 1)
                y = 130 + i * 120
                text(img, (90, y), "•", 40, ACCENT, bold=True, alpha=a)
                para(img, (135, y + 4), s, 30, INK, alpha=a, width=56)
        return Scene(["It's just as important to be clear about what the tool doesn't do yet.",
                      f"There's one body size so far: an average adult, five foot seven.",
                      "The wheelchair's seat height and distances are estimates, and they're marked that way.",
                      "Many conditions and mobility aids aren't in the library yet, such as post-polio syndrome, "
                      "canes, crutches and walkers. Each one needs its own research before it goes in.",
                      "And the room is a test room. Reading real architectural floor plans comes next."], draw)

    def close(self):
        def draw(img, t, on):
            rrect(img, (80, 250, 92, 450), ACCENT, on(0), radius=4)
            text(img, (120, 240), "Every result traces back to a card.", 44, INK, bold=True, alpha=on(0))
            text(img, (120, 320), "Every card traces back to its source.", 44, INK, bold=True, alpha=on(0))
            text(img, (124, 410), "AccessPath", 34, ACCENT, bold=True, alpha=on(0))
        return Scene(["Every result can be traced back to a card, and every card back to the research it came from. "
                      "That's what makes it checkable."], draw)

    # -------------------------------------------------------- order

    def scenes(self):
        out = [self.title(), self.question(), self.steps(), self.library(), self.person(), self.choice(), self.gap(),
               self.clouds(), self.room_scene(), self.answers(), self.tests_intro()]
        for k, r in enumerate(self.results, start=1):
            out.append(self.test_intro(k, r))
            if self.fx[r["fixture"]]["type"] == "door":
                out.append(self.door_scene(k, r))
            else:
                for i, att in enumerate(r["attempts"]):
                    s = self.attempt(k, r, i, att)
                    s.is_clip = True
                    out.append(s)
            out.append(self.verdict(k, r))
        out += [self.summary(), self.limits(), self.close()]
        return out


# ---------------------------------------------------------------- audio


class Voice:
    def __init__(self, model, voices, name, speed, cache):
        from kokoro_onnx import Kokoro
        self.k = Kokoro(model, voices)
        self.name, self.speed, self.cache = name, speed, Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)

    def say(self, s):
        key = hashlib.sha1(f"{self.name}|{self.speed}|{s}".encode()).hexdigest()[:16]
        f = self.cache / f"{key}.npy"
        if f.exists():
            return np.load(f)
        audio, sr = self.k.create(s, voice=self.name, speed=self.speed, lang="en-us")
        assert sr == SR
        np.save(f, audio)
        return audio


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "out" / "results.json"))
    ap.add_argument("--clips", default=str(ROOT / "out" / "tests"))
    ap.add_argument("--voice-model", required=True)
    ap.add_argument("--voices", required=True)
    ap.add_argument("--voice", default="am_michael")
    ap.add_argument("--speed", type=float, default=0.85, help="speaking speed; 1.0 is normal")
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", help="write one still per scene into this folder instead of a video")
    a = ap.parse_args()

    story = Story(a)
    scenes = story.scenes()
    voice = Voice(a.voice_model, a.voices, a.voice, a.speed, ROOT / "out" / "voice_cache")
    tracks = []
    for s in scenes:
        clips = [voice.say(spoken) for spoken, _ in s.lines]
        s.layout([len(c) / SR for c in clips])
        tracks.append(clips)

    if a.preview:
        Path(a.preview).mkdir(parents=True, exist_ok=True)
        for i, s in enumerate(scenes):
            story.cur = s
            s.frame(s.ends[-1] - 0.3).save(Path(a.preview) / f"scene_{i:02d}.png")
        print(f"{len(scenes)} previews, {sum(s.duration for s in scenes) / 60:.1f} min")
        return

    total = sum(s.duration for s in scenes)
    audio = np.zeros(int((total + 1) * SR), dtype=np.float32)
    t0 = 0.0
    for s, clips in zip(scenes, tracks):
        for st, c in zip(s.starts, clips):
            i = int((t0 + st) * SR)
            audio[i:i + len(c)] += c
        t0 += s.duration
    wav_path = Path(a.out).with_suffix(".wav")
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())

    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           # Main profile, regular keyframes and 48 kHz stereo audio: phone and TV players showed a black
           # picture (sound only) with the encoder defaults and the 24 kHz mono voice track.
           "-i", str(wav_path), "-c:v", "libx264", "-profile:v", "main", "-level", "3.1", "-pix_fmt", "yuv420p",
           "-g", str(FPS * 2), "-crf", "26", "-maxrate", "1500k", "-bufsize", "3000k",
           "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "96k", "-shortest", "-movflags", "+faststart", a.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for s in scenes:
        story.cur = s
        for i in range(int(round(s.duration * FPS))):
            proc.stdin.write(s.frame(i / FPS).tobytes())
    proc.stdin.close()
    proc.wait()
    wav_path.unlink()
    print(f"Wrote {a.out}: {total / 60:.1f} min, {len(scenes)} scenes")


if __name__ == "__main__":
    main()
