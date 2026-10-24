#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_branch_lineage_check.py — Branch lineage coverage check tests."""

import json
import os
import subprocess
import sys
import tempfile
import pathlib
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import branch_lineage_check as blc  # noqa: E402


class TestBranchLineageCheck(unittest.TestCase):
    """Tests for the branch lineage coverage check."""

    def test_main_to_main_pass(self):
        """main → main should PASS (all commits reachable)."""
        with tempfile.TemporaryDirectory() as td:
            # Run from a temp dir that's not a git repo, should get ERROR
            # But we test the main repo directly
            result = blc.main()
            # This will use the actual repo, so just verify it runs without error
            # and returns 0 for main→main
            self.assertEqual(result, 0)

    def test_branch_with_unreachable_commits_fail(self):
        """A branch with commits not on target should FAIL."""
        # Test with a feature branch that has unreachable commits
        # We test the actual repo behavior
        import pathlib
        result = subprocess.run(
            ["python3", "/Users/alikaya/Desktop/leibniz2/_calisma/CIKTI/branch_lineage_check.py",
             "main", "feat/a11y-gate-witness-summary-20261012"],
            cwd="/Users/alikaya/Desktop/leibniz2", capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 1)  # FAIL expected

    def test_sidecar_written_on_pass(self):
        """Sidecar file should be written on PASS."""
        with tempfile.TemporaryDirectory() as td:
            # We can't easily test in isolation without a git repo,
            # but we can verify the script writes the sidecar
            result = subprocess.run(
                ["python3", "/Users/alikaya/Desktop/leibniz2/_calisma/CIKTI/branch_lineage_check.py",
                 "main", "main"],
                cwd="/Users/alikaya/Desktop/leibniz2", capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0)
            sidecar = pathlib.Path("/Users/alikaya/Desktop/leibniz2/branch_lineage_sidecar.json")
            self.assertTrue(sidecar.is_file())
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertTrue(data["ok"])

    def test_sidecar_written_on_fail(self):
        """Sidecar file should be written on FAIL too."""
        result = subprocess.run(
            ["python3", "/Users/alikaya/Desktop/leibniz2/_calisma/CIKTI/branch_lineage_check.py",
             "main", "feat/a11y-gate-witness-summary-20261012"],
            cwd="/Users/alikaya/Desktop/leibniz2", capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 1)  # FAIL
        sidecar = pathlib.Path("/Users/alikaya/Desktop/leibniz2/branch_lineage_sidecar.json")
        self.assertTrue(sidecar.is_file())
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        self.assertFalse(data["ok"])  # Should be False on FAIL

    def test_findings_md_updated(self):
        """findings.md should have a lineage section added."""
        # Run twice to add two sessions
        subprocess.run(
            ["python3", "/Users/alikaya/Desktop/leibniz2/_calisma/CIKTI/branch_lineage_check.py",
             "main", "main"],
            cwd="/Users/alikaya/Desktop/leibniz2", capture_output=True, text=True
        )
        subprocess.run(
            ["python3", "/Users/alikaya/Desktop/leibniz2/_calisma/CIKTI/branch_lineage_check.py",
             "main", "main"],
            cwd="/Users/alikaya/Desktop/leibniz2", capture_output=True, text=True
        )
        findings = pathlib.Path("/Users/alikaya/Desktop/leibniz2/findings.md")
        self.assertTrue(findings.is_file())
        content = findings.read_text(encoding="utf-8")
        # Should have "## Session" markers
        self.assertIn("## Session", content)


if __name__ == "__main__":
    unittest.main()