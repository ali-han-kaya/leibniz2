#!/usr/bin/env python3
"""verify.yml timeout contract: jobs and expensive steps are bounded."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"
SLOW_STEPS = (
    "Run pre-commit",
    "Download remaining artifacts",
    "Run live CI audit",
)


def blocks(text, indent):
    pattern = rf"^({indent}\S[^\n]*\n(?:{indent}{{2}}.*\n|\n)*)"
    return re.findall(pattern, text, re.M)


class WorkflowTimeoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_every_named_job_has_timeout(self):
        jobs = re.findall(r"^  ([\w-]+):\n(?=    name:)", self.text, re.M)
        self.assertTrue(jobs)
        for job in jobs:
            block = re.search(rf"^  {re.escape(job)}:\n(.*?)(?=^  \w|\Z)", self.text, re.M | re.S).group(1)
            self.assertRegex(block, r"(?m)^    timeout-minutes:\s*\d+\s*$", job)

    def test_k9_lake_build_uses_fifteen_minute_job_timeout(self):
        block = re.search(r"^  lake-proof:\n(.*?)(?=^  \w|\Z)", self.text, re.M | re.S).group(1)
        self.assertIn("    timeout-minutes: 15", block)
        self.assertIn("lake build --wfail", block)

    def test_expensive_steps_have_step_timeout(self):
        for marker in SLOW_STEPS:
            # Adım adı aynı satırda geçmeli ([^\n]*) — DOTALL `.*` ilk
            # `- name:` satırından en uzak adıma kayıp body'yi boşaltıyordu.
            pattern = rf"^      - name: [^\n]*{re.escape(marker)}[^\n]*\n" \
                      rf"(?P<body>[\s\S]*?)(?=^      - |^  \w|\Z)"
            match = re.search(pattern, self.text, re.M)
            self.assertIsNotNone(match, marker)
            self.assertRegex(match.group("body"), r"(?m)^        timeout-minutes:\s*\d+\s*$", marker)


if __name__ == "__main__":
    unittest.main()
