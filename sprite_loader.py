#!/usr/bin/env python3
"""
sprite_loader.py
================
Stream Avatars-compatible sprite sheet loader for the AI Agent Overlay.

Each ROW in the sheet = one animation state.
Each COLUMN         = one frame of that animation (left to right).
Empty frames (fully transparent cells) are auto-detected and skipped.

Row convention (Stream Avatars standard):
    Row 0 — idle
    Row 1 — run / walk
    Row 2 — sit
    Row 3 — stand
    Row 4 — jump
    Row 5+ — custom

Usage:
    registry = SpriteRegistry()
    registry.load("amongo",   "assets/amongo.png",   frame_w=48, scale=2.0)
    registry.load("meowatar", "assets/meowatar.png", frame_w=60, scale=2.0)

    # In your render loop:
    photo = registry.get_photo("amongo", status="busy", frame=tick)
    canvas.itemconfig(sprite_id, image=photo)
"""

import threading
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("[sprite_loader] Pillow not installed. Run: pip install pillow")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("[sprite_loader] numpy not installed — hue rotation and blank-detection disabled. Run: pip install numpy")


def hue_rotate_image(img: "Image.Image", degrees: float) -> "Image.Image":
    """Rotate the hue of an RGBA image by `degrees` (0–360). Returns new image."""
    if not HAS_PIL or not HAS_NUMPY:
        return img
    arr   = np.array(img.convert("RGBA"), dtype=np.float32)
    rgb   = arr[..., :3] / 255.0
    alpha = arr[..., 3:4]

    max_c = rgb.max(2); min_c = rgb.min(2); delta = max_c - min_c
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.zeros_like(max_c)
    m  = delta > 0
    mr = m & (max_c == r); mg = m & (max_c == g); mb = m & (max_c == b)
    h[mr] = ((g[mr] - b[mr]) / delta[mr]) % 6
    h[mg] = ((b[mg] - r[mg]) / delta[mg]) + 2
    h[mb] = ((r[mb] - g[mb]) / delta[mb]) + 4
    h = (h / 6.0 + degrees / 360.0) % 1.0

    s  = np.where(max_c > 0, delta / max_c, 0.0)
    v  = max_c
    h6 = h * 6.0
    i  = h6.astype(int) % 6
    f  = h6 - np.floor(h6)
    p  = v * (1 - s);  q = v * (1 - f * s);  t = v * (1 - (1 - f) * s)
    nr = np.select([i==0,i==1,i==2,i==3,i==4,i==5], [v,q,p,p,t,v], v)
    ng = np.select([i==0,i==1,i==2,i==3,i==4,i==5], [t,v,v,q,p,p], v)
    nb = np.select([i==0,i==1,i==2,i==3,i==4,i==5], [p,p,t,v,v,q], v)

    out = np.concatenate(
        [np.stack([nr, ng, nb], 2) * 255, alpha], 2
    ).clip(0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


# ── Status → Row mapping ────────────────────────────────────────────────────
# Maps AgentInfo.status strings to sprite sheet row indices.
# Edit this to remap any status to a different animation row.
ANIM_ROW: dict[str, int] = {
    "idle":     0,
    "thinking": 2,   # sit animation = thinking/waiting
    "busy":     1,   # run animation = tool use
    "subagent": 4,   # jump animation = subagent active
    "done":     3,   # stand animation = done/cooldown
    "error":    3,   # stand animation fallback (add row 5 for custom error anim)
}

# A cell is "blank" if the sum of all alpha pixel values is below this threshold.
# Increase if your sprite sheet has very faint frames you want to keep.
BLANK_ALPHA_THRESHOLD = 10


# ── SpriteSheet ─────────────────────────────────────────────────────────────

class SpriteSheet:
    """
    Loads one sprite sheet image and slices it into animation frames.

    Python concepts used here:
        - Image.open() / .convert("RGBA") — loads image, ensures 4-channel RGBA
        - Image.resize(..., Image.NEAREST) — pixel-perfect upscale (no blurring)
        - Image.crop((x0, y0, x1, y1)) — cuts a rectangle out of the image
        - numpy.array(img)[:,:,3] — grabs only the alpha channel as a 2D number array
        - .sum() — adds all alpha values; near-zero means blank frame
        - list[list[...]] — 2D list: _frames[row_index][frame_index]
    """

    def __init__(
        self,
        path: Optional[str] = None,
        frame_w: int = 32,
        frame_h: Optional[int] = None,
        scale: float = 1.0,
        *,
        image: Optional["Image.Image"] = None,
    ):
        if not HAS_PIL:
            raise ImportError("Pillow required: pip install pillow")

        self.frame_w = frame_w
        self.frame_h = frame_h or frame_w
        self.scale   = scale

        if image is not None:
            self.path = Path("<memory>")
            raw = image if image.mode == "RGBA" else image.convert("RGBA")
        else:
            if path is None:
                raise ValueError("path or image required")
            self.path = Path(path)
            raw = Image.open(path).convert("RGBA")

        # Load and optionally scale the full sheet
        if scale != 1.0:
            new_w = int(raw.width  * scale)
            new_h = int(raw.height * scale)
            raw   = raw.resize((new_w, new_h), Image.NEAREST)
        self.image = raw

        # How many columns and rows fit in the sheet at the scaled cell size
        self.cell_w = int(self.frame_w * scale)
        self.cell_h = int(self.frame_h * scale)
        self.cols   = self.image.width  // self.cell_w
        self.rows   = self.image.height // self.cell_h

        # _frames[row][col] = PIL Image  (or row is shorter if blanks found)
        # _photos[row][col] = ImageTk.PhotoImage or None (lazy, cached on first use)
        self._frames: list[list[Image.Image]] = []
        self._photos: list[list[Optional[ImageTk.PhotoImage]]] = []
        self._slice_all()

    def _slice_all(self):
        """
        Slice the full sheet into individual cell images.
        Stops each row at the first blank (fully transparent) cell.
        """
        for r in range(self.rows):
            row_frames = []
            for c in range(self.cols):
                x0   = c * self.cell_w
                y0   = r * self.cell_h
                cell = self.image.crop((x0, y0, x0 + self.cell_w, y0 + self.cell_h))
                if self._is_blank(cell):
                    break                   # stop this row here
                row_frames.append(cell)
            self._frames.append(row_frames)
            self._photos.append([None] * len(row_frames))

    def _is_blank(self, cell: "Image.Image") -> bool:
        """Returns True if a cell has no visible pixels (alpha sum below threshold)."""
        if HAS_NUMPY:
            alpha_sum = np.array(cell)[:, :, 3].sum()
            return int(alpha_sum) < BLANK_ALPHA_THRESHOLD
        # Fallback without numpy: use PIL to check if any pixel has alpha > 0
        r, g, b, a = cell.split()
        return a.getbbox() is None

    def get_frame_count(self, row: int) -> int:
        """How many non-blank frames exist in the given row."""
        if row >= len(self._frames):
            return 0
        return len(self._frames[row])

    def get_photo(self, row: int, frame_idx: int) -> Optional["ImageTk.PhotoImage"]:
        """
        Return a tkinter-compatible PhotoImage for (row, frame).

        PhotoImage objects are created lazily (on first request) and cached.
        WHY: tkinter requires PhotoImage objects to stay referenced in Python
        memory or they get garbage-collected and the canvas shows a blank.
        Keeping them in self._photos prevents that.

        frame_idx is modulo'd so it loops — you can pass the raw tick counter.
        """
        if row >= len(self._frames):
            row = 0
        frames = self._frames[row]
        if not frames:
            for fallback in range(len(self._frames)):
                if self._frames[fallback]:
                    frames = self._frames[fallback]
                    break
            else:
                return None
        idx = frame_idx % len(frames)
        if self._photos[row][idx] is None:
            self._photos[row][idx] = ImageTk.PhotoImage(frames[idx])
        return self._photos[row][idx]

    def get_render_size(self) -> tuple[int, int]:
        """Returns (width, height) of one rendered cell in pixels."""
        return (self.cell_w, self.cell_h)

    def debug_info(self) -> str:
        """Human-readable summary of this sheet's layout."""
        anim_names = ["idle", "run", "sit", "stand", "jump"] + \
                     [f"custom{i}" for i in range(1, 20)]
        lines = [
            f"SpriteSheet '{self.path.name}'",
            f"  Image   : {self.image.width}x{self.image.height} px",
            f"  Cell    : {self.cell_w}x{self.cell_h} px  (scale={self.scale}x)",
            f"  Grid    : {self.cols} cols x {self.rows} rows",
            f"  Animations:",
        ]
        for r, frames in enumerate(self._frames):
            name = anim_names[r] if r < len(anim_names) else f"row{r}"
            lines.append(f"    row {r}  [{name:8s}]  {len(frames)} frame(s)")
        return "\n".join(lines)


# ── SpriteRegistry ──────────────────────────────────────────────────────────

class SpriteRegistry:
    """
    Manages multiple named SpriteSheet instances.
    Translates (skin_name, agent_status, frame_tick) → PhotoImage.

    Thread-safe: uses a Lock so background threads can call get_photo()
    while the main thread loads new sheets.

    Python concepts:
        - dict[str, SpriteSheet] — maps name string → sheet object
        - threading.Lock() — prevents simultaneous read+write crashes
        - with self._lock: — acquires lock for the block, auto-releases on exit
    """

    def __init__(self):
        self._sheets: dict[str, SpriteSheet] = {}
        self._lock   = threading.Lock()

    def load(
        self,
        name: str,
        path: str,
        frame_w: int,
        frame_h: Optional[int] = None,
        scale: float = 1.0,
    ) -> "SpriteSheet":
        """
        Load a sprite sheet and register it under `name`.

        Args:
            name:    Identifier used later in get_photo() — e.g. "amongo"
            path:    File path to the PNG sprite sheet
            frame_w: Width of one animation cell in pixels
            frame_h: Height of one cell (default = frame_w)
            scale:   Render scale multiplier (2.0 = double size, pixel-perfect)

        Example:
            registry.load("amongo", "assets/amongo.png", frame_w=48, scale=2.0)
        """
        sheet = SpriteSheet(path, frame_w, frame_h, scale)
        print(sheet.debug_info())
        with self._lock:
            self._sheets[name] = sheet
        return sheet

    def get_photo(
        self,
        name: str,
        status: str,
        frame: int,
    ) -> Optional["ImageTk.PhotoImage"]:
        """
        Get the right animation frame for a given skin and agent status.

        name:   registered sheet name (e.g. "amongo")
        status: agent status string ("idle", "busy", "thinking", etc.)
        frame:  raw frame counter (will be modulo'd by row's frame count)
        """
        with self._lock:
            sheet = self._sheets.get(name)
        if not sheet:
            return None

        row = ANIM_ROW.get(status, 0)
        # If the target row has no frames, fall back to idle (row 0)
        if sheet.get_frame_count(row) == 0:
            row = 0
        return sheet.get_photo(row, frame)

    def get_render_size(self, name: str) -> tuple[int, int]:
        """Returns rendered cell (width, height) for the named sheet."""
        with self._lock:
            sheet = self._sheets.get(name)
        return sheet.get_render_size() if sheet else (48, 48)

    def reload_all(self, scale: float) -> None:
        """Reload every file-backed sheet at a new scale. Skips in-memory hue variants."""
        with self._lock:
            snapshot = {
                n: (str(s.path), s.frame_w, s.frame_h)
                for n, s in self._sheets.items()
                if str(s.path) != "<memory>"
            }
        for name, (path, fw, fh) in snapshot.items():
            try:
                sheet = SpriteSheet(path, fw, fh, scale)
                with self._lock:
                    self._sheets[name] = sheet
                print(f"[sprites] reloaded {name} at {scale:.1f}×")
            except Exception as e:
                print(f"[sprites] reload failed for {name}: {e}")

    def load_hue_variant(
        self, variant_name: str, base_name: str, hue_degrees: float
    ) -> Optional["SpriteSheet"]:
        """Register a hue-rotated copy of base_name under variant_name."""
        with self._lock:
            base = self._sheets.get(base_name)
        if not base:
            return None
        rotated = hue_rotate_image(base.image, hue_degrees)
        # base.image is already scaled; pass cell_w/cell_h as frame dims and scale=1.0
        # to prevent SpriteSheet.__init__ from applying the scale a second time.
        sheet   = SpriteSheet(frame_w=base.cell_w, frame_h=base.cell_h,
                               scale=1.0, image=rotated)
        with self._lock:
            self._sheets[variant_name] = sheet
        return sheet

    def get_thumbnail(self, name: str, size: int = 48) -> Optional["ImageTk.PhotoImage"]:
        """Return a fixed-size PhotoImage for UI thumbnails, ignoring current AVATAR_SCALE."""
        with self._lock:
            sheet = self._sheets.get(name)
        if not sheet or not sheet._frames or not sheet._frames[0]:
            return None
        frame = sheet._frames[0][0]
        thumb = frame.resize((size, size), Image.NEAREST)
        return ImageTk.PhotoImage(thumb)

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._sheets

    def list_sheets(self) -> list[str]:
        with self._lock:
            return list(self._sheets.keys())


# ── Utility: JPG → PNG converter ────────────────────────────────────────────

def convert_jpg_to_png(src: str, dst: str) -> None:
    """
    Convert a JPG sprite sheet to PNG (preserving as much data as possible).
    JPG does not support transparency, so this is a lossy operation —
    the resulting PNG will have all pixels fully opaque (alpha = 255).
    You will need to manually remove the background color in an image editor
    (or use a chroma-key approach in code).

    Usage:
        convert_jpg_to_png("char_AmongoCat-2.jpg", "assets/amongo.png")
        convert_jpg_to_png("meowatar_orig.jpg",     "assets/meowatar.png")
    """
    if not HAS_PIL:
        raise ImportError("Pillow required: pip install pillow")
    img = Image.open(src).convert("RGBA")
    img.save(dst)
    print(f"Converted {src} -> {dst}  ({img.width}x{img.height})")


# ── CLI helper ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "convert":
        # python sprite_loader.py convert char_AmongoCat-2.jpg assets/amongo.png
        if len(sys.argv) < 4:
            print("Usage: python sprite_loader.py convert <src.jpg> <dst.png>")
            sys.exit(1)
        convert_jpg_to_png(sys.argv[2], sys.argv[3])

    elif len(sys.argv) >= 2 and sys.argv[1] == "info":
        # python sprite_loader.py info assets/amongo.png 48 48
        if len(sys.argv) < 5:
            print("Usage: python sprite_loader.py info <sheet.png> <frame_w> <frame_h>")
            sys.exit(1)
        sheet = SpriteSheet(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
        print(sheet.debug_info())

    else:
        print("sprite_loader.py — utilities for AI Agent Overlay sprite sheets")
        print()
        print("Commands:")
        print("  convert <src.jpg> <dst.png>           Convert JPG to PNG")
        print("  info <sheet.png> <frame_w> <frame_h>  Print sheet layout info")
