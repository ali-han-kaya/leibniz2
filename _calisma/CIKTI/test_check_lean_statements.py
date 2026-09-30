#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_lean_statements.py — fail-closed LaTeX↔Lean gate tests.

The contract is inventory-driven: these tests use two declarations (not the
repository's historical eight) and separately pin the real repository pair.
MAP.md is intentionally absent from the API and is only a legacy Z3 map.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_lean_statements as cls  # noqa: E402


LATEX = r"""
\documentclass{article}
\usepackage{amsmath,amssymb,amsthm}
\newenvironment{leanstatement}
  {\par\noindent\ttfamily\begin{minipage}{0.94\linewidth}}
  {\end{minipage}\par}
\begin{document}
\begin{theorem}
\label{lean:theorem_a}
\begin{leanstatement}
\( \mathsf{A} = \mathsf{B} \)
\end{leanstatement}
\end{theorem}
\begin{lemma}
\label{lean:theorem_b}
\begin{leanstatement}
\(\lnot\,\mathsf{Injective}\,\mathsf{f}\)
\end{leanstatement}
\end{lemma}
\end{document}
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
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


class TestExtractSignatures(unittest.TestCase):
    def test_single_line(self):
        signatures = cls.extract_signatures("theorem foo : a = b := by\n  rfl\n")
        self.assertEqual(signatures, {"foo": "a = b"})

    def test_multiline_and_comments(self):
        text = ("theorem foo :\n    a =\n    b := by\n  rfl\n"
                "-- theorem ignored : x = y\n")
        self.assertEqual(cls.extract_signatures(text), {"foo": "a = b"})

    def test_string_contents_and_assignment_are_respected(self):
        text = 'theorem foo : String = "a -- b := c" := by\n  rfl\n'
        self.assertEqual(cls.extract_signatures(text),
                         {"foo": 'String = "a -- b := c"'})

    def test_duplicate_declaration_is_diagnostic(self):
        findings = []
        text = "theorem foo : A := by\n  rfl\ntheorem foo : B := by\n  rfl\n"
        self.assertEqual(cls.extract_signatures(text, findings), {"foo": "A"})
        self.assertEqual([item["kind"] for item in findings],
                         ["duplicate_theorem"])

    def test_real_inventory_is_not_frozen_to_eight(self):
        root = Path(HERE).parent / "lean_reduct"
        lean = cls.extract_signatures((root / "Content.lean").read_text(
            encoding="utf-8"))
        contract, findings = cls.parse_latex_statements(
            (root / "Content.lean.tex").read_text(encoding="utf-8"))
        self.assertEqual(findings, [])
        self.assertEqual(set(lean), set(contract))
        self.assertGreater(len(contract), 0)
        self.assertIn("forgetTopic_not_injective", contract)
        self.assertEqual(contract["forgetTopic_not_injective"],
                         "¬ Injective forgetTopic")


class TestParseLatex(unittest.TestCase):
    def test_parses_formal_environments_and_translates_math(self):
        contract, findings = cls.parse_latex_statements(LATEX)
        self.assertEqual(findings, [])
        self.assertEqual(contract, {
            "theorem_a": "A = B",
            "theorem_b": "¬ Injective f",
        })

    def test_comments_do_not_hide_or_invent_a_contract(self):
        text = "% \\begin{theorem}\\label{lean:hidden}\\end{theorem}\n" + LATEX
        contract, findings = cls.parse_latex_statements(text)
        self.assertEqual(findings, [])
        self.assertEqual(set(contract), {"theorem_a", "theorem_b"})

    def test_missing_contract_is_fail_closed(self):
        contract, findings = cls.parse_latex_statements(
            "\\documentclass{article}\\begin{document}\\end{document}\n")
        self.assertEqual(contract, {})
        self.assertEqual([item["kind"] for item in findings],
                         ["contract_missing"])

    def test_unbalanced_environment_is_fail_closed(self):
        text = LATEX.replace("\\end{theorem}\n\\begin{lemma}",
                              "\\begin{lemma}", 1)
        contract, findings = cls.parse_latex_statements(text)
        self.assertEqual(contract, {})
        self.assertEqual(findings[0]["kind"], "latex_syntax")

    def test_duplicate_label_is_rejected(self):
        text = LATEX.replace("\\label{lean:theorem_b}",
                              "\\label{lean:theorem_a}")
        contract, findings = cls.parse_latex_statements(text)
        self.assertNotIn("theorem_a", contract)
        self.assertIn("duplicate_label", [item["kind"] for item in findings])

    def test_unbound_label_is_rejected(self):
        text = LATEX.replace("\\begin{document}",
                            "\\begin{document}\\label{lean:outside}", 1)
        contract, findings = cls.parse_latex_statements(text)
        self.assertEqual(set(contract), {"theorem_a", "theorem_b"})
        self.assertIn("unbound_label", [item["kind"] for item in findings])

    def test_missing_and_duplicate_statements_are_rejected(self):
        missing = LATEX.replace(
            "\\begin{leanstatement}\n\\( \\mathsf{A} = \\mathsf{B} \\)\n"
            "\\end{leanstatement}\n", "", 1)
        _, findings = cls.parse_latex_statements(missing)
        self.assertIn("statement_missing", [item["kind"] for item in findings])

        duplicate = LATEX.replace(
            "\\end{leanstatement}\n\\end{theorem}\n\\begin{lemma}",
            "\\end{leanstatement}\n\\begin{leanstatement}\\(A = B\\)"
            "\\end{leanstatement}\n\\end{theorem}\n\\begin{lemma}", 1)
        _, findings = cls.parse_latex_statements(duplicate)
        self.assertIn("statement_duplicate", [item["kind"] for item in findings])

    def test_unknown_latex_command_is_not_silently_dropped(self):
        text = LATEX.replace("\\mathsf{A}", "\\unknown{A}", 1)
        _, findings = cls.parse_latex_statements(text)
        self.assertIn("statement_syntax", [item["kind"] for item in findings])

    def test_unbound_statement_is_rejected(self):
        text = LATEX.replace("\\begin{theorem}",
                             "\\begin{leanstatement}\\(A = B\\)"
                             "\\end{leanstatement}\\begin{theorem}", 1)
        _, findings = cls.parse_latex_statements(text)
        self.assertIn("unbound_statement", [item["kind"] for item in findings])


class TestCheckStatements(unittest.TestCase):
    def _check(self, lean_text, latex_text):
        with tempfile.TemporaryDirectory(prefix="stmt-") as tmp:
            lean_file = write(tmp, "Content.lean", lean_text)
            latex_file = write(tmp, "Content.lean.tex", latex_text)
            return cls.check_statements(lean_file, latex_file)

    def test_match(self):
        ok, findings = self._check(LEAN, LATEX)
        self.assertTrue(ok, findings)
        self.assertEqual(findings, [])

    def test_changed_expression(self):
        ok, findings = self._check(LEAN.replace("A = B", "A = C"), LATEX)
        self.assertFalse(ok)
        self.assertEqual(findings[0]["kind"], "changed")
        self.assertEqual(findings[0]["name"], "theorem_a")

    def test_missing_and_extra_are_bidirectional(self):
        lean = LEAN.replace("theorem theorem_b", "theorem theorem_c")
        ok, findings = self._check(lean, LATEX)
        self.assertFalse(ok)
        kinds = {item["kind"] for item in findings}
        self.assertEqual(kinds, {"missing", "extra"})

    def test_latex_syntax_prevents_pass(self):
        ok, findings = self._check(LEAN, LATEX.replace(
            "\\mathsf{A}", "\\notACommand{A}", 1))
        self.assertFalse(ok)
        self.assertIn("statement_syntax", [item["kind"] for item in findings])

    def test_map_is_not_a_statement_source(self):
        # A stale/contradictory MAP cannot affect this API: no map path exists.
        with tempfile.TemporaryDirectory(prefix="stmt-") as tmp:
            lean_file = write(tmp, "Content.lean", LEAN)
            latex_file = write(tmp, "Content.lean.tex", LATEX)
            write(tmp, "MAP.md", "## STATEMENT CONTRACT\ntheorem_b : nonsense\n")
            ok, findings = cls.check_statements(lean_file, latex_file)
        self.assertTrue(ok, findings)


class TestMain(unittest.TestCase):
    def _run(self, tmp, *args):
        return subprocess.run(
            [sys.executable, os.path.join(HERE, "check_lean_statements.py"),
             "--lean-file", os.path.join(tmp, "Content.lean"),
             "--latex-file", os.path.join(tmp, "Content.lean.tex"), *args],
            capture_output=True, text=True, timeout=60)

    def test_match_exit_0(self):
        with tempfile.TemporaryDirectory(prefix="stmt-") as tmp:
            write(tmp, "Content.lean", LEAN)
            write(tmp, "Content.lean.tex", LATEX)
            result = self._run(tmp)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("uyumlu", result.stdout)
        self.assertNotIn("8 teorem", result.stdout)

    def test_drift_exit_1_and_json_shape(self):
        with tempfile.TemporaryDirectory(prefix="stmt-") as tmp:
            write(tmp, "Content.lean", LEAN.replace("A = B", "A = C"))
            write(tmp, "Content.lean.tex", LATEX)
            result = self._run(tmp, "--json")
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["kind"], "changed")
        self.assertIsNone(report["map_file"])
        self.assertIn("latex_file", report)

    def test_exit_0_flag(self):
        with tempfile.TemporaryDirectory(prefix="stmt-") as tmp:
            write(tmp, "Content.lean", LEAN.replace("A = B", "A = C"))
            write(tmp, "Content.lean.tex", LATEX)
            result = self._run(tmp, "--exit-0")
        self.assertEqual(result.returncode, 0)

    def test_missing_source_exit_2(self):
        with tempfile.TemporaryDirectory(prefix="stmt-") as tmp:
            result = self._run(tmp)
        self.assertEqual(result.returncode, 2)


class TestK9Wiring(unittest.TestCase):
    def test_real_latex_pair_passes(self):
        import verify_delivery as vd
        root = Path(HERE).parent / "lean_reduct"
        ok, findings = vd._check_statements(
            str(root / "Content.lean"), str(root / "Content.lean.tex"))
        self.assertTrue(ok, findings)

    def test_verify_delivery_k9_calls_statement_gate(self):
        import verify_delivery as vd
        source = Path(vd.__file__).read_text(encoding="utf-8")
        start = source.index("    if args.lean_proof:", source.index("# ---- K9:"))
        end = source.index("    # ---- K19:", start)
        k9 = source[start:end]
        self.assertIn("_check_statements(", k9)
        self.assertIn("Content.lean.tex", k9)
        self.assertIn("K9-STMNT", k9)
        self.assertIn("statement_ok and proof_ok", k9)

    def test_workflow_runs_statement_gate_before_lake(self):
        workflow = (Path(HERE).parent.parent / ".github" / "workflows" /
                    "verify.yml").read_text(encoding="utf-8")
        start = workflow.index("  lake-proof:")
        end = workflow.index("\n  action-runtimes:", start)
        block = workflow[start:end]
        self.assertIn("name: Check Lean LaTeX statement contract (K9)", block)
        self.assertIn("check_lean_statements.py", block)
        self.assertIn("--latex-file _calisma/lean_reduct/Content.lean.tex", block)
        # Niyet aynı, ifade değişti: lake build artık inline `lake build
        # --wfail` değil, tek kaynaklı wrapper script'i (verify_lean_lake.sh)
        # üzerinden koşuyor. Sıralama iddiası script'e, fail-closed'lik
        # (--wfail) de script'in içine sabitleniyor.
        wrapper = (Path(HERE) / "verify_lean_lake.sh").read_text(encoding="utf-8")
        self.assertIn("lake build --wfail", wrapper)
        self.assertLess(block.index("check_lean_statements.py"),
                        block.index("verify_lean_lake.sh"))

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
                     "check": "K9 LaTeX statement gate",
                     "message": "statement drift", "detail": "statement drift"}]
        layers = vd.build_layers_summary(ns, findings)
        self.assertEqual(layers["K9"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
