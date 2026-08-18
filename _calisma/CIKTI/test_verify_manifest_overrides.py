#!/usr/bin/env python3
"""test_verify_manifest_overrides.py — K10 cli_overrides↔config tutarlılığı kapısı.

verify_delivery._cli_overrides_consistency'yi kapsar: effective_config.json
(cli_overrides kaydı) ile verify_delivery.config.json (dosya değerleri)
arasındaki tutarlılık denetimi. stdlib unittest; ek bağımlılık yok — CI'da
`test_*.py` deseniyle otomatik koşar.
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_delivery as vd  # noqa: E402


FILE_CFG = {"budget_usd": 30.0, "budget_method": "both"}


def _effective(overrides=None):
    return {
        "config_path": "verify_delivery.config.json",
        "source": "file",
        "budget_usd": 30.0,
        "budget_method": "both",
        "budget_ratios": {"text": 8, "pdf": 8, "archive": 100, "binary": 100},
        "expected_pages": 33, "expected_refs": 64, "expected_manifest": 19,
        "cli_overrides": overrides
        if overrides is not None else {
            "budget": {"cli_given": False, "cli_value": None,
                       "file_value": 30.0, "effective": 30.0,
                       "override": False},
            "budget_method": {"cli_given": False, "cli_value": None,
                              "file_value": "both", "effective": "both",
                              "override": False},
        },
    }


class _Collector:
    def __init__(self):
        self.findings = []

    def __call__(self, pri, cid, check, issue, evidence=""):
        self.findings.append((pri, cid, issue))


def _run(eff_cfg, file_cfg, rel_prefix="config"):
    findings = _Collector()
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, rel_prefix), exist_ok=True)
        eff_p = os.path.join(d, rel_prefix, "effective_config.json")
        cfg_p = os.path.join(d, rel_prefix, "verify_delivery.config.json")
        with open(eff_p, "w", encoding="utf-8") as f:
            json.dump(eff_cfg, f)
        with open(cfg_p, "w", encoding="utf-8") as f:
            json.dump(file_cfg, f)
        files = {}
        for rel in (f"{rel_prefix}/effective_config.json",
                    f"{rel_prefix}/verify_delivery.config.json"):
            with open(os.path.join(d, rel), "rb") as f:
                files[rel] = hashlib.sha256(f.read()).hexdigest()
        ok, rows = vd._cli_overrides_consistency(files, d, findings)
        return ok, rows, findings.findings


class TestConsistent(unittest.TestCase):
    def test_consistent(self):
        ok, rows, findings = _run(_effective(), FILE_CFG)
        self.assertTrue(ok)
        self.assertEqual(findings, [])
        self.assertTrue(any("PASS" in r for r in rows))

    def test_skip_when_pair_absent(self):
        # İkisi de yoksa denetim atlanır (ok True, bulgu yok).
        collector = _Collector()
        ok, rows = vd._cli_overrides_consistency({}, "/nonexistent", collector)
        self.assertTrue(ok)
        self.assertEqual(collector.findings, [])
        self.assertTrue(any("atlandı" in r for r in rows))


class TestInconsistencies(unittest.TestCase):
    def test_file_value_mismatch(self):
        eff = _effective()
        eff["cli_overrides"]["budget"]["file_value"] = 99.0
        ok, rows, findings = _run(eff, FILE_CFG)
        self.assertFalse(ok)
        self.assertTrue(any("file_value=99.0" in r for r in rows))
        self.assertTrue(any(f[1] == "K10-OVERRIDE" for f in findings))

    def test_override_flag_inconsistent(self):
        eff = _effective()
        eff["cli_overrides"]["budget"]["override"] = True
        ok, rows, _ = _run(eff, FILE_CFG)
        self.assertFalse(ok)
        self.assertTrue(any("override bayrağı tutarsız" in r for r in rows))

    def test_effective_vs_cli_value(self):
        # override=True iken effective != cli_value olmalı → FAIL.
        eff = _effective({
            "budget": {"cli_given": True, "cli_value": 25.0,
                       "file_value": 30.0, "effective": 20.0,
                       "override": True},
            "budget_method": {"cli_given": False, "cli_value": None,
                              "file_value": "both", "effective": "both",
                              "override": False},
        })
        ok, rows, _ = _run(eff, FILE_CFG)
        self.assertFalse(ok)
        self.assertTrue(any("effective" in r for r in rows))

    def test_missing_cli_overrides(self):
        eff = _effective()
        eff.pop("cli_overrides")
        ok, rows, _ = _run(eff, FILE_CFG)
        self.assertFalse(ok)
        self.assertTrue(any("dict değil/yok" in r for r in rows))

    def test_missing_one_of_pair(self):
        # effective_config.json var ama verify_delivery.config.json yok.
        findings = _Collector()
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "config"), exist_ok=True)
            eff_p = os.path.join(d, "config", "effective_config.json")
            with open(eff_p, "w", encoding="utf-8") as f:
                json.dump(_effective(), f)
            files = {}
            with open(eff_p, "rb") as f:
                files["config/effective_config.json"] = \
                    hashlib.sha256(f.read()).hexdigest()
            ok, rows = vd._cli_overrides_consistency(
                files, d, findings)
        self.assertFalse(ok)
        self.assertTrue(any("verify_delivery.config.json yok" in r
                            for r in rows))
        self.assertTrue(any(f[1] == "K10-OVERRIDE" for f in findings.findings))


if __name__ == "__main__":
    unittest.main()
