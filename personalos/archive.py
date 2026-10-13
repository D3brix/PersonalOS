"""Append-only mirror of a source folder into the archive tier, with a sha256 manifest.

The archive never deletes. If a source file shrinks (for example an app truncated it), the larger archived
copy is preserved under superseded/ before being replaced.
"""
import datetime as dt
import shutil
import time
from pathlib import Path

from .index import sha256_file

MANIFEST = "MANIFEST.tsv"


def _copy_preserving(src, dst, superseded_root, rel):
    st = src.stat()
    action = "new"
    if dst.exists():
        dst_st = dst.stat()
        if dst_st.st_size == st.st_size and int(dst_st.st_mtime) == int(st.st_mtime):
            return None
        action = "updated"
        if st.st_size < dst_st.st_size:
            keep = superseded_root / rel
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, keep)
            action = "preserved"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return action


def mirror(pairs, archive_dir):
    """pairs: [(source_file, relative_path_in_archive)]. Writes files under archive_dir/files/."""
    t0 = time.perf_counter()
    archive_dir = Path(archive_dir)
    files_root = archive_dir / "files"
    superseded = archive_dir / "superseded" / dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    counts = {"new": 0, "updated": 0, "preserved": 0}
    copied = []
    for src, rel in pairs:
        action = _copy_preserving(src, files_root / rel, superseded, rel)
        if action:
            counts[action] += 1
            copied.append((src, files_root / rel))
    # Verify what was copied. A file still being written by a live session may legitimately differ.
    mismatched, live = [], []
    for src, dst in copied:
        if sha256_file(src) != sha256_file(dst):
            (live if time.time() - src.stat().st_mtime < 300 else mismatched).append(str(src))
    write_manifest(archive_dir)
    return {**counts, "archived_files": sum(1 for f in files_root.rglob("*") if f.is_file()) if files_root.exists() else 0,
            "hash_mismatch": len(mismatched), "still_changing": len(live),
            "seconds": round(time.perf_counter() - t0, 2)}, mismatched


def write_manifest(archive_dir):
    files_root = Path(archive_dir) / "files"
    tmp = Path(archive_dir) / (MANIFEST + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as m:
        m.write("sha256\tsize\tpath\n")
        if files_root.exists():
            for f in sorted(files_root.rglob("*")):
                if f.is_file():
                    m.write(f"{sha256_file(f)}\t{f.stat().st_size}\t{f.relative_to(files_root).as_posix()}\n")
    tmp.replace(Path(archive_dir) / MANIFEST)


def verify(archive_dir):
    archive_dir = Path(archive_dir)
    manifest = archive_dir / MANIFEST
    if not manifest.exists():
        return {"ok": 0, "missing": [], "corrupted": [], "manifest": False}
    ok, missing, bad = 0, [], []
    for line in manifest.read_text(encoding="utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        digest, _size, rel = line.split("\t", 2)
        f = archive_dir / "files" / rel
        if not f.exists():
            missing.append(rel)
        elif sha256_file(f) != digest:
            bad.append(rel)
        else:
            ok += 1
    return {"ok": ok, "missing": missing, "corrupted": bad, "manifest": True}
