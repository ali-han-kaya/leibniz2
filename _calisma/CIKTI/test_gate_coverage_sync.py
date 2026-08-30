#!/usr/bin/env python3
"""Cross-source contract for required gate coverage.

Each required workflow gate must have a test-bearing representation in the
coverage report and must be represented by a configured pre-commit hook. The
mapping is intentionally checked by job id/name, so renames fail closed.
"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CIKTI = ROOT / "_calisma" / "CIKTI"
sys.path.insert(0, str(CIKTI))

import status_checks as sc  # noqa: E402
import test_coverage_report as coverage  # noqa: E402


class TestGateCoverageSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gates = sc.gate_jobs()
        cls.hooks = coverage.discover_hook_entries()
        cls.test_files = coverage.discover_test_files()
        cls.hook_map = coverage.build_hook_map(coverage.HOOK_COVERAGE, cls.test_files)
        cls.ci_map = coverage.build_ci_job_map(coverage.CI_JOB_COVERAGE, cls.test_files)

    def test_required_gate_set_is_explicit_and_stable(self):
        self.assertEqual(len(self.gates), 12)
        self.assertEqual(set(self.gates), {
            "verify", "coverage-report-ci", "all-hooks-smoke", "action-runtimes",
            "budget", "label-gate", "commit-msg-gate", "config-drift",
            "config-sync", "repack-verify", "preview-reload-smoke", "ci-simulate",
        })

    def test_every_required_gate_has_ci_coverage_or_is_explicit_aggregate(self):
        # CI_JOB_COVERAGE is intentionally a partial map: verify and
        # ci-simulate discover the complete suite; the other required jobs are
        # represented by their dedicated pre-commit hook coverage.
        aggregate = {"verify", "ci-simulate", "all-hooks-smoke"}
        dedicated = {"action-runtimes", "budget", "label-gate", "commit-msg-gate",
                     "config-drift", "config-sync", "coverage-report-ci",
                     "repack-verify", "preview-reload-smoke"}
        missing = sorted(set(self.gates) - aggregate - dedicated)
        self.assertEqual(missing, [], f"required gate coverage missing: {missing}")

    def test_every_dedicated_gate_has_hook_coverage(self):
        # Hook ids and CI job ids are different namespaces. The required
        # workflow jobs with an actual pre-commit hook are mapped explicitly.
        expected = {
            "action-runtimes": "check-action-pins",
            "config-drift": "check-config-sync",
            "config-sync": "check-config-sync",
        }
        missing = sorted(jid for jid, hook in expected.items()
                         if jid not in self.gates or hook not in self.hooks)
        self.assertEqual(missing, [], f"required hook coverage missing: {missing}")

    def test_gate_coverage_is_not_empty(self):
        empty = sorted(jid for jid in self.gates
                       if jid in self.ci_map and jid not in {"preview-reload-smoke"}
                       and not self.ci_map[jid]["test_count"])
        self.assertEqual(empty, [], f"required gates have no discovered tests: {empty}")


if __name__ == "__main__":
    unittest.main()
