# Claude Code Hooks Integration

By default, CLI Avatars polls Claude Code session files every **2 seconds**. This works for most use cases but introduces a small lag between what the agent is doing and what the avatar shows.

For **instant** status updates, you can wire in Claude Code hooks via UDP.

---

## How It Works

Claude Code supports **hooks** — shell commands (or Python scripts) that run automatically at specific points in the agent lifecycle:

- `PreToolUse` — fires before each tool call
- `PostToolUse` — fires after each tool call completes
- `Stop` — fires when the agent finishes a turn

`claude_hooks_example.py` (included in this repo) is a hook script that sends a tiny UDP packet to CLI Avatars on each event. CLI Avatars (once the UDP listener is wired in v0.5) will receive these packets and update avatar status immediately.

---

## Current Status

> **The UDP listener is not yet implemented in CLI Avatars** (planned for v0.5).  
> The `claude_hooks_example.py` file is ready and documents the protocol.  
> Until v0.5 ships, the overlay uses 2-second polling instead.

---

## Setup (for when v0.5 ships)

### Step 1 — Copy the hook script to your project

```bash
cp claude_hooks_example.py /path/to/your/project/.claude/hooks/overlay_hook.py
```

Or copy it to `~/.claude/hooks/` to apply it globally to all Claude Code sessions.

### Step 2 — Register it in your Claude Code hooks config

In your project's `.claude/settings.json` (or `~/.claude/settings.json` for global):

```json
{
  "hooks": {
    "PreToolUse": [
      { "command": "python .claude/hooks/overlay_hook.py pre_tool" }
    ],
    "PostToolUse": [
      { "command": "python .claude/hooks/overlay_hook.py post_tool" }
    ],
    "Stop": [
      { "command": "python .claude/hooks/overlay_hook.py stop" }
    ]
  }
}
```

### Step 3 — Run CLI Avatars

```bash
python overlay.py
```

The overlay listens on UDP port **47200** for hook events and updates avatar status immediately on each tool call.

---

## UDP Packet Format

Each packet is a UTF-8 JSON string:

```json
{ "event": "pre_tool",  "tool": "Bash",  "session_id": "abc123" }
{ "event": "post_tool", "tool": "Read",  "session_id": "abc123" }
{ "event": "stop",      "session_id": "abc123" }
```

| Field | Values | Meaning |
|-------|--------|---------|
| `event` | `pre_tool`, `post_tool`, `stop` | Lifecycle point |
| `tool` | `Bash`, `Read`, `Write`, `Edit`, `Grep`, `Task`, … | Tool name (only on `pre/post_tool`) |
| `session_id` | UUID string | Matches the agent's JSONL filename |

The overlay maps `session_id` to the right avatar and updates its status:
- `pre_tool` → `busy` (with tool name label)
- `post_tool` → `thinking` (processing result)
- `stop` → `idle` (turn complete, waiting)

---

## Why Hooks vs Polling

| Method | Latency | Setup |
|--------|---------|-------|
| Polling (default) | ~2 seconds | None — works out of the box |
| Hooks (UDP) | ~50ms | Copy one file + edit settings.json |

Polling is good enough for casual use. Hooks make the animation snap to the agent's actual state instantly — useful if you're watching the overlay closely or streaming.

---

## Troubleshooting

**Avatar doesn't update faster after setting up hooks:**
- The UDP listener requires CLI Avatars v0.5+. Check which version you're running (see the docstring at the top of `overlay.py`).

**Hook script fails with "connection refused":**
- Make sure CLI Avatars is already running before triggering the hook.
- Hooks fire even if no listener is on port 47200 — they silently drop the packet, so this won't break Claude Code.

**I want a different port:**
- Change `UDP_PORT = 47200` at the top of both `claude_hooks_example.py` and the listener section in `overlay.py`.
