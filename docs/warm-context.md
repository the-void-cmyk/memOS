# Warm Context

The optional **SessionStart hook** that auto-loads relevant memOS notes into a new Claude Code session when the working directory matches a known project in your vault.

## Why

Without warm context, every new session starts with zero knowledge of your projects. Claude has to `Grep` the vault as soon as you ask something about past work - adds one round-trip and requires you to phrase questions that trigger a search.

With warm context, Claude already has the project hub and your last few sessions loaded at turn 1. Ask about past work without thinking.

## What gets loaded

When you start Claude Code in a folder whose path contains a wing name (e.g. `~/Local Sites/sunlouvre-dev-local` matches the `sunlouvre` wing), the hook injects:

1. **`Projects/<wing>/<wing>.md`** - the project hub (summary, room list, Dataview queries)
2. **The latest 3 session notes** from `Diary/sessions/` whose `cwd:` frontmatter contains the wing name
3. A trailing note reminding Claude to `Grep` the vault for anything beyond what's loaded

Everything else stays on disk, reachable via `Grep` when needed.

## What *doesn't* get loaded

- Every drawer in the wing (potentially hundreds of KB of src dumps)
- Unrelated wings
- The full KG entity list
- Session notes older than the top 3

## Budget

Capped at **30,000 characters (~7,500 tokens)** per session start. Configurable via `MEMOS_WARM_MAX_CHARS`. The hub + 3 session notes usually comes in well under that; big sessions get the tail truncated with a note explaining how to grep for more.

## Cost

**Zero LLM cost.** The hook is Python reading local files. The only "cost" is the ~7K tokens consumed in your context window for every new session - trading that for skipping `Grep` round-trips is a fair trade for any actively-worked project.

If you want to pay **even less**, set `MEMOS_WARM_MAX_CHARS=10000` to cap at ~2,500 tokens (hub only, maybe one session).

If you want to pay **nothing**, don't install the warm-context hook. The core memory loop (Stop + SessionEnd) still works fine without it - you just lose the pre-loading convenience.

## When does it fire?

Only at session start, only if:

- `MEMOS_VAULT` env var is set
- The vault contains a `Projects/<wing>/` folder whose name appears in the session's working directory
- The cwd is non-empty

If any check fails, the hook exits silently - no context injected, no error surfaced.

## How wing matching works

The hook iterates `Projects/<name>/` folders in your vault, sorts by name length (longest first), and checks if the name appears anywhere in the lowercased cwd. Examples:

| cwd | matched wing |
|---|---|
| `~/Local Sites/sunlouvre-dev-local` | `sunlouvre` |
| `~/Documents/PROJECTS/demeterrr` | `demeterrr` |
| `/Volumes/nex/decahedron 82` | *(no match - wing is called `octahedron`)* |
| `~/Documents/PROJECTS/memOS` | *(no match - no `memOS` wing)* |

Longest-name-first ordering means that if you had both `sunlouvre` and `sunlouvre-staging` wings, working in the staging folder correctly matches the staging wing.

**If a folder is misaligned** (like decahedron → octahedron above), either:

1. Rename the folder, or
2. Create an alias wing folder (empty `Projects/decahedron/` with a README that says "see octahedron"), or
3. Live with it and grep when needed

## Install

The `setup.sh` installer wires this up automatically. To wire it manually, add this block to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "MEMOS_VAULT=\"$HOME/Documents/memOS\" /usr/bin/python3 $HOME/.claude/hooks/warm-context-from-memos.py",
        "timeout": 10
      }]
    }]
  }
}
```

Replace the vault path with yours. The hook is idempotent - it reads files but never writes anything.

## Troubleshooting

**Warm context doesn't seem to load.**
Check three things:

1. `echo $MEMOS_VAULT` returns a valid path
2. Your cwd actually contains a wing name (run `ls $MEMOS_VAULT/Projects/` and check)
3. Test manually: `echo '{"cwd":"/your/cwd"}' | python3 ~/.claude/hooks/warm-context-from-memos.py`

If the test pipe returns an empty string, the hook found no match.

**Too much context getting loaded.**
Set `MEMOS_WARM_MAX_CHARS=10000` in your shell profile. Or set `MEMOS_WARM_MAX_SESSIONS=1` to cap the session history at one note.

**I don't want warm context for one specific project.**
Rename the wing folder to something the cwd doesn't match, or add an early-exit condition at the top of the hook.
