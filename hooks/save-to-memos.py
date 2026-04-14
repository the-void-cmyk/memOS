#!/usr/bin/env python3
"""
Save Claude Code conversation transcripts into an Obsidian-compatible vault.

Fires as:
  - Stop hook (after every assistant turn, appends new content)
  - SessionEnd hook (adds a completion marker, flips status)

Both are idempotent and zero-LLM-cost (pure Python).

Usage (from Claude Code hooks):
  save-to-memos.py           # Stop mode (default)
  save-to-memos.py --end     # SessionEnd mode

Environment:
  MEMOS_VAULT   Absolute path to the vault root. Required.
               Example: export MEMOS_VAULT="$HOME/Documents/memOS"

Reads the hook payload JSON from stdin (session_id, transcript_path, cwd).
"""

import datetime
import json
import os
import sys
from pathlib import Path

VAULT_ENV = os.environ.get("MEMOS_VAULT")
if not VAULT_ENV:
    # Fail silent - don't block the hook chain.
    sys.exit(0)

VAULT = Path(VAULT_ENV).expanduser()
SESSIONS_DIR = VAULT / "Diary" / "sessions"
STATE_DIR = Path.home() / ".claude" / "hooks" / "state"
END_MODE = "--end" in sys.argv

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

session_id = payload.get("session_id") or ""
transcript = payload.get("transcript_path") or ""
cwd = payload.get("cwd") or os.getcwd()

if not session_id or not transcript or not Path(transcript).exists():
    sys.exit(0)

SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)

today = datetime.date.today().isoformat()
short = session_id[:8]
note = SESSIONS_DIR / f"{today}-{short}.md"
offset_file = STATE_DIR / f"memos-{session_id}.offset"

if not note.exists():
    with note.open("w", encoding="utf-8") as f:
        f.write(
            "---\n"
            "type: session-log\n"
            f"session_id: {session_id}\n"
            f"date: {today}\n"
            f"cwd: {json.dumps(cwd)}\n"
            "status: active\n"
            "tags:\n"
            "  - session-log\n"
            "---\n\n"
            f"# Session {today} - {short}\n\n"
            f"> cwd: `{cwd}`\n\n"
        )

try:
    offset = int(offset_file.read_text())
except Exception:
    offset = 0

with open(transcript, "rb") as f:
    f.seek(offset)
    raw = f.read()
    new_offset = f.tell()


def extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype == "tool_use":
                name = block.get("name", "tool")
                parts.append(f"`[tool: {name}]`")
        return "\n".join(p for p in parts if p)
    return ""


if raw:
    lines = raw.decode("utf-8", errors="replace").splitlines()
    with note.open("a", encoding="utf-8") as out:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            role = obj.get("type") or obj.get("role") or ""
            msg = obj.get("message")
            if not isinstance(msg, dict):
                continue
            text = extract_text(msg.get("content"))
            text = text.strip()
            if not text:
                continue
            if role == "user":
                label = "User"
            elif role == "assistant":
                label = "Assistant"
            else:
                label = role.capitalize() or "Message"
            ts = obj.get("timestamp", "")
            ts_str = f" _{ts}_" if ts else ""
            out.write(f"### {label}{ts_str}\n\n{text}\n\n")
    offset_file.write_text(str(new_offset))

if END_MODE:
    ended = datetime.datetime.now().isoformat(timespec="seconds")
    with note.open("a", encoding="utf-8") as out:
        out.write(f"\n---\n\n*Session ended {ended}.*\n")
    try:
        body = note.read_text(encoding="utf-8")
        body = body.replace("status: active", "status: completed", 1)
        note.write_text(body, encoding="utf-8")
    except Exception:
        pass
    try:
        offset_file.unlink()
    except Exception:
        pass

sys.exit(0)
