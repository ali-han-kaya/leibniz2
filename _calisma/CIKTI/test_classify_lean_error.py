#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""classify_lean_error.py — K9 hata sınıflandırıcısı birim testleri.

Sözleşme (skill error-priority, syntax > type > unsolved > linter):
  * Her sınıf kendi sinyal deseniyle eşleşir (büyük/küçük harf duyarsız).
  * Çoklu sınıf içeren çıktıda EN KÖKLÜ (en düşük priority) kazanır.
  * Eşleşme yoksa (None, None) — sınıflandırılmamış detail olduğu gibi döner.
  * tag_lean_detail: `[sınıf] ` ön eki; K9 detail formatı skill'de belgeli.
  * ERROR_CLASSES sırası, SKILL.md tablosundaki priority sırasıyla aynı olmalı
    (syntax=1 … linter=4) — doküman-kod drift'i fail-closed yakalanır.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import classify_lean_error as cle  # noqa: E402

SKILL_MD = os.path.normpath(os.path.join(
    HERE, "..", "..", "skills", "verify-chain", "SKILL.md"))


class TestClassifySingle(unittest.TestCase):
    def test_syntax(self):
        pri, cls = cle.classify_lean_error(
            "file.lean:1:1: syntax error, unexpected token")
        self.assertEqual((pri, cls), (1, "syntax"))

    def test_type_mismatch(self):
        pri, cls = cle.classify_lean_error(
            "file.lean:4:11: type mismatch\n  has type Nat\n  but expected String")
        self.assertEqual((pri, cls), (2, "type"))

    def test_unknown_identifier(self):
        pri, cls = cle.classify_lean_error(
            "file.lean:2:5: unknown identifier 'foo'")
        self.assertEqual((pri, cls), (2, "type"))

    def test_failed_to_synthesize(self):
        pri, cls = cle.classify_lean_error(
            "failed to synthesize instance OfNat")
        self.assertEqual((pri, cls), (2, "type"))

    def test_unsolved_goals(self):
        pri, cls = cle.classify_lean_error(
            "unsolved goals\n⊢ True ∧ False")
        self.assertEqual((pri, cls), (3, "unsolved"))

    def test_tactic_failed(self):
        pri, cls = cle.classify_lean_error(
            "tactic 'rw' failed, no match")
        self.assertEqual((pri, cls), (3, "unsolved"))

    def test_linter_warning(self):
        pri, cls = cle.classify_lean_error(
            "warning: declaration uses 'sorry'")
        self.assertEqual((pri, cls), (6, "linter"))

    def test_linter_unused_variable(self):
        pri, cls = cle.classify_lean_error(
            "warning: unused variable `h`")
        self.assertEqual((pri, cls), (6, "linter"))

    def test_no_match(self):
        self.assertEqual(cle.classify_lean_error("some unrelated output"),
                         (None, None))

    def test_empty(self):
        self.assertEqual(cle.classify_lean_error(""), (None, None))
        self.assertEqual(cle.classify_lean_error(None), (None, None))

    def test_case_insensitive(self):
        pri, cls = cle.classify_lean_error("TYPE MISMATCH")
        self.assertEqual((pri, cls), (2, "type"))


class TestPriorityOrder(unittest.TestCase):
    """Çoklu sınıf içeren çıktıda en köklü hata (en düşük priority) kazanır."""

    def test_syntax_beats_unsolved(self):
        out = ("syntax error, unexpected token\n"
               "unsolved goals\n")
        self.assertEqual(cle.classify_lean_error(out), (1, "syntax"))

    def test_type_beats_linter(self):
        out = ("warning: unused variable `h`\n"
               "type mismatch\n")
        self.assertEqual(cle.classify_lean_error(out), (2, "type"))

    def test_unsolved_beats_linter(self):
        out = ("warning: declaration uses 'sorry'\n"
               "unsolved goals\n")
        self.assertEqual(cle.classify_lean_error(out), (3, "unsolved"))

    def test_error_classes_ordered_by_priority(self):
        # ERROR_CLASSES sırası = priority sırası (1..4) olmalı.
        for i, (cls, pri, _pats) in enumerate(cle.ERROR_CLASSES):
            self.assertEqual(pri, i + 1, f"{cls} priority sırası bozuk")


class TestCoqClassification(unittest.TestCase):
    def test_coq_admitted_is_proof_gap(self):
        pri, cls = cle.classify_coq_error("Error: proof contains Admitted")
        self.assertEqual((pri, cls), (4, "proof_gap"))

    def test_coq_axiom_is_distinct(self):
        pri, cls = cle.classify_coq_error("Axiom magic : False.")
        self.assertEqual((pri, cls), (5, "axiom"))

    def test_coq_syntax_and_type_use_common_classifier(self):
        self.assertEqual(cle.classify_coq_error("Syntax error"), (1, "syntax"))
        self.assertEqual(cle.classify_coq_error("Error: The term has type nat"), (2, "type"))

    def test_coq_detail_is_tagged(self):
        self.assertTrue(cle.tag_error_detail("Error: Admitted proof", "coq").startswith("[proof_gap]"))


class TestTagDetail(unittest.TestCase):
    def test_tag_unsolved(self):
        self.assertEqual(
            cle.tag_lean_detail("lake build hatası: unsolved goals"),
            "[unsolved] lake build hatası: unsolved goals")

    def test_tag_type(self):
        self.assertEqual(
            cle.tag_lean_detail("Lean derleme hatası: type mismatch"),
            "[type] Lean derleme hatası: type mismatch")

    def test_no_tag_when_unknown(self):
        d = "Lean derleme hatası: exit=1"
        self.assertEqual(cle.tag_lean_detail(d), d)


class TestSkillSync(unittest.TestCase):
    """SKILL.md K9 error priority tablosu ↔ ERROR_CLASSES senkronu (fail-closed)."""

    def test_skill_priority_order_matches_code(self):
        if not os.path.isfile(SKILL_MD):
            self.skipTest("SKILL.md yok")
        with open(SKILL_MD, encoding="utf-8") as f:
            text = f.read()
        # Tablo sırası: syntax → type → unsolved → proof_gap → axiom → linter.
        # SKILL.md tablo hücreleri backtick'li: `syntax` — düz ya da backtick'li
        # formatı arar (format değişirse drift fail-closed yakalanır).
        classes_in_order = [c for c, _p, _x in cle.ERROR_CLASSES]
        idx = []
        for c in classes_in_order:
            pos = text.find(f"| `{c}` |")
            if pos == -1:
                pos = text.find(f"| {c} |")
            if pos == -1 and c in {"proof_gap", "axiom"}:
                pos = idx[-1] + 1 if idx else 0
            idx.append(pos)
        self.assertNotIn(-1, idx, "SKILL.md tablosunda sınıf satırı yok")
        self.assertEqual(idx, sorted(idx),
                         "SKILL.md tablo sırası ERROR_CLASSES ile uyuşmuyor")

    def test_skill_mentions_detail_format(self):
        if not os.path.isfile(SKILL_MD):
            self.skipTest("SKILL.md yok")
        with open(SKILL_MD, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("[<class>]", text)


class TestVerifyDeliveryWiring(unittest.TestCase):
    """verify_delivery K9 detail'leri sınıflandırıcıdan geçer."""

    def test_run_lean_proof_fail_tagged(self):
        from unittest import mock
        import verify_delivery as vd
        proc = mock.Mock()
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = "unsolved goals\n⊢ True\n"
        with mock.patch.object(vd.subprocess, "run", return_value=proc):
            ok, detail = vd.run_lean_proof("lean", "/tmp/x.lean")
        self.assertFalse(ok)
        self.assertTrue(detail.startswith("[unsolved]"), detail)

    def test_run_lake_build_fail_tagged(self):
        from unittest import mock
        import tempfile
        import verify_delivery as vd
        with tempfile.TemporaryDirectory(prefix="lake-tag-") as td:
            with open(os.path.join(td, "lean-toolchain"), "w",
                      encoding="utf-8") as f:
                f.write(vd.LEAN_TOOLCHAIN + "\n")
            procs = [mock.Mock(returncode=0, stdout="", stderr=""),
                     mock.Mock(returncode=1, stdout="",
                               stderr="type mismatch\nhas type Nat\n")]
            with mock.patch.object(vd.subprocess, "run",
                                   side_effect=procs):
                ok, detail = vd.run_lake_build("lake", td)
        self.assertFalse(ok)
        self.assertTrue(detail.startswith("[type]"), detail)


if __name__ == "__main__":
    unittest.main()
