import json
import os
import shutil

from helpers import Sandbox

from personalos import config


class FreshInstall(Sandbox):
    """First-time setup through the CLI, on a starter vault, an existing vault and two storage layouts."""

    def fresh(self):
        os.remove(config.config_path())
        shutil.rmtree(self.vault_dir)

    def test_init_starter_ssd_only(self):
        self.fresh()
        r = self.cli("init", "--vault", str(self.vault_dir), "--data", str(self.data_dir))
        self.assertIn("SSD-only mode", r.stdout)
        self.assertTrue((self.vault_dir / "99_System" / "Rules.md").exists())
        self.assertFalse(any(self.vault_dir.rglob("Crop_Rotation.md")))  # no demo data in a real vault
        doc = self.cli("doctor")
        self.assertIn("0 failed", doc.stdout)

    def test_init_with_archive_drive(self):
        self.fresh()
        hdd = self.tmp / "D drive" / "PersonalOS Archive"
        self.cli("init", "--vault", str(self.vault_dir), "--data", str(self.data_dir), "--archive", str(hdd), "--demo")
        cfg = self.reload()
        self.assertEqual(cfg.archive_root.resolve(), hdd.resolve())
        (hdd / "long-term" / "old.md").write_text("# Old\nTax return checklist from 2019.\n", encoding="utf-8")
        self.cli("index")
        out = json.loads(self.cli("search", "tax", "return", "--json").stdout)
        self.assertEqual((out["tier1"] + out["tier2"])[0]["label"], "ARCHIVED DOC")

    def test_init_refuses_non_empty_and_adopts_without_changes(self):
        self.fresh()
        existing = self.tmp / "My Obsidian"
        existing.mkdir()
        (existing / "note.md").write_text("# Mine\nexisting content\n", encoding="utf-8")
        before = {p: p.read_bytes() for p in existing.rglob("*")}
        r = self.cli("init", "--vault", str(existing), "--data", str(self.data_dir), check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not empty", r.stderr)
        self.cli("init", "--vault", str(existing), "--data", str(self.data_dir), "--adopt")
        self.assertEqual(before, {p: p.read_bytes() for p in existing.rglob("*")})
        self.assertIn("note.md", self.cli("search", "existing", "content").stdout)

    def test_init_refuses_to_replace_config(self):
        r = self.cli("init", "--vault", str(self.tmp / "other"), check=False)
        self.assertIn("already configured", r.stderr)

    def test_data_inside_vault_rejected(self):
        self.fresh()
        r = self.cli("init", "--vault", str(self.vault_dir), "--data", str(self.vault_dir / "data"), check=False)
        self.assertNotEqual(r.returncode, 0)

    def test_missing_config_message(self):
        os.remove(config.config_path())
        r = self.cli("search", "x", check=False)
        self.assertIn("personalos init", r.stderr)


class EverydayCommands(Sandbox):
    def setUp(self):
        super().setUp()
        self.index()

    def test_capture_inbox_projects_goals(self):
        self.cli("capture", "Ask", "Priya", "about", "hill", "repeats", "--title", "Hill repeats")
        self.assertIn("Hill repeats", self.cli("inbox").stdout)
        self.assertIn("Hill repeats", self.cli("search", "hill", "repeats").stdout)
        self.cli("capture", input="piped text from another program")
        self.assertIn("piped text", self.cli("search", "piped").stdout)
        p = self.cli("projects").stdout
        self.assertLess(p.index("ACTIVE"), p.index("DONE"))
        self.assertIn("Riverside", self.cli("goals").stdout)

    def test_config_set_validates(self):
        self.cli("config", "set", "search.limit", "7")
        self.assertEqual(self.reload().data["search"]["limit"], 7)
        self.assertNotEqual(self.cli("config", "set", "ui.port", "80", check=False).returncode, 0)
        self.assertNotEqual(self.cli("config", "set", "no.such", "1", check=False).returncode, 0)

    def test_integrations_cli(self):
        out = self.cli("integrations", "list").stdout
        for name in ("claude_code", "obsidian", "mcp"):
            self.assertIn(name, out)
        r = self.cli("integrations", "enable", "claude_code", check=False)
        self.assertIn("not found", r.stderr)  # no fake Claude home was created in this test

    def test_maintain_report_and_stats(self):
        r = self.cli("maintain", "--quiet")
        self.assertIn("report saved", r.stdout)
        self.assertIn("note", self.cli("stats").stdout)
        self.assertIn("Active context", self.cli("active").stdout)

    def test_vault_files_are_never_modified_by_any_command(self):
        before = {p: p.read_bytes() for p in self.vault_dir.rglob("*") if p.is_file()}
        for args in (["index"], ["index", "--rebuild"], ["maintain"], ["search", "garden"], ["doctor"],
                     ["projects"], ["inbox"], ["stats"], ["backup", "--to", str(self.tmp / "bk")]):
            self.cli(*args)
        after = {p: p.read_bytes() for p in self.vault_dir.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


class ExampleConfigs(Sandbox):
    def test_examples_load_and_validate(self):
        from helpers import REPO
        for name in ("config.single-drive.json", "config.ssd-hdd.json"):
            raw = json.loads((REPO / "examples" / name).read_text(encoding="utf-8"))
            raw["vault"], raw["data_dir"] = str(self.vault_dir), str(self.data_dir)
            if raw.get("archive_dir"):
                raw["archive_dir"] = str(self.tmp / "hdd")
            raw.get("integrations", {}).get("claude_code", {}).update(home=str(self.claude_home))
            config.config_path().write_text(json.dumps(raw), encoding="utf-8")
            cfg = self.reload()
            self.assertEqual(cfg.data["schema_version"], 1)
            self.assertIn(cfg.data["search"]["kind_weight"]["system"], (1.5,))  # defaults merged in
