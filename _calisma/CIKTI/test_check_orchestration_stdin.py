#!/usr/bin/env python3
import pathlib
import tempfile
import unittest

import check_orchestration_stdin as audit


class TestOrchestrationStdin(unittest.TestCase):
    def write(self, text):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        path = pathlib.Path(td.name) / "sample.py"
        path.write_text(text, encoding="utf-8")
        return path

    def test_all_subprocess_calls_require_devnull(self):
        path = self.write("import subprocess\nsubprocess.run(['x'], stdin=subprocess.DEVNULL)\n")
        self.assertEqual(audit.audit(path), [])

    def test_missing_stdin_is_fail_closed(self):
        path = self.write("import subprocess\nsubprocess.run(['x'])\n")
        findings = audit.audit(path)
        self.assertEqual(len(findings), 1)
        self.assertIn("DEVNULL", findings[0]["message"])

    def test_other_stdin_value_is_rejected(self):
        path = self.write("import subprocess\nsubprocess.run(['x'], stdin=None)\n")
        self.assertEqual(len(audit.audit(path)), 1)

    def test_real_orchestration_files_are_clean(self):
        base = pathlib.Path(audit.__file__).parent
        for name in audit.DEFAULT_FILES:
            self.assertEqual(audit.audit(base / name), [], name)


if __name__ == "__main__":
    unittest.main()
