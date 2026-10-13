# Privacy and security

PersonalOS holds the most personal data you have. Privacy is a design constraint, not a setting.

## Guarantees

| Guarantee | How it is enforced | Verified by |
|---|---|---|
| No network requests, no telemetry, no update checks | The package imports no network client (no `urllib.request`, `http.client`, `socket`, `requests`...). | `tests/test_privacy.py` scans every module's imports |
| No cloud account | Nothing to sign in to. | — |
| UI reachable only from this computer | Server bound to `127.0.0.1` (hard-coded). | `test_privacy`, `test_web` |
| No external assets in the UI | No CDNs or web fonts; strict Content-Security-Policy `default-src 'self'`. | `test_privacy`, `test_web` |
| Notes are never modified | Only new inbox files are created, with exclusive-create. | `test_cli` (byte-for-byte vault comparison after every command) |
| Secrets stay out of the index | Credential-like files are skipped; secret-like strings are redacted before indexing and when shown. | `test_privacy` |
| Secrets are not captured | Capture refuses text that looks like a key, token or password. | `test_privacy`, `test_web` |
| Data stays where you put it | All locations come from your config; nothing is hard-coded. | `test_privacy` (no user paths in the package), `test_cli` (custom paths, spaces, non-ASCII) |
| Uninstall keeps your data | The vault is never deleted; index and archive deletion need typed confirmation. | `test_installer` |

## What PersonalOS stores, and where

| Data | Location | Contains |
|---|---|---|
| Config | `%APPDATA%\PersonalOS\config.json` | Paths and settings. No note content, no credentials. |
| Index | `<data>\index\memory.db` | Searchable chunks of your notes (with secrets redacted). Delete it at any time; `personalos index --rebuild` recreates it. |
| Operations log | `<data>\logs\operations.jsonl` | What indexing, archiving and maintenance did, and file paths. |
| Usage log | `<data>\logs\usage.jsonl` | Search words and the files they returned, used for "promote this note" suggestions. Turn off storing the search words with `personalos config set privacy.log_queries false` or in Settings. |
| Reports | `<data>\logs\reports\` | Maintenance reports. |
| Archive | `<archive>\claude-code\` | Copies of Claude Code transcripts, only if you enable that integration. |

## Local web interface

Being on localhost is not authentication, because any website in your browser can try to reach `127.0.0.1`. So the
UI also has:

- **A per-launch session key.** `personalos ui` prints a link containing a random 256-bit key in the URL fragment,
  which is never sent in requests or logged. The page sends it as the `X-PersonalOS-Token` header; every API call
  without it is refused. Other websites cannot read it, and cannot attach custom headers cross-origin without a
  CORS preflight, which the server never approves. This blocks CSRF.
- **A Host header allow-list** (`127.0.0.1:<port>`, `localhost:<port>`), which defeats DNS rebinding.
- **Origin and `Sec-Fetch-Site` checks**, JSON-only bodies and a 64 KB request cap on every write.
- **Server-side confirmation.** Changing settings or integrations and rebuilding the index require `confirm: true`
  in the request; the dialog in the page is not the security boundary.
- **Settings allow-list.** The UI can change only search and maintenance numbers and query logging. Storage paths
  can only be changed from the command line.
- **Path-traversal guards** for static files and vault notes; errors never reveal internals.
- **Headers:** CSP, `nosniff`, `X-Frame-Options: DENY`, `no-referrer`, `no-store`.

**Accepted limit:** other programs running as your Windows user can read your files anyway, and could read the session
key from the terminal output. PersonalOS does not defend against malware already running as you.

## AI integrations

- The **MCP server** talks over stdin/stdout only (no port). It is off until you enable it, read-only by default
  (search, read, list inbox), and `capture_note` exists only if you set `integrations.mcp.allow_capture`.
- The **Claude Code skill** tells the assistant to cite sources, treat transcripts and AI memory as unverified, keep
  redaction markers, and never write to the vault without asking.
- Whatever an assistant reads through these tools is sent to that assistant's model provider, under that provider's
  terms. Local-model MCP clients keep it on your machine.

## File permissions

- Folders under your user profile (the defaults) are already private to your Windows account.
- For index or archive folders elsewhere (for example `D:\`), the installer offers to remove inherited permissions
  and grant access only to your account, SYSTEM and Administrators.
- On Linux and macOS, the config file is created `0600` and data folders `0700`.

## Redaction limits

Secret detection is pattern-based: API keys from common providers, GitHub/Slack/Discord/AWS/Google/Stripe tokens,
JWTs, bearer tokens, private keys, passwords in URLs, `password=`/`token:` assignments, and long hex strings. Unusual
formats can slip through. Keep secrets in a password manager, not in notes. `personalos maintain` lists notes that
contain secret-like strings.

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md).
