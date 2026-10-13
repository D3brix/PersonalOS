# Installation

## Requirements

- Windows 10 or 11 (the installer). Linux and macOS work through `pip` but are not yet tested regularly.
- Python 3.10 or newer from python.org or `winget install Python.Python.3.12`. The Microsoft Store "python"
  shortcut is not enough. The installer checks that Python's SQLite has FTS5 (all python.org builds do).
- About 50 MB plus the index: roughly 10-20% of the size of what you index.
- No administrator rights and no internet connection.

## Windows installer

Double-click `installer\install.cmd`, or run in PowerShell from the PersonalOS folder:

```powershell
powershell -ExecutionPolicy Bypass -File installer\install.ps1
```

It walks through nine steps:

| Step | What happens |
|---|---|
| 1. Requirements | Windows version, PowerShell, Python 3.10+ with FTS5 |
| 2. Storage | Lists your drives, free space and whether each is an SSD or HDD |
| 3. Locations | Vault folder, index folder (SSD recommended), optional archive folder (second drive) |
| 4. Program | Copies PersonalOS to `%LOCALAPPDATA%\PersonalOS\app` and creates `personalos.cmd` and `pos.cmd` in `...\bin` |
| 5. Vault and index | Creates your vault from the starter template (or adopts an existing folder unchanged) and builds the index |
| 6. Integrations | Asks about Claude Code, Obsidian and MCP. All are off unless you say yes |
| 7. Permissions and maintenance | Restricts index/archive folders outside your profile to your account; optional weekly scheduled task |
| 8. PATH | Optionally adds the `bin` folder to your user PATH |
| 9. Health check | Runs `personalos doctor` and prints how to get started |

Everything it creates is recorded in `%LOCALAPPDATA%\PersonalOS\install.json`.

### Storage layouts

**Single drive** (the default): leave the archive question empty. Index, logs and the transcript archive live in
the index folder.

**SSD + HDD**: put the index folder on the SSD and give an archive folder on the HDD. Search stays fast because
only the index is read; archived transcripts and `long-term\` documents live on the HDD and are indexed as long-term
memory. If the HDD is disconnected, search still works on what is indexed, and `personalos doctor` reports the drive
as unavailable.

### Using an existing vault

Point the installer (or `personalos init --adopt`) at an existing Markdown or Obsidian folder. Nothing in it is
changed. If your folder names differ from the defaults, map them afterwards, for example:

```
personalos config set folders.inbox "Inbox"
personalos config set folders.projects "Projects"
personalos index --rebuild
```

### Unattended install

```powershell
install.ps1 -NonInteractive -VaultPath "D:\Notes\PersonalOS" -DataPath "C:\PersonalOS\index" `
            -ArchivePath "E:\PersonalOS Archive" -Integrations obsidian -AddToPath -ScheduleMaintenance
```

In non-interactive mode, nothing optional happens unless its switch is given.

## Uninstalling

```powershell
powershell -ExecutionPolicy Bypass -File installer\uninstall.ps1
```

It removes the program, the commands, the PATH entry, the scheduled task and the Claude Code skill. **Your vault is
never deleted.** It asks separately whether to delete the index/logs and the archive, and each deletion must be
confirmed by typing `DELETE`. Unattended: `-NonInteractive -RemoveIndex -RemoveArchive -ConfirmDelete DELETE`.
Without `-ConfirmDelete DELETE`, data is kept.

## Upgrading

Run the new installer. It finds your configuration and keeps your locations, vault and settings.

## Other platforms (experimental)

```bash
pip install .            # from the PersonalOS folder; installs `personalos` and `pos`
personalos init --vault ~/PersonalOS --demo
```

Configuration goes to `~/.config/personalos/config.json` and data to `~/.local/share/personalos` (XDG variables are
respected). On these platforms the config file and data folder are created owner-only.

## Running from source

```
python -m personalos --help
```

Set `PERSONALOS_CONFIG` to use a separate configuration (for example a demo or a test).
