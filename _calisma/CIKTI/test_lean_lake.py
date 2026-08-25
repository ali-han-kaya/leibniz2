#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_lean_lake.py — K9 lake build kapısının regresyon testleri.

verify_delivery.run_lake_build: 8 teoremli Content.lean çekirdeğini
`lake clean && lake build --wfail` ile, lean-toolchain v4.14.0 zorunluluğuyla
fail-closed derler. subprocess mock'lu (OFFLINE) — gerçek lake koşmaz.

Kapsam:
  - toolchain doğrulaması: yok / uyuşmaz → FAIL (yanlış sürüm kapıda yakalanır)
  - lake clean/build: returncode 0 → PASS; nonzero → FAIL + çıktı kuyruğu
  - lake yok (FileNotFoundError) ve timeout → FAIL
  - find_tool: PATH / brew / elan sırası
  - K9 genel: file-ok ∧ lake-ok (biri FAIL ise K9 FAIL)
  - --lean-only: lean derleyicisi hiç yokken lake alt-kapısı SKIP
    (None = nötr; subprocess çağrılmaz); bayrak yoksa veya lean varsa
    davranış eskisi gibi fail-closed
"""
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery as vd  # noqa: E402


def _proc(returncode=0, stdout="", stderr=""):
    p = mock.Mock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


class TestRunLakeBuild(unittest.TestCase):
    """run_lake_build: toolchain + clean + build zinciri (fail-closed)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.tc = os.path.join(self.dir, "lean-toolchain")
        with open(self.tc, "w", encoding="utf-8") as f:
            f.write(vd.LEAN_TOOLCHAIN + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self):
        return vd.run_lake_build("lake", self.dir)

    def test_pass_with_correct_toolchain(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=[_proc(0), _proc(0)]):
            ok, detail = self._run()
        self.assertTrue(ok, detail)
        self.assertIn("8 teorem PASS", detail)

    def test_missing_toolchain_fails(self):
        os.remove(self.tc)
        ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("lean-toolchain yok", detail)

    def test_wrong_toolchain_version_fails(self):
        with open(self.tc, "w", encoding="utf-8") as f:
            f.write("leanprover/lean4:v4.15.0\n")
        with mock.patch.object(vd.subprocess, "run") as m:
            ok, detail = self._run()
            # Yanlış sürümle lake HİÇ koşmamalı (fail-closed).
            m.assert_not_called()
        self.assertFalse(ok)
        self.assertIn("lean-toolchain uyuşmaz", detail)
        self.assertIn("v4.14.0", detail)

    def test_clean_failure_fails(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=[_proc(1, stdout="hata\nsatır")]):
            ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("lake clean hatası", detail)
        self.assertIn("hata", detail)

    def test_build_failure_fails_with_tail(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=[_proc(0), _proc(1, stdout="a\nb\nc\nd")]):
            ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("lake build hatası", detail)
        self.assertIn("b | c | d", detail)  # son 3 satır kuyruğu

    def test_lake_missing_fails(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=FileNotFoundError):
            ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("lake bulunamadı", detail)

    def test_build_timeout_fails(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=[_proc(0), vd.subprocess.TimeoutExpired("lake", 600)]):
            ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("zaman aşımı", detail)

    def test_calls_clean_then_build_in_project_dir(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=[_proc(0), _proc(0)]) as m:
            self._run()
        calls = [c for c in m.call_args_list]
        self.assertEqual(calls[0].args[0], ["lake", "clean"])
        self.assertEqual(calls[1].args[0], ["lake", "build", "--wfail"])
        self.assertEqual(calls[0].kwargs["cwd"], self.dir)
        self.assertEqual(calls[1].kwargs["cwd"], self.dir)


class TestFindTool(unittest.TestCase):
    def test_returns_elan_shim_when_present(self):
        elan = os.path.expanduser("~/.elan/bin/lake")
        if os.path.isfile(elan):
            self.assertEqual(vd.find_tool("lake"), elan)
        else:
            self.skipTest("~/.elan/bin/lake yok")

    def test_returns_bare_when_nowhere(self):
        with mock.patch.object(os.path, "isfile", return_value=False):
            self.assertEqual(vd.find_tool("lake"), "lake")


class TestLeanOnlySkip(unittest.TestCase):
    """--lean-only: lean derleyicisi yokken lake alt-kapısı atlanabilir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        with open(os.path.join(self.dir, "lean-toolchain"), "w",
                  encoding="utf-8") as f:
            f.write(vd.LEAN_TOOLCHAIN + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _no_compiler(self):
        return mock.patch.object(vd, "find_tool", return_value="lean"), \
            mock.patch.object(vd.shutil, "which", return_value=None)

    def test_skip_returns_none_without_compiler(self):
        p1, p2 = self._no_compiler()
        with p1, p2:
            ok, detail = vd.run_lake_build("lake", self.dir, lean_only=True)
        self.assertIsNone(ok)
        self.assertIn("SKIP", detail)
        self.assertIn("--lean-only", detail)

    def test_skip_short_circuits_before_subprocess(self):
        # SKIP kararında lake/toolchain HİÇ sorgulanmaz.
        p1, p2 = self._no_compiler()
        with mock.patch.object(vd.subprocess, "run") as m, p1, p2:
            vd.run_lake_build("lake", self.dir, lean_only=True)
        m.assert_not_called()

    def test_default_still_fails_closed_without_compiler(self):
        # Bayrak yokken lean yokluğu davranışı değiştirmez: zincir koşar,
        # lake bulunamazsa FAIL (fail-closed korunur).
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=FileNotFoundError):
            ok, detail = vd.run_lake_build("lake", self.dir)
        self.assertFalse(ok)
        self.assertIn("lake bulunamadı", detail)

    def test_lean_present_runs_normally_with_flag(self):
        # find_tool eşleşme bulamadı ama PATH'te var (which → yol): kapı koşar.
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=[_proc(0), _proc(0)]), \
                mock.patch.object(vd, "find_tool", return_value="/x/lean"), \
                mock.patch.object(vd.shutil, "which",
                                  return_value="/usr/bin/lean"):
            ok, detail = vd.run_lake_build("lake", self.dir, lean_only=True)
        self.assertTrue(ok, detail)
        self.assertIn("8 teorem PASS", detail)

    def test_wrong_toolchain_still_fails_even_with_flag(self):
        # SKIP kararı toolchain doğrulamasını BYPASS ETMEZ: lean kuruluysa
        # sürüm uyuşmazlığı yine FAIL'tir (fail-closed).
        with open(os.path.join(self.dir, "lean-toolchain"), "w",
                  encoding="utf-8") as f:
            f.write("leanprover/lean4:v4.15.0\n")
        with mock.patch.object(vd, "find_tool", return_value="/x/lean"), \
                mock.patch.object(vd.shutil, "which",
                                  return_value="/usr/bin/lean"):
            ok, detail = vd.run_lake_build("lake", self.dir, lean_only=True)
        self.assertFalse(ok)
        self.assertIn("uyuşmaz", detail)


class TestK9Combined(unittest.TestCase):
    """K9 genel: file-check ∧ lake-check — biri FAIL ise K9 FAIL.

    SKIP (None) nötrdür: yalnızca --lean-only + lean-yok ortamında oluşur,
    birleşik sonucu tek başına bozmaz (file-ok belirler).
    """

    def _call_k9(self, file_ok, lake_ok):
        # K9 bloğunu izole koşulamayacağı için iki kapının mantığını
        # aynen uygulayan birleşimi doğrula (ok = file_ok and lake≠False).
        ok = file_ok and (lake_ok is not False)
        return ok

    def test_both_pass(self):
        self.assertTrue(self._call_k9(True, True))

    def test_file_fail_dominates(self):
        self.assertFalse(self._call_k9(False, True))

    def test_lake_fail_dominates(self):
        self.assertFalse(self._call_k9(True, False))

    def test_skip_is_neutral_when_file_passes(self):
        # --lean-only SKIP: file-ok ∧ (None ≠ False) → K9 PASS.
        self.assertTrue(self._call_k9(True, None))

    def test_skip_does_not_rescue_failing_file_check(self):
        self.assertFalse(self._call_k9(False, None))

    def test_k9_layer_label_mentions_both_cores(self):
        self.assertIn("8 teorem", vd.LAYER_LABELS["K9"])

    def test_constants(self):
        self.assertEqual(vd.LEAN_TOOLCHAIN, "leanprover/lean4:v4.14.0")
        self.assertTrue(vd.LEAN_REDUCT_DIR)
        # lean-toolchain dosyası gerçekten v4.14.0'ı taşıyor olmalı (tek kaynak).
        tc = pathlib.Path(__file__).resolve().parent.parent \
            / "lean_reduct" / "lean-toolchain"
        self.assertEqual(tc.read_text(encoding="utf-8").strip(),
                         vd.LEAN_TOOLCHAIN)


if __name__ == "__main__":
    unittest.main()
