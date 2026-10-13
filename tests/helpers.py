"""Test sandbox. Every test runs against temporary folders only: the config file, APPDATA, LOCALAPPDATA, the
vault, the data folder, the archive and the fake Claude Code home all live under one temp directory, and
`assert_sandboxed` fails the test if any configured path points elsewhere."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from personalos import config, index, vault  # noqa: E402


def fake_transcript(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


class Sandbox(unittest.TestCase):
    demo = True
    archive = False

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="personalos-test-"))
        self._env = os.environ.copy()
        os.environ["PERSONALOS_CONFIG"] = str(self.tmp / "config" / "config.json")
        os.environ["APPDATA"] = str(self.tmp / "appdata")
        os.environ["LOCALAPPDATA"] = str(self.tmp / "localappdata")
        os.environ.pop("PERSONALOS_LAUNCHER", None)
        self.vault_dir = self.tmp / "Vault With Spaces ü"
        self.data_dir = self.tmp / "data"
        self.archive_dir = self.tmp / "hdd" / "archive" if self.archive else None
        self.claude_home = self.tmp / "fake-claude"
        data = config.new_config(self.vault_dir, self.data_dir, self.archive_dir)
        data["integrations"]["claude_code"]["home"] = str(self.claude_home)
        vault.create_vault(self.vault_dir, "demo" if self.demo else "default")
        self.cfg = config.Config(data, config.config_path())
        self.cfg.save()
        self.assert_sandboxed()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def reload(self):
        self.cfg = config.load()
        return self.cfg

    def assert_sandboxed(self):
        root = self.tmp.resolve()
        paths = [self.cfg.path, self.cfg.vault, self.cfg.data_dir, self.cfg.archive_root,
                 Path(self.cfg.integration("claude_code")["home"])]
        for p in paths:
            p = Path(p).resolve()
            self.assertTrue(p == root or root in p.parents, f"{p} escapes the test sandbox")

    def index(self, rebuild=False):
        return index.run_index(self.cfg, rebuild)

    def cli(self, *args, input=None, check=True):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO)
        r = subprocess.run([sys.executable, "-X", "utf8", "-m", "personalos", *args], capture_output=True, text=True,
                           encoding="utf-8", input=input, env=env, cwd=str(self.tmp))
        if check and r.returncode != 0:
            self.fail(f"personalos {' '.join(args)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        return r

    def top_titles(self, query, n=3, **kw):
        res = index.search(self.cfg, query, n, **kw)
        return [h["title"] for h in res["tier1"] + res["tier2"]]
