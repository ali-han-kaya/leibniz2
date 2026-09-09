#!/usr/bin/env python3
"""verify.yml install-step hardening: K-gate tool installs must be if: always().

Without if: always(), a preceding unit-test failure skips the installs
(default if: success()), and --full then surfaces missing pdfinfo/Z3/Lean
as distant K-layer P1s (phantom env gaps) instead of a loud install failure.

This contract pins:
  verify job:     Install pdfinfo + qpdf (K6), Install Z3 (K8), Install Lean 4 (K9)
  ci-simulate job: Install deps (Z3 et al), Install pdfinfo + qpdf
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"

# (job_id, step name substring that uniquely identifies the install step)
VERIFY_INSTALL_STEPS = (
    ("verify", "Install pdfinfo (poppler-utils) + qpdf"),
    ("verify", "Install Z3 (K8)"),
    ("verify", "Install Lean 4 (K9)"),
)
CISIM_INSTALL_STEPS = (
    ("ci-simulate", "Install deps (pre-commit + PyYAML + jsonschema + Z3)"),
    ("ci-simulate", "Install pdfinfo (poppler-utils) + qpdf"),
)


def job_block(text, job_id):
    m = re.search(rf"^  {re.escape(job_id)}:\n(.*?)(?=^  [a-z0-9_-]+:|\Z)", text, re.M | re.S)
    return m.group(1) if m else None


def step_block(job_text, name_marker):
    pattern = (
        rf"^      - name: [^\n]*{re.escape(name_marker)}[^\n]*\n"
        rf"(?P<body>[\s\S]*?)(?=^      - |^  [a-z0-9_-]+:|\Z)"
    )
    m = re.search(pattern, job_text, re.M)
    return f"- name: {name_marker}\n{m.group('body')}" if m else None


class WorkflowInstallHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_verify_k_gate_installs_carry_if_always(self):
        blk = job_block(self.text, "verify")
        self.assertIsNotNone(blk, "verify job not found")
        for _, marker in VERIFY_INSTALL_STEPS:
            step = step_block(blk, marker)
            self.assertIsNotNone(step, f"verify: '{marker}' step not found")
            self.assertIn("if: always()", step,
                          f"verify: '{marker}' must carry if: always() so tool absence fails loudly instead of phantom K-layer P1")

    def test_cisimulate_installs_carry_if_always(self):
        blk = job_block(self.text, "ci-simulate")
        self.assertIsNotNone(blk, "ci-simulate job not found")
        for _, marker in CISIM_INSTALL_STEPS:
            step = step_block(blk, marker)
            self.assertIsNotNone(step, f"ci-simulate: '{marker}' step not found")
            self.assertIn("if: always()", step,
                          f"ci-simulate: '{marker}' must carry if: always() (same phantom-gap hardening as verify)")


if __name__ == "__main__":
    unittest.main()
