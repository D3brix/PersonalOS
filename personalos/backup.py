"""Backup and restore.

A backup is one zip with the vault, the config and the logs (optionally the archive), plus a manifest of
sha256 hashes. The index is not included because it can always be rebuilt. Restore verifies every hash and
only extracts into an empty folder, so it can never overwrite existing data.
"""
import datetime as dt
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath

from . import __version__, logs


class BackupError(Exception):
    pass


def _inside(child, parent):
    child, parent = Path(child).resolve(), Path(parent).resolve()
    return child == parent or parent in child.parents


def create(cfg, dest_dir, include_archive=False):
    dest_dir = Path(dest_dir)
    if _inside(dest_dir, cfg.vault):
        raise BackupError("the backup folder must not be inside the vault")
    if include_archive and _inside(dest_dir, cfg.archive_root):
        raise BackupError("the backup folder must not be inside the archive when the archive is included")
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"personalos-backup-{dt.datetime.now():%Y%m%d-%H%M%S}.zip"
    roots = [("vault", cfg.vault), ("logs", cfg.logs)]
    if include_archive and cfg.archive_root.is_dir():
        roots.append(("archive", cfg.archive_root))
    exclude = set(cfg.data["vault_exclude_dirs"]) - {".obsidian"}  # keep Obsidian settings, skip trash/git
    manifest = {"format": 1, "created": dt.datetime.now().isoformat(timespec="seconds"),
                "personalos_version": __version__, "files": {}}
    with zipfile.ZipFile(out, "x", zipfile.ZIP_DEFLATED) as z:
        z.writestr("config.json", json.dumps(cfg.data, indent=2, ensure_ascii=False))
        for prefix, root in roots:
            if not root.is_dir():
                continue
            for f in sorted(root.rglob("*")):
                if not f.is_file() or _inside(f, dest_dir):
                    continue
                rel = f.relative_to(root)
                if prefix == "vault" and any(p in exclude for p in rel.parts):
                    continue
                arc = f"{prefix}/{rel.as_posix()}"
                data = f.read_bytes()
                z.writestr(arc, data)
                manifest["files"][arc] = hashlib.sha256(data).hexdigest()
        z.writestr("backup-manifest.json", json.dumps(manifest, indent=1))
    logs.op(cfg, "backup", {"file": str(out), "files": len(manifest["files"]), "archive": include_archive})
    return out, len(manifest["files"])


def verify(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        try:
            manifest = json.loads(z.read("backup-manifest.json"))
        except KeyError:
            raise BackupError("not a PersonalOS backup (no backup-manifest.json)") from None
        bad = [arc for arc, digest in manifest["files"].items()
               if hashlib.sha256(z.read(arc)).hexdigest() != digest]
    return manifest, bad


def restore(zip_path, target):
    """Extract a verified backup into an empty folder: target/vault, target/logs, target/archive, config.json."""
    target = Path(target)
    if target.exists() and any(target.iterdir()):
        raise BackupError(f"{target} is not empty; restore only writes into an empty folder")
    manifest, bad = verify(zip_path)
    if bad:
        raise BackupError(f"backup is damaged: {len(bad)} files fail their checksum (first: {bad[0]})")
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts or ":" in info.filename:
                raise BackupError(f"unsafe path in backup: {info.filename}")
            dst = (root / Path(*name.parts)).resolve()
            if root not in dst.parents:
                raise BackupError(f"unsafe path in backup: {info.filename}")
            if info.is_dir():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(z.read(info))
    return manifest
