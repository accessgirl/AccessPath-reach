"""Narrated video: how AccessPath is built, then six made-up people tested in three made-up rooms.

  for r in bathroom kitchen bedroom; do
    python -m accesspath verify --room data/rooms/test_$r.json -o out/results_$r.json
    python3 video/fill_poses.py out/results_$r.json data/rooms/test_$r.json
  done
  # one .blend per person (build_rig.py + apply_profile.py), then the 3D clips (see CLIPS below):
  python3 video/test_clips.py -- --blend out/blends/<person>.blend --results out/results_<room>.json \
      --profile <person> --room data/rooms/test_<room>.json --out out/clips/<person>/<room> --fixture <id> --final
  python3 video/cast_video.py --voice-model kokoro-v1.0.onnx --voices voices-v1.0.bin --out out/AccessPath_six_people.mp4

Every number shown or spoken comes from the card library, the room files and the verifier's results.
"""
import argparse
import json
import subprocess
import sys
import wave
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_video import W, H, FPS, BG, INK, MUTED, ACCENT, STATUS, font, text, rrect, kicker  # noqa: E402
from walkthrough import Scene, Voice, para, chip, inches, SR, CLIP_FPS, WHITE  # noqa: E402
from accesspath.cards import load_library  # noqa: E402
from accesspath.profiles import compose  # noqa: E402
from accesspath.kinematics import load_body  # noqa: E402

ROOMS = [("bathroom", "Bathroom"), ("kitchen", "Kitchen"), ("bedroom", "Bedroom")]
CAST = [  # profile, short name, one-line description
    ("wheelchair_long_trunk", "Person 1", "Manual wheelchair, tape-measured body"),
    ("wheelchair_short_trunk", "Person 2", "Same as Person 1, shorter trunk"),
    ("stroke_R_moderate_wheelchair", "Person 3", "Stroke (right side, moderate), manual wheelchair"),
    ("arthritis_both", "Person 4", "Arthritis, both sides, standing"),
    ("crutches_wet_floor", "Person 5", "Crutches, on a wet floor"),
    ("kafo_L", "Person 6", "Locked leg brace (KAFO), left leg"),
]
NAMES = {
    "outlet_low": "Low outlet", "outlet_counter": "Outlet over the vanity", "switch_door": "Light switch",
    "shelf_high": "Linen shelf", "door_main": "Bathroom door", "door_closet": "Closet door",
    "sink_vanity": "Knee space: vanity",
    "outlet_backsplash": "Outlet over the counter", "upper_cabinet": "Wall cabinet shelf",
    "sink_kitchen": "Knee space: sink", "prep_counter": "Knee space: work counter", "pantry_shelf": "Pantry shelf",
    "switch_kitchen": "Light switch", "door_kitchen": "Kitchen door", "door_pantry": "Pantry door",
    "outlet_bedside": "Outlet by the bed", "outlet_desk": "Outlet by the desk", "closet_rod": "Closet rod",
    "thermostat": "Thermostat", "switch_bedroom": "Light switch", "door_bedroom": "Bedroom door",
    "door_closet_bed": "Closet door",
}
LIGHT = (222, 220, 214)


def L(s):
    """(spoken, subtitle): spell out what the voice would misread."""
    spoken = (s.replace("ADA", "A D A").replace("KAFO", "K A F O").replace("27.5", "27 and a half")
              .replace("23.5", "23 and a half").replace(" cm", " centimetres").replace("%", " percent"))
    return (spoken, s)


def cm_in(m):
    return f"{m * 100:.0f} cm ({m * 100 / 2.54:.0f} in)"


class Story:
    def __init__(self, a):
        self.lib = load_library(ROOT / "data" / "card_library.xlsx")
        self.bodyjson = json.loads((ROOT / "data" / "body.json").read_text())
        self.rooms, self.res = {}, {}
        for key, _ in ROOMS:
            self.rooms[key] = json.loads((ROOT / "data" / "rooms" / f"test_{key}.json").read_text())
            for r in json.loads((ROOT / "out" / f"results_{key}.json").read_text()):
                self.res[(r["profile"], key, r["fixture"])] = r
        self.people = {pid: compose(self.lib, pid) for pid, _, _ in CAST}
        self.bodies = {pid: load_body(ROOT / "data" / "body.json", p.posture, p.height_m, p.measured)
                       for pid, p in self.people.items()}
        self.clips = Path(a.clips)
        self.cur = None

    def r(self, pid, room, fid):
        return self.res[(pid, room, fid)]

    def fx(self, room, fid):
        return next(f for f in self.rooms[room]["fixtures"] if f["id"] == fid)

    def results_for(self, pid, room):
        return [self.res[(pid, room, f["id"])] for f in self.rooms[room]["fixtures"] if (pid, room, f["id"]) in self.res]

    # -------------------------------------------------------- drawing helpers

    def plan(self, img, room, a, origin, box, pid=None, numbers=False):
        """Top-down plan fitted into `box` (w, h) px; fixtures coloured by result when `pid` is given."""
        rm = self.rooms[room]
        xs = [v for w in rm["walls"] for v in (w[0], w[2])]
        ys = [v for w in rm["walls"] for v in (w[1], w[3])]
        s = min(box[0] / (max(xs) - min(xs)), box[1] / (max(ys) - min(ys)))
        ox, oy = origin
        d = ImageDraw.Draw(img)

        def P(x, y):
            return ox + (x - min(xs)) * s, oy + (max(ys) - y) * s
        if a < 0.5:
            return
        for x1, y1, x2, y2 in rm["walls"]:
            d.line([P(x1, y1), P(x2, y2)], fill=INK, width=6)
        for i, f in enumerate(rm["fixtures"]):
            x, y = f["position"][:2]
            n = f["wall_normal"]
            if f["type"] == "door":
                w = f["clear_width_m"]
                along = (-n[1], n[0])
                d.line([P(x - along[0] * w / 2, y - along[1] * w / 2), P(x + along[0] * w / 2, y + along[1] * w / 2)],
                       fill=BG, width=9)
            if f["type"] in ("sink", "counter") or "obstruction" in f:
                dep = 0.6 if f["type"] in ("sink", "counter") else f["obstruction"]["depth_m"]
                along = (-n[1], n[0])
                pts = [P(x - along[0] * 0.45, y - along[1] * 0.45), P(x + along[0] * 0.45 + n[0] * dep,
                                                                      y + along[1] * 0.45 + n[1] * dep)]
                d.rectangle([min(pts[0][0], pts[1][0]), min(pts[0][1], pts[1][1]),
                             max(pts[0][0], pts[1][0]), max(pts[0][1], pts[1][1])], fill=(220, 214, 200))
        for i, f in enumerate(rm["fixtures"]):
            x, y = f["position"][:2]
            n = f["wall_normal"]
            off = 0.15 if f["type"] != "door" else 0.12
            px, py = P(x + n[0] * off, y + n[1] * off)
            col = ACCENT
            if pid:
                r = self.res.get((pid, room, f["id"]))
                col = STATUS[r["status"]] if r else (200, 200, 196)
            rad = max(9, int(s * 0.075))
            d.ellipse([px - rad, py - rad, px + rad, py + rad], fill=col)
            if numbers:
                text(img, (px, py), str(i + 1), int(rad * 1.1), WHITE, bold=True, anchor="mm")

    def play(self, img, frames, t, box=(0, 0, W, H)):
        if not frames:
            return
        start = self.cur.starts[0]
        idx = int(max(0.0, t - start) * CLIP_FPS)
        im = Image.open(frames[min(idx, len(frames) - 1)]).convert("RGB").resize((box[2] - box[0], box[3] - box[1]))
        img.paste(im, (box[0], box[1]))

    def frames(self, pid, room, fid):
        r = self.r(pid, room, fid)
        i = max(k for k, t in enumerate(r["attempts"]) if (t["arm"], t["approach"]) == (r["arm"], r["approach"]))
        fr = sorted((self.clips / pid / room).glob(f"{fid}_{i}_*.png"))
        if not fr:
            print(f"warning: no clip frames for {pid} {room} {fid} attempt {i}; render them first (see the docstring)")
        return fr

    def label_box(self, img, top, main, width=None):
        w = width or max(560, int(font(30, True).getlength(main)) + 60)
        rrect(img, (30, 24, 30 + w, 130), (20, 26, 24), 0.85, radius=12)
        text(img, (50, 36), top, 24, (200, 210, 205))
        text(img, (50, 76), main, 30, WHITE, bold=True)

    def status_badge(self, img, st, extra, a):
        if a <= 0:
            return
        s = f"{st}  ·  {extra}" if extra else st
        w = int(font(30, True).getlength(s)) + 60
        rrect(img, (W - 30 - w, 150, W - 30, 230), STATUS[st], a, radius=16)
        text(img, (W - 30 - w // 2, 190), s, 30, WHITE, bold=True, alpha=a, anchor="mm")

    # -------------------------------------------------------- part 1: how it's built

    def title(self):
        def draw(img, t, on):
            rrect(img, (80, 220, 92, 460), ACCENT, on(0), radius=4)
            text(img, (120, 210), "AccessPath", 92, INK, bold=True, alpha=on(0))
            text(img, (124, 330), "Six people. Three rooms. One method.", 40, MUTED, alpha=on(0))
            text(img, (124, 410), "Every number shown comes from the tool's own output.", 28, ACCENT, alpha=on(1))
        return Scene(["This is AccessPath. In this video, six different people are tested in three different rooms, "
                      "to show how the tool works, and that it works across very different situations.",
                      "Nothing is staged. Every number on the screen comes from the tool's own output."], draw)

    def problem(self):
        def draw(img, t, on):
            kicker(img, "The question", on(0))
            text(img, (80, 120), "Can this person use this room?", 54, INK, bold=True, alpha=on(0))
            text(img, (80, 250), "A building code:", 34, MUTED, bold=True, alpha=on(1))
            text(img, (80, 300), "the same numbers for everyone.", 34, MUTED, alpha=on(1))
            text(img, (80, 390), "AccessPath:", 34, ACCENT, bold=True, alpha=on(2))
            text(img, (80, 440), "one specific person, their own body, their own limits.", 34, INK, alpha=on(2))
        return Scene(["The question is always the same. Can this particular person use this room?",
                      "A building code checks every room against the same numbers, for everyone.",
                      "AccessPath checks the room against one specific person: their own body, and their own limits."],
                     draw)

    def parts(self):
        names = ["Research library", "The person", "The room", "The tests"]

        def draw(img, t, on):
            kicker(img, "How it's built", on(0))
            text(img, (80, 110), "Four parts", 54, INK, bold=True, alpha=on(0))
            for i, s in enumerate(names):
                a = on(i + 1)
                x = 80 + i * 285
                rrect(img, (x, 280, x + 250, 420), WHITE, a, outline=ACCENT, width=3)
                text(img, (x + 125, 320), str(i + 1), 44, ACCENT, bold=True, alpha=a, anchor="mm")
                text(img, (x + 125, 380), s, 26, INK, bold=True, alpha=a, anchor="mm")
        return Scene(["AccessPath is built from four parts.",
                      "A library of published research on how joints move.",
                      "A person, built from that research and their own measurements.",
                      "A room, with every height and width that matters.",
                      "And the tests, which put the person in the room."], draw)

    def library(self):
        c = Counter(x.status for x in self.lib.cards.values())
        ev = Counter(x.evidence for x in self.lib.cards.values())
        n = len(self.lib.cards)
        rows = [("sourced", c["sourced"], "from published research"),
                ("interpolated", c["interpolated"], "careful estimates, labelled as estimates"),
                ("placeholder", c["placeholder"], "known gaps: no number until research exists")]
        colors = {"sourced": (221, 239, 227), "interpolated": (255, 243, 205), "placeholder": (248, 215, 218)}

        def draw(img, t, on):
            kicker(img, "Part 1 · The research library", on(0))
            text(img, (80, 100), f"{n} joint cards", 54, INK, bold=True, alpha=on(0))
            for i, (st, k, label) in enumerate(rows):
                a = on(1 + i)
                y = 200 + i * 90
                rrect(img, (80, y, 180, y + 70), colors[st], a, radius=14)
                text(img, (130, y + 35), str(k), 38, INK, bold=True, alpha=a, anchor="mm")
                para(img, (200, y + 6), label, 26, INK, alpha=a, width=30)
            a = on(4)
            rrect(img, (700, 190, 1200, 480), WHITE, a, outline=LIGHT)
            text(img, (725, 210), "Verified = 5 independent", 28, INK, bold=True, alpha=a)
            text(img, (725, 248), "sources agree", 28, INK, bold=True, alpha=a)
            b = on(5)
            text(img, (725, 310), f"Verified today: {ev.get('verified', 0)}", 30, STATUS["FAIL"], bold=True, alpha=b)
            text(img, (725, 360), f"Contested: {ev['contested']}", 30, STATUS["CAUTION"], bold=True, alpha=b)
            para(img, (725, 410), "Sources disagree; every number is shown, never averaged.", 22, MUTED, alpha=b,
                 width=40)
        return Scene([
            f"Part one, the research library. It holds {n} cards. Each card is one fact about how a joint moves, "
            "and the research it came from.",
            f"{c['sourced']} come straight from published research.",
            f"{c['interpolated']} are careful estimates, and they are labelled as estimates.",
            f"And {c['placeholder']} are gaps, where the research doesn't exist yet. The tool never fills a gap "
            "with a guess and calls it a pass.",
            "A number only counts as verified when five independent sources agree.",
            L(f"By that rule, none are verified yet, and {ev['contested']} are contested: studies that measured real "
              "people disagree with the textbook. The tool shows that openly, instead of hiding it.")], draw)

    def measurements(self):
        p = self.people["wheelchair_long_trunk"]
        m = p.measured

        def draw(img, t, on):
            kicker(img, "Part 2 · The person", on(0))
            text(img, (80, 100), "Cards, plus a tape measure", 50, INK, bold=True, alpha=on(0))
            a = on(1)
            if a > 0.5:
                d = ImageDraw.Draw(img)
                s = 9.0  # px per inch
                fx, fy = 300, 640  # floor point under the seat front
                seat = fy - m["seat_height_in"] * s
                sh = seat - m["seated_shoulder_in"] * s
                d.line([fx - 140, fy, fx + 260, fy], fill=MUTED, width=3)  # floor
                d.rectangle([fx - 110, seat, fx + 40, seat + 12], fill=(80, 80, 86))  # seat
                d.line([fx - 110, seat, fx - 110, sh - 10], fill=(80, 80, 86), width=6)  # backrest
                d.line([fx - 80, seat, fx - 80, sh], fill=ACCENT, width=12)  # trunk
                d.ellipse([fx - 110, sh - 75, fx - 50, sh - 15], fill=ACCENT)  # head
                d.line([fx - 80, seat, fx + 80, seat], fill=ACCENT, width=12)  # thigh
                knee_y = fy - m["knee_height_in"] * s
                d.line([fx + 80, seat, fx + 80, fy - 10], fill=ACCENT, width=10)  # shin
                arm = m["arm_length_in"] * s
                d.line([fx - 80, sh, fx - 80 + arm, sh], fill=(70, 120, 200), width=10)  # arm held forward
                # dimension lines
                for x, y0, y1, lab, li in [(fx - 170, fy, seat, f"Seat height {m['seat_height_in']:g} in", 2),
                                           (fx - 200, seat, sh, f"Seat to shoulder {m['seated_shoulder_in']:g} in", 3),
                                           (fx + 140, fy, knee_y, f"Knee height {m['knee_height_in']:g} in", 5)]:
                    if on(li) > 0.5:
                        d.line([x, y0, x, y1], fill=INK, width=3)
                        d.line([x - 10, y0, x + 10, y0], fill=INK, width=3)
                        d.line([x - 10, y1, x + 10, y1], fill=INK, width=3)
                if on(4) > 0.5:
                    d.line([fx - 80, sh - 30, fx - 80 + arm, sh - 30], fill=INK, width=3)
            items = [(2, f"Seat height: {m['seat_height_in']:g} in"),
                     (3, f"Seat to shoulder (trunk): {m['seated_shoulder_in']:g} in"),
                     (4, f"Arm length: {m['arm_length_in']:g} in"),
                     (5, f"Knee height: {m['knee_height_in']:g} in")]
            for k, (li, s_) in enumerate(items):
                text(img, (700, 200 + k * 60), s_, 32, INK, bold=True, alpha=on(li))
            para(img, (700, 460), "Each one replaces an estimate. Every result says which values were measured.",
                 26, ACCENT, alpha=on(6), width=34)
        return Scene([
            "Part two, the person. A person is built by combining cards: normal ranges for every joint, plus the "
            "cards for their condition.",
            "For a wheelchair user, four tape measurements make the body their own.",
            L(f"Seat height: {m['seat_height_in']:g} inches, floor to the top of the cushion."),
            L(f"Seat to shoulder: {m['seated_shoulder_in']:g} inches. That's the trunk."),
            L(f"Arm length: {m['arm_length_in']:g} inches, shoulder to fingertip."),
            L(f"And knee height: {m['knee_height_in']:g} inches, floor to the top of the knee."),
            "Each one replaces an estimate. And every result says which values were measured, and which were not."],
            draw)

    def answers(self):
        items = [("PASS", "This person can do it, and the data behind it holds up."),
                 ("CAUTION", "This person can do it, but research says many people in their group can't."),
                 ("UNVERIFIED", "It only works by filling a research gap with normal values. It might really fail."),
                 ("FAIL", "This person can't do it.")]

        def draw(img, t, on):
            kicker(img, "Part 4 · The tests", on(0))
            text(img, (80, 90), "Four possible answers", 44, INK, bold=True, alpha=on(0))
            for i, (st, s) in enumerate(items):
                a = on(i + 1)
                y = 170 + i * 105
                chip(img, (80, y), st, a, 26)
                para(img, (330, y + 4), s, 28, INK, alpha=a, width=48)
        return Scene(["Part four, the tests. Every test ends with one of four answers.",
                      "Pass: this person can do it, and the data behind it holds up.",
                      "Caution: this person can do it, but research shows many people in their group can't.",
                      "Unverified: it only works by filling a research gap with normal values. The real answer "
                      "might be fail.",
                      "And fail: this person can't do it."], draw)

    def rooms_scene(self):
        kinds = sum(len(self.rooms[k]["fixtures"]) for k, _ in ROOMS)

        def draw(img, t, on):
            kicker(img, "Part 3 · The rooms", on(0))
            text(img, (80, 100), "Three made-up rooms, typical builder heights", 40, INK, bold=True, alpha=on(0))
            for i, (key, name) in enumerate(ROOMS):
                a = on(1 + i)
                x = 80 + i * 390
                text(img, (x, 180), name, 32, ACCENT, bold=True, alpha=a)
                self.plan(img, key, a, (x, 230), (330, 300), numbers=True)
                text(img, (x, 560), f"{len(self.rooms[key]['fixtures'])} things to check", 24, MUTED, alpha=a)
        return Scene([
            "Part three, the rooms. There are three, all made up for testing, with typical builder heights.",
            "A bathroom: outlets, a light switch, a linen shelf, the knee space under the sink, and two doors.",
            "A kitchen: an outlet over the counter, a wall cabinet, a pantry shelf, the knee space under the sink and "
            "a lowered work counter, and two doors.",
            f"And a bedroom: outlets, a closet rod, a thermostat, a light switch, and two doors. {kinds} things to "
            "check in all."], draw)

    def cast_scene(self):
        def draw(img, t, on):
            kicker(img, "Six people", on(0))
            text(img, (80, 95), "Made-up examples, not real people", 40, INK, bold=True, alpha=on(0))
            for i, (pid, short, desc) in enumerate(CAST):
                a = on(1 + i // 2)
                col, row = i % 2, i // 2
                x, y = 80 + col * 570, 180 + row * 130
                rrect(img, (x, y, x + 540, y + 110), WHITE, a, radius=14, outline=LIGHT)
                text(img, (x + 22, y + 16), short, 28, ACCENT, bold=True, alpha=a)
                para(img, (x + 22, y + 56), desc, 24, INK, alpha=a, width=40)
        return Scene([
            "Now the six people. They are made-up examples, built to show the range of what the tool handles. "
            "None of them is a real person.",
            "Persons one and two use manual wheelchairs, and their bodies are tape-measured. They are identical "
            "except for one measurement.",
            "Person three had a stroke affecting the right side, and uses a wheelchair. Person four has arthritis "
            "on both sides.",
            L("Person five walks with crutches, on a wet floor. Person six wears a locked brace on the left leg, "
              "called a KAFO.")], draw)

    # -------------------------------------------------------- part 2: Person 1 in detail

    def p1_intro(self):
        def draw(img, t, on):
            kicker(img, "Person 1 · in detail", on(0))
            text(img, (80, 250), "One person, three rooms,", 56, INK, bold=True, alpha=on(0))
            text(img, (80, 330), "every test.", 56, ACCENT, bold=True, alpha=on(0))
        return Scene(["First, person one, in detail: one person, three rooms, and what each test found."], draw)

    def clip_scene(self, pid, room, fid, lines, verdict_line, extra):
        fr = self.frames(pid, room, fid)
        r = self.r(pid, room, fid)
        motion = len(fr) / CLIP_FPS
        short = dict((p, s) for p, s, _ in CAST)[pid]
        main = f"{dict(ROOMS)[room]} · {NAMES[fid]}"

        def draw(img, t, on):
            self.play(img, fr, t)
            self.label_box(img, short, main)
            self.status_badge(img, r["status"], extra, on(verdict_line))
        s = Scene(lines, draw, holds={0: max(0.0, motion - 2.0)})
        return s

    def reach_words(self, r, room):
        side = "left" if r["arm"] == "L" else "right"
        f = self.fx(room, r["fixture"])
        what = "counter" if "obstruction" in f else "wall"
        how = f"facing the {what}" if r["approach"] == "forward" else f"parked alongside the {what}"
        return side, how

    def p1_kitchen_outlet(self):
        pid, room, fid = "wheelchair_long_trunk", "kitchen", "outlet_backsplash"
        r, f = self.r(pid, room, fid), self.fx(room, fid)
        side, how = self.reach_words(r, room)
        return self.clip_scene(pid, room, fid, [
            L(f"In the kitchen: the outlet over the counter, {inches(f['position'][2])} inches up, behind a counter "
              f"{inches(f['obstruction']['depth_m'])} inches deep."),
            L(f"The {side} hand reaches it, with the chair {how}."),
            L(f"But in a study of wheelchair users funded by the U.S. Access Board, only about {r['population_pct']}% "
              "could reach that spot. The study's own line for good design is 75%. So it's a caution.")],
            2, f"{r['population_pct']}% of wheelchair users")

    def p1_upper(self):
        pid, room, fid = "wheelchair_long_trunk", "kitchen", "upper_cabinet"
        r, f = self.r(pid, room, fid), self.fx(room, fid)
        e = r["error_m"]
        return self.clip_scene(pid, room, fid, [
            L(f"Next, the lowest shelf of the wall cabinet, {inches(f['position'][2])} inches up, over the same counter."),
            L(f"The closest try stops {e * 100:.0f} cm short, about {e * 100 / 2.54:.0f} inches. Fail.")],
            1, f"{cm_in(e)} short")

    def knee_scene(self):
        pid = "wheelchair_long_trunk"
        knee = self.bodies[pid].knee_height
        allow = self.bodies[pid].knee_allowance
        prep, sink = self.r(pid, "kitchen", "prep_counter"), self.r(pid, "kitchen", "sink_kitchen")
        h_prep = self.fx("kitchen", "prep_counter")["knee_clearance_m"]
        h_sink = self.fx("kitchen", "sink_kitchen")["knee_clearance_m"]

        def draw(img, t, on):
            kicker(img, "Person 1 · Kitchen · knee space", on(0))
            text(img, (80, 95), "Can the chair pull in underneath?", 44, INK, bold=True, alpha=on(0))
            d = ImageDraw.Draw(img)
            base, s = 600, 11.0  # px per inch
            bars = [(0, "This person's knee", knee, ACCENT, "measured"),
                    (1, "Under the work counter", h_prep, STATUS[prep["status"]], prep["status"]),
                    (2, "Under the sink", h_sink, STATUS[sink["status"]], sink["status"])]
            for i, label, h, col, tag in bars:
                a = on(i + (1 if i else 0))
                if a < 0.5:
                    continue
                x = 160 + i * 340
                hh = h / 0.0254 * s
                if hh > 0:
                    d.rectangle([x, base - hh, x + 160, base], fill=col)
                else:
                    d.line([x, base, x + 160, base], fill=col, width=8)
                text(img, (x + 80, base - hh - 40), f"{h / 0.0254:.1f} in".replace(".0 in", " in"), 30, INK, bold=True,
                     anchor="mm")
                text(img, (x + 80, base + 30), label, 24, INK, anchor="mm")
                text(img, (x + 80, base + 64), tag, 22, col, bold=True, anchor="mm")
            if on(1) > 0.5:
                y = base - knee / 0.0254 * s
                for x0 in range(140, W - 140, 22):
                    d.line([x0, y, x0 + 11, y], fill=ACCENT, width=3)
        return Scene([
            L(f"Then knee space. This person's knee is {knee / 0.0254:.0f} inches off the floor, measured, not "
              "estimated."),
            L(f"The lowered work counter is open {h_prep / 0.0254:.1f} inches underneath: more than the knee needs, plus "
              f"a {allow * 100:.0f} cm allowance for clothing and moving in. Pass.".replace(".0 inches", " inches")),
            "The sink sits on a standard cabinet with no knee space at all. Fail. Measuring first tells you that "
            "before anything is built."], draw)

    def door_scene(self, pid, room, fid, intro, need_m, need_label, source, extra_lines=()):
        f, r = self.fx(room, fid), self.r(pid, room, fid)
        w = f["clear_width_m"]
        short = dict((p, s) for p, s, _ in CAST)[pid]

        def draw(img, t, on):
            kicker(img, f"{short} · {dict(ROOMS)[room]} · {NAMES[fid]}", on(0))
            text(img, (80, 95), "Seen from above", 34, INK, bold=True, alpha=on(0))
            s = 700
            cx, y = W // 2, 330
            a = on(0)
            d = ImageDraw.Draw(img)
            left, right = cx - w * s / 2, cx + w * s / 2
            if a > 0.5:
                d.rectangle([80, y - 14, left, y + 14], fill=INK)
                d.rectangle([right, y - 14, W - 80, y + 14], fill=INK)
                d.line([left, y - 40, right, y - 40], fill=INK, width=3)
            text(img, (cx, y - 70), f"Opening: {w / 0.0254:.0f} in", 34, INK, bold=True, alpha=a, anchor="mm")
            b = on(1)
            nl, nr = cx - need_m * s / 2, cx + need_m * s / 2
            col = STATUS[r["status"]]
            if b > 0.5:
                for x0 in range(int(nl), int(nr), 24):
                    d.line([x0, y + 60, min(x0 + 12, nr), y + 60], fill=col, width=5)
                d.line([nl, y + 45, nl, y + 75], fill=col, width=4)
                d.line([nr, y + 45, nr, y + 75], fill=col, width=4)
            text(img, (cx, y + 110), need_label, 30, col, bold=True, alpha=b, anchor="mm")
            text(img, (cx, y + 155), source, 22, MUTED, alpha=b, anchor="mm")
            chip(img, (80, 560), r["status"], on(len(extra_lines) + 1), 30)
        return Scene([L(intro)] + [L(x) for x in extra_lines] + [L(f"Result: {r['status'].lower()}.")], draw)

    def p1_pantry_door(self):
        pid, room, fid = "wheelchair_long_trunk", "kitchen", "door_pantry"
        f = self.fx(room, fid)
        need = self.bodyjson["doorway_clear_width_m"]["wheelchair"]["value"]
        return self.door_scene(pid, room, fid, f"The pantry door has a clear opening of {f['clear_width_m'] / 0.0254:.0f} "
                               f"inches.", need, f"Needed for a wheelchair: {need / 0.0254:.0f} in",
                               "ADA 2010 Standards, section 404.2.3",
                               [f"The ADA requires at least {need / 0.0254:.0f} inches for a wheelchair."])

    def p1_closet(self):
        pid, room, fid = "wheelchair_long_trunk", "bedroom", "closet_rod"
        r, f = self.r(pid, room, fid), self.fx(room, fid)
        side, how = self.reach_words(r, room)
        return self.clip_scene(pid, room, fid, [
            L(f"In the bedroom: the closet rod, {inches(f['position'][2])} inches up."),
            L(f"The {side} hand reaches it, with the chair {how}. But only about {r['population_pct']}% of measured "
              "wheelchair users could. Caution.")], 1, f"{r['population_pct']}% of wheelchair users")

    def p1_switch(self):
        pid, room, fid = "wheelchair_long_trunk", "bathroom", "switch_door"
        r, f = self.r(pid, room, fid), self.fx(room, fid)
        return self.clip_scene(pid, room, fid, [
            L(f"And in the bathroom, a light switch at {inches(f['position'][2])} inches, the highest the ADA allows."),
            L(f"Reached, and about {r['population_pct']}% of measured wheelchair users could reach it too. Pass.")],
            1, f"{r['population_pct']}% of wheelchair users")

    def report(self, pid, lines):
        short = dict((p, s) for p, s, _ in CAST)[pid]

        def draw(img, t, on):
            kicker(img, f"{short} · the full report", on(0))
            for c, (key, name) in enumerate(ROOMS):
                x = 60 + c * 395
                text(img, (x, 100), name, 30, ACCENT, bold=True, alpha=on(0))
                for i, r in enumerate(self.results_for(pid, key)):
                    y = 150 + i * 62
                    rrect(img, (x, y, x + 375, y + 54), WHITE, on(0), radius=10, outline=LIGHT)
                    chip(img, (x + 10, y + 11), r["status"], on(0), 16)
                    text(img, (x + 170, y + 14), NAMES[r["fixture"]][:22], 21, INK, alpha=on(0))
        return Scene([L(x) for x in lines], draw)

    def p1_report(self):
        pid = "wheelchair_long_trunk"
        c = Counter(r["status"] for k, _ in ROOMS for r in self.results_for(pid, k))
        return self.report(pid, [
            f"Here is person one's full report: {sum(c.values())} checks across three rooms. {c['PASS']} pass, "
            f"{c['CAUTION']} cautions, and {c['FAIL']} fail.",
            "Every one comes with its reason, and the source behind it."])

    def rests_on(self):
        r = self.r("wheelchair_long_trunk", "kitchen", "outlet_backsplash")
        rows = [i for i in r["inputs"] if i["input"] not in ("body height",)]

        def tag(i):
            if i["status"] == "measured":
                return "measured", ACCENT
            if i["status"] == "interpolated":
                return "estimate" + (f" · {i['evidence']}" if i.get("evidence") else ""), STATUS["CAUTION"]
            return i.get("evidence", i["status"]), (STATUS["CAUTION"] if i.get("evidence") == "contested"
                                                     else STATUS["UNVERIFIED"])

        def val(i):
            if "value_deg" in i:
                return f"{i['value_deg']:g}°"
            return f"{i['value_m'] / 0.0254:.1f} in".replace(".0 in", " in")

        def draw(img, t, on):
            kicker(img, "Person 1 · Kitchen · outlet over the counter", on(0))
            text(img, (80, 90), "What this one result rests on", 40, INK, bold=True, alpha=on(0))
            for k, i in enumerate(rows):
                y = 160 + k * 42
                if y > 620:
                    break
                tg, col = tag(i)
                a = on(1) if i["status"] == "measured" else on(2) if i["status"] == "sourced" else on(3)
                name = i["input"].replace("_R", " (right)")
                text(img, (80, y), name, 24, INK, alpha=a)
                text(img, (560, y), val(i), 24, INK, bold=True, alpha=a)
                text(img, (700, y), tg, 24, col, bold=True, alpha=a)
        return Scene([
            "Every result lists exactly what it rests on. Here is that outlet.",
            "The tape measurements, marked measured.",
            L("The joint ranges, from published references, with how many sources agree. Most say contested: "
              "studies of real people measured different numbers than the textbook, and the tool says so."),
            "And the estimates, like how far a seated person can lean forward, labelled as estimates."], draw)

    # -------------------------------------------------------- part 3: the others

    def p2_compare(self):
        a_, b_ = "wheelchair_long_trunk", "wheelchair_short_trunk"
        room, fid = "kitchen", "outlet_backsplash"
        fa, fb = self.frames(a_, room, fid), self.frames(b_, room, fid)
        ra, rb = self.r(a_, room, fid), self.r(b_, room, fid)
        ma, mb = self.people[a_].measured, self.people[b_].measured
        diffs = [(k, f["id"]) for k, _ in ROOMS for f in self.rooms[k]["fixtures"]
                 if (a_, k, f["id"]) in self.res and self.r(a_, k, f["id"])["status"] != self.r(b_, k, f["id"])["status"]]
        motion = max(len(fa), len(fb)) / CLIP_FPS

        def draw(img, t, on):
            kicker(img, "Person 1 vs Person 2 · same height, different trunk", on(0))
            for k, (fr, r, m, name) in enumerate([(fa, ra, ma, "Person 1"), (fb, rb, mb, "Person 2")]):
                x = 20 + k * 630
                self.play(img, fr, t, (x, 110, x + 610, 110 + 343))
                rrect(img, (x, 470, x + 610, 600), WHITE, on(0), radius=12, outline=LIGHT)
                text(img, (x + 20, 485), f"{name}: seat to shoulder {m['seated_shoulder_in']:g} in", 26, INK,
                     bold=True, alpha=on(0))
                if on(2) > 0:
                    chip(img, (x + 20, 535), r["status"], on(2), 22)
                    extra = (f"{r['error_m'] * 100:.0f} cm short" if r["status"] == "FAIL" else "reached")
                    text(img, (x + 250, 545), extra, 24, INK, alpha=on(2))
        n_d = len(diffs)
        return Scene([
            L(f"Person two is identical to person one: same height, same arms, same chair. Only the trunk is "
              f"different: {mb['seated_shoulder_in']:g} inches from seat to shoulder, instead of "
              f"{ma['seated_shoulder_in']:g}."),
            "Same outlet, over the same kitchen counter.",
            L(f"Person one reaches it. Person two stops {rb['error_m'] * 100:.0f} cm short. Fail."),
            L(f"A guess based on height alone would treat them the same. The tape measure changes the answer"
              + (f", here and in {n_d - 1} other place{'s' if n_d - 1 != 1 else ''}." if n_d > 1 else "."))],
            draw, holds={1: max(0.0, motion - 2.0)})

    def p3_stroke(self):
        pid, room, fid = "stroke_R_moderate_wheelchair", "kitchen", "pantry_shelf"
        card = self.lib.cards["stroke-shoulder-abd-1"]
        r, f = self.r(pid, room, fid), self.fx(room, fid)
        side, how = self.reach_words(r, room)
        return self.clip_scene(pid, room, fid, [
            "Person three had a stroke affecting the right side, of moderate severity, and uses a manual wheelchair.",
            L(f"The stroke card limits how far the right arm lifts out to the side: {card.ROM_min_deg:.0f} to "
              f"{card.ROM_max_deg:.0f} degrees. The tool uses the low end, so the room has to work for everyone in "
              "that group."),
            L(f"So it reaches with the {side} hand. Here, the pantry shelf at {inches(f['position'][2])} inches: "
              f"reached, with the chair {how}."),
            L(f"About {r['population_pct']}% of measured wheelchair users could reach it too, under the study's 75% "
              "line. Caution.")], 3, f"{side} arm · {r['population_pct']}%")

    def p4_arthritis(self):
        pid, room, fid = "arthritis_both", "kitchen", "upper_cabinet"
        return self.clip_scene(pid, room, fid, [
            "Person four has arthritis in both arms and both legs, and stands.",
            "Here's an important one. The hand reaches the cabinet shelf, but the tool does not call it a pass.",
            "There is arthritis research for lifting the arm forward. There isn't yet for lifting it out to the side, "
            "or for the hip or the hand. Where a number is missing, the tool fills in normal values, and marks the "
            "answer unverified.",
            "Every test for person four comes back unverified. That is the tool refusing to guess."],
            1, "research gap")

    def p5_crutches(self):
        pid = "crutches_wet_floor"
        fp, fb = self.fx("kitchen", "door_pantry"), self.fx("bedroom", "door_bedroom")
        need = self.bodyjson["doorway_clear_width_m"]["crutches"]["value"]
        rb = self.r(pid, "bedroom", "door_bedroom")
        cau = self.bodyjson["doorway_clear_width_m"]["crutches"].get("caution_below")
        lines = [f"Person five walks with crutches. Doorways first. The pantry door is "
                 f"{fp['clear_width_m'] / 0.0254:.0f} inches.",
                 f"The U.S. Access Board says people using walking aids need at least {need / 0.0254:.0f} inches."]
        s1 = self.door_scene(pid, "kitchen", "door_pantry", lines[0], need,
                             f"Needed with walking aids: {need / 0.0254:.0f} in",
                             "U.S. Access Board, ADAAG Appendix A4.2.1(2)", [lines[1]])
        extra = []
        if rb["status"] == "CAUTION" and cau:
            extra = [f"That meets the {need / 0.0254:.0f} inches, but a UK estimate puts crutch users closer to "
                     f"{cau / 0.0254:.0f} inches. So: caution, not pass."]
        s2 = self.door_scene(pid, "bedroom", "door_bedroom",
                             f"The bedroom door is just over {fb['clear_width_m'] / 0.0254:.0f} inches.", need,
                             f"Needed with walking aids: {need / 0.0254:.0f} in",
                             "U.S. Access Board; UK estimate for crutches", extra)

        def draw(img, t, on):
            kicker(img, "Person 5 · reaching", on(0))
            text(img, (80, 200), "Every reach:", 50, INK, bold=True, alpha=on(0))
            chip(img, (420, 195), "UNVERIFIED", on(0), 34)
            para(img, (80, 320), "No research yet on how far someone on crutches can safely reach on a wet floor.",
                 34, INK, alpha=on(0), width=50)
        s3 = Scene(["Reaching comes back unverified for person five: there's no research yet on how far someone on "
                    "crutches can safely reach on a wet floor. It's on the list to find."], draw)
        return [s1, s2, s3]

    def p6_kafo(self):
        def draw(img, t, on):
            kicker(img, "Person 6 · locked leg brace", on(0))
            text(img, (80, 150), "Reaching:", 44, INK, bold=True, alpha=on(1))
            chip(img, (340, 145), "PASS", on(1), 30)
            text(img, (80, 260), "Doorways:", 44, INK, bold=True, alpha=on(2))
            chip(img, (340, 255), "UNVERIFIED", on(2), 30)
            para(img, (80, 360), "A locked knee swings outward with each step. That swing width isn't in the "
                 "research library yet.", 32, INK, alpha=on(2), width=55)
        return Scene([L("Person six wears a locked brace on the left leg, a KAFO."),
                      "The arms aren't affected, so every reach passes.",
                      "But every doorway comes back unverified. A locked knee swings outward with each step, and "
                      "how wide that swing is isn't in the research library yet."], draw)

    # -------------------------------------------------------- wrap-up

    def whole(self):
        total = sum(1 for k in self.res if k[0] in dict((p, 1) for p, _, _ in CAST))
        order = ["PASS", "CAUTION", "UNVERIFIED", "FAIL"]

        def draw(img, t, on):
            kicker(img, "The whole picture", on(0))
            for c, (key, name) in enumerate(ROOMS):
                text(img, (420 + c * 285, 100), name, 28, ACCENT, bold=True, alpha=on(0))
            for i, (pid, short, desc) in enumerate(CAST):
                y = 150 + i * 80
                a = on(0)
                text(img, (60, y + 6), short, 26, INK, bold=True, alpha=a)
                text(img, (60, y + 40), desc[:34], 18, MUTED, alpha=a)
                for c, (key, _) in enumerate(ROOMS):
                    cnt = Counter(r["status"] for r in self.results_for(pid, key))
                    x = 420 + c * 285
                    for st in order:
                        if cnt[st]:
                            w = 24 * cnt[st]
                            rrect(img, (x, y + 10, x + w, y + 50), STATUS[st], a, radius=6)
                            if w >= 24:
                                text(img, (x + w // 2, y + 30), str(cnt[st]), 18, WHITE, bold=True, alpha=a,
                                     anchor="mm")
                            x += w + 4
            for k, st in enumerate(order):
                chip(img, (420 + k * 200, 640), st, on(1), 16)
        return Scene([f"Here is the whole picture: six people, three rooms, {total} checks.",
                      "The same room gives different answers for different people. A building code would have given "
                      "every one of them the same answer. That difference is what AccessPath is for."], draw)

    def limits(self):
        items = ["The six people are made-up examples, not real people.",
                 "The rooms are test rooms. Reading real floor plans comes next.",
                 "The figure doesn't bend down, kneel or move furniture yet.",
                 "For walking aids, only door widths are in; hallways and turning space aren't yet.",
                 "No number is verified by five sources yet. That's tracked openly.",
                 "It's a planning tool, not a medical assessment or a building inspection."]

        def draw(img, t, on):
            kicker(img, "What it doesn't claim yet", on(0))
            for i, s in enumerate(items):
                a = on(i + 1)
                y = 120 + i * 88
                text(img, (90, y), "•", 40, ACCENT, bold=True, alpha=a)
                para(img, (135, y + 4), s, 28, INK, alpha=a, width=62)
        return Scene(["It's just as important to be clear about what the tool doesn't do yet.",
                      "The six people are made-up examples, not real people.",
                      "The rooms are test rooms. Reading real architectural floor plans comes next.",
                      "The figure doesn't bend down, kneel, or move the furniture yet.",
                      "For canes, crutches and walkers, only door widths are in so far.",
                      "No number is verified by five sources yet, and the tool tracks that openly.",
                      "And it's a planning tool. It isn't a medical assessment, or a building inspection."], draw)

    def close(self):
        def draw(img, t, on):
            rrect(img, (80, 250, 92, 450), ACCENT, on(0), radius=4)
            text(img, (120, 240), "Every result traces back to a card.", 44, INK, bold=True, alpha=on(0))
            text(img, (120, 320), "Every card traces back to its source.", 44, INK, bold=True, alpha=on(0))
            text(img, (124, 410), "AccessPath", 34, ACCENT, bold=True, alpha=on(0))
        return Scene(["Six people, three rooms, one method. Every result traces back to a card, and every card back "
                      "to the research it came from. That's what makes it checkable."], draw)

    def scenes(self):
        out = [self.title(), self.problem(), self.parts(), self.library(), self.measurements(), self.rooms_scene(),
               self.answers(), self.cast_scene(),
               self.p1_intro(), self.p1_kitchen_outlet(), self.p1_upper(), self.knee_scene(), self.p1_pantry_door(),
               self.p1_closet(), self.p1_switch(), self.p1_report(), self.rests_on(),
               self.p2_compare(), self.p3_stroke(), self.report("stroke_R_moderate_wheelchair", [
                   "Person three's report. The left hand does the work, so the results match person one's, wherever "
                   "the right arm isn't needed."]),
               self.p4_arthritis()]
        out += self.p5_crutches()
        out += [self.p6_kafo(), self.whole(), self.limits(), self.close()]
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", default=str(ROOT / "out" / "clips"))
    ap.add_argument("--voice-model", required=True)
    ap.add_argument("--voices", required=True)
    ap.add_argument("--voice", default="am_michael")
    ap.add_argument("--speed", type=float, default=0.9, help="speaking speed; 1.0 is normal")
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
