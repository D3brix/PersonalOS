"""Command-line interface: `personalos <command>` (alias `pos`)."""
import argparse
import datetime as dt
import json
import os
import shutil
import sys
import time
from pathlib import Path

from . import __version__, archive, backup, config, health, index, logs, maintain, vault
from .integrations import all_integrations, enabled_integrations, get as get_integration
from .sources import LABEL_HELP, LABELS


class UserError(Exception):
    pass


def _cfg():
    try:
        return config.load()
    except config.ConfigError as e:
        raise UserError(str(e)) from None


# ---------------------------------------------------------------- setup

def cmd_init(a):
    path = config.config_path()
    if path.exists() and not a.force_config:
        raise UserError(f"PersonalOS is already configured ({path}). Use `personalos config show`, or pass "
                        "--force-config to replace it (the old file is kept as a .bak copy).")
    data = config.new_config(a.vault, a.data, a.archive)
    errors = config.validate(data)
    if errors:
        raise UserError("invalid setup:\n  - " + "\n  - ".join(errors))
    try:
        res = vault.create_vault(data["vault"], "demo" if a.demo else "default", adopt=a.adopt)
    except vault.VaultError as e:
        raise UserError(str(e)) from None
    if path.exists():
        bak = path.with_name(f"config.json.bak-{dt.datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(path, bak)
        print(f"previous config kept as {bak}")
    cfg = config.Config(data, path)
    cfg.save()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    if a.archive:
        (Path(data["archive_dir"]) / "long-term").mkdir(parents=True, exist_ok=True)
    if os.name != "nt":  # on Windows the installer restricts folders with ACLs
        for d in [cfg.data_dir] + ([Path(data["archive_dir"])] if a.archive else []):
            os.chmod(d, 0o700)
    if res["adopted"]:
        print(f"using existing vault {res['adopted']} (nothing in it was changed)")
    else:
        print(f"vault created: {data['vault']} ({len(res['created'])} files from the "
              f"{'demo' if a.demo else 'starter'} template)")
    print(f"config: {path}\ndata (index, logs): {data['data_dir']}")
    print(f"archive: {data['archive_dir'] or str(cfg.archive_root) + '  (SSD-only mode)'}")
    st, _, _ = index.run_index(cfg)
    print(f"index built: {st['added']} files in {st['seconds']} s")
    print("\nnext: `personalos search <words>`, `personalos capture \"an idea\"`, `personalos ui`, "
          "`personalos doctor`")


def cmd_config(a):
    if a.action == "path":
        print(config.config_path())
        return
    cfg = _cfg()
    if a.action == "show":
        print(json.dumps(cfg.data, indent=2, ensure_ascii=False))
        return
    if not a.key or a.value is None:
        raise UserError("usage: personalos config set <dotted.key> <value>")
    data = json.loads(json.dumps(cfg.data))
    node, keys = data, a.key.split(".")
    for k in keys[:-1]:
        if not isinstance(node.get(k), dict):
            raise UserError(f"unknown setting '{a.key}'")
        node = node[k]
    if keys[-1] not in node:
        raise UserError(f"unknown setting '{a.key}'")
    try:
        value = json.loads(a.value)
    except ValueError:
        value = a.value
    if keys[-1] in ("vault", "data_dir", "archive_dir") and isinstance(value, str):
        value = config.norm(value)
    node[keys[-1]] = value
    errors = config.validate(data)
    if errors:
        raise UserError("not saved:\n  - " + "\n  - ".join(errors))
    cfg.data = data
    cfg.save()
    print(f"{a.key} = {json.dumps(value)}")


def cmd_integrations(a):
    cfg = _cfg()
    if a.action == "list":
        for integ in all_integrations():
            on = "enabled " if cfg.integration(integ.NAME).get("enabled") else "disabled"
            print(f"{integ.NAME:<12} {on}  {integ.DESCRIPTION}")
            if cfg.integration(integ.NAME).get("enabled"):
                for k, v in integ.status(cfg).items():
                    print(f"{'':<23}{k}: {v}")
        return
    if not a.name:
        raise UserError(f"usage: personalos integrations {a.action} <name>")
    try:
        integ = get_integration(a.name)
        msgs = integ.enable(cfg) if a.action == "enable" else integ.disable(cfg)
    except (KeyError, RuntimeError) as e:
        raise UserError(str(e).strip("'\"")) from None
    for m in msgs:
        print(m)


# ---------------------------------------------------------------- search

def print_hit(i, r):
    head = f" > {r['heading']}" if r["heading"] and r["heading"] != "frontmatter" else ""
    when = f"conversation {r['ts']}" if r["kind"] == "transcript" and r["ts"] else f"modified {r['date']}"
    print(f"{i:>2}. [{r['label']}] {r['title']}{head}")
    print(f"    {r['path']} :{r['loc']}   {when}")
    print(f"    {' '.join(r['snip'].split())[:400]}")


def cmd_search(a):
    cfg = _cfg()
    q = " ".join(a.query)
    t0 = time.perf_counter()
    res = index.search(cfg, q, a.limit, a.all, a.kind.split(",") if a.kind else None)
    ms = (time.perf_counter() - t0) * 1000
    hits = res["tier1"] + res["tier2"]
    if not a.no_log:
        logs.usage(cfg, {"q": q, "hits": [h["path"] for h in hits[:3]]})
    if a.json:
        print(json.dumps({**res, "ms": round(ms, 1), "labels": LABEL_HELP}, ensure_ascii=False, indent=1))
        return
    print(f'search "{q}"  ({ms:.0f} ms)')
    if res["mode"] == "OR" and hits:
        print("  note: no result contained every word; showing partial matches.")
    print("\nTIER 1 - ACTIVE MEMORY")
    for i, r in enumerate(res["tier1"], 1):
        print_hit(i, r)
    if not res["tier1"]:
        print("   (no hits)")
    if res["tier2_searched"] or res["tier2"]:
        print("\nTIER 2 - LONG-TERM MEMORY" + ("" if res["tier2_searched"] else " (title matches only)"))
        for i, r in enumerate(res["tier2"], 1):
            print_hit(i, r)
        if not res["tier2"]:
            print("   (no hits)")
    if not res["tier2_searched"]:
        print("\n(active memory filled the result limit, so long-term memory was only checked for title "
              "matches; add --all for a full search)")
    kinds = sorted({h["kind"] for h in hits})
    if kinds:
        print("\nlabels: " + "; ".join(f"{LABELS[k]} = {LABEL_HELP[k]}" for k in kinds))
        print('open one: personalos show "<path>" --loc <loc>')


def cmd_show(a):
    cfg = _cfg()
    try:
        r = index.show(cfg, a.path, a.loc, a.max)
    except index.NotIndexed as e:
        raise UserError(str(e)) from None
    print(f"[{r['label']}] {LABEL_HELP[r['kind']]}")
    print(f"{r['path']}   modified {r['date']}")
    if r["stale"]:
        print("note: the file changed since it was indexed; run `personalos index`.")
    print("-" * 70)
    print(r["text"])
    if r["truncated"]:
        print(f"... [truncated at {a.max} characters; use --max 0 for everything]")
    if r["redactions"]:
        print(f"\n({r['redactions']} secret-like strings redacted)")
    logs.usage(cfg, {"show": r["path"], "loc": a.loc or ""})


# ---------------------------------------------------------------- index / archive / maintain

def cmd_index(a):
    cfg = _cfg()
    try:
        st, changed, errors = index.run_index(cfg, a.rebuild)
    except index.IndexBusy as e:
        raise UserError(str(e)) from None
    if st["recovered_corrupt_index"]:
        print("the index was corrupt or from an incompatible version: it was moved aside and rebuilt.")
    print("index: " + ", ".join(f"{k}={v}" for k, v in st.items() if k != "recovered_corrupt_index"))
    for c in changed[:30]:
        print("  changed:", c)
    if len(changed) > 30:
        print(f"  ... {len(changed) - 30} more (see the operations log)")
    for e in errors:
        print("  could not read:", e)


def cmd_archive(a):
    cfg = _cfg()
    results = maintain.run_archives(cfg)
    if not results:
        print("nothing to archive: no enabled integration archives files (see `personalos integrations list`)")
        return
    failed = False
    for name, (st, mism) in results.items():
        print(f"archive ({name}): " + ", ".join(f"{k}={v}" for k, v in st.items()))
        for m in mism:
            print("  HASH MISMATCH:", m)
        failed |= bool(mism)
    if failed:
        sys.exit(2)


def cmd_verify_archive(a):
    cfg = _cfg()
    bad = False
    targets = [i for i in enabled_integrations(cfg) if hasattr(i, "archive_dir")]
    if not targets:
        print("no archive to verify")
    for integ in targets:
        r = archive.verify(integ.archive_dir(cfg))
        if not r["manifest"]:
            print(f"{integ.NAME}: no manifest yet (run `personalos archive`)")
            continue
        print(f"{integ.NAME}: ok={r['ok']} missing={len(r['missing'])} corrupted={len(r['corrupted'])}")
        for x in r["missing"]:
            print("   missing:", x)
        for x in r["corrupted"]:
            print("   corrupted:", x)
        bad |= bool(r["missing"] or r["corrupted"])
        logs.op(cfg, "verify-archive", {"integration": integ.NAME, "ok": r["ok"], "missing": len(r["missing"]),
                                        "corrupted": len(r["corrupted"])})
    sys.exit(1 if bad else 0)


def cmd_maintain(a):
    cfg = _cfg()
    try:
        text, out = maintain.run_maintain(cfg, a.no_archive)
    except index.IndexBusy as e:
        raise UserError(str(e)) from None
    if not a.quiet:
        print(text)
    print(f"\nreport saved: {out}")


def cmd_doctor(a):
    results, _ = health.checks(a.deep)
    if a.json:
        print(json.dumps(results, indent=1))
    else:
        for r in results:
            print(f"[{r['status']:<4}] {r['check']:<26} {r['detail']}")
        fails = sum(r["status"] == "FAIL" for r in results)
        warns = sum(r["status"] == "WARN" for r in results)
        print(f"\n{fails} failed, {warns} warnings" + ("" if fails else " - PersonalOS is usable"))
    if any(r["status"] == "FAIL" for r in results):
        sys.exit(1)


def cmd_stats(a):
    st = index.stats(_cfg())
    print(f"index: {st['db']}  {st['db_bytes'] / 1e6:.1f} MB\nlast index: {st['last_index'] or 'never'}")
    print(f"{'tier':>4} {'kind':<12} {'files':>6} {'chunks':>7} {'source MB':>9} {'redactions':>10}")
    for g in st["groups"]:
        print(f"{g['tier']:>4} {g['kind']:<12} {g['files']:>6} {g['chunks']:>7} {g['bytes'] / 1e6:>9.2f} "
              f"{g['redactions']:>10}")


def cmd_active(a):
    f = _cfg().data_dir / "active" / "ACTIVE_CONTEXT.md"
    print(f.read_text(encoding="utf-8") if f.exists() else "run `personalos index` first")


# ---------------------------------------------------------------- vault

def cmd_capture(a):
    cfg = _cfg()
    text = " ".join(a.text) if a.text else sys.stdin.read()
    try:
        p = vault.capture(cfg, text, a.title)
    except vault.VaultError as e:
        raise UserError(str(e)) from None
    print(f"captured: {p}")
    index.run_index(cfg)


def cmd_inbox(a):
    cfg = _cfg()
    notes = vault.list_notes(cfg, "inbox")
    print(f"inbox: {len(notes)} unprocessed notes in {cfg.folder('inbox')}")
    for n in notes:
        print(f"  {n['modified']}  {n['title']}\n              {n['rel']}")


def cmd_projects(a):
    cfg = _cfg()
    groups = vault.projects(cfg)
    if not groups:
        print(f"no projects yet in {cfg.folder('projects')}")
    for status in sorted(groups, key=lambda s: (s != "active", s)):
        print(f"\n{status.upper()}")
        for n in groups[status]:
            print(f"  {n['title']:<40} {n['modified']}  {n['rel']}")


def cmd_goals(a):
    cfg = _cfg()
    p = cfg.folder("system") / "Goals.md"
    print(p.read_text(encoding="utf-8") if p.exists() else f"no goals file at {p}")


def cmd_obsidian(a):
    from .integrations import obsidian
    print("opening", obsidian.open_vault(_cfg()))


# ---------------------------------------------------------------- backup

def cmd_backup(a):
    cfg = _cfg()
    try:
        out, n = backup.create(cfg, a.to, a.include_archive)
    except backup.BackupError as e:
        raise UserError(str(e)) from None
    print(f"backup written: {out} ({n} files, {out.stat().st_size / 1e6:.1f} MB)")


def cmd_restore(a):
    try:
        if a.verify_only:
            manifest, bad = backup.verify(a.zip)
            print(f"{len(manifest['files'])} files, {len(bad)} damaged")
            sys.exit(1 if bad else 0)
        manifest = backup.restore(a.zip, a.to)
    except backup.BackupError as e:
        raise UserError(str(e)) from None
    target = Path(a.to).resolve()
    print(f"restored {len(manifest['files'])} files (backup from {manifest['created']}) into {target}")
    if a.activate:
        cfg = _cfg()
        cfg.data["vault"] = config.norm(target / "vault")
        if (target / "archive").is_dir():
            cfg.data["archive_dir"] = config.norm(target / "archive")
        cfg.save()
        st, _, _ = index.run_index(cfg, rebuild=True)
        print(f"now using the restored vault; index rebuilt ({st['added']} files)")
    else:
        print(f"to use it: personalos config set vault \"{target / 'vault'}\" and then personalos index --rebuild")


# ---------------------------------------------------------------- servers

def cmd_ui(a):
    from .web.server import serve
    serve(_cfg(), a.port, open_browser=not a.no_browser)


def cmd_mcp(a):
    cfg = _cfg()
    if not cfg.integration("mcp").get("enabled"):
        raise UserError("the MCP server is disabled. Enable it with `personalos integrations enable mcp`.")
    from .integrations.mcp import serve
    serve(cfg)


# ---------------------------------------------------------------- parser

def build_parser():
    ap = argparse.ArgumentParser(prog="personalos", description="PersonalOS: a local-first second brain.")
    ap.add_argument("--version", action="version", version=f"PersonalOS {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="<command>")

    def cmd(name, fn, help_):
        p = sub.add_parser(name, help=help_, description=help_)
        p.set_defaults(fn=fn)
        return p

    p = cmd("init", cmd_init, "create your vault, configuration and search index")
    p.add_argument("--vault", required=True, help="vault folder (new and empty, or existing with --adopt)")
    p.add_argument("--data", help="index and logs folder; an SSD is best (default: per-user app data)")
    p.add_argument("--archive", help="optional long-term archive folder, e.g. on an HDD")
    p.add_argument("--demo", action="store_true", help="fill the vault with fictional demo notes")
    p.add_argument("--adopt", action="store_true", help="use an existing Markdown/Obsidian vault without changing it")
    p.add_argument("--force-config", action="store_true", help="replace an existing configuration")

    p = cmd("search", cmd_search, "search active memory first, then long-term memory")
    p.add_argument("query", nargs="+")
    p.add_argument("-n", "--limit", type=int)
    p.add_argument("--all", action="store_true", help="always include long-term memory")
    p.add_argument("--kind", help="comma list: system,note,raw,archived,inferred,transcript,instruction")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-log", action="store_true", help="do not record this search in the usage log")

    p = cmd("show", cmd_show, "print part of an indexed original (secrets redacted)")
    p.add_argument("path")
    p.add_argument("--loc", help="e.g. L12-40 or 'line 100-140'")
    p.add_argument("--max", type=int, default=12000, help="character limit, 0 for none")

    p = cmd("capture", cmd_capture, "save a new note to the inbox (reads stdin if no text is given)")
    p.add_argument("text", nargs="*")
    p.add_argument("--title")
    cmd("inbox", cmd_inbox, "list unprocessed inbox notes")
    cmd("projects", cmd_projects, "list projects by status")
    cmd("goals", cmd_goals, "print your goals")

    p = cmd("index", cmd_index, "update the search index (only changed files are re-read)")
    p.add_argument("--rebuild", action="store_true", help="rebuild the index from scratch")
    cmd("archive", cmd_archive, "copy new AI transcripts into the archive and verify them")
    cmd("verify-archive", cmd_verify_archive, "check every archived file against its recorded hash")
    p = cmd("maintain", cmd_maintain, "archive + index + a report of suggestions (changes nothing)")
    p.add_argument("--no-archive", action="store_true")
    p.add_argument("--quiet", action="store_true", help="print only where the report was saved")
    p = cmd("doctor", cmd_doctor, "run health checks")
    p.add_argument("--deep", action="store_true", help="also verify every archived file")
    p.add_argument("--json", action="store_true")
    cmd("stats", cmd_stats, "index statistics")
    cmd("active", cmd_active, "print the generated active-context digest")

    p = cmd("backup", cmd_backup, "write a verified zip backup of your vault, config and logs")
    p.add_argument("--to", required=True, help="folder for the backup file (outside the vault)")
    p.add_argument("--include-archive", action="store_true")
    p = cmd("restore", cmd_restore, "restore a backup into an empty folder")
    p.add_argument("zip")
    p.add_argument("--to", help="empty target folder")
    p.add_argument("--activate", action="store_true", help="switch PersonalOS to the restored vault")
    p.add_argument("--verify-only", action="store_true", help="only check the backup's checksums")

    p = cmd("config", cmd_config, "show or change settings")
    p.add_argument("action", choices=["show", "path", "set"])
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p = cmd("integrations", cmd_integrations, "list, enable or disable optional integrations")
    p.add_argument("action", choices=["list", "enable", "disable"])
    p.add_argument("name", nargs="?")

    p = cmd("ui", cmd_ui, "open the local web interface (127.0.0.1 only)")
    p.add_argument("--port", type=int)
    p.add_argument("--no-browser", action="store_true")
    cmd("mcp", cmd_mcp, "run the MCP server on stdio (for AI assistants)")
    cmd("obsidian", cmd_obsidian, "open the vault in Obsidian")
    return ap


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    a = build_parser().parse_args(argv)
    if a.cmd == "restore" and not a.verify_only and not a.to:
        print("error: restore needs --to <empty folder> (or --verify-only)", file=sys.stderr)
        sys.exit(1)
    try:
        a.fn(a)
    except UserError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
