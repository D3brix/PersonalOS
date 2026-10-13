# Configuration

One JSON file. Find it with `personalos config path`, view it with `personalos config show`, and change values
with `personalos config set <dotted.key> <value>`, which validates before saving. You can also edit the file by
hand; `personalos doctor` reports mistakes.

The location is `%APPDATA%\PersonalOS\config.json` on Windows and `~/.config/personalos/config.json` elsewhere.
Set the `PERSONALOS_CONFIG` environment variable to use another file (a separate demo, a test, or a second vault).

## Keys

| Key | Default | Meaning |
|---|---|---|
| `vault` | — | Your vault folder |
| `data_dir` | `%LOCALAPPDATA%\PersonalOS\data` | Index and logs. Put it on an SSD. Must not be inside the vault. |
| `archive_dir` | `null` | Optional archive on a second drive. `null` = single-drive mode (archive kept in `data_dir\archive`). |
| `folders.<role>` | `00_Inbox`, `02_Projects`, ... | Folder names for each role: `inbox daily projects areas knowledge people skills systems resources archive raw system`. Map them to an existing vault's names. |
| `vault_rules` | see below | Glob → kind and tier. First match wins. `{role}` placeholders are replaced by folder names. |
| `vault_exclude_dirs` | `.obsidian .trash .git` | Never indexed or browsed |
| `extra_sources` | archive `long-term` folder | Additional read-only folders: `{"path", "kind", "tier", "extensions"}` |
| `search.limit` | `5` | Results per tier |
| `search.kind_weight` | system 1.5 ... transcript 0.7 | Trust multipliers in ranking |
| `maintenance.stale_days` | `60` | Suggest archiving projects untouched this long |
| `maintenance.promote_min_hits` | `3` | Suggest promoting long-term notes used this often in 30 days |
| `privacy.log_queries` | `true` | Store search words in the local usage log |
| `ui.port` | `7531` | First port tried by `personalos ui` (the next 9 are tried if it is busy) |
| `integrations.claude_code` | disabled | `home`, `index_memory`, `index_instructions`, `archive_transcripts`, `index_transcripts` |
| `integrations.obsidian` | disabled | — |
| `integrations.mcp` | disabled | `allow_capture` (default `false`) |

## Default tier rules

| Glob | Kind | Tier |
|---|---|---|
| `*README.md` | note | 2 |
| `{system}/*`, `AGENTS.md` | system | 1 |
| `{raw}/*` | raw | 2 |
| `{inbox}/*` | raw | 1 |
| `{archive}/*`, `{people}/*`, `{resources}/*`, `{daily}/*` | note | 2 |
| `{knowledge}/*` | note | 1 |
| everything else | note | 1 |

After changing folders or rules, run `personalos index --rebuild`.

## Examples

- [examples/config.single-drive.json](../examples/config.single-drive.json)
- [examples/config.ssd-hdd.json](../examples/config.ssd-hdd.json): index on the SSD, archive and old documents on a
  second drive, an adopted vault with its own folder names, and the Claude Code integration enabled.
