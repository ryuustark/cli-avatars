# AI Agent Desktop Overlay — Complete Project Reference
> **v0.1 — 2026-05-14**
> Hand this single file to any AI assistant to continue the project from scratch.
> It contains: project context, architecture, Python learning notes, all source code, roadmap, and git setup.

---

## Table of Contents

1. [What This Project Is](#what-this-project-is)
2. [Quick Start](#quick-start)
3. [File Structure](#file-structure)
4. [Architecture](#architecture)
5. [Python Concepts Glossary](#python-concepts-glossary)
6. [Sprite Sheet Format](#sprite-sheet-format)
7. [Source Code — overlay.py](#source-code--overlaypy)
8. [Source Code — sprite_loader.py](#source-code--sprite_loaderpy)
9. [Source Code — claude_hooks_example.py](#source-code--claude_hooks_examplepy)
10. [requirements.txt](#requirementstxt)
11. [Current State & Known Issues](#current-state--known-issues)
12. [Roadmap](#roadmap)
13. [Git Setup](#git-setup)
14. [Changelog](#changelog)

---

## What This Project Is

A **transparent, always-on-top desktop overlay** written in Python that renders animated pixel-art avatars for active AI agent sessions (Claude Code, subagents, Copilot, etc.).

Each avatar represents one running agent and reacts visually to what it is doing:

- Walking slowly → idle
- Running fast → busy (using a tool like Bash, Read, Write)
- Bouncing with dots above head → thinking
- Purple status dot + ⚡ counter → subagent active
- Red ✕ on body → error

Avatars have gravity, walk on your open application windows as terrain (window top-edges = platforms), bounce off screen walls, and pause randomly to idle.

The core visual inspiration is **Stream Avatars** (the Twitch streaming app) — characters that roam freely on screen reacting to events — applied to AI agent monitoring.

---

## Quick Start

```bash
# 1. Clone repo
git clone <your-repo-url>
cd ai-overlay

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python overlay.py
# Right-click or ESC to quit
```

**Demo mode:** If no Claude Code sessions are active, 4 demo agents automatically cycle through all animation states so you can see it working immediately.

---

## File Structure

```
zz_cli_avatars/
│
├── overlay.py                ← ENTRY POINT — run this
│   Contains: OverlayApp, Avatar, SessionScanner,
│             WindowTerrain, AgentInfo, draw_hud()
│
├── sprite_loader.py          ← Sprite sheet utilities
│   Contains: SpriteSheet, SpriteRegistry, convert_jpg_to_png()
│
├── claude_hooks_example.py   ← Claude Code hooks → UDP integration
│   Drop into .claude/hooks/ in any project
│
├── requirements.txt          ← pip dependencies
│
├── assets/                   ← PUT YOUR PNG SPRITE SHEETS HERE
│   ├── amongo.png            (convert from char_AmongoCat-2.jpg)
│   └── meowatar.png          (convert from meowatar_orig.jpg)
│
├── CLAUDE.md                 ← Claude Code project guide
├── TASKS.md                  ← Development task board
└── AI_OVERLAY.md             ← this file
```

---

## Architecture

### How the main loop works

```
python overlay.py
    │
    └── OverlayApp.__init__()
          ├── Creates full-screen transparent tkinter window
          ├── Starts SessionScanner thread  (every 2s)
          ├── Starts WindowTerrain thread   (every 0.5s)
          └── Calls _tick() to start render loop
                │
                └── _tick() runs every 50ms (20 FPS via root.after)
                      ├── SessionScanner.get_agents()  → dict of AgentInfo
                      ├── WindowTerrain.get_floors()   → list of floor rects
                      ├── Sync Avatar pool ↔ agent dict
                      │     ├── New agent   → spawn Avatar
                      │     └── Gone agent  → remove Avatar + canvas items
                      ├── For each Avatar:
                      │     ├── avatar.update(floors)  → physics step
                      │     └── avatar.draw(canvas)    → render sprite
                      └── draw_hud(canvas, agents)     → status panel
```

### Background threads

```
SessionScanner.loop()
    Every 2 seconds:
    ├── Scans ~/.claude/projects/*/sessions/*.jsonl
    │     Reads last 4KB, parses JSON lines for:
    │       {"type": "tool_use"}  → status=BUSY, tool=name
    │       {"type": "thinking"}  → status=THINKING
    │       "subagent" in line    → status=SUBAGENT
    └── Falls back to 4 cycling demo agents if no real sessions found

WindowTerrain.loop()
    Every 0.5 seconds:
    ├── Calls pywinctl.getAllWindows()
    ├── Filters: visible, titled, width > 60px, not the overlay itself
    └── Returns list of (x1, y1, x2, y2) tuples
          each is the TOP EDGE of a window = one floor platform
```

### Data flow

```
~/.claude/ session files
    → SessionScanner._scan()
        → AgentInfo(id, name, status, tool, subagents)
            → Avatar.agent  (reference updated every tick)
                → Avatar.update()  uses status for speed / jump behavior
                → Avatar.draw()    uses status for sprite row selection
                                   uses status for HUD color coding
```

### Key Classes

| Class | File | Responsibility |
|---|---|---|
| `OverlayApp` | overlay.py | tkinter window, main tick loop, thread coordination |
| `Avatar` | overlay.py | Physics entity + sprite renderer for one agent |
| `AgentInfo` | overlay.py | Dataclass: id, name, status, tool, subagents, last_seen |
| `SessionScanner` | overlay.py | Reads Claude Code logs, provides AgentInfo dict |
| `WindowTerrain` | overlay.py | Reads open windows, provides floor rect list |
| `SpriteSheet` | sprite_loader.py | Slices one PNG into 2D frame array |
| `SpriteRegistry` | sprite_loader.py | Named collection of SpriteSheets, status→row lookup |

### Status → Visual mapping

| Status | Sprite row | Walk speed | Special behavior |
|---|---|---|---|
| idle | 0 (idle) | normal | random pauses |
| thinking | 2 (sit) | normal | small bounces |
| busy | 1 (run) | 2× faster | no pauses |
| subagent | 4 (jump) | normal | purple dot, ⚡ label |
| done | 3 (stand) | normal | — |
| error | 3 (stand) | normal | red ✕ on sprite |

---

## Python Concepts Glossary

For learning Python while working on this project.

| Concept | Where used | What it does |
|---|---|---|
| `@dataclass` | `AgentInfo` | Decorator that auto-generates `__init__`, `__repr__` from type-annotated fields. Saves writing boilerplate. |
| `field(default_factory=time.time)` | `AgentInfo.last_seen` | For mutable defaults in dataclasses — `default_factory` calls a function each time, avoiding shared state bugs. |
| `threading.Thread(target=fn, daemon=True)` | Scanner + Terrain | Runs `fn` in a parallel thread. `daemon=True` means it dies automatically when the main program exits. |
| `threading.Lock()` | All shared state | A mutex — only one thread can be inside `with self._lock:` at a time. Prevents crashes from simultaneous reads+writes. |
| `with self._lock:` | get_agents(), get_floors() | Context manager — acquires the lock on enter, releases on exit (even if an exception occurs). |
| `Path(...)` / `pathlib` | Session file paths | Modern file path handling. `Path.home()` = home directory. `path.glob("*/*.jsonl")` = pattern search. |
| `f.seek(0, 2)` | Session log reader | `seek(offset, whence)` — whence=2 means "from end". So `seek(0, 2)` jumps to the last byte. Used to read only the tail of large log files. |
| `json.loads(line)` | Session log parser | Parses one JSON string into a Python dict. `.jsonl` files have one JSON object per line. |
| `canvas.after(ms, fn)` | Main tick loop | tkinter's way to schedule a function call after N milliseconds. Used to create the animation loop without blocking the UI. |
| `canvas.create_image(x, y, image=photo)` | Avatar.draw() | Places an image on the canvas. Returns an integer ID used later to move/update it. |
| `canvas.coords(id, x, y)` | Avatar.draw() | Moves an existing canvas item to new coordinates. Faster than deleting+recreating. |
| `Image.crop((x0,y0,x1,y1))` | SpriteSheet._slice_all() | Cuts a rectangular region from a PIL Image. Returns a new Image. |
| `numpy array[:,:,3]` | SpriteSheet._is_blank() | `[:,:,3]` selects the alpha channel (index 3 of RGBA). The result is a 2D array of 0-255 values. `.sum()` adds them all. |
| `% (modulo)` | Avatar frame counter | `frame_idx % len(frames)` loops the frame index — when it reaches the end of the row, it wraps back to 0. |
| `Optional[X]` | Type hints | Means the value can be either type `X` or `None`. Documents intent; Python doesn't enforce it at runtime. |
| `dict[str, SpriteSheet]` | SpriteRegistry | Type hint for a dictionary mapping strings to SpriteSheet objects. |
| `wm_attributes("-topmost", True)` | OverlayApp | Tells the OS window manager to keep this window above all others. |
| `overrideredirect(True)` | OverlayApp | Removes the OS title bar and window decorations entirely. |
| `wm_attributes("-transparentcolor", "#010101")` | OverlayApp | Makes every pixel of the given color invisible (chroma-key transparency). The canvas background uses this color. |

---

## Sprite Sheet Format

### Stream Avatars Row Convention

This project uses the same sprite sheet layout as the Stream Avatars app.

```
Sheet structure:
  ┌──────┬──────┬──────┬──────┐  ← Row 0: IDLE animation
  │ fr 0 │ fr 1 │ fr 2 │      │    (empty cells at end are skipped)
  ├──────┼──────┼──────┼──────┤
  │ fr 0 │ fr 1 │ fr 2 │ fr 3 │  ← Row 1: RUN / WALK animation
  ├──────┼──────┼──────┼──────┤
  │ fr 0 │ fr 1 │      │      │  ← Row 2: SIT animation
  ├──────┼──────┼──────┼──────┤
  │ fr 0 │ fr 1 │ fr 2 │      │  ← Row 3: STAND animation
  ├──────┼──────┼──────┼──────┤
  │ fr 0 │ fr 1 │ fr 2 │ fr 3 │  ← Row 4: JUMP animation
  └──────┴──────┴──────┴──────┘
```

| Row | Name | Agent status |
|-----|------|-------------|
| 0 | idle | idle |
| 1 | run / walk | busy (tool use) |
| 2 | sit | thinking |
| 3 | stand | done / error |
| 4 | jump | subagent active |
| 5+ | custom | extensible |

### Your Sprite Sheets

| File | Size | Cell | Grid |
|------|------|------|------|
| `char_AmongoCat-2.jpg` | 192×240 px | 48×48 px | 4 cols × 5 rows |
| `meowatar_orig.jpg` | 240×300 px | 60×60 px | 4 cols × 5 rows |

**Important:** Both are JPG — JPG has no alpha channel (no transparency).
Convert to PNG before using with SpriteRegistry:

```bash
python sprite_loader.py convert char_AmongoCat-2.jpg assets/amongo.png
python sprite_loader.py convert meowatar_orig.jpg    assets/meowatar.png
```

After converting, the PNG background will be fully opaque. You will need to
remove the white/solid background in an image editor (Aseprite, Photoshop, GIMP)
or implement chroma-key background removal in code.

---

## Source Code — overlay.py

See `overlay.py` in this folder.

---

## Source Code — sprite_loader.py

See `sprite_loader.py` in this folder.

---

## Source Code — claude_hooks_example.py

See `claude_hooks_example.py` in this folder.

---

## requirements.txt

See `requirements.txt` in this folder.

---

## Current State & Known Issues

### What works (v0.1)
- Full-screen transparent tkinter overlay (always on top)
- 4 demo agents auto-animate when no real Claude Code sessions detected
- Physics engine: gravity, floor collision, wall bounce, idle pauses, status-reactive speed
- Inline pixel sprite renderer (8×8 procedural, no external assets needed)
- Multi-avatar management (spawn/remove as sessions appear/disappear)
- HUD panel top-left: agent count, busy/thinking/subagent summary
- Claude Code session scanner: watches `~/.claude/projects/*/sessions/*.jsonl`
- Window terrain scanner: open windows via `pywinctl` → floor list
- `sprite_loader.py`: SpriteSheet + SpriteRegistry fully implemented

### Not yet wired / implemented
- `sprite_loader.py` exists but is **not yet imported into `overlay.py`** — Avatar still uses procedural sprites
- `AgentInfo` has no `skin` field yet — needed to assign sprite sheets per agent
- JPG → PNG conversion not done (transparent sprites need PNG)
- Windows click-through (`WS_EX_TRANSPARENT` via ctypes) — mouse clicks do not yet pass through
- macOS click-through (`NSWindow.ignoresMouseEvents` via pyobjc)
- UDP listener for Claude Code hooks (instant status updates vs polling)
- `config.json` for FPS, sprite assignments, scale factors

---

## Roadmap

### v0.2 — Sprite Integration & Click-through
- [ ] Convert sprite sheets to PNG (`python sprite_loader.py convert ...`)
- [ ] Add `skin: str = "amongo"` field to `AgentInfo`
- [ ] Import `SpriteRegistry` in `overlay.py`, pass to `Avatar`
- [ ] Replace procedural sprite in `Avatar.draw()` with `registry.get_photo()`
- [ ] Windows click-through via ctypes (code below)
- [ ] macOS click-through via pyobjc
- [ ] `config.json` loading

**Windows click-through snippet:**
```python
import ctypes, sys
if sys.platform == "win32":
    hwnd  = ctypes.windll.user32.GetParent(self.root.winfo_id())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20)
    # 0x80000 = WS_EX_LAYERED,  0x20 = WS_EX_TRANSPARENT
```

### v0.3 — Richer Agent Interaction
- [ ] UDP listener for instant Claude Code hook events (port 47200)
- [ ] Subagent spawn animation: child avatar falls from parent position
- [ ] Avatar-to-avatar interaction (walk toward each other when idle)
- [ ] Emotion bubbles: 💭 🔥 ✅ ❌ float above head
- [ ] Jump between window platforms (detect platform gaps)

### v0.4 — UX Polish
- [ ] System tray icon (show/hide, mute, quit — no right-click needed)
- [ ] Name tags that fade after idle timeout
- [ ] Optional sound effects (toggle in config)
- [ ] Drag-to-reposition HUD panel

### v0.5 — Tauri Port
- [ ] Port Canvas rendering to PixiJS / HTML5 Canvas inside Tauri webview
- [ ] Rust sidecar for faster OS window enumeration
- [ ] Cross-platform binary (no Python install required)
- [ ] Auto-update mechanism

---

## Git Setup

```bash
# First time — on your machine
cd zz_cli_avatars
git init
git add overlay.py sprite_loader.py claude_hooks_example.py requirements.txt CLAUDE.md TASKS.md AI_OVERLAY.md
git commit -m "feat: v0.1 baseline — transparent overlay, physics, sprite loader, session scanner"
git remote add origin https://github.com/<you>/ai-overlay.git
git push -u origin main

# On another machine
git clone https://github.com/<you>/ai-overlay.git
cd ai-overlay
pip install -r requirements.txt
python overlay.py
```

### Recommended `.gitignore`

```
__pycache__/
*.pyc
*.pyo
.env
assets/*.jpg        # keep only PNG in git
```

---

## Changelog

### v0.1 — 2026-05-14
**Added**
- `overlay.py` — full baseline: transparent tkinter overlay, physics engine,
  multi-avatar management, HUD panel, session scanner, window terrain scanner
- `sprite_loader.py` — `SpriteSheet` and `SpriteRegistry` classes;
  Stream Avatars-compatible row/column slicing with empty frame auto-detection
- `claude_hooks_example.py` — UDP notification helper for Claude Code hooks
- `requirements.txt`
- Demo mode: 4 animated agents cycling through all states when no Claude sessions found

**Sprite sheet analysis**
- `char_AmongoCat-2.jpg`: 192×240 px, 48×48 cell, 4 cols × 5 rows
- `meowatar_orig.jpg`: 240×300 px, 60×60 cell, 4 cols × 5 rows
- Both follow Stream Avatars row convention: idle(0), run(1), sit(2), stand(3), jump(4)

**Known issues at release**
- JPG sprites need PNG conversion before SpriteRegistry use
- `sprite_loader.py` not yet wired into `overlay.py`
- Windows click-through not yet implemented
- UDP hook listener not yet implemented
