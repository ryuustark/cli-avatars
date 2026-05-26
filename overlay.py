#!/usr/bin/env python3
"""
AI Agent Desktop Overlay — v0.4
=================================
Transparent always-on-top overlay that renders pixel avatars for
active AI agents and lets them walk on window-top edges as terrain.

v0.4 additions:
  - Caine stick-figure sprite sheet (auto-generated at startup)
  - No session → single idle Caine avatar instead of 4 demo agents
  - Subagent avatars: spawn Caine stick figures for each active subagent
  - Elastic spring line connecting main agent to its subagents
  - Subagent avatars dangle from spring physics, not walk AI

Dependencies:
    pip install pillow pywinctl numpy

Run:
    python overlay.py

Controls:
    Drag HUD panel        → reposition info box
    Right-click avatar    → focus your terminal window
    Right-click empty     → quit
    ESC                   → quit
"""

import ctypes
import tkinter as tk
from tkinter import ttk
import threading
import time
import math
import random
import json
import traceback
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

VERSION = "0.4"

try:
    import pywinctl as pwc
    HAS_WINCTL = True
except ImportError:
    HAS_WINCTL = False
    print("[WARN] pywinctl not installed — window terrain disabled.")
    print("       Install: pip install pywinctl")

try:
    from PIL import Image, ImageTk, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("[WARN] Pillow not installed — using fallback rectangles.")
    print("       Install: pip install pillow")

try:
    from sprite_loader import SpriteRegistry, hue_rotate_image
    HAS_SPRITES = True
except Exception as _sprite_err:
    HAS_SPRITES = False
    print(f"[WARN] sprite_loader failed ({type(_sprite_err).__name__}: {_sprite_err}) -- using procedural sprites only.")


# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

OVERLAY_FPS       = 20
WINDOW_SCAN_RATE  = 0.5
SESSION_SCAN_RATE = 2.0
GRAVITY           = 0.55
WALK_SPEED        = 1.8
JUMP_VEL          = -10.0
AVATAR_W          = 32
AVATAR_H          = 32
FLOOR_MARGIN      = 2
CHROMA_KEY        = "#010101"

SPRING_REST   = 80    # px rest length of elastic line
SPRING_K      = 0.04  # spring stiffness
SPRING_DAMP   = 0.94  # velocity damping for spring avatars
THROW_SCALE   = 0.4   # fraction of mouse delta → throw velocity on drag release

FLOOR_LINE_ALPHA = 0.0    # 0.0=off, 1.0=solid — floor platform line visibility
FLOOR_LINE_COLOR = "#44aaff"
OVERLAY_ALPHA    = 1.0    # window alpha: 0.1–1.0

WALL_MARGIN       = 6     # px proximity to latch onto a wall
WALL_CLIMB_SPEED  = 1.4   # px/frame upward climb velocity
WALL_CLIMB_CHANCE = 0.4   # probability of climbing vs passing through on contact

TEST_SUBAGENTS = 0    # set > 0 to spawn fake subagents on demo avatar for testing
AVATAR_SCALE   = 2.5  # global sprite scale multiplier — 2.0 = double size (0.5 steps)

BODY_COLORS = [
    "#4488ff", "#ff6644", "#44cc88", "#dd44cc",
    "#ffaa22", "#22ccff", "#ff4488", "#88ff44",
]

SPRITES_DIR = Path(__file__).parent / "Sprites"

# Skin cycling order for real sessions (index 0 = first real session)
REAL_SESSION_SKINS = ["caine", "meowatar", "amongo", "michimaru"]


# ═══════════════════════════════════════════════════════════════
#  CAINE STICK-FIGURE SPRITE SHEET GENERATOR
# ═══════════════════════════════════════════════════════════════

def _extract_bubble_sheet(path: Path) -> None:
    """
    Build bubble.png — 192×240 px, 48×48 cells, 4 cols × 5 rows —
    by extracting and remapping frames from Images/char_Bubble.png.

    Source: ../Images/char_Bubble.png — 336×144 px, 7 cols × 3 rows, 48×48 cells.
      Row 0 (down):  walk1, walk2/idle, walk3, type1, type2, read1, read2
      Row 1 (up):    same sequence, back-facing
      Row 2 (right): same sequence, side-facing

    Target row → source (col, row) mapping:
      0 idle:  (1,0), (0,0), (1,0), (2,0)  — front neutral sway
      1 walk:  (0,2), (1,2), (2,2), (1,2)  — right walk cycle
      2 sit:   (3,0), (4,0), (3,0), (4,0)  — front type1/type2
      3 stand: (5,0), (6,0), (5,0), (6,0)  — front read1/read2
      4 jump:  (3,2), (1,2), (4,2), (2,2)  — right active frames
    """
    if not HAS_PIL:
        print("[sprites] Pillow required to extract bubble.png")
        return

    src_path = Path(__file__).parent.parent / "Images" / "char_Bubble.png"
    if not src_path.exists():
        print(f"[sprites] WARN: source not found at {src_path} — skipping bubble.png")
        return

    FW, FH = 48, 48
    src = Image.open(str(src_path)).convert("RGBA")

    def crop(col, row):
        return src.crop((col * FW, row * FH, (col + 1) * FW, (row + 1) * FH))

    # (src_col, src_row) per target frame, row-major
    mapping = [
        # target row 0 — idle: front neutral sway
        [(1, 0), (0, 0), (1, 0), (2, 0)],
        # target row 1 — walk: right-facing walk cycle
        [(0, 2), (1, 2), (2, 2), (1, 2)],
        # target row 2 — sit/think: front type frames
        [(3, 0), (4, 0), (3, 0), (4, 0)],
        # target row 3 — stand/done: front read frames
        [(5, 0), (6, 0), (5, 0), (6, 0)],
        # target row 4 — jump/subagent: right active frames
        [(3, 2), (1, 2), (4, 2), (2, 2)],
    ]

    out = Image.new("RGBA", (FW * 4, FH * 5), (0, 0, 0, 0))
    for tgt_row, frames in enumerate(mapping):
        for tgt_col, (sc, sr) in enumerate(frames):
            out.paste(crop(sc, sr), (tgt_col * FW, tgt_row * FH))

    out.save(str(path))
    print(f"[sprites] extracted bubble.png from char_Bubble.png ({out.width}x{out.height} px, 48x48 cells)")


def _extract_caine_sheet(path: Path) -> None:
    """
    Build caine.png — 192×240 px, 48×48 cells, 4 cols × 5 rows —
    by extracting and remapping frames from Images/char_caine.png.

    Source: ../Images/char_caine.png — 336×144 px, 7 cols × 3 rows, 48×48 cells.
      Row 0 (down/front): walk1, walk2/idle, walk3, type1, type2, read1, read2
      Row 1 (up/back):    same sequence
      Row 2 (right/side): same sequence

    Target row → source (col, row) mapping:
      0 idle:  (1,0),(0,0),(1,0),(2,0)  — front neutral sway
      1 walk:  (0,2),(1,2),(2,2),(1,2)  — right-facing walk cycle
      2 sit:   (3,0),(4,0),(3,0),(4,0)  — front type1/type2 loop
      3 stand: (5,0),(6,0),(5,0),(6,0)  — front read1/read2 loop
      4 jump:  (3,2),(1,2),(4,2),(2,2)  — right active frames
    """
    if not HAS_PIL:
        print("[sprites] Pillow required to extract caine.png")
        return

    src_path = Path(__file__).parent.parent / "Images" / "char_caine.png"
    if not src_path.exists():
        print(f"[sprites] WARN: source not found at {src_path} — skipping caine.png")
        return

    FW, FH = 48, 48
    src = Image.open(str(src_path)).convert("RGBA")

    def crop(col, row):
        return src.crop((col * FW, row * FH, (col + 1) * FW, (row + 1) * FH))

    mapping = [
        [(1, 0), (0, 0), (1, 0), (2, 0)],   # idle — front neutral sway
        [(0, 2), (1, 2), (2, 2), (1, 2)],   # walk — right-facing cycle
        [(3, 0), (4, 0), (3, 0), (4, 0)],   # sit  — front type loop
        [(5, 0), (6, 0), (5, 0), (6, 0)],   # stand — front read loop
        [(3, 2), (1, 2), (4, 2), (2, 2)],   # jump — right active frames
    ]

    out = Image.new("RGBA", (FW * 4, FH * 5), (0, 0, 0, 0))
    for tgt_row, frames in enumerate(mapping):
        for tgt_col, (sc, sr) in enumerate(frames):
            out.paste(crop(sc, sr), (tgt_col * FW, tgt_row * FH))

    out.save(str(path))
    print(f"[sprites] extracted caine.png from char_caine.png ({out.width}x{out.height} px, 48x48 cells)")


def _extract_amongo_sheet(path: Path) -> None:
    """
    Build amongo.png — 160×200 px, 40×40 cells, 4 cols × 5 rows —
    by extracting and remapping frames from Images/Amongo Cat.png.

    Source: ../Images/Amongo Cat.png — 360×280 px, 9 cols × 7 rows, 40×40 cells.
      Row 0: idle  (cols 0–3 non-empty)
      Row 1: walk  (cols 0–3 non-empty)
      Row 2: sit   (col 0 only)
      Row 3: stand (col 0 only)
      Row 4: jump  (col 0 only)
      Row 5: sleep (col 0 only)
      Row 6: spawn/despawn effect — skipped

    Target row → source (col, row) mapping:
      0 idle:  (0,0),(1,0),(2,0),(3,0)  — full 4-frame idle cycle
      1 walk:  (0,1),(1,1),(2,1),(3,1)  — full 4-frame walk cycle
      2 sit:   (0,2)                    — single sit frame, rest transparent
      3 stand: (0,3),(0,0)              — stand + idle alternating
      4 jump:  (0,4),(1,1),(0,4),(3,1)  — jump alternating with walk for bounce
    """
    if not HAS_PIL:
        print("[sprites] Pillow required to extract amongo.png")
        return

    src_path = Path(__file__).parent.parent / "Images" / "Amongo Cat.png"
    if not src_path.exists():
        print(f"[sprites] WARN: source not found at {src_path} — skipping amongo.png")
        return

    FW, FH = 40, 40
    src = Image.open(str(src_path)).convert("RGBA")

    def crop(col, row):
        return src.crop((col * FW, row * FH, (col + 1) * FW, (row + 1) * FH))

    mapping = [
        # target row 0 — idle: full 4-frame cycle
        [(0, 0), (1, 0), (2, 0), (3, 0)],
        # target row 1 — walk: full 4-frame cycle
        [(0, 1), (1, 1), (2, 1), (3, 1)],
        # target row 2 — sit/think: single sit frame (loader loops it)
        [(0, 2)],
        # target row 3 — stand/done: stand + idle alternating
        [(0, 3), (0, 0)],
        # target row 4 — jump/subagent: jump frame alternating with walk for bounce
        [(0, 4), (1, 1), (0, 4), (3, 1)],
    ]

    out = Image.new("RGBA", (FW * 4, FH * 5), (0, 0, 0, 0))
    for tgt_row, frames in enumerate(mapping):
        for tgt_col, (sc, sr) in enumerate(frames):
            out.paste(crop(sc, sr), (tgt_col * FW, tgt_row * FH))

    out.save(str(path))
    print(f"[sprites] extracted amongo.png from Amongo Cat.png ({out.width}x{out.height} px, 40x40 cells)")


# ═══════════════════════════════════════════════════════════════
#  SPRITE REGISTRY
# ═══════════════════════════════════════════════════════════════

REGISTRY: Optional["SpriteRegistry"] = SpriteRegistry() if HAS_SPRITES else None


def _load_sprites(registry: "SpriteRegistry") -> None:
    """Extract sprite sheets from source art if missing, then load all sheets."""
    bubble_path = SPRITES_DIR / "bubble.png"
    if not bubble_path.exists():
        _extract_bubble_sheet(bubble_path)

    caine_path = SPRITES_DIR / "caine.png"
    if not caine_path.exists():
        _extract_caine_sheet(caine_path)

    amongo_path = SPRITES_DIR / "amongo.png"
    if not amongo_path.exists():
        _extract_amongo_sheet(amongo_path)

    sheets = [
        ("bubble",   "bubble.png",       48, 48),
        ("caine",    "caine.png",        48, 48),
        ("meowatar", "meowatar.png",     60, 50),
        ("amongo",   "amongo.png",       40, 40),
        ("bunnylot", "BunnyLot.png",     40, 56),
        ("michimaru","Michimaru.png",    40, 51),
    ]
    for name, fname, fw, fh in sheets:
        path = SPRITES_DIR / fname
        if path.exists():
            try:
                registry.load(name, str(path), frame_w=fw, frame_h=fh, scale=AVATAR_SCALE)
                print(f"[sprites] loaded {name} ({fw}x{fh})")
            except Exception as e:
                print(f"[sprites] could not load {fname}: {e}")
        else:
            print(f"[sprites] not found: {path}")


def _startup_report(registry) -> None:
    """Print a boxed summary of sprite load state to the console."""
    sep = "-" * 60
    print(f"\n{sep}")
    print("  AI Overlay -- Sprite Load Report")
    print(sep)
    print(f"  HAS_PIL      : {HAS_PIL}")
    print(f"  HAS_SPRITES  : {HAS_SPRITES}")
    if HAS_SPRITES:
        try:
            from sprite_loader import HAS_NUMPY as _sn
            print(f"  HAS_NUMPY    : {_sn}  {'(hue rotation available)' if _sn else '(install numpy for hue shifts)'}")
        except Exception:
            pass
    print(f"  REGISTRY     : {'OK' if registry else 'None (sprites disabled)'}")
    print(f"  SPRITES_DIR  : {SPRITES_DIR}")
    print(f"  Dir exists   : {SPRITES_DIR.exists()}")

    expected = [
        ("caine",     "caine_stick.png",  32, 32),
        ("meowatar",  "meowatar.png",     60, 50),
        ("amongo",    "Amongo Cat.png",   60, 56),
        ("bunnylot",  "BunnyLot.png",     40, 56),
        ("michimaru", "Michimaru.png",    40, 51),
    ]

    # Attempt each load independently to surface the exact error
    print("  Load diagnostics:")
    for name, fname, fw, fh in expected:
        p = SPRITES_DIR / fname
        if not p.exists():
            print(f"    [{name}]  MISSING  {p}")
            continue
        if not HAS_SPRITES:
            print(f"    [{name}]  SKIP (HAS_SPRITES=False)")
            continue
        try:
            from sprite_loader import SpriteSheet
            sheet = SpriteSheet(str(p), fw, fh, 1.0)
            frames = [sheet.get_frame_count(r) for r in range(sheet.rows)]
            print(f"    [{name}]  OK  {sheet.image.width}x{sheet.image.height}px "
                  f"cell={fw}x{fh}  rows={sheet.rows}  frames={frames}")
        except Exception as e:
            tb = traceback.format_exc().strip().splitlines()
            print(f"    [{name}]  FAILED: {type(e).__name__}: {e}")
            for line in tb[-4:]:
                print(f"              {line}")

    if registry:
        sheets = registry.list_sheets()
        print(f"  Registry sheets: {len(sheets)}")
        for name in sheets:
            sheet = registry._sheets.get(name)
            if sheet:
                rows = "  ".join(
                    f"r{r}={sheet.get_frame_count(r)}f" for r in range(sheet.rows)
                )
                print(f"    [{name}]  {sheet.cell_w}x{sheet.cell_h}  {rows}")
    print(sep + "\n")


# ═══════════════════════════════════════════════════════════════
#  AGENT STATE
# ═══════════════════════════════════════════════════════════════

class S:
    IDLE     = "idle"
    THINKING = "thinking"
    BUSY     = "busy"
    SUBAGENT = "subagent"
    ERROR    = "error"
    DONE     = "done"

STATUS_COLOR = {
    S.IDLE:     "#44ff88",
    S.THINKING: "#ffdd44",
    S.BUSY:     "#ff8844",
    S.SUBAGENT: "#aa44ff",
    S.ERROR:    "#ff4444",
    S.DONE:     "#44aaff",
}

@dataclass
class AgentInfo:
    agent_id:       str
    name:           str
    status:         str   = S.IDLE
    tool:           str   = ""
    subagents:      int   = 0
    last_seen:      float = field(default_factory=time.time)
    skin:           str   = "meowatar"
    is_demo:        bool  = False
    workspace_hash: str   = ""
    pid:            int   = 0


# ═══════════════════════════════════════════════════════════════
#  PROCEDURAL PIXEL SPRITE — fallback
# ═══════════════════════════════════════════════════════════════

_WALK_A = [
    "..HHH...", ".HHHHH..", ".HHHHH..", "..HHH...",
    ".BBBBBB.", "BBBBBBB.", ".L..LL..", "..L.LL..",
]
_WALK_B = [
    "..HHH...", ".HHHHH..", ".HHHHH..", "..HHH...",
    ".BBBBBB.", "BBBBBBB.", ".LL.L...", ".LL..L..",
]

def _parse_sprite(rows, body_rgba, skin_rgba=(255,200,150,255), dark_rgba=(40,40,40,255)):
    scale = 4
    img = Image.new("RGBA", (8*scale, 8*scale), (0,0,0,0))
    dr  = ImageDraw.Draw(img)
    for ri, row in enumerate(rows):
        for ci, ch in enumerate(row):
            if ch == ".":
                continue
            color = {"H":skin_rgba,"B":body_rgba,"L":body_rgba,"D":dark_rgba}.get(ch,body_rgba)
            x0,y0 = ci*scale, ri*scale
            dr.rectangle([x0,y0,x0+scale-1,y0+scale-1], fill=color)
    return img

def make_photo(body_hex, status, frame):
    if not HAS_PIL:
        return None
    br,bg,bb = tuple(int(body_hex.lstrip("#")[i:i+2],16) for i in (0,2,4))
    body_rgba = (br,bg,bb,255)
    rows = _WALK_A if frame%2==0 else _WALK_B
    img  = _parse_sprite(rows, body_rgba)
    dr   = ImageDraw.Draw(img)
    sc = STATUS_COLOR.get(status,"#888888")
    sr,sg,sb = tuple(int(sc.lstrip("#")[i:i+2],16) for i in (0,2,4))
    dr.ellipse([25,1,31,7], fill=(sr,sg,sb,255))
    if status == S.THINKING:
        oy = int(2 + math.sin(frame*0.8)*1.5)
        for i in range(3):
            dr.rectangle([i*4+8,oy,i*4+9,oy+1], fill=(255,255,100,200))
    if status == S.ERROR:
        dr.line([8,12,20,24], fill=(255,60,60,200), width=2)
        dr.line([20,12,8,24], fill=(255,60,60,200), width=2)
    return ImageTk.PhotoImage(img)


# ═══════════════════════════════════════════════════════════════
#  PARTICLE BURST EFFECT
# ═══════════════════════════════════════════════════════════════

@dataclass
class Particle:
    x: float; y: float; vx: float; vy: float
    color: str; life: int; max_life: int
    canvas_id: Optional[int] = None

class BurstEffect:
    N = 14; LIFE = 50

    def __init__(self, cx, cy, color, extra_colors=None, n=None, life=None, speed_max=4.0):
        base_palette = [color, "#ffffff", "#ffdd44", "#88ffcc", "#ff88cc", "#aaddff"]
        if extra_colors:
            base_palette = list(extra_colors) + [color, "#ffffff"]
        n    = n    or self.N
        life = life or self.LIFE
        self.particles = []
        for i in range(n):
            ang   = (i / n) * 2 * math.pi + random.uniform(-0.3, 0.3)
            speed = random.uniform(1.5, speed_max)
            self.particles.append(Particle(
                x=cx, y=cy,
                vx=math.cos(ang)*speed, vy=math.sin(ang)*speed - 2.5,
                color=random.choice(base_palette),
                life=life, max_life=life,
            ))

    def tick(self, canvas):
        alive = False
        for p in self.particles:
            if p.life <= 0:
                if p.canvas_id: canvas.delete(p.canvas_id); p.canvas_id = None
                continue
            alive = True
            p.x += p.vx; p.y += p.vy; p.vy += 0.12; p.life -= 1
            r  = max(1, int(5*p.life/p.max_life))
            x0,y0 = int(p.x)-r, int(p.y)-r
            x1,y1 = int(p.x)+r, int(p.y)+r
            if p.canvas_id:
                canvas.coords(p.canvas_id, x0,y0,x1,y1)
            else:
                p.canvas_id = canvas.create_oval(x0,y0,x1,y1, fill=p.color, outline="", tags="burst")
        return alive

    def cleanup(self, canvas):
        for p in self.particles:
            if p.canvas_id: canvas.delete(p.canvas_id)


class GlitchFlash:
    LIFE = 10
    GRID = 12
    SHARED       = ["#aaaaaa", "#00ffee", "#ff6666"]
    PINK_PALETTE = ["#ff44aa", "#ff00ff", "#ff88cc", "#dd0066", "#ffaadd", "#cc00ff"] + SHARED
    DARK_PALETTE = ["#111111", "#000000", "#1a0a1a", "#0d000d", "#220011", "#0a0a0a"] + SHARED

    def __init__(self, canvas, ax, ay, aw, ah, pink: bool):
        self.canvas  = canvas
        self.life    = self.LIFE
        self.palette = self.PINK_PALETTE if pink else self.DARK_PALETTE
        self._items: list[int] = []
        # 20% inset so the matrix sits inside the avatar bounds
        inset_x = aw * 0.10;  inset_y = ah * 0.10
        self.mx  = ax + inset_x;  self.my = ay + inset_y
        self.mw  = aw * 0.80;     self.mh = ah * 0.80
        self._cw = self.mw / self.GRID
        self._ch = self.mh / self.GRID
        self._draw_cells()

    def _draw_cells(self):
        for _ in range(random.randint(6, 11)):
            col  = random.randint(0, self.GRID - 1)
            row  = random.randint(0, self.GRID - 1)
            span = random.randint(1, min(3, self.GRID - col))
            x0   = self.mx + col  * self._cw
            y0   = self.my + row  * self._ch
            item = self.canvas.create_rectangle(
                x0, y0, x0 + span * self._cw, y0 + self._ch,
                fill=random.choice(self.palette), outline="", width=0)
            self._items.append(item)

    def tick(self) -> bool:
        for item in self._items:
            self.canvas.delete(item)
        self._items.clear()
        self.life -= 1
        if self.life <= 0:
            return False
        self._draw_cells()
        return True


def _sample_sprite_colors(registry, skin: str, n=3) -> list[str]:
    """Sample n visually distinct colors from a sprite's idle frame."""
    if not (registry and HAS_PIL):
        return []
    try:
        with registry._lock:
            sheet = registry._sheets.get(skin)
        if not sheet or not sheet._frames or not sheet._frames[0]:
            return []
        frame = sheet._frames[0][0]
        small = frame.resize((16, 16)).convert("RGBA")
        pixels = [
            (r, g, b) for r, g, b, a in small.getdata()
            if a > 128 and (r + g + b) > 30
        ]
        if not pixels:
            return []
        # Bucket into thirds of hue to get spread; pick brightest from each
        import colorsys
        buckets: list[list] = [[], [], []]
        for r, g, b in pixels:
            h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
            if s > 0.15:
                buckets[int(h * 3) % 3].append((v, r, g, b))
        colors = []
        for bucket in buckets:
            if bucket:
                bucket.sort(reverse=True)
                _, r, g, b = bucket[0]
                colors.append(f"#{r:02x}{g:02x}{b:02x}")
        return colors[:n] if colors else []
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
#  AVATAR ENTITY
# ═══════════════════════════════════════════════════════════════

class Avatar:
    def __init__(self, agent: AgentInfo, sw, sh, color_idx,
                 registry: Optional["SpriteRegistry"] = None,
                 spring_mode: bool = False):
        self.agent      = agent
        self.sw, self.sh = sw, sh
        self.color      = BODY_COLORS[color_idx % len(BODY_COLORS)]
        self.registry   = registry
        self.spring_mode = spring_mode   # True → skip walk AI, driven by spring
        self.aw, self.ah = self._sprite_size()
        self.x          = float(random.randint(60, sw-100))
        self.y          = float(random.randint(30, 200))
        self.vx         = 0.0 if spring_mode else random.choice([-WALK_SPEED, WALK_SPEED])
        self.vy         = 0.0
        self.dir        = 1
        self.on_ground  = False
        self.frame      = 0
        self.ftick      = 0
        self.idle_t     = 0
        self.spr_id     = None
        self.lbl_id     = None
        self._photo     = None
        self._spr_mode  = "none"
        self._prev_status    = agent.status
        self._burst_requested = False
        # Per-instance chaos multipliers (normal avatars = 1.0, subagents get randomized)
        self.anim_speed_mult  = 1.0
        self._spring_k_mult   = 1.0
        self._spring_damp_v   = SPRING_DAMP
        # Wall climb state
        self._wall_climb: Optional[tuple] = None
        # Float-away state (triggered when subagent idle too long)
        self.last_active     = time.time()
        self._floating_away  = False
        self._float_frames   = 0
        # Main-avatar disappear state (5 min inactivity)
        self._vanishing      = False
        self._vanish_frames  = 0
        # Set when task finishes and subagent moves to lingering list
        self._task_done_at: Optional[float] = None

    def _sprite_size(self):
        if self.registry:
            w, h = self.registry.get_render_size(self.agent.skin)
            if w > 0 and h > 0:
                return w, h
        return AVATAR_W, AVATAR_H

    @property
    def _anim_status(self) -> str:
        if self.agent.status == S.IDLE and (abs(self.vx) > 0.1 or self._wall_climb is not None):
            return S.BUSY
        return self.agent.status

    def update(self, floors, walls=()):
        self.aw, self.ah = self._sprite_size()

        # Wall climbing overrides normal gravity + walk when active
        if self._wall_climb is not None and not self.spring_mode:
            wx, wy1, wy2 = self._wall_climb
            near_x = abs((self.x + self.aw / 2) - wx) < WALL_MARGIN + 6
            in_y   = self.y < wy2 and self.y + self.ah > wy1
            if near_x and in_y and self.y > wy1:
                self.vy = -WALL_CLIMB_SPEED
                self.vx  = 0.0
                self.x   = float(wx - self.aw // 2)   # stay glued to wall x
                self.y  += self.vy
                self.ftick += 1
                thresh = max(1, int((OVERLAY_FPS // 6) / self.anim_speed_mult))
                if self.ftick >= thresh:
                    self.ftick = 0; self.frame += 1
                curr = self.agent.status
                if self._prev_status in (S.BUSY, S.THINKING) and curr in (S.IDLE, S.DONE):
                    self._burst_requested = True
                self._prev_status = curr
                return
            else:
                # Reached top or fell off wall — kick off horizontally
                self._wall_climb = None
                self.vx = WALK_SPEED * self.dir
                self.vy = JUMP_VEL * 0.3

        self.vy += GRAVITY
        nx = self.x + self.vx
        ny = self.y + self.vy

        all_floors = floors + [(0, self.sh-2, self.sw, self.sh)]
        self.on_ground = False
        for (fx1, fy, fx2, _) in all_floors:
            if fx1 <= nx + self.aw/2 <= fx2:
                if self.y + self.ah <= fy <= ny + self.ah:
                    ny, self.vy, self.on_ground = fy - self.ah, 0.0, True
                    break

        if not self.spring_mode:
            # Normal walk AI
            if self.agent.status == S.THINKING and self.on_ground and random.random() < 0.04:
                self.vy = JUMP_VEL * 0.5

            self.idle_t -= 1
            if self.idle_t <= 0:
                if self.vx != 0 and random.random() < 0.015:
                    self.vx = 0.0; self.idle_t = random.randint(30,90)
                elif self.vx == 0:
                    self.dir = random.choice([-1,1])
                    self.vx  = WALK_SPEED * self.dir

            if self.vx != 0:
                self.vx = WALK_SPEED * (2.0 if self.agent.status==S.BUSY else 1.0) * self.dir

            # Wall latch check — only for walking avatars, not while airborne far
            if self._wall_climb is None and walls:
                cx = self.x + self.aw / 2
                for (wx, wy1, wy2) in walls:
                    if abs(cx - wx) < WALL_MARGIN and wy1 <= self.y + self.ah and self.y <= wy2:
                        if random.random() < WALL_CLIMB_CHANCE:
                            self._wall_climb = (wx, wy1, wy2)
                            break

        if nx < 0:
            nx, self.vx, self.dir = 0.0, abs(self.vx), 1
        elif nx > self.sw - self.aw:
            nx, self.vx, self.dir = float(self.sw-self.aw), -abs(self.vx), -1

        self.x, self.y = nx, ny

        self.ftick += 1
        thresh = max(1, int((OVERLAY_FPS // (8 if self._anim_status == S.BUSY else 4)) / self.anim_speed_mult))
        if self.ftick >= thresh:
            self.ftick = 0; self.frame += 1

        curr = self.agent.status
        if self._prev_status in (S.BUSY,S.THINKING) and curr in (S.IDLE,S.DONE):
            self._burst_requested = True
        self._prev_status = curr

    def draw(self, canvas):
        px, py = int(self.x), int(self.y)
        sc     = STATUS_COLOR.get(self.agent.status, "#aaaaaa")

        photo = None
        if self.registry:
            photo = self.registry.get_photo(self.agent.skin, self._anim_status, self.frame)
        if photo is None:
            photo = make_photo(self.color, self.agent.status, self.frame)

        if photo:
            if self._spr_mode == "rect" and self.spr_id:
                canvas.delete(self.spr_id); self.spr_id = None
            self._spr_mode = "image"
            self._photo = photo
            if self.spr_id:
                canvas.coords(self.spr_id, px, py)
                canvas.itemconfig(self.spr_id, image=self._photo)
            else:
                self.spr_id = canvas.create_image(px, py, image=self._photo, anchor="nw")
        else:
            if self._spr_mode == "image" and self.spr_id:
                canvas.delete(self.spr_id); self.spr_id = None
            self._spr_mode = "rect"
            dash = (4,2) if (self.agent.is_demo or self.spring_mode) else ()
            if self.spr_id:
                canvas.coords(self.spr_id, px,py,px+self.aw,py+self.ah)
                canvas.itemconfig(self.spr_id, fill=self.color, outline=sc, dash=dash)
            else:
                self.spr_id = canvas.create_rectangle(
                    px,py,px+self.aw,py+self.ah,
                    fill=self.color, outline=sc, width=2, dash=dash)

        # Label
        if self.spring_mode:
            label = self.agent.name
        else:
            pfx   = "[D] " if self.agent.is_demo else ""
            parts = [f"{pfx}{self.agent.name}", self.agent.status]
            if self.agent.tool:
                parts.append(f"→{self.agent.tool[:10]}")
            if self.agent.subagents > 0:
                parts.append(f"⚡{self.agent.subagents}")
            label = "\n".join(parts)

        lx = px + self.aw//2
        ly = py - 14
        if self.lbl_id:
            canvas.coords(self.lbl_id, lx, ly)
            canvas.itemconfig(self.lbl_id, text=label)
        else:
            self.lbl_id = canvas.create_text(
                lx, ly, text=label,
                font=("Courier", 7, "bold"),
                fill="#7799cc" if (self.agent.is_demo or self.spring_mode) else "white",
                justify="center")

    def cleanup(self, canvas):
        for iid in [self.spr_id, self.lbl_id]:
            if iid: canvas.delete(iid)


# ═══════════════════════════════════════════════════════════════
#  SESSION SCANNER
# ═══════════════════════════════════════════════════════════════

class SessionScanner:
    CLAUDE_DIR = Path.home() / ".claude" / "projects"

    def __init__(self):
        self._agents: dict[str,AgentInfo] = {}
        self._lock    = threading.Lock()
        self._tick    = 0
        self._skin_idx = 0   # cycles through REAL_SESSION_SKINS for new sessions

    def get_agents(self):
        with self._lock: return dict(self._agents)

    def loop(self):
        while True: self._scan(); time.sleep(SESSION_SCAN_RATE)

    def _scan(self):
        self._tick += 1
        found: dict[str, AgentInfo] = {}

        if self.CLAUDE_DIR.exists():
            for f in self.CLAUDE_DIR.glob("*/*.jsonl"):
                try:
                    if time.time() - f.stat().st_mtime > 28800:  # 8 hours
                        continue
                    aid = f.stem[:8]                          # session UUID → 1 avatar per session
                    status, tool = self._parse_tail(f)
                    sub_dir = f.parent / f.stem / "subagents"
                    if sub_dir.exists():
                        cutoff = time.time() - 1800
                        subs = sum(1 for sf in sub_dir.glob("*.jsonl")
                                   if sf.stat().st_mtime > cutoff)
                    else:
                        subs = 0
                    found[aid] = AgentInfo(
                        agent_id=aid,
                        name=f"Claude-{aid[:4]}",
                        status=status, tool=tool, subagents=subs,
                        last_seen=f.stat().st_mtime,
                        skin="__new__", is_demo=False,
                        workspace_hash=f.parent.name)
                except Exception:
                    pass

        # No real sessions → single idle demo avatar (hue assigned at spawn)
        if not found:
            found["demo"] = AgentInfo(
                agent_id="demo", name="Caine",
                status=S.IDLE, skin="amongo",
                subagents=TEST_SUBAGENTS, is_demo=True)

        self._match_pids(found)

        # Drop real sessions with no live process — avoids ghost avatars from closed sessions
        live = {aid: ai for aid, ai in found.items() if ai.is_demo or ai.pid}
        if live:
            found = live

        with self._lock:
            for aid, new_a in found.items():
                old = self._agents.get(aid)
                if old and not old.is_demo and not new_a.is_demo:
                    new_a.skin = old.skin   # preserve existing skin across scans
                    if old.pid:
                        new_a.pid = old.pid
                elif not new_a.is_demo and new_a.skin == "__new__":
                    new_a.skin = REAL_SESSION_SKINS[self._skin_idx % len(REAL_SESSION_SKINS)]
                    self._skin_idx += 1
            self._agents = found

    def _match_pids(self, found: dict):
        import re
        hash_of = lambda p: re.sub(r'[^a-zA-Z0-9]', '-', str(p).lower())
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
                try:
                    name = (proc.info['name'] or '').lower()
                    cmdline = ' '.join(proc.info['cmdline'] or []).lower()
                    if 'node' not in name and 'claude' not in name:
                        continue
                    if 'claude' not in cmdline:
                        continue
                    cwd = proc.info['cwd']
                    if not cwd:
                        continue
                    h = hash_of(cwd)
                    for ai in found.values():
                        if ai.workspace_hash and ai.workspace_hash.lower() == h:
                            ai.pid = proc.info['pid']  # all sessions in same workspace share pid
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass

    def _parse_tail(self, path) -> tuple[str, str]:
        try:
            with open(path, "rb") as f:
                size = f.seek(0, 2)
                f.seek(max(0, size - 4096))
                lines = f.read().decode("utf-8", errors="ignore").splitlines()
            for line in reversed(lines[-30:]):
                if '"tool_use"' in line:
                    try:
                        obj = json.loads(line)
                        for block in obj.get("message", {}).get("content", []):
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                return S.BUSY, block.get("name", "")
                    except Exception:
                        pass
                    return S.BUSY, ""
                if '"thinking"' in line:
                    return S.THINKING, ""
        except Exception:
            pass
        return S.IDLE, ""


# ═══════════════════════════════════════════════════════════════
#  WINDOW TERRAIN
# ═══════════════════════════════════════════════════════════════

class WindowTerrain:
    def __init__(self, own_title):
        self._floors: list[tuple] = []
        self._walls:  list[tuple] = []
        self._lock   = threading.Lock()
        self._own    = own_title

    def get_floors(self):
        with self._lock: return list(self._floors)

    def get_walls(self):
        with self._lock: return list(self._walls)

    def loop(self):
        while True: self._scan(); time.sleep(WINDOW_SCAN_RATE)

    def _scan(self):
        if not HAS_WINCTL: return
        candidates = []   # (width, x1, y1, x2, y2)
        try:
            for w in pwc.getAllWindows():
                try:
                    if not w.isVisible or not (w.title or "").strip(): continue
                    if self._own in (w.title or ""): continue
                    r  = w.rect
                    x1 = getattr(r, "left",   0)
                    y1 = getattr(r, "top",    0)
                    x2 = getattr(r, "right",  x1 + 50)
                    y2 = getattr(r, "bottom", y1 + 50)
                    if x2 - x1 < 80 or y1 < 5: continue
                    candidates.append((x2 - x1, x1, y1, x2, y2))
                except Exception: pass
        except Exception as e: print(f"[WARN] Terrain: {e}")

        # Keep only the 10 widest windows as floors
        candidates.sort(reverse=True)
        floors = []
        walls  = []
        for (w_px, x1, y1, x2, y2) in candidates[:10]:
            floors.append((x1, y1, x2, y1 + FLOOR_MARGIN))
            walls.append((x1, y1, y2))   # left edge
            walls.append((x2, y1, y2))   # right edge

        with self._lock:
            self._floors = floors
            self._walls  = walls


def _alpha_stipple(alpha: float) -> str:
    """Map 0–1 opacity to a tkinter canvas stipple pattern string."""
    if alpha >= 1.0:  return ""
    if alpha >= 0.75: return "gray75"
    if alpha >= 0.5:  return "gray50"
    if alpha >= 0.25: return "gray25"
    return "gray12"


# ═══════════════════════════════════════════════════════════════
#  HUD  (draggable)
# ═══════════════════════════════════════════════════════════════

def _hud_status_text(agents) -> tuple[list[tuple[str,str]], bool]:
    """Return (rows, no_sess) for the HUD status panel."""
    real     = sum(1 for a in agents.values() if not a.is_demo)
    demo     = sum(1 for a in agents.values() if a.is_demo)
    busy     = sum(1 for a in agents.values() if a.status == S.BUSY)
    subs     = sum(a.subagents for a in agents.values())
    thinking = sum(1 for a in agents.values() if a.status == S.THINKING)

    no_sess    = (real == 0 and list(agents.keys()) == ["caine"])
    sess_color = "#44ff88" if real > 0 else ("#aaaaaa" if no_sess else "#aaccff")
    sess_line  = "  Waiting for session..." if no_sess else f"  Sessions  : {real} real / {demo} demo"

    rows = [
        (sess_line,                      sess_color),
        (f"  Busy      : {busy}",        STATUS_COLOR[S.BUSY]     if busy     else "#aaccff"),
        (f"  Thinking  : {thinking}",    STATUS_COLOR[S.THINKING] if thinking else "#aaccff"),
        (f"  Subagents : {subs}",        STATUS_COLOR[S.SUBAGENT] if subs     else "#aaccff"),
    ]
    return rows, no_sess


# ═══════════════════════════════════════════════════════════════
#  OVERLAY APP
# ═══════════════════════════════════════════════════════════════

class OverlayApp:
    TITLE = "AI Agent Overlay"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(self.TITLE)
        _ico = Path(__file__).parent / "Caine_Icon.ico"
        if not _ico.exists():
            _ico = Path(__file__).parent.parent / "Images" / "Caine_Icon.ico"
        if _ico.exists():
            try: self.root.wm_iconbitmap(str(_ico))
            except Exception: pass
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.sw, self.sh = sw, sh

        self.root.geometry(f"{sw}x{sh}+0+0")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", OVERLAY_ALPHA)
        self.root.config(bg=CHROMA_KEY)
        self.root.wm_attributes("-transparentcolor", CHROMA_KEY)

        self.canvas = tk.Canvas(self.root, width=sw, height=sh,
            bg=CHROMA_KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.scanner = SessionScanner()
        self.terrain = WindowTerrain(self.TITLE)
        self.avatars: dict[str, Avatar] = {}
        self.sub_avatars: dict[str, list[Avatar]] = {}   # parent_id → [sub Avatar, …]
        self._lingering_subs: list["Avatar"] = []         # task-done subs waiting to float away
        self._dismissed_subs: dict[str, int] = {}         # parent_id → manually dismissed count
        self._cidx   = 0
        self._picker = None
        self._bursts:   list[BurstEffect]  = []
        self._glitches: list[GlitchFlash]  = []

        # Avatar drag state
        self._drag_av:   Optional[Avatar]      = None
        self._drag_off:  tuple[int, int]       = (0, 0)
        self._drag_prev: tuple[int, int]       = (0, 0)

        # Bindings
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.root.bind("<Escape>", lambda e: self._quit())

        self._config_win = None

        self.canvas.bind("<ButtonPress-1>",   self._on_left_press)
        self.canvas.bind("<B1-Motion>",       self._on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_left_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)

        # HUD status window — separate, not topmost, draggable
        self._hud_win = None
        self._hud_drag_origin: Optional[tuple] = None
        self._bubble_icon_photo = None
        self._bubble_icon_id    = None
        self._tray = None

        threading.Thread(target=self.scanner.loop, daemon=True).start()
        threading.Thread(target=self.terrain.loop, daemon=True).start()

        # Load sprites and set up UI in background so window appears immediately
        threading.Thread(target=self._deferred_init, daemon=True).start()
        self._tick()

    def _deferred_init(self):
        if REGISTRY:
            _load_sprites(REGISTRY)
        self.root.after(0, self._load_bubble_icon)
        self.root.after(0, self._create_hud_win)
        self.root.after(0, self._setup_tray)

    # ── Main loop ─────────────────────────────────────────────────────

    def _tick(self):
        agents = self.scanner.get_agents()
        floors = self.terrain.get_floors()
        walls  = self.terrain.get_walls()

        # ── Main avatars ──────────────────────────────────────────────
        for aid in self.avatars.keys() - agents.keys():
            self.avatars.pop(aid).cleanup(self.canvas)
            for sv in self.sub_avatars.pop(aid, []):
                sv.cleanup(self.canvas)

        for aid in agents.keys() - self.avatars.keys():
            agent = agents[aid]
            self.avatars[aid] = Avatar(agent, self.sw, self.sh, self._cidx, REGISTRY)
            self._cidx += 1

        vanished_aids = []
        for aid, av in self.avatars.items():
            av.agent = agents[aid]

            # Refresh activity timestamp while agent is doing work
            if av.agent.status in (S.BUSY, S.THINKING):
                av.last_active = time.time()

            if av._vanishing:
                # Float upward, then pop with sprite-colored particles
                av._vanish_frames += 1
                av.vy  -= 0.18
                av.vx  *= 0.97
                av.y   += av.vy
                av.x   += av.vx
                av.draw(self.canvas)
                if av._vanish_frames >= 65 or av.y < -av.ah:
                    sprite_cols = _sample_sprite_colors(REGISTRY, av.agent.skin)
                    cx, cy = av.x + av.aw / 2, av.y + av.ah / 2
                    self._bursts.append(BurstEffect(cx, cy, self.color_for(av),
                        extra_colors=sprite_cols, n=30, life=70, speed_max=6.0))
                    vanished_aids.append(aid)
                continue

            # Trigger vanish after 5 min idle (demo avatars excluded)
            if not av.agent.is_demo and time.time() - av.last_active > 300:
                av._vanishing    = True
                av._vanish_frames = 0
                av.vx = random.uniform(-0.4, 0.4)
                continue

            if av is self._drag_av:
                av.vx = av.vy = 0.0
            else:
                av.update(floors, walls)
                if av.y > self.sh + 80:
                    av.x = float(random.randint(0, max(1, self.sw - av.aw)))
                    av.y = float(self.sh - av.ah - 10)
                    av.vx = random.choice([-WALK_SPEED, WALK_SPEED])
                    av.vy = 0.0
            av.draw(self.canvas)

        for aid in vanished_aids:
            av = self.avatars.pop(aid)
            av.cleanup(self.canvas)
            for sv in self.sub_avatars.pop(aid, []):
                sv.cleanup(self.canvas)

        # ── Subagent avatars ─────────────────────────────────────────
        self.canvas.delete("elastic")   # clear all elastic lines
        self.canvas.delete("floor_line")
        if FLOOR_LINE_ALPHA > 0:
            stpl = _alpha_stipple(FLOOR_LINE_ALPHA)
            for (fx1, fy, fx2, _) in floors:
                # Inset 16px from each end so floor doesn't touch wall corners
                self.canvas.create_line(fx1 + 16, fy, fx2 - 16, fy,
                                        fill=FLOOR_LINE_COLOR, width=2,
                                        stipple=stpl, tags="floor_line")
            for (wx, wy1, wy2) in walls:
                # Start 24px below window top so wall clears the floor line
                self.canvas.create_line(wx, wy1 + 24, wx, wy2,
                                        fill=FLOOR_LINE_COLOR, width=1,
                                        stipple=stpl, tags="floor_line")

        for aid, agent in agents.items():
            if (agent.is_demo and TEST_SUBAGENTS == 0) or agent.subagents <= 0:
                for sv in self.sub_avatars.pop(aid, []):
                    sv._task_done_at = time.time()
                    self._lingering_subs.append(sv)
                continue

            sub_list = self.sub_avatars.setdefault(aid, [])
            parent_av = self.avatars.get(aid)

            # Trim excess subagent avatars — send to lingering so they float away
            while len(sub_list) > agent.subagents:
                sv = sub_list.pop()
                sv._task_done_at = time.time()
                self._lingering_subs.append(sv)

            # Consume dismissed-count credit as scanner naturally reports fewer subagents
            dismissed = self._dismissed_subs.get(aid, 0)
            if dismissed > 0:
                prev = getattr(self, "_prev_subagent_counts", {})
                old_count = prev.get(aid, agent.subagents)
                drop = max(0, old_count - agent.subagents)
                self._dismissed_subs[aid] = max(0, dismissed - drop)
                dismissed = self._dismissed_subs[aid]
            if not hasattr(self, "_prev_subagent_counts"):
                self._prev_subagent_counts: dict[str, int] = {}
            self._prev_subagent_counts[aid] = agent.subagents

            # Spawn new subagent avatars near parent (respecting manual dismissals)
            effective_target = max(0, agent.subagents - dismissed)
            while len(sub_list) < effective_target:
                px = (parent_av.x if parent_av else self.sw/2) + random.randint(-80,80)
                py = (parent_av.y if parent_av else 100)
                sub_info = AgentInfo(
                    agent_id=f"{aid}_sub_{len(sub_list)}",
                    name=f"sub-{len(sub_list)+1}",
                    status=S.BUSY, skin="bubble",
                )
                sv = Avatar(sub_info, self.sw, self.sh,
                            self._cidx + 100 + len(sub_list), REGISTRY,
                            spring_mode=False)
                sv.x, sv.y = float(px), float(py)
                sv.anim_speed_mult = random.uniform(0.5, 2.2)
                sv._spring_k_mult  = random.uniform(0.4, 1.8)
                sv._spring_damp_v  = random.uniform(0.88, 0.97)
                sub_list.append(sv)

            # Refresh last_active while parent is working
            if agent.status in (S.BUSY, S.THINKING):
                for sv in sub_list:
                    sv.last_active = time.time()

            # Update + draw subagents; trigger float-away after 10 min idle
            to_remove = []
            for sv in sub_list:
                if not sv._floating_away and time.time() - sv.last_active > 600:
                    sv._floating_away = True
                    sv._float_frames  = 0
                    sv.vx = random.uniform(-0.6, 0.6)

                if sv._floating_away:
                    sv._float_frames += 1
                    sv.vy  -= 0.22                        # accelerate upward
                    sv.vx  *= 0.97                        # gentle horizontal drift
                    sv.y   += sv.vy
                    sv.x   += sv.vx
                    sv.draw(self.canvas)
                    if sv._float_frames >= 55 or sv.y < -sv.ah:
                        self._bursts.append(BurstEffect(
                            sv.x + sv.aw / 2, sv.y + sv.ah / 2, "#cc66ff"))
                        to_remove.append(sv)
                else:
                    sv.update(floors, walls)
                    sv.draw(self.canvas)

            for sv in to_remove:
                sv.cleanup(self.canvas)
                sub_list.remove(sv)

            # Draw elastic lines only for non-floating subagents, then push behind sprites
            if parent_av:
                for sv in sub_list:
                    if not sv._floating_away:
                        self._draw_elastic(parent_av, sv)
                self.canvas.tag_lower("elastic")

        # ── Lingering subagents (task done, float away after 5 min) ──
        linger_done = []
        for sv in self._lingering_subs:
            if not sv._floating_away and time.time() - sv._task_done_at > 30:
                sv._floating_away = True
                sv._float_frames  = 0
                sv.vx = random.uniform(-0.6, 0.6)

            if sv._floating_away:
                sv._float_frames += 1
                sv.vy -= 0.22
                sv.vx *= 0.97
                sv.y  += sv.vy
                sv.x  += sv.vx
                sv.draw(self.canvas)
                if sv._float_frames >= 55 or sv.y < -sv.ah:
                    self._bursts.append(BurstEffect(
                        sv.x + sv.aw / 2, sv.y + sv.ah / 2, "#cc66ff"))
                    linger_done.append(sv)
            else:
                sv.update(floors, walls)
                sv.draw(self.canvas)

        for sv in linger_done:
            sv.cleanup(self.canvas)
            self._lingering_subs.remove(sv)

        # ── Burst effects ─────────────────────────────────────────────
        for av in list(self.avatars.values()):
            if av._burst_requested:
                av._burst_requested = False
                self._bursts.append(BurstEffect(
                    av.x + av.aw / 2, av.y - 10,
                    STATUS_COLOR.get(av.agent.status, "#44ff88")))

        self._bursts   = [b for b in self._bursts   if b.tick(self.canvas)]
        self._glitches = [g for g in self._glitches if g.tick()]

        self._update_hud_win(agents)
        self.root.after(1000 // OVERLAY_FPS, self._tick)

    # ── Spring physics ────────────────────────────────────────────────

    def color_for(self, av: "Avatar") -> str:
        return STATUS_COLOR.get(av.agent.status, av.color)

    def _apply_spring(self, sv: Avatar, parent_av: Avatar):
        """Pull subagent toward parent with elastic spring force."""
        px = parent_av.x + parent_av.aw / 2
        py = parent_av.y + parent_av.ah / 2
        sx = sv.x + sv.aw / 2
        sy = sv.y + sv.ah / 2
        dx, dy = px - sx, py - sy
        dist = math.sqrt(dx*dx + dy*dy) or 1.0
        if dist > SPRING_REST:
            force = (dist - SPRING_REST) * SPRING_K * sv._spring_k_mult
            sv.vx += (dx / dist) * force
            sv.vy += (dy / dist) * force
        sv.vx *= sv._spring_damp_v
        sv.vy *= sv._spring_damp_v

    def _draw_elastic(self, parent_av: Avatar, sv: Avatar):
        """Draw a purple zigzag spring line between parent and subagent."""
        x0 = parent_av.x + parent_av.aw / 2
        y0 = parent_av.y + parent_av.ah / 2
        x1 = sv.x + sv.aw / 2
        y1 = sv.y + sv.ah / 2
        dx, dy = x1 - x0, y1 - y0
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < 4:
            return
        # Perpendicular unit vector for zigzag offset
        px_v = -dy / dist;  py_v = dx / dist
        SEGS = 10
        amp  = min(8.0, dist * 0.08)
        pts  = []
        for i in range(SEGS + 1):
            t  = i / SEGS
            mx = x0 + dx * t;  my = y0 + dy * t
            if i == 0 or i == SEGS:
                pts.append((mx, my))
            else:
                sign = 1 if i%2 else -1
                pts.append((mx + px_v*amp*sign, my + py_v*amp*sign))
        for i in range(len(pts)-1):
            self.canvas.create_line(
                pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
                fill="#aa44ff", width=1, tags="elastic")

    # ── HUD status window ─────────────────────────────────────────────

    def _load_bubble_icon(self):
        img_path = Path(__file__).parent / "Sprites" / "bubble.png"
        if not HAS_PIL or not img_path.exists():
            return
        try:
            sheet = Image.open(str(img_path)).convert("RGBA")
            frame = sheet.crop((48, 0, 96, 48))   # row 0 col 1 — idle neutral
            frame = frame.resize((72, 72), Image.NEAREST)
            self._bubble_icon_photo = ImageTk.PhotoImage(frame)
            self._bubble_icon_id = self.canvas.create_image(
                36, 36, image=self._bubble_icon_photo, anchor="center",
                tags="bubble_icon"
            )
            self.canvas.tag_bind("bubble_icon", "<Button-1>",
                                 lambda e: self._show_hud_win())
            self.canvas.tag_bind("bubble_icon", "<Enter>",
                                 lambda e: self.canvas.config(cursor="hand2"))
            self.canvas.tag_bind("bubble_icon", "<Leave>",
                                 lambda e: self.canvas.config(cursor=""))
        except Exception as e:
            print(f"[overlay] bubble icon load failed: {e}")

    def _bring_all_to_front(self):
        for win in [self._hud_win, self._picker, self._config_win]:
            if win and win.winfo_exists():
                win.deiconify()
                win.lift()
                win.focus_force()

    def _setup_tray(self):
        if not HAS_PIL:
            return
        try:
            import pystray
            caine_path = Path(__file__).parent / "Caine_Icon.png"
            if not caine_path.exists():
                caine_path = Path(__file__).parent.parent / "Images" / "Caine_Icon.png"
            if caine_path.exists():
                icon_img = Image.open(str(caine_path)).convert("RGBA").resize((32, 32), Image.NEAREST)
            else:
                icon_img = Image.new("RGBA", (32, 32), (68, 136, 255, 255))
            menu = pystray.Menu(
                pystray.MenuItem("Skins",       lambda icon, item: self.root.after(0, self._open_skin_picker)),
                pystray.MenuItem("Config",      lambda icon, item: self.root.after(0, self._open_config_screen)),
                pystray.MenuItem("Show Status", lambda icon, item: self.root.after(0, self._show_hud_win)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Close",       lambda icon, item: self.root.after(0, self._quit)),
            )
            self._tray = pystray.Icon(
                "AI Overlay", icon_img, "AI Overlay", menu,
                on_activate=lambda icon: self.root.after(0, self._bring_all_to_front),
            )
            threading.Thread(target=self._tray.run, daemon=True).start()
        except Exception as e:
            print(f"[overlay] tray icon failed: {e}")
            self._tray = None

    def _show_hud_win(self):
        if not (self._hud_win and self._hud_win.winfo_exists()):
            self._create_hud_win()
        else:
            self._hud_win.deiconify()
            self._hud_win.lift()
            self._hud_win.attributes("-topmost", True)
            self._hud_win.after(200, lambda: (
                self._hud_win and self._hud_win.winfo_exists() and
                self._hud_win.attributes("-topmost", False)
            ))

    def _create_hud_win(self):
        BG = "#0d0d1a"; FG = "#aaccff"; SEL = "#223366"
        FONT = ("Courier", 10); BFONT = ("Courier", 11, "bold")

        win = tk.Toplevel(self.root)
        win.title("AI Overlay")
        win.overrideredirect(True)
        win.attributes("-topmost", False)      # can go behind other windows
        win.configure(bg=BG)
        win.geometry("340x400+10+10")
        win.resizable(True, True)
        try:
            win.wm_attributes("-alpha", 0.92)
        except Exception:
            pass
        self._hud_win = win

        # Title bar (drag handle)
        title_bar = tk.Frame(win, bg="#111133", pady=6, cursor="fleur")
        title_bar.pack(fill="x")
        tk.Button(title_bar, text="x", command=lambda: win.withdraw(),
                  bg="#111133", fg="#445566",
                  activebackground="#330011", activeforeground="#ff6666",
                  font=("Courier", 10), relief="flat", bd=0,
                  padx=6, pady=0, cursor="hand2"
                  ).pack(side="right", padx=(0, 4))
        tk.Label(title_bar, text="  AI Overlay v0.4", bg="#111133",
                 fg="#88aaff", font=BFONT, anchor="w").pack(side="left")

        # Buttons row
        btn_row = tk.Frame(win, bg=BG, pady=3)
        btn_row.pack(fill="x", padx=8)
        tk.Button(btn_row, text="Skins", command=self._open_skin_picker,
                  bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
                  font=FONT, relief="flat", padx=10, pady=3, cursor="hand2"
                  ).pack(side="left", padx=(0, 4))
        tk.Button(btn_row, text="Config", command=self._open_config_screen,
                  bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
                  font=FONT, relief="flat", padx=10, pady=3, cursor="hand2"
                  ).pack(side="left")

        tk.Frame(win, bg=SEL, height=1).pack(fill="x", padx=8, pady=(4, 0))

        # Status label — updated every tick
        self._hud_status_lbl = tk.Label(win, text="", bg=BG, fg=FG,
                                        font=FONT, anchor="w", justify="left",
                                        padx=10, pady=8)
        self._hud_status_lbl.pack(fill="x")

        tk.Frame(win, height=1, bg="#223366").pack(fill="x", padx=8, pady=(4, 0))
        tk.Label(win, text="HOW TO USE", font=("Consolas", 10, "bold"),
                 fg="#00ffee", bg=BG).pack(anchor="w", padx=12, pady=(6, 0))
        for line in [
            "R-click avatar  →  see bubble menu",
            "Double-click    →  focus terminal",
            "L-drag          →  throw",
            "R-click empty   →  quit",
            "Click avatar + ESC  →  close",
        ]:
            tk.Label(win, text=line, font=("Consolas", 9),
                     fg="#aaccff", bg=BG, justify="left").pack(
                         anchor="w", padx=12, pady=1)

        # Resize grip — bottom-right corner drag
        import tkinter.ttk as ttk
        grip_style = ttk.Style(win)
        grip_style.configure("Dark.TSizegrip", background=BG)
        grip = ttk.Sizegrip(win, style="Dark.TSizegrip")
        grip.pack(side="right", anchor="se")

        # Drag the window by its title bar
        def _drag_start(e):
            self._hud_drag_origin = (e.x_root - win.winfo_x(),
                                     e.y_root - win.winfo_y())
        def _drag_move(e):
            if self._hud_drag_origin:
                ox, oy = self._hud_drag_origin
                win.geometry(f"+{e.x_root - ox}+{e.y_root - oy}")
        def _drag_end(e):
            self._hud_drag_origin = None

        title_bar.bind("<ButtonPress-1>",   _drag_start)
        title_bar.bind("<B1-Motion>",       _drag_move)
        title_bar.bind("<ButtonRelease-1>", _drag_end)
        for child in title_bar.winfo_children():
            child.bind("<ButtonPress-1>",   _drag_start)
            child.bind("<B1-Motion>",       _drag_move)
            child.bind("<ButtonRelease-1>", _drag_end)

    def _update_hud_win(self, agents):
        if not (self._hud_win and self._hud_win.winfo_exists()):
            return
        rows, _ = _hud_status_text(agents)
        self._hud_status_lbl.config(text="\n".join(text for text, _ in rows))

    # ── Left-click drag ───────────────────────────────────────────────

    def _on_left_press(self, event):
        # Click on any bubble sub-agent → dismiss it immediately
        all_subs = (
            [sv for sl in self.sub_avatars.values() for sv in sl]
            + list(self._lingering_subs)
        )
        for sv in all_subs:
            if sv.x <= event.x <= sv.x + sv.aw and sv.y <= event.y <= sv.y + sv.ah:
                sv._floating_away = True
                sv._float_frames  = 0
                # Record the dismissal so the spawn loop doesn't immediately recreate it
                parent_aid = sv.agent.agent_id.split("_sub_")[0]
                self._dismissed_subs[parent_aid] = self._dismissed_subs.get(parent_aid, 0) + 1
                return
        for av in list(self.avatars.values()):
            if av.x <= event.x <= av.x + av.aw and av.y <= event.y <= av.y + av.ah:
                self._drag_av   = av
                self._drag_off  = (int(event.x - av.x), int(event.y - av.y))
                self._drag_prev = (event.x, event.y)
                self._glitches.append(GlitchFlash(
                    self.canvas, int(av.x), int(av.y), av.aw, av.ah, pink=True))
                return

    def _on_left_drag(self, event):
        av = self._drag_av
        if av is None:
            return
        nx = event.x - self._drag_off[0]
        ny = event.y - self._drag_off[1]
        nx = max(0, min(nx, self.sw - av.aw))
        ny = max(0, min(ny, self.sh - av.ah))
        av.x = float(nx)
        av.y = float(ny)
        self._drag_prev = (event.x, event.y)

    def _on_left_release(self, event):
        av = self._drag_av
        if av is None:
            return
        dx = event.x - self._drag_prev[0]
        dy = event.y - self._drag_prev[1]
        max_v = WALK_SPEED * 3
        av.vx = max(-max_v, min(dx * THROW_SCALE, max_v))
        av.vy = max(-max_v, min(dy * THROW_SCALE, max_v))
        self._drag_av = None

    def _on_double_click(self, event):
        self._drag_av = None  # cancel drag started by the first click
        for av in list(self.avatars.values()):
            if av.x <= event.x <= av.x + av.aw and av.y <= event.y <= av.y + av.ah:
                self._focus_linked_console(av.agent.pid)
                return

    # ── Right-click ───────────────────────────────────────────────────

    def _quit(self):
        if getattr(self, "_tray", None):
            try: self._tray.stop()
            except Exception: pass
        self.root.quit()

    def _on_right_click(self, event):
        for av in list(self.avatars.values()) + [sv for sl in self.sub_avatars.values() for sv in sl]:
            if av.x <= event.x <= av.x+av.aw and av.y <= event.y <= av.y+av.ah:
                self._glitches.append(GlitchFlash(
                    self.canvas, int(av.x), int(av.y), av.aw, av.ah, pink=False))
                self._focus_linked_console(av.agent.pid)
                return
        self._quit()

    def _focus_console(self):
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 5)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception as e:
            print(f"[overlay] focus_console: {e}")

    def _focus_linked_console(self, pid: int):
        try:
            import os, ctypes.wintypes
            candidates: set[int] = set()
            has_vscode = False

            seed = pid if pid else os.getpid()

            # Try psutil first; fall back to ctypes CreateToolhelp32Snapshot
            try:
                import psutil
                try:
                    p = psutil.Process(seed)
                    for _ in range(12):
                        candidates.add(p.pid)
                        if 'code' in (p.name() or '').lower():
                            has_vscode = True
                        p = p.parent()
                        if p is None:
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                if has_vscode:
                    for proc in psutil.process_iter(['pid', 'name']):
                        if (proc.info['name'] or '').lower() == 'code.exe':
                            candidates.add(proc.info['pid'])
            except ImportError:
                # ctypes fallback: walk parent chain via CreateToolhelp32Snapshot
                class PROCESSENTRY32(ctypes.Structure):
                    _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
                                 ("th32ProcessID", ctypes.c_ulong), ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                                 ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
                                 ("th32ParentProcessID", ctypes.c_ulong), ("pcPriClassBase", ctypes.c_long),
                                 ("dwFlags", ctypes.c_ulong), ("szExeFile", ctypes.c_char * 260)]
                snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(0x2, 0)
                parents, names = {}, {}
                e = PROCESSENTRY32(); e.dwSize = ctypes.sizeof(PROCESSENTRY32)
                if ctypes.windll.kernel32.Process32First(snap, ctypes.byref(e)):
                    while True:
                        parents[e.th32ProcessID] = e.th32ParentProcessID
                        names[e.th32ProcessID] = e.szExeFile.decode('utf-8', errors='ignore').lower()
                        if not ctypes.windll.kernel32.Process32Next(snap, ctypes.byref(e)):
                            break
                ctypes.windll.kernel32.CloseHandle(snap)
                p = seed
                for _ in range(12):
                    if p not in parents: break
                    candidates.add(p)
                    if 'code' in names.get(p, ''): has_vscode = True
                    p = parents[p]

            found_hwnd: list = []
            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

            def _cb(hwnd, _):
                wpid = ctypes.c_ulong(0)
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                if wpid.value in candidates and ctypes.windll.user32.IsWindowVisible(hwnd):
                    if ctypes.windll.user32.GetWindowTextLengthW(hwnd) > 0:
                        found_hwnd.append(hwnd)
                return True

            ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)

            if found_hwnd:
                hwnd = found_hwnd[0]
                if ctypes.windll.user32.IsIconic(hwnd):
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE only if minimized
                # AttachThreadInput bypasses Windows foreground-stealing prevention
                cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
                tgt_thread = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
                ctypes.windll.user32.AttachThreadInput(cur_thread, tgt_thread, True)
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.AttachThreadInput(cur_thread, tgt_thread, False)
        except Exception:
            pass

    # ── Skin picker ───────────────────────────────────────────────────

    def _open_skin_picker(self):
        if self._picker and self._picker.winfo_exists():
            self._picker.lift(); return
        win = tk.Toplevel(self.root)
        win.title("Avatar Skins")
        win.geometry("300x440+80+80")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.configure(bg="#0d0d1a")
        self._picker = win
        self._build_picker_ui(win)

    def _build_picker_ui(self, win):
        BG  = "#0d0d1a"; FG = "#aaccff"; SEL = "#223366"; FONT = ("Courier",9)

        agents    = self.scanner.get_agents()
        agent_ids = list(agents.keys())
        labels    = [f"{a.name} {'[D]' if a.is_demo else '[R]'}" for a in agents.values()]
        lbl_to_id = dict(zip(labels, agent_ids))

        top = tk.Frame(win, bg=BG, pady=6)
        top.pack(fill="x", padx=10)
        tk.Label(top, text="Agent:", bg=BG, fg=FG, font=FONT).pack(side="left")

        sel_agent = tk.StringVar(win, value=labels[0] if labels else "")
        if labels:
            m = tk.OptionMenu(top, sel_agent, *labels)
            m.config(bg=SEL,fg=FG,activebackground="#334477",activeforeground="white",
                     font=FONT,highlightthickness=0,bd=0)
            m["menu"].config(bg=SEL,fg=FG,font=FONT)
            m.pack(side="left",padx=6)

        # ── Scale slider ──────────────────────────────────────────
        tk.Frame(win, bg="#223366", height=1).pack(fill="x", padx=10, pady=(6,2))
        sc_row = tk.Frame(win, bg=BG, pady=3)
        sc_row.pack(fill="x", padx=10)
        tk.Label(sc_row, text="Scale:", bg=BG, fg=FG, font=FONT).pack(side="left")
        _sc_lbl = tk.Label(sc_row, text=f"{AVATAR_SCALE:.1f}×",
                           bg=BG, fg="#44ff88", font=FONT, width=4)
        _sc_lbl.pack(side="right")
        def _on_scale(val):
            global AVATAR_SCALE
            AVATAR_SCALE = round(float(val) * 2) / 2   # snap to 0.5 steps
            _sc_lbl.config(text=f"{AVATAR_SCALE:.1f}×")
            if REGISTRY:
                REGISTRY.reload_all(AVATAR_SCALE)
        tk.Scale(sc_row, from_=0.5, to=4.0, resolution=0.5, orient="horizontal",
                 command=_on_scale, bg=BG, fg=FG, troughcolor="#223366",
                 highlightthickness=0, showvalue=False, length=140,
                 ).pack(side="left", padx=6)
        tk.Frame(win, bg="#223366", height=1).pack(fill="x", padx=10, pady=(2,4))

        # ── Hue shift slider ──────────────────────────────────────────
        hue_row = tk.Frame(win, bg=BG, pady=3)
        hue_row.pack(fill="x", padx=10)
        tk.Label(hue_row, text="Hue shift:", bg=BG, fg=FG, font=FONT).pack(side="left")
        _hue_lbl = tk.Label(hue_row, text="0°", bg=BG, fg="#44ff88", font=FONT, width=5)
        _hue_lbl.pack(side="right")
        hue_var = tk.IntVar(win, value=0)
        def _on_hue(val):
            _hue_lbl.config(text=f"{int(float(val))}°")
            _update_preview()
        tk.Scale(hue_row, variable=hue_var, from_=0, to=359, resolution=1,
                 orient="horizontal", bg=BG, fg=FG, troughcolor="#223366",
                 highlightthickness=0, showvalue=False, length=140,
                 command=_on_hue).pack(side="left", padx=6)

        # ── Hue preview ───────────────────────────────────────────────
        preview_row = tk.Frame(win, bg=BG)
        preview_row.pack(fill="x", padx=10, pady=(4, 2))
        _preview_canvas = tk.Canvas(preview_row, width=64, height=64, bg="#111122",
                                    highlightthickness=1, highlightbackground="#223366")
        _preview_canvas.pack(side="left")
        _preview_lbl = tk.Label(preview_row, text="— no skin —", bg=BG,
                                fg="#556677", font=FONT, anchor="w", justify="left")
        _preview_lbl.pack(side="left", padx=(10, 0))
        _preview_photo: list = [None]

        def _update_preview():
            sn  = sel_skin.get()
            hue = hue_var.get()
            if not REGISTRY or not sn or not REGISTRY.has(sn):
                return
            with REGISTRY._lock:
                sheet = REGISTRY._sheets.get(sn)
            if not sheet or not sheet._frames or not sheet._frames[0]:
                return
            frame = sheet._frames[0][0]
            if hue != 0 and HAS_SPRITES:
                frame = hue_rotate_image(frame, float(hue))
            size = 64
            thumb = frame.resize((size, size), Image.NEAREST)
            _preview_photo[0] = ImageTk.PhotoImage(thumb)
            _preview_canvas.delete("all")
            _preview_canvas.create_image(size // 2, size // 2,
                                         image=_preview_photo[0], anchor="center")
            _preview_lbl.config(text=f"{sn}\nhue {hue}°", fg=FG)

        tk.Frame(win, bg="#223366", height=1).pack(fill="x", padx=10, pady=(4, 4))

        tk.Label(win, text="  Choose skin:", bg=BG, fg=FG, font=FONT, anchor="w"
                 ).pack(fill="x",padx=10,pady=(4,0))

        # Apply button and separator packed at bottom BEFORE the expanding skin list
        # so they are always visible regardless of how many skins are loaded.
        def _apply():
            aid  = lbl_to_id.get(sel_agent.get())
            base = sel_skin.get()
            hue  = hue_var.get()
            if aid and base:
                if hue != 0:
                    variant = f"{base}_h{hue}"
                    if REGISTRY and not REGISTRY.has(variant):
                        REGISTRY.load_hue_variant(variant, base, float(hue))
                    skin = variant
                else:
                    skin = base
                self._apply_skin(aid, skin)
                btn.config(text="Applied!", fg="#44ff88")
                win.after(1200, lambda: btn.config(text="Apply", fg=FG))

        btn = tk.Button(win, text="Apply", command=_apply,
            bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
            font=("Courier",10,"bold"), relief="flat", padx=14, pady=5, cursor="hand2")
        btn.pack(side="bottom", pady=8)
        tk.Frame(win, bg="#223366", height=1).pack(side="bottom", fill="x", padx=10, pady=2)

        scroll_outer = tk.Frame(win, bg=BG)
        scroll_outer.pack(fill="both", expand=True, padx=10, pady=4)

        sb = tk.Scrollbar(scroll_outer, orient="vertical", bg="#223366",
                          troughcolor=BG, highlightthickness=0, bd=0)
        sb.pack(side="right", fill="y")

        sc = tk.Canvas(scroll_outer, bg=BG, highlightthickness=0, yscrollcommand=sb.set)
        sc.pack(side="left", fill="both", expand=True)
        sb.config(command=sc.yview)

        sf = tk.Frame(sc, bg=BG)
        sf_id = sc.create_window((0, 0), window=sf, anchor="nw")

        def _on_inner_configure(e):
            sc.configure(scrollregion=sc.bbox("all"))
        def _on_canvas_configure(e):
            sc.itemconfig(sf_id, width=e.width)
        sf.bind("<Configure>", _on_inner_configure)
        sc.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(e):
            sc.yview_scroll(int(-1 * (e.delta / 120)), "units")

        sel_skin = tk.StringVar(win, value="meowatar")
        row_frames: dict[str,tk.Frame] = {}
        photos: list = []

        raw_names  = REGISTRY.list_sheets() if REGISTRY else []
        skin_names = [sn for sn in raw_names
                      if sn != "bubble"
                      and not (sn.startswith("amongo_h") and sn[8:].isdigit())]
        if not skin_names:
            tk.Label(sf, text="No skins loaded.", bg=BG, fg="#556677", font=FONT).pack(anchor="w")
        else:
            for sn in skin_names:
                row = tk.Frame(sf, bg=BG, cursor="hand2", pady=3)
                row.pack(fill="x")
                row_frames[sn] = row
                pc = tk.Canvas(row, width=48, height=48, bg=BG,
                               highlightthickness=1, highlightbackground="#223366")
                pc.pack(side="left", padx=(0,8))
                if REGISTRY:
                    ph = REGISTRY.get_thumbnail(sn, 48)
                    if ph: photos.append(ph); pc.create_image(24,24,image=ph,anchor="center")
                tk.Label(row,text=sn,bg=BG,fg=FG,font=("Courier",10,"bold"),anchor="w").pack(side="left")

        win._photos = photos

        for w in (sc, sf):
            w.bind("<MouseWheel>", _on_mousewheel)

        def _select(sn):
            sel_skin.set(sn)
            _update_preview()
            for n,f in row_frames.items():
                c = SEL if n==sn else BG
                f.config(bg=c)
                for ch in f.winfo_children():
                    try: ch.config(bg=c)
                    except Exception: pass

        for sn, row in row_frames.items():
            row.bind("<Button-1>", lambda e,s=sn: _select(s))
            row.bind("<MouseWheel>", _on_mousewheel)
            for ch in row.winfo_children():
                ch.bind("<Button-1>", lambda e,s=sn: _select(s))
                ch.bind("<MouseWheel>", _on_mousewheel)

        if agent_ids:
            _select(agents[agent_ids[0]].skin)

        def _on_agent_change(*_):
            aid = lbl_to_id.get(sel_agent.get())
            if aid and aid in agents: _select(agents[aid].skin)
        sel_agent.trace("w", _on_agent_change)

    def _apply_skin(self, agent_id, skin):
        with self.scanner._lock:
            if agent_id in self.scanner._agents:
                self.scanner._agents[agent_id].skin = skin

    # ── Config screen ─────────────────────────────────────────────────────────

    def _open_config_screen(self):
        if self._config_win and self._config_win.winfo_exists():
            self._config_win.lift(); return
        win = tk.Toplevel(self.root)
        win.title("Overlay Config")
        win.geometry("340x460+300+80")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.configure(bg="#0d0d1a")
        self._config_win = win
        self._build_config_ui(win)

    def _build_config_ui(self, win):
        BG = "#0d0d1a"; FG = "#aaccff"; SEL = "#223366"
        FONT = ("Courier", 9); BFONT = ("Courier", 9, "bold")

        style = ttk.Style(win)
        style.theme_use("default")
        style.configure("Dark.TNotebook",        background=BG, borderwidth=0)
        style.configure("Dark.TNotebook.Tab",    background=SEL, foreground=FG,
                        font=FONT, padding=[8, 3])
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", "#334477")],
                  foreground=[("selected", "white")])
        style.configure("Dark.TFrame", background=BG)

        nb = ttk.Notebook(win, style="Dark.TNotebook")
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        def tab(label):
            f = ttk.Frame(nb, style="Dark.TFrame")
            nb.add(f, text=label)
            return f

        def row(parent, label, widget_fn, pady=3):
            r = tk.Frame(parent, bg=BG, pady=pady)
            r.pack(fill="x", padx=12)
            tk.Label(r, text=label, bg=BG, fg=FG, font=FONT,
                     width=18, anchor="w").pack(side="left")
            widget_fn(r)

        def slider(parent, var, lo, hi, res=0.01):
            tk.Scale(parent, variable=var, from_=lo, to=hi, resolution=res,
                     orient="horizontal", bg=BG, fg=FG, troughcolor=SEL,
                     highlightthickness=0, showvalue=True, length=150,
                     font=("Courier", 7)).pack(side="left")

        def spinbox(parent, var, lo, hi, inc=1):
            tk.Spinbox(parent, textvariable=var, from_=lo, to=hi, increment=inc,
                       bg=SEL, fg=FG, insertbackground=FG, font=FONT,
                       width=6, relief="flat").pack(side="left")

        # ── Tab 1: Physics ────────────────────────────────────────────
        tp = tab(" Physics ")
        tk.Label(tp, text="", bg=BG).pack(pady=4)

        v_grav  = tk.DoubleVar(win, GRAVITY)
        v_walk  = tk.DoubleVar(win, WALK_SPEED)
        v_jump  = tk.DoubleVar(win, JUMP_VEL)
        v_srest = tk.IntVar(win,    SPRING_REST)
        v_sk    = tk.DoubleVar(win, SPRING_K)
        v_sd    = tk.DoubleVar(win, SPRING_DAMP)

        row(tp, "Gravity",        lambda p: slider(p, v_grav, 0.1, 1.5))
        row(tp, "Walk speed",     lambda p: slider(p, v_walk, 0.5, 4.0))
        row(tp, "Jump velocity",  lambda p: slider(p, v_jump, -15.0, -3.0))
        row(tp, "Spring rest px", lambda p: spinbox(p, v_srest, 20, 200, 5))
        row(tp, "Spring K",       lambda p: slider(p, v_sk, 0.01, 0.15, 0.005))
        row(tp, "Spring damping", lambda p: slider(p, v_sd, 0.80, 0.99, 0.01))

        # ── Tab 2: Display ────────────────────────────────────────────
        td = tab(" Display ")
        tk.Label(td, text="", bg=BG).pack(pady=4)

        v_scale = tk.DoubleVar(win, AVATAR_SCALE)
        v_fps   = tk.StringVar(win, str(OVERLAY_FPS))

        def _on_scale_cfg(val):
            global AVATAR_SCALE
            AVATAR_SCALE = round(float(val) * 2) / 2
            v_scale.set(AVATAR_SCALE)
            if REGISTRY:
                REGISTRY.reload_all(AVATAR_SCALE)

        def scale_widget(parent):
            tk.Scale(parent, variable=v_scale, from_=0.5, to=4.0, resolution=0.5,
                     orient="horizontal", bg=BG, fg=FG, troughcolor=SEL,
                     highlightthickness=0, showvalue=True, length=150,
                     font=("Courier", 7), command=_on_scale_cfg).pack(side="left")

        def fps_widget(parent):
            om = tk.OptionMenu(parent, v_fps, "10", "20", "30", "60")
            om.config(bg=SEL, fg=FG, activebackground="#334477",
                      activeforeground="white", font=FONT,
                      highlightthickness=0, bd=0)
            om["menu"].config(bg=SEL, fg=FG, font=FONT)
            om.pack(side="left")

        row(td, "Avatar scale",  scale_widget)
        row(td, "Overlay FPS",   fps_widget)

        v_flalpha = tk.DoubleVar(win, FLOOR_LINE_ALPHA)
        v_walpha  = tk.DoubleVar(win, OVERLAY_ALPHA)

        def _on_floor_alpha(val):
            global FLOOR_LINE_ALPHA
            FLOOR_LINE_ALPHA = float(val)

        def _on_win_alpha(val):
            global OVERLAY_ALPHA
            OVERLAY_ALPHA = float(val)
            self.root.wm_attributes("-alpha", OVERLAY_ALPHA)

        row(td, "Floor line opacity",
            lambda p: tk.Scale(p, variable=v_flalpha, from_=0.0, to=1.0, resolution=0.05,
                               orient="horizontal", bg=BG, fg=FG, troughcolor=SEL,
                               highlightthickness=0, showvalue=True, length=150,
                               font=("Courier", 7), command=_on_floor_alpha).pack(side="left"))

        row(td, "Overlay opacity",
            lambda p: tk.Scale(p, variable=v_walpha, from_=0.1, to=1.0, resolution=0.05,
                               orient="horizontal", bg=BG, fg=FG, troughcolor=SEL,
                               highlightthickness=0, showvalue=True, length=150,
                               font=("Courier", 7), command=_on_win_alpha).pack(side="left"))

        tk.Frame(td, bg="#223366", height=1).pack(fill="x", padx=12, pady=(10, 4))

        def _rescan_floors():
            self.terrain._scan()
            rescan_btn.config(text="Rescanned!", fg="#44ff88")
            win.after(1200, lambda: rescan_btn.config(text="Rescan Floors & Walls", fg=FG))

        rescan_btn = tk.Button(td, text="Rescan Floors & Walls", command=_rescan_floors,
            bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
            font=FONT, relief="flat", padx=10, pady=4, cursor="hand2")
        rescan_btn.pack(pady=6)

        # ── Tab 3: Behavior ───────────────────────────────────────────
        tb = tab(" Behavior ")
        tk.Label(tb, text="", bg=BG).pack(pady=4)

        v_sscan  = tk.DoubleVar(win, SESSION_SCAN_RATE)
        v_wscan  = tk.DoubleVar(win, WINDOW_SCAN_RATE)
        v_tsub   = tk.IntVar(win,   TEST_SUBAGENTS)
        v_idlelo = tk.IntVar(win,   30)
        v_idlehi = tk.IntVar(win,   90)

        row(tb, "Session scan s", lambda p: slider(p, v_sscan, 0.5, 10.0, 0.5))
        row(tb, "Window scan s",  lambda p: slider(p, v_wscan, 0.1, 2.0,  0.1))
        row(tb, "Test subagents", lambda p: spinbox(p, v_tsub, 0, 8))
        row(tb, "Idle min frames",lambda p: spinbox(p, v_idlelo, 5, 200, 5))
        row(tb, "Idle max frames",lambda p: spinbox(p, v_idlehi, 5, 200, 5))

        # ── Apply button ──────────────────────────────────────────────
        tk.Frame(win, bg="#223366", height=1).pack(fill="x", padx=10, pady=4)

        def _apply_all():
            global GRAVITY, WALK_SPEED, JUMP_VEL, SPRING_REST
            global SPRING_K, SPRING_DAMP, OVERLAY_FPS
            global SESSION_SCAN_RATE, WINDOW_SCAN_RATE, TEST_SUBAGENTS
            GRAVITY           = v_grav.get()
            WALK_SPEED        = v_walk.get()
            JUMP_VEL          = v_jump.get()
            SPRING_REST       = v_srest.get()
            SPRING_K          = v_sk.get()
            SPRING_DAMP       = v_sd.get()
            OVERLAY_FPS       = int(v_fps.get())
            SESSION_SCAN_RATE = v_sscan.get()
            WINDOW_SCAN_RATE  = v_wscan.get()
            TEST_SUBAGENTS    = v_tsub.get()
            apply_btn.config(text="✓ Applied!", fg="#44ff88")
            win.after(1200, lambda: apply_btn.config(text="Apply", fg=FG))

        apply_btn = tk.Button(win, text="Apply", command=_apply_all,
            bg=SEL, fg=FG, activebackground="#334477", activeforeground="white",
            font=BFONT, relief="flat", padx=14, pady=5, cursor="hand2")
        apply_btn.pack(pady=6)

    def run(self):
        print(f"[AI Overlay v0.4] {self.sw}x{self.sh} @ {OVERLAY_FPS}fps")
        print("[AI Overlay] Drag HUD | R-Click avatar=terminal | R-Click empty=quit | ESC=quit")
        self.root.mainloop()


if __name__ == "__main__":
    app = OverlayApp()
    app.run()
