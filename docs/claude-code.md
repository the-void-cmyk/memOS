# Using memOS with Claude Code

The automated install (`./setup.sh` from the repo root) handles everything. This doc covers what the installer does, how to customize, and how to uninstall.

> **Obsidian is optional.** The hook writes plain markdown files and Claude reads/writes them directly. Obsidian is only needed if you want the graph view, backlinks, or pretty browsing. Skip it and the memory loop still works.

## What the installer does

1. Creates vault folders at `$MEMOS_VAULT` (default `~/Documents/memOS`):
   - `Diary/sessions/` - auto-populated by the hook
   - `Projects/`, `Entities/` - for your own notes
2. Copies `hooks/save-to-memos.py` to `~/.claude/hooks/save-to-memos.py`
3. Patches `~/.claude/settings.json` to register two hooks:
   - **Stop** - fires after every assistant turn, appends new turns
   - **SessionEnd** - fires on clean exit, writes a completion marker
4. Appends `export MEMOS_VAULT="..."` to your shell profile

All changes are additive. Existing hooks and settings are preserved.

## Manual install

If you prefer to wire it up yourself:

```bash
# 1. Pick a vault path and export it
export MEMOS_VAULT="$HOME/Documents/memOS"
mkdir -p "$MEMOS_VAULT/Diary/sessions"

# 2. Drop the hook in place
mkdir -p ~/.claude/hooks
cp hooks/save-to-memos.py ~/.claude/hooks/
chmod +x ~/.claude/hooks/save-to-memos.py

# 3. Add to ~/.claude/settings.json (merge with existing hooks)
```

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [
        { "type": "command",
          "command": "/usr/bin/python3 $HOME/.claude/hooks/save-to-memos.py",
          "timeout": 10 }
      ]}
    ],
    "SessionEnd": [
      { "hooks": [
        { "type": "command",
          "command": "/usr/bin/python3 $HOME/.claude/hooks/save-to-memos.py --end",
          "timeout": 15 }
      ]}
    ]
  }
}
```

## What ends up in the vault

Each session produces one markdown file: `Diary/sessions/YYYY-MM-DD-<short-id>.md`.

Structure:

```markdown
---
type: session-log
session_id: 01932abc-...
date: 2026-04-14
cwd: /Users/you/projects/your-app
status: active
tags:
  - session-log
---

# Session 2026-04-14 - 01932abc

> cwd: `/Users/you/projects/your-app`

### User _2026-04-14T10:22:41Z_

What did we decide about the auth flow last week?

### Assistant _2026-04-14T10:22:44Z_

Looking at the session notes... `[tool: Read]`

We agreed to use Clerk instead of rolling our own, because...
```

## Telling Claude to use the vault

Add a `CLAUDE.md` at your vault root (or at a project root) with something like:

```markdown
# Memory

Before answering questions about past work, check:
- `~/Documents/memOS/Diary/sessions/` for recent conversations
- `~/Documents/memOS/Projects/<project>/` for project notes
- `~/Documents/memOS/Entities/` for people, services, tools

Prefer reading the vault over guessing.
```

Claude Code reads this at session start. That's how the rehydration loop closes.

## Uninstall

```bash
# Remove hook
rm ~/.claude/hooks/save-to-memos.py

# Edit ~/.claude/settings.json and delete the two blocks referencing save-to-memos.py

# Optionally remove vault
rm -rf "$MEMOS_VAULT"

# Optionally remove MEMOS_VAULT line from your shell profile
```

Your other hooks and settings are untouched.

## Customize

**Different save format:** edit `~/.claude/hooks/save-to-memos.py`. The `extract_text()` function decides what content makes it to the note. Tool calls are currently collapsed to `` `[tool: name]` `` placeholders - you can expand them if you want full traces.

**Exclude sensitive conversations:** add a check at the top of the script for `cwd` patterns you want to skip:

```python
if "/secrets/" in cwd or "/keys/" in cwd:
    sys.exit(0)
```

**Different file naming:** change the `note = SESSIONS_DIR / f"{today}-{short}.md"` line.
