#!/usr/bin/env python3
"""test_check_unstaged_delta.py — unstaged-delta kapısının sözleşme testleri.

Seam: kapının CLI'si (stdout/stderr + exit kodu) ve GERÇEK pre-commit
davranışı. Testler izole scratch repo'larda koşar (kendi `PRE_COMMIT_HOME`'i,
kendi `.git`'i, global/system git config'i nötrlenmiş) — geliştiricinin
kirli ağacı testi etkilemez, test de gerçek cache'i kirletmez
(check-precommit-orphans kapısı bu yüzden rahat kalır).

Neden gerçek commit testi şart: kapı, pre-commit'in unstaged deltayı
STASH'lemesi yüzünden `git diff` ile göremeyeceği durumu ATA-pid'li stash
patch'i üzerinden yakalar. pre-commit güncellemesi patch adlandırmasını
değiştirirse kapı sessizce PASS verirdi; `test_mixed_tree_commit_...`
gerçek bir `git commit` koştuğu için o sessiz çürümeyi YAKALAR (kırmızıya
düşer) — kapının kendi bekçisi.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
SCRIPT = HERE / "check_unstaged_delta.py"
VENV_PC = REPO / "_calisma" / ".venv_z3" / "bin" / "pre-commit"
GIT = shutil.which("git")

HOOK_ID = "unstaged-delta"
CONFIG = """\
repos:
  - repo: local
    hooks:
      - id: {hook}
        name: unstaged delta gate
        entry: {python} {script}
        language: system
        always_run: true
        pass_filenames: false
        verbose: true
"""


def _env(home_dir: pathlib.Path) -> dict:
    """İzole ortam: kendi PRE_COMMIT_HOME'i, nötr git config, temiz PRE_COMMIT."""
    env = dict(os.environ)
    env["PRE_COMMIT_HOME"] = str(home_dir / ".pchome")
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env.pop("PRE_COMMIT", None)
    return env


class _Scratch(unittest.TestCase):
    """Ortak: scratch repo kurma/koşma yardımcıları."""

    def setUp(self):
        if GIT is None:
            self.skipTest("git yok")
        self.repo = pathlib.Path(tempfile.mkdtemp(prefix="unstaged-delta-"))
        self.addCleanup(shutil.rmtree, self.repo, True)
        self.env = _env(self.repo)
        self._git("init", "-q", ".")
        self._git("config", "user.email", "t@example.invalid")
        self._git("config", "user.name", "t")
        (self.repo / "a.txt").write_text("a1\n", encoding="utf-8")
        (self.repo / "b.txt").write_text("b1\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-qm", "initial")

    def _git(self, *args, **kw):
        env = kw.pop("env", self.env)
        return subprocess.run(
            [GIT, *args], cwd=str(self.repo), capture_output=True, text=True,
            env=env, timeout=120, **kw,
        )

    def _commit(self, msg):
        return subprocess.run(
            [GIT, "-c", "commit.gpgsign=false", "commit", "-qm", msg],
            cwd=str(self.repo), capture_output=True, text=True,
            env=self.env, timeout=300,
        )

    def _gate(self, **kw):
        env = kw.pop("env", self.env)
        return subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=str(self.repo),
            capture_output=True, text=True, env=env, timeout=120, **kw,
        )

    def _head(self):
        return self._git("rev-parse", "HEAD").stdout.strip()

    def _pchome(self) -> pathlib.Path:
        return pathlib.Path(self.env["PRE_COMMIT_HOME"])


class TestGateCli(_Scratch):
    """`git diff` ile görülebilen delta + ayrım sözleşmeleri."""

    def test_clean_tree_passes(self):
        res = self._gate()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("OK", res.stdout)

    def test_staged_only_change_passes(self):
        (self.repo / "a.txt").write_text("a2\n", encoding="utf-8")
        self._git("add", "a.txt")
        res = self._gate()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_unstaged_tracked_change_blocks_and_names_files(self):
        (self.repo / "a.txt").write_text("a2\n", encoding="utf-8")
        self._git("add", "b.txt")  # b1 ile aynı → staged hiçbir şey yok
        res = self._gate()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("COMMIT BLOKE", res.stdout)
        self.assertIn("a.txt", res.stdout, "bekleyen dosya adı yazılmalı")

    def test_message_carries_remedy(self):
        (self.repo / "a.txt").write_text("a2\n", encoding="utf-8")
        out = self._gate()
        self.assertIn("git add", out.stdout, "çözüm `git add` söylenmeli")
        self.assertIn("git stash", out.stdout, "alternatif çözüm söylenmeli")

    def test_untracked_file_is_not_a_delta(self):
        """Spec: yalnız İZLENEN dosyalar (untracked stash'e girmez)."""
        (self.repo / "yeni.txt").write_text("x\n", encoding="utf-8")
        res = self._gate()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_help_and_usage(self):
        ok = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                            capture_output=True, text=True, timeout=60)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        bad = subprocess.run([sys.executable, str(SCRIPT), "--nope"],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(bad.returncode, 2, bad.stdout + bad.stderr)


class TestStashSignal(_Scratch):
    """`git diff` KÖR olduğunda tek sinyal: ATA-pid'li stash patch'i."""

    def test_ancestor_pid_patch_is_detected(self):
        """Patch adındaki pid ata zincirindeyse delta görünmez olsa da bloklar."""
        self._pchome().mkdir(parents=True, exist_ok=True)
        patch = self._pchome() / f"patch{int(time.time())}-{os.getpid()}"
        patch.write_text(
            "diff --git a/gizli.txt b/gizli.txt\n"
            "index 1111111..2222222 100644\n"
            "--- a/gizli.txt\n+++ b/gizli.txt\n@@ -1 +1 @@\n-x\n+y\n",
            encoding="utf-8",
        )
        # git diff BOŞ olmalı: sinyal yalnız patch'ten geliyor
        self.assertEqual(self._git("diff", "--name-only").stdout.strip(), "")
        res = self._gate()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("gizli.txt", res.stdout)
        self.assertIn("stash patch", res.stdout, "sinyal kaynağı görünmeli")

    def test_foreign_pid_orphan_patch_is_ignored(self):
        """Yetim patch (ölmüş koşum) yanlış-pozitif üretmemeli."""
        self._pchome().mkdir(parents=True, exist_ok=True)
        orphan = self._pchome() / f"patch{int(time.time())}-999999"
        orphan.write_text(
            "diff --git a/eski.txt b/eski.txt\n--- a/eski.txt\n+++ b/eski.txt\n",
            encoding="utf-8",
        )
        res = self._gate()
        self.assertEqual(res.returncode, 0, "yabancı pid'li patch sayılmamalı")
        self.assertIn("OK", res.stdout)

    def test_missing_cache_dir_is_not_an_error(self):
        res = self._gate()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


@unittest.skipUnless(VENV_PC.is_file() or shutil.which("pre-commit"),
                     "pre-commit yok — entegrasyon testleri atlandı")
class TestRealPreCommitIntegration(_Scratch):
    """GERÇEK pre-commit: stash körlüğünü yakalayan bekçi testler."""

    def setUp(self):
        super().setUp()
        self.pc = str(VENV_PC) if VENV_PC.is_file() else shutil.which("pre-commit")
        (self.repo / ".pre-commit-config.yaml").write_text(
            CONFIG.format(hook=HOOK_ID, python=sys.executable, script=SCRIPT),
            encoding="utf-8",
        )
        self._git("add", ".pre-commit-config.yaml")
        self._commit("add config")
        inst = subprocess.run(
            [self.pc, "install", "-f"], cwd=str(self.repo),
            capture_output=True, text=True, env=self.env, timeout=300,
        )
        self.assertEqual(inst.returncode, 0, inst.stdout + inst.stderr)

    def test_commit_with_no_unstaged_delta_succeeds(self):
        """Negatif kontrol: kapı her commit'i bloklamamalı."""
        (self.repo / "a.txt").write_text("a2\n", encoding="utf-8")
        self._git("add", "a.txt")
        before = self._head()
        res = self._commit("temiz commit")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotEqual(self._head(), before, "commit ilerlemeliydi")

    def test_mixed_tree_commit_is_blocked_and_delta_survives(self):
        """Asıl sözleşme: stash kör olsa da commit BLOKE + delta KAYBOLMAZ."""
        (self.repo / "b.txt").write_text("b2\n", encoding="utf-8")
        self._git("add", "b.txt")
        (self.repo / "a.txt").write_text("a-unstaged\n", encoding="utf-8")
        before = self._head()
        res = self._commit("karışık ağaç")
        out = res.stdout + res.stderr
        self.assertNotEqual(res.returncode, 0, "karışık ağaçta commit bloke edilmeli\n" + out)
        self.assertIn("COMMIT BLOKE", out)
        self.assertIn("a.txt", out, "bekleyen dosya raporda görünmeli")
        self.assertEqual(self._head(), before, "commit ilerlememeliydi")
        self.assertEqual(
            (self.repo / "a.txt").read_text(encoding="utf-8"), "a-unstaged\n",
            "unstaged delta stash'ten geri gelmeli (kayıp yok)",
        )

    def test_all_files_run_blocks_on_visible_delta(self):
        """`--all-files` stash'i kapatır → görünür delta da yakalanmalı."""
        (self.repo / "a.txt").write_text("a-visible\n", encoding="utf-8")
        res = subprocess.run(
            [self.pc, "run", HOOK_ID, "--all-files"], cwd=str(self.repo),
            capture_output=True, text=True, env=self.env, timeout=300,
        )
        out = res.stdout + res.stderr
        self.assertNotEqual(res.returncode, 0, "görünür delta bloklanmalı\n" + out)
        self.assertIn("COMMIT BLOKE", out)

    def test_all_files_run_passes_on_clean_tree(self):
        res = subprocess.run(
            [self.pc, "run", HOOK_ID, "--all-files"], cwd=str(self.repo),
            capture_output=True, text=True, env=self.env, timeout=300,
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


class TestRealRepoConsistency(unittest.TestCase):
    """Gerçek repo: kapı rc'si `git diff --name-only` gerçeğiyle tutmalı.

    Kirli ve temiz ağaçta da doğru cevabı verir; geliştiricinin ağaç durumuna
    bağlı sahte yeşil/kırmızı üretmez.
    """

    def test_exit_code_matches_git_state(self):
        if GIT is None:
            self.skipTest("git yok")
        dirty = subprocess.run(
            [GIT, "diff", "--name-only"], cwd=str(REPO),
            capture_output=True, text=True, timeout=60,
        ).stdout.strip()
        res = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=str(REPO),
            capture_output=True, text=True, timeout=120,
        )
        expected = 1 if dirty else 0
        self.assertEqual(res.returncode, expected, res.stdout + res.stderr)


if __name__ == "__main__":
    unittest.main()
