"""Vault operations.

PersonalOS never edits or deletes an existing note. The only writes to a vault are:
  * `init` copying the template into a new (empty) vault, and
  * `capture` creating a new, uniquely named note in the inbox.
"""
import datetime as dt
import os
import re
import shutil
from pathlib import Path

from .redact import contains_secret, redact
from .sources import parse_frontmatter

TEMPLATES = Path(__file__).resolve().parent / "templates"
MAX_CAPTURE = 20000


class VaultError(Exception):
    pass


def create_vault(target, template="default", adopt=False):
    """Create a vault from a template. Refuses to write into a non-empty folder unless adopting it as-is."""
    target = Path(target)
    if template not in ("default", "demo"):
        raise VaultError(f"unknown template '{template}'")
    if target.exists() and any(target.iterdir()):
        if adopt:
            return {"created": [], "adopted": str(target)}
        raise VaultError(f"{target} is not empty. Choose an empty folder, or pass --adopt to use it as an "
                         "existing vault (nothing in it will be changed).")
    if adopt:
        raise VaultError(f"{target} does not exist or is empty; there is no vault to adopt")
    # The demo is the starter template with fictional notes layered on top.
    layers = [TEMPLATES / "demo", TEMPLATES / "default"] if template == "demo" else [TEMPLATES / "default"]
    created = []
    for src in layers:
        for f in sorted(src.rglob("*")):
            rel = f.relative_to(src)
            dst = target / rel
            if f.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            elif not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
                created.append(rel.as_posix())
    return {"created": created, "adopted": None}


def safe_resolve(cfg, rel):
    """Resolve a vault-relative path and require it to stay inside the vault."""
    root = cfg.vault.resolve()
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        raise VaultError("path is outside the vault")
    return p


def _slug(text):
    s = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    s = re.sub(r"[\s_-]+", "-", s)[:50].strip("-")
    return s or "note"


def capture(cfg, text, title=None, source="cli"):
    """Create a new inbox note. Never overwrites: the file is created with O_EXCL."""
    text = (text or "").strip()
    if not text:
        raise VaultError("nothing to capture")
    if len(text) > MAX_CAPTURE:
        raise VaultError(f"capture is limited to {MAX_CAPTURE} characters")
    if contains_secret(text) or (title and contains_secret(title)):
        raise VaultError("this text looks like it contains a password, key or token. Store secrets in a "
                         "password manager, not in notes.")
    inbox = cfg.folder("inbox")
    inbox.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now()
    title = (title or text.splitlines()[0])[:80].strip().lstrip("#").strip()
    base = f"{now:%Y-%m-%d_%H%M%S}-{_slug(title)}"
    body = (f"---\ncaptured: {now.isoformat(timespec='seconds')}\nsource: {source}\nstatus: unprocessed\n---\n\n"
            f"# {title}\n\n{text}\n")
    for n in range(100):
        p = inbox / (base + (f"-{n}" if n else "") + ".md")
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        return p
    raise VaultError("could not find a free file name in the inbox")


def note_info(cfg, p):
    text = p.read_text(encoding="utf-8", errors="replace")
    meta, m = parse_frontmatter(text)
    rest = text[m.end():] if m else text
    title = next((l.lstrip("#").strip() for l in rest.splitlines() if l.startswith("# ")), p.stem)
    first = next((l.strip() for l in rest.splitlines() if l.strip() and not l.startswith("#")), "")
    first = re.sub(r"\[\[([^\]|]+\|)?([^\]]+)\]\]", r"\2", first).lstrip("-*> ").replace("**", "")
    st = p.stat()
    return {"rel": p.relative_to(cfg.vault).as_posix(), "path": str(p), "title": title,
            "status": meta.get("status", ""), "summary": redact(first[:160])[0],
            "modified": dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"), "mtime": st.st_mtime}


def list_notes(cfg, role, recursive=True):
    folder = cfg.folder(role)
    if not folder.is_dir():
        return []
    files = folder.rglob("*.md") if recursive else folder.glob("*.md")
    out = [note_info(cfg, p) for p in files if p.name.lower() != "readme.md"]
    return sorted(out, key=lambda n: -n["mtime"])


def projects(cfg):
    """Projects grouped by frontmatter status (active, waiting, done...)."""
    groups = {}
    for n in list_notes(cfg, "projects"):
        groups.setdefault((n["status"] or "unspecified").lower(), []).append(n)
    return groups


def tree(cfg, rel=""):
    """One level of the vault: folders and Markdown notes. Excluded dirs are hidden."""
    p = safe_resolve(cfg, rel)
    if not p.is_dir():
        raise VaultError("not a folder")
    exclude = set(cfg.data["vault_exclude_dirs"])
    dirs, notes = [], []
    for c in sorted(p.iterdir(), key=lambda c: c.name.lower()):
        if c.name in exclude or c.name.startswith("."):
            continue
        if c.is_dir():
            dirs.append({"name": c.name, "rel": c.relative_to(cfg.vault).as_posix(),
                         "count": sum(1 for _ in c.rglob("*.md"))})
        elif c.suffix.lower() == ".md":
            notes.append(note_info(cfg, c))
    return {"rel": rel, "dirs": dirs, "notes": notes}


def read_note(cfg, rel):
    p = safe_resolve(cfg, rel)
    if p.suffix.lower() != ".md" or not p.is_file():
        raise VaultError("not a Markdown note")
    exclude = set(cfg.data["vault_exclude_dirs"])
    if any(part in exclude for part in p.relative_to(cfg.vault.resolve()).parts):
        raise VaultError("this folder is excluded")
    text, k = redact(p.read_text(encoding="utf-8", errors="replace"))
    return {**note_info(cfg, p), "text": text, "redactions": k}


def find_note(cfg, name):
    """Resolve a [[wikilink]] target to a vault-relative path (first match by file name)."""
    name = name.split("|")[0].split("#")[0].strip()
    if not name:
        return None
    direct = cfg.vault / (name if name.endswith(".md") else name + ".md")
    try:
        if direct.is_file() and safe_resolve(cfg, direct.relative_to(cfg.vault)):
            return direct.relative_to(cfg.vault).as_posix()
    except (VaultError, ValueError):
        pass
    target = Path(name).name.lower()
    target = target if target.endswith(".md") else target + ".md"
    exclude = set(cfg.data["vault_exclude_dirs"])
    for p in cfg.vault.rglob("*.md"):
        if p.name.lower() == target and not any(x in exclude for x in p.relative_to(cfg.vault).parts):
            return p.relative_to(cfg.vault).as_posix()
    return None
