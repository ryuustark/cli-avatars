---
type: tasks
project: "[[Project - CLI Avatars]]"
status: active
tags: [cli-avatars, tasks, development]
updated: 2026-05-14
---

# CLI Avatars — Task Board

> Live task list for the `zz_cli_avatars/` overlay project.
> Full context: [[Project - CLI Avatars]] · Architecture: `CLAUDE.md` · Reference: `AI_OVERLAY.md`

---

## 🤖 Orchestrator Queue

> Tagged `<!-- ORCHESTRATOR: ready -->` — picked up by nightly orchestrator, one per run.
> These are small, bounded code tasks. Bubble handles docs (tagged `<!-- BUBBLE: fix -->`).

- [x] Add VERSION constant to overlay.py <!-- ORCHESTRATOR: ready -->
  - Context: overlay.py has no version constant. The project is at v0.4 per CLAUDE.md and the project note.
  - Acceptance: Add `VERSION = "0.4"` as a module-level constant near the top of overlay.py (after imports, before class definitions). No other changes.
  - Guardrail: Only modify overlay.py. Do not change any logic, class, or function. One line added.

- [ ] Add config.json loader stub to overlay.py <!-- ORCHESTRATOR: ready -->
  - Context: The v0.4 roadmap calls for a config.json with fps, scale, and skins keys. overlay.py has no config loading yet.
  - Acceptance: Add a `load_config()` function that reads `config.json` from the same directory as overlay.py, returns a dict, and silently returns `{}` if the file is missing. Call it at the start of `OverlayApp.__init__()` and store the result as `self.config`. Do not yet use the config values anywhere else.
  - Guardrail: Only modify overlay.py. Do not change existing behavior. The overlay must still run correctly if config.json is absent.

---

## 📝 Documentation & Presentation Trail

> Bubble picks **one** item per run. Do not batch. Each item is one file, one change.
> Tag: `<!-- BUBBLE: fix -->`

- [ ] Reconcile stale checkboxes — check off v0.2/v0.3/v0.4 items already done per `Project - CLI Avatars.md` feature table (sprite_loader wired, click-through, HUD, system tray) <!-- BUBBLE: fix -->
- [ ] Update `CLAUDE.md` Current State section: change "v0.1" references to "v0.4 (functional)" and remove "not yet wired" notes that are now done <!-- BUBBLE: fix -->
- [ ] Fix README clone URL: replace `your-username/cli-avatars` with `ryuustark/RuneIsaRaido` subfolder path, add note "(standalone repo coming)" <!-- BUBBLE: fix -->
- [ ] Add "Download" section to README after Quick Start — GitHub Releases as distribution channel, placeholder: `[Download latest release →](https://github.com/ryuustark/RuneIsaRaido/releases)` <!-- BUBBLE: fix -->
- [ ] Add archive notice to top of `AI_OVERLAY.md`: "This file documents v0.1. The project is now at v0.4. See `CLAUDE.md` and `overlay.py` for current state." <!-- BUBBLE: fix -->
- [ ] Remove embedded source code blocks from `AI_OVERLAY.md` (sections 7–9: overlay.py, sprite_loader.py, claude_hooks_example.py) — replace each with one line: "See `<filename>` in the project root." <!-- BUBBLE: fix -->
- [ ] Add Changelog section to README (after Roadmap): summarize v0.1→v0.4 milestones in 4 bullet points <!-- BUBBLE: fix -->
- [ ] Create `docs/download.md`: install from source + "Prebuilt Windows executable: see GitHub Releases" + link placeholder <!-- BUBBLE: fix -->
- [ ] Add version + Windows badges to README header: `![version](https://img.shields.io/badge/version-v0.4-blue)` `![platform](https://img.shields.io/badge/platform-Windows-lightgrey)` <!-- BUBBLE: fix -->
- [ ] Tighten `CLAUDE.md` Key Files table: remove `assets/` row (assets live in `Sprites/`), add `gen_ponmi.py` row, update architecture notes to mention skin picker and hue rotation <!-- BUBBLE: fix -->

---

## ✅ Done (v0.1 Baseline)

- [x] Full-screen transparent tkinter overlay (always on top)
- [x] Physics engine: gravity, floor collision, wall bounce, idle pauses, status-reactive speed
- [x] Procedural 8×8 pixel sprite renderer (no external assets needed)
- [x] Multi-avatar management (spawn/remove as sessions appear/disappear)
- [x] HUD panel top-left: agent count, busy/thinking/subagent summary
- [x] Claude Code session scanner (`~/.claude/projects/*/sessions/*.jsonl`)
- [x] Window terrain scanner (open windows → floor platforms via pywinctl)
- [x] Demo mode: 4 agents cycling all states when no real sessions found
- [x] `sprite_loader.py`: SpriteSheet + SpriteRegistry fully implemented
- [x] `claude_hooks_example.py`: UDP notification helper

---

## 🔴 v0.2 — Sprite Integration & Click-Through

### Sprite pipeline

- [ ] **Convert JPG sprite sheets to PNG**
  - `python sprite_loader.py convert char_AmongoCat-2.jpg assets/amongo.png`
  - `python sprite_loader.py convert meowatar_orig.jpg assets/meowatar.png`
  - After converting: open in GIMP/Aseprite and remove solid background (make transparent)

- [ ] **Add `skin` field to `AgentInfo`**
  - `skin: str = "amongo"` in the `@dataclass` in `overlay.py`
  - Demo agents each get a different skin assigned

- [ ] **Import and wire `SpriteRegistry` into `overlay.py`**
  - `from sprite_loader import SpriteRegistry`
  - Instantiate as `REGISTRY = SpriteRegistry()` global
  - At startup (after tkinter root created): load sheets into REGISTRY with fallback if PNGs missing

- [ ] **Pass registry to `Avatar.__init__()`**
  - Add `registry: SpriteRegistry` param, store as `self.registry`
  - Update `OverlayApp._tick()` to pass registry when spawning new avatars

- [ ] **Replace procedural sprite in `Avatar.draw()`**
  - Call `self.registry.get_photo(self.agent.skin, self.agent.status, self.frame)`
  - Keep `make_photo()` as fallback when registry returns None (no PNG loaded)
  - Resize `AVATAR_W`/`AVATAR_H` constants to match actual cell size (48×48 or 60×60)

### Click-through (Windows)

- [ ] **Apply `WS_EX_TRANSPARENT` after window creation**
  - File: `overlay.py`, in `OverlayApp.__init__()` after `overrideredirect(True)`
  - Guard: `if sys.platform == "win32":`
  - Code:
    ```python
    import ctypes, sys
    hwnd  = ctypes.windll.user32.GetParent(self.root.winfo_id())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20)
    ```
  - Note: right-click to quit still works via canvas binding; left-click passes through to apps below

### Config

- [ ] **Create `config.json` loader**
  - Schema: `{ "fps": 20, "scale": 1.0, "skins": { "demo_0": "amongo", "demo_1": "meowatar" } }`
  - Load at startup in `OverlayApp.__init__()`, silently skip if file missing
  - Apply `fps` to `OVERLAY_FPS`, `scale` to registry `load()` calls

---

## 🟠 v0.3 — Richer Agent Interaction

- [ ] **UDP listener for instant hook events**
  - Add `UDPListener` thread in `overlay.py` listening on port 47200
  - Parse events from `claude_hooks_example.py` and update `AgentInfo` directly (bypass poll delay)

  **Available Claude Code hooks (all safe if script exits 0):**

  | Hook | When | Can block? |
  |------|------|-----------|
  | `PreToolUse` | before each tool call | yes (exit ≠ 0 blocks) |
  | `PostToolUse` | after tool completes | no |
  | `Stop` | turn finished | no |
  | `Notification` | push notification sent | no |
  | `UserPromptSubmit` | user hits submit | yes (can modify input) |

  **Proposed avatar action map:**

  | Event | Payload | Avatar action |
  |-------|---------|---------------|
  | `PreToolUse` — Bash | tool name | run animation, speed boost |
  | `PreToolUse` — Read | tool name | lean / open-book pose |
  | `PreToolUse` — Edit/Write | tool name | pencil pose |
  | `PreToolUse` — Grep/Glob | tool name | crouch / search pose |
  | `PreToolUse` — Agent | tool name | look sideways (subagent spawn hint) |
  | `PostToolUse` | tool name + exit code | small bounce (success) or wince (error) |
  | `Stop` | — | sit down, yawn, go idle |
  | `Notification` | message | wave arms, speech bubble |
  | `UserPromptSubmit` | — | snap to attention |

- [ ] **Subagent spawn animation**
  - On `subagent_start` event: spawn child Avatar at parent's x/y position
  - Child starts with `vy = JUMP_VEL` (falls from parent)
  - Link child to parent with a small line drawn in `draw_hud`

- [ ] **Avatar-to-avatar interaction**
  - When two idle avatars are within 60px: both stop and face each other for 2–4s
  - Emit a small speech bubble `💬` above both

- [ ] **Emotion bubbles**
  - Float above head for 1.5s then fade: 💭 thinking · 🔥 busy · ✅ done · ❌ error
  - Trigger on status transitions

- [ ] **Jump between window platforms**
  - When avatar reaches a floor edge: check if adjacent platform is within jump range
  - Calculate jump velocity to land on target; execute jump animation (row 4)

---

## 🟡 v0.4 — UX Polish

- [ ] **System tray icon** (show/hide, mute, quit)
  - Use `pystray` library: `pip install pystray`
  - Menu: Toggle Overlay / Mute Sounds / Quit

- [ ] **Name tags fade after idle timeout**
  - Track `last_active_t` on Avatar
  - After 30s idle: fade label alpha to 30% via canvas `stipple`

- [ ] **Optional sound effects**
  - Short blip on status change (busy → done)
  - Toggle via config or system tray menu
  - Use `playsound` or `winsound` (Windows only)

- [ ] **Draggable HUD panel**
  - Bind `<B1-Motion>` on HUD canvas items to move the panel

---

## 🔵 v0.5 — Tauri Port

- [ ] **Port rendering to PixiJS / HTML5 Canvas inside Tauri webview**
- [ ] **Rust sidecar for window enumeration** (faster than pywinctl)
- [ ] **Cross-platform binary** (no Python install required)
- [ ] **Auto-update mechanism**

---

## Reference

| Doc | Path |
|-----|------|
| Full project reference (v0.1) | `AI_OVERLAY.md` |
| Claude Code project guide | `CLAUDE.md` |
| Sprite sheet format & Stream Avatars convention | `AI_OVERLAY.md` → Sprite Sheet Format |
| Python concepts glossary | `AI_OVERLAY.md` → Python Concepts Glossary |
