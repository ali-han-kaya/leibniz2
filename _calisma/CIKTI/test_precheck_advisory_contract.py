#!/usr/bin/env python3
"""Repository invariant: verify.yml's precheck advisory contract is valid."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

if HAVE_YAML:
    import status_checks  # noqa: E402


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli (status_checks import)")
class TestPrecheckAdvisoryContract(unittest.TestCase):
    def test_real_verify_workflow_contract_is_ok(self):
        """The exact workflow used by CI must satisfy advisory_contract.ok."""
        workflow = ROOT / ".github" / "workflows" / "verify.yml"
        self.assertTrue(workflow.is_file(), workflow)
        contract = status_checks.advisory_contract()
        self.assertIs(contract["ok"], True, contract["issues"])
        self.assertTrue(contract["plist_check"]["ok"], contract)


if __name__ == "__main__":
    unittest.main()
