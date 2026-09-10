#!/usr/bin/env python3
"""Deterministic ``status_checks --gh --json`` smoke contract.

The test replaces the GitHub API response, not the production comparison logic:
all 13 workflow-derived check names must render as PASS, while a single missing
check must render as FAIL.  The separate UNREADABLE case remains explicit.
"""
import io
import json
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

if HAVE_YAML:
    import status_checks as sc  # noqa: E402


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli (status_checks import)")
class TestStatusChecksGhSmoke(unittest.TestCase):
    def _protection(self, contexts):
        return {
            "required_status_checks": {"strict": True, "contexts": contexts},
            "enforce_admins": {"enabled": True},
            "allow_force_pushes": {"enabled": False},
            "allow_deletions": {"enabled": False},
        }

    def _json(self, protection):
        out = io.StringIO()
        with mock.patch.object(sc, "run_gh", return_value=json.dumps(protection)), \
             mock.patch.object(sys, "stdout", new=out):
            try:
                sc.main(["--gh", "--repo", "owner/name", "--json"])
            except SystemExit as exc:
                self._exit_code = exc.code
            else:
                self._exit_code = 0
        return json.loads(out.getvalue())

    def test_real_13_rows_are_deterministic_pass_table(self):
        checks = list(sc.gate_jobs().values())
        # Current workflow: 13 required-check candidates (GitHub required
        # contexts listinin birebir karşılığı).
        self.assertEqual(len(checks), 13)
        payload = self._json(self._protection(checks))
        self.assertEqual(payload["verdict"], "PASS")
        self.assertEqual(payload["configured"], sorted(checks))
        self.assertEqual(len(payload["configured"]), 13)
        self.assertEqual(len(payload["checks"]), 13)
        self.assertTrue(payload["names_ok"])
        self.assertTrue(payload["enforcement_ok"])

    def test_missing_row_is_fail(self):
        checks = list(sc.gate_jobs().values())
        payload = self._json(self._protection(checks[:-1]))
        self.assertEqual(self._exit_code, 1)
        self.assertEqual(payload["verdict"], "FAIL")
        self.assertEqual(payload["missing"], [checks[-1]])

    def test_unreadable_is_not_pass(self):
        out = io.StringIO()
        with mock.patch.object(sc, "run_gh", side_effect=RuntimeError("HTTP 403: forbidden")), \
             mock.patch.object(sys, "stdout", new=out):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertEqual(cm.exception.code, 1)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["verdict"], "UNREADABLE")
        self.assertNotEqual(payload["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
