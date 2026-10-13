"""SQLite FTS5 index: incremental updates, tiered search, integrity checks and corruption recovery.

The index is a cache. Deleting it loses nothing: `personalos index --rebuild` recreates it from the sources.
"""
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from . import logs
from .redact import is_denied_file, redact
from .sources import LABELS, iter_sources, parsers

INDEX_VERSION = 1
SCHEMA = """
create table if not exists files(
  path text primary key, origin text, kind text, tier int, parser text, mtime real, size int,
  sha256 text, indexed_at text, chunks int, redactions int, meta text);
create table if not exists chunks(
  id integer primary key, path text, kind text, tier int, title text, heading text, loc text, ts text);
create index if not exists chunks_path on chunks(path);
create index if not exists chunks_tier on chunks(tier, kind);
create virtual table if not exists fts using fts5(title, heading, body, tokenize='unicode61 remove_diacritics 2');
create table if not exists state(key text primary key, value text);
"""


class IndexBusy(Exception):
    pass


def now_iso():
    return dt.datetime.now().isoformat(timespec="seconds")


def fmt_date(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------- open / recover

def _connect(path):
    con = sqlite3.connect(path, timeout=10)
    try:
        con.row_factory = sqlite3.Row
        con.executescript(SCHEMA)
        row = con.execute("select value from state where key='index_version'").fetchone()
        if row is None:
            con.execute("insert into state values('index_version', ?)", (str(INDEX_VERSION),))
            con.commit()
        elif int(row[0]) != INDEX_VERSION:
            raise sqlite3.DatabaseError(f"index version {row[0]} != {INDEX_VERSION}")
        con.execute("select count(*) from files").fetchone()
        return con
    except BaseException:
        con.close()  # Windows cannot move the file aside while a handle is open
        raise


def quarantine(cfg, reason):
    """Move a broken index aside (never delete it) so a fresh one can be built."""
    db = cfg.db_path
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    moved = []
    for suffix in ("", "-journal", "-wal", "-shm"):
        f = Path(str(db) + suffix)
        if f.exists():
            dst = Path(f"{db}.corrupt-{stamp}{suffix}")
            os.replace(f, dst)
            moved.append(str(dst))
    logs.op(cfg, "quarantine", {"reason": reason, "moved": moved})
    return moved


def open_db(cfg, recover=True):
    """Open the index. A corrupt or incompatible index is quarantined and recreated empty (recovered=True)."""
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return _connect(cfg.db_path), False
    except sqlite3.DatabaseError as e:
        if not recover:
            raise
        quarantine(cfg, str(e))
        return _connect(cfg.db_path), True


def integrity(cfg):
    """Return a list of problems (empty when healthy). Does not modify anything."""
    if not cfg.db_path.exists():
        return ["index does not exist yet (run `personalos index`)"]
    try:
        con = sqlite3.connect(f"file:{cfg.db_path.as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            problems = [r[0] for r in con.execute("pragma integrity_check") if r[0] != "ok"]
            if not problems:
                n_chunks = con.execute("select count(*) from chunks").fetchone()[0]
                n_fts = con.execute("select count(*) from fts").fetchone()[0]
                if n_chunks != n_fts:
                    problems.append(f"chunk table ({n_chunks}) and search table ({n_fts}) disagree")
            return problems
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        return [f"index cannot be read: {e}"]


@contextmanager
def index_lock(cfg, stale_after=1800):
    lock = cfg.db_path.parent / "index.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - lock.stat().st_mtime < stale_after:
            raise IndexBusy(f"another indexing run is in progress ({lock}); try again shortly") from None
        lock.unlink(missing_ok=True)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


# ---------------------------------------------------------------- indexing

def drop_file(con, path):
    ids = [r[0] for r in con.execute("select id from chunks where path=?", (path,))]
    con.executemany("delete from fts where rowid=?", [(i,) for i in ids])
    con.execute("delete from chunks where path=?", (path,))
    con.execute("delete from files where path=?", (path,))


def index_file(con, src, digest, st, parse):
    sp = str(src.path)
    title, rows, meta = parse(src)  # parse before dropping, so a parse error keeps the old entry
    drop_file(con, sp)
    redactions = 0
    for heading, loc, ts, body in rows:
        body, k = redact(body)
        redactions += k
        cur = con.execute("insert into chunks(path,kind,tier,title,heading,loc,ts) values(?,?,?,?,?,?,?)",
                          (sp, src.kind, src.tier, title, heading, loc, ts))
        # Front matter is searchable by its content only, so it never outranks the note body on a title match.
        fts_title = "" if heading == "frontmatter" else title
        con.execute("insert into fts(rowid,title,heading,body) values(?,?,?,?)",
                    (cur.lastrowid, fts_title, heading, body))
    con.execute("insert into files values(?,?,?,?,?,?,?,?,?,?,?,?)",
                (sp, src.origin, src.kind, src.tier, src.parser, st.st_mtime, st.st_size, digest, now_iso(),
                 len(rows), redactions, json.dumps(meta, ensure_ascii=False)))
    return redactions


def run_index(cfg, rebuild=False):
    """Incremental update: unchanged files (same mtime+size, or same sha256) are skipped."""
    t0 = time.perf_counter()
    with index_lock(cfg):
        if rebuild:
            for suffix in ("", "-journal", "-wal", "-shm"):
                Path(str(cfg.db_path) + suffix).unlink(missing_ok=True)
        con, recovered = open_db(cfg)
        parse_fns = parsers()
        known = {r["path"]: r for r in con.execute("select path,kind,tier,mtime,size,sha256 from files")}
        seen = set()
        stats = {"added": 0, "updated": 0, "unchanged": 0, "removed": 0, "skipped_secret_files": 0,
                 "errors": 0, "redactions": 0}
        changed, errors = [], []
        try:
            for src in iter_sources(cfg):
                if is_denied_file(src.path.name):
                    stats["skipped_secret_files"] += 1
                    continue
                sp = str(src.path)
                seen.add(sp)
                try:
                    st = src.path.stat()
                    row = known.get(sp)
                    same_class = row is not None and row["kind"] == src.kind and row["tier"] == src.tier
                    if same_class and row["mtime"] == st.st_mtime and row["size"] == st.st_size:
                        stats["unchanged"] += 1
                        continue
                    digest = sha256_file(src.path)
                    if same_class and row["sha256"] == digest:
                        con.execute("update files set mtime=?, size=? where path=?", (st.st_mtime, st.st_size, sp))
                        stats["unchanged"] += 1
                        continue
                    stats["redactions"] += index_file(con, src, digest, st, parse_fns[src.parser][0])
                    stats["updated" if row else "added"] += 1
                    changed.append(sp)
                except (OSError, UnicodeError, ValueError) as e:
                    # One unreadable file must not stop the run; it keeps its previous index entry.
                    stats["errors"] += 1
                    errors.append(f"{sp}: {type(e).__name__}: {e}")
            for sp in set(known) - seen:
                drop_file(con, sp)
                stats["removed"] += 1
                changed.append(sp + "  (removed: original no longer present)")
            con.execute("insert or replace into state values('last_index', ?)", (now_iso(),))
            con.commit()
        except BaseException:
            con.rollback()
            con.close()
            raise
        stats["seconds"] = round(time.perf_counter() - t0, 2)
        stats["recovered_corrupt_index"] = recovered
        logs.op(cfg, "index", {**stats, "rebuild": rebuild, "changed": changed[:200], "error_list": errors[:50]})
        write_active(cfg, con)
        con.close()
    return stats, changed, errors


# ---------------------------------------------------------------- search

STOPWORDS = {"the", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "what", "why", "how", "when",
             "where", "who", "did", "do", "does", "we", "i", "my", "a", "an", "it", "that", "this", "with",
             "about", "from", "be", "at", "by", "as"}


def fts_query(q, mode):
    """Turn free text into a safe FTS5 expression: every token is quoted, so no FTS syntax gets through."""
    words = re.findall(r"\w+", q)
    toks = [t for t in words if len(t) > 1 and t.lower() not in STOPWORDS] or \
        [t for t in words if len(t) > 1] or words
    if not toks:
        return None
    return f" {mode} ".join(f'"{t}"' + ("*" if len(t) >= 4 else "") for t in toks[:32])


def _search_tier(cfg, con, match, tier, limit, kinds, origins_excluded):
    sql = ("select c.path, c.kind, c.tier, c.title, c.heading, c.loc, c.ts, f.mtime, f.origin, "
           "snippet(fts, 2, '«', '»', ' … ', 24) as snip, bm25(fts, 6.0, 3.0, 1.0) as score "
           "from fts join chunks c on c.id = fts.rowid join files f on f.path = c.path "
           "where fts match ? and c.tier = ?")
    args = [match, tier]
    if kinds:
        sql += f" and c.kind in ({','.join('?' * len(kinds))})"
        args += kinds
    if origins_excluded:
        sql += f" and f.origin not in ({','.join('?' * len(origins_excluded))})"
        args += origins_excluded
    sql += " order by score limit ?"
    args.append(limit * 8)
    weights = cfg.data["search"]["kind_weight"]
    rows = sorted(con.execute(sql, args), key=lambda r: r["score"] * weights.get(r["kind"], 1.0))
    out, per_path = [], {}
    for r in rows:
        if per_path.get(r["path"], 0) >= 1:  # best chunk per file; `show` opens the rest
            continue
        per_path[r["path"]] = per_path.get(r["path"], 0) + 1
        hit = dict(r)
        hit["label"] = LABELS[hit["kind"]]
        hit["date"] = fmt_date(hit["mtime"])
        out.append(hit)
        if len(out) >= limit:
            break
    return out


def search(cfg, query, limit=None, all_tiers=False, kinds=None, exclude_origins=None, con=None):
    """Tier 1 first; tier 2 only if tier 1 has fewer than `limit` hits (or all_tiers). AND, then OR fallback."""
    limit = limit or cfg.data["search"]["limit"]
    own = con is None
    if own:
        con, _ = open_db(cfg)
    result = {"tier1": [], "tier2": [], "tier2_searched": False, "mode": "AND"}
    try:
        for mode in ("AND", "OR"):
            match = fts_query(query, mode)
            if not match:
                break
            t1 = _search_tier(cfg, con, match, 1, limit, kinds, exclude_origins)
            t2_searched = all_tiers or len(t1) < limit
            if t2_searched:
                t2 = _search_tier(cfg, con, match, 2, limit, kinds, exclude_origins)
            else:
                # Tier 1 is full, but a long-term file whose title matches the query is still worth showing.
                t2 = _search_tier(cfg, con, f"title : ({match})", 2, 2, kinds, exclude_origins)
            result = {"tier1": t1, "tier2": t2, "tier2_searched": t2_searched, "mode": mode}
            if t1 or t2:
                break
    finally:
        if own:
            con.close()
    return result


class NotIndexed(Exception):
    pass


def show(cfg, path, loc=None, max_chars=12000):
    """Read part of an indexed original, redacted. Refuses files that are not in the index."""
    con, _ = open_db(cfg)
    row = con.execute("select * from files where path=?", (str(Path(path)),)).fetchone()
    con.close()
    if not row:
        raise NotIndexed("only files that are in the index can be shown (search first)")
    p = Path(row["path"])
    if not p.exists():
        raise NotIndexed(f"original no longer exists: {p} (run `personalos index`)")
    nums = [int(x) for x in re.findall(r"\d+", loc or "")[:2]]
    text = parsers()[row["parser"]][1](p, nums)
    text, k = redact(text)
    truncated = bool(max_chars) and len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return {"path": str(p), "kind": row["kind"], "label": LABELS[row["kind"]], "date": fmt_date(p.stat().st_mtime),
            "stale": p.stat().st_mtime != row["mtime"], "text": text, "redactions": k, "truncated": truncated}


def stats(cfg):
    con, _ = open_db(cfg)
    last = con.execute("select value from state where key='last_index'").fetchone()
    rows = [dict(r) for r in con.execute(
        "select tier, kind, count(*) files, sum(chunks) chunks, sum(size) bytes, sum(redactions) redactions "
        "from files group by tier, kind order by tier, kind")]
    con.close()
    size = cfg.db_path.stat().st_size if cfg.db_path.exists() else 0
    return {"db": str(cfg.db_path), "db_bytes": size, "last_index": last[0] if last else None, "groups": rows}


# ---------------------------------------------------------------- active digest

def write_active(cfg, con):
    """Generated pointer list of tier-1 files: path, date, one-line summary. Never a copy of content."""
    rows = list(con.execute("select path, kind, mtime, meta from files where tier=1 order by path"))

    def line(r):
        meta = json.loads(r["meta"] or "{}")
        desc = meta.get("description") or meta.get("summary") or ""
        return f"- `{r['path']}` - modified {fmt_date(r['mtime'])} - {desc[:120]}"

    groups = [
        ("System layer (authoritative)", "system"),
        ("Active notes", "note"),
        ("Unprocessed inbox (lower trust)", "raw"),
        ("AI assistant instructions", "instruction"),
        ("AI-written memory (verify before use)", "inferred"),
    ]
    out = ["# Active context (generated - do not edit)", "",
           f"Generated {now_iso()} by `personalos index`. Pointers only; edit the source files, not this one."]
    for title, kind in groups:
        items = [line(r) for r in rows if r["kind"] == kind]
        if items:
            out += ["", f"## {title}", *items]
    used = logs.most_used(cfg, 30)
    if used:
        out += ["", "## Most used in the last 30 days"] + [f"- `{p}` - {n} uses" for p, n in used[:10]]
    active = cfg.data_dir / "active" / "ACTIVE_CONTEXT.md"
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text("\n".join(out) + "\n", encoding="utf-8")
