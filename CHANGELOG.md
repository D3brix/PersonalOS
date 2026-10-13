# Release notes

## 0.1.0 (unreleased): first MVP

### Included
- Starter vault: inbox, daily, projects, areas, knowledge (with a decision log and lessons learned), people, skills,
  systems, resources, archive, raw and a system layer (identity, goals, preferences, rules, proposed changes,
  changelog). Includes the Knowledge Processing skill, the Inbox Workflow and the Weekly Review.
- Fictional demo vault (`init --demo`).
- SQLite FTS5 index with incremental updates, tier-1/tier-2 search, trust labels, kind weighting, one result per
  file, an AND→OR fallback and title matches from long-term memory.
- Secret redaction in the index and in every displayed original; credential files are never indexed; capture
  refuses secrets.
- Maintenance report: duplicates, same-title conflicts, possibly outdated AI memories, archival and promotion
  suggestions, raw backlog, notes containing secrets.
- Verified zip backup and restore into an empty folder.
- `doctor` health checks; automatic quarantine and rebuild of a corrupt index.
- Local web UI: search, knowledge browser, inbox capture, projects, goals, archive, maintenance, health,
  integrations, settings. Light and dark themes; works at phone width.
- Integrations: Claude Code (skill, memory, transcript archive), Obsidian, MCP server (stdio, read-only by default).
- Windows installer/uninstaller: per-user, no admin, SSD-only or SSD+HDD, optional PATH entry, folder ACLs and
  weekly scheduled task.

### Known limitations
- Keyword search only (no synonyms or semantic matching). Prefix matching applies to words of 4+ letters.
- The UI reads and captures; editing and moving notes happens in your editor.
- The installer needs a separately installed Python 3.10+.
- Tested on Windows 11 with Python 3.13. Windows 10, older Python versions, Linux and macOS are not yet tested
  regularly.
- The "outdated AI memory" check is a heuristic.
