# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's **Report a vulnerability** button (Security tab →
Advisories) on this repository, not in a public issue. Include the version, your OS, steps to reproduce and the
impact. You should get a reply within 7 days.

Relevant examples: a way for a website to reach the local UI API, reading files outside the vault through the UI or
MCP server, secrets reaching the index unredacted, any code path that modifies or deletes notes, or any network
request made by PersonalOS.

## Supported versions

Only the latest release receives fixes until 1.0.

## Design

See [docs/PRIVACY_SECURITY.md](docs/PRIVACY_SECURITY.md) for the threat model and the guarantees the test suite
enforces.
