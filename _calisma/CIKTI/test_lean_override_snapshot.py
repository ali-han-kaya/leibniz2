#!/usr/bin/env python3
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import preview_server as ps


class LeanOverrideSnapshotTests(unittest.TestCase):
    def test_finalize_exposes_lean_override_and_source(self):
        old = {k: ps.LATEST.get(k) for k in ("lean_override", "lean_source")}
        try:
            payload = json.dumps({
                "verdict": "PASS", "counts": {"P0": 0, "P1": 0},
                "lean_override": {"requested": True, "ok": True},
                "lean_source": "history",
            })
            ps._finalize_run(payload, "", 0, 0.1, data=None, verify_dir=None)
            self.assertEqual(ps.LATEST["lean_override"],
                             {"requested": True, "ok": True})
            self.assertEqual(ps.LATEST["lean_source"], "history")
            snapshot = ps.snapshot_dict()
            self.assertEqual(snapshot["lean_override"]["ok"], True)
            self.assertEqual(snapshot["lean_source"], "history")
        finally:
            ps.LATEST.update(old)

    def test_run_history_serializes_both_fields(self):
        old_runs, old_path = ps.RUNS_DIR, ps.HISTORY_PATH
        try:
            with tempfile.TemporaryDirectory() as td:
                ps.RUNS_DIR = os.path.join(td, "runs")
                ps.HISTORY_PATH = os.path.join(td, "history.jsonl")
                ps.persist_run_log({"ts": "2026-01-01T00:00:00Z",
                                    "lean_override": {"ok": False},
                                    "lean_source": "history",
                                    "verdict": "FAIL"})
                rows = ps.load_run_logs()
                self.assertEqual(rows[0]["lean_override"]["ok"], False)
                self.assertEqual(rows[0]["lean_source"], "history")
        finally:
            ps.RUNS_DIR, ps.HISTORY_PATH = old_runs, old_path


if __name__ == "__main__":
    unittest.main()
