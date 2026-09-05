import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_unit_tests_timing as timing


class TimingTests(unittest.TestCase):
    def run_case(self, returncode, elapsed, limit):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "report.json")
            with mock.patch.object(timing.subprocess, "run", return_value=mock.Mock(returncode=returncode)), \
                 mock.patch.object(timing.time, "monotonic", side_effect=[0.0, elapsed]):
                rc = timing.main(["--limit", str(limit), "--out", out])
            with open(out, encoding="utf-8") as f:
                report = json.load(f)
        return rc, report

    def test_success_under_limit(self):
        rc, report = self.run_case(0, 9.999, 10)
        self.assertEqual(rc, 0)
        self.assertTrue(report["ok"])
        self.assertFalse(report["timeout_exceeded"])

    def test_exact_limit_is_allowed(self):
        rc, report = self.run_case(0, 10, 10)
        self.assertEqual(rc, 0)
        self.assertFalse(report["timeout_exceeded"])

    def test_over_limit_blocks(self):
        rc, report = self.run_case(0, 10.001, 10)
        self.assertEqual(rc, 1)
        self.assertFalse(report["ok"])
        self.assertTrue(report["timeout_exceeded"])

    def test_hook_failure_remains_failure(self):
        rc, report = self.run_case(7, 1, 10)
        self.assertEqual(rc, 7)
        self.assertFalse(report["ok"])


if __name__ == "__main__":
    unittest.main()
