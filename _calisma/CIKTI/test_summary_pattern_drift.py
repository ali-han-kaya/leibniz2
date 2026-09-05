#!/usr/bin/env python3
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import summary_pattern_drift as spd


class SummaryPatternDriftTests(unittest.TestCase):
    def run_cli(self, pattern, expected, *args):
        jobs = {"job": ["test_summary_pattern_drift.py"]}
        with mock.patch.object(spd, "_read_pattern", return_value=set(pattern)), \
             mock.patch.object(spd.gm, "ARTIFACT_JOBS", {name: "job" for name in expected}), \
             mock.patch.object(spd.gm, "CI_JOB_COVERAGE", jobs), \
             mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(sys, "argv", ["summary_pattern_drift.py", *args]):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = spd.main()
        return rc, out.getvalue(), err.getvalue()

    def test_json_pass_is_machine_readable(self):
        rc, out, err = self.run_cli({"a", "b"}, {"a", "b"}, "--json")
        self.assertEqual(rc, 0)
        report = json.loads(out)
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["extra"], [])
        self.assertIn("Sonuç: PASS", err)

    def test_json_out_reports_missing_and_extra(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "pattern.json")
            rc, out, err = self.run_cli(
                {"a", "old"}, {"a", "required"}, "--json-out", path
            )
            self.assertEqual(rc, 1)
            self.assertEqual(out, "")
            with open(path, encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(report["verdict"], "DRIFT")
            self.assertEqual(report["missing"], ["required"])
            self.assertEqual(report["extra"], ["old"])
            self.assertIn("Sonuç: DRIFT", err)

    def test_markdown_summary_is_written(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "summary.md")
            rc, out, _ = self.run_cli({"a"}, {"a"}, "--summary-path", path)
            self.assertEqual(rc, 0)
            self.assertIn("Summary yazıldı", out)
            with open(path, encoding="utf-8") as f:
                self.assertIn("merge pattern", f.read())


if __name__ == "__main__":
    unittest.main()
