#!/usr/bin/env python3
"""
Save Claude Code conversation transcripts into an Obsidian-compatible vault.

Fires as:
  - Stop hook (after every assistant turn, appends new content)
  - SessionEnd hook (adds a completion marker, flips status, writes a drawer)

Both are idempotent. The Stop path is zero-LLM-cost (pure Python).
The SessionEnd path optionally spawns `claude -p` to write a knowledge drawer.

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
import re
import shutil
import subprocess
import sys
from pathlib import Path

VAULT_ENV = os.environ.get("MEMOS_VAULT")
if not VAULT_ENV:
    # Fail silent - don't block the hook chain.
    sys.exit(0)

VAULT = Path(VAULT_ENV).expanduser()
SESSIONS_DIR = VAULT / "Diary" / "sessions"
PROJECTS_DIR = VAULT / "Projects"
STATE_DIR = Path.home() / ".claude" / "hooks" / "state"
END_MODE = "--end" in sys.argv

ALIASES_FILE = PROJECTS_DIR / ".cwd-aliases.json"


# ---------------------------------------------------------------------------
# Wing detection
# ---------------------------------------------------------------------------

def _norm(s):
    """Strip dashes/underscores/spaces so 'mtl-metro-map' matches 'mtlmetromap'."""
    return "".join(c for c in s.lower() if c.isalnum())


def _load_aliases():
    """Load cwd-to-wing aliases from Projects/.cwd-aliases.json."""
    try:
        return json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def detect_wing(cwd_str):
    """Map a cwd path to a vault wing name.

    Resolution order:
      1. Explicit alias (Projects/.cwd-aliases.json)
      2. Existing wing folder (dash/underscore-insensitive)
      3. Fallback to cwd basename
    """
    tail = Path(cwd_str).name
    aliases = _load_aliases()
    # 1. Alias match on cwd basename or substring.
    if tail in aliases:
        return aliases[tail]
    for key, val in aliases.items():
        if key in cwd_str:
            return val
    # 2. Match against existing wing folders.
    if PROJECTS_DIR.exists():
        cwd_norm = _norm(cwd_str)
        tail_norm = _norm(tail)
        wings = [p.name for p in PROJECTS_DIR.iterdir() if p.is_dir()]
        for w in sorted(wings, key=len, reverse=True):
            if _norm(w) == tail_norm:
                return w
        for w in sorted(wings, key=len, reverse=True):
            if _norm(w) in cwd_norm:
                return w
    # 3. Fallback: cwd basename becomes the wing name.
    return tail or None


def ensure_wing_stub(wing):
    """Create Projects/<wing>/<wing>.md if missing so wikilinks resolve in the graph."""
    if not wing:
        return
    wing_dir = PROJECTS_DIR / wing
    wing_note = wing_dir / f"{wing}.md"
    if wing_note.exists():
        return
    wing_dir.mkdir(parents=True, exist_ok=True)
    wing_note.write_text(
        "---\n"
        "type: project\n"
        f"name: {wing}\n"
        "tags:\n"
        "  - project\n"
        f"  - {wing}\n"
        "---\n\n"
        f"# {wing}\n\n"
        "> Auto-created by memOS on first session.\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------

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

wing = detect_wing(cwd)
ensure_wing_stub(wing)

if not note.exists():
    project_fm = f'project: "[[{wing}]]"\n' if wing else ""
    wing_tag = f"  - {wing}\n" if wing else ""
    project_line = f"> project: [[{wing}]]\n\n" if wing else ""
    with note.open("w", encoding="utf-8") as f:
        f.write(
            "---\n"
            "type: session-log\n"
            f"session_id: {session_id}\n"
            f"date: {today}\n"
            f"cwd: {json.dumps(cwd)}\n"
            f"{project_fm}"
            "status: active\n"
            "tags:\n"
            "  - session-log\n"
            f"{wing_tag}"
            "---\n\n"
            f"# Session {today} - {short}\n\n"
            f"> cwd: `{cwd}`\n\n"
            f"{project_line}"
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

    # --- Knowledge drawer (optional, requires `claude` CLI) -------------------
    # Spawns a detached `claude -p --bare` to summarize the session into a
    # concise drawer note. Skipped if `claude` is not installed.
    if wing and shutil.which("claude"):
        drawers_dir = PROJECTS_DIR / wing / "drawers"
        drawers_dir.mkdir(parents=True, exist_ok=True)
        drawer_path = drawers_dir / f"{today}-{short}.md"
        if not drawer_path.exists():
            prompt = (
                "Read the session transcript below. Write a concise "
                "'knowledge drawer' note in markdown capturing what FUTURE "
                "sessions would need to know cold:\n"
                "- Decisions made and why (not what was done, why)\n"
                "- Architectural changes, new files/systems introduced\n"
                "- Gotchas, constraints, non-obvious behavior discovered\n"
                "Skip: pleasantries, tool noise, debugging dead-ends that "
                "went nowhere. If the session was trivial (UI tweaks, "
                "small fixes, chit-chat), output exactly: SKIP\n\n"
                f"Output format:\n"
                f"---\ntype: drawer\ndate: {today}\n"
                f"session: {short}\nproject: \"[[{wing}]]\"\n"
                f"tags:\n  - drawer\n  - {wing}\n---\n\n"
                f"# <short title>\n\n<1-3 paragraphs>\n\n"
                f"Part of [[{wing}]]\n"
            )
            try:
                transcript_text = note.read_text(encoding="utf-8")
                full_prompt = prompt + "\n\n=== SESSION TRANSCRIPT ===\n\n" + transcript_text
                log_path = STATE_DIR / f"drawer-{session_id}.log"
                tmp_path = drawer_path.with_suffix(".tmp")
                wrapper = (
                    f'claude -p --bare '
                    f'--append-system-prompt "You write terse knowledge drawers for an Obsidian vault. No fluff. Output SKIP for trivial sessions." '
                    f'{json.dumps(full_prompt)} > {json.dumps(str(tmp_path))} 2> {json.dumps(str(log_path))}; '
                    f'if grep -qx "SKIP" {json.dumps(str(tmp_path))}; then '
                    f'  rm -f {json.dumps(str(tmp_path))}; '
                    f'else '
                    f'  mv {json.dumps(str(tmp_path))} {json.dumps(str(drawer_path))}; '
                    f'fi'
                )
                subprocess.Popen(
                    ["bash", "-c", wrapper],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except Exception as e:
                with open(STATE_DIR / f"drawer-err-{session_id}.log", "w") as f:
                    f.write(str(e))

sys.exit(0)
