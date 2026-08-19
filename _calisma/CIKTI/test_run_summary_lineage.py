#!/usr/bin/env python3
"""test_run_summary_lineage.py — run_summary_lineage.py regresyon kapısı.

main() lineage_findings.json sidecar'ını GITHUB_STEP_SUMMARY/stdout'a yazar;
ok=TRUE → yeşil onay, ok=FALSE → kırmızı uyarı. stdlib unittest — ek
bağımlılık yok.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest

import run_summary_lineage as rsl


class TestIcon(unittest.TestCase):
    def test_pass_fail_info(self):
        self.assertEqual(rsl._icon("PASS (git show ile aynı)"), "✅")
        self.assertEqual(rsl._icon("FAIL"), "🔴")
        self.assertEqual(rsl._icon("INFO (dondurulmuş §9)"), "ℹ️")
        self.assertEqual(rsl._icon("UNVERIFIED (git yok)"), "ℹ️")


class TestMain(unittest.TestCase):
    def _run(self, path):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = rsl.main([path])
        return code, buf.getvalue()

    def _write(self, d, payload):
        p = os.path.join(d, "lineage_findings.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return p

    def test_ok_writes_confirm(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, {
                "ok": True,
                "count": 2,
                "generations": [
                    {"gen": "current", "note": "V5m", "hash": "a" * 64,
                     "commit": None, "status": "PASS (canlı dosya ile aynı)"},
                    {"gen": "pre-git", "note": "iCloud orijinal", "hash": "b" * 64,
                     "commit": None, "status": "INFO (dondurulmuş §9)"},
                ],
            })
            code, out = self._run(p)
        self.assertEqual(code, 0)
        self.assertIn("nesil doğrulandı", out)
        self.assertIn("PASS (canlı dosya ile aynı)", out)

    def test_fail_writes_warning(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, {
                "ok": False,
                "count": 1,
                "generations": [
                    {"gen": "current", "note": "V5m", "hash": "a" * 64,
                     "commit": None, "status": "FAIL"},
                ],
            })
            code, out = self._run(p)
        self.assertEqual(code, 0)
        self.assertIn("doğrulama başarısız", out)
        self.assertIn("🔴", out)

    def test_missing_file_is_advisory(self):
        code, out = self._run("nonexistent.json")
        self.assertEqual(code, 0)
        self.assertIn("sidecar bulunamadı", out)

    def test_pipe_in_note_escaped(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, {
                "ok": True,
                "count": 1,
                "generations": [
                    {"gen": "x", "note": "a|b", "hash": "c" * 64,
                     "commit": None, "status": "PASS (git show ile aynı)"},
                ],
            })
            code, out = self._run(p)
        self.assertEqual(code, 0)
        self.assertIn("a\\|b", out)


if __name__ == "__main__":
    unittest.main()
