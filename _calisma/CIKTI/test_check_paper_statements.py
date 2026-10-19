#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_paper_statements.py — fail-closed canonical kâğıt statement tests.

The gate binds the canonical paper's six real proposition/lemma statements to
the SAME fail-closed parser machinery as the K9 gate (shared
``check_lean_statements`` primitives) plus the frozen ``CANONICAL_LABELS``
inventory.  Every structural rule and both inventory directions are pinned by
mutating fixtures, and the real committed ``core_section.tex`` is exercised
directly.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_paper_statements as cps  # noqa: E402
import check_lean_statements as k9  # noqa: E402


def _env(kind, label, body):
    return f"\\begin{{{kind}}}\n{label}\n{body}\n\\end{{{kind}}}"


# Frozen inventory fixture: the six real labels with compact statement bodies.
PAPER_OK = "\n".join([
    "\\documentclass{article}",
    "\\begin{document}",
    _env("proposition", "\\label{prop:strength}",
         "Let $M_0$ hold. Then $T_2\\land M_0 \\models T_1$."),
    _env("proposition", "\\label{prop:bridge-collapse}",
         "Over $M_0$, $T_1\\land B_0 \\models T_2$."),
    _env("lemma", "\\label{lem:reduct-invariance}",
         "For every $L_0$-sentence $\\varphi$ the reducts agree."),
    _env("proposition", "\\label{prop:underdet}",
         "There exist admissible structures with identical reducts."),
    _env("proposition", "\\label{prop:definability}",
         "There is no $L_0$-formula $\\theta(b,c)$ defining $G$."),
    _env("proposition", "\\label{prop:stability}",
         "No $L_0$-theory separates the two grounding readings."),
    "\\end{document}",
])


def write(tmp, name, content):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


class FrozenInventoryContract(unittest.TestCase):
    def test_canonical_labels_are_sorted_unique_and_wellformed(self):
        labels = list(cps.CANONICAL_LABELS)
        self.assertEqual(labels, sorted(labels))
        self.assertEqual(len(labels), len(set(labels)))
        for value in labels:
            prefix, sep, name = value.partition(":")
            self.assertTrue(sep, value)
            self.assertIn(prefix, ("prop", "lem"))
            self.assertRegex(name, cps.LABEL_NAME_RE)

    def test_paper_lemmas_lean_counterpart_is_documented(self):
        # The six paper statements are formalized on the ReductInvariance side
        # (not in the K9 Content.lean.tex pair, which covers forget*/historical
        # pair statements).  Pin the documented counterpart so the two
        # inventories cannot silently drift apart in name only.
        reduct = os.path.normpath(os.path.join(
            HERE, "..", "lean_reduct", "ReductInvariance.lean"))
        with open(reduct, encoding="utf-8") as handle:
            lean_src = handle.read()
        self.assertIn("theorem reduct_invariance", lean_src)
        report = os.path.normpath(os.path.join(
            HERE, "..", "lean_reduct", "LEAN_ISPAT_RAPORU.md"))
        with open(report, encoding="utf-8") as handle:
            self.assertIn("lem:reduct-invariance", handle.read())


class SharedParserMachinery(unittest.TestCase):
    def test_gate_imports_k9_primitives_by_identity(self):
        self.assertIs(cps._k9._strip_latex_comments,
                      k9._strip_latex_comments)
        self.assertIs(cps._k9._scan_latex_environments,
                      k9._scan_latex_environments)
        self.assertIs(cps._k9._parse_labels, k9._parse_labels)
        self.assertIs(cps._k9.FORMAL_ENVS, k9.FORMAL_ENVS)

    def test_same_scanner_failure_on_unbalanced_environment(self):
        broken = "\\begin{document}\\begin{proposition}\n\\label{prop:strength}\nX\n"
        _contract, paper_findings = cps.parse_paper_statements(broken)
        _k9contract, k9_findings = k9.parse_latex_statements(broken)
        self.assertTrue(any(f["kind"] == "latex_syntax"
                            for f in paper_findings))
        self.assertTrue(any(f["kind"] == "latex_syntax"
                            for f in k9_findings))


class StructureRules(unittest.TestCase):
    def test_valid_six_env_fixture_passes(self):
        contract, findings = cps.parse_paper_statements(PAPER_OK)
        self.assertEqual(findings, [])
        self.assertEqual(set(contract), set(cps.CANONICAL_LABELS))

    def test_label_missing_fails(self):
        doc = PAPER_OK.replace("\\label{prop:stability}\n", "")
        contract, findings = cps.parse_paper_statements(doc)
        self.assertTrue(any(f["kind"] == "label_missing" for f in findings))
        self.assertNotIn("prop:stability", contract)

    def test_empty_statement_body_fails(self):
        doc = PAPER_OK.replace(
            "No $L_0$-theory separates the two grounding readings.", "")
        _contract, findings = cps.parse_paper_statements(doc)
        self.assertTrue(any(f["kind"] == "statement_missing"
                            and f.get("name") == "prop:stability"
                            for f in findings))

    def test_nested_formal_environment_fails(self):
        doc = "\n".join([
            "\\begin{document}",
            "\\begin{proposition}",
            "\\label{prop:outer}",
            "Outer statement.",
            _env("lemma", "\\label{lem:inner}", "Inner statement."),
            "\\end{proposition}",
            "\\end{document}",
        ])
        _contract, findings = cps.parse_paper_statements(doc)
        self.assertTrue(any(f["kind"] == "latex_syntax"
                            for f in findings))

    def test_duplicate_label_fails(self):
        doc = PAPER_OK.replace(
            "\\label{prop:strength}",
            "\\label{prop:strength}\n\\begin{lemma}\n\\label{prop:strength}\n"
            "Dup.\n\\end{lemma}")
        _contract, findings = cps.parse_paper_statements(doc)
        self.assertTrue(any(f["kind"] == "duplicate_label"
                            and f.get("name") == "prop:strength"
                            for f in findings))

    def test_prefix_mismatch_fails(self):
        doc = PAPER_OK.replace("\\label{lem:reduct-invariance}",
                               "\\label{prop:reduct-invariance}")
        _contract, findings = cps.parse_paper_statements(doc)
        self.assertTrue(any(f["kind"] == "label_prefix"
                            for f in findings))

    def test_stray_label_outside_environment_fails(self):
        doc = PAPER_OK.replace(
            "\\end{document}",
            "\\label{prop:stray}\n\\end{document}")
        _contract, findings = cps.parse_paper_statements(doc)
        self.assertTrue(any(f["kind"] == "unbound_label"
                            and f.get("name") == "prop:stray"
                            for f in findings))

    def test_commented_out_environment_does_not_count(self):
        doc = PAPER_OK.replace(
            "\\begin{proposition}\n\\label{prop:stability}\n"
            "No $L_0$-theory separates the two grounding readings.\n"
            "\\end{proposition}",
            "%\\begin{proposition}\n%\\label{prop:stability}\n"
            "%No $L_0$-theory separates the two grounding readings.\n"
            "%\\end{proposition}")
        with tempfile.TemporaryDirectory() as tmp:
            ok, findings, contract = cps.check_paper(
                write(tmp, "c.tex", doc))
        self.assertFalse(ok)
        self.assertNotIn("prop:stability", contract)
        self.assertTrue(any(f["kind"] == "inventory_missing"
                            and f.get("name") == "prop:stability"
                            for f in findings))

    def test_no_formal_environment_fails_closed(self):
        doc = "\\begin{document}\nNo statements here.\n\\end{document}\n"
        _contract, findings = cps.parse_paper_statements(doc)
        self.assertTrue(any(f["kind"] == "contract_missing"
                            for f in findings))


class FrozenInventoryDirections(unittest.TestCase):
    def test_missing_env_reports_inventory_missing(self):
        doc = PAPER_OK.replace(
            "\\begin{proposition}\n\\label{prop:stability}\n"
            "No $L_0$-theory separates the two grounding readings.\n"
            "\\end{proposition}\n", "")
        ok, findings, contract = cps.check_paper(
            write(tempfile.mkdtemp(), "m.tex", doc))
        self.assertFalse(ok)
        self.assertTrue(any(f["kind"] == "inventory_missing"
                            and f.get("name") == "prop:stability"
                            for f in findings))
        self.assertNotIn("prop:stability", contract)

    def test_extra_env_reports_inventory_extra(self):
        doc = PAPER_OK.replace(
            "\\end{document}",
            _env("proposition", "\\label{prop:extra}",
                 "An envanter dışı statement.")
            + "\\end{document}")
        ok, findings, _contract = cps.check_paper(
            write(tempfile.mkdtemp(), "x.tex", doc))
        self.assertFalse(ok)
        self.assertTrue(any(f["kind"] == "inventory_extra"
                            and f.get("name") == "prop:extra"
                            for f in findings))

    def test_renamed_label_reports_missing_and_extra(self):
        doc = PAPER_OK.replace("prop:stability", "prop:stable")
        ok, findings, _contract = cps.check_paper(
            write(tempfile.mkdtemp(), "r.tex", doc))
        self.assertFalse(ok)
        kinds = {(f["kind"], f.get("name")) for f in findings}
        self.assertIn(("inventory_missing", "prop:stability"), kinds)
        self.assertIn(("inventory_extra", "prop:stable"), kinds)


class SourceFailures(unittest.TestCase):
    def test_missing_file_is_fail_closed(self):
        ok, findings, contract = cps.check_paper(
            os.path.join(tempfile.gettempdir(), "yok-boyle-bir-dosya.tex"))
        self.assertFalse(ok)
        self.assertEqual(contract, {})
        self.assertEqual(findings[0]["kind"], "source_error")

    def test_main_missing_file_exits_2(self):
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, "check_paper_statements.py"),
             "--paper-file", "/nope/missing.tex", "--json"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("HATA", result.stderr)


class LiveCanonicalPaper(unittest.TestCase):
    def test_real_core_section_matches_frozen_inventory(self):
        ok, findings, contract = cps.check_paper(cps.DEFAULT_PAPER)
        self.assertEqual(findings, [], findings)
        self.assertTrue(ok)
        self.assertEqual(set(contract), set(cps.CANONICAL_LABELS))

    def test_main_json_pass_on_real_paper(self):
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, "check_paper_statements.py"),
             "--json"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["labels"], sorted(cps.CANONICAL_LABELS))
        self.assertEqual(payload["findings"], [])

    def test_main_json_fail_on_broken_paper(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "broken.tex", PAPER_OK.replace(
                "\\label{prop:strength}", ""))
            result = subprocess.run(
                [sys.executable,
                 os.path.join(HERE, "check_paper_statements.py"),
                 "--paper-file", path, "--json"],
                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["findings"])


if __name__ == "__main__":
    unittest.main()
