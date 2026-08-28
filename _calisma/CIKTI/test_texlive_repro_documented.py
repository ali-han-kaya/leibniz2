#!/usr/bin/env python3
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "_calisma" / "CIKTI" / "texlive_determinism_test.sh"
PACKAGE = ROOT / "_calisma" / "V5_ICERIK" / "TESLIM_V5_FINAL_2026-08-17" / "stoic_hume_package" / "Stoic_Hume_Formal_Section_2026-08-17"
DOC = PACKAGE / "REPRODUCIBILITY.md"
MAKEFILE = ROOT / "docs" / "Makefile.tectonic"


class TestDocumentedTexliveRepro(unittest.TestCase):
    def test_documented_contract_and_hash_report(self):
        text = DOC.read_text(encoding="utf-8")
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("tectonic", text.lower())
        self.assertIn("SOURCE_DATE_EPOCH", text)
        self.assertIn("SOURCE_DATE_EPOCH", makefile)
        self.assertIn("--outdir", makefile)
        self.assertIn("make pdf", text)

        with tempfile.TemporaryDirectory(prefix="texlive-doc-") as td:
            root = Path(td)
            source = root / "sample.tex"
            source.write_text("\\documentclass{article}\\begin{document}x\\end{document}\n")
            tools = root / "tools"
            tools.mkdir()
            pdf = b"deterministic-pdf"
            stub = (
                "#!/bin/sh\n"
                "for arg in \"$@\"; do case \"$arg\" in *.tex) src=\"$arg\";; esac; done\n"
                "out=$(basename -- \"${src:-sample.tex}\" .tex).pdf; "
                "printf 'deterministic-pdf' > \"$out\"\n"
            )
            for name in ("tectonic", "pdflatex"):
                path = tools / name
                path.write_text(stub, encoding="utf-8")
                path.chmod(0o755)
            report = root / "report.txt"
            env = dict(os.environ, TEX_SOURCE=str(source), TECTONIC_BIN=str(tools / "tectonic"),
                       TEXLIVE_BIN=str(tools), DETERMINISM_OUT=str(report),
                       SOURCE_DATE_EPOCH="123")
            result = subprocess.run(["bash", str(SCRIPT)], env=env,
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report_text = report.read_text(encoding="utf-8")
            expected = hashlib.sha256(pdf).hexdigest()
            self.assertIn(f"tectonic_sha256={expected}", report_text)
            self.assertIn(f"texlive_run1_sha256={expected}", report_text)
            self.assertIn(f"texlive_run2_sha256={expected}", report_text)
            self.assertIn("source_date_epoch=123", report_text)
            self.assertIn("verdict=PASS", report_text)


if __name__ == "__main__":
    unittest.main()
