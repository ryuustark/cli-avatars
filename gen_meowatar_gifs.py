#!/usr/bin/env python3
"""
gen_meowatar_gifs.py — Extract animated GIFs from meowatar.png sprite sheet.

Sheet: 240x250 px | 4 cols x 5 rows | 60x50 cells | RGBA
Row 0: idle | Row 1: walk | Row 2: sit/think | Row 3: stand | Row 4: jump

Outputs: meowatar_preview/*.gif
"""
from pathlib import Path
from PIL import Image

CELL_W = 60
CELL_H = 50
COLS   = 4
SCALE  = 4
FPS    = 6

SRC      = Path(__file__).parent / "Sprites/meowatar.png"
OUT_DIR  = Path(__file__).parent / "meowatar_preview"

def get_frames(sheet, row, cols=None):
    if cols is None:
        cols = list(range(COLS))
    frames = []
    for c in cols:
        x0, y0 = c * CELL_W, row * CELL_H
        frames.append(sheet.crop((x0, y0, x0 + CELL_W, y0 + CELL_H)))
    return frames

def save_gif(frames, path):
    scaled = [f.resize((CELL_W * SCALE, CELL_H * SCALE), Image.NEAREST).convert("RGBA")
              for f in frames]
    scaled[0].save(
        path, save_all=True, append_images=scaled[1:],
        loop=0, duration=int(1000 / FPS), disposal=2,
    )
    print(f"  {path.name}")

if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)
    sheet = Image.open(SRC)

    save_gif(get_frames(sheet, row=1, cols=[0,1,2,1]),   OUT_DIR / "meowatar_walk.gif")
    save_gif(get_frames(sheet, row=1, cols=[0,1,2,1]),   OUT_DIR / "meowatar_type.gif")
    save_gif(get_frames(sheet, row=2, cols=[0,1,2,1]),   OUT_DIR / "meowatar_read.gif")
    save_gif(get_frames(sheet, row=0, cols=[0,1]),        OUT_DIR / "meowatar_idle.gif")

    print(f"Done — 4 GIFs in {OUT_DIR}")
