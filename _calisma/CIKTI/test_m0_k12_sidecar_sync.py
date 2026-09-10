#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M0 K12 row ↔ k12_repro_manifest.json scenarios contract."""
import json
import pathlib
import re
import unittest

HERE = pathlib.Path(__file__).resolve().parent
M0 = HERE / "M0_TOOLKIT_DENETIM_RAPORU.md"
WORKFLOW = HERE.parents[1] / ".github" / "workflows" / "verify.yml"
SIDECAR = HERE / "logs" / "k12_repro_manifest.json"

K12_ROW = re.compile(r"^\|\s*K12\s*\|(?P<control>.*?)\|\s*(?P<status>[^|]+)\|", re.M)
SCENARIO_MARKERS = ("bozuk-plist", "eksik-golden")


def _k12_row(text):
    match = K12_ROW.search(text)
    if not match:
        raise AssertionError("M0 raporunda K12 satırı yok")
    return match.group("control"), match.group("status").strip()


def _scenario_names(data):
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, dict):
        raise AssertionError("K12 sidecar scenarios dict olmalı")
    missing = set(SCENARIO_MARKERS) - set(scenarios)
    if missing:
        raise AssertionError(f"K12 sidecar senaryoları eksik: {missing}")
    return set(scenarios), scenarios


class TestM0K12SidecarSync(unittest.TestCase):
    def test_m0_k12_row_describes_sidecar_scenarios(self):
        if not SIDECAR.is_file():
            self.skipTest("k12_repro_manifest.json henüz üretilmemiş")
        control, status = _k12_row(M0.read_text(encoding="utf-8"))
        names, scenarios = _scenario_names(json.loads(SIDECAR.read_text(encoding="utf-8")))
        self.assertTrue(set(SCENARIO_MARKERS) <= names,
                        f"K12 sidecar senaryoları eksik: {names}")
        self.assertIn("PASS", control)
        self.assertIn("scenarios", control)
        self.assertEqual(status, "PASS")
        self.assertTrue(all(value == "PASS" for value in scenarios.values()),
                        f"K12 sidecar'da başarısız senaryo: {scenarios}")

    def test_m0_row_and_workflow_use_same_k12_contract(self):
        control, _ = _k12_row(M0.read_text(encoding="utf-8"))
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("--check-plist", control)
        m0 = M0.read_text(encoding="utf-8")
        k12_to_k13 = m0[m0.index("| K12 |"):m0.index("| K13 |")]
        self.assertIn("K12", k12_to_k13)
        self.assertIn("scenarios", m0)
        self.assertIn("K12", workflow,
                      "workflow K12 kapısını çalıştırmalı")
        self.assertIn("plist_report.json", workflow,
                      "workflow K12 raporunu üretmeli")


class TestM0K12SidecarParsing(unittest.TestCase):
    def test_scenario_contract_rejects_missing_marker(self):
        with self.assertRaises(AssertionError):
            _scenario_names({"scenarios": {"bozuk-plist": "PASS"}})

    def test_scenario_contract_accepts_both_markers(self):
        names, values = _scenario_names({"scenarios": {
            "bozuk-plist": "PASS", "eksik-golden": "PASS"}})
        self.assertEqual(names, set(SCENARIO_MARKERS))
        self.assertTrue(all(v == "PASS" for v in values.values()))


if __name__ == "__main__":
    unittest.main()
