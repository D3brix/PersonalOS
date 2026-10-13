# Integrations

All integrations are optional and off by default. `personalos integrations list` shows them;
`personalos integrations enable|disable <name>` switches them (or use the Integrations page). Disabling never
deletes your data.

## Claude Code (`claude_code`)

What it does when enabled:

- **Skill:** writes `~/.claude/skills/personalos/SKILL.md`, so Claude Code runs `personalos search` when a task
  needs your personal context, and cites path and date for every fact. The file carries a PersonalOS marker; an
  existing skill of the same name that PersonalOS did not create is never overwritten, and only the marked file is
  removed on disable.
- **Memory:** indexes Claude Code's auto-memory (`~/.claude/projects/*/memory/*.md`) as INFERRED and
  `~/.claude/CLAUDE.md` as INSTRUCTION.
- **Transcripts:** `personalos archive` (also part of `maintain`) copies `~/.claude/projects` and
  `history.jsonl` into `<archive>/claude-code/files/`, verifies each copy by sha256 and writes a manifest. Only user
  and assistant text is indexed (as TRANSCRIPT, long-term); tool calls, tool output, thinking and attachments are
  skipped.

Claude Code deletes transcripts after `cleanupPeriodDays` (30 by default). Archive before then, or raise the
setting in Claude Code. PersonalOS does not change Claude Code's settings.

Options: `integrations.claude_code.home`, `index_memory`, `index_instructions`, `archive_transcripts`,
`index_transcripts`.

Your vault also contains `CLAUDE.md` (which imports `AGENTS.md`), so Claude Code sessions started inside the vault
follow its rules.

## Obsidian (`obsidian`)

A PersonalOS vault is a normal Obsidian vault: open the folder with *Open folder as vault*. Enabling the
integration:

- on a vault without `.obsidian`, writes two settings files so new notes go to the inbox, attachments go to
  `08_Resources/attachments` and daily notes go to `01_Daily`;
- leaves an existing Obsidian configuration completely unchanged;
- `personalos obsidian` opens the vault through the `obsidian://` link handler.

## MCP server (`mcp`)

For any assistant that speaks the Model Context Protocol, including Claude Desktop, Claude Code, editors and
desktop apps that run local models. It communicates over stdin/stdout only.

```
personalos integrations enable mcp
claude mcp add personalos -- personalos mcp          # Claude Code
```

JSON-configured clients (for example Claude Desktop's `claude_desktop_config.json`):

```json
{ "mcpServers": { "personalos": { "command": "C:\\Users\\<you>\\AppData\\Local\\PersonalOS\\bin\\personalos.cmd", "args": ["mcp"] } } }
```

Tools: `search_memory`, `read_memory` and `list_inbox` (read-only). `capture_note` appears only when you set
`integrations.mcp.allow_capture` to `true`, and it can only create new inbox notes.

## Local AI models

PersonalOS does not run models itself. To use your memory with a local model, use an MCP-capable local client and
add the MCP server above; nothing leaves your machine. Built-in local processing (summaries, inbox triage
suggestions, semantic search with local embeddings) is on the [roadmap](ROADMAP.md) as an optional add-on.

## Writing an integration

An integration is a module in `personalos/integrations/` with `NAME`, `DESCRIPTION`, `enable(cfg)`,
`disable(cfg)` and `status(cfg)`, and optionally `sources(cfg)` (yielding `Source` objects to index) and `PARSERS`
(parser name → `(parse, show)`). Register it in `integrations/__init__.py`. It must not make network requests and
must not write into the vault except through `vault.capture`. See [CONTRIBUTING.md](../CONTRIBUTING.md).
