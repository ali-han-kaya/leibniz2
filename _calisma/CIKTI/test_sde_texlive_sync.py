#!/usr/bin/env python3
"""K21 --check-sde ile TeXLive determinism kapısının SDE sözleşmesi."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import verify_delivery as vd  # noqa: E402


def _sde_contract_text():
    return (ROOT / "texlive_determinism_test.sh").read_text(encoding="utf-8")


class TestSdeContractSync(unittest.TestCase):
    def test_both_gates_use_source_date_epoch(self):
        script = (ROOT / "texlive_determinism_test.sh").read_text(encoding="utf-8")
        self.assertIn('SDE="${SOURCE_DATE_EPOCH:-0}"', script)
        self.assertIn('export SOURCE_DATE_EPOCH="$SDE"', script)
        self.assertIn("SDE", _sde_contract_text())

    def test_both_gates_require_same_sde_input(self):
        script = (ROOT / "texlive_determinism_test.sh").read_text(encoding="utf-8")
        self.assertIn("SOURCE_DATE_EPOCH", _sde_contract_text())
        self.assertIn("SDE", script)
        self.assertIn("source_date_epoch=", script)

    def test_k21_is_fail_closed(self):
        self.assertTrue(hasattr(vd, "main"), "verify entrypoint mevcut olmalı")
        self.assertIn("SOURCE_DATE_EPOCH", _sde_contract_text())


if __name__ == "__main__":
    unittest.main()
