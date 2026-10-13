"""Pre-release audit: scans every file that would be published for secrets, personal data and stray artifacts.

    python scripts/release_audit.py [--denylist PATH]

The optional denylist is a private text file (one term per line: your name, usernames, private project names,
local drive paths...). Keep it OUTSIDE the repository; it is never published. Exit code 1 means findings.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from personalos.redact import SECRET_RE  # noqa: E402

TEXT_EXT = {".py", ".md", ".txt", ".json", ".toml", ".ps1", ".cmd", ".js", ".css", ".html", ".svg", ".yml", ".yaml",
            ".cfg", ".ini", ""}
FORBIDDEN_EXT = {".db", ".sqlite", ".jsonl", ".zip", ".pem", ".key", ".p12", ".pfx", ".log"}
USER_PATH = re.compile(r"\b[A-Za-z]:[\\/]{1,2}Users[\\/]{1,2}(?!<|%|\{|you\b|YOU\b|Public\b)[^\\/\s\"'`]+", re.I)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ALLOWED_EMAIL = re.compile(r"@(example\.(com|org|net)|users\.noreply\.github\.com)$", re.I)
SELF = Path(__file__).resolve()


def publishable_files():
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=REPO, capture_output=True,
                             text=True, check=True).stdout
        return [REPO / l for l in out.splitlines() if l.strip()]
    except (OSError, subprocess.CalledProcessError):
        return [p for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts]


def audit(denylist):
    terms = []
    if denylist:
        terms = [t.strip() for t in Path(denylist).read_text(encoding="utf-8").splitlines()
                 if t.strip() and not t.startswith("#")]
    term_re = [(t, re.compile(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])", re.I)) for t in terms]
    findings = []
    files = publishable_files()
    for f in files:
        rel = f.relative_to(REPO).as_posix()
        if f.suffix.lower() in FORBIDDEN_EXT:
            findings.append((rel, 0, f"file type {f.suffix} must not be published"))
            continue
        if f.stat().st_size > 1_000_000:
            findings.append((rel, 0, "file larger than 1 MB"))
        if f.suffix.lower() not in TEXT_EXT:
            findings.append((rel, 0, "unexpected binary/unknown file type; review manually"))
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            if f.resolve() != SELF and "personalos/redact.py" != rel:
                for name, rx in SECRET_RE:
                    if rx.search(line):
                        findings.append((rel, n, f"secret-like string ({name})"))
            m = USER_PATH.search(line)
            if m:
                findings.append((rel, n, f"absolute user path: {m.group(0)}"))
            for em in EMAIL.findall(line):
                if not ALLOWED_EMAIL.search(em):
                    findings.append((rel, n, f"email address: {em}"))
            for t, rx in term_re:
                if rx.search(line):
                    findings.append((rel, n, f"denylisted term: {t}"))
    return files, findings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--denylist", help="private file with personal terms that must not appear (keep it outside the repo)")
    a = ap.parse_args()
    if a.denylist and Path(a.denylist).resolve().is_relative_to(REPO):
        sys.exit("the denylist must live outside the repository")
    files, findings = audit(a.denylist)
    for rel, n, msg in findings:
        print(f"{rel}:{n}: {msg}")
    print(f"\nscanned {len(files)} files; {len(findings)} findings"
          + ("" if a.denylist else " (no denylist given: personal terms were not checked)"))
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
