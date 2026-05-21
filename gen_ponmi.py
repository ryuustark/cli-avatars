#!/usr/bin/env python3
"""
gen_ponmi.py — Generate Ponmi (jester art director) sprite sheet.

Design: Based on Pomni from The Amazing Digital Circus.
Sheet : 336×144 px | 7 cols × 3 rows | 48×48 cells | RGBA PNG

Rows  : DOWN (facing viewer) | UP (back) | RIGHT (profile, left = runtime flip)
Cols  : walk1 | idle | walk3 | type1 | type2 | read1 | read2

Outputs
  char_ponmi.png          → PixelCircus characters folder
  char_ponmi_overlay.png  → cli_avatars Sprites folder
  ponmi_preview/          → animated GIFs per animation

Usage
  python gen_ponmi.py           # generate + save
  python gen_ponmi.py --view    # also open each GIF in default viewer
"""
import os, sys
from pathlib import Path
from PIL import Image

# ── Constants ─────────────────────────────────────────────────────────────────
CELL   = 48
COLS   = 7
ROWS   = 3

OUTPUT_PIXELCIRCUS = (
    Path(__file__).parent.parent /
    "zz_PixelCircus/webview-ui/public/assets/characters/char_ponmi.png"
)
OUTPUT_OVERLAY = Path(__file__).parent / "Sprites/ponmi.png"
OUTPUT_GIF_DIR = Path(__file__).parent / "ponmi_preview"

# ── Palette ───────────────────────────────────────────────────────────────────
T    = (  0,  0,  0,   0)   # transparent
K    = ( 22, 22, 22, 255)   # near-black outline
SKN  = (244, 220, 202, 255)  # pale face / skin
HR   = (138,  68,  18, 255)  # auburn hair
RED  = (202,  48,  48, 255)  # jester red
BLU  = ( 62,  98, 202, 255)  # jester blue
YEL  = (254, 200,   0, 255)  # yellow trim / buttons / boots
GLD  = (192, 158,  42, 255)  # gold bells
EWH  = (236, 236, 236, 255)  # eye white
ERD  = (202,  48,  48, 255)  # eye X red
EBL  = ( 62,  98, 202, 255)  # eye iris blue
LMB  = (228, 226, 214, 255)  # limb off-white
MTH  = (172, 134, 124, 255)  # mouth line
CLP  = (196, 196, 196, 255)  # clipboard grey
CLK  = (136, 136, 136, 255)  # clipboard dark
PNKL = (240, 180, 180, 255)  # pencil pink (art director prop)
PNKD = ( 80,  40,  10, 255)  # pencil dark tip

# ── Pixel helpers ─────────────────────────────────────────────────────────────
def p(img, x, y, c):
    if 0 <= x < CELL and 0 <= y < CELL:
        img.putpixel((x, y), c)

def hl(img, y, x0, x1, c):
    for x in range(x0, x1 + 1):
        p(img, x, y, c)

def vl(img, x, y0, y1, c):
    for y in range(y0, y1 + 1):
        p(img, x, y, c)

def bk(img, x0, y0, x1, y1, c):
    for y in range(y0, y1 + 1):
        hl(img, y, x0, x1, c)


# ── Body part drawers ─────────────────────────────────────────────────────────

def hat_front(img, cx):
    """Jester hat, front view. Hat occupies y=0..7."""
    # Hat body: two halves, y=4..7
    bk(img, cx - 11, 4, cx - 1,  7, RED)
    bk(img, cx,      4, cx + 10, 7, BLU)
    hl(img, 4, cx - 11, cx + 10, YEL)  # top trim
    hl(img, 7, cx - 11, cx + 10, YEL)  # brim trim

    # LEFT point (red, upper-left) — tip at (cx-9, 0)
    for i, (dx, w) in enumerate([(0,1),(0,2),(1,3),(2,4),(2,5)]):
        hl(img, i, cx - 9 - dx, cx - 9 - dx + w - 1, RED)
    p(img, cx - 9, 0, GLD)  # bell

    # RIGHT point (blue, upper-right) — mirror
    for i, (dx, w) in enumerate([(0,1),(0,2),(1,3),(2,4),(2,5)]):
        hl(img, i, cx + 9 + dx - w + 1, cx + 9 + dx, BLU)
    p(img, cx + 9, 0, GLD)  # bell

    # CENTER front point (tallest) — half red / half blue
    for i, half in enumerate([1, 1, 2, 2, 2]):
        if i < 4:
            hl(img, i, cx - half, cx - 1, RED)
            hl(img, i, cx,        cx + half - 1, BLU)

    # Outline corners of brim
    p(img, cx - 12, 5, K); p(img, cx + 11, 5, K)
    p(img, cx - 12, 7, K); p(img, cx + 11, 7, K)


def hat_back(img, cx):
    """Hat, back view — shows two rear points + flat brim from behind."""
    bk(img, cx - 11, 4, cx - 1,  7, BLU)   # mirrored sides from back
    bk(img, cx,      4, cx + 10, 7, RED)
    hl(img, 4, cx - 11, cx + 10, YEL)
    hl(img, 7, cx - 11, cx + 10, YEL)

    # Back-left point (blue from this view)
    for i, (dx, w) in enumerate([(0,1),(0,2),(1,3),(2,4)]):
        hl(img, i, cx - 9 - dx, cx - 9 - dx + w - 1, BLU)
    p(img, cx - 9, 0, GLD)

    # Back-right point (red from this view)
    for i, (dx, w) in enumerate([(0,1),(0,2),(1,3),(2,4)]):
        hl(img, i, cx + 9 + dx - w + 1, cx + 9 + dx, RED)
    p(img, cx + 9, 0, GLD)


def hat_side(img, cx):
    """Hat, right-profile view — one point forward, one back, brim edge."""
    bk(img, cx - 8, 4, cx + 8, 7, RED)     # side shows mostly one colour
    hl(img, 4, cx - 8, cx + 8, YEL)
    hl(img, 7, cx - 8, cx + 8, YEL)

    # Forward point (blue tipped)
    for i, (dx, w) in enumerate([(0,1),(0,2),(1,3),(1,4)]):
        hl(img, i, cx + 6 + dx - w + 1, cx + 6 + dx, BLU)
    p(img, cx + 6, 0, GLD)

    # Back point (red)
    for i, (dx, w) in enumerate([(0,1),(0,2),(1,3)]):
        hl(img, i, cx - 7 - dx, cx - 7 - dx + w - 1, RED)
    p(img, cx - 7, 0, GLD)


def eye_front(img, ex, ey):
    """One eye, front view, 4×4 px. White bg, blue ring, red X."""
    bk(img, ex, ey, ex + 3, ey + 3, EWH)
    hl(img, ey,     ex, ex + 3, EBL)
    hl(img, ey + 3, ex, ex + 3, EBL)
    vl(img, ex,     ey, ey + 3, EBL)
    vl(img, ex + 3, ey, ey + 3, EBL)
    p(img, ex + 1, ey + 1, ERD)
    p(img, ex + 2, ey + 1, ERD)
    p(img, ex + 1, ey + 2, ERD)
    p(img, ex + 2, ey + 2, ERD)


def head_front(img, cx, ht):
    """Head + face, front view. ht = y of top of head. Head is 12 wide × 8 tall."""
    hb  = ht + 7
    hx0 = cx - 6
    hx1 = cx + 5
    bk(img, hx0, ht, hx1, hb, SKN)
    hl(img, ht - 1, hx0,     hx1,     K)
    hl(img, hb + 1, hx0,     hx1,     K)
    vl(img, hx0 - 1, ht,     hb,      K)
    vl(img, hx1 + 1, ht,     hb,      K)
    # eyes
    eye_front(img, cx - 5, ht + 1)
    eye_front(img, cx + 1, ht + 1)
    # mouth
    hl(img, hb - 1, cx - 1, cx + 1, MTH)


def head_back(img, cx, ht):
    """Head, back view — no face, just hair colour with beret edge."""
    bk(img, cx - 6, ht, cx + 5, ht + 7, HR)
    hl(img, ht - 1, cx - 6, cx + 5, K)
    hl(img, ht + 8, cx - 6, cx + 5, K)
    vl(img, cx - 7, ht, ht + 7, K)
    vl(img, cx + 6, ht, ht + 7, K)
    # 2-px auburn hair tuft below hat brim
    hl(img, ht,     cx - 3, cx + 2, HR)
    hl(img, ht + 1, cx - 4, cx + 3, HR)


def head_side(img, cx, ht):
    """Head, right-profile view — one eye visible on right side."""
    bk(img, cx - 5, ht, cx + 4, ht + 7, SKN)
    hl(img, ht - 1, cx - 5, cx + 4, K)
    hl(img, ht + 8, cx - 5, cx + 4, K)
    vl(img, cx - 6, ht, ht + 7, K)
    vl(img, cx + 5, ht, ht + 7, K)
    # single eye on right side
    eye_front(img, cx + 1, ht + 1)
    hl(img, ht + 6, cx - 1, cx + 1, MTH)


def pigtails_front(img, cx, ht, pb):
    """Pigtails alongside body, front view. ht=head top, pb=pigtail bottom."""
    # Left pigtail (x=cx-8, cx-7)
    for y in range(ht + 2, pb + 1):
        p(img, cx - 8, y, HR)
        if y < pb - 2:
            p(img, cx - 7, y, HR)
    # Right pigtail
    for y in range(ht + 2, pb + 1):
        p(img, cx + 7, y, HR)
        if y < pb - 2:
            p(img, cx + 6, y, HR)


def pigtails_back(img, cx, ht, pb):
    """Pigtails from back — more visible, 3px wide each."""
    for y in range(ht + 1, pb + 1):
        for dx in [-8, -7, -6]:
            p(img, cx + dx, y, HR)
        for dx in [5, 6, 7]:
            p(img, cx + dx, y, HR)


def pigtails_side(img, cx, ht, pb):
    """Pigtails from side — only left pigtail visible as one strip."""
    for y in range(ht + 2, pb + 1):
        p(img, cx - 7, y, HR)
        if y < pb - 2:
            p(img, cx - 6, y, HR)


def neck(img, cx, y0, y1):
    bk(img, cx - 1, y0, cx + 1, y1, SKN)


def torso_front(img, cx, y0, y1):
    """Torso: red left half, blue right half, 3 yellow buttons at centre seam."""
    bk(img, cx - 8, y0, cx - 1, y1, RED)
    bk(img, cx,     y0, cx + 7, y1, BLU)
    vl(img, cx - 9, y0, y1, K)
    vl(img, cx + 8, y0, y1, K)
    hl(img, y0 - 1, cx - 8, cx + 7, K)
    hl(img, y1 + 1, cx - 8, cx + 7, K)
    mid = (y0 + y1) // 2
    for by in [y0 + 1, mid, y1 - 1]:
        p(img, cx - 1, by, YEL)
        p(img, cx,     by, YEL)


def torso_back(img, cx, y0, y1):
    """Torso from back — colours flip."""
    bk(img, cx - 8, y0, cx - 1, y1, BLU)
    bk(img, cx,     y0, cx + 7, y1, RED)
    vl(img, cx - 9, y0, y1, K)
    vl(img, cx + 8, y0, y1, K)
    hl(img, y0 - 1, cx - 8, cx + 7, K)
    hl(img, y1 + 1, cx - 8, cx + 7, K)


def torso_side(img, cx, y0, y1):
    """Torso from right side — all red."""
    bk(img, cx - 5, y0, cx + 4, y1, RED)
    vl(img, cx - 6, y0, y1, K)
    vl(img, cx + 5, y0, y1, K)
    hl(img, y0 - 1, cx - 5, cx + 4, K)
    hl(img, y1 + 1, cx - 5, cx + 4, K)
    p(img, cx + 4, (y0 + y1) // 2, K)  # edge shading hint


def hips(img, cx, y0, y1, flip=False):
    c0, c1 = (BLU, RED) if flip else (RED, BLU)
    bk(img, cx - 6, y0, cx - 1, y1, c0)
    bk(img, cx,     y0, cx + 5, y1, c1)


def arm(img, ax, ay_top, ay_bot, cuff_w=2):
    """Single arm: off-white strip + yellow cuff at bottom."""
    vl(img, ax,     ay_top, ay_bot - 3, LMB)
    vl(img, ax + 1, ay_top, ay_bot - 3, LMB)
    bk(img, ax - 1, ay_bot - 2, ax + 2, ay_bot, YEL)
    p(img, ax - 1, ay_bot - 2, K)
    p(img, ax + 2, ay_bot - 2, K)


def leg(img, lx, ly_top, boot_top, ly_bot):
    """Single leg: off-white strip + yellow boot."""
    vl(img, lx,     ly_top, boot_top - 1, LMB)
    vl(img, lx + 1, ly_top, boot_top - 1, LMB)
    bk(img, lx - 1, boot_top, lx + 2, ly_bot, YEL)
    hl(img, ly_bot, lx - 1, lx + 2, GLD)  # sole
    p(img, lx - 1, boot_top, K)
    p(img, lx + 2, boot_top, K)


def pencil_h(img, px0, py, length, angle_right=True):
    """Horizontal-ish pencil prop."""
    c = PNKL
    for i in range(length):
        p(img, px0 + i, py + (i // 4 if angle_right else -(i // 4)), c)
    p(img, px0, py, PNKD)   # dark tip


def clipboard(img, cx, cy, w=8, h=6):
    """Clipboard prop centered at cx,cy."""
    bk(img, cx - w//2, cy, cx + w//2, cy + h, CLP)
    hl(img, cy,     cx - w//2, cx + w//2, CLK)
    hl(img, cy + h, cx - w//2, cx + w//2, CLK)
    vl(img, cx - w//2, cy, cy + h, CLK)
    vl(img, cx + w//2, cy, cy + h, CLK)
    # clip at top
    bk(img, cx - 1, cy - 1, cx + 1, cy, K)


# ── Frame builders ────────────────────────────────────────────────────────────

# Layout constants (based on 48×48 cell, feet at y=41)
_CX       = 24    # horizontal centre
_FEET_Y   = 41    # bottom of boots / feet
_BOOT_H   = 4     # boot height in px
_LEG_H    = 11    # leg strip height
_HIP_H    = 3
_TORSO_H  = 8
_NECK_H   = 2
_HEAD_H   = 8     # head top to bottom
_HAT_BOT  = 7     # hat brim y (hat is y=0..7)

# Computed y anchors (bottom-up from feet)
_BOOT_TOP  = _FEET_Y - _BOOT_H + 1          # y=38
_LEG_TOP   = _BOOT_TOP - _LEG_H             # y=27
_HIP_BOT   = _LEG_TOP - 1                   # y=26
_HIP_TOP   = _HIP_BOT - _HIP_H + 1         # y=24
_TRS_BOT   = _HIP_TOP - 1                   # y=23
_TRS_TOP   = _TRS_BOT - _TORSO_H + 1       # y=15
_NCK_BOT   = _TRS_TOP - 1                   # y=14
_NCK_TOP   = _NCK_BOT - _NECK_H + 1        # y=13
_HD_TOP    = _NCK_TOP - 1                   # y=12
# head bottom = _HD_TOP + _HEAD_H - 1 = y=19
# hat is above head, pinned to y=0..7 at top of cell

_SHD_Y    = _TRS_TOP                        # shoulder y
_ARM_TOP  = _SHD_Y
_ARM_BOT  = _FEET_Y - 6                     # arms reach to y=35


def frame_down(anim):
    img = Image.new("RGBA", (CELL, CELL), T)
    cx = _CX

    # ── walk / idle ──────────────────────────────────────────────────────────
    if anim in ("walk1", "idle", "walk3"):
        ll_off = {"walk1": -2, "idle": 0, "walk3": +2}[anim]  # leg x-offset
        rl_off = -ll_off
        la_off = {"walk1": +2, "idle": 0, "walk3": -2}[anim]  # arm y-offset
        ra_off = -la_off

        pigtails_front(img, cx, _HD_TOP, _HIP_BOT + 4)
        hat_front(img, cx)
        # left arm (behind torso)
        arm(img, cx - 11, _ARM_TOP + la_off, _ARM_BOT + la_off)
        torso_front(img, cx, _TRS_TOP, _TRS_BOT)
        hips(img, cx, _HIP_TOP, _HIP_BOT)
        # right arm (in front)
        arm(img, cx + 9, _ARM_TOP + ra_off, _ARM_BOT + ra_off)
        neck(img, cx, _NCK_TOP, _NCK_BOT)
        head_front(img, cx, _HD_TOP)
        # legs
        lx = cx + ll_off
        rx = cx + rl_off
        leg(img, lx - 3, _LEG_TOP, _BOOT_TOP, _FEET_Y)
        leg(img, rx + 2, _LEG_TOP, _BOOT_TOP, _FEET_Y)

    # ── typing ───────────────────────────────────────────────────────────────
    elif anim in ("type1", "type2"):
        lean = 2   # lean right toward work surface
        arm_reach = 4 if anim == "type2" else 2   # right arm lower
        pigtails_front(img, cx + lean, _HD_TOP, _HIP_BOT + 4)
        hat_front(img, cx + lean)
        arm(img, cx - 11 + lean, _ARM_TOP, _ARM_BOT - 4)
        torso_front(img, cx + lean, _TRS_TOP, _TRS_BOT)
        hips(img, cx + lean, _HIP_TOP, _HIP_BOT)
        # right arm reaching down-right
        ry0 = _ARM_TOP
        ry1 = _ARM_BOT - 4 + arm_reach
        arm(img, cx + 9 + lean + arm_reach, ry0, ry1)
        neck(img, cx + lean, _NCK_TOP, _NCK_BOT)
        head_front(img, cx + lean, _HD_TOP)
        leg(img, cx - 3, _LEG_TOP, _BOOT_TOP, _FEET_Y)
        leg(img, cx + 2, _LEG_TOP, _BOOT_TOP, _FEET_Y)
        # pencil at right hand
        pencil_h(img, cx + 9 + lean + arm_reach + 2, ry1, 5)

    # ── reading ──────────────────────────────────────────────────────────────
    elif anim in ("read1", "read2"):
        tilt = 1 if anim == "read2" else 0
        pigtails_front(img, cx, _HD_TOP, _HIP_BOT + 4)
        hat_front(img, cx)
        # arms raised, holding clipboard above head
        arm(img, cx - 11, _TRS_TOP - 6, _TRS_TOP + 1)
        arm(img, cx + 9,  _TRS_TOP - 6, _TRS_TOP + 1)
        torso_front(img, cx, _TRS_TOP, _TRS_BOT)
        hips(img, cx, _HIP_TOP, _HIP_BOT)
        neck(img, cx, _NCK_TOP, _NCK_BOT)
        head_front(img, cx, _HD_TOP + tilt)
        clipboard(img, cx, _HD_TOP - 7, w=10, h=5)
        leg(img, cx - 3, _LEG_TOP, _BOOT_TOP, _FEET_Y)
        leg(img, cx + 2, _LEG_TOP, _BOOT_TOP, _FEET_Y)

    return img


def frame_up(anim):
    img = Image.new("RGBA", (CELL, CELL), T)
    cx = _CX

    if anim in ("walk1", "idle", "walk3"):
        ll_off = {"walk1": -2, "idle": 0, "walk3": +2}[anim]
        rl_off = -ll_off
        la_off = {"walk1": +2, "idle": 0, "walk3": -2}[anim]
        ra_off = -la_off

        pigtails_back(img, cx, _HD_TOP, _HIP_BOT + 4)
        hat_back(img, cx)
        arm(img, cx - 11, _ARM_TOP + la_off, _ARM_BOT + la_off)
        torso_back(img, cx, _TRS_TOP, _TRS_BOT)
        hips(img, cx, _HIP_TOP, _HIP_BOT, flip=True)
        arm(img, cx + 9, _ARM_TOP + ra_off, _ARM_BOT + ra_off)
        head_back(img, cx, _HD_TOP)
        leg(img, cx + ll_off - 3, _LEG_TOP, _BOOT_TOP, _FEET_Y)
        leg(img, cx + rl_off + 2, _LEG_TOP, _BOOT_TOP, _FEET_Y)

    elif anim in ("type1", "type2"):
        lean = 2
        arm_reach = 4 if anim == "type2" else 2
        pigtails_back(img, cx + lean, _HD_TOP, _HIP_BOT + 6)
        hat_back(img, cx + lean)
        arm(img, cx - 11 + lean, _ARM_TOP, _ARM_BOT - 4)
        torso_back(img, cx + lean, _TRS_TOP, _TRS_BOT)
        hips(img, cx + lean, _HIP_TOP, _HIP_BOT, flip=True)
        arm(img, cx + 9 + lean + arm_reach, _ARM_TOP, _ARM_BOT - 4 + arm_reach)
        head_back(img, cx + lean, _HD_TOP)
        leg(img, cx - 3, _LEG_TOP, _BOOT_TOP, _FEET_Y)
        leg(img, cx + 2, _LEG_TOP, _BOOT_TOP, _FEET_Y)

    elif anim in ("read1", "read2"):
        tilt = 1 if anim == "read2" else 0
        pigtails_back(img, cx, _HD_TOP, _HIP_BOT + 4)
        hat_back(img, cx)
        arm(img, cx - 11, _TRS_TOP - 6, _TRS_TOP + 1)
        arm(img, cx + 9,  _TRS_TOP - 6, _TRS_TOP + 1)
        torso_back(img, cx, _TRS_TOP, _TRS_BOT)
        hips(img, cx, _HIP_TOP, _HIP_BOT, flip=True)
        head_back(img, cx, _HD_TOP + tilt)
        clipboard(img, cx, _HD_TOP - 6, w=10, h=5)
        leg(img, cx - 3, _LEG_TOP, _BOOT_TOP, _FEET_Y)
        leg(img, cx + 2, _LEG_TOP, _BOOT_TOP, _FEET_Y)

    return img


def frame_right(anim):
    img = Image.new("RGBA", (CELL, CELL), T)
    cx = _CX

    if anim in ("walk1", "idle", "walk3"):
        la_off = {"walk1": +2, "idle": 0, "walk3": -2}[anim]
        ll_off = {"walk1": -2, "idle": 0, "walk3": +2}[anim]

        pigtails_side(img, cx, _HD_TOP, _HIP_BOT + 4)
        hat_side(img, cx)
        arm(img, cx - 8, _ARM_TOP + la_off, _ARM_BOT + la_off)
        torso_side(img, cx, _TRS_TOP, _TRS_BOT)
        hips(img, cx - 1, _HIP_TOP, _HIP_BOT)
        arm(img, cx + 4, _ARM_TOP - la_off, _ARM_BOT - la_off)
        neck(img, cx, _NCK_TOP, _NCK_BOT)
        head_side(img, cx, _HD_TOP)
        leg(img, cx + ll_off - 2, _LEG_TOP, _BOOT_TOP, _FEET_Y)
        leg(img, cx - ll_off + 1, _LEG_TOP, _BOOT_TOP, _FEET_Y)

    elif anim in ("type1", "type2"):
        arm_reach = 5 if anim == "type2" else 3
        hat_side(img, cx)
        arm(img, cx - 8, _ARM_TOP, _ARM_BOT - 4)
        torso_side(img, cx, _TRS_TOP, _TRS_BOT)
        hips(img, cx - 1, _HIP_TOP, _HIP_BOT)
        arm(img, cx + 4 + arm_reach, _ARM_TOP, _ARM_BOT - 4 + arm_reach)
        neck(img, cx, _NCK_TOP, _NCK_BOT)
        head_side(img, cx, _HD_TOP)
        leg(img, cx - 2, _LEG_TOP, _BOOT_TOP, _FEET_Y)
        leg(img, cx + 1, _LEG_TOP, _BOOT_TOP, _FEET_Y)
        pencil_h(img, cx + 6 + arm_reach, _ARM_BOT - 4 + arm_reach, 5)

    elif anim in ("read1", "read2"):
        tilt = 1 if anim == "read2" else 0
        pigtails_side(img, cx, _HD_TOP, _HIP_BOT + 4)
        hat_side(img, cx)
        arm(img, cx - 8, _TRS_TOP - 5, _TRS_TOP + 1)
        arm(img, cx + 4, _TRS_TOP - 5, _TRS_TOP + 1)
        torso_side(img, cx, _TRS_TOP, _TRS_BOT)
        hips(img, cx - 1, _HIP_TOP, _HIP_BOT)
        neck(img, cx, _NCK_TOP, _NCK_BOT)
        head_side(img, cx, _HD_TOP + tilt)
        # clipboard appears edge-on (thin vertical bar)
        vl(img, cx + 3, _HD_TOP - 6, _HD_TOP, CLP)
        vl(img, cx + 4, _HD_TOP - 6, _HD_TOP, CLK)
        leg(img, cx - 2, _LEG_TOP, _BOOT_TOP, _FEET_Y)
        leg(img, cx + 1, _LEG_TOP, _BOOT_TOP, _FEET_Y)

    return img


# ── Sheet assembly ────────────────────────────────────────────────────────────
ANIMS = ["walk1", "idle", "walk3", "type1", "type2", "read1", "read2"]
DIRS  = [frame_down, frame_up, frame_right]


def build_sheet():
    sheet = Image.new("RGBA", (CELL * COLS, CELL * ROWS), T)
    for row_idx, builder in enumerate(DIRS):
        for col_idx, anim in enumerate(ANIMS):
            frame = builder(anim)
            ox = col_idx * CELL
            oy = row_idx * CELL
            sheet.paste(frame, (ox, oy))
    return sheet


# ── Animated GIF helpers ──────────────────────────────────────────────────────

def frames_to_gif(frames, path, fps=8, scale=4):
    """Save list of RGBA PIL Images as an animated GIF."""
    converted = []
    for f in frames:
        big = f.resize((CELL * scale, CELL * scale), Image.NEAREST)
        converted.append(big.convert("RGBA"))
    delay = int(1000 / fps)
    converted[0].save(
        path,
        save_all=True,
        append_images=converted[1:],
        loop=0,
        duration=delay,
        disposal=2,
    )


def make_gifs(sheet, out_dir, scale=4):
    out_dir.mkdir(parents=True, exist_ok=True)
    dir_names = ["down", "up", "right"]

    # Walk cycle: cols 0, 1, 2, 1 (ping-pong)
    walk_idx = [0, 1, 2, 1]
    type_idx = [3, 4]
    read_idx = [5, 6]
    idle_idx = [1]

    gifs = []
    for row_idx, dname in enumerate(dir_names):
        for group_name, col_list in [
            ("walk", walk_idx),
            ("type", type_idx),
            ("read", read_idx),
            ("idle", idle_idx),
        ]:
            frames = []
            for ci in col_list:
                x0 = ci * CELL
                y0 = row_idx * CELL
                frames.append(sheet.crop((x0, y0, x0 + CELL, y0 + CELL)))
            gif_path = out_dir / f"ponmi_{dname}_{group_name}.gif"
            frames_to_gif(frames, gif_path, fps=6, scale=scale)
            gifs.append(gif_path)
            print(f"  wrote {gif_path.name}")

    return gifs


# ── Overlay-compatible 4-row sheet (idle/walk/sit/stand/jump) ─────────────────

def build_overlay_sheet():
    """
    Build a Stream Avatars compatible sheet from existing row-0 frames.
    5 rows × 4 cols, 48×48 cells → 192×240 px

    Row 0 idle   : [idle, idle, idle, idle]
    Row 1 walk   : [walk1, walk2, walk3, walk2]  (ping-pong)
    Row 2 think  : [read1, read2, read1, read2]
    Row 3 done   : [idle, idle, idle, idle]
    Row 4 subagt : [walk1, walk3, walk1, walk3]
    """
    ow, oh = CELL * 4, CELL * 5
    out = Image.new("RGBA", (ow, oh), T)
    sheet = build_sheet()  # full 3-row sheet

    def get(col, row=0):
        return sheet.crop((col * CELL, row * CELL, (col+1)*CELL, (row+1)*CELL))

    plan = [
        [1, 1, 1, 1],          # row 0 idle
        [0, 1, 2, 1],          # row 1 walk
        [5, 6, 5, 6],          # row 2 think/read
        [1, 1, 1, 1],          # row 3 stand/done
        [0, 2, 0, 2],          # row 4 subagent/jump
    ]
    for r, cols in enumerate(plan):
        for c, src_col in enumerate(cols):
            out.paste(get(src_col), (c * CELL, r * CELL))

    return out


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    view_mode = "--view" in sys.argv

    print("Building Ponmi sprite sheet …")
    sheet = build_sheet()

    # Save to PixelCircus characters folder
    OUTPUT_PIXELCIRCUS.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUTPUT_PIXELCIRCUS)
    print(f"  saved -> {OUTPUT_PIXELCIRCUS}")

    # Save overlay-compatible sheet
    OUTPUT_OVERLAY.parent.mkdir(parents=True, exist_ok=True)
    overlay_sheet = build_overlay_sheet()
    overlay_sheet.save(OUTPUT_OVERLAY)
    print(f"  saved -> {OUTPUT_OVERLAY}")

    # Generate animated GIFs
    print("Generating preview GIFs …")
    gifs = make_gifs(sheet, OUTPUT_GIF_DIR, scale=6)

    print(f"\nDone. {len(gifs)} GIFs in {OUTPUT_GIF_DIR}")
    print("Sheets saved to:")
    print(f"  {OUTPUT_PIXELCIRCUS}")
    print(f"  {OUTPUT_OVERLAY}")

    if view_mode:
        import subprocess
        for g in gifs:
            subprocess.Popen(["start", str(g)], shell=True)
