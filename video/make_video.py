"""Builds the ~70 s AccessPath demo video from real verifier output.

  python3 video/make_video.py --clip out/frames/clip_ --out out/AccessPath_demo.mp4

Needs: pillow, matplotlib, imageio-ffmpeg, plus out/results.json and the Blender clip frames.
No audio track: it is meant to be talked over, with captions on screen.
"""
import argparse
import io
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

W, H, FPS = 1280, 720, 24
BG = (246, 244, 239)
INK = (28, 36, 33)
MUTED = (96, 106, 102)
ACCENT = (47, 93, 80)
STATUS = {"PASS": (38, 153, 77), "CAUTION": (224, 150, 20), "UNVERIFIED": (125, 128, 140), "FAIL": (205, 45, 45)}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_fonts = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(BOLD if bold else FONT, size)
    return _fonts[key]


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def appear(t, start, dur=0.5):
    return ease((t - start) / dur)


def blank():
    return Image.new("RGB", (W, H), BG)


def text(img, xy, s, size, color=INK, bold=False, alpha=1.0, anchor="la", dy=0):
    """Draw text faded in by alpha (0..1), sliding up a little as it appears."""
    if alpha <= 0:
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = xy
    d.text((x, y + (1 - alpha) * 14 + dy), s, font=font(size, bold), fill=color + (int(255 * alpha),), anchor=anchor)
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))


def rrect(img, box, fill, alpha=1.0, radius=18, outline=None, width=2):
    if alpha <= 0:
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius, fill=fill + (int(255 * alpha),),
                        outline=(outline + (int(255 * alpha),)) if outline else None, width=width)
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))


def caption(img, s, alpha=1.0):
    """Lower-third caption bar."""
    rrect(img, (60, H - 118, W - 60, H - 40), (28, 36, 33), alpha * 0.88, radius=14)
    text(img, (W // 2, H - 79), s, 28, (255, 255, 255), alpha=alpha, anchor="mm")


def kicker(img, s, alpha):
    text(img, (80, 60), s.upper(), 20, ACCENT, bold=True, alpha=alpha)


# ---------------------------------------------------------------- scenes


def s_title(t, d):
    img = blank()
    a = appear(t, 0.2, 0.8)
    rrect(img, (80, 250, 92, 420), ACCENT, a, radius=4)
    text(img, (120, 250), "AccessPath", 92, INK, bold=True, alpha=a)
    text(img, (124, 370), "Will this building work for the person who uses it?", 34, MUTED, alpha=appear(t, 1.0))
    text(img, (124, 610), "Prototype demo", 22, MUTED, alpha=appear(t, 1.8))
    return img


def s_problem(t, d):
    img = blank()
    kicker(img, "The problem", appear(t, 0))
    text(img, (80, 150), "Accessibility today is a checklist.", 52, INK, bold=True, alpha=appear(t, 0.2))
    text(img, (80, 260), "A door is 32 inches wide, or it isn't.", 36, MUTED, alpha=appear(t, 1.2))
    text(img, (80, 320), "A switch is under 48 inches, or it isn't.", 36, MUTED, alpha=appear(t, 1.9))
    text(img, (80, 450), "But people aren't checklists.", 52, ACCENT, bold=True, alpha=appear(t, 3.0))
    text(img, (80, 530), "A stroke, a leg brace, arthritis: each changes what someone can reach.", 30, MUTED,
         alpha=appear(t, 3.8))
    return img


def s_idea(t, d):
    img = blank()
    kicker(img, "The idea", appear(t, 0))
    text(img, (80, 170), "Test the floor plan against", 52, INK, bold=True, alpha=appear(t, 0.2))
    text(img, (80, 240), "digital people, before it's built.", 52, INK, bold=True, alpha=appear(t, 0.5))
    steps = ["Real clinical data", "Digital body", "Placed in the plan", "Pass / fail report"]
    for i, s in enumerate(steps):
        a = appear(t, 1.4 + i * 0.6)
        x = 80 + i * 285
        rrect(img, (x, 400, x + 250, 500), (255, 255, 255), a, outline=ACCENT)
        text(img, (x + 125, 450), s, 22, INK, bold=True, alpha=a, anchor="mm")
        if i < 3:
            text(img, (x + 267, 450), "→", 30, ACCENT, alpha=appear(t, 1.7 + i * 0.6), anchor="mm")
    return img


CARDS = [
    ("Shoulder", "Able-bodied", "Raise arm: 0–180°", "sourced", "Norkin & White / AAOS"),
    ("Shoulder", "Stroke, moderate", "Sideways: 45° max", "sourced", "Chino et al. 1996"),
    ("Knee", "Leg brace (KAFO)", "Bend: 0°", "interpolated", "Orthotics principle"),
    ("Shoulder", "Arthritis", "Not yet sourced", "placeholder", "Research needed"),
]
CARD_COLORS = {"sourced": (221, 239, 227), "interpolated": (255, 243, 205), "placeholder": (248, 215, 218)}


def s_cards(t, d):
    img = blank()
    kicker(img, "How the bodies are built", appear(t, 0))
    text(img, (80, 110), "Every body is built from joint cards.", 46, INK, bold=True, alpha=appear(t, 0.2))
    for i, (joint, cond, rng, status, src) in enumerate(CARDS):
        a = appear(t, 1.0 + i * 0.7)
        x, y = 80 + i * 285, 230
        rrect(img, (x, y, x + 260, y + 300), (255, 255, 255), a, outline=(210, 210, 205))
        rrect(img, (x, y, x + 260, y + 58), ACCENT, a, radius=18)
        text(img, (x + 20, y + 14), joint, 28, (255, 255, 255), bold=True, alpha=a)
        text(img, (x + 20, y + 80), cond, 22, INK, bold=True, alpha=a)
        text(img, (x + 20, y + 125), rng, 22, INK, alpha=a)
        text(img, (x + 20, y + 180), src, 18, MUTED, alpha=a)
        rrect(img, (x + 20, y + 235, x + 200, y + 275), CARD_COLORS[status], a, radius=20)
        text(img, (x + 110, y + 255), status, 20, INK, alpha=a, anchor="mm")
    caption(img, "Mix cards to make a person. Fix one card: everyone using it updates.", appear(t, 4.2))
    return img


def envelope_points():
    from accesspath.cards import load_library
    from accesspath.profiles import compose
    from accesspath.kinematics import load_body, arm_chain, envelope
    lib = load_library(ROOT / "data" / "card_library.xlsx")
    body = load_body(ROOT / "data" / "body.json", "standing")
    out = {}
    for pid in ["baseline_standing", "stroke_R_severe"]:
        p = compose(lib, pid)
        # Trunk held upright so the picture shows the arm itself.
        p.limits["trunk"]["flex"] = [0.0, 0.0]
        out[pid] = envelope(arm_chain(body, p, "R"), n=2500, seed=3)
    return out, body


class EnvelopeScene:
    def __init__(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        self.plt = plt
        self.pts, self.body = envelope_points()

    def frame(self, t, d):
        plt = self.plt
        fig = plt.figure(figsize=(12.8, 4.5), dpi=100, facecolor=np.array(BG) / 255)
        az = -90 + 55 * (t / d)
        b = self.body
        titles = {"baseline_standing": "Able-bodied arm", "stroke_R_severe": "After a severe stroke (right arm)"}
        colors = {"baseline_standing": "#2F5D50", "stroke_R_severe": "#C0392B"}
        for i, (pid, pts) in enumerate(self.pts.items()):
            ax = fig.add_subplot(1, 2, i + 1, projection="3d")
            ax.set_facecolor(np.array(BG) / 255)
            ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], s=2, c=colors[pid], alpha=0.35, depthshade=False)
            sh, hip = b.shoulder_height, b.hip_height
            # Simple body for scale: legs, trunk, shoulders, head.
            for seg in [((0, 0, 0), (0, 0, hip)), ((0, 0, hip), (0, 0, sh)),
                        ((-b.half_shoulder, 0, sh), (b.half_shoulder, 0, sh))]:
                (x1, y1, z1), (x2, y2, z2) = seg
                ax.plot([x1, x2], [y1, y2], [z1, z2], color="#1C2421", lw=4)
            ax.scatter([0], [0], [sh + 0.15], s=500, c="#1C2421")
            ax.plot([-b.half_shoulder, -b.half_shoulder], [0, 0], [sh, sh - b.arm_length], color="#1C2421", lw=3)
            ax.set_xlim(-0.7, 1.1)
            ax.set_ylim(-0.9, 0.9)
            ax.set_zlim(0.2, 2.2)
            ax.set_box_aspect((1.8, 1.8, 2.0), zoom=1.45)
            ax.view_init(elev=10, azim=az)
            ax.set_axis_off()
            ax.set_title(titles[pid], fontsize=18, color="#1C2421", pad=0)
        fig.subplots_adjust(0, 0, 1, 0.95, 0.0)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        plot = Image.open(buf).convert("RGB")
        img = blank()
        kicker(img, "What the cards do", 1.0)
        text(img, (80, 92), "The cards decide how far each person can reach.", 36, INK, bold=True)
        img.paste(plot, (0, 160))
        caption(img, "Same body, one card changed: the arm can no longer lift out to the side.", appear(t, 1.0))
        return img


class ClipScene:
    def __init__(self, prefix, n):
        self.frames = [Path(f"{prefix}{i:04d}.png") for i in range(1, n + 1)]
        self.frames = [f for f in self.frames if f.exists()]

    def frame(self, t, d):
        i = min(int(t * FPS), len(self.frames) - 1)
        img = Image.open(self.frames[i]).convert("RGB").resize((W, H))
        rrect(img, (40, 30, 700, 92), (28, 36, 33), 0.85, radius=12)
        text(img, (60, 44), "Stroke (right side) + wheelchair, in a test bathroom", 24, (255, 255, 255))
        caption(img, "It puts each person in the room and checks every fixture.",
                appear(t, 0.6))
        return img


def s_results_factory(results):
    rows = [r for r in results if r["profile"] == "stroke_R_moderate_wheelchair"]
    names = {"outlet_low": "Outlet, 12 in high", "outlet_counter": "Outlet above counter",
             "switch_door": "Light switch, 48 in", "shelf_high": "Linen shelf, 5 ft 7 in",
             "door_main": "Main door, 30 in wide", "door_closet": "Closet door, 34 in wide"}
    why = {"outlet_low": "Reaches it with the unaffected (left) arm",
           "outlet_counter": "Fingertip stops 19 cm short: counter is in the way",
           "switch_door": "Reachable, but above seated shoulder height",
           "shelf_high": "Reachable, but above shoulder height for many wheelchair users",
           "door_main": "Under the 32 in a wheelchair needs",
           "door_closet": "Wide enough for a wheelchair"}

    def s_results(t, d):
        img = blank()
        kicker(img, "The report", 1.0)
        text(img, (80, 92), "Pass or fail, per fixture, with the reason.", 40, INK, bold=True)
        for i, r in enumerate(rows):
            a = appear(t, 0.5 + i * 0.55)
            y = 175 + i * 76
            rrect(img, (80, y, W - 80, y + 64), (255, 255, 255), a, radius=12, outline=(222, 220, 214))
            col = STATUS[r["status"]]
            rrect(img, (96, y + 14, 266, y + 50), col, a, radius=18)
            text(img, (181, y + 32), r["status"], 20, (255, 255, 255), bold=True, alpha=a, anchor="mm")
            text(img, (290, y + 18), names.get(r["fixture"], r["fixture"]), 24, INK, bold=True, alpha=a)
            text(img, (640, y + 21), why.get(r["fixture"], ""), 20, MUTED, alpha=a)
        return img
    return s_results


def s_honest(t, d):
    img = blank()
    kicker(img, "Built to be trusted", appear(t, 0))
    text(img, (80, 150), "It doesn't guess.", 60, INK, bold=True, alpha=appear(t, 0.2))
    text(img, (80, 260), "Every number has a citation.", 36, MUTED, alpha=appear(t, 1.0))
    text(img, (80, 320), "Where the research doesn't exist yet, the answer is", 36, MUTED, alpha=appear(t, 1.7))
    a = appear(t, 2.5)
    rrect(img, (80, 390, 370, 450), STATUS["UNVERIFIED"], a, radius=24)
    text(img, (225, 420), "UNVERIFIED", 28, (255, 255, 255), bold=True, alpha=a, anchor="mm")
    text(img, (395, 400), "not a false PASS.", 36, INK, bold=True, alpha=a)
    text(img, (80, 530), "8 research gaps are already tracked, ready to fill.", 30, ACCENT, alpha=appear(t, 3.4))
    return img


def s_status(t, d):
    img = blank()
    kicker(img, "Where it stands", appear(t, 0))
    text(img, (80, 100), "Working prototype", 48, INK, bold=True, alpha=appear(t, 0.2))
    done = ["36 cited joint cards", "10 people profiles", "Reach engine (inverse kinematics)",
            "3D view in Blender", "Pass / fail report", "25 automated tests"]
    for i, s in enumerate(done):
        a = appear(t, 0.8 + i * 0.3)
        y = 190 + i * 58
        text(img, (90, y), "✓", 30, STATUS["PASS"], bold=True, alpha=a)
        text(img, (135, y + 2), s, 28, INK, alpha=a)
    text(img, (700, 190), "Next", 30, ACCENT, bold=True, alpha=appear(t, 3.0))
    nxt = ["Import real AutoCAD floor plans", "Fill the research gaps", "More tasks: showers, transfers",
           "Pilot with an architect"]
    for i, s in enumerate(nxt):
        a = appear(t, 3.3 + i * 0.3)
        text(img, (700, 248 + i * 58), "→  " + s, 26, INK, alpha=a)
    return img


def s_close(t, d):
    img = blank()
    a = appear(t, 0.2, 0.8)
    rrect(img, (80, 270, 92, 410), ACCENT, a, radius=4)
    text(img, (120, 262), "AccessPath", 80, INK, bold=True, alpha=a)
    text(img, (124, 370), "Design for the people who will actually use it.", 34, MUTED, alpha=appear(t, 1.0))
    return img


# ---------------------------------------------------------------- assembly


def fade(img, t, d, edge=0.35):
    k = min(ease(t / edge), ease((d - t) / edge))
    if k >= 1:
        return img
    return Image.blend(Image.new("RGB", img.size, BG), img, k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True, help="Blender clip frame prefix")
    ap.add_argument("--clip-frames", type=int, default=96)
    ap.add_argument("--results", default=str(ROOT / "out" / "results.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", help="write one still per scene into this folder instead of a video")
    a = ap.parse_args()

    results = json.loads(Path(a.results).read_text())
    env = EnvelopeScene()
    clip = ClipScene(a.clip, a.clip_frames)
    scenes = [
        (s_title, 5.0), (s_problem, 7.5), (s_idea, 6.5), (s_cards, 8.5),
        (env.frame, 8.0), (clip.frame, len(clip.frames) / FPS + 3.0),
        (s_results_factory(results), 8.0), (s_honest, 7.0), (s_status, 8.0), (s_close, 5.0),
    ]

    if a.preview:
        Path(a.preview).mkdir(parents=True, exist_ok=True)
        for i, (fn, d) in enumerate(scenes):
            fn(d * 0.8, d).save(Path(a.preview) / f"scene_{i:02d}.png")
        print("previews written")
        return

    import imageio_ffmpeg
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
           "-movflags", "+faststart", a.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    total = 0
    for fn, d in scenes:
        n = int(round(d * FPS))
        for i in range(n):
            t = i / FPS
            proc.stdin.write(fade(fn(t, d), t, d).tobytes())
        total += n
    proc.stdin.close()
    proc.wait()
    print(f"Wrote {a.out}: {total / FPS:.1f} s")


if __name__ == "__main__":
    main()
