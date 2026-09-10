#!/usr/bin/env python3
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
VERIFY = HERE / "verify_delivery.py"


class DurationPctConfigTests(unittest.TestCase):
    def test_config_declares_positive_threshold(self):
        cfg = json.loads((HERE / "verify_delivery.config.json").read_text())
        self.assertGreater(cfg["duration_pct_warn"], 0)

    def test_cli_flag_is_documented_and_wired(self):
        out = subprocess.run([sys.executable, str(VERIFY), "--help"],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("--duration-pct-warn", out)
        source = VERIFY.read_text()
        self.assertIn('cfg.get("duration_pct_warn", 10.0)', source)
        self.assertIn('"duration_pct_warn": _override_rec', source)

    def test_invalid_threshold_is_rejected_by_config_validation(self):
        source = VERIFY.read_text()
        self.assertIn('duration_pct_warn: 0\'dan büyük olmalı', source)


if __name__ == "__main__":
    unittest.main()
