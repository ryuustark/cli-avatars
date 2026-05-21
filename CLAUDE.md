# CLI Avatars — Claude Code Project Guide

Standalone Python desktop overlay. Animated pixel-art avatars walk on screen for each active AI agent session.

**Full reference:** `AI_OVERLAY.md` — contains all architecture, sprite spec, and roadmap. Read it first.

---

## Run

```bash
pip install -r requirements.txt
python overlay.py
# Right-click or ESC to quit
```

Demo mode activates automatically when no Claude Code sessions are found (4 agents cycling all states).

---

## Key Files

| File | Role |
|------|------|
| `overlay.py` | Entry point. OverlayApp, Avatar, SessionScanner, WindowTerrain, HUD |
| `sprite_loader.py` | SpriteSheet + SpriteRegistry — Stream Avatars row/col format |
| `claude_hooks_example.py` | Drop into `.claude/hooks/` for real-time UDP events |
| `requirements.txt` | pip deps |
| `assets/` | Put PNG sprite sheets here (convert from JPG first) |

---

## Architecture in 30 Seconds

- `OverlayApp` creates a full-screen transparent tkinter window (chroma key `#010101`)
- Two daemon threads: `SessionScanner` (reads `~/.claude/projects/*/sessions/*.jsonl`) and `WindowTerrain` (open window tops = floor platforms via pywinctl)
- Main loop at 20 FPS via `root.after()` — syncs agent pool, runs physics, draws sprites
- `Avatar` has gravity, wall bounce, floor collision, idle pauses; speed doubles when status=`busy`
- Procedural 8×8→32×32 pixel sprites via Pillow (no external assets needed for v0.1)
- `sprite_loader.py` exists but is **not yet wired** — v0.2 task

---

## Current State (v0.1)

- Full physics + demo mode: works out of the box
- `sprite_loader.py`: fully implemented, not imported into overlay yet
- Click-through (mouse passes through overlay): not yet implemented
- UDP hook listener: not yet implemented

See `TASKS.md` for the v0.2 milestone breakdown.

---

## Python Concepts

The `AI_OVERLAY.md` reference has a full glossary table. Key ones:

- `@dataclass` / `field(default_factory=...)` — `AgentInfo`
- `threading.Thread(daemon=True)` + `threading.Lock()` — scanner + terrain threads
- `canvas.after(ms, fn)` — animation loop without blocking UI
- `Image.crop()` / `numpy[:,:,3].sum()` — sprite slicing + blank frame detection
- `% (modulo)` on frame counter — loops animation

---

## Sprite Sheets

Stream Avatars row convention:

| Row | Animation | Agent Status |
|-----|-----------|-------------|
| 0 | idle | idle |
| 1 | run/walk | busy |
| 2 | sit | thinking |
| 3 | stand | done/error |
| 4 | jump | subagent |

Known sheets (need PNG conversion before use):
- `char_AmongoCat-2.jpg` — 192×240 px, 48×48 cell, 4×5 grid
- `meowatar_orig.jpg` — 240×300 px, 60×60 cell, 4×5 grid

Convert: `python sprite_loader.py convert char_AmongoCat-2.jpg assets/amongo.png`
