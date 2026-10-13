"""Optional integrations. The core works with none of them enabled.

Each integration module defines NAME, DESCRIPTION, enable(cfg), disable(cfg) and status(cfg), and may define
sources(cfg) (extra files to index) and PARSERS (parser name -> (parse, show)).
"""
from . import claude_code, mcp, obsidian

_ALL = {m.NAME: m for m in (claude_code, obsidian, mcp)}


def all_integrations():
    return list(_ALL.values())


def get(name):
    if name not in _ALL:
        raise KeyError(f"unknown integration '{name}'. Available: {', '.join(_ALL)}")
    return _ALL[name]


def enabled_integrations(cfg):
    return [m for n, m in _ALL.items() if cfg.integration(n).get("enabled")]
