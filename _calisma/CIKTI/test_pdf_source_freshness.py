#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "check_pdf_source_freshness.py"


class PdfSourceFreshnessTests(unittest.TestCase):
    def run_check(self, tex_mtime, pdf_mtime, *, include_pdf=True):
        with tempfile.TemporaryDirectory() as td:
            tex = Path(td) / "manuscript.tex"
            pdf = Path(td) / "manuscript.pdf"
            tex.write_text("source", encoding="utf-8")
            if include_pdf:
                pdf.write_bytes(b"pdf")
            os.utime(tex, ns=(tex_mtime, tex_mtime))
            if include_pdf:
                os.utime(pdf, ns=(pdf_mtime, pdf_mtime))
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--tex", str(tex), "--pdf", str(pdf)],
                capture_output=True, text=True,
            )

    def test_source_newer_than_pdf_fails_closed(self):
        result = self.run_check(200, 100)
        self.assertEqual(result.returncode, 1)
        self.assertIn("source TeX is newer", result.stdout)

    def test_pdf_at_least_as_new_as_source_passes(self):
        result = self.run_check(100, 100)
        self.assertEqual(result.returncode, 0)
        self.assertIn("freshness: PASS", result.stdout)

    def test_missing_pdf_fails_closed(self):
        result = self.run_check(100, 0, include_pdf=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("shipped PDF not found", result.stdout)


if __name__ == "__main__":
    unittest.main()
