#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_hook_collisions.py — yazan-hook ↔ unstaged delta kapısı testleri.

Seam: kapının CLI'si (stdout/stderr, exit kodu) ve GERÇEK git ağacı. Testler
izole scratch repo'larda koşar (kendi `PRE_COMMIT_HOME`'i, kendi `.git`'i,
global/system git config nötrlenmiş) — geliştiricinin kirli ağacı testi
etkilemez.

Pinlenen davranışlar:
  * README / PUBLISH_SCENARIO / verify_delivery.config.json üzerinde
    UNSTAGED delta + o dosyayı YAZAN hook → exit 1, dosya→hook eşleşmesi
    ADIYLA + çözüm; dosya içeriği ve index DEĞİŞMEZ (kapı yazmaz).
  * Yalnız stage'li değişiklik → exit 0 (hook'un okuyacağı içerik zaten
    commit'in içeriği).
  * Hedef-dışı unstaged dosya → exit 0 (genel kural `check-unstaged-delta`'nın
    işi; bu kapı onu tekrar etmez).
  * Registry bayatlığı (hook config'te yok / hedef izlenmiyor) → exit 2.
  * Delta ölçümü imkânsız (yardımcı modül yok) / config yok → exit 2
    (fail-closed: sessiz PASS yok).
  * Gerçek ağaçta `check-hook-collisions` config'te ve zincirin BAŞINDA.
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
SCRIPT = HERE / "check_hook_collisions.py"
GIT = shutil.which("git")

sys.path.insert(0, str(HERE))
import check_hook_collisions as gate  # noqa: E402

TARGETS = ("README.md", "docs/PUBLISH_SCENARIO.md",
           "_calisma/CIKTI/verify_delivery.config.json")

CONFIG = """\
repos:
  - repo: local
    hooks:
      - id: check-hook-collisions
        name: collision gate
        entry: python3 _calisma/CIKTI/check_hook_collisions.py
        language: system
        always_run: true
        pass_filenames: false
      # Yazan üç hook: gerçek gövdeleri sandbox'ta yok; kapı yalnız
      # ADLARINI (registry doğrulaması) görür.
      - id: update-config
        name: update config
        entry: "true"
        language: system
        always_run: true
        pass_filenames: false
      - id: check-changelog-sync
        name: changelog
        entry: "true"
        language: system
        always_run: true
        pass_filenames: false
      - id: check-skills-index
        name: skills index
        entry: "true"
        language: system
        always_run: true
        pass_filenames: false
"""


def _env(home: pathlib.Path) -> dict:
    env = dict(os.environ)
    env["PRE_COMMIT_HOME"] = str(home / ".pchome")
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env.pop("PRE_COMMIT", None)
    return env


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _Scratch(unittest.TestCase):
    """Sandbox repo: gerçek dosya adları + alt küme config + kopya gate."""

    def setUp(self):
        if GIT is None:
            self.skipTest("git yok")
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="hook-collisions-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.env = _env(self.root)
        cikti = self.root / "_calisma" / "CIKTI"
        cikti.mkdir(parents=True)
        for name in ("check_hook_collisions.py", "check_unstaged_delta.py",
                     "check_precommit_inventory.py"):
            shutil.copy(HERE / name, cikti / name)
        self.script = cikti / "check_hook_collisions.py"

        (self.root / ".pre-commit-config.yaml").write_text(CONFIG, encoding="utf-8")
        (self.root / "README.md").write_text("readme1\n", encoding="utf-8")
        (self.root / "other.txt").write_text("other1\n", encoding="utf-8")
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "PUBLISH_SCENARIO.md").write_text("publish1\n", encoding="utf-8")
        (cikti / "verify_delivery.config.json").write_text("{}\n", encoding="utf-8")

        self._git("init", "-q", ".")
        self._git("config", "user.email", "t@example.invalid")
        self._git("config", "user.name", "t")
        self._git("add", "-A")
        self._git("commit", "-qm", "initial")

    def _git(self, *args, **kw):
        return subprocess.run(
            [GIT, *args], cwd=str(self.root), capture_output=True, text=True,
            env=kw.pop("env", self.env), timeout=120, **kw,
        )

    def _gate(self, *args, **kw):
        return subprocess.run(
            [sys.executable, str(kw.pop("script", self.script)), *args],
            cwd=str(self.root), capture_output=True, text=True,
            env=kw.pop("env", self.env), timeout=120, **kw,
        )

    def _write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _tracked_snapshot(self):
        """İzlenen tüm dosyaların (yol → sha256) + index durumunun anlık görüntüsü."""
        files = self._git("ls-files", "-z").stdout.split("\0")
        hashes = {rel: _sha(self.root / rel) for rel in files if rel}
        staged = self._git("diff", "--cached", "--name-only").stdout
        return hashes, staged

    def _unstaged(self, rel, text="changed\n"):
        self._write(rel, text)


class TestPureMapping(unittest.TestCase):
    """Registry → ters indeks ve kesişim (yan etkisiz)."""

    def test_readme_maps_to_both_writing_hooks(self):
        hits = gate.collisions(["README.md"])
        self.assertEqual(len(hits), 1)
        rel, hooks = hits[0]
        self.assertEqual(rel, "README.md")
        self.assertEqual([h for h, _ in hooks],
                         ["check-changelog-sync", "check-skills-index"])

    def test_non_target_file_never_collides(self):
        self.assertEqual(gate.collisions(["other.txt", "docs/README.md"]), [])

    def test_collision_order_is_stable(self):
        hits = gate.collisions(["docs/PUBLISH_SCENARIO.md", "README.md"])
        self.assertEqual([rel for rel, _ in hits],
                         ["README.md", "docs/PUBLISH_SCENARIO.md"])

    def test_registry_names_only_writing_hooks(self):
        self.assertEqual(set(gate.WRITERS),
                         {"update-config", "check-changelog-sync", "check-skills-index"})


class TestGateCli(_Scratch):
    """CLI sözleşmesi: bloke / geç / ölçülemedi."""

    def test_clean_tree_passes(self):
        res = self._gate()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("OK", res.stdout)
        self.assertIn("3 hook", res.stdout)

    def test_staged_only_is_fine(self):
        self._write("README.md", "readme2\n")
        self._git("add", "README.md")
        res = self._gate()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_unstaged_readme_blocks_names_hook_and_preserves_tree(self):
        self._write("README.md", "readme2 (unstaged)\n")
        before = self._tracked_snapshot()
        res = self._gate()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("HOOK ÇAKIŞMASI", res.stdout)
        self.assertIn("README.md", res.stdout)
        self.assertIn("check-changelog-sync", res.stdout)
        self.assertIn("check-skills-index", res.stdout)
        self.assertIn("git add README.md", res.stdout)
        self.assertIn("git stash push", res.stdout)
        self.assertIn("YAZMADI", res.stdout)
        after = self._tracked_snapshot()
        self.assertEqual(before, after,
                         "kapı yazmamalı: içerik ve index aynı kalmalı")

    def test_staged_plus_unstaged_still_blocks(self):
        self._write("README.md", "readme2 (staged)\n")
        self._git("add", "README.md")
        self._write("README.md", "readme3 (unstaged)\n")
        res = self._gate()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"),
                         "readme3 (unstaged)\n")

    def test_unstaged_publish_and_config_are_detected(self):
        self._unstaged("docs/PUBLISH_SCENARIO.md")
        self._unstaged("_calisma/CIKTI/verify_delivery.config.json",
                      '{"expected_pages": 33}\n')
        res = self._gate()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("docs/PUBLISH_SCENARIO.md", res.stdout)
        self.assertIn("_calisma/CIKTI/verify_delivery.config.json", res.stdout)
        self.assertIn("update-config", res.stdout)

    def test_non_target_unstaged_is_left_to_generic_gate(self):
        self._unstaged("other.txt")
        res = self._gate()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("OK", res.stdout)

    def test_untracked_file_next_to_targets_is_not_a_collision(self):
        (self.root / "docs" / "new-note.md").write_text("x\n", encoding="utf-8")
        res = self._gate()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


class TestFailClosed(_Scratch):
    """Ölçülemezse veya registry bayatsa yeşil YOK."""

    def test_missing_helper_blocks(self):
        (self.root / "_calisma" / "CIKTI" / "check_unstaged_delta.py").unlink()
        res = self._gate()
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("ÖLÇÜLEMEDİ", res.stdout)
        self.assertNotIn("OK —", res.stdout)

    def test_missing_config_blocks(self):
        (self.root / ".pre-commit-config.yaml").unlink()
        res = self._gate()
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("ÖLÇÜLEMEDİ", res.stdout)

    def test_registry_hook_absent_from_config_blocks(self):
        cfg = self.root / ".pre-commit-config.yaml"
        text = cfg.read_text(encoding="utf-8")
        cfg.write_text(text.replace("      - id: check-skills-index\n", ""),
                       encoding="utf-8")
        res = self._gate()
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("registry bayat", res.stdout)
        self.assertIn("check-skills-index", res.stdout)

    def test_registry_target_not_tracked_blocks(self):
        self._git("rm", "--cached", "-q",
                  "_calisma/CIKTI/verify_delivery.config.json")
        res = self._gate()
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("izlenen dosya değil", res.stdout)

    def test_json_mode_is_machine_readable(self):
        self._write("README.md", "readme2\n")
        res = self._gate("--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        payload = json.loads(res.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["rc"], 1)
        self.assertEqual([c["path"] for c in payload["collisions"]], ["README.md"])
        self.assertEqual(payload["problems"], [])


VENV_PC = REPO / "_calisma" / ".venv_z3" / "bin" / "pre-commit"


@unittest.skipUnless(VENV_PC.is_file() or shutil.which("pre-commit"),
                     "pre-commit yok — stash-penceresi entegrasyonu atlandı")
class TestRealPreCommitIntegration(_Scratch):
    """GERÇEK pre-commit: stash penceresinde kapı yine de çakışmayı görmeli.

    `git commit` sırasında pre-commit ağacı index'e eşitler ve `git diff`
    BOŞ döner; kapı delta'yı ata-pid'li `patch<epoch>-<pid>` üzerinden bulur.
    Bu test o mekanizmanın uçtan uca çalıştığını ve kullanıcının unstaged
    düzenlemesinin commit engellendiğinde KAYBOLMADIĞINI pinler.
    """

    def setUp(self):
        super().setUp()
        self.pc = str(VENV_PC) if VENV_PC.is_file() else shutil.which("pre-commit")
        inst = subprocess.run(
            [self.pc, "install", "-f"], cwd=str(self.root),
            capture_output=True, text=True, env=self.env, timeout=300,
        )
        self.assertEqual(inst.returncode, 0, inst.stdout + inst.stderr)

    def _commit(self, msg):
        return subprocess.run(
            [GIT, "-c", "commit.gpgsign=false", "commit", "-qm", msg],
            cwd=str(self.root), capture_output=True, text=True,
            env=self.env, timeout=300,
        )

    def _head(self):
        return self._git("rev-parse", "HEAD").stdout.strip()

    def test_commit_blocked_inside_stash_window_and_edit_survives(self):
        self._write("other.txt", "other2\n")
        self._git("add", "other.txt")
        self._write("README.md", "readme (unstaged kullanıcı düzenlemesi)\n")
        before = self._head()
        res = self._commit("karışık ağaç")
        out = res.stdout + res.stderr
        self.assertNotEqual(res.returncode, 0,
                            "stash penceresinde commit bloke edilmeli\n" + out)
        self.assertIn("HOOK ÇAKIŞMASI", out)
        self.assertIn("README.md", out)
        self.assertIn("check-changelog-sync", out)
        self.assertEqual(self._head(), before, "commit ilerlememeliydi")
        self.assertEqual(
            (self.root / "README.md").read_text(encoding="utf-8"),
            "readme (unstaged kullanıcı düzenlemesi)\n",
            "unstaged düzenleme stash'ten geri gelmeli (kayıp yok)",
        )

    def test_clean_staged_commit_succeeds(self):
        self._write("other.txt", "other2\n")
        self._git("add", "other.txt")
        before = self._head()
        res = self._commit("temiz commit")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotEqual(self._head(), before, "temiz commit ilerlemeliydi")


class TestRealRepo(unittest.TestCase):
    """Gerçek ağaç: registry + zincir sırası."""

    def test_writer_ids_exist_in_real_config(self):
        ids = gate.config_hook_ids(REPO / ".pre-commit-config.yaml")
        for hook in gate.WRITERS:
            self.assertIn(hook, ids)

    def test_writer_targets_are_tracked(self):
        paths = [rel for paths_, _ in gate.WRITERS.values() for rel in paths_]
        tracked = gate.tracked_paths(paths)
        self.assertEqual(set(paths) - tracked, set())

    def test_gate_is_first_in_chain(self):
        ids = gate.config_hook_ids(REPO / ".pre-commit-config.yaml")
        self.assertEqual(ids[0], "check-hook-collisions",
                         "fail-fast kapısı zincirin BAŞINDA olmalı")

    def test_real_repo_registry_is_healthy(self):
        self.assertEqual(gate.validate_registry(REPO / ".pre-commit-config.yaml"), [])


if __name__ == "__main__":
    unittest.main()
