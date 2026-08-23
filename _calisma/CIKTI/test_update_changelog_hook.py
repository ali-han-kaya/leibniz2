#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_update_changelog_hook.py — update_changelog_hook.sh birim kapısı.

Hook'u izole bir sandbox git repo'sunda koşar: hook'un bir KOPYASI sandbox'a
kopyalanır (SCRIPT_DIR sandbox'a düşer → README/PUBLISH yolları sandbox içinde
kalır) ve yanına bir MOCK gen_changelog.py konur (gerçek gen_changelog'a,
git log'a veya canlı repo'ya bağımlılık yok).

Mock, ortam değişkenleriyle yönlendirilir:
  MOCK_GC_CHECK_EXIT     --check exit kodu (0 = drift yok, 1 = drift var)
  MOCK_GC_UPDATE_EXIT    --update exit kodu (0 = başarı, 1 = hata)
  MOCK_GC_UPDATE_TOUCH   "1" ise --update README/PUBLISH'a satır ekler
                         (gerçek tablo güncellemesini simüle → hook git add
                         tetiklenir)

Kapsanan dallar:
  drift yok        → --check exit 0 → hook dokunmaz, exit 0
  drift var+stage  → --check exit 1 → --update başarılı + tablolar değişti →
                     README/PUBLISH stage edilir, ℹ️ mesajı, exit 0
  gen_changelog hata → --update exit 1 → "HATA: ..." stderr + exit 1 (bloke)

stdlib unittest — ek bağımlılık yok.
"""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
REAL_HOOK = CIKTI / "update_changelog_hook.sh"

MOCK_GEN_CHANGELOG = """#!/usr/bin/env python3
# Mock gen_changelog.py — gerçek git log/table mantığı yerine env ile yönlendirilir.
import os
import pathlib
import sys

mode = sys.argv[1] if len(sys.argv) > 1 else ""
if mode == "--check":
    sys.exit(int(os.environ.get("MOCK_GC_CHECK_EXIT", "0")))
if mode == "--update":
    if os.environ.get("MOCK_GC_UPDATE_TOUCH", "0") == "1":
        line = "| 2026-08-23 | fix | (test) mock update | `mockhash` |\\n"
        for rel in ("README.md", "docs/PUBLISH_SCENARIO.md"):
            with open(pathlib.Path(rel), "a", encoding="utf-8") as f:
                f.write(line)
    sys.exit(int(os.environ.get("MOCK_GC_UPDATE_EXIT", "0")))
sys.exit(0)
"""

BASE_TABLE = (
    "# test repo\\n\\n"
    "## Değişiklik Geçmişi\\n\\n"
    "| Tarih | Kategori | Değişiklik | Commit |\\n"
    "|---|---|---|---|\\n"
    "| 2026-08-23 | fix | (test) base | `aaaa1111` |\\n"
)


class UpdateChangelogHookTest(unittest.TestCase):
    """Her testte taze sandbox git repo + hook kopyası + mock gen_changelog."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="changelog_hook_test_"))
        cikti = self.tmp / "_calisma" / "CIKTI"
        cikti.mkdir(parents=True)
        shutil.copy(REAL_HOOK, cikti / "update_changelog_hook.sh")
        (cikti / "gen_changelog.py").write_text(MOCK_GEN_CHANGELOG, encoding="utf-8")
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "test")
        (self.tmp / "README.md").write_text(BASE_TABLE, encoding="utf-8")
        (self.tmp / "docs").mkdir()
        (self.tmp / "docs" / "PUBLISH_SCENARIO.md").write_text(
            BASE_TABLE, encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "test: base")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git(self, *args):
        subprocess.run(["git", *args], cwd=str(self.tmp), check=True,
                       capture_output=True, text=True)

    def _run_hook(self, env=None):
        full_env = dict(os.environ)
        if env:
            full_env.update(env)
        return subprocess.run(
            ["bash", str(self.tmp / "_calisma" / "CIKTI" / "update_changelog_hook.sh")],
            cwd=str(self.tmp), env=full_env, capture_output=True, text=True)

    def _porcelain(self):
        return subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(self.tmp),
            capture_output=True, text=True, check=True).stdout

    def test_no_drift_exits_0_without_touching(self):
        # --check exit 0 → hook dokunmadan exit 0; ℹ️ mesajı yok, stage yok.
        r = self._run_hook({"MOCK_GC_CHECK_EXIT": "0"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("changelog tabloları", r.stdout)
        self.assertEqual(self._porcelain(), "")

    def test_drift_updates_and_stages_both_files(self):
        # --check exit 1 (drift) → --update başarılı + tabloları değiştirdi →
        # README + PUBLISH stage edilir, ℹ️ mesajı basılır, exit 0.
        r = self._run_hook({
            "MOCK_GC_CHECK_EXIT": "1",
            "MOCK_GC_UPDATE_EXIT": "0",
            "MOCK_GC_UPDATE_TOUCH": "1",
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("changelog tabloları git log'a göre güncellendi", r.stdout)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"], cwd=str(self.tmp),
            capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertIn("README.md", staged)
        self.assertIn("docs/PUBLISH_SCENARIO.md", staged)
        # Mock güncellemesi gerçekten dosyalara işlendi.
        self.assertIn("mockhash", (self.tmp / "README.md").read_text(encoding="utf-8"))
        self.assertIn(
            "mockhash",
            (self.tmp / "docs" / "PUBLISH_SCENARIO.md").read_text(encoding="utf-8"))

    def test_drift_without_changes_stages_nothing(self):
        # Drift var ama --update hiçbir dosyayı değiştirmedi → stage yok,
        # ℹ️ mesajı yok, yine exit 0.
        r = self._run_hook({
            "MOCK_GC_CHECK_EXIT": "1",
            "MOCK_GC_UPDATE_EXIT": "0",
            "MOCK_GC_UPDATE_TOUCH": "0",
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("changelog tabloları", r.stdout)
        self.assertEqual(self._porcelain(), "")

    def test_update_failure_blocks_with_hata(self):
        # --check exit 1 (drift) → --update exit 1 → "HATA: ..." stderr +
        # exit 1 (fail-closed — commit bloke).
        r = self._run_hook({
            "MOCK_GC_CHECK_EXIT": "1",
            "MOCK_GC_UPDATE_EXIT": "1",
        })
        self.assertEqual(r.returncode, 1)
        self.assertIn("HATA: gen_changelog --update başarısız", r.stderr)
        self.assertEqual(self._porcelain(), "")


if __name__ == "__main__":
    unittest.main()
