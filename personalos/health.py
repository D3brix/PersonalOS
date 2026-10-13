"""`personalos doctor`: read-only health checks with OK / WARN / FAIL results."""
import datetime as dt
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from . import archive, index
from .config import ConfigError, load
from .integrations import all_integrations, enabled_integrations

OK, WARN, FAIL = "OK", "WARN", "FAIL"


def _writable(d):
    try:
        d.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=d, prefix=".write-test-", delete=True):
            pass
        return True
    except OSError:
        return False


def fts5_available():
    try:
        con = sqlite3.connect(":memory:")
        con.execute("create virtual table t using fts5(x)")
        con.close()
        return True
    except sqlite3.OperationalError:
        return False


def checks(deep=False):
    out = []

    def add(status, name, detail=""):
        out.append({"status": status, "check": name, "detail": detail})

    v = sys.version_info
    add(OK if v >= (3, 10) else FAIL, "Python", f"{v.major}.{v.minor}.{v.micro} (3.10+ required)")
    add(OK if fts5_available() else FAIL, "SQLite FTS5", sqlite3.sqlite_version)
    try:
        cfg = load()
    except ConfigError as e:
        add(FAIL, "Configuration", str(e))
        return out, None
    add(OK, "Configuration", str(cfg.path))

    if cfg.vault.is_dir():
        notes = sum(1 for _ in cfg.vault.rglob("*.md"))
        add(OK, "Vault", f"{cfg.vault} ({notes} notes)")
        missing = [r for r in cfg.data["folders"] if not cfg.folder(r).is_dir()]
        add(WARN if missing else OK, "Vault folders",
            f"missing: {', '.join(cfg.data['folders'][r] for r in missing)}" if missing else "all present")
    else:
        add(FAIL, "Vault", f"{cfg.vault} does not exist")

    add(OK if _writable(cfg.data_dir) else FAIL, "Data folder writable", str(cfg.data_dir))
    try:
        free = shutil.disk_usage(cfg.data_dir).free
        add(OK if free > 1 << 30 else WARN, "Free space (data)", f"{free / 1e9:.1f} GB")
    except OSError:
        pass
    if cfg.data.get("archive_dir"):
        a = Path(cfg.data["archive_dir"])
        if a.is_dir() and _writable(a):
            add(OK, "Archive folder", f"{a} ({shutil.disk_usage(a).free / 1e9:.1f} GB free)")
        else:
            add(FAIL, "Archive folder", f"{a} is not reachable or not writable (drive disconnected?)")
    else:
        add(OK, "Archive folder", f"SSD-only mode: {cfg.archive_root}")

    problems = index.integrity(cfg)
    if problems and "does not exist" in problems[0]:
        add(WARN, "Search index", problems[0])
    elif problems:
        add(FAIL, "Search index", "; ".join(problems) + " - run `personalos index --rebuild`")
    else:
        st = index.stats(cfg)
        n = sum(g["files"] for g in st["groups"])
        last = st["last_index"]
        age_days = (dt.datetime.now() - dt.datetime.fromisoformat(last)).days if last else None
        add(OK if age_days is not None and age_days <= 7 else WARN, "Search index",
            f"{n} files, {st['db_bytes'] / 1e6:.1f} MB, last updated {last or 'never'}")
        con, _ = index.open_db(cfg)
        gone = [r[0] for r in con.execute("select path from files") if not Path(r[0]).exists()]
        con.close()
        add(WARN if gone else OK, "Indexed files present",
            f"{len(gone)} indexed files no longer exist - run `personalos index`" if gone else "all present")

    for integ in enabled_integrations(cfg):
        if hasattr(integ, "archive_dir"):
            adir = integ.archive_dir(cfg)
            if deep:
                r = archive.verify(adir)
                bad = len(r["missing"]) + len(r["corrupted"])
                add(FAIL if bad else OK, f"Archive integrity ({integ.NAME})",
                    f"ok={r['ok']} missing={len(r['missing'])} corrupted={len(r['corrupted'])}")
            elif (adir / archive.MANIFEST).exists():
                add(OK, f"Archive ({integ.NAME})", "manifest present (use --deep to verify every file)")
    for integ in all_integrations():
        on = bool(cfg.integration(integ.NAME).get("enabled"))
        detail = "enabled" if on else "disabled"
        status = OK
        if on and integ.NAME == "claude_code":
            s = integ.status(cfg)
            if not s["skill_installed"]:
                status, detail = WARN, "enabled but the skill is missing - run `personalos integrations enable claude_code`"
        add(status, f"Integration: {integ.NAME}", detail)

    if os.name != "nt" and cfg.data_dir.exists():
        mode = cfg.data_dir.stat().st_mode & 0o077
        add(WARN if mode else OK, "Data folder permissions", "readable by other users" if mode else "owner only")
    add(OK, "Network", "PersonalOS makes no network requests; the UI listens on 127.0.0.1 only")
    return out, cfg

