#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_run_summary_refs_trend.py — run_summary_refs_trend.py regresyon kapısı.

render() refs-trend.md içeriğini GITHUB_STEP_SUMMARY/stdout'a taşır (tabloyu
yeniden üretmez — refs_trend.py tek kaynaktır). stdlib unittest — ek bağımlılık
yok.
"""
import contextlib
import io
import os
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import run_summary_refs_trend as rsrt  # noqa: E402


class TestRender(unittest.TestCase):
    def _run(self, md_path):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = False
            # render() doğrudan sink alır; stdout'u sink yap.
            ok = rsrt.render(buf, md_path)
        return ok, buf.getvalue()

    def test_transports_markdown_verbatim(self):
        md = "# Çevrimiçi Referans Doğrulama Trendi (refs-online)\n\n"
        md += "| # | Tarih | Run ID | Toplam |\n|---|---|---|---|\n"
        md += "| 1 | 2026-08-19 12:00 | 123 | 54 |\n"
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "refs-trend.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(md)
            ok, out = self._run(p)
        self.assertTrue(ok)
        # İçerik birebir taşınır (render çoğaltılmaz).
        self.assertIn(md.strip(), out)

    def test_missing_file_is_advisory(self):
        ok, out = self._run("nonexistent/refs-trend.md")
        self.assertFalse(ok)
        self.assertIn("tablo bulunamadı", out)


class TestSummarySinkLazy(unittest.TestCase):
    def test_env_read_at_call_time(self):
        # summary_sink() GITHUB_STEP_SUMMARY'yi çağrı anında okur (import
        # anında değil) — CI'da dosyaya, testte stdout'a yazar.
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "summary.md")
            os.environ["GITHUB_STEP_SUMMARY"] = p
            try:
                with rsrt.summary_sink() as s:
                    s.write("x")
            finally:
                del os.environ["GITHUB_STEP_SUMMARY"]
            with open(p, encoding="utf-8") as f:
                self.assertEqual(f.read(), "x")


if __name__ == "__main__":
    unittest.main()
