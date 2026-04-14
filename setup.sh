#!/usr/bin/env bash
# memOS installer - gives Claude Code persistent memory via a local Obsidian-compatible vault.
#
# What this does:
#   1. Creates the vault folder (or uses your existing one)
#   2. Installs the save-to-memos.py hook into ~/.claude/hooks/
#   3. Patches ~/.claude/settings.json to wire the hook to Stop + SessionEnd
#   4. Sets MEMOS_VAULT in your shell profile
#
# Safe to re-run: existing hooks are left alone, only memOS entries are added.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_VAULT="$HOME/Documents/memOS"

echo
echo "==============================="
echo "  memOS - setup"
echo "==============================="
echo

# --- 1. Pick vault path -----------------------------------------------------
read -r -p "Vault path [$DEFAULT_VAULT]: " VAULT
VAULT="${VAULT:-$DEFAULT_VAULT}"
VAULT="${VAULT/#\~/$HOME}"

mkdir -p "$VAULT/Diary/sessions" "$VAULT/Projects" "$VAULT/Entities"
echo "vault ready at $VAULT"

# --- 2. Install hooks -------------------------------------------------------
HOOK_DIR="$HOME/.claude/hooks"
mkdir -p "$HOOK_DIR" "$HOOK_DIR/state"
cp "$REPO_DIR/hooks/save-to-memos.py"           "$HOOK_DIR/save-to-memos.py"
cp "$REPO_DIR/hooks/warm-context-from-memos.py" "$HOOK_DIR/warm-context-from-memos.py"
chmod +x "$HOOK_DIR/save-to-memos.py" "$HOOK_DIR/warm-context-from-memos.py"
echo "hooks installed at $HOOK_DIR/"

# --- 3. Patch settings.json --------------------------------------------------
SETTINGS="$HOME/.claude/settings.json"
if [[ ! -f "$SETTINGS" ]]; then
  echo '{}' > "$SETTINGS"
fi

python3 - "$SETTINGS" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
data = json.loads(p.read_text() or "{}")
hooks = data.setdefault("hooks", {})

STOP_CMD = "/usr/bin/python3 $HOME/.claude/hooks/save-to-memos.py"
END_CMD  = "/usr/bin/python3 $HOME/.claude/hooks/save-to-memos.py --end"
WARM_CMD = "/usr/bin/python3 $HOME/.claude/hooks/warm-context-from-memos.py"

def ensure(event, cmd, timeout, dedup_token):
    arr = hooks.setdefault(event, [])
    if not arr:
        arr.append({"hooks": []})
    group = arr[0]
    existing = [h.get("command","") for h in group.get("hooks", [])]
    if not any(dedup_token in c for c in existing):
        group.setdefault("hooks", []).append({
            "type": "command",
            "command": cmd,
            "timeout": timeout,
        })

ensure("Stop",         STOP_CMD, 10, "save-to-memos.py")
ensure("SessionEnd",   END_CMD,  15, "save-to-memos.py --end")
ensure("SessionStart", WARM_CMD, 10, "warm-context-from-memos.py")
p.write_text(json.dumps(data, indent=2))
print("settings.json patched")
PYEOF

# --- 4. Export MEMOS_VAULT ---------------------------------------------------
PROFILE=""
for candidate in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile"; do
  if [[ -f "$candidate" ]]; then
    PROFILE="$candidate"
    break
  fi
done

if [[ -n "$PROFILE" ]]; then
  if ! grep -q "MEMOS_VAULT=" "$PROFILE" 2>/dev/null; then
    printf '\n# memOS vault path (used by save-to-memos hook)\nexport MEMOS_VAULT="%s"\n' "$VAULT" >> "$PROFILE"
    echo "added MEMOS_VAULT to $PROFILE"
  else
    echo "MEMOS_VAULT already set in $PROFILE - skipping"
  fi
else
  echo "could not find a shell profile; add this line manually:"
  echo "  export MEMOS_VAULT=\"$VAULT\""
fi

# --- Done --------------------------------------------------------------------
cat <<EOF

Done.

Next steps:
  1. Open a new terminal (or: source "$PROFILE")
  2. Open the vault in Obsidian:  open -a Obsidian "$VAULT"
  3. Start a Claude Code session - every reply is auto-saved to:
        $VAULT/Diary/sessions/

Optional:
  - Claude Desktop: see docs/claude-desktop.md for MCP filesystem setup
  - Customize the graph/theme: drop snippets into $VAULT/.obsidian/snippets/

EOF
