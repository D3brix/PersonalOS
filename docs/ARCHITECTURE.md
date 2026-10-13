# Architecture

PersonalOS is three separate layers. Only the first two are the product; the third never leaves your computer.

```
 ┌──────────────────────────── PersonalOS Core (personalos/) ─────────────────────────────┐
 │  config.py     configuration, validation, platform paths                              │
 │  vault.py      vault templates, capture, browsing (never edits existing notes)        │
 │  sources.py    what gets indexed, trust kinds, Markdown chunking                      │
 │  index.py      SQLite FTS5 index: incremental updates, tiered search, recovery        │
 │  redact.py     secret detection and redaction                                         │
 │  archive.py    append-only archive with sha256 manifest                               │
 │  maintain.py   maintenance report (suggestions only)                                  │
 │  backup.py     verified zip backup / restore into an empty folder                     │
 │  health.py     `doctor` checks                                                        │
 │  cli.py        command line          web/  local interface (127.0.0.1 only)           │
 │  templates/    starter vault and fictional demo data                                  │
 └────────────────────────────────────────────────────────────────────────────────────────┘
 ┌──────────────────────── PersonalOS Integrations (personalos/integrations/) ────────────┐
 │  claude_code   index Claude Code memory + transcripts, archive transcripts, install a  │
 │                search skill                                                           │
 │  obsidian      open the vault in Obsidian; inbox/daily folders for a new vault        │
 │  mcp           stdio MCP server: any MCP client (assistants, local-model apps)        │
 └────────────────────────────────────────────────────────────────────────────────────────┘
 ┌──────────────────────────── User data (yours, never packaged) ────────────────────────┐
 │  vault/          your Markdown notes                       (location you chose)       │
 │  config.json     paths and settings                        (%APPDATA%\PersonalOS)     │
 │  data/index      memory.db search index (a rebuildable cache)  ┐ data folder (SSD)   │
 │  data/logs       operations, usage, maintenance reports        ┘                      │
 │  archive/        archived transcripts, long-term documents     (optional second drive)│
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

The core has no dependency on any integration: `enabled_integrations()` is empty by default, and every feature
works without one. Integrations plug in through a small interface: `enable`, `disable`, `status`, and optionally
`sources` (extra files to index) and `PARSERS` (how to read them).

## Data flow

```
  sources (read-only)                         index (SSD)                       you / assistants
  ───────────────────                         ───────────                       ────────────────
  vault/*.md ──┐                                                                personalos search
  extra folders├─► chunk ─► redact secrets ─► files + chunks + FTS5 ──► tier 1 ─► (tier 2 if few hits,
  integrations ┘   (headings,                  (path, mtime, sha256,            or title matches)
                   ~1800 chars)                 kind, tier)                   personalos show (redacted slice)
```

- **Incremental indexing.** A file is re-read only when its size or mtime changed, and re-indexed only when its
  sha256 changed. Deleted files leave the index. One unreadable file never stops a run.
- **Tiers.** Tier 1 (active memory): system layer, root notes, inbox, projects, areas, knowledge, skills, systems,
  AI memory. Tier 2 (long-term): archive, daily notes, people, resources, `raw/`, extra folders, transcripts. Tier 2
  is searched when tier 1 returns fewer results than the limit, always with `--all`, and otherwise checked for title
  matches only. The rules are globs in the config and can be changed.
- **Ranking.** BM25 with title (6x) and heading (3x) weights, multiplied by a per-kind trust weight (system 1.5,
  note 1.3, ... transcript 0.7). One result per file. Queries try AND first, then OR. Stop words are dropped, and
  every token is quoted, so user input can never inject FTS syntax.
- **Trust labels.** Each kind maps to a label shown with every result: AUTHORITATIVE (system layer), VERIFIED NOTE,
  RAW, INFERRED (AI-written memory), TRANSCRIPT, ARCHIVED DOC, INSTRUCTION.

## Write boundaries

| Component | Writes to |
|---|---|
| `init` | an *empty* vault folder (template files), the config file, the data folder |
| `capture` (CLI, UI, MCP if allowed) | one new file in the inbox, created with O_EXCL (cannot overwrite) |
| `index`, `maintain` | the data folder only |
| `archive` (Claude Code) | the archive folder, append-only; a shrunk source never replaces a larger copy without preserving it |
| `backup` | one new zip in a folder outside the vault |
| `restore` | an *empty* target folder |
| integrations | Claude Code skill file (only one carrying the PersonalOS marker); Obsidian settings only when `.obsidian` does not exist |

Nothing in PersonalOS edits, moves or deletes an existing note.

## Reliability

- The index is a cache. A corrupt or incompatible index is moved aside (`memory.db.corrupt-<time>`, never deleted)
  and rebuilt automatically on the next index or search.
- `doctor` runs `PRAGMA integrity_check` and compares the chunk and FTS tables.
- A lock file prevents two indexing runs at once (scheduled task + UI); a lock older than 30 minutes is treated as
  stale.
- The archive has a sha256 manifest; `verify-archive` and `doctor --deep` detect missing or altered files.
- Backups carry a sha256 per file and are verified before restore.

## Why these choices

- **Python standard library only:** nothing to install or audit beyond Python itself, and nothing can phone home
  through a dependency.
- **SQLite FTS5 rather than embeddings:** instant, deterministic, explainable, and fully offline. Semantic search is
  planned as an optional local add-on (see [ROADMAP.md](ROADMAP.md)).
- **Markdown files as the source of truth:** readable in 20 years, editable in any tool, trivially backed up.
- **A local web UI rather than a desktop framework:** no extra runtime, and the same API can later back a packaged
  desktop app.
