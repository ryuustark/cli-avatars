#!/usr/bin/env python3
"""
Claude Code Hooks integration example
Place this in your project as .claude/hooks/notify_overlay.py
then register in settings.json:

{
  "hooks": {
    "PostToolUse":  [{"command": "python .claude/hooks/notify_overlay.py tool_use $TOOL_NAME"}],
    "Stop":         [{"command": "python .claude/hooks/notify_overlay.py done"}],
    "SubagentStart":[{"command": "python .claude/hooks/notify_overlay.py subagent_start"}],
    "SubagentStop": [{"command": "python .claude/hooks/notify_overlay.py subagent_stop"}]
  }
}
"""

import sys
import socket
import json
import time

OVERLAY_HOST = "127.0.0.1"
OVERLAY_PORT = 47200   # overlay listens on this UDP port

def notify(event: str, data: dict = None):
    payload = json.dumps({
        "event": event,
        "data":  data or {},
        "ts":    time.time(),
    }).encode()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.sendto(payload, (OVERLAY_HOST, OVERLAY_PORT))
        except Exception as e:
            print(f"[hooks] overlay notify failed: {e}")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(0)
    event = args[0]
    extra = {"tool_name": args[1]} if len(args) > 1 else {}
    notify(event, extra)
    print(f"[hooks] sent: {event} {extra}")
