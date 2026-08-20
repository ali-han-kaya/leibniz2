#!/usr/bin/env python3
"""test_run_summary_k0.py — run_summary_k0.py (rapor ayrıştırma) regresyon kapısı.

K0 bayat-zip sidecar'ı (k0_findings.json) ayrıştırma, durum-panosu özeti ve
render çıktısını kapsar: bulgu yoksa PASS/temiz, bulgu varsa FAIL/kırmızı
liste, sidecar yoksa MISSING/advisory. stdlib unittest — ek bağımlılık yok.
"""
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import run_summary_k0 as k0  # noqa: E402


class TestLoad(unittest.TestCase):
    def test_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(k0._load(os.path.join(d, "yok.json")))

    def test_valid_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "k0_findings.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"count": 1, "findings": []}, f)
            self.assertEqual(k0._load(p)["count"], 1)


class TestStatus(unittest.TestCase):
    def _write(self, d, data):
        p = os.path.join(d, "k0_findings.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(k0.status(os.path.join(d, "yok.json")), "MISSING")

    def test_pass_when_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, {"count": 0, "findings": []})
            self.assertEqual(k0.status(p), "PASS")

    def test_fail_when_findings(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, {"count": 2, "findings": [{"rel": "a.zip"}]})
            self.assertEqual(k0.status(p), "FAIL")


class TestRender(unittest.TestCase):
    def _render(self, data):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "k0_findings.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f)
            n = k0.render(buf, p)
        return n, buf.getvalue()

    def test_clean(self):
        n, out = self._render({"count": 0, "findings": []})
        self.assertEqual(n, 0)
        self.assertIn("K0 bayat zip: temiz", out)

    def test_findings_listed_with_short_hash(self):
        n, out = self._render({"count": 1, "findings": [
            {"rel": "dipsar/bayat.zip", "sha256": "a" * 64}]})
        self.assertEqual(n, 1)
        self.assertIn("bayat.zip", out)
        self.assertIn("a" * 16 + "…", out)  # kısaltılmış hash
        self.assertIn("Fail-closed", out)

    def test_missing_sidecar_advisory(self):
        buf = io.StringIO()
        n = k0.render(buf, "/yok/k0_findings.json")
        self.assertEqual(n, 0)
        self.assertIn("sidecar bulunamadı", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
