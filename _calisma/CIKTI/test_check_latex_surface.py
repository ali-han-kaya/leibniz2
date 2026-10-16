#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the fail-closed LaTeX surface gate."""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import check_latex_surface as gate  # noqa: E402


class TestLatexSurface(unittest.TestCase):
    def test_input_graph_resolves_refs_and_ignores_comments(self):
        with tempfile.TemporaryDirectory(prefix="latex-surface-") as td:
            root = pathlib.Path(td)
            (root / "parts").mkdir()
            (root / "main.tex").write_text(
                "\\documentclass{article}\n"
                "\\input{parts/body}\n"
                "% $$ and \\ref{comment-only} are ignored\n",
                encoding="utf-8",
            )
            (root / "parts" / "body.tex").write_text(
                "\\section{Answer}\\label{sec:answer}\n"
                "See \\ref{sec:answer}; 50\\% is literal.\n",
                encoding="utf-8",
            )
            self.assertEqual(gate.scan_surface([root / "main.tex"], root), [])

    def test_active_double_dollar_is_finding(self):
        with tempfile.TemporaryDirectory(prefix="latex-surface-") as td:
            root = pathlib.Path(td)
            source = root / "main.tex"
            source.write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "$$ x = y $$\n"
                "% $$ ignored\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            findings = gate.scan_surface([source], root)
            self.assertEqual([item["kind"] for item in findings], ["double_dollar", "double_dollar"])
            self.assertEqual(findings[0]["line"], 3)
            self.assertEqual(findings[0]["column"], 1)

    def test_missing_ref_is_scoped_to_input_graph(self):
        with tempfile.TemporaryDirectory(prefix="latex-surface-") as td:
            root = pathlib.Path(td)
            main = root / "main.tex"
            unrelated = root / "unrelated.tex"
            main.write_text(
                "\\documentclass{article}\n"
                "\\input{body}\n",
                encoding="utf-8",
            )
            (root / "body.tex").write_text("See \\ref{fig:missing}.\n", encoding="utf-8")
            unrelated.write_text(
                "\\documentclass{article}\n"
                "\\label{fig:missing}\n",
                encoding="utf-8",
            )
            findings = gate.scan_surface([main, root / "body.tex", unrelated], root)
            missing = [item for item in findings if item["kind"] == "label_missing"]
            self.assertEqual(len(missing), 1)
            self.assertEqual(missing[0]["file"], "body.tex")
            self.assertIn("fig:missing", missing[0]["detail"])

    def test_duplicate_label_within_one_graph_is_finding(self):
        with tempfile.TemporaryDirectory(prefix="latex-surface-") as td:
            root = pathlib.Path(td)
            (root / "main.tex").write_text(
                "\\documentclass{article}\n"
                "\\input{body1}\n"
                "\\input{body2}\n",
                encoding="utf-8",
            )
            (root / "body1.tex").write_text(
                "\\section{A}\\label{eq:twin}\n", encoding="utf-8")
            (root / "body2.tex").write_text(
                "\\section{B}\\label{eq:twin}\nSee \\ref{eq:twin}.\n",
                encoding="utf-8")
            findings = gate.scan_surface(
                [root / "main.tex", root / "body1.tex", root / "body2.tex"],
                root)
            dups = [item for item in findings if item["kind"] == "label_duplicate"]
            # İkinci tanım raporlanır; ref'ın kendisi label'ı bulur (eksik değil).
            self.assertEqual(len(dups), 1)
            self.assertEqual(dups[0]["file"], "body2.tex")
            self.assertIn("eq:twin", dups[0]["detail"])
            self.assertIn("body1.tex:1", dups[0]["detail"])
            self.assertFalse([i for i in findings if i["kind"] == "label_missing"])

    def test_duplicate_label_in_same_file_is_finding(self):
        with tempfile.TemporaryDirectory(prefix="latex-surface-") as td:
            root = pathlib.Path(td)
            source = root / "main.tex"
            source.write_text(
                "\\documentclass{article}\n"
                "\\label{sec:twice}\n"
                "\\label{sec:twice}\n",
                encoding="utf-8",
            )
            findings = gate.scan_surface([source], root)
            dups = [item for item in findings if item["kind"] == "label_duplicate"]
            self.assertEqual(len(dups), 1)
            self.assertEqual(dups[0]["line"], 3)

    def test_duplicate_label_across_manuscript_copies_is_scoped_out(self):
        # Gerçek ağaç sözleşmesi: iki bağımsız manuscript kopyası aynı label'ı
        # tanımlayabilir (TESLIM kopyası ↔ sde_experiment kopyası — 44 label).
        with tempfile.TemporaryDirectory(prefix="latex-surface-") as td:
            root = pathlib.Path(td)
            copy_a = root / "a" / "main.tex"
            copy_b = root / "b" / "main.tex"
            copy_a.parent.mkdir()
            copy_b.parent.mkdir()
            copy_a.write_text(
                "\\documentclass{article}\n\\label{sec:intro}\n",
                encoding="utf-8")
            copy_b.write_text(
                "\\documentclass{article}\n\\label{sec:intro}\n",
                encoding="utf-8")
            findings = gate.scan_surface([copy_a, copy_b], root)
            self.assertFalse(
                [i for i in findings if i["kind"] == "label_duplicate"])

    def test_unresolved_input_is_finding_but_existing_and_commented_are_not(self):
        with tempfile.TemporaryDirectory(prefix="latex-surface-") as td:
            root = pathlib.Path(td)
            (root / "parts").mkdir()
            (root / "parts" / "ok.tex").write_text("ok\n", encoding="utf-8")
            source = root / "main.tex"
            source.write_text(
                "\\documentclass{article}\n"
                "\\input{parts/ok.tex}\n"
                "\\input{parts/nope}\n"
                "% \\input{parts/commented-out}\n",
                encoding="utf-8",
            )
            findings = gate.scan_surface([source, root / "parts" / "ok.tex"], root)
            missing = [item for item in findings if item["kind"] == "input_missing"]
            self.assertEqual(len(missing), 1)
            self.assertEqual(missing[0]["line"], 3)
            self.assertIn("parts/nope", missing[0]["detail"])

    def test_macro_input_target_is_flagged_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="latex-surface-") as td:
            root = pathlib.Path(td)
            source = root / "main.tex"
            source.write_text(
                "\\documentclass{article}\n\\input{\\chapters}\n",
                encoding="utf-8")
            findings = gate.scan_surface([source], root)
            missing = [item for item in findings if item["kind"] == "input_missing"]
            self.assertEqual(len(missing), 1)
            self.assertIn("makro", missing[0]["detail"])

    def test_multiple_ref_commands_are_reported(self):
        with tempfile.TemporaryDirectory(prefix="latex-surface-") as td:
            root = pathlib.Path(td)
            source = root / "main.tex"
            source.write_text(
                "\\documentclass{article}\n"
                "\\eqref{eq:one} \\autoref{sec:two} \\cref{fig:three}\n",
                encoding="utf-8",
            )
            findings = gate.scan_surface([source], root)
            self.assertEqual(len(findings), 3)
            self.assertTrue(all(item["kind"] == "label_missing" for item in findings))

    def test_cli_exit_codes_and_json(self):
        with tempfile.TemporaryDirectory(prefix="latex-surface-") as td:
            root = pathlib.Path(td)
            source = root / "main.tex"
            source.write_text("\\documentclass{article}\n$$x$$\n", encoding="utf-8")
            report = root / "report.json"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = gate.main([
                    "--root", str(root), "--file", str(source),
                    "--json", "--out", str(report),
                ])
            self.assertEqual(rc, 1)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(data["ok"])
            self.assertEqual(data["findings"][0]["kind"], "double_dollar")

    def test_real_repository_surface_is_clean(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = gate.main(["--root", str(gate.REPO_ROOT), "--json"])
        self.assertEqual(rc, 0, output.getvalue())
        self.assertTrue(json.loads(output.getvalue())["ok"])

    def test_gate_is_wired_to_precommit_and_ci(self):
        precommit = (gate.REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        workflow = (gate.REPO_ROOT / ".github" / "workflows" / "verify.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("id: check-latex-surface", precommit)
        self.assertIn("check_latex_surface.py --root .", precommit)
        self.assertIn("Check LaTeX surface (fail-closed)", workflow)
        self.assertIn("check_latex_surface.py", workflow)


if __name__ == "__main__":
    unittest.main()
