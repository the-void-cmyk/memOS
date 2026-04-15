<pre>
 ╔══════════════════════════════════════════════════════════════╗
 ║                                                              ║
 ║      ███╗   ███╗███████╗███╗   ███╗ ██████╗ ███████╗         ║
 ║      ████╗ ████║██╔════╝████╗ ████║██╔═══██╗██╔════╝         ║
 ║      ██╔████╔██║█████╗  ██╔████╔██║██║   ██║███████╗         ║
 ║      ██║╚██╔╝██║██╔══╝  ██║╚██╔╝██║██║   ██║╚════██║         ║
 ║      ██║ ╚═╝ ██║███████╗██║ ╚═╝ ██║╚██████╔╝███████║         ║
 ║      ╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚══════╝         ║
 ║                                                              ║
 ║      > persistent memory for claude                          ║
 ║      > local vault · 2 hooks · 0 tokens                      ║
 ║                                                              ║
 ╚══════════════════════════════════════════════════════════════╝
</pre>

# memOS

**Persistent memory for Claude.** Every conversation is auto-saved into a local Obsidian-compatible vault. Claude reads it at the start of each session, so it actually remembers past work.

No API hacks, no cloud, no tokens burned polling. Just files, two hooks, and a folder.

---

## The problem

> *"I have to re-explain my project to ChatGPT every single time."*

LLMs don't have persistent memory by default. Context windows are long but session-scoped - close the tab and it's gone.

## The solution

A local vault of markdown files + three shell hooks:

- **Stop hook** fires after every assistant reply → appends new turns to `Diary/sessions/<date>.md`
- **SessionEnd hook** fires when you exit → writes a completion marker
- **SessionStart hook** (optional) fires at session start → auto-injects the project hub + last 3 session notes when your cwd matches a known wing

See [`docs/warm-context.md`](docs/warm-context.md) for how the SessionStart hook decides what to load.

Works with **Claude Code** (the CLI) via native hooks.

## What it looks like

![graph view](assets/graph.png)

Each node is a note. Each line is a wiki-link. Clusters = projects. Build it over weeks, scroll back through 2,000+ notes whenever you need to.

---

## Install (Claude Code - 60 seconds)

```bash
git clone https://github.com/the-void-cmyk/memOS.git
cd memOS
./setup.sh
```

What the installer does:

1. Creates your vault at `~/Documents/memOS` (or a path you choose)
2. Drops `save-to-memos.py` into `~/.claude/hooks/`
3. Patches `~/.claude/settings.json` to wire Stop + SessionEnd
4. Adds `MEMOS_VAULT` to your shell profile

Open a new terminal, start Claude Code in any project, and look inside `~/Documents/memOS/Diary/sessions/` - the conversation is there.

---

## How it actually works

```
┌────────────────┐     Stop hook      ┌────────────────┐
│  Claude Code   │ ─────────────────► │ save-to-memos.py │
│   (any proj)   │   (after reply)    └────────┬───────┘
└────────────────┘                             │
                                               ▼
                                   ┌───────────────────────┐
                                   │   Obsidian vault      │
                                   │   ~/Documents/memOS/   │
                                   │   └─ Diary/sessions/  │
                                   │   └─ Projects/        │
                                   │   └─ Entities/        │
                                   └───────────────────────┘
```

The hook is ~100 lines of Python. It reads Claude Code's session JSONL, diffs against a byte offset (so reruns are idempotent), and appends only the new turns.

**Zero LLM cost.** The hook is a plain Python script - no Claude involvement, no tokens.

## Opening a past session

Just ask:

> *"What did we decide about the auth flow last Tuesday?"*

Claude greps the vault, reads the relevant session notes, and answers. Or you browse `~/Documents/memOS` in Obsidian and read them yourself.

## Project structure (suggested)

```
memOS/
├── CLAUDE.md                 # vault-level instructions for Claude
├── MOC.md                    # map of content
├── Projects/<name>/          # per-project hub + notes by topic
├── Entities/                 # one note per person/service/tool
├── Diary/
│   └── sessions/             # auto-populated by the hook
└── .obsidian/
    └── snippets/             # optional CSS themes
```

---

## FAQ

**Does this work with ChatGPT / Gemini?**
Not out of the box. The hook uses Claude Code's native hook API. A similar approach would work for anything that exposes post-turn events, but you'd need to write the integration.

**Will this slow down my sessions?**
No. Hook runs in <50ms on a vault with 2,000+ notes.

**Does my conversation data leave my machine?**
No. Everything is local markdown files. Nothing is uploaded.

**What if I write sensitive stuff in a session?**
Redact or delete the session note. It's just a file.

**What about Claude's own native memory feature?**
Complementary. Native memory is per-project, Anthropic-hosted, opaque. memOS is your local, inspectable, portable copy.

---

## License

MIT. See [LICENSE](LICENSE).
