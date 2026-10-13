"""Obsidian integration (optional). PersonalOS vaults are plain Markdown, so Obsidian works without this.

Enabling it on a vault without an .obsidian folder writes two small settings files so new notes land in the
inbox and daily notes go to the daily folder. An existing Obsidian configuration is never changed.
"""
import json
import os
import sys
from urllib.parse import quote

NAME = "obsidian"
DESCRIPTION = "Open the vault in Obsidian; set inbox and daily-note folders on a new vault"


def enable(cfg):
    msgs = []
    obs = cfg.vault / ".obsidian"
    if obs.exists():
        msgs.append(f"{obs} already exists; your Obsidian settings were left unchanged")
    else:
        obs.mkdir(parents=True)
        f = cfg.data["folders"]
        (obs / "app.json").write_text(json.dumps(
            {"newFileLocation": "folder", "newFileFolderPath": f["inbox"],
             "attachmentFolderPath": f"{f['resources']}/attachments"}, indent=2), encoding="utf-8")
        (obs / "daily-notes.json").write_text(json.dumps(
            {"folder": f["daily"], "format": "YYYY-MM-DD"}, indent=2), encoding="utf-8")
        msgs.append(f"created {obs} (new notes -> {f['inbox']}, daily notes -> {f['daily']})")
    cfg.data["integrations"][NAME]["enabled"] = True
    cfg.save()
    msgs.append("open it with `personalos obsidian` or Obsidian > Open folder as vault")
    return msgs


def disable(cfg):
    cfg.data["integrations"][NAME]["enabled"] = False
    cfg.save()
    return ["disabled; the vault and its .obsidian folder were left unchanged"]


def uri(cfg):
    return "obsidian://open?path=" + quote(str(cfg.vault), safe="")


def open_vault(cfg):
    """Hand the vault to the Obsidian app via its URI scheme (local only; nothing goes over the network)."""
    u = uri(cfg)
    if sys.platform == "win32":
        os.startfile(u)  # noqa: S606 - opens the registered obsidian:// handler
    else:
        import subprocess
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", u], check=False)
    return u


def status(cfg):
    return {"vault_has_obsidian_settings": (cfg.vault / ".obsidian").is_dir(), "open_uri": uri(cfg)}
