#!/usr/bin/env python3
"""test_run_summary_budget.py — run_summary_budget.py regresyon kapısı.

_nomalize() tek-run (budget_verify.json) ve aggregated (budget/index.json)
şekillerini ortak {failures, runs} yapısına indirir; main() her iki şekli de
GITHUB_STEP_SUMMARY/stdout'a yazar. stdlib unittest — ek bağımlılık yok.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest

import run_summary_budget as rsb


class TestNormalize(unittest.TestCase):
    def test_single_run_ok(self):
        failures, runs = rsb._normalize({
            "limit": 30.0, "estimated_usd": 1.08, "verdict": "OK",
        })
        self.assertEqual(failures, [])
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["source"], "verify")
        self.assertEqual(runs[0]["limit"], 30.0)

    def test_single_run_fail(self):
        failures, runs = rsb._normalize({
            "limit": 5.0, "estimated_usd": 7.5, "verdict": "FAIL",
        })
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["source"], "verify")
        self.assertEqual(runs, [])

    def test_aggregated_passthrough(self):
        agg = {
            "failures": [{"source": "a"}],
            "runs": [{"source": "b"}],
        }
        failures, runs = rsb._normalize(agg)
        self.assertEqual(failures, agg["failures"])
        self.assertEqual(runs, agg["runs"])


class TestMain(unittest.TestCase):
    def setUp(self):
        # CI'da GITHUB_STEP_SUMMARY set olduğunda summary_sink() dosyaya
        # yazar; bu testler stdout çıktısını doğrular — env'i temizle.
        self._saved = os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["GITHUB_STEP_SUMMARY"] = self._saved

    def _run(self, path):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = rsb.main([path])
        return code, buf.getvalue()

    def test_single_run_ok_writes_confirm(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "budget_verify.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({
                    "limit": 30.0, "estimated_usd": 1.08, "tokens_est": 175990,
                    "verdict": "OK", "method": "both",
                }, f)
            code, out = self._run(p)
        self.assertEqual(code, 0)
        self.assertIn("limit içinde", out)
        self.assertIn("verify", out)
        self.assertIn("$1.08", out)

    def test_single_run_fail_writes_warning(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "budget_verify.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({
                    "limit": 5.0, "estimated_usd": 7.5, "verdict": "FAIL",
                    "method": "both",
                }, f)
            code, out = self._run(p)
        self.assertEqual(code, 0)
        self.assertIn("Bütçe limiti aşıldı", out)
        self.assertIn("+$2.5", out)

    def test_missing_file_is_advisory(self):
        code, out = self._run("nonexistent.json")
        self.assertEqual(code, 0)
        self.assertIn("sidecar bulunamadı", out)

    def test_cli_overrides_rendered(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "index.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({
                    "failures": [],
                    "runs": [{"source": "verify", "limit": 30.0,
                              "estimated_usd": 1.08, "tokens_est": 175990}],
                    "method": "both",
                    "cli_overrides": {"warning": True, "overrides": [
                        {"key": "budget_usd", "file_value": 30.0,
                         "effective": 25.0},
                    ]},
                }, f)
            code, out = self._run(p)
        self.assertEqual(code, 0)
        self.assertIn("CLI override uyarısı", out)
        self.assertIn("30.0 → 25.0", out)


if __name__ == "__main__":
    unittest.main()
