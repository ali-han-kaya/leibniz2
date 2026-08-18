#!/usr/bin/env python3
"""test_diff_config_artifacts.py — diff_config_artifacts.py regresyon kapısı.

Kapsam: fark nedenlerinin sınıflandırılması (classify) ve --fail-on-drift
bayrağının exit koduna etkisi (drift → 1; cli_override/default → 0; fark yok
→ 0). stdlib unittest; ek bağımlılık yok — CI'da `test_*.py` deseniyle otomatik
koşar.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import diff_config_artifacts as dca  # noqa: E402


RAW = {
    "budget_usd": 30.0, "budget_method": "both",
    "budget_ratios": {"text": 8, "pdf": 8, "archive": 100, "binary": 100},
    "expected_pages": 33, "expected_refs": 64, "expected_manifest": 19,
}


def _effective(budget=30.0, method="both", cli_overrides=None):
    return {
        "budget_usd": budget, "budget_method": method,
        "budget_ratios": RAW["budget_ratios"],
        "expected_pages": 33, "expected_refs": 64, "expected_manifest": 19,
        "cli_overrides": cli_overrides
        if cli_overrides is not None else {
            "budget": {"cli_given": False, "cli_value": None,
                       "file_value": 30.0, "effective": budget,
                       "override": False},
            "budget_method": {"cli_given": False, "cli_value": None,
                              "file_value": "both", "effective": method,
                              "override": False},
        },
    }


class TestClassify(unittest.TestCase):
    def test_drift(self):
        # cli_overrides override=false ama değer farklı → drift.
        eff = _effective(budget=99.0)
        self.assertEqual(
            dca.classify("budget_usd", 30.0, 99.0, eff), "drift")

    def test_cli_override(self):
        eff = _effective(budget=25.0, cli_overrides={
            "budget": {"cli_given": True, "cli_value": 25.0,
                       "file_value": 30.0, "effective": 25.0,
                       "override": True},
            "budget_method": {"cli_given": False, "cli_value": None,
                              "file_value": "both", "effective": "both",
                              "override": False},
        })
        self.assertEqual(
            dca.classify("budget_usd", 30.0, 25.0, eff), "cli_override")

    def test_default(self):
        eff = _effective()
        self.assertEqual(
            dca.classify("expected_refs", None, 64, eff), "default")


class TestFailOnDrift(unittest.TestCase):
    def _run(self, raw, effective, fail_on_drift):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "verify_delivery.config.json"),
                      "w", encoding="utf-8") as f:
                json.dump(raw, f)
            with open(os.path.join(d, "effective_config.json"),
                      "w", encoding="utf-8") as f:
                json.dump(effective, f)
            argv = ["--config-dir", d, "--out-dir", d]
            if fail_on_drift:
                argv.append("--fail-on-drift")
            rc = dca.main(argv)
            diff = json.load(open(os.path.join(d, "config-diff.json"),
                                  encoding="utf-8"))
            return rc, diff

    def test_no_diff(self):
        rc, diff = self._run(RAW, _effective(), True)
        self.assertEqual(rc, 0)
        self.assertFalse(diff["changed"])

    def test_cli_override_advisory(self):
        eff = _effective(budget=25.0, method="universal", cli_overrides={
            "budget": {"cli_given": True, "cli_value": 25.0,
                       "file_value": 30.0, "effective": 25.0,
                       "override": True},
            "budget_method": {"cli_given": True, "cli_value": "universal",
                              "file_value": "both", "effective": "universal",
                              "override": True},
        })
        rc, diff = self._run(RAW, eff, True)
        self.assertEqual(rc, 0)
        reasons = {d["reason"] for d in diff["differences"]}
        self.assertEqual(reasons, {"cli_override"})

    def test_default_advisory(self):
        raw = dict(RAW)
        raw.pop("expected_pages")
        eff = _effective()
        rc, diff = self._run(raw, eff, True)
        self.assertEqual(rc, 0)
        reasons = {d["reason"] for d in diff["differences"]}
        self.assertEqual(reasons, {"default"})

    def test_drift_fails_when_flag_set(self):
        eff = _effective(budget=99.0)  # cli_overrides.override=false
        rc, diff = self._run(RAW, eff, True)
        self.assertEqual(rc, 1)
        self.assertTrue(any(d["reason"] == "drift"
                            for d in diff["differences"]))

    def test_drift_advisory_without_flag(self):
        eff = _effective(budget=99.0)
        rc, _ = self._run(RAW, eff, False)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
