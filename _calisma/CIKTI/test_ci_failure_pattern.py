#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_ci_failure_pattern.py — ci_failure_pattern.py sınıflandırıcı testleri.

KURAL sabitlemesi (offline, mock veriyle):
  - deterministic: F_J > W_J/2 (tutarlı kırmızı)
  - flaky        : 0 < F_J ≤ W_J/2 (aralıklı)
  - config-drift : config anahtarlı job + F_J > 0 (K10/K11/K13 drift sinyali)
  - skipped      : pencereye katılmaz (PR-only job'lar push'ta flaky görünmez)
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ci_failure_pattern as cfp  # noqa: E402


def _job(name, concl):
    return {"name": name, "conclusion": concl}


def _run(run_id, concl, jobs):
    return {"databaseId": run_id, "status": "completed",
            "conclusion": concl, "jobs": jobs}


def _analyze(rows):
    """rows: [ {run_id, concl, jobs:[(name, concl)]} ] → (timeline, jobs)."""
    runs = []
    for r in rows:
        runs.append({
            "databaseId": r["run_id"],
            "status": "completed",
            "conclusion": r["concl"],
        })
    orig_jobs, orig_repo = cfp.list_jobs, cfp.get_repo
    cfp.get_repo = lambda: "mock/repo"  # ağ çağrısı yok (test hızlı)

    def fake_jobs(repo, rid):
        for r in rows:
            if r["run_id"] == rid:
                return [_job(n, c) for (n, c) in r["jobs"]]
        return []
    cfp.list_jobs = fake_jobs
    try:
        return cfp.analyze(runs)
    finally:
        cfp.list_jobs, cfp.get_repo = orig_jobs, orig_repo


class TestClassifyJob(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(cfp.classify_job("Verify", 0, 10)[0], "pass")

    def test_deterministic_over_half(self):
        cat, det = cfp.classify_job("Delivery verification", 8, 10)
        self.assertEqual(cat, "deterministic")
        self.assertIn("tutarlı", det)

    def test_flaky_half_or_less(self):
        self.assertEqual(cfp.classify_job("Mirror sync check", 4, 10)[0],
                         "flaky")
        self.assertEqual(cfp.classify_job("Mirror sync check", 5, 10)[0],
                         "flaky")  # F == W/2 → flaky (eşitlik flaky)

    def test_config_drift_keyword(self):
        for name in ("Config drift check (gen_config + diff-on-drift)",
                     "Config snapshot ↔ CONFIG_BASENAMES sync check",
                     "Hook env matrix check (advisory)"):
            cat = cfp.classify_job(name, 3, 10)[0]
            self.assertEqual(cat, "config-drift", name)

    def test_config_drift_beats_deterministic(self):
        # Config anahtarlı job çok FAIL'se bile kategori config-drift kalır.
        cat, det = cfp.classify_job("Config drift check", 9, 10)
        self.assertEqual(cat, "config-drift")
        self.assertIn("drift", det)

    def test_plain_job_not_config(self):
        self.assertEqual(cfp.classify_job("Delivery verification", 9, 10)[0],
                         "deterministic")


class TestAnalyzeAndSummarize(unittest.TestCase):
    def test_skipped_not_counted(self):
        # PR-only job push'ta skipped → pencereye katılmaz → flaky yok.
        rows = [
            {"run_id": 1, "concl": "success",
             "jobs": [("label-gate", "skipped"), ("Verify", "success")]},
            {"run_id": 2, "concl": "success",
             "jobs": [("label-gate", "skipped"), ("Verify", "success")]},
        ]
        timeline, jobs = _analyze(rows)
        self.assertNotIn("label-gate", jobs)
        self.assertNotIn("label-gate",
                         {b["job"] for b in cfp.summarize(timeline, jobs)
                          ["jobs"]})

    def test_deterministic_job_summarized(self):
        rows = [{"run_id": i, "concl": "failure",
                 "jobs": [("Verify", "failure")]} for i in range(1, 8)]
        rows += [{"run_id": i, "concl": "success",
                  "jobs": [("Verify", "success")]} for i in range(8, 11)]
        timeline, jobs = _analyze(rows)
        s = cfp.summarize(timeline, jobs)
        self.assertIn("Verify", s["categories"]["deterministic"])
        v = [b for b in s["jobs"] if b["job"] == "Verify"][0]
        self.assertEqual(v["category"], "deterministic")
        self.assertEqual(v["failures"], 7)
        self.assertEqual(v["window"], 10)

    def test_flaky_job_summarized(self):
        rows = [{"run_id": 1, "concl": "failure",
                 "jobs": [("Daemon mode", "failure")]}]
        rows += [{"run_id": i, "concl": "success",
                  "jobs": [("Daemon mode", "success")]} for i in range(2, 11)]
        timeline, jobs = _analyze(rows)
        s = cfp.summarize(timeline, jobs)
        self.assertIn("Daemon mode", s["categories"]["flaky"])

    def test_mixed_failures_classified_separately(self):
        rows = [
            {"run_id": 1, "concl": "failure",
             "jobs": [("Verify", "failure"), ("Config drift check", "failure")]},
            {"run_id": 2, "concl": "failure",
             "jobs": [("Verify", "failure"), ("Config drift check", "success")]},
        ]
        rows += [{"run_id": i, "concl": "success",
                  "jobs": [("Verify", "success"),
                            ("Config drift check", "success")]}
                 for i in range(3, 11)]
        timeline, jobs = _analyze(rows)
        s = cfp.summarize(timeline, jobs)
        # Verify: 2/10 FAIL → flaky; Config: 1/10 FAIL → config-drift.
        self.assertIn("Verify", s["categories"]["flaky"])
        self.assertIn("Config drift check", s["categories"]["config_drift"])

    def test_success_rate(self):
        rows = [{"run_id": i, "concl": "success", "jobs": []}
                for i in range(1, 9)]
        rows += [{"run_id": i, "concl": "failure", "jobs": []}
                 for i in range(9, 11)]
        timeline, jobs = _analyze(rows)
        s = cfp.summarize(timeline, jobs)
        self.assertEqual(s["success_rate"], 0.8)
        self.assertEqual(s["runs_failure"], 2)


class TestJsonSchema(unittest.TestCase):
    def test_summary_shape(self):
        rows = [{"run_id": 1, "concl": "failure",
                 "jobs": [("Config drift check", "failure")]}]
        rows += [{"run_id": i, "concl": "success", "jobs": []}
                 for i in range(2, 11)]
        timeline, jobs = _analyze(rows)
        s = cfp.summarize(timeline, jobs)
        self.assertEqual(set(s), {"runs_total", "runs_failure",
                                  "success_rate", "jobs", "categories"})
        self.assertEqual(set(s["categories"]),
                         {"deterministic", "flaky", "config_drift"})


if __name__ == "__main__":
    unittest.main()
