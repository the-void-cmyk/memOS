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

# --- Match the cwd to a wing (optional) --------------------------------------
wings = [p.name for p in projects_dir.iterdir() if p.is_dir()]
matched_wing = None
# Longest wing name first so e.g. "sunlouvre-staging" matches "sunlouvre".
for w in sorted(wings, key=len, reverse=True):
    if w.lower() in cwd:
        matched_wing = w
        break

sessions_dir = VAULT / "Diary" / "sessions"

# --- Always: find the single most-recent session note ------------------------
last_session = None
if sessions_dir.exists():
    try:
        last_session = max(
            sessions_dir.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            default=None,
        )
    except Exception:
        last_session = None

# If there's no wing match AND no last session, nothing useful to inject.
if not matched_wing and not last_session:
    sys.exit(0)

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
    "**Use this context as background** when answering. If the user asks "
    "about past work not covered here, `Grep` the full vault at "
    f"`{VAULT}` - especially `Diary/sessions/` and `Projects/<wing>/`."
)
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
