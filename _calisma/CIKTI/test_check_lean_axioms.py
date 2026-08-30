#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_lean_axioms.py — K9 sorry/axiom ön-kapısı birim testleri.

Kapı sözleşmesi (fail-closed):
  * Her .lean kaynağında \\bsorry\\b + top-level axiom aranır.
  * Yorumlar (-- / /- -/) ve string literal'lerdeki kelimeler bulgu DEĞİLDİR.
  * axiom yalnızca satır başında (top-level bildirim) sayılır.
  * scan_lean_dir → (ok, findings); bulgu varsa ok=False.
  * main() → 0 temiz / 1 bulgu / 2 dizin yok; --exit-0 advisory; --json şema.
  * Aksiyom analizi (sorry_analyzer deseni): parse_axioms_output / classify_
    axioms saf fonksiyonlar; analyze_axioms lean yoksa SKIP; main --analyze-
    axioms JSON'a axiom_state/axiom_detail ekler.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_lean_axioms as cla  # noqa: E402

CLEAN = """\
import Mathlib

theorem identity (a : Nat) : a = a := by
  rfl

namespace Foo
  theorem comm (a b : Nat) : a + b = b + a := by
    omega
end Foo
"""


def write_lean(tmp, name, content):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


class TestStripCommentsAndStrings(unittest.TestCase):
    def test_line_comment_removed(self):
        lines = cla.strip_comments_and_strings("theorem t : True := by\n  trivial -- sorry burada\n")
        self.assertNotIn("sorry", lines[1])

    def test_block_comment_removed_single_line(self):
        txt = "theorem t : True := by\n  trivial /- sorry gizli -/\n"
        lines = cla.strip_comments_and_strings(txt)
        self.assertNotIn("sorry", lines[1])

    def test_block_comment_removed_multiline(self):
        txt = "theorem t : True := by\n  /- satır 1\n     sorry satır 2\n  -/ trivial\n"
        lines = cla.strip_comments_and_strings(txt)
        self.assertNotIn("sorry", lines[1])
        self.assertNotIn("sorry", lines[2])
        self.assertIn("trivial", lines[3])

    def test_string_literal_masked(self):
        txt = 'theorem t : True := by\n  have h : String := "sorry degil"\n  trivial\n'
        lines = cla.strip_comments_and_strings(txt)
        self.assertNotIn("sorry", lines[1])

    def test_axiom_in_comment_not_matched(self):
        # Blok yorum içindeki "axiom" bulgu değildir.
        txt = "theorem t : True := by\n  /- axiom burada geçer ama yorum -/\n  trivial\n"
        lines = cla.strip_comments_and_strings(txt)
        self.assertFalse(cla._AXIOM_RE.match(lines[1]))

    def test_line_numbers_preserved(self):
        lines = cla.strip_comments_and_strings("a\nb\nc")
        self.assertEqual(len(lines), 3)


class TestScanLeanDir(unittest.TestCase):
    def test_clean_dir_pass(self):
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean", CLEAN)
            ok, findings = cla.scan_lean_dir(tmp)
            self.assertTrue(ok)
            self.assertEqual(findings, [])

    def test_admit_found(self):
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "B.lean", "theorem t : False := by\n  admit\n")
            ok, findings = cla.scan_lean_dir(tmp)
            self.assertFalse(ok)
            self.assertEqual(findings[0]["kind"], "sorry")
            self.assertEqual(findings[0]["line"], 2)

    def test_unsafe_declaration_found(self):
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "Unsafe.lean", "unsafe def dangerous : Nat := 0\n")
            ok, findings = cla.scan_lean_dir(tmp)
            self.assertFalse(ok)
            self.assertEqual(findings[0]["kind"], "unsafe")
            self.assertEqual(findings[0]["line"], 1)

    def test_unsafe_in_comment_not_matched(self):
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean", "-- unsafe def example : Nat := 0\n" + CLEAN)
            ok, findings = cla.scan_lean_dir(tmp)
            self.assertTrue(ok, findings)

    def test_sorry_found(self):
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean", CLEAN)
            write_lean(tmp, "B.lean",
                       "theorem t : False := by\n  sorry\n")
            ok, findings = cla.scan_lean_dir(tmp)
            self.assertFalse(ok)
            self.assertEqual(len(findings), 1)
            f = findings[0]
            self.assertEqual(f["kind"], "sorry")
            self.assertEqual(f["file"], "B.lean")
            self.assertEqual(f["line"], 2)

    def test_axiom_top_level_found(self):
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean",
                       "axiom choice : (x : Nat) -> Nat\n")
            ok, findings = cla.scan_lean_dir(tmp)
            self.assertFalse(ok)
            self.assertEqual(findings[0]["kind"], "axiom")
            self.assertEqual(findings[0]["line"], 1)

    def test_axiom_indented_still_top_level(self):
        # namespace bloğu içindeki axiom da top-level bildirimdir (satır başı).
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean",
                       "namespace Foo\n  axiom f : Nat\nend Foo\n")
            ok, findings = cla.scan_lean_dir(tmp)
            self.assertFalse(ok)
            self.assertEqual(findings[0]["kind"], "axiom")

    def test_axiom_word_in_body_not_matched(self):
        # `theorem ... := by` gövdesinde "axiom" kelimesi satır başında değilse
        # (ör. bir tanımlayıcı) bulgu DEĞİLDİR.
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean",
                       "theorem t (axiom_name : Nat) : axiom_name = axiom_name := by\n  rfl\n")
            ok, findings = cla.scan_lean_dir(tmp)
            self.assertTrue(ok, findings)

    def test_lake_dir_excluded(self):
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            os.makedirs(os.path.join(tmp, ".lake"))
            write_lean(os.path.join(tmp, ".lake"), "build.lean", "sorry\n")
            write_lean(tmp, "A.lean", CLEAN)
            ok, findings = cla.scan_lean_dir(tmp)
            self.assertTrue(ok)

    def test_missing_dir_ok_false(self):
        ok, findings = cla.scan_lean_dir("/nonexistent/xyz")
        self.assertFalse(ok)
        self.assertEqual(findings, [])


class TestMain(unittest.TestCase):
    def _run(self, tmp, *args):
        return subprocess.run(
            [sys.executable, os.path.join(HERE, "check_lean_axioms.py"),
             "--lean-dir", tmp, *args],
            capture_output=True, text=True, timeout=60)

    def test_clean_exit_0(self):
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean", CLEAN)
            r = self._run(tmp)
            self.assertEqual(r.returncode, 0)
            self.assertIn("temiz", r.stdout)

    def test_sorry_exit_1(self):
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean", "theorem t : False := by\n  sorry\n")
            r = self._run(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("SORRY", r.stdout)

    def test_exit_0_flag_advisory(self):
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean", "theorem t : False := by\n  sorry\n")
            r = self._run(tmp, "--exit-0")
            self.assertEqual(r.returncode, 0)

    def test_json_shape(self):
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean", CLEAN)
            write_lean(tmp, "B.lean", "axiom f : Nat\n")
            r = self._run(tmp, "--json")
            self.assertEqual(r.returncode, 1)
            d = json.loads(r.stdout)
            self.assertFalse(d["ok"])
            self.assertEqual(len(d["findings"]), 1)
            self.assertEqual(d["findings"][0]["kind"], "axiom")
            self.assertEqual(d["findings"][0]["file"], "B.lean")

    def test_missing_dir_exit_2(self):
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "check_lean_axioms.py"),
             "--lean-dir", "/nonexistent/xyz"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)


class TestK9Wiring(unittest.TestCase):
    def test_verify_workflow_has_fail_closed_axiom_step(self):
        workflow = os.path.normpath(os.path.join(HERE, "..", "..", ".github", "workflows", "verify.yml"))
        with open(workflow, encoding="utf-8") as f:
            text = f.read()
        start = text.index("name: Check Lean sorry and axioms (K9)")
        block = text[start:text.index("      # `pipefail`", start)]
        self.assertIn("check_lean_axioms.py", block)
        self.assertIn("--lean-dir _calisma/lean_reduct", block)
        self.assertIn("--json", block)
        self.assertIn("set -euo pipefail", block)


    """verify_delivery K9 bloğu: --lean-proof'ta tarama koşar; bulgu P0."""

    def test_verify_delivery_imports_scanner(self):
        sys.path.insert(0, HERE)
        import verify_delivery as vd
        self.assertTrue(hasattr(vd, "_scan_lean_dir"))
        # Tarama gerçek lean_reduct'ta temiz olmalı (kapı mevcut kodu PASS'ler).
        ok, findings = vd._scan_lean_dir(vd._HERE and os.path.join(
            vd._HERE, "..", "lean_reduct"))
        self.assertTrue(ok, findings)

    def test_klayers_k9_fail_on_axiom_finding(self):
        """K9-AXIOM P0 bulgusu → K9 FAIL (fail-closed)."""
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
            verify_manifest=None,
        )
        findings = [{"priority": "P0", "id": "K9-AXIOM",
                     "check": "K9 Lean sorry/axiom kapısı",
                     "message": "sorry/axiom: A.lean:2 (sorry)",
                     "detail": "sorry/axiom: A.lean:2 (sorry) — sorry"}]
        layers = vd.build_layers_summary(ns, findings)
        self.assertEqual(layers["K9"]["status"], "FAIL")

    def test_scan_lean_dir_findings_shape(self):
        """findings sözleşmesi: {file, line, kind, snippet} — K9 detail'i."""
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "X.lean", "theorem t : False := by\n  sorry\n")
            ok, findings = cla.scan_lean_dir(tmp)
            self.assertFalse(ok)
            f = findings[0]
            self.assertEqual(set(f), {"file", "line", "kind", "snippet"})


class TestAxiomAnalysis(unittest.TestCase):
    """Aksiyom analizi (sorry_analyzer deseni): #print axioms ayrıştırma."""

    def test_parse_axioms_output_none(self):
        out = "'foo' does not depend on any axioms\n"
        self.assertEqual(cla.parse_axioms_output(out), {"foo": []})

    def test_parse_axioms_output_depends(self):
        out = "'bar' depends on axioms: [propext, Classical.choice]\n"
        self.assertEqual(cla.parse_axioms_output(out),
                         {"bar": ["propext", "Classical.choice"]})

    def test_parse_axioms_output_mixed(self):
        out = ("'a' does not depend on any axioms\n"
               "'b' depends on axioms: [Quot.sound]\n")
        deps = cla.parse_axioms_output(out)
        self.assertEqual(deps["a"], [])
        self.assertEqual(deps["b"], ["Quot.sound"])

    def test_classify_standard_only(self):
        deps = {"t": ["propext", "funext", "Classical.choice", "Quot.sound"]}
        ok, non = cla.classify_axioms(deps)
        self.assertTrue(ok)
        self.assertEqual(non, [])

    def test_classify_non_standard(self):
        deps = {"t": ["propext", "my_axiom"]}
        ok, non = cla.classify_axioms(deps)
        self.assertFalse(ok)
        self.assertEqual(non, [{"theorem": "t", "axioms": ["my_axiom"]}])

    def test_analyze_axioms_skip_without_lean(self):
        # lean yoksa SKIP (nötr) — statik sorry/axiom kapısı zaten koştu.
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean", CLEAN)
            with mock.patch.object(cla.shutil, "which", return_value=None):
                state, detail = cla.analyze_axioms(tmp, "lean")
        self.assertEqual(state, "SKIP")
        self.assertIn("atlandı", detail)

    def test_analyze_axioms_pass_via_mock_subprocess(self):
        # lean çalışır + yalnızca standart aksiyomlar → PASS.
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean",
                       "theorem t : True := by\n  trivial\n")
            proc = mock.Mock()
            proc.returncode = 0
            proc.stdout = "'t' does not depend on any axioms\n"
            proc.stderr = ""
            with mock.patch.object(cla.subprocess, "run",
                                   return_value=proc) as m:
                state, detail = cla.analyze_axioms(tmp, "lean")
        self.assertEqual(state, "PASS")
        self.assertIn("standart aksiyomlar dışında aksiyom yok", detail)
        # probe kaynağa #print axioms ekler — dosyaya dokunmaz (stdin).
        # subprocess.run([lean, "-"], input=probe, ...) — input kwargs'ta.
        probe = m.call_args.kwargs.get("input", "")
        self.assertIn("#print axioms t", probe)

    def test_analyze_axioms_fail_non_standard(self):
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean",
                       "theorem t : True := by\n  trivial\n")
            proc = mock.Mock()
            proc.returncode = 0
            proc.stdout = "'t' depends on axioms: [my_axiom]\n"
            proc.stderr = ""
            with mock.patch.object(cla.subprocess, "run",
                                   return_value=proc):
                state, detail = cla.analyze_axioms(tmp, "lean")
        self.assertEqual(state, "FAIL")
        self.assertIn("my_axiom", detail)

    def test_main_analyze_axioms_json_shape(self):
        # --analyze-axioms --json: JSON'da axiom_state + axiom_detail olmalı.
        import argparse
        with tempfile.TemporaryDirectory(prefix="lean-ax-") as tmp:
            write_lean(tmp, "A.lean", CLEAN)
            proc = mock.Mock()
            proc.returncode = 0
            proc.stdout = "'identity' does not depend on any axioms\n"
            proc.stderr = ""
            with mock.patch.object(cla.shutil, "which", return_value="lean"), \
                 mock.patch.object(cla.subprocess, "run", return_value=proc), \
                 mock.patch("sys.stdout") as m_out, \
                 mock.patch.object(sys, "argv",
                                   ["check_lean_axioms.py", "--lean-dir", tmp,
                                    "--analyze-axioms", "--json"]):
                rc = cla.main()
            self.assertEqual(rc, 0)
            call_args = m_out.write.call_args_list
            payload = "".join(c.args[0] for c in call_args)
            d = json.loads(payload)
            self.assertTrue(d["ok"])
            self.assertEqual(d["axiom_state"], "PASS")
            self.assertIn("standart aksiyomlar dışında aksiyom yok",
                          d["axiom_detail"])


if __name__ == "__main__":
    unittest.main()
