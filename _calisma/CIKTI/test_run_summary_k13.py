#!/usr/bin/env python3
"""test_run_summary_k13.py — run_summary_k13.py (K13 ayrı-step summary)
regresyon kapısı.

logs/k13_repro_manifest.json sidecar'ından durum özeti (status) ve
render çıktısı üretimini kapsar: PASS/FAIL/MISSING ayrımı, scenarios
tablosu ve eksik/bozuk sidecar davranışı. stdlib unittest — bağımlılık yok.
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

import run_summary_k13 as k13  # noqa: E402

SIDECAR_OK = {
    "layer": "K13",
    "ok": True,
    "exit": 0,
    "detail": "[K13] repro manifest: mock artifacts verified",
    "scenarios": [{"name": "hash-match", "status": "PASS"},
                  {"name": "tamper-detected", "status": "PASS"}],
}

SIDECAR_FAIL = {
    "layer": "K13",
    "ok": False,
    "exit": 1,
    "detail": "[K13] repro manifest: tampered artifact mismatch",
    "scenarios": [{"name": "tamper-detected", "status": "FAIL"}],
}


def _write_sidecar(d, data):
    p = os.path.join(d, "k13_repro_manifest.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return p


class TestLoad(unittest.TestCase):
    def test_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(k13._load(os.path.join(d, "yok.json")))

    def test_loads_ok_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            data = k13._load(_write_sidecar(d, SIDECAR_OK))
        self.assertIsNotNone(data)
        self.assertTrue(data["ok"])

    def test_corrupt_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "k13_repro_manifest.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write("{bad json}")
            self.assertIsNone(k13._load(p))


class TestStatus(unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(k13.status(os.path.join(d, "yok.json")), "MISSING")

    def test_pass(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(k13.status(_write_sidecar(d, SIDECAR_OK)), "PASS")

    def test_fail(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(k13.status(_write_sidecar(d, SIDECAR_FAIL)), "FAIL")


class TestRender(unittest.TestCase):
    def test_missing_advisory(self):
        buf = io.StringIO()
        k13.render(buf, "/yok/k13_repro_manifest.json")
        self.assertIn("sidecar bulunamadı", buf.getvalue())

    def test_ok_sidecar(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            k13.render(buf, _write_sidecar(d, SIDECAR_OK))
        out = buf.getvalue()
        self.assertIn("K13 repro-manifest: PASS", out)
        self.assertIn("exit=0", out)
        self.assertIn("hash-match", out)

    def test_fail_sidecar(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            k13.render(buf, _write_sidecar(d, SIDECAR_FAIL))
        out = buf.getvalue()
        self.assertIn("K13 repro-manifest: FAIL", out)
        self.assertIn("tampered artifact mismatch", out)


if __name__ == "__main__":
    unittest.main()
