#!/usr/bin/env python3
"""test_consolidate_budget.py — consolidate_budget.py (bütçe konsolidasyonu)
regresyon kapısı.

budget/*.json sidecar'larının budget/index.json'da toplanmasını kapsar:
limit aşımı (verdict != OK) failures listesine düşer, any_fail doğru olur,
bozuk JSON atlanır, boş dizin boş özet üretir. CWD'ye bağımlıdır — her test
kendi geçici dizininde çalışır. stdlib unittest.
"""
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import consolidate_budget as cb  # noqa: E402


def _sidecar(p, verdict="OK", limit=30.0, est=1.08, tokens=175990, method="both"):
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"verdict": verdict, "limit": limit, "estimated_usd": est,
                   "tokens_est": tokens, "method": method,
                   "date": "2026-08-20T00:00:00Z"}, f)


class TestConsolidateBudget(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self._tmp.name)
        os.chdir(self.d)
        (self.d / "budget").mkdir()

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _run(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cb.main()
        with open("budget/index.json", encoding="utf-8") as f:
            index = json.load(f)
        return index, buf.getvalue()

    def test_all_ok_no_failures(self):
        _sidecar(self.d / "budget" / "a.json")
        _sidecar(self.d / "budget" / "b.json")
        index, _ = self._run()
        self.assertFalse(index["any_fail"])
        self.assertEqual(index["failures"], [])
        self.assertEqual(len(index["runs"]), 2)
        self.assertEqual({r["source"] for r in index["runs"]},
                         {"a.json", "b.json"})

    def test_over_limit_goes_to_failures(self):
        _sidecar(self.d / "budget" / "ok.json")
        _sidecar(self.d / "budget" / "over.json", verdict="FAIL",
                 limit=30.0, est=45.2, tokens=7000000)
        index, _ = self._run()
        self.assertTrue(index["any_fail"])
        self.assertEqual(len(index["failures"]), 1)
        f = index["failures"][0]
        self.assertEqual(f["source"], "over.json")
        self.assertEqual(f["estimated_usd"], 45.2)
        self.assertEqual(f["tokens_est"], 7000000)

    def test_invalid_json_skipped(self):
        (self.d / "budget" / "broken.json").write_text("{not json",
                                                       encoding="utf-8")
        _sidecar(self.d / "budget" / "ok.json")
        index, _ = self._run()
        self.assertEqual([r["source"] for r in index["runs"]], ["ok.json"])

    def test_empty_dir_empty_summary(self):
        index, _ = self._run()
        self.assertEqual(index["runs"], [])
        self.assertFalse(index["any_fail"])
        self.assertIsNone(index["date"])


if __name__ == "__main__":
    unittest.main()
