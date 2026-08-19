#!/usr/bin/env python3
"""test_run_summary_klayers.py — run_summary_klayers.py regresyon kapısı.

main() klayers.json sidecar'ını GITHUB_STEP_SUMMARY/stdout'a yazar; her K1-K10
katmanı için PASS/FAIL/SKIP bölümü üretir. stdlib unittest — ek bağımlılık yok.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest

import run_summary_klayers as rsk


class TestMain(unittest.TestCase):
    def setUp(self):
        # CI'da GITHUB_STEP_SUMMARY set olduğunda summary_sink() dosyaya
        # yazar; bu testler stdout çıktısını doğrular — env'i temizle.
        self._saved = os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["GITHUB_STEP_SUMMARY"] = self._saved

    def _run(self, path):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = rsk.main([path])
        return code, buf.getvalue()

    def _write(self, d, layers):
        p = os.path.join(d, "klayers.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"verdict": "PASS", "counts": {"P0": 0, "P1": 0},
                       "layers": layers}, f, ensure_ascii=False)
        return p

    def _layer(self, status, findings=None):
        return {"label": "X", "status": status, "ran": status != "SKIP",
                "findings": findings or []}

    def test_all_pass_renders_ten_sections(self):
        layers = {k: self._layer("PASS") for k in rsk.RENDER_LAYERS}
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, layers)
            code, out = self._run(p)
        self.assertEqual(code, 0)
        # Her K1-K10 bölümü bir kez ve PASS rozetiyle
        for k in rsk.RENDER_LAYERS:
            self.assertIn(f"## ✅ {k}", out)
        self.assertEqual(out.count("PASS"), 10)

    def test_fail_renders_findings(self):
        layers = {k: self._layer("PASS") for k in rsk.RENDER_LAYERS}
        layers["K4"] = {"label": "Manifest 19/19", "status": "FAIL", "ran": True,
                        "findings": [
                            {"id": "K4-MANIFEST", "priority": "P0",
                             "check": "K4-MANIFEST", "issue": "MD5 uyuşmuyor: x",
                             "evidence": "expected=.. actual=.."},
                        ]}
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, layers)
            code, out = self._run(p)
        self.assertEqual(code, 0)
        self.assertIn("## 🔴 K4", out)
        self.assertIn("[P0] K4-MANIFEST: MD5 uyuşmuyor: x", out)

    def test_skip_renders_na(self):
        layers = {k: self._layer("PASS") for k in rsk.RENDER_LAYERS}
        layers["K10"] = self._layer("SKIP")
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, layers)
            code, out = self._run(p)
        self.assertEqual(code, 0)
        self.assertIn("## ⏭️ K10", out)
        self.assertIn("koşmadı", out)

    def test_missing_file_is_advisory(self):
        code, out = self._run("nonexistent.json")
        self.assertEqual(code, 0)
        self.assertIn("sidecar bulunamadı", out)


if __name__ == "__main__":
    unittest.main()
