#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_precommit_patch_recover.py — kurtarma yardımcısının sözleşmesi.

Ölçülen gerçek: `pre-commit` unstaged delta'yı `patch<epoch>-<pid>` dosyasına
stash'ler; süreç pencerede ölürse patch cache'te kalır (bu depoda üç olay:
`~/.cache/pre-commit/orphans-archive-20261003`). Yardımcı o kalıntıyı
OKUR, dosya bazında ağaç durumunu ölçer ve `--include` ile dosya dosya
geri uygular.

Bu süit gerçek git deposu + gerçek `git diff --binary` patch'i kullanır
(sentetik metin değil): list/diff/restore/dry-run, idempotensi, kısmi
`--include`, çakışma reddi, eklenen/silinen dosya işaretleri, yinelenen
patch tespiti ve hata kodları.

stdlib unittest — git gerekir (yoksa SKIP).
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = HERE / "precommit_patch_recover.py"
GIT = shutil.which("git")

ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_NOSYSTEM": "1",
    "HOME": os.environ.get("HOME", "/tmp"),
}


def run(cmd, cwd, check=True):
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          env=ENV, timeout=120)
    if check and proc.returncode != 0:
        raise AssertionError("%r başarısız (rc=%d): %s\n%s"
                             % (cmd, proc.returncode, proc.stdout, proc.stderr))
    return proc


def gate(*args, root, check=False):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--root", str(root)],
        capture_output=True, text=True, env=ENV, timeout=120)


@unittest.skipUnless(GIT, "git yok")
class _Scratch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="patch-recover-")
        self.root = pathlib.Path(self.tmp.name) / "repo"
        self.cache = pathlib.Path(self.tmp.name) / "cache"
        self.root.mkdir()
        self.cache.mkdir()
        run([GIT, "init", "-q", "."], self.root)
        run([GIT, "config", "user.email", "t@example.com"], self.root)
        run([GIT, "config", "user.name", "T"], self.root)
        (self.root / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
        (self.root / "b.txt").write_text("alpha\nbeta\n", encoding="utf-8")
        run([GIT, "add", "a.txt", "b.txt"], self.root)
        run([GIT, "commit", "-qm", "base"], self.root)
        self.patch = self.cache / "patch1700000000-4242"

    def tearDown(self):
        self.tmp.cleanup()

    def make_patch(self, mutate, name=None):
        """Çalışma ağacını boz, `git diff --binary`'yi patch olarak yaz, geri al."""
        mutate()
        diff = run([GIT, "diff", "--binary"], self.root).stdout
        self.assertIn("diff --git", diff, "patch üretilemedi")
        dest = self.cache / (name or self.patch.name)
        dest.write_text(diff, encoding="utf-8")
        # `git checkout -- .` yetmez: `git add -N` girişi index'te kalır ve
        # yeni-dosya yolunu BOŞ içerikle geri yazar. Base durumuna dön.
        run([GIT, "reset", "-q", "--hard"], self.root)
        run([GIT, "clean", "-fdq"], self.root)
        return dest

    def restore_tree(self):
        run([GIT, "checkout", "--", "."], self.root)
        run([GIT, "clean", "-fdq"], self.root)


class TestListAndDiff(_Scratch):
    def test_list_reports_files_counts_and_tree_state(self):
        self.make_patch(lambda: (self.root / "a.txt").write_text(
            "one\nTWO\nthree\nfour\n", encoding="utf-8"))
        proc = gate("--dir", str(self.cache), root=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("patch1700000000-4242", proc.stdout)
        self.assertIn("a.txt", proc.stdout)
        self.assertIn("uygulanabilir", proc.stdout)
        self.assertRegex(proc.stdout, r"\+2\s+-1")

    def test_list_shows_already_present_after_restore(self):
        self.make_patch(lambda: (self.root / "a.txt").write_text(
            "one\nTWO\nthree\n", encoding="utf-8"))
        self.assertEqual(gate("--restore", self.patch.name, "--dir",
                              str(self.cache), root=self.root).returncode, 0)
        proc = gate("--dir", str(self.cache), root=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ağaçta VAR", proc.stdout)

    def test_empty_directory_is_not_an_error(self):
        proc = gate("--dir", str(self.cache), root=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("kalıntı yok", proc.stdout)

    def test_diff_filters_by_include(self):
        def mutate():
            (self.root / "a.txt").write_text("one\nTWO\n", encoding="utf-8")
            (self.root / "b.txt").write_text("alpha\nBETA\n", encoding="utf-8")
        self.make_patch(mutate)
        full = gate("--diff", self.patch.name, "--dir", str(self.cache),
                    root=self.root)
        self.assertEqual(full.returncode, 0, full.stderr)
        self.assertIn("+TWO", full.stdout)
        self.assertIn("+BETA", full.stdout)
        only = gate("--diff", self.patch.name, "--dir", str(self.cache),
                    "--include", "b.txt", root=self.root)
        self.assertEqual(only.returncode, 0, only.stderr)
        self.assertIn("+BETA", only.stdout)
        self.assertNotIn("+TWO", only.stdout)
        self.assertIn("diff --git a/b.txt b/b.txt", only.stdout)

    def test_json_is_one_document(self):
        self.make_patch(lambda: (self.root / "a.txt").write_text(
            "one\nX\n", encoding="utf-8"))
        proc = gate("--dir", str(self.cache), "--json", root=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(len(payload["patches"]), 1)
        patch = payload["patches"][0]
        self.assertEqual(patch["name"], self.patch.name)
        self.assertEqual(len(patch["sha256"]), 64)
        self.assertEqual(patch["files"][0]["path"], "a.txt")
        self.assertEqual(patch["files"][0]["state"], "uygulanabilir")
        self.assertFalse(patch["stale"])

    def test_duplicate_patches_are_flagged(self):
        self.make_patch(lambda: (self.root / "a.txt").write_text(
            "one\nX\n", encoding="utf-8"))
        shutil.copy(self.patch, self.cache / "patch1700000001-4343")
        proc = gate("--dir", str(self.cache), root=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("yinelenen", proc.stdout)


class TestRestore(_Scratch):
    def test_dry_run_does_not_write(self):
        self.make_patch(lambda: (self.root / "a.txt").write_text(
            "one\nTWO\n", encoding="utf-8"))
        proc = gate("--restore", self.patch.name, "--dry-run", "--dir",
                    str(self.cache), root=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("yazılmadı", proc.stdout)
        self.assertEqual((self.root / "a.txt").read_text(encoding="utf-8"),
                         "one\ntwo\nthree\n")

    def test_restore_applies_and_is_idempotent(self):
        self.make_patch(lambda: (self.root / "a.txt").write_text(
            "one\nTWO\nthree\nfour\n", encoding="utf-8"))
        first = gate("--restore", self.patch.name, "--dir", str(self.cache),
                     root=self.root)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("GERİ", first.stdout)
        self.assertEqual((self.root / "a.txt").read_text(encoding="utf-8"),
                         "one\nTWO\nthree\nfour\n")
        second = gate("--restore", self.patch.name, "--dir", str(self.cache),
                      root=self.root)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("zaten var", second.stdout)
        self.assertIn("0 uygulandı · 1 zaten var", second.stdout)

    def test_include_restores_only_selected_file(self):
        def mutate():
            (self.root / "a.txt").write_text("one\nTWO\n", encoding="utf-8")
            (self.root / "b.txt").write_text("alpha\nBETA\n", encoding="utf-8")
        self.make_patch(mutate)
        proc = gate("--restore", self.patch.name, "--include", "b.txt",
                    "--dir", str(self.cache), root=self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual((self.root / "b.txt").read_text(encoding="utf-8"),
                         "alpha\nBETA\n")
        self.assertEqual((self.root / "a.txt").read_text(encoding="utf-8"),
                         "one\ntwo\nthree\n", "seçilmeyen dosya değişti")

    def test_conflict_is_refused_and_nothing_written(self):
        self.make_patch(lambda: (self.root / "a.txt").write_text(
            "one\nTWO\nthree\n", encoding="utf-8"))
        (self.root / "a.txt").write_text("one\nBAMBASKA\nthree\n",
                                        encoding="utf-8")
        proc = gate("--restore", self.patch.name, "--dir", str(self.cache),
                    root=self.root)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("ÇAKIŞ", proc.stdout)
        self.assertIn("patch SİLİNMEDİ", proc.stderr)
        self.assertEqual((self.root / "a.txt").read_text(encoding="utf-8"),
                         "one\nBAMBASKA\nthree\n")

    def test_added_and_deleted_files_round_trip(self):
        (self.root / "c.txt").write_text("new file\n", encoding="utf-8")
        run([GIT, "add", "-N", "c.txt"], self.root)

        def mutate():
            (self.root / "b.txt").unlink()
        self.make_patch(mutate)
        listed = gate("--dir", str(self.cache), root=self.root)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("A", listed.stdout)
        self.assertIn("D", listed.stdout)
        proc = gate("--restore", self.patch.name, "--dir", str(self.cache),
                    root=self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse((self.root / "b.txt").exists(), "silinen dosya kaldı")
        self.assertTrue((self.root / "c.txt").exists(), "eklenen dosya gelmedi")

    def test_new_file_with_intent_to_add_counts_as_present(self):
        """`git add -N` girişi varken içerik eşleşiyorsa dosya "zaten var"dır.

        Bu ölçüldü: `--reverse --check` intent-to-add girdisine rağmen temiz
        döner; yani yardımcı bu durumu ÇAKIŞMA diye reddetmemeli.
        """
        (self.root / "c.txt").write_text("new file\n", encoding="utf-8")
        run([GIT, "add", "-N", "c.txt"], self.root)
        self.make_patch(lambda: (self.root / "a.txt").write_text(
            "one\nX\n", encoding="utf-8"))
        # Ağacı patch'in SONRASI duruma getir, sonra index'e niyet girişi ekle.
        (self.root / "c.txt").write_text("new file\n", encoding="utf-8")
        run([GIT, "add", "-N", "c.txt"], self.root)
        proc = gate("--restore", self.patch.name, "--dir", str(self.cache),
                    root=self.root)
        self.assertNotIn("ÇAKIŞ", proc.stdout, proc.stdout)
        state = self.restore_state("c.txt")
        self.assertEqual(state, "zaten-var", proc.stdout)

    def restore_state(self, rel):
        proc = gate("--dir", str(self.cache), "--json", root=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        for patch in payload["patches"]:
            for info in patch["files"]:
                if info["path"] == rel:
                    return info["state"]
        raise AssertionError("%s patch'te yok" % rel)

    def test_patch_path_outside_cache_is_accepted(self):
        self.make_patch(lambda: (self.root / "a.txt").write_text(
            "one\nX\n", encoding="utf-8"))
        outside = pathlib.Path(self.tmp.name) / "elsewhere.patch"
        shutil.copy(self.patch, outside)
        proc = gate("--diff", str(outside), "--dir", str(self.cache),
                    root=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("+X", proc.stdout)


class TestErrors(_Scratch):
    def test_missing_directory_is_measurement_error(self):
        proc = gate("--dir", str(pathlib.Path(self.tmp.name) / "yok"),
                    root=self.root)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("dizini yok", proc.stderr)

    def test_not_a_patch_file_is_measurement_error(self):
        bad = self.cache / "patch1700000002-1"
        bad.write_text("bu bir patch degil\n", encoding="utf-8")
        proc = gate("--dir", str(self.cache), root=self.root)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("diff --git", proc.stderr)

    def test_restore_without_patch_name_is_usage_error(self):
        proc = gate("--restore", "--dir", str(self.cache), root=self.root)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("patch adı gerekli", proc.stderr)

    def test_unknown_patch_name_is_usage_error(self):
        proc = gate("--restore", "patch9999999999-1", "--dir", str(self.cache),
                    root=self.root)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("patch bulunamadı", proc.stderr)

    def test_non_matching_include_is_usage_error(self):
        self.make_patch(lambda: (self.root / "a.txt").write_text(
            "one\nX\n", encoding="utf-8"))
        proc = gate("--restore", self.patch.name, "--include", "zzz.txt",
                    "--dir", str(self.cache), root=self.root)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("eşleşen dosya yok", proc.stderr)

    def test_non_repo_root_is_rejected(self):
        outside = pathlib.Path(self.tmp.name) / "notrepo"
        outside.mkdir()
        proc = gate("--dir", str(self.cache), root=outside)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("git deposu değil", proc.stderr)


class TestRealArchiveTools(unittest.TestCase):
    """Yardımcının kendisi gerçek arşivde okuma hatası vermemeli."""

    ARCHIVE = pathlib.Path(os.path.expanduser(
        "~/.cache/pre-commit/orphans-archive-20261003"))

    @unittest.skipUnless(ARCHIVE.is_dir(), "yerel arşiv yok")
    def test_reads_local_incident_archive(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--dir", str(self.ARCHIVE),
             "--json", "--root", str(ROOT)],
            capture_output=True, text=True, timeout=180)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertGreaterEqual(len(payload["patches"]), 1)
        for patch in payload["patches"]:
            self.assertEqual(len(patch["sha256"]), 64)
            self.assertGreaterEqual(len(patch["files"]), 1)
            for info in patch["files"]:
                self.assertIn(info["state"],
                              ("zaten-var", "uygulanabilir", "cakisma"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
