#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_config_drift_summary.py — summary.txt tek-kaynak sözleşmesi.

config_drift_comment.js ve tum_sapmalar_comment.js override bölümünü
config-drift/summary.txt 'cli_overrides=' satırından türetir. Bu test,
check_config_drift_summary.py'nin fail-closed davranışını sabitler:

  1) summary.txt eksik → FAIL (script override bölümünü sessiz atlar)
  2) summary.txt var ama 'cli_overrides=' satırı yok → FAIL
  3) cli_overrides=WARNING/OK/N/A satırları → PASS
  4) main() exit kodları (0/1/2)
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from check_config_drift_summary import check_summary, main, OVERRIDE_LINE_RE


def _write(dirpath, name, content):
    p = os.path.join(dirpath, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


class TestCheckSummary(unittest.TestCase):

    def _td(self):
        return tempfile.TemporaryDirectory()

    def test_missing_summary_fails_closed(self):
        with self._td() as td:
            ok, findings, detail = check_summary(td)
            self.assertFalse(ok)
            self.assertEqual(len(findings), 1)
            self.assertIn("YOK", findings[0])
            self.assertIn("fail-closed", findings[0])
            self.assertIn("eksik", detail)

    def test_summary_without_override_line_fails_closed(self):
        with self._td() as td:
            _write(td, "summary.txt",
                   "config-drift exit=0 verdict=PASS\n"
                   "fark yok\n")
            ok, findings, detail = check_summary(td)
            self.assertFalse(ok)
            self.assertEqual(len(findings), 1)
            self.assertIn("cli_overrides=", findings[0])
            self.assertIn("fail-closed", findings[0])

    def test_warning_line_passes(self):
        with self._td() as td:
            _write(td, "summary.txt",
                   "config-drift exit=0 verdict=PASS\n"
                   "cli_overrides=WARNING 1 (override_count=1)\n")
            ok, findings, detail = check_summary(td)
            self.assertTrue(ok)
            self.assertEqual(findings, [])
            self.assertIn("WARNING", detail)

    def test_ok_line_passes(self):
        with self._td() as td:
            _write(td, "summary.txt",
                   "config-drift exit=0 verdict=PASS\n"
                   "cli_overrides=OK 0 (override_count=0)\n")
            ok, findings, detail = check_summary(td)
            self.assertTrue(ok)
            self.assertIn("OK", detail)

    def test_na_line_passes(self):
        with self._td() as td:
            _write(td, "summary.txt",
                   "config-drift exit=0 verdict=PASS\n"
                   "cli_overrides=N/A (denetim yok)\n")
            ok, findings, detail = check_summary(td)
            self.assertTrue(ok)
            self.assertIn("N/A", detail)

    def test_override_line_mid_file(self):
        # Satır dosyanın ortasında da olabilir (Bundle adımı append eder).
        with self._td() as td:
            _write(td, "summary.txt",
                   "config-drift exit=1 (gen_config=1, diff-on-drift=0) "
                   "verdict=FAIL\n"
                   "cli_overrides=WARNING 2 (override_count=2)\n"
                   "Overridden by cli_overrides WARNING — verdict → FAIL\n")
            ok, findings, detail = check_summary(td)
            self.assertTrue(ok)

    def test_main_exit_codes(self):
        with self._td() as td:
            # eksik → exit 1
            self.assertEqual(main(["--dir", td]), 1)
            # tam → exit 0
            _write(td, "summary.txt",
                   "config-drift exit=0 verdict=PASS\n"
                   "cli_overrides=OK 0 (override_count=0)\n")
            self.assertEqual(main(["--dir", td]), 0)


class TestRegex(unittest.TestCase):

    def test_matches_expected_formats(self):
        for line in ["cli_overrides=WARNING 1 (override_count=1)",
                     "cli_overrides=OK 0 (override_count=0)",
                     "cli_overrides=N/A (denetim yok)"]:
            self.assertTrue(OVERRIDE_LINE_RE.search(line), line)

    def test_rejects_lookalikes(self):
        for line in ["cli_overrides = WARNING 1",
                     "xcli_overrides=WARNING 1",
                     "cli_override=WARNING 1",
                     "cli_overrides=MAYBE 1"]:
            self.assertFalse(OVERRIDE_LINE_RE.search(line), line)


if __name__ == "__main__":
    unittest.main()
