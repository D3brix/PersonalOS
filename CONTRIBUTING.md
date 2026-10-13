# Contributing

Thanks for helping. PersonalOS holds people's most private data, so a few rules are firm.

## Non-negotiables

1. **No network code in the core or integrations.** No telemetry, update checks, analytics, CDNs or web fonts.
   `tests/test_privacy.py` enforces this.
2. **Never modify existing notes.** New features may create new files; moving or editing notes needs an explicit,
   reversible design (an undo log) and discussion first.
3. **No new runtime dependencies** without discussion. The standard library keeps PersonalOS auditable and
   installable offline.
4. **No real personal data** in code, tests, docs or issues. Use the fictional demo persona (Alex Morgan) or
   invent new fictional data.
5. **Tests never touch a real vault.** Use `tests/helpers.Sandbox`, which isolates config, APPDATA, LOCALAPPDATA,
   vault, data, archive and the Claude Code home in a temporary folder.

## Development

```
python -m personalos --help          # run from source
cd tests
python -m unittest                   # the whole suite (the installer test runs on Windows only)
python -m unittest test_search -v    # one module
```

Style: plain Python 3.10+, standard library, small modules, comments only where the reason is not obvious. The UI
is vanilla JavaScript and CSS with no build step.

## Pull requests

- One topic per PR, with tests for new behaviour and for each bug fix.
- Update the docs and `CHANGELOG.md` when behaviour changes.
- Run `python scripts/release_audit.py` before opening a PR; it must report no findings.
- Security issues: do not open a public issue; see [SECURITY.md](SECURITY.md).
