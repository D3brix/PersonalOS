"""End-to-end Windows install and uninstall into a sandbox (install dir, config, vault, data, archive all temporary).
Nothing is added to PATH and no scheduled task is created, because those switches are not passed."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def ps(script, *args):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)


@unittest.skipUnless(sys.platform == "win32", "Windows installer")
class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="personalos-install-"))
        self.install = self.tmp / "Program Folder"
        self.vault = self.tmp / "My Vault"
        self.data = self.tmp / "ssd data"
        self.archive = self.tmp / "hdd" / "archive"
        self.config = self.tmp / "cfg" / "config.json"
        self.path_before = self.user_path()

    def tearDown(self):
        self.assertEqual(self.user_path(), self.path_before, "the test must not change the user PATH")
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def user_path():
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetEnvironmentVariable('Path','User')"],
                           capture_output=True, text=True)
        return r.stdout.strip()

    def do_install(self):
        r = ps(REPO / "installer" / "install.ps1", "-NonInteractive", "-InstallDir", str(self.install),
               "-VaultPath", str(self.vault), "-DataPath", str(self.data), "-ArchivePath", str(self.archive),
               "-ConfigPath", str(self.config), "-Demo")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def shim(self, *args):
        return subprocess.run([str(self.install / "bin" / "personalos.cmd"), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

    def test_install_use_uninstall_keeps_vault(self):
        r = self.do_install()
        self.assertIn("PersonalOS is installed", r.stdout)
        rec = json.loads((self.install / "install.json").read_text(encoding="utf-8-sig"))
        self.assertFalse(rec["path_added"])
        self.assertIsNone(rec["scheduled_task"])
        self.assertTrue((self.vault / "99_System" / "Rules.md").exists())
        out = self.shim("search", "sourdough")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Sourdough_Basics", out.stdout)
        self.assertEqual(self.shim("doctor").returncode, 0)
        notes_before = sorted(p.relative_to(self.vault).as_posix() for p in self.vault.rglob("*.md"))

        # uninstall without confirmation: program gone, every piece of data kept
        u = ps(REPO / "installer" / "uninstall.ps1", "-NonInteractive", "-InstallDir", str(self.install),
               "-RemoveIndex", "-RemoveArchive")
        self.assertEqual(u.returncode, 0, u.stdout + u.stderr)
        self.assertFalse((self.install / "bin").exists())
        self.assertTrue(self.data.exists() and self.archive.exists() and self.config.exists())
        self.assertEqual(notes_before, sorted(p.relative_to(self.vault).as_posix() for p in self.vault.rglob("*.md")))

        # reinstall picks the configuration up again; then uninstall with explicit confirmation
        self.do_install()
        u = ps(REPO / "installer" / "uninstall.ps1", "-NonInteractive", "-InstallDir", str(self.install),
               "-RemoveIndex", "-RemoveArchive", "-ConfirmDelete", "DELETE")
        self.assertEqual(u.returncode, 0, u.stdout + u.stderr)
        self.assertFalse(self.data.exists())
        self.assertFalse(self.archive.exists())
        self.assertFalse(self.config.exists())
        self.assertFalse(self.install.exists())
        self.assertEqual(notes_before, sorted(p.relative_to(self.vault).as_posix() for p in self.vault.rglob("*.md")))

    def test_refuses_non_empty_vault_without_adopt(self):
        self.vault.mkdir(parents=True)
        (self.vault / "mine.md").write_text("mine", encoding="utf-8")
        r = ps(REPO / "installer" / "install.ps1", "-NonInteractive", "-InstallDir", str(self.install),
               "-VaultPath", str(self.vault), "-DataPath", str(self.data), "-ConfigPath", str(self.config))
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual((self.vault / "mine.md").read_text(encoding="utf-8"), "mine")
        self.assertEqual([p.name for p in self.vault.iterdir()], ["mine.md"])
