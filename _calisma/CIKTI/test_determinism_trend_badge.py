#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_determinism_trend_badge.py — determinism-trend panel sözleşmeleri.

Üç yüzü sabitler:
  1. Üretici (determinism_trend_badge.py): jsonl → satır-başına badge + SVG.
  2. Dashboard bağlantısı: preview.html'de bölüm, preview.js'de render + fetch,
     preview_server'da route + handler + API_CONTRACT.
  3. Handler davranışı: temp jsonl ile /api/determinism-trend = rows.

Ölçülen canlı örnek (2026-09-21):
  [{"date": "2026-09-17", "platform": "darwin", "texlive": "a75c3409…"},
   {"date": "2026-09-20", "platform": "linux",   "texlive": "092154a0…"},
   {"date": "2026-09-21", "platform": "linux",   "texlive": "092154a0…"}]

stdlib unittest — OFFLINE, temp dizinlerle izole.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import determinism_trend_badge as dtb  # noqa: E402
import preview_server as ps  # noqa: E402

ROW = {"date": "2026-09-17", "source_mtime": 1, "tectonic_bin": "/bin/tectonic",
       "texlive_bin": "/bin/pdflatex", "sde": 0, "platform": "darwin",
       "gate": "PASS",
       "tectonic_canonical_sha256": "ad8fca69" * 8,
       "texlive_canonical_sha256": "a75c3409" * 8,
       "source_sha256": "a9f34e05" * 8}


def _row(date, platform, texlive, tectonic="ad8fca69" * 8, gate="PASS"):
    r = dict(ROW)
    r["date"], r["platform"] = date, platform
    r["texlive_canonical_sha256"] = texlive
    r["tectonic_canonical_sha256"] = tectonic
    r["gate"] = gate
    return r


class TestBadgeAndPlot(unittest.TestCase):
    def test_empty_and_missing_file(self):
        self.assertEqual(dtb.badge([]), {"cls": "unknown",
                                         "text": "determinizm: veri yok"})
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(dtb.rows_from(
                os.path.join(td, "missing.jsonl")))

    def test_malformed_lines_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "trend.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write("{broken json\n")
                f.write(json.dumps(_row("2026-09-17", "darwin",
                                        "a75c3409" * 8)) + "\n")
                f.write("\n")
            rows = dtb.rows_from(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(dtb.badge(rows)["cls"], "ok")

    def test_single_record_green_no_streak_suffix(self):
        b = dtb.badge([_row("2026-09-17", "darwin", "a75c3409" * 8)])
        self.assertEqual(b, {"cls": "ok",
                             "text": "✓ DETERMİNİZM PASS · 1 ölçüm"})

    def test_streak_counts_all_records(self):
        rows = [_row("2026-09-17", "darwin", "a75c3409" * 8),
                _row("2026-09-20", "linux", "092154a0" * 8),
                _row("2026-09-21", "linux", "092154a0" * 8)]
        self.assertEqual(dtb.badge(rows),
                         {"cls": "ok", "text": "✓ DETERMİNİZM PASS · 3 ölçüm"})

    def test_bad_gate_amber(self):
        rows = [_row("2026-09-17", "darwin", "a75c3409" * 8),
                _row("2026-09-21", "linux", "092154a0" * 8, gate="FAIL")]
        b = dtb.badge(rows)
        self.assertEqual(b["cls"], "warn")
        self.assertEqual(b["text"], "⚠️ determinizm gate FAIL · 2 ölçüm")

    def test_svg_stable_and_marks_points(self):
        rows = [_row("2026-09-17", "darwin", "a75c3409" * 8),
                _row("2026-09-21", "linux", "092154a0" * 8)]
        svg = dtb.svg(rows)
        self.assertIn("<svg", svg)
        self.assertIn("<circle", svg)
        self.assertIn("092154a0", svg)  # hash öneki tooltip'te
        # Deterministik: aynı veri → aynı çıktı (stat/snapshot tuzaklarına kapalı).
        self.assertEqual(svg, dtb.svg(rows))


class TestDashboardWiring(unittest.TestCase):
    """preview.html/preview.js/preview_server: bölüm + render + endpoint."""

    def _src(self, name):
        with open(os.path.join(SCRIPT_DIR, name), encoding="utf-8") as f:
            return f.read()

    def test_html_section_present(self):
        html = self._src("preview.html")
        self.assertIn('id="det-trend"', html)
        self.assertIn('id="det-trend-badge"', html)
        self.assertIn('id="det-trend-legend"', html)

    def test_js_render_and_fetch_present(self):
        js = self._src("preview.js")
        self.assertIn("function renderDeterminismTrend(rows)", js)
        self.assertIn('fetch("/api/determinism-trend")', js)

    def test_server_route_and_contract(self):
        src = self._src("preview_server.py")
        self.assertIn('if p == "/api/determinism-trend":', src)
        self.assertIn('return "det_trend"', src)
        self.assertIn('elif route == "det_trend":', src)
        self.assertIn('def serve_determinism_trend(self):', src)
        self.assertIn('DETERMINISM_TREND_PATH', src)
        contract = self._src("test_api_method_contract.py")
        self.assertIn('"/api/determinism-trend": {"GET"},', contract)
        self.assertIn('"/api/determinism-trend": \'"det_trend"\'', contract)
        self.assertIn('"/api/determinism-trend": "/api/determinism-trend",',
                      contract)

    def test_handler_serves_rows_from_temp_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "trend.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps(_row("2026-09-17", "darwin",
                                        "a75c3409" * 8)) + "\n")
            sent = {}

            class Resp:
                def __init__(self, code, body, content_type):
                    sent.update(code=code, body=body)

            with mock.patch.object(ps, "DETERMINISM_TREND_PATH", p), \
                 mock.patch.object(ps.Handler, "_send",
                                   side_effect=lambda code, body,
                                   content_type=None: sent.update(
                                       code=code, body=body)):
                h = object.__new__(ps.Handler)
                h.serve_determinism_trend()
            self.assertEqual(sent["code"], 200)
            data = json.loads(sent["body"])
            self.assertEqual(data["rows"][0]["date"], "2026-09-17")
            self.assertEqual(data["rows"][0]["badge"]["cls"], "ok")

    def test_handler_missing_file_serves_empty_rows(self):
        sent = {}
        with mock.patch.object(ps, "DETERMINISM_TREND_PATH", None), \
             mock.patch.object(ps.Handler, "_send",
                               side_effect=lambda code, body,
                               content_type=None: sent.update(
                                   code=code, body=body)):
            h = object.__new__(ps.Handler)
            h.serve_determinism_trend()
        self.assertEqual(sent["code"], 200)
        data = json.loads(sent["body"])
        self.assertEqual(data["rows"], [])
        self.assertEqual(data["badge"]["cls"], "unknown")


class TestGeneratorCli(unittest.TestCase):
    def test_cli_writes_svg_and_json_from_temp_trend(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "trend.jsonl")
            with open(src, "w", encoding="utf-8") as f:
                f.write(json.dumps(_row("2026-09-17", "darwin",
                                        "a75c3409" * 8)) + "\n")
                f.write(json.dumps(_row("2026-09-21", "linux",
                                        "092154a0" * 8)) + "\n")
            out = os.path.join(td, "out")
            rc = dtb.main(["--out-dir", out, "--trend", src, "--quiet"])
            self.assertEqual(rc, 0)
            with open(os.path.join(out, "determinism-trend.svg"),
                      encoding="utf-8") as f:
                self.assertIn("<svg", f.read())
            with open(os.path.join(out, "determinism-trend.json"),
                      encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data["rows"]), 2)
            self.assertEqual(data["badge"]["cls"], "ok")


if __name__ == "__main__":
    unittest.main()
