#!/usr/bin/env python3
import json
import os
import pathlib
import tempfile
import unittest

import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import preview_server as ps


class HistorySourceTests(unittest.TestCase):
    def test_run_history_keeps_smoke_and_daemon_sources(self):
        old_runs, old_path = ps.RUNS_DIR, ps.HISTORY_PATH
        try:
            with tempfile.TemporaryDirectory() as td:
                ps.RUNS_DIR = os.path.join(td, "runs")
                ps.HISTORY_PATH = os.path.join(td, "history.jsonl")
                with open(ps.HISTORY_PATH, "w", encoding="utf-8") as f:
                    for source in ("smoke", "daemon"):
                        f.write(json.dumps({"ts": source, "source": source,
                                            "verdict": "PASS"}) + "\n")
                records = ps.load_history()
                self.assertEqual([r["source"] for r in records], ["smoke", "daemon"])
        finally:
            ps.RUNS_DIR, ps.HISTORY_PATH = old_runs, old_path

    def test_dashboard_contains_source_badge_contract(self):
        html = (pathlib.Path(__file__).resolve().parent / "preview.html").read_text()
        self.assertIn(".source-badge.smoke", html)
        self.assertIn(".source-badge.daemon", html)
        self.assertIn('r.source || "daemon"', html)


if __name__ == "__main__":
    unittest.main()
