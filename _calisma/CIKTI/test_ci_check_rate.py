#!/usr/bin/env python3
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ci_check_rate as cr  # noqa: E402


class TestCalculate(unittest.TestCase):
    def test_mixed_completed_running_and_missing(self):
        checks = ["A", "B", "C"]
        jobs = [
            [{"name": "A", "status": "completed", "conclusion": "success"},
             {"name": "B", "status": "completed", "conclusion": "failure"}],
            [{"name": "A", "status": "completed", "conclusion": "failure"},
             {"name": "B", "status": "in_progress"}],
        ]
        got = cr.calculate(checks, jobs)
        self.assertEqual(got["A"]["success"], 1)
        self.assertEqual(got["A"]["completed"], 2)
        self.assertEqual(got["A"]["success_rate"], 0.5)
        self.assertEqual(got["B"]["completed"], 1)
        self.assertEqual(got["B"]["success_rate"], 0.0)
        self.assertIsNone(got["C"]["success_rate"])

    def test_cancelled_and_skipped_count_as_non_success(self):
        got = cr.calculate(["A"], [[
            {"name": "A", "status": "completed", "conclusion": "cancelled"},
            {"name": "A", "status": "completed", "conclusion": "skipped"},
        ]])
        self.assertEqual(got["A"]["failed"], 2)
        self.assertEqual(got["A"]["success_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
