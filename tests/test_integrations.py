import json
import os
import subprocess
import sys

from helpers import REPO, Sandbox, fake_transcript

from personalos import archive, index
from personalos.integrations import claude_code, mcp, obsidian


def transcript_lines():
    return [
        {"type": "ai-title", "aiTitle": "Planning the greenhouse"},
        {"type": "user", "timestamp": "2026-01-05T10:00:00Z", "message": {"content": "Should the greenhouse face south?"}},
        {"type": "assistant", "timestamp": "2026-01-05T10:00:05Z", "message": {"content": [
            {"type": "text", "text": "Yes, a south-facing greenhouse gets the most winter light."},
            {"type": "tool_use", "name": "Bash", "input": {"command": "echo SECRET_TOOL_OUTPUT"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "SECRET_TOOL_OUTPUT"}]}},
        "not a dict",
    ]


class ClaudeCode(Sandbox):
    archive = True

    def setUp(self):
        super().setUp()
        h = self.claude_home
        (h / "projects" / "garden" / "memory").mkdir(parents=True)
        (h / "projects" / "garden" / "memory" / "glazing.md").write_text(
            "---\nname: glazing\ndescription: polycarbonate glazing chosen\n---\nPolycarbonate glazing.\n", encoding="utf-8")
        (h / "CLAUDE.md").write_text("Prefer short answers.\n", encoding="utf-8")
        fake_transcript(h / "projects" / "garden" / "session1.jsonl", transcript_lines())

    def test_enable_archive_index_search_disable(self):
        msgs = claude_code.enable(self.cfg)
        self.assertTrue(any("skill installed" in m for m in msgs))
        skill = claude_code.skill_path(self.cfg)
        self.assertIn(claude_code.MARKER, skill.read_text(encoding="utf-8"))

        stats, mism = claude_code.run_archive(self.cfg)
        self.assertEqual((stats["new"], mism), (2, []))
        adir = claude_code.archive_dir(self.cfg)
        self.assertTrue(str(adir).startswith(str(self.archive_dir)))  # lands on the archive drive
        self.index()

        hits = index.search(self.cfg, "greenhouse south", all_tiers=True)
        t = [h for h in hits["tier2"] if h["kind"] == "transcript"]
        self.assertTrue(t)
        self.assertIn("Planning the greenhouse", t[0]["title"])
        self.assertEqual(self.top_titles("SECRET_TOOL_OUTPUT", all_tiers=True), [])  # tool output never indexed
        inferred = index.search(self.cfg, "polycarbonate glazing", all_tiers=True)
        self.assertEqual(inferred["tier1"][0]["label"], "INFERRED")
        shown = index.show(self.cfg, t[0]["path"], t[0]["loc"])
        self.assertIn("south-facing", shown["text"])

        # second archive run copies nothing; verify passes; corruption and loss are detected
        stats, _ = claude_code.run_archive(self.cfg)
        self.assertEqual(stats["new"] + stats["updated"], 0)
        self.assertEqual(archive.verify(adir)["ok"], 2)
        f = adir / "files" / "projects" / "garden" / "session1.jsonl"
        f.write_text("tampered", encoding="utf-8")
        (adir / "files" / "projects" / "garden" / "memory" / "glazing.md").unlink()
        r = archive.verify(adir)
        self.assertEqual((len(r["corrupted"]), len(r["missing"])), (1, 1))

        claude_code.disable(self.cfg)
        self.assertFalse(skill.exists())
        self.assertTrue(adir.exists())  # data is kept
        st, _, _ = self.index()
        self.assertGreater(st["removed"], 0)

    def test_shrunk_source_is_preserved(self):
        claude_code.enable(self.cfg)
        claude_code.run_archive(self.cfg)
        src = self.claude_home / "projects" / "garden" / "session1.jsonl"
        src.write_text("{}\n", encoding="utf-8")
        os.utime(src, (src.stat().st_mtime + 10,) * 2)
        stats, _ = claude_code.run_archive(self.cfg)
        self.assertEqual(stats["preserved"], 1)
        kept = list((claude_code.archive_dir(self.cfg) / "superseded").rglob("session1.jsonl"))
        self.assertIn("greenhouse", kept[0].read_text(encoding="utf-8"))

    def test_foreign_skill_is_never_overwritten(self):
        p = claude_code.skill_path(self.cfg)
        p.parent.mkdir(parents=True)
        p.write_text("someone else's skill", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            claude_code.enable(self.cfg)
        claude_code.disable(self.cfg)
        self.assertEqual(p.read_text(encoding="utf-8"), "someone else's skill")

    def test_missing_claude_home(self):
        self.cfg.data["integrations"]["claude_code"]["home"] = str(self.tmp / "nope")
        with self.assertRaises(RuntimeError):
            claude_code.enable(self.cfg)


class Obsidian(Sandbox):
    def test_creates_settings_only_when_absent(self):
        obsidian.enable(self.cfg)
        app = json.loads((self.vault_dir / ".obsidian" / "app.json").read_text(encoding="utf-8"))
        self.assertEqual(app["newFileFolderPath"], "00_Inbox")
        (self.vault_dir / ".obsidian" / "app.json").write_text("{}", encoding="utf-8")
        obsidian.enable(self.cfg)
        self.assertEqual((self.vault_dir / ".obsidian" / "app.json").read_text(encoding="utf-8"), "{}")
        self.assertTrue(obsidian.uri(self.cfg).startswith("obsidian://open?path="))
        self.index()
        con, _ = index.open_db(self.cfg)
        self.assertEqual(con.execute("select count(*) from files where path like '%.obsidian%'").fetchone()[0], 0)
        con.close()


class Mcp(Sandbox):
    def rpc(self, msgs):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO)
        payload = "".join(json.dumps(m) + "\n" for m in msgs)
        r = subprocess.run([sys.executable, "-X", "utf8", "-m", "personalos", "mcp"], input=payload,
                           capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
        return r, [json.loads(l) for l in r.stdout.splitlines() if l.strip()]

    def test_refuses_when_disabled(self):
        r, _ = self.rpc([])
        self.assertNotEqual(r.returncode, 0)

    def test_protocol_and_tools(self):
        self.index()
        mcp.enable(self.cfg)
        r, out = self.rpc([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search_memory", "arguments": {"query": "sourdough"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "capture_note", "arguments": {"text": "x"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "nope"},
        ])
        self.assertEqual(r.returncode, 0, r.stderr)
        by_id = {m["id"]: m for m in out}
        self.assertEqual(len(out), 5)  # the notification gets no response
        self.assertEqual(by_id[1]["result"]["protocolVersion"], "2025-06-18")
        names = [t["name"] for t in by_id[2]["result"]["tools"]]
        self.assertNotIn("capture_note", names)  # read-only by default
        self.assertIn("Sourdough_Basics", by_id[3]["result"]["content"][0]["text"])
        self.assertTrue(by_id[4]["result"]["isError"])
        self.assertEqual(by_id[5]["error"]["code"], -32601)

    def test_capture_when_allowed(self):
        mcp.enable(self.cfg)
        self.cfg.data["integrations"]["mcp"]["allow_capture"] = True
        self.cfg.save()
        _, out = self.rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": "capture_note", "arguments": {"text": "from an assistant"}}}])
        self.assertFalse(out[0]["result"]["isError"])
        self.assertEqual(len(list((self.vault_dir / "00_Inbox").glob("*from-an-assistant*.md"))), 1)
