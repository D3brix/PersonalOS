import json
import os
import time
import zipfile

from helpers import Sandbox

from personalos import backup, health, index


class CorruptIndex(Sandbox):
    def test_garbage_index_is_quarantined_and_rebuilt(self):
        self.index()
        db = self.cfg.db_path
        db.write_bytes(b"this is not a sqlite database" * 100)
        self.assertTrue(index.integrity(self.cfg))
        checks, _ = health.checks()
        self.assertIn("FAIL", {c["status"] for c in checks if c["check"] == "Search index"})
        st, _, _ = self.index()
        self.assertTrue(st["recovered_corrupt_index"])
        self.assertGreater(st["added"], 20)
        self.assertEqual(index.integrity(self.cfg), [])
        self.assertTrue(list(db.parent.glob("memory.db.corrupt-*")))  # moved aside, never deleted
        self.assertEqual(self.top_titles("sourdough")[0], "Sourdough_Basics")

    def test_truncated_index_is_detected(self):
        self.index()
        data = self.cfg.db_path.read_bytes()
        self.cfg.db_path.write_bytes(data[: len(data) // 3])
        self.assertTrue(index.integrity(self.cfg))
        st, _, _ = self.index()
        self.assertEqual(index.integrity(self.cfg), [])

    def test_search_recovers_transparently(self):
        self.index()
        self.cfg.db_path.write_bytes(b"\x00" * 4096)
        index.search(self.cfg, "anything")  # must not raise
        self.index()
        self.assertTrue(self.top_titles("sourdough"))

    def test_lock_prevents_concurrent_runs_and_expires(self):
        lock = self.cfg.db_path.parent / "index.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("123")
        with self.assertRaises(index.IndexBusy):
            self.index()
        old = time.time() - 3600
        os.utime(lock, (old, old))
        self.index()
        self.assertFalse(lock.exists())

    def test_unreadable_file_does_not_stop_indexing(self):
        self.index()
        bad = self.vault_dir / "04_Knowledge" / "binary.md"
        bad.write_bytes(b"\xff\xfe\x00garbage\x00" * 50)
        st, _, errors = self.index()
        self.assertEqual(st["errors"], 0)  # undecodable bytes are replaced, not fatal
        self.assertGreaterEqual(st["added"], 1)


class BackupRestore(Sandbox):
    def test_round_trip(self):
        self.index()
        out, n = backup.create(self.cfg, self.tmp / "backups")
        self.assertGreater(n, 20)
        manifest, bad = backup.verify(out)
        self.assertEqual(bad, [])
        target = self.tmp / "restored"
        backup.restore(out, target)
        orig = sorted(p.relative_to(self.vault_dir).as_posix() for p in self.vault_dir.rglob("*.md"))
        rest = sorted(p.relative_to(target / "vault").as_posix() for p in (target / "vault").rglob("*.md"))
        self.assertEqual(orig, rest)
        self.assertEqual((self.vault_dir / "Home.md").read_bytes(), (target / "vault" / "Home.md").read_bytes())
        self.assertIn("vault", json.loads((target / "config.json").read_text(encoding="utf-8")))

    def test_activate_via_cli(self):
        self.index()
        out, _ = backup.create(self.cfg, self.tmp / "backups")
        r = self.cli("restore", str(out), "--to", str(self.tmp / "restored"), "--activate")
        self.assertIn("index rebuilt", r.stdout)
        self.assertTrue(self.reload().vault.as_posix().endswith("restored/vault"))
        self.assertEqual(self.top_titles("sourdough")[0], "Sourdough_Basics")

    def test_refuses_non_empty_target_damaged_zip_and_zip_slip(self):
        out, _ = backup.create(self.cfg, self.tmp / "backups")
        busy = self.tmp / "busy"
        busy.mkdir()
        (busy / "keep.txt").write_text("mine")
        with self.assertRaises(backup.BackupError):
            backup.restore(out, busy)
        self.assertEqual((busy / "keep.txt").read_text(), "mine")

        damaged = self.tmp / "damaged.zip"
        with zipfile.ZipFile(out) as src, zipfile.ZipFile(damaged, "w") as dst:
            for info in src.infolist():
                data = src.read(info)
                dst.writestr(info, b"changed" if info.filename == "vault/Home.md" else data)
        with self.assertRaises(backup.BackupError):
            backup.restore(damaged, self.tmp / "t1")

        evil = self.tmp / "evil.zip"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("../escaped.txt", "x")
            z.writestr("backup-manifest.json", json.dumps({"files": {}, "created": "x"}))
        with self.assertRaises(backup.BackupError):
            backup.restore(evil, self.tmp / "t2")
        self.assertFalse((self.tmp / "escaped.txt").exists())

    def test_backup_inside_vault_refused(self):
        with self.assertRaises(backup.BackupError):
            backup.create(self.cfg, self.vault_dir / "backups")
