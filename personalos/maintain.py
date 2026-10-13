"""Maintenance: archive, re-index, then a report of suggestions. It never changes a note."""
import datetime as dt
import json
import re
import time
from pathlib import Path

from . import index, logs
from .integrations import enabled_integrations
from .index import fmt_date, now_iso

GENERIC_TITLES = {"readme", "memory", "index", "agents", "claude", "home"}
STATUS_DONE = re.compile(r"^(done|completed?|finished|archived|cancell?ed|shipped)$", re.I)


def norm_title(path):
    return re.sub(r"[\s_\-]*(\d+|copy)$", "", Path(path).stem.lower()).strip()


def run_archives(cfg):
    out = {}
    for integ in enabled_integrations(cfg):
        if hasattr(integ, "run_archive") and cfg.integration(integ.NAME).get("archive_transcripts", True):
            stats, mismatched = integ.run_archive(cfg)
            logs.op(cfg, "archive", {"integration": integ.NAME, **stats, "mismatched": mismatched})
            out[integ.NAME] = (stats, mismatched)
    return out


def run_maintain(cfg, skip_archive=False):
    report = [f"# Maintenance report - {now_iso()}", "",
              "Suggestions only. Nothing below has been applied, and no note was changed.", ""]
    if not skip_archive:
        for name, (a, mism) in run_archives(cfg).items():
            report += [f"## Archive ({name})", f"- new {a['new']}, updated {a['updated']}, preserved before "
                       f"overwrite {a['preserved']}, hash mismatches {a['hash_mismatch']}, "
                       f"{a['archived_files']} files archived"] + [f"  - MISMATCH {m}" for m in mism] + [""]
    stats, changed, errors = index.run_index(cfg)
    report += ["## Index", f"- added {stats['added']}, updated {stats['updated']}, removed {stats['removed']}, "
               f"unchanged {stats['unchanged']}, unreadable {stats['errors']}, secret-like strings redacted "
               f"{stats['redactions']}"]
    if stats["recovered_corrupt_index"]:
        report.append("- the previous index was corrupt; it was moved aside and rebuilt")
    report += [f"  - {c}" for c in changed[:50]] + [f"  - ERROR {e}" for e in errors[:20]] + [""]

    con, _ = index.open_db(cfg)
    files = [dict(r) for r in con.execute("select * from files where kind != 'transcript'")]
    vault = str(cfg.vault)

    dup = {}
    for f in files:
        dup.setdefault(f["sha256"], []).append(f["path"])
    exact = [v for v in dup.values() if len(v) > 1]
    report.append("## Exact duplicates (identical content)")
    report += [f"- {' == '.join(v)}" for v in exact] or ["- none"]

    by_title = {}
    for f in files:
        if norm_title(f["path"]) not in GENERIC_TITLES:
            by_title.setdefault(norm_title(f["path"]), []).append(f)
    diverged = [v for v in by_title.values() if len(v) > 1 and len({f["sha256"] for f in v}) > 1]
    report += ["", "## Same title, different content (possible conflict - compare them)"]
    report += ["- " + " vs ".join(f"{f['path']} ({fmt_date(f['mtime'])})" for f in v) for v in diverged] or ["- none"]

    report += ["", "## AI-written memories that may be outdated (heuristic)"]
    flagged = 0
    for f in files:
        if f["kind"] != "inferred" or Path(f["path"]).name == "MEMORY.md":
            continue
        meta = json.loads(f["meta"] or "{}")
        words = [w for w in re.findall(r"\w+", meta.get("description", "") + " " + meta.get("name", ""))
                 if len(w) >= 5][:6]
        if not words:
            continue
        rel = index.search(cfg, " ".join(words), limit=3, all_tiers=True, kinds=["note", "system"], con=con)
        for r in rel["tier1"] + rel["tier2"]:
            if r["mtime"] > f["mtime"] + 86400:
                report.append(f"- {f['path']} ({fmt_date(f['mtime'])}): related note {r['path']} changed later "
                              f"({fmt_date(r['mtime'])}); check the memory is still true")
                flagged += 1
                break
    if not flagged:
        report.append("- none")

    stale_days = cfg.data["maintenance"]["stale_days"]
    stale_cut = time.time() - stale_days * 86400
    projects_dir = str(cfg.folder("projects"))
    report += ["", f"## Archival suggestions (active notes marked done, or projects untouched > {stale_days} days)"]
    sugg = 0
    for f in files:
        if not f["path"].startswith(vault) or f["tier"] != 1 or f["kind"] == "system":
            continue
        status = json.loads(f["meta"] or "{}").get("status", "")
        if STATUS_DONE.match(status.strip()):
            report.append(f"- {f['path']}: status `{status}` but still in an active folder")
            sugg += 1
        elif f["mtime"] < stale_cut and f["path"].startswith(projects_dir):
            report.append(f"- {f['path']}: not modified since {fmt_date(f['mtime'])}")
            sugg += 1
    if not sugg:
        report.append("- none")

    min_hits = cfg.data["maintenance"]["promote_min_hits"]
    report += ["", f"## Promotion suggestions (long-term items used {min_hits}+ times in 30 days)"]
    tier2 = {r["path"] for r in con.execute("select path from files where tier = 2")}
    promo = [(p, n) for p, n in logs.most_used(cfg, 30) if p in tier2 and n >= min_hits]
    report += [f"- {p}: {n} uses; consider linking it from your current-focus note" for p, n in promo] or ["- none"]

    raw = [f for f in files if f["kind"] == "raw"]
    report += ["", "## Unprocessed material", f"- {len(raw)} inbox/raw notes"
               + (f"; oldest from {fmt_date(min(f['mtime'] for f in raw))}" if raw else "")]

    secrets = [f for f in files if f["redactions"]]
    report += ["", "## Notes containing secret-like strings (redacted in the index; the notes are unchanged)"]
    report += [f"- {f['path']}: {f['redactions']} match(es) - move these to a password manager" for f in secrets] \
        or ["- none"]
    con.close()

    out = cfg.logs / "reports" / f"maintenance-{dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    logs.op(cfg, "maintain", {"report": str(out), "duplicates": len(exact), "diverged": len(diverged),
                              "outdated_inferred": flagged, "archival_suggestions": sugg, "promotions": len(promo)})
    return "\n".join(report), out


def list_reports(cfg):
    d = cfg.logs / "reports"
    return sorted(d.glob("maintenance-*.md"), reverse=True) if d.is_dir() else []
