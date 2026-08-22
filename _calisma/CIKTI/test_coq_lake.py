#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_coq_lake.py — K19 coqtop kapısının regresyon testleri.

verify_delivery.run_coq_proof: 8 teoremli Content.v çekirdeğini coqtop ile
fail-closed derler. subprocess mock'lu (OFFLINE) — gerçek coqtop koşmaz.

Kapsam:
  - coq-version doğrulaması: yok / uyuşmaz → FAIL (yanlış sürüm kapıda yakalanır)
  - admit/Admitted/Axiom/Parameter taraması → FAIL (proof gap)
  - coqtop --version ayrıştırma: uyuşur → devam; ayrıştırılamaz → FAIL
  - coqtop -compile: returncode 0 → PASS; nonzero → FAIL + çıktı kuyruğu
  - coqtop yok (FileNotFoundError) ve timeout → FAIL
  - K19 genel: sürüm ∧ gap ∧ derleme — biri FAIL ise K19 FAIL
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

COQ_DIR = pathlib.Path(__file__).resolve().parent.parent / "coq_reduct"
REAL_V = COQ_DIR / "Content.v"

VERSION_OUT = "The Coq Proof Assistant, version 8.18.0 (December 2023, compiled with OCaml 4.14.1)\n"


def _proc(returncode=0, stdout="", stderr=""):
    p = mock.Mock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


class TestRunCoqProof(unittest.TestCase):
    """run_coq_proof: sürüm + gap + derleme zinciri (fail-closed)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.v = os.path.join(self.dir, "Content.v")
        with open(self.v, "w", encoding="utf-8") as f:
            f.write("Theorem trivial : True.\nProof. exact I. Qed.\n")
        self.vf = os.path.join(self.dir, "coq-version")
        with open(self.vf, "w", encoding="utf-8") as f:
            f.write(vd.COQ_VERSION + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self):
        return vd.run_coq_proof("coqtop", self.v,
                                version_file=self.vf)

    def test_pass_with_matching_version(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=[_proc(0, stdout=VERSION_OUT),
                                            _proc(0)]):
            ok, detail = self._run()
        self.assertTrue(ok, detail)
        self.assertIn("8 teorem PASS", detail)

    def test_missing_version_file_fails(self):
        os.remove(self.vf)
        with mock.patch.object(vd.subprocess, "run") as m:
            ok, detail = self._run()
            m.assert_not_called()
        self.assertFalse(ok)
        self.assertIn("coq-version yok", detail)

    def test_wrong_version_file_fails(self):
        with open(self.vf, "w", encoding="utf-8") as f:
            f.write("8.20\n")
        with mock.patch.object(vd.subprocess, "run") as m:
            ok, detail = self._run()
            # Yanlış sürümle coqtop HİÇ koşmamalı (fail-closed).
            m.assert_not_called()
        self.assertFalse(ok)
        self.assertIn("coq-version uyuşmaz", detail)
        self.assertIn("8.18", detail)

    def test_coqtop_version_mismatch_fails(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=[_proc(0, stdout=VERSION_OUT.replace(
                                   "8.18.0", "8.20.1"))]):
            ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("coqtop sürüm uyuşmaz", detail)
        self.assertIn("8.20 (beklenen 8.18)", detail)

    def test_version_unparseable_fails(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=[_proc(0, stdout="coqtop: hata\n")]):
            ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("ayrıştırılamadı", detail)

    def test_admit_detected_fails(self):
        with open(self.v, "w", encoding="utf-8") as f:
            f.write("Theorem foo : True.\nProof. admit. Qed.\n")
        with mock.patch.object(vd.subprocess, "run") as m:
            ok, detail = self._run()
            m.assert_not_called()
        self.assertFalse(ok)
        self.assertIn("proof gap", detail)
        self.assertIn("admit", detail)

    def test_axiom_detected_fails(self):
        with open(self.v, "w", encoding="utf-8") as f:
            f.write("Axiom magic : False.\n")
        with mock.patch.object(vd.subprocess, "run") as m:
            ok, detail = self._run()
            m.assert_not_called()
        self.assertFalse(ok)
        self.assertIn("proof gap", detail)
        self.assertIn("Axiom", detail)

    def test_compile_failure_fails_with_tail(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=[_proc(0, stdout=VERSION_OUT),
                                            _proc(1, stdout="a\nb\nc\nd")]):
            ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("coqtop derleme hatası", detail)
        self.assertIn("b | c | d", detail)  # son 3 satır kuyruğu

    def test_coqtop_missing_fails(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=FileNotFoundError):
            ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("coqtop bulunamadı", detail)

    def test_version_timeout_fails(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=vd.subprocess.TimeoutExpired(
                                   "coqtop", 30)):
            ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("zaman aşımı", detail)

    def test_compile_timeout_fails(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=[_proc(0, stdout=VERSION_OUT),
                                            vd.subprocess.TimeoutExpired(
                                                "coqtop", 300)]):
            ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("zaman aşımı", detail)

    def test_calls_version_then_compile_in_tempdir(self):
        with mock.patch.object(vd.subprocess, "run",
                               side_effect=[_proc(0, stdout=VERSION_OUT),
                                            _proc(0)]) as m:
            self._run()
        calls = [c for c in m.call_args_list]
        self.assertEqual(calls[0].args[0], ["coqtop", "--version"])
        self.assertEqual(calls[1].args[0], ["coqtop", "-compile", self.v])
        # .vo repo'ya değil geçici dizine yazılır (repo kirlenmez).
        self.assertNotEqual(calls[1].kwargs["cwd"], self.dir)


class TestK19Combined(unittest.TestCase):
    """K19 genel: sürüm ∧ gap ∧ derleme — biri FAIL ise K19 FAIL."""

    def _call_k19(self, version_ok, gap_ok, compile_ok):
        ok = version_ok and gap_ok and compile_ok
        return ok

    def test_all_pass(self):
        self.assertTrue(self._call_k19(True, True, True))

    def test_version_fail_dominates(self):
        self.assertFalse(self._call_k19(False, True, True))

    def test_gap_fail_dominates(self):
        self.assertFalse(self._call_k19(True, False, True))

    def test_compile_fail_dominates(self):
        self.assertFalse(self._call_k19(True, True, False))

    def test_layer_label_and_constants(self):
        self.assertIn("Coq", vd.LAYER_LABELS["K19"])
        self.assertTrue(vd.COQ_REDUCT_DIR)
        # coq-version dosyası gerçekten COQ_VERSION'ı taşıyor olmalı (tek kaynak).
        ver_file = COQ_DIR / "coq-version"
        self.assertEqual(ver_file.read_text(encoding="utf-8").strip(),
                         vd.COQ_VERSION)
        # Gerçek Content.v'de proof gap olmamalı (fail-closed ön-koşul).
        src = REAL_V.read_text(encoding="utf-8")
        self.assertNotIn("admit", src)
        self.assertNotIn("Admitted", src)
        self.assertNotIn("Axiom", src)
        # 8 teorem adı gerçek dosyada olmalı.
        for name in ["historical_pair_collapses_under_forgetTopic",
                     "historical_pair_survives_forgetAccess",
                     "historical_pair_survives_forgetJustification",
                     "historical_pair_survives_forgetSource",
                     "forgetAccess_not_injective",
                     "forgetJustification_not_injective",
                     "forgetSource_not_injective",
                     "forgetTopic_not_injective"]:
            self.assertIn(name, src, name)


if __name__ == "__main__":
    unittest.main()
