"""load_cached_latest history yedeği: yalnız HISTORY_KEYS geri yüklenir.

history.jsonl satırı LATEST'te adı geçen ama geçmişe hiç yazılmamış alanları
(stdout, stderr, override_report) taşıyabilir. Okuma tarafı LATEST üyeliğine
değil yazım sözleşmesine (HISTORY_KEYS) güvenmeli.
"""
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import preview_server as ps  # noqa: E402


class HistoryRestoreAllowlistTests(unittest.TestCase):
    def setUp(self):
        self._old = (ps.RUNS_DIR, ps.HISTORY_PATH, dict(ps.LATEST))
        self._td = tempfile.TemporaryDirectory()
        ps.RUNS_DIR = os.path.join(self._td.name, "runs")  # yok -> run-log yolu kapalı
        ps.HISTORY_PATH = os.path.join(self._td.name, "history.jsonl")

    def tearDown(self):
        ps.RUNS_DIR, ps.HISTORY_PATH = self._old[0], self._old[1]
        ps.LATEST.clear()
        ps.LATEST.update(self._old[2])
        self._td.cleanup()

    def _write_history(self, row):
        with open(ps.HISTORY_PATH, "w", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def test_writer_contract_keys_are_restored(self):
        self._write_history({"ts": "2026-10-20T10:00:00", "verdict": "PASS",
                             "layers": {"K1": "PASS"}})
        ps.LATEST["verdict"] = "UNKNOWN"
        self.assertTrue(ps.load_cached_latest())
        self.assertEqual(ps.LATEST["verdict"], "PASS")
        self.assertEqual(ps.LATEST["layers"], {"K1": "PASS"})
        self.assertTrue(ps.LATEST["cached"])

    def test_non_history_latest_keys_are_not_injected(self):
        self.assertIn("stdout", ps.LATEST)  # ön koşul: LATEST'te adı var
        self._write_history({"ts": "2026-10-20T10:00:00", "verdict": "PASS",
                             "stdout": "INJECTED", "stderr": "INJECTED",
                             "override_report": {"injected": True}})
        ps.LATEST["stdout"] = "ORIGINAL"
        ps.LATEST["override_report"] = None
        self.assertTrue(ps.load_cached_latest())
        self.assertEqual(ps.LATEST["stdout"], "ORIGINAL")
        self.assertIsNone(ps.LATEST["override_report"])
        self.assertNotEqual(ps.LATEST["stderr"], "INJECTED")


if __name__ == "__main__":
    unittest.main()
