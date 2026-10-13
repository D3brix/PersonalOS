"""Configuration: where it lives, what it contains, how it is validated.

The config file only holds paths and settings, never note content or credentials. Its location is
PERSONALOS_CONFIG if set, otherwise the per-user config directory of the platform.
"""
import copy
import json
import os
import sys
from pathlib import Path

SCHEMA_VERSION = 1

# Vault folder roles. A user adopting an existing vault can map each role to their own folder names.
DEFAULT_FOLDERS = {
    "inbox": "00_Inbox",
    "daily": "01_Daily",
    "projects": "02_Projects",
    "areas": "03_Areas",
    "knowledge": "04_Knowledge",
    "people": "05_People",
    "skills": "06_Skills",
    "systems": "07_Systems",
    "resources": "08_Resources",
    "archive": "09_Archive",
    "raw": "raw",
    "system": "99_System",
}

DEFAULTS = {
    "schema_version": SCHEMA_VERSION,
    "vault": None,
    "data_dir": None,
    "archive_dir": None,
    "folders": DEFAULT_FOLDERS,
    # First matching rule wins. Globs are relative to the vault, with "{role}" replaced by the folder name.
    # kind: system | note | raw. tier 1 = active memory (searched first), tier 2 = long-term.
    "vault_rules": [
        {"glob": "*README.md", "kind": "note", "tier": 2},
        {"glob": "{system}/*", "kind": "system", "tier": 1},
        {"glob": "AGENTS.md", "kind": "system", "tier": 1},
        {"glob": "{raw}/*", "kind": "raw", "tier": 2},
        {"glob": "{inbox}/*", "kind": "raw", "tier": 1},
        {"glob": "{archive}/*", "kind": "note", "tier": 2},
        {"glob": "{knowledge}/*", "kind": "note", "tier": 1},
        {"glob": "{people}/*", "kind": "note", "tier": 2},
        {"glob": "{resources}/*", "kind": "note", "tier": 2},
        {"glob": "{daily}/*", "kind": "note", "tier": 2},
        {"glob": "*", "kind": "note", "tier": 1},
    ],
    "vault_exclude_dirs": [".obsidian", ".trash", ".git"],
    # Extra read-only folders to index, e.g. old documents on an HDD.
    "extra_sources": [],
    "search": {
        "limit": 5,
        "kind_weight": {"system": 1.5, "note": 1.3, "instruction": 1.2, "inferred": 1.0, "archived": 0.9,
                        "raw": 0.8, "transcript": 0.7},
    },
    "maintenance": {"stale_days": 60, "promote_min_hits": 3},
    "privacy": {"log_queries": True},
    "ui": {"port": 7531},
    "integrations": {
        "claude_code": {"enabled": False, "home": "~/.claude", "index_memory": True, "index_instructions": True,
                        "archive_transcripts": True, "index_transcripts": True},
        "obsidian": {"enabled": False},
        "mcp": {"enabled": False, "allow_capture": False},
    },
}


class ConfigError(Exception):
    pass


def _platform_dir(env_var, fallback):
    base = os.environ.get(env_var)
    return Path(base) if base else Path.home() / fallback


def default_config_dir():
    if sys.platform == "win32":
        return _platform_dir("APPDATA", "AppData/Roaming") / "PersonalOS"
    return _platform_dir("XDG_CONFIG_HOME", ".config") / "personalos"


def default_data_dir():
    if sys.platform == "win32":
        return _platform_dir("LOCALAPPDATA", "AppData/Local") / "PersonalOS" / "data"
    return _platform_dir("XDG_DATA_HOME", ".local/share") / "personalos"


def config_path():
    env = os.environ.get("PERSONALOS_CONFIG")
    return Path(env).expanduser() if env else default_config_dir() / "config.json"


def _merge(base, override):
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def norm(p):
    """Absolute path with forward slashes, user and environment variables expanded."""
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve().as_posix()


class Config:
    def __init__(self, data, path):
        self.data = data
        self.path = Path(path)

    # ---- paths
    @property
    def vault(self):
        return Path(self.data["vault"])

    @property
    def data_dir(self):
        return Path(self.data["data_dir"])

    @property
    def archive_root(self):
        """HDD tier if configured, otherwise an archive folder next to the index (SSD-only mode)."""
        a = self.data.get("archive_dir")
        return Path(a) if a else self.data_dir / "archive"

    @property
    def db_path(self):
        return self.data_dir / "index" / "memory.db"

    @property
    def logs(self):
        return self.data_dir / "logs"

    def folder(self, role):
        return self.vault / self.data["folders"][role]

    def integration(self, name):
        return self.data["integrations"].get(name, {})

    def vault_rules(self):
        f = self.data["folders"]
        return [{**r, "glob": r["glob"].format(**f)} for r in self.data["vault_rules"]]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        if os.name != "nt":
            os.chmod(self.path, 0o600)


def validate(data):
    errors = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}, found {data.get('schema_version')!r}")
    for key in ("vault", "data_dir"):
        if not data.get(key):
            errors.append(f"'{key}' is not set")
    missing = set(DEFAULT_FOLDERS) - set(data.get("folders", {}))
    if missing:
        errors.append(f"folders is missing roles: {', '.join(sorted(missing))}")
    for r in data.get("vault_rules", []):
        if r.get("kind") not in ("system", "note", "raw") or r.get("tier") not in (1, 2):
            errors.append(f"invalid vault rule {r}")
    for s in data.get("extra_sources", []):
        if not s.get("path") or s.get("tier", 2) not in (1, 2):
            errors.append(f"invalid extra source {s}")
    if data.get("vault") and data.get("data_dir"):
        v, d = Path(data["vault"]), Path(data["data_dir"])
        if v == d or v in d.parents:
            errors.append("data_dir must not be inside the vault (the index would index itself)")
    port = data.get("ui", {}).get("port")
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        errors.append("ui.port must be an integer between 1024 and 65535")
    return errors


def new_config(vault, data_dir=None, archive_dir=None):
    data = copy.deepcopy(DEFAULTS)
    data["vault"] = norm(vault)
    data["data_dir"] = norm(data_dir or default_data_dir())
    data["archive_dir"] = norm(archive_dir) if archive_dir else None
    if archive_dir:
        data["extra_sources"] = [{"path": norm(Path(archive_dir) / "long-term"), "kind": "archived", "tier": 2,
                                  "extensions": [".md", ".txt"]}]
    return data


def load(path=None):
    path = Path(path) if path else config_path()
    if not path.exists():
        raise ConfigError(f"no configuration at {path}. Run `personalos init` first.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ConfigError(f"{path} is not valid JSON: {e}") from None
    data = _merge(DEFAULTS, raw)
    errors = validate(data)
    if errors:
        raise ConfigError(f"{path} is invalid:\n  - " + "\n  - ".join(errors))
    return Config(data, path)
