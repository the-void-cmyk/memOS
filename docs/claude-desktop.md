# Using memOS with Claude Desktop

Claude Desktop doesn't have filesystem access by default. You give it access via the **Filesystem MCP server** - one config file, one restart, done.

After this, Claude Desktop can read and write the same memOS vault as Claude Code. The two stay in sync because they edit the same `.md` files.

> **Obsidian is optional** for Desktop users too. Claude Desktop reads/writes the vault via the Filesystem MCP whether or not Obsidian is installed. Install Obsidian only if you want the graph view or search UI.

## Prerequisites

- Claude Desktop installed (macOS or Windows)
- Node.js 18+ (the MCP server is an npm package run via `npx`)
- A memOS vault - set up via `./setup.sh` from this repo, or created manually

## Step 1 - Locate the Claude Desktop config

**macOS**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Windows**
```
%APPDATA%\Claude\claude_desktop_config.json
```

Create the file if it doesn't exist.

## Step 2 - Add the Filesystem MCP server

Open the config file and merge in this block (replace the path with your actual vault):

```json
{
  "mcpServers": {
    "memos-vault": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/Users/YOUR_USERNAME/Documents/memOS"
      ]
    }
  }
}
```

If you already have other MCP servers configured, add `memos-vault` as another entry under `mcpServers` - don't overwrite the others.

## Step 3 - Restart Claude Desktop

Quit (Cmd+Q) and reopen. In the chat window, you should see a new MCP tool indicator (small icon bottom-right of the input). Click it to confirm `memos-vault` is connected.

## Step 4 - Test it

Ask Claude Desktop:

> *"Read the file MOC.md in my memOS vault."*

If it returns the contents, you're done.

## How the hook differs on Desktop

The **Stop/SessionEnd hooks in this repo are Claude Code only.** Claude Desktop has no hook system - it can only read/write when you prompt it.

Practical consequence: on Desktop, memory isn't auto-appended. You have to ask at the end of a session:

> *"Save a summary of this conversation to Diary/sessions/ in memOS."*

To automate: set up a Projects in Claude Desktop with a system prompt like:

> *"At the end of each conversation, automatically write a summary to `Diary/sessions/YYYY-MM-DD-<topic>.md` in the memOS vault."*

Not as bulletproof as a shell hook, but close enough for most users.

## Combining Code + Desktop

Running both? They share the same vault. Recommended split:

- **Claude Code**: auto-saves via hooks while you work in the terminal/IDE
- **Claude Desktop**: for browsing past notes, summarizing, asking questions about the vault

Both see the same files, so memory stays unified.

## Troubleshooting

**"Server 'memos-vault' failed to start"**
- Check Node.js is installed: `node --version`
- Run the command manually in terminal: `npx -y @modelcontextprotocol/server-filesystem /path/to/memOS`

**Tool icon doesn't appear**
- Restart Claude Desktop fully (Cmd+Q, not just close window)
- Check the config file is valid JSON - a syntax error silently disables everything

**Claude can't find files**
- Confirm the vault path in the config is absolute (starts with `/` on macOS or `C:\` on Windows)
- Path must not contain the `~` shortcut - expand it to `/Users/YOU/...`
