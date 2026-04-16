#!/usr/bin/env python3
"""
Warm the Claude Code session with relevant memOS context at startup.

When the session starts in a folder that matches a wing in the memOS vault,
inject the project hub + the last N session notes into the session context.
Keeps the payload small (~20 KB max) so the context window stays usable.

Fires as SessionStart hook. Zero LLM cost.

Environment:
  MEMOS_VAULT   Absolute path to the vault. Required.
  MEMOS_WARM_MAX_SESSIONS   Optional int, default 3.
  MEMOS_WARM_MAX_CHARS      Optional int, default 30000 (~7.5K tokens).

Reads hook payload JSON from stdin (session_id, cwd, ...).
Outputs JSON with additionalContext to inject into the session.
"""

import json
import os
import re
import sys
from pathlib import Path

VAULT_ENV = os.environ.get("MEMOS_VAULT") or os.environ.get("MEMX_VAULT")
if not VAULT_ENV:
    sys.exit(0)

VAULT = Path(VAULT_ENV).expanduser()
if not VAULT.exists():
    sys.exit(0)

MAX_SESSIONS = int(os.environ.get("MEMOS_WARM_MAX_SESSIONS", "3"))
MAX_CHARS = int(os.environ.get("MEMOS_WARM_MAX_CHARS", "30000"))

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

cwd = (payload.get("cwd") or os.getcwd() or "").lower()
if not cwd:
    sys.exit(0)

projects_dir = VAULT / "Projects"
if not projects_dir.exists():
    sys.exit(0)

# --- Load cwd-to-wing aliases (optional) ------------------------------------
aliases_file = projects_dir / ".cwd-aliases.json"
try:
    aliases = json.loads(aliases_file.read_text(encoding="utf-8"))
except Exception:
    aliases = {}


def _norm(s):
    return "".join(c for c in s.lower() if c.isalnum())


# --- Match the cwd to a wing (optional) --------------------------------------
cwd_tail = Path(cwd).name
matched_wing = None

# 1. Alias match
if cwd_tail in aliases:
    matched_wing = aliases[cwd_tail]
else:
    for key, val in aliases.items():
        if key in cwd:
            matched_wing = val
            break

# 2. Folder match (dash/underscore-insensitive)
if not matched_wing:
    wings = [p.name for p in projects_dir.iterdir() if p.is_dir()]
    tail_norm = _norm(cwd_tail)
    for w in sorted(wings, key=len, reverse=True):
        if _norm(w) == tail_norm:
            matched_wing = w
            break
    if not matched_wing:
        for w in sorted(wings, key=len, reverse=True):
            if w.lower() in cwd:
                matched_wing = w
                break

sessions_dir = VAULT / "Diary" / "sessions"

# --- Always: find the 3 most-recent session notes ----------------------------
recent_sessions = []
if sessions_dir.exists():
    try:
        recent_sessions = sorted(
            sessions_dir.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:3]
    except Exception:
        recent_sessions = []

last_session = recent_sessions[0] if recent_sessions else None

# If there's no wing match AND no recent sessions, nothing useful to inject.
if not matched_wing and not recent_sessions:
    sys.exit(0)


def first_user_gist(path):
    """Pull the first substantive user message as a one-line gist."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    turns = re.split(r"^### User _[^_]+_\s*$", text, flags=re.MULTILINE)
    for turn in turns[1:]:
        for raw in turn.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("<") or line.startswith("---"):
                continue
            if line.startswith("<command-") or line.startswith("<local-"):
                continue
            line = re.sub(r"^[#>*\-\d.]+\s*", "", line)
            if len(line) < 4:
                continue
            return line[:140]
    return ""


def session_meta(path):
    """Return (date, short_id, cwd_tail) from a session file."""
    name = path.stem
    m = re.match(r"(\d{4}-\d{2}-\d{2})-([0-9a-f]+)", name)
    date = m.group(1) if m else ""
    short_id = m.group(2) if m else name
    cwd_tail = ""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:2048]
        cm = re.search(r"^cwd:\s*\"?([^\"\n]+)\"?", head, re.MULTILINE)
        if cm:
            cwd_tail = Path(cm.group(1).strip()).name
    except Exception:
        pass
    return date, short_id, cwd_tail


parts = []
parts.append("# memOS - warm context")
parts.append("")
parts.append(
    "You have persistent memory from past Claude Code sessions. "
    "The notes below were auto-loaded from the user's local memOS vault "
    "so this session starts with continuity, not from scratch."
)
parts.append("")
parts.append(
    "**On your FIRST turn of this session, echo the 'Last 3 sessions' "
    "digest back verbatim as your opening lines**, so the user can see "
    "on screen what warm context was loaded. Format it as a compact "
    "numbered list (same 3 lines shown below), prefixed with a single "
    "header like `**memOS - warm context loaded:**`. After the list, "
    "add one short sentence naming what was most recently worked on, "
    "then wait for the user. Do not add other commentary."
)
parts.append("")
parts.append(
    "**Use this context as background** when answering. If the user asks "
    "about past work not covered here, `Grep` the full vault at "
    f"`{VAULT}` - especially `Diary/sessions/` and `Projects/<wing>/`."
)
parts.append("")

# --- Section 0: quick digest of last 3 sessions (ALWAYS shown) ---------------
if recent_sessions:
    parts.append("## Last 3 sessions - quick digest")
    parts.append("")
    for idx, note in enumerate(recent_sessions, 1):
        date, short_id, cwd_tail = session_meta(note)
        gist = first_user_gist(note) or "(no user prompt found)"
        tag = f"**{date}** `{short_id}`"
        if cwd_tail:
            tag += f" _{cwd_tail}_"
        marker = " [most recent]" if idx == 1 else ""
        parts.append(f"{idx}. {tag}{marker} - {gist}")
    parts.append("")

# --- Section 1: most recent session (ALWAYS shown) ---------------------------
if last_session:
    try:
        body = last_session.read_text(encoding="utf-8", errors="replace")
    except Exception:
        body = ""
    # Keep head (frontmatter + first turn) and tail (last ~4K chars).
    if len(body) > 6000:
        snippet = body[:2000] + "\n\n...[truncated]...\n\n" + body[-4000:]
    else:
        snippet = body
    parts.append("## Previous session (most recent)")
    parts.append("")
    parts.append(
        f"File: `Diary/sessions/{last_session.name}` "
        f"(showing head + tail if long - grep this file for full content)"
    )
    parts.append("")
    parts.append(snippet)
    parts.append("")

# --- Section 2: wing-specific context when cwd matches -----------------------
if matched_wing:
    wing_dir = projects_dir / matched_wing
    hub = wing_dir / f"{matched_wing}.md"

    parts.append(f"## Current wing: {matched_wing}")
    parts.append("")
    parts.append(
        f"Your working directory matches the `{matched_wing}` project in memOS. "
        f"The hub and latest wing sessions are pre-loaded below."
    )
    parts.append("")

    if hub.exists():
        try:
            parts.append(f"### Hub: {hub.name}")
            parts.append("")
            parts.append(hub.read_text(encoding="utf-8", errors="replace"))
            parts.append("")
        except Exception:
            pass

    if sessions_dir.exists():
        candidates = []
        for note in sorted(sessions_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            if last_session and note == last_session:
                # Skip - already loaded above.
                continue
            try:
                head = note.read_text(encoding="utf-8", errors="replace")[:4096]
            except Exception:
                continue
            m = re.search(r"^cwd:\s*(.+)$", head, re.MULTILINE)
            if not m:
                continue
            note_cwd = m.group(1).strip().strip('"').lower()
            if matched_wing.lower() in note_cwd:
                candidates.append(note)
            if len(candidates) >= MAX_SESSIONS:
                break

        if candidates:
            parts.append(f"### Recent sessions in {matched_wing} (latest {len(candidates)})")
            parts.append("")
            for note in candidates:
                try:
                    body = note.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                parts.append(f"#### {note.name}")
                parts.append("")
                parts.append(body)
                parts.append("")

parts.append("---")
parts.append(f"End of memOS warm context. Full vault: `{VAULT}`")

context = "\n".join(parts)

# --- Budget: trim to MAX_CHARS -----------------------------------------------
if len(context) > MAX_CHARS:
    context = (
        context[:MAX_CHARS]
        + f"\n\n*[warm context truncated at {MAX_CHARS} chars - grep the vault for more]*"
    )

# --- Emit as Claude Code SessionStart hook output ----------------------------
output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context,
    }
}
print(json.dumps(output))
sys.exit(0)
