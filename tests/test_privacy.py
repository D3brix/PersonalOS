import ast
import re
from pathlib import Path

from helpers import REPO, Sandbox

from personalos import index, vault
from personalos.redact import contains_secret, is_denied_file, redact

PKG = REPO / "personalos"
FAKE_KEY = "sk-ant-" + "api03-" + "A" * 30  # assembled so the literal never sits in the source


class Redaction(Sandbox):
    def test_patterns(self):
        samples = [FAKE_KEY, "ghp_" + "a" * 36, "AKIA" + "B" * 16, "xoxb-" + "1" * 20,
                   "password = hunter2hunter2", "https://user:" + "pa55word@example.com/x",
                   "-----BEGIN RSA " + "PRIVATE KEY-----\nabc\n-----END RSA " + "PRIVATE KEY-----", "Bearer " + "x" * 30]
        for s in samples:
            out, n = redact(f"before {s} after")
            self.assertGreater(n, 0, s)
            self.assertIn("[REDACTED:", out)
        self.assertFalse(contains_secret("The garden planner stores data locally in SQLite."))

    def test_secrets_never_reach_the_index_and_secret_files_are_skipped(self):
        note = self.vault_dir / "00_Inbox" / "server.md"
        note.write_text(f"# Server\n\nThe token is {FAKE_KEY} for the build box.\n", encoding="utf-8")
        (self.vault_dir / "08_Resources" / "passwords.md").write_text("# all my passwords\nbank: x\n", encoding="utf-8")
        st, _, _ = self.index()
        self.assertEqual(st["skipped_secret_files"], 1)
        self.assertGreaterEqual(st["redactions"], 1)
        con, _ = index.open_db(self.cfg)
        body = " ".join(r[0] for r in con.execute("select body from fts"))
        con.close()
        self.assertNotIn(FAKE_KEY, body)
        res = index.search(self.cfg, "bank passwords", all_tiers=True)
        self.assertFalse([h for h in res["tier1"] + res["tier2"] if h["path"].endswith("passwords.md")])
        self.assertNotIn(FAKE_KEY, index.show(self.cfg, str(note))["text"])
        self.assertTrue(is_denied_file(".env.local"))

    def test_capture_refuses_secrets_and_never_overwrites(self):
        with self.assertRaises(vault.VaultError):
            vault.capture(self.cfg, f"key {FAKE_KEY}")
        a = vault.capture(self.cfg, "same title", "Same")
        b = vault.capture(self.cfg, "same title", "Same")
        self.assertNotEqual(a, b)
        self.assertTrue(a.exists() and b.exists())

    def test_vault_path_traversal_is_refused(self):
        for rel in ["../config/config.json", "..\\..\\x.md", str(self.cfg.path)]:
            with self.assertRaises(vault.VaultError):
                vault.read_note(self.cfg, rel)

    def test_query_logging_can_be_disabled(self):
        self.index()
        self.cfg.data["privacy"]["log_queries"] = False
        self.cfg.save()
        self.cli("search", "sourdough")
        log = (self.data_dir / "logs" / "usage.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("sourdough", log.split('"hits"')[0])


class StaticPrivacyAudit(Sandbox):
    """Source-level guarantees: no network clients, no telemetry, no hard-coded personal paths."""
    NETWORK_MODULES = {"urllib.request", "http.client", "socket", "requests", "httpx", "aiohttp", "smtplib",
                       "ftplib", "telnetlib", "xmlrpc", "ssl", "urllib3"}

    def test_no_network_client_imports(self):
        for f in PKG.rglob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
                for n in names:
                    self.assertFalse(any(n == m or n.startswith(m + ".") for m in self.NETWORK_MODULES),
                                     f"{f.name} imports {n}")

    def test_server_binds_loopback_only(self):
        src = (PKG / "web" / "server.py").read_text(encoding="utf-8")
        self.assertIn('HOST = "127.0.0.1"', src)
        self.assertNotIn("0.0.0.0", src)

    def test_no_external_urls_in_ui(self):
        for f in (PKG / "web" / "static").iterdir():
            text = f.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"(src|href)=[\"']https?://", text), f.name)
            self.assertNotIn("fetch(\"http", text)

    def test_no_hardcoded_user_paths(self):
        rx = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+(?!<|%|\{)", re.I)
        for f in list(PKG.rglob("*")) + list((REPO / "installer").rglob("*")):
            if f.is_file() and f.suffix in (".py", ".md", ".js", ".html", ".ps1", ".json", ".css"):
                self.assertIsNone(rx.search(f.read_text(encoding="utf-8")), f"hard-coded user path in {f}")
