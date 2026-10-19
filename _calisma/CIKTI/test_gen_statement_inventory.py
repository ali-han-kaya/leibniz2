#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_statement_inventory.py — envanter + drift raporu yayın testleri.

The generator composes both statement gates (K9 + canonical paper) into one
deterministic artifact pair: machine-readable JSON inventory and a
human-readable Markdown drift report.  Drift must surface in BOTH output
formats and in the exit code; a missing source must never publish a partial
("all green") report.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_statement_inventory as gsi  # noqa: E402
import check_paper_statements as cps  # noqa: E402
from test_check_paper_statements import PAPER_OK  # noqa: E402

SCRIPT = os.path.join(HERE, "gen_statement_inventory.py")

# Minimal K9 pair (test_check_lean_statements deseni — iki statement).
K9_LATEX = r"""
\documentclass{article}
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

K9_LEAN = """\
def f (α : Type) : Type := α

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


def sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def run_generator(out_dir, lean, latex, paper):
    return subprocess.run(
        [sys.executable, SCRIPT, "--out-dir", out_dir,
         "--lean-file", lean, "--latex-file", latex, "--paper-file", paper],
        capture_output=True, text=True)


class LiveInventory(unittest.TestCase):
    def test_real_sources_publish_pass_inventory(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--out-dir",
             tempfile.mkdtemp(prefix="si-live-")],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_real_json_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_generator(
                tmp, gsi.k9.DEFAULT_LEAN, gsi.k9.DEFAULT_LATEX,
                cps.DEFAULT_PAPER)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(os.path.join(tmp, gsi.JSON_NAME),
                      encoding="utf-8") as handle:
                payload = json.load(handle)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["verdict"], "PASS")
        self.assertEqual(payload["gate"], "statement-inventory")
        self.assertEqual(
            {e["label"] for e in payload["paper"]["statements"]},
            set(cps.CANONICAL_LABELS))
        self.assertTrue(payload["k9"]["statements"],
                        "K9 envanteri boş olamaz (gerçek repoda)")
        for key in ("lean", "latex", "paper"):
            self.assertIn("sha256", payload["sources"][key])

    def test_real_markdown_names_every_statement(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_generator(tmp, gsi.k9.DEFAULT_LEAN, gsi.k9.DEFAULT_LATEX,
                          cps.DEFAULT_PAPER)
            with open(os.path.join(tmp, gsi.MD_NAME),
                      encoding="utf-8") as handle:
                md = handle.read()
        self.assertIn("PASS", md)
        for label in cps.CANONICAL_LABELS:
            self.assertIn(f"`{label}`", md)
        self.assertIn("`forgetTopic_not_injective`", md)


class Determinism(unittest.TestCase):
    def test_same_sources_produce_byte_identical_reports(self):
        outputs = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                run_generator(tmp, gsi.k9.DEFAULT_LEAN, gsi.k9.DEFAULT_LATEX,
                              cps.DEFAULT_PAPER)
                with open(os.path.join(tmp, gsi.JSON_NAME), "rb") as handle:
                    json_bytes = handle.read()
                with open(os.path.join(tmp, gsi.MD_NAME), "rb") as handle:
                    md_bytes = handle.read()
                outputs.append((json_bytes, md_bytes))
        self.assertEqual(outputs[0], outputs[1],
                         "aynı kaynaklar bayt-bayt aynı rapor üretmeli "
                         "(zaman damgası yasak)")

    def test_json_provenance_matches_source_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_generator(tmp, gsi.k9.DEFAULT_LEAN, gsi.k9.DEFAULT_LATEX,
                          cps.DEFAULT_PAPER)
            with open(os.path.join(tmp, gsi.JSON_NAME),
                      encoding="utf-8") as handle:
                payload = json.load(handle)
        self.assertEqual(payload["sources"]["paper"]["sha256"],
                         sha256(cps.DEFAULT_PAPER))
        self.assertEqual(payload["sources"]["lean"]["sha256"],
                         sha256(gsi.k9.DEFAULT_LEAN))


class DriftSurfaces(unittest.TestCase):
    def _fixture(self, tmp, paper_text=None, latex_text=None):
        lean = write(tmp, "Content.lean", K9_LEAN)
        latex = write(tmp, "Content.lean.tex",
                      latex_text or K9_LATEX)
        paper = write(tmp, "core.tex", paper_text or PAPER_OK)
        return lean, latex, paper

    def test_paper_drift_exits_1_and_reports_in_both_formats(self):
        broken = PAPER_OK.replace(
            "\\begin{proposition}\n\\label{prop:stability}\n"
            "No $L_0$-theory separates the two grounding readings.\n"
            "\\end{proposition}\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            lean, latex, paper = self._fixture(tmp, paper_text=broken)
            result = run_generator(tmp, lean, latex, paper)
            self.assertEqual(result.returncode, 1, result.stdout)
            with open(os.path.join(tmp, gsi.JSON_NAME),
                      encoding="utf-8") as handle:
                payload = json.load(handle)
            with open(os.path.join(tmp, gsi.MD_NAME),
                      encoding="utf-8") as handle:
                md = handle.read()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["verdict"], "DRIFT")
        self.assertTrue(any(f["kind"] == "inventory_missing"
                            and f.get("name") == "prop:stability"
                            for f in payload["paper"]["findings"]))
        pkeys = [(f.get("kind"), f.get("name"), f.get("detail"))
                 for f in payload["paper"]["findings"]]
        self.assertEqual(len(pkeys), len(set(pkeys)),
                         "kâğıt bulguları da tekilleşmiş olmalı")
        self.assertIn("DRIFT", md)
        self.assertIn("INVENTORY_MISSING", md)
        self.assertIn("prop:stability", md)

    def test_k9_drift_exits_1_and_reports_in_both_formats(self):
        broken = K9_LATEX.replace("\\begin{leanstatement}", "%\\begin{leanstatement}")
        with tempfile.TemporaryDirectory() as tmp:
            lean, latex, paper = self._fixture(tmp, latex_text=broken)
            result = run_generator(tmp, lean, latex, paper)
            self.assertEqual(result.returncode, 1, result.stdout)
            with open(os.path.join(tmp, gsi.JSON_NAME),
                      encoding="utf-8") as handle:
                payload = json.load(handle)
            with open(os.path.join(tmp, gsi.MD_NAME),
                      encoding="utf-8") as handle:
                md = handle.read()
        self.assertFalse(payload["k9"]["ok"])
        self.assertTrue(payload["k9"]["findings"],
                        "K9 bulgusu JSON'a yansımalı")
        keys = [(f.get("kind"), f.get("name"), f.get("detail"))
                for f in payload["k9"]["findings"]]
        self.assertEqual(len(keys), len(set(keys)),
                         "JSON bulguları tekilleşmiş olmalı (yinelenen K9 "
                         "bulgusu listeyi şişirir)")
        self.assertIn("DRIFT", md)
        self.assertIn("K9 bulguları", md)


class FailClosedSourceErrors(unittest.TestCase):
    def test_missing_paper_source_exits_2_without_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            lean = write(tmp, "Content.lean", K9_LEAN)
            latex = write(tmp, "Content.lean.tex", K9_LATEX)
            result = run_generator(
                tmp, lean, latex, os.path.join(tmp, "yok.tex"))
            self.assertEqual(result.returncode, 2)
            self.assertIn("HATA", result.stderr)
            self.assertEqual(
                sorted(os.listdir(tmp)),
                ["Content.lean", "Content.lean.tex"],
                "kaynak hatasında rapor dosyası yazılmamalı")

    def test_missing_lean_source_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            latex = write(tmp, "Content.lean.tex", K9_LATEX)
            paper = write(tmp, "core.tex", PAPER_OK)
            result = run_generator(
                tmp, os.path.join(tmp, "yok.lean"), latex, paper)
            self.assertEqual(result.returncode, 2)


class MarkdownRendering(unittest.TestCase):
    def test_table_rows_match_statement_counts(self):
        inventory, error = gsi.collect_inventory(
            gsi.k9.DEFAULT_LEAN, gsi.k9.DEFAULT_LATEX, cps.DEFAULT_PAPER)
        self.assertIsNone(error)
        md = gsi.render_markdown(inventory)
        k9_rows = sum(1 for line in md.splitlines()
                      if line.startswith("| `"))
        self.assertEqual(
            k9_rows,
            len(inventory["k9"]["statements"])
            + len(inventory["paper"]["statements"]),
            "tablo satır sayısı envanter boyutuna eşit olmalı")

    def test_pipes_in_expression_are_escaped(self):
        inventory = {
            "ok": False, "verdict": "DRIFT", "total_findings": 0,
            "sources": {k: {"path": "p", "sha256": "0" * 64}
                        for k in ("lean", "latex", "paper")},
            "k9": {"ok": False, "statements": [{"name": "t_a",
                                                "expression": "A | B"}],
                   "findings": []},
            "paper": {"ok": True, "statements": [], "findings": []},
        }
        md = gsi.render_markdown(inventory)
        self.assertIn("A \\| B", md)


if __name__ == "__main__":
    unittest.main()
