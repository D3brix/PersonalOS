# PersonalOS

**A local-first second brain you own.** Plain Markdown notes, organized so that both you and your AI assistants
can find what matters, with a fast local search index, trust labels on every result, and maintenance that keeps
your knowledge honest.

- **Your files, your computer.** Notes are ordinary Markdown in a folder you choose. Works with Obsidian, VS Code
  or any editor. No account, no cloud, no telemetry, no network requests.
- **Search that knows what to trust.** Results come from *active memory* first (your system layer, current notes,
  inbox), then *long-term memory* (archive, daily notes, old documents, past AI conversations). Every result is
  labelled: AUTHORITATIVE, VERIFIED NOTE, RAW, INFERRED, TRANSCRIPT, ARCHIVED DOC.
- **Two storage tiers.** Keep the index on an SSD for instant search and put bulky archives on a second drive, or run
  everything from one drive.
- **Never edits your notes.** PersonalOS only *adds* new inbox notes when you capture something. Maintenance
  suggests; you decide.
- **AI-ready, AI-optional.** An MCP server and a Claude Code skill let assistants search your memory with sources
  and dates. The core needs no AI at all.
- **No dependencies.** Python 3.10+ standard library only (SQLite FTS5).

```
personalos search crop rotation

TIER 1 - ACTIVE MEMORY
 1. [VERIFIED NOTE] Crop_Rotation > Crop rotation
    04_Knowledge/Gardening/Crop_Rotation.md :L5-7   modified 2026-01-10
    Rotating plant families between beds reduces soil-borne disease ...
 2. [AUTHORITATIVE] Goals > This quarter
    99_System/Goals.md :L12-15   modified 2026-01-02
```

## Install (Windows 10/11)

1. Install [Python 3.10+](https://www.python.org/downloads/windows/) (tick *Add python.exe to PATH*).
2. Download PersonalOS and double-click `installer\install.cmd`, or run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File installer\install.ps1
   ```
3. Answer a few questions (where your vault, index and optional archive live). No administrator rights needed.

Other platforms (experimental): `pip install .` then `personalos init --vault ~/PersonalOS`. See
[docs/INSTALL.md](docs/INSTALL.md).

## Use

| Command | What it does |
|---|---|
| `personalos ui` | Local web interface: search, knowledge browser, inbox, projects, goals, archive, maintenance, health, settings, integrations |
| `personalos search <words>` | Tiered search with trust labels (`--all`, `--kind`, `--json`) |
| `personalos capture "text"` | New note in your inbox (also reads from stdin) |
| `personalos projects` / `inbox` / `goals` | Your current work at a glance |
| `personalos maintain` | Archive, re-index and a suggestions report (duplicates, conflicts, stale projects, secrets in notes) |
| `personalos backup --to <folder>` | Verified zip backup; `personalos restore` brings it back into an empty folder |
| `personalos doctor` | Health check |
| `personalos integrations list` | Claude Code, Obsidian, MCP (all optional) |

`pos` is a short alias for `personalos`. Start with [docs/QUICKSTART.md](docs/QUICKSTART.md).

## Documentation

- [Quick start](docs/QUICKSTART.md): your first 15 minutes
- [Installation](docs/INSTALL.md): Windows installer, storage layouts, uninstalling, other platforms
- [Architecture](docs/ARCHITECTURE.md): core, integrations and user data, and how search works
- [Configuration](docs/CONFIGURATION.md) and [examples](examples/)
- [Integrations](docs/INTEGRATIONS.md): Claude Code, Obsidian, MCP clients and local models
- [Privacy and security](docs/PRIVACY_SECURITY.md)
- [Roadmap](docs/ROADMAP.md) and [release notes](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md) and [security policy](SECURITY.md)

## Status

Version 0.1.0, the first MVP. The core (vault, index, search, maintenance, backup, CLI, local UI, installer) is
tested on Windows 11 with Python 3.13. See [CHANGELOG.md](CHANGELOG.md) for what is and is not included yet.

## License

Not yet chosen; see [docs/LICENSING.md](docs/LICENSING.md). Until a license file is added, all rights are reserved.
