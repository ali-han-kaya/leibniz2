import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_skip_budget as gate  # noqa: E402


def _log(text):
    fd, path = tempfile.mkstemp(suffix=".log")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _budget(value):
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(value)
    return path


def _run(log_text, budget_text="25\n"):
    lp = _log(log_text)
    bp = _budget(budget_text)
    try:
        err = StringIO()
        with redirect_stderr(err):
            rc = gate.main(["--budget-file", bp, lp])
        return rc, err.getvalue()
    finally:
        os.unlink(lp)
        os.unlink(bp)


class CountSkipsTest(unittest.TestCase):
    def test_counts_skipped_in_summary(self):
        blocks, skipped = gate.count_skips("Ran 10 tests in 0.1s\n\nOK (skipped=4)\n")
        self.assertEqual((blocks, skipped), (1, 4))

    def test_no_summary_means_zero_blocks(self):
        self.assertEqual(gate.count_skips("hello\n"), (0, 0))

    def test_ok_without_skipped_counts_zero(self):
        self.assertEqual(gate.count_skips("Ran 3 tests in 0.1s\n\nOK\n"), (1, 0))


class BudgetGateTest(unittest.TestCase):
    def test_within_budget_passes(self):
        rc, _ = _run("Ran 30 tests in 1s\n\nOK (skipped=25)\n")
        self.assertEqual(rc, 0)

    def test_over_budget_fails(self):
        rc, err = _run("Ran 300 tests in 1s\n\nOK (skipped=221)\n")
        self.assertEqual(rc, 1)
        self.assertIn("221", err)

    def test_missing_summary_fails_closed(self):
        rc, err = _run("Ran 300 tests in 1s\n")
        self.assertEqual(rc, 1)
        self.assertIn("ölçüm yok", err)

    def test_empty_log_fails_closed(self):
        rc, _ = _run("")
        self.assertEqual(rc, 1)

    def test_bad_budget_file_is_usage_error(self):
        rc, _ = _run("Ran 1 tests in 0s\n\nOK\n", budget_text="abc\n")
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
