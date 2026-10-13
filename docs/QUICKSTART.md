# Quick start

Your first 15 minutes with PersonalOS. This assumes you ran the installer (see [INSTALL.md](INSTALL.md)).

## 1. Try it on demo data (optional, 2 minutes)

The demo vault belongs to a fictional person, Alex Morgan, and shows every feature without touching your own notes:

```powershell
$env:PERSONALOS_CONFIG = "$env:TEMP\personalos-demo\config.json"
personalos init --vault "$env:TEMP\personalos-demo\vault" --data "$env:TEMP\personalos-demo\data" --demo
personalos search crop rotation
personalos ui
```

Close the window and open a new terminal to go back to your real vault (the variable only lives in that terminal).

## 2. Open the interface

```
personalos ui
```

Your browser opens a local page (`http://127.0.0.1:7531/...`). The link carries a one-time session key, so use the
link the command prints. Press Ctrl+C in the terminal to stop it.

## 3. Tell your assistant (and yourself) who you are

Open your vault in your editor (`personalos obsidian` if you use Obsidian) and fill in:

- `99_System/Identity.md`: background, interests, how you work
- `99_System/Goals.md`: concrete goals for this year and quarter
- `99_System/Preferences.md` and `Rules.md`: adjust the defaults to taste
- `Current_Focus.md`: what you are doing this week

These files are the *authoritative* layer: search ranks them highest, and AI assistants are told never to edit them,
only to propose changes in `99_System/Proposed_Changes.md`.

## 4. Capture, then process

Capture anything without deciding where it goes:

```
personalos capture "Look into standing desks under 300 EUR"
```

Once a week, empty the inbox following `07_Systems/Inbox_Workflow.md`: move each item to where it belongs (projects,
knowledge, people...) or leave it with a note saying what is missing.

## 5. Projects have a status

Each note in `02_Projects/` starts with frontmatter:

```
---
status: active
outcome: what "finished" looks like
---
```

`personalos projects` and the Projects page group them by status. When a project is done, set `status: done` and
move it to `09_Archive/`; maintenance reminds you.

## 6. Search

```
personalos search knee warm-up
personalos search tax --all              # always include long-term memory
personalos search goals --kind system    # only the system layer
```

Then read only the relevant part: `personalos show "<path>" --loc L12-30`.

## 7. Weekly review (20 minutes)

Follow `07_Systems/Weekly_Review.md`:

1. `personalos maintain` and read the report (it changes nothing).
2. Empty the inbox.
3. Update `Current_Focus.md` and project statuses.
4. Monthly: `personalos backup --to "E:\Backups"` (any folder outside the vault).

## 8. Optional: let your AI assistant use it

```
personalos integrations enable claude_code   # Claude Code skill + transcript archive
personalos integrations enable mcp           # any MCP-capable assistant, read-only
```

See [INTEGRATIONS.md](INTEGRATIONS.md).
