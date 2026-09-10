#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_lean_statements.py — K9 statement-safety kapısı birim testleri.

Sözleşme (fail-closed):
  * Content.lean'daki `theorem NAME :` imzaları (ilk `:=`'e kadar, whitespace
    normalize, yorum atlanarak) MAP.md STATEMENT CONTRACT listesiyle birebir.
  * Eksik teorem (contract'ta var, kodda yok) → drift.
  * Değişmiş imza (kod ≠ contract) → drift.
  * Fazla teorem (kodda var, contract'ta yok) → drift.
  * Contract bölümü yoksa → drift (MAP.md makine-okunur kalmalı).
  * main(): 0 uyumlu / 1 drift / 2 hata; --json şeması; --exit-0 advisory.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_lean_statements as cls  # noqa: E402

CONTRACT = """\
## STATEMENT CONTRACT

theorem_a : A = B
theorem_b : ¬ Injective f
"""

LEAN = """\
import Mathlib

def f (x : Nat) : Nat := x

theorem theorem_a : A = B := by
  rfl

theorem theorem_b : ¬ Injective f := by
  intro h
  sorry
"""


def write(tmp, name, content):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


class TestExtractSignatures(unittest.TestCase):
    def test_single_line(self):
        sigs = cls.extract_signatures("theorem foo : a = b := by\n  rfl\n")
        self.assertEqual(sigs, {"foo": "a = b"})

    def test_multiline_statement(self):
        text = "theorem foo :\n    a =\n    b := by\n  rfl\n"
        sigs = cls.extract_signatures(text)
        self.assertEqual(sigs, {"foo": "a = b"})

    def test_comment_line_ignored(self):
        text = ("-- theorem commented : x = y\n"
                "theorem foo : a = b := by\n  rfl\n")
        sigs = cls.extract_signatures(text)
        self.assertEqual(sigs, {"foo": "a = b"})

    def test_string_with_double_dash_preserved(self):
        # String içindeki `--` yorum değildir (basit maskeleme).
        text = 'theorem foo : String = "a -- b" := by\n  rfl\n'
        sigs = cls.extract_signatures(text)
        self.assertIn("foo", sigs)
        self.assertIn('"a -- b"', sigs["foo"])

    def test_eight_real_theorems(self):
        with open(os.path.join(HERE, "..", "lean_reduct", "Content.lean"),
                  encoding="utf-8") as f:
            sigs = cls.extract_signatures(f.read())
        self.assertEqual(len(sigs), 8)
        self.assertIn("forgetTopic_not_injective", sigs)
        self.assertEqual(sigs["forgetTopic_not_injective"],
                         "¬ Injective forgetTopic")


class TestParseContract(unittest.TestCase):
    def test_parses_names(self):
        c = cls.parse_contract(CONTRACT)
        self.assertEqual(set(c), {"theorem_a", "theorem_b"})
        self.assertEqual(c["theorem_a"], "A = B")

    def test_missing_header_returns_none(self):
        self.assertIsNone(cls.parse_contract("# basit\nZ3: x <-> Lean: y\n"))

    def test_ignores_markdown_tables(self):
        text = CONTRACT + "\n| A | B |\n|---|\n"
        c = cls.parse_contract(text)
        self.assertEqual(set(c), {"theorem_a", "theorem_b"})


class TestCheckStatements(unittest.TestCase):
    def _check(self, lean_text, map_text):
        with tempfile.TemporaryDirectory(prefix="stmt-") as tmp:
            lf = write(tmp, "Content.lean", lean_text)
            mf = write(tmp, "MAP.md", map_text)
            return cls.check_statements(lf, mf)

    def test_match(self):
        ok, findings = self._check(LEAN, CONTRACT)
        self.assertTrue(ok, findings)
        self.assertEqual(findings, [])

    def test_missing_theorem(self):
        lean = LEAN.replace("theorem theorem_b", "theorem theorem_c")
        ok, findings = self._check(lean, CONTRACT)
        self.assertFalse(ok)
        kinds = [f["kind"] for f in findings]
        self.assertIn("missing", kinds)
        self.assertIn("extra", kinds)  # theorem_c sözleşmede yok

    def test_changed_signature(self):
        lean = LEAN.replace("A = B", "A = C")
        ok, findings = self._check(lean, CONTRACT)
        self.assertFalse(ok)
        self.assertEqual(findings[0]["kind"], "changed")
        self.assertEqual(findings[0]["name"], "theorem_a")

    def test_contract_missing(self):
        ok, findings = self._check(LEAN, "# başlık yok\n")
        self.assertFalse(ok)
        self.assertEqual(findings[0]["kind"], "contract_missing")

    def test_whitespace_normalized(self):
        # Contract ve kodda farklı boşluk düzeni → yine de eşleşir.
        lean = "theorem theorem_a :\n   A   =\n   B  := by\n  rfl\n"
        map_t = "## STATEMENT CONTRACT\n\ntheorem_a : A = B\n"
        ok, findings = self._check(lean, map_t)
        self.assertTrue(ok, findings)


class TestMain(unittest.TestCase):
    def _run(self, tmp, *args):
        return subprocess.run(
            [sys.executable, os.path.join(HERE, "check_lean_statements.py"),
             "--lean-file", os.path.join(tmp, "Content.lean"),
             "--map", os.path.join(tmp, "MAP.md"), *args],
            capture_output=True, text=True, timeout=60)

    def test_match_exit_0(self):
        with tempfile.TemporaryDirectory(prefix="stmt-") as tmp:
            write(tmp, "Content.lean", LEAN)
            write(tmp, "MAP.md", CONTRACT)
            r = self._run(tmp)
            self.assertEqual(r.returncode, 0)
            self.assertIn("uyumlu", r.stdout)

    def test_drift_exit_1(self):
        with tempfile.TemporaryDirectory(prefix="stmt-") as tmp:
            write(tmp, "Content.lean", LEAN.replace("A = B", "A = C"))
            write(tmp, "MAP.md", CONTRACT)
            r = self._run(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("CHANGED", r.stdout)

    def test_exit_0_flag(self):
        with tempfile.TemporaryDirectory(prefix="stmt-") as tmp:
            write(tmp, "Content.lean", LEAN.replace("A = B", "A = C"))
            write(tmp, "MAP.md", CONTRACT)
            r = self._run(tmp, "--exit-0")
            self.assertEqual(r.returncode, 0)

    def test_json_shape(self):
        with tempfile.TemporaryDirectory(prefix="stmt-") as tmp:
            write(tmp, "Content.lean", LEAN.replace("A = B", "A = C"))
            write(tmp, "MAP.md", CONTRACT)
            r = self._run(tmp, "--json")
            self.assertEqual(r.returncode, 1)
            d = json.loads(r.stdout)
            self.assertFalse(d["ok"])
            self.assertEqual(d["findings"][0]["kind"], "changed")

    def test_missing_files_exit_2(self):
        with tempfile.TemporaryDirectory(prefix="stmt-") as tmp:
            r = self._run(tmp)
            self.assertEqual(r.returncode, 2)


class TestK9Wiring(unittest.TestCase):
    def test_verify_delivery_imports_statement_check(self):
        import verify_delivery as vd
        self.assertTrue(hasattr(vd, "_check_statements"))
        # Gerçek repo: Content.lean ↔ MAP.md uyumlu olmalı (kapı PASS).
        ok, findings = vd._check_statements(
            os.path.join(HERE, "..", "lean_reduct", "Content.lean"),
            os.path.join(HERE, "..", "lean_reduct", "MAP.md"))
        self.assertTrue(ok, findings)

    def test_klayers_k9_fail_on_statement_finding(self):
        import argparse
        import verify_delivery as vd
        ns = argparse.Namespace(
            full=False, check_history=None,
            check_references=False, symbolic_proof=False, lean_proof=True,
            check_lineage=False, check_repro_manifest=False,
            check_config_drift=False, check_cleanup=False,
            check_github_scripts=False, check_mirror=False,
            mirror_auto_sync=False, check_daemon=False,
            check_plist=False, coq_proof=False, check_launchd=False,
            check_sde=False, verify_manifest=None,
        )
        findings = [{"priority": "P0", "id": "K9-STMNT",
                     "check": "K9 Lean statement-safety",
                     "message": "statement drift: theorem_a (changed)",
                     "detail": "statement drift: theorem_a (changed)"}]
        layers = vd.build_layers_summary(ns, findings)
        self.assertEqual(layers["K9"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
