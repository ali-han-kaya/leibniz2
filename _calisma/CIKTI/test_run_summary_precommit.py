#!/usr/bin/env python3
"""test_run_summary_precommit.py — run_summary_precommit.py (rapor ayrıştırma)
regresyon kapısı.

PRECOMMIT_RAPORU.md'den P0/P1 bulguları + hook durumları + sonuç ayrıştırma,
durum-panosu özeti ve render çıktısını kapsar. Gerçek rapor biçimiyle aynı
fixture'lar kullanılır. stdlib unittest — ek bağımlılık yok.
"""
import io
import os
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import run_summary_precommit as pc  # noqa: E402

REPORT_CLEAN = """# PRECOMMIT DENETİM RAPORU

- **Sonuç:** 8/8 Passed

## Hook sonuçları

| Hook | Durum |
|---|---|
| Verify Stoic-Hume V5 delivery (fail-closed) | Passed |
| Plist gate unit tests (exit 0/1/2) | Passed |

## Bulgular (P0/P1)

Bulgu yok — tüm hook'lar geçti.
"""

REPORT_FINDINGS = """# PRECOMMIT DENETİM RAPORU

- **Sonuç:** FAIL (exit 1)

## Hook sonuçları

| Hook | Durum |
|---|---|
| Verify Stoic-Hume V5 delivery (fail-closed) | Passed |
| Plist gate unit tests (exit 0/1/2) | Failed |

## Bulgular (P0/P1)

| P1 | Plist gate testi başarısız (test_plist_gate_exit) |
| P1 | K0 taraması bulgu üretti |
"""


def _write(d, text):
    p = os.path.join(d, "PRECOMMIT_RAPORU.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class TestLoad(unittest.TestCase):
    def test_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(pc._load(os.path.join(d, "yok.md")))

    def test_parses_findings_hooks_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, REPORT_FINDINGS)
            findings, hooks, verdict = pc._load(p)
        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[0][0], "P1")
        self.assertIn("Plist gate", findings[0][1])
        self.assertEqual(len(hooks), 2)
        self.assertIn(("Plist gate unit tests (exit 0/1/2)", "Failed"), hooks)
        self.assertIn("FAIL", verdict)

    def test_clean_report_no_findings(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, REPORT_CLEAN)
            findings, hooks, verdict = pc._load(p)
        self.assertEqual(findings, [])
        self.assertEqual(verdict, "8/8 Passed")


class TestStatus(unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(pc.status(os.path.join(d, "yok.md")), "MISSING")

    def test_pass_no_findings(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(pc.status(_write(d, REPORT_CLEAN)), "PASS")

    def test_fail_with_findings(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(pc.status(_write(d, REPORT_FINDINGS)), "FAIL")


class TestRender(unittest.TestCase):
    def test_clean_output(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            pc.render(buf, _write(d, REPORT_CLEAN))
        out = buf.getvalue()
        self.assertIn("bulgu yok", out)
        self.assertIn("Sonuç: 8/8 Passed", out)

    def test_findings_output(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            pc.render(buf, _write(d, REPORT_FINDINGS))
        out = buf.getvalue()
        self.assertIn("Pre-commit bulguları: 2 bulgu", out)
        self.assertIn("**P1**: Plist gate", out)
        self.assertIn("Advisory", out)
        self.assertIn(":x:", out)  # Failed hook kırmızı çarpı

    def test_missing_advisory(self):
        buf = io.StringIO()
        pc.render(buf, "/yok/PRECOMMIT_RAPORU.md")
        self.assertIn("rapor bulunamadı", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
