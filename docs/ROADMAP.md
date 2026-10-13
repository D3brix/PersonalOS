# Roadmap

Principle: the core must be boring and reliable before anything clever is added on top. Each stage ships only when
the previous one has held up in real use.

## MVP: 0.1 (this release): a reliable, installable local second brain

- [x] Vault template (folder architecture, system layer, workflows) and fictional demo vault
- [x] Two-tier SQLite FTS5 index: incremental, trust labels, title-aware tiering, corruption recovery
- [x] CLI: init, search, show, capture, inbox, projects, goals, index, maintain, archive, verify, backup, restore,
      doctor, config, integrations
- [x] Local web UI covering every CLI area, hardened for localhost
- [x] Integrations: Claude Code, Obsidian, MCP server
- [x] Windows per-user installer and uninstaller (SSD-only and SSD+HDD)
- [x] Automated tests (56), including installer end-to-end and privacy guarantees

## 0.2-0.4: harden with real users (next)

- Beta with 5-10 users on clean machines, and an issue template for bug reports
- Signed release zip with checksums; `personalos update` that verifies a downloaded zip (no automatic downloads)
- Tests on Windows 10, Python 3.10-3.13, OneDrive-synced vaults, network and removable drives
- Index watch mode (re-index on file change), so maintenance is less manual
- Inbox triage in the UI: move a note to a folder, with an undo log (the first time PersonalOS moves files)
- Daily note command and template
- Linux and macOS CI

## 1.0: a polished application

- Packaged Windows app (one installer, embedded Python, no separate Python install), code-signed
- Desktop window instead of a browser tab (WebView2), tray icon, global capture shortcut
- Note editing in the UI (or a deliberate decision to leave editing to Obsidian/VS Code)
- Onboarding wizard in the UI (identity, goals and focus questions that write the starter notes)
- Accessibility audit, keyboard-first navigation, documentation site
- Stable config schema with migrations; semantic versioning guarantees

## Future: optional and premium

Free core stays local and complete. Candidates for paid add-ons, each opt-in and clearly separated:

- **Local AI processing:** semantic search with local embeddings, inbox triage suggestions, weekly-review summaries
  and contradiction detection, using a local model by default, with cloud models only with explicit consent and a
  per-request preview of what is sent
- **Cross-device sync:** end-to-end encrypted, with the server never seeing plaintext; or first-class support for
  existing sync (Syncthing, OneDrive, iCloud) with conflict handling
- **Mobile capture app** that feeds the inbox
- **Automation:** scheduled routines (weekly review prep, project staleness nudges) with approval gates
- **Team/family vaults** with shared areas

Not planned: telemetry, ads, or any feature that requires your notes to leave your machine by default.
