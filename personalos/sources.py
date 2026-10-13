"""Where indexed content comes from, and how each kind of file is split into searchable chunks.

Core sources are the vault and any extra folders from the config. Integrations add their own sources and
parsers (see personalos.integrations). Every source is read-only: nothing here writes to it.
"""
import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Source:
    path: Path
    origin: str  # vault | extra | <integration name>
    kind: str  # system | note | raw | archived | inferred | transcript | instruction
    tier: int
    parser: str = "markdown"


LABELS = {
    "system": "AUTHORITATIVE",
    "note": "VERIFIED NOTE",
    "raw": "RAW",
    "archived": "ARCHIVED DOC",
    "inferred": "INFERRED",
    "transcript": "TRANSCRIPT",
    "instruction": "INSTRUCTION",
}
LABEL_HELP = {
    "system": "system layer of your vault - authoritative",
    "note": "curated vault note - authoritative for its topic",
    "raw": "unprocessed material - lower trust, not knowledge",
    "archived": "long-term archive document - check its date",
    "inferred": "AI-written memory - verify before relying on it",
    "transcript": "past AI conversation - historical context, not a current fact",
    "instruction": "AI assistant instruction file",
}


def vault_kind(rel, rules):
    for rule in rules:
        if fnmatch.fnmatch(rel, rule["glob"]):
            return rule["kind"], rule["tier"]
    return "note", 2


def iter_sources(cfg):
    from .integrations import enabled_integrations

    vault = cfg.vault
    rules = cfg.vault_rules()
    exclude = set(cfg.data["vault_exclude_dirs"])
    if vault.is_dir():
        for p in vault.rglob("*.md"):
            rel = p.relative_to(vault)
            if any(part in exclude for part in rel.parts):
                continue
            kind, tier = vault_kind(rel.as_posix(), rules)
            yield Source(p, "vault", kind, tier)
    for s in cfg.data["extra_sources"]:
        root = Path(s["path"])
        exts = {e.lower() for e in s.get("extensions", [".md", ".txt"])}
        if root.is_dir():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in exts:
                    yield Source(p, "extra", s.get("kind", "archived"), s.get("tier", 2))
    for integ in enabled_integrations(cfg):
        if hasattr(integ, "sources"):
            yield from integ.sources(cfg)


# ---------------------------------------------------------------- markdown

FRONT_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
HEADING_RE = re.compile(r"#{1,6}\s+(.*)")
MAX_CHUNK = 1800


def parse_frontmatter(text):
    meta = {}
    m = FRONT_RE.match(text)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip().strip("\"'")
    return meta, m


def md_chunks(text):
    """Split Markdown at headings (and every ~1800 chars). Returns ([(heading, loc, body)], meta)."""
    text = text.replace("\r\n", "\n")
    meta, m = parse_frontmatter(text)
    offset = 0
    if m:
        offset = text[: m.end()].count("\n")
        text = text[m.end():]
    chunks, buf, heading = [], [], ""
    start = line_no = offset
    size = 0

    def flush(end):
        body = "\n".join(buf).strip()
        if body:
            chunks.append((heading, f"L{start + 1}-{end}", body))

    for line in text.split("\n"):
        line_no += 1
        hm = HEADING_RE.match(line)
        if hm or size > MAX_CHUNK:
            flush(line_no - 1)
            buf, size, start = [], 0, line_no - 1
            if hm:
                heading = hm.group(1).strip()
        buf.append(line)
        size += len(line) + 1
    flush(line_no)
    if m:
        chunks.insert(0, ("frontmatter", f"L1-{offset}", m.group(1)))
    first = next((l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")), "")
    meta.setdefault("summary", first[:140])
    return chunks, meta


def parse_markdown(src):
    text = src.path.read_text(encoding="utf-8", errors="replace")
    chunks, meta = md_chunks(text)
    return src.path.stem, [(h, loc, "", body) for h, loc, body in chunks], meta


def show_markdown(path, nums):
    lines = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    if nums:
        lines = lines[nums[0] - 1: nums[-1]]
    return "\n".join(lines)


def parsers():
    """parser name -> (parse(source) -> (title, rows, meta), show(path, line_numbers) -> text)."""
    from .integrations import all_integrations

    out = {"markdown": (parse_markdown, show_markdown)}
    for integ in all_integrations():
        out.update(getattr(integ, "PARSERS", {}))
    return out
