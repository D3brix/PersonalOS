"""Secret detection and redaction. Applied before text reaches the index and whenever an original is shown."""
import re

SECRET_PATTERNS = [
    ("private_key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)"),
    ("anthropic_key", r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    ("openai_key", r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}"),
    ("github_token", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}"),
    ("aws_key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("google_key", r"\bAIza[0-9A-Za-z_\-]{35}"),
    ("slack_token", r"\bxox[abposr]-[A-Za-z0-9\-]{10,}"),
    ("stripe_key", r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}"),
    ("discord_token", r"\b[MNO][A-Za-z\d_\-]{23,27}\.[A-Za-z\d_\-]{6}\.[A-Za-z\d_\-]{27,40}\b"),
    ("jwt", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    ("bearer", r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{20,}=*"),
    ("url_credentials", r"(?i)\b[a-z][a-z0-9+.\-]*://[^/\s:@\"']+:[^/\s@\"']+@"),
    ("long_hex", r"\b[a-fA-F0-9]{40,}\b"),
]
SECRET_RE = [(n, re.compile(p)) for n, p in SECRET_PATTERNS]
ASSIGN_RE = re.compile(
    r"(?i)\b([A-Z0-9_\-]*(?:passw(?:or)?d|passwd|secret|token|api[_\-]?key|access[_\-]?key|client[_\-]?secret|auth[_\-]?key)[A-Z0-9_\-]*)"
    r"(\s*[:=]\s*[\"']?)([^\s\"'`,;<>]{8,})"
)
# Files that are never indexed, whatever folder they are in.
DENY_NAME = re.compile(r"(^\.env|\.env$|credential|password|secret|api[_\-]?keys?|\.pem$|\.key$|\.p12$|\.pfx$)", re.I)


def redact(text):
    """Return (redacted_text, number_of_redactions)."""
    n = 0
    for name, rx in SECRET_RE:
        text, k = rx.subn(f"[REDACTED:{name}]", text)
        n += k
    text, k = ASSIGN_RE.subn(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED:assignment]", text)
    return text, n + k


def contains_secret(text):
    return redact(text)[1] > 0


def is_denied_file(name):
    return bool(DENY_NAME.search(name))
