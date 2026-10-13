"""Local operation log and usage log. Both stay in the data directory; nothing is sent anywhere."""
import datetime as dt
import json


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def op(cfg, name, details):
    cfg.logs.mkdir(parents=True, exist_ok=True)
    entry = {"ts": _now(), "op": name, **details}
    with open(cfg.logs / "operations.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def usage(cfg, entry):
    """Record which files a search returned or which file was opened, for promotion suggestions.

    The query text itself is only stored when privacy.log_queries is true.
    """
    cfg.logs.mkdir(parents=True, exist_ok=True)
    if not cfg.data["privacy"].get("log_queries", True):
        entry = {k: v for k, v in entry.items() if k != "q"}
    with open(cfg.logs / "usage.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _now(), **entry}, ensure_ascii=False) + "\n")


def most_used(cfg, days):
    f = cfg.logs / "usage.jsonl"
    if not f.exists():
        return []
    cutoff = (dt.datetime.now() - dt.timedelta(days=days)).isoformat()
    counts = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("ts", "") < cutoff:
            continue
        for p in ([e["show"]] if "show" in e else []) + e.get("hits", []):
            counts[p] = counts.get(p, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])


def recent_ops(cfg, n=20):
    f = cfg.logs / "operations.jsonl"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines()[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out[::-1]
