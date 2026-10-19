#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_run_summary_k9.py — run_summary_k9.py sözleşme kapısı.

K9 lake build logu (verify_lean_lake.sh `tee` çıktısı — tek kaynak) run
summary'ye "K9 lake build" bölümü ve durum panosu satırı olarak taşınır.
Sözleşme fail-closed:

  1) PASS: log `[K9-LAKE] PASS` içerir → status=PASS, bölüm ✅ + marker'lar.
  2) FAIL: log `[K9-LAKE] FAIL` içerir → status=FAIL, bölüm 🔴 + hata satırları.
  3) Fail-closed verdict: log var ama HİÇ verdict yok (timeout/kesilme) →
     status=FAIL — PASS asla türetilmez.
  4) MISSING: log yok → status=MISSING, advisory not (exit 0).
  5) Pano entegrasyonu: consolidate_summary SECTIONS'inde "k9" kaydı ve
     DEFAULT_PATHS["k9"] = "lean_lake_build.log" (tek kaynak yolu).

stdlib-only, OFFLINE.
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

import run_summary_k9 as rk9  # noqa: E402

PASS_LOG = (
    "[K9-LAKE] START — lake clean && lake build --wfail\n"
    "info: lake clean\n"
    "[K9-LAKE] PASS — Lean project build completed\n"
)
FAIL_LOG = (
    "[K9-LAKE] START — lake clean && lake build --wfail\n"
    "[K9-LAKE] FAIL — lake build hatası (exit 1)\n"
    "error: build failed\n"
)
PARTIAL_LOG = "[K9-LAKE] START — lake clean && lake build --wfail\n"


class TestRunSummaryK9(unittest.TestCase):
    def _log(self, d, text):
        p = pathlib.Path(d)
        p.mkdir(parents=True, exist_ok=True)
        f = p / "lean_lake_build.log"
        f.write_text(text, encoding="utf-8")
        return str(f)

    def test_status_pass_fail_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(rk9.status(self._log(d, PASS_LOG)), "PASS")
            self.assertEqual(rk9.status(self._log(d, FAIL_LOG)), "FAIL")
            self.assertEqual(
                rk9.status(str(pathlib.Path(d) / "yok.log")), "MISSING")

    def test_status_partial_log_is_fail_closed(self):
        # Verdict'süz log (timeout/kesilme) PASS sayılmaz.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(rk9.status(self._log(d, PARTIAL_LOG)), "FAIL")

    def test_render_pass_section(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            verdict = rk9.render(buf, self._log(d, PASS_LOG))
            out = buf.getvalue()
        self.assertEqual(verdict, "PASS")
        self.assertIn("## ✅ K9 lake build: PASS", out)
        self.assertIn("[K9-LAKE] PASS — Lean project build completed", out)

    def test_render_fail_section_with_error_lines(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            verdict = rk9.render(buf, self._log(d, FAIL_LOG))
            out = buf.getvalue()
        self.assertEqual(verdict, "FAIL")
        self.assertIn("## 🔴 K9 lake build: FAIL", out)
        self.assertIn("[K9-LAKE] FAIL", out)
        self.assertIn("error: build failed", out)

    def test_render_missing_is_advisory(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            verdict = rk9.render(buf, str(pathlib.Path(d) / "yok.log"))
            out = buf.getvalue()
        self.assertEqual(verdict, "MISSING")
        self.assertIn("K9 lake build: log bulunamadı", out)

    def test_render_partial_log_explains_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            verdict = rk9.render(buf, self._log(d, PARTIAL_LOG))
            out = buf.getvalue()
        self.assertEqual(verdict, "FAIL")
        self.assertIn("verdict işareti yok", out)

    def test_consolidate_registers_k9_single_source(self):
        # Tek kaynak: bölüm kaydı + varsayılan log yolu (verify job cwd = repo
        # kökü; lake adımı `tee lean_lake_build.log` ile AYNI adı yazar).
        import consolidate_summary as cs
        keys = [name for name, _label, _r, _s in cs.SECTIONS]
        self.assertIn("k9", keys)
        idx = keys.index("k9")
        self.assertLess(idx, keys.index("k12"))
        self.assertGreater(idx, keys.index("klayers"))
        label = [lbl for name, lbl, _r, _s in cs.SECTIONS if name == "k9"][0]
        self.assertEqual(label, "K9 lake build")
        self.assertEqual(cs.DEFAULT_PATHS["k9"], "lean_lake_build.log")

    def test_status_board_icons_via_consolidate(self):
        # Pano satırı K9 için ✅/🔴/⚠️ üretir (SECTIONS status akışı).
        import consolidate_summary as cs
        sections = {name: (label, status)
                    for name, label, _r, status in cs.SECTIONS}
        label, status = sections["k9"]
        with tempfile.TemporaryDirectory() as d:
            # Ayrı alt dizinler: aynı dosya adını ezmek status okumasını bozar.
            ok = self._log(pathlib.Path(d) / "ok", PASS_LOG)
            bad = self._log(pathlib.Path(d) / "bad", FAIL_LOG)
            absent = str(pathlib.Path(d) / "absent" / "yok.log")
            self.assertEqual(status(ok), "PASS")
            self.assertEqual(status(bad), "FAIL")
            self.assertEqual(status(absent), "MISSING")
        self.assertEqual(label, "K9 lake build")


if __name__ == "__main__":
    unittest.main()
