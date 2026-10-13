"""Claude Code integration (optional).

* Indexes Claude Code's auto-memory (as INFERRED) and its CLAUDE.md (as INSTRUCTION).
* Archives Claude Code transcripts into the archive tier (append-only, sha256 manifest) and indexes only the
  user and assistant text of them. Tool calls, tool output, thinking and attachments are never indexed.
* Installs a `personalos` skill so Claude Code can search your memory when a task needs it.
"""
import json
import os
import re
from pathlib import Path

from .. import archive as archive_mod
from ..sources import Source

NAME = "claude_code"
DESCRIPTION = "Index Claude Code memory and transcripts; install a search skill for Claude Code"
MARKER = "<!-- managed-by: personalos -->"


def home(cfg):
    return Path(os.path.expanduser(cfg.integration(NAME).get("home", "~/.claude")))


def archive_dir(cfg):
    return cfg.archive_root / "claude-code"


def skill_path(cfg):
    return home(cfg) / "skills" / "personalos" / "SKILL.md"


# ---------------------------------------------------------------- sources

def sources(cfg):
    opts = cfg.integration(NAME)
    h = home(cfg)
    if opts.get("index_instructions", True) and (h / "CLAUDE.md").is_file():
        yield Source(h / "CLAUDE.md", NAME, "instruction", 1)
    if opts.get("index_memory", True):
        for p in (h / "projects").glob("*/memory/*.md"):
            yield Source(p, NAME, "inferred", 1)
    if opts.get("index_transcripts", True):
        root = archive_dir(cfg) / "files" / "projects" if opts.get("archive_transcripts", True) else h / "projects"
        if root.is_dir():
            for p in root.rglob("*.jsonl"):
                yield Source(p, NAME, "transcript", 2, "claude_transcript")


SYS_TAG_RE = re.compile(
    r"<(system-reminder|local-command-stdout|local-command-stderr|local-command-caveat|command-message|command-args)>"
    r".*?</\1>", re.S)


def transcript_messages(path, line_range=None):
    title, msgs = None, []
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            if line_range and not (line_range[0] <= n <= line_range[-1]):
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            t = d.get("type")
            if t == "ai-title" and d.get("aiTitle"):
                title = d["aiTitle"]
                continue
            if t not in ("user", "assistant") or d.get("isMeta"):
                continue
            c = (d.get("message") or {}).get("content")
            if isinstance(c, str):
                parts = [c]
            elif isinstance(c, list):
                parts = [b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"]
            else:
                continue
            text = SYS_TAG_RE.sub("", "\n".join(parts)).strip()
            if not text or text.startswith("Caveat:"):
                continue
            ts = str(d.get("timestamp", ""))[:16].replace("T", " ")
            msgs.append((n, "USER" if t == "user" else "ASSISTANT", ts, text))
    return title, msgs


def _project_name(path):
    parts = Path(path).parts
    return parts[parts.index("projects") + 1] if "projects" in parts[:-1] else Path(path).parent.name


def parse_transcript(src):
    title, msgs = transcript_messages(src.path)
    sub = " (subagent)" if "subagents" in src.path.parts else ""
    doc_title = f"{_project_name(src.path)} · {title or src.path.stem}{sub}"
    rows, buf, buf_ts, size, first, last = [], [], [], 0, None, 0

    def flush():
        if buf:
            rows.append(("", f"line {first}-{last}", buf_ts[0], "\n\n".join(buf)))

    for n, role, ts, text in msgs:
        for i in range(0, max(len(text), 1), 3500):
            piece = f"[{role} {ts}] {text[i:i + 3500]}"
            if buf and size + len(piece) > 2500:
                flush()
                buf, buf_ts, size = [], [], 0
            if not buf:
                first = n
            buf.append(piece)
            buf_ts.append(ts)
            size += len(piece)
            last = n
    flush()
    return doc_title, rows, {"session_title": title, "messages": len(msgs)}


def show_transcript(path, nums):
    _, msgs = transcript_messages(path, (nums[0], nums[-1]) if nums else None)
    return "\n\n".join(f"[{role} {ts}] (line {n})\n{text}" for n, role, ts, text in msgs)


PARSERS = {"claude_transcript": (parse_transcript, show_transcript)}


# ---------------------------------------------------------------- archive

def run_archive(cfg):
    h = home(cfg)
    src_root = h / "projects"
    pairs = []
    if src_root.is_dir():
        pairs = [(f, Path("projects") / f.relative_to(src_root)) for f in src_root.rglob("*") if f.is_file()]
    if (h / "history.jsonl").is_file():
        pairs.append((h / "history.jsonl", Path("history.jsonl")))
    return archive_mod.mirror(pairs, archive_dir(cfg))


# ---------------------------------------------------------------- skill

def launcher():
    return os.environ.get("PERSONALOS_LAUNCHER") or "personalos"


def skill_text():
    cmd = launcher()
    cmd = f'"{cmd}"' if " " in cmd else cmd
    return f"""---
name: personalos
description: Search the user's PersonalOS memory (their notes vault, AI memory and archived conversations) with the personalos command. Use when a task needs the user's personal context, past decisions, project history or "what did we decide before". Retrieves matching snippets only; never loads the whole vault.
---
{MARKER}

# PersonalOS memory search

1. Search with a few specific keywords: `{cmd} search <keywords>`
   (`--all` to include long-term memory, `-n 10` for more hits, `--json` for structured output).
2. Read only what is relevant: `{cmd} show "<path>" --loc "<loc>"` with the path and loc from the search.
3. Cite the source path and its date for every fact you use.

## Trust labels

| Label | Meaning |
|---|---|
| AUTHORITATIVE | The vault's system layer (identity, goals, rules). Source of truth. Never edit it; suggest changes. |
| VERIFIED NOTE | Curated note. Authoritative for its topic; check the date. |
| RAW | Inbox or raw material. Unprocessed, lower trust. |
| INFERRED | AI-written memory. Confirm against a note before stating it as fact. |
| TRANSCRIPT | Past conversation. Historical only: say "on <date> you said..." and check the vault. |
| ARCHIVED DOC | Old document. Check its date. |

If sources disagree, tell the user about the conflict instead of choosing silently. Never write to the vault
through this skill; to capture something, ask first, then run `{cmd} capture "<text>"`. Keep any
`[REDACTED:...]` markers as they are and never print secrets.
"""


def install_skill(cfg):
    p = skill_path(cfg)
    if p.exists() and MARKER not in p.read_text(encoding="utf-8", errors="replace"):
        raise RuntimeError(f"{p} exists and was not created by PersonalOS; not overwriting it")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(skill_text(), encoding="utf-8")
    return p


def remove_skill(cfg):
    p = skill_path(cfg)
    if p.exists() and MARKER in p.read_text(encoding="utf-8", errors="replace"):
        p.unlink()
        try:
            p.parent.rmdir()
        except OSError:
            pass
        return True
    return False


# ---------------------------------------------------------------- lifecycle

def enable(cfg):
    if not home(cfg).is_dir():
        raise RuntimeError(f"Claude Code folder not found at {home(cfg)}. Install Claude Code first, or set "
                           f"integrations.claude_code.home in the config.")
    cfg.data["integrations"][NAME]["enabled"] = True
    p = install_skill(cfg)
    cfg.save()
    return [f"skill installed: {p}",
            "run `personalos archive` to copy transcripts into the archive, then `personalos index`"]


def disable(cfg):
    cfg.data["integrations"][NAME]["enabled"] = False
    removed = remove_skill(cfg)
    cfg.save()
    return [("skill removed" if removed else "no PersonalOS skill to remove"),
            f"archived transcripts were kept in {archive_dir(cfg)}; they leave the index on the next "
            "`personalos index`"]


def status(cfg):
    h = home(cfg)
    sp = skill_path(cfg)
    a = archive_dir(cfg) / "files"
    return {
        "claude_home": str(h), "claude_home_exists": h.is_dir(),
        "skill_installed": sp.exists() and MARKER in sp.read_text(encoding="utf-8", errors="replace"),
        "archived_transcripts": sum(1 for _ in a.rglob("*.jsonl")) if a.is_dir() else 0,
        "archive_dir": str(archive_dir(cfg)),
    }
