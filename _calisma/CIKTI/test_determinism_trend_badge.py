#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_determinism_trend_badge.py — determinism-trend panel sözleşmeleri.

Üç yüzü sabitler:
  1. Üretici (determinism_trend_badge.py): jsonl → satır-başına badge + SVG.
  2. Dashboard bağlantısı: preview.html'de bölüm, preview.js'de render + fetch,
     preview_server'da route + handler + API_CONTRACT.
  3. Handler davranışı: temp jsonl ile /api/determinism-trend = rows.
  4. AİLELER (2026-10-08): badge aile BAŞINA son kayda bakar — taze canvas
     satırı, bayat/FAILED manuscript serisini yeşile boyayamaz. JS ikizi
     (preview.js = JS_CODE) hem METİN hem node ile davranış eşitliğinde
     kilitlidir (node yoksa statik eşitlik katmanı yine de çalışır).

Ölçülen canlı örnek (2026-09-21):
  [{"date": "2026-09-17", "platform": "darwin", "texlive": "a75c3409…"},
   {"date": "2026-09-20", "platform": "linux",   "texlive": "092154a0…"},
   {"date": "2026-09-21", "platform": "linux",   "texlive": "092154a0…"}]

stdlib unittest — OFFLINE, temp dizinlerle izole.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import determinism_trend_badge as dtb  # noqa: E402
import preview_server as ps  # noqa: E402
import record_determinism_trend as rdt  # noqa: E402

ROW = {"date": "2026-09-17", "source_mtime": 1, "tectonic_bin": "/bin/tectonic",
       "texlive_bin": "/bin/pdflatex", "sde": 0, "platform": "darwin",
       "gate": "PASS",
       "tectonic_canonical_sha256": "ad8fca69" * 8,
       "texlive_canonical_sha256": "a75c3409" * 8,
       "source_sha256": "a9f34e05" * 8}


def _crow(**over):
    """Canvas satırı: family=canvas + texlive bacağı YOK (gerçek şema)."""
    r = dict(ROW)
    r.pop("texlive_canonical_sha256")
    r["family"] = "canvas"
    r.update(over)
    return r


def _js_block(text):
    """preview.js / JS_CODE içinden üç fonksiyonluk metni çıkarır (0. sütun
    kapanış süsüne kadar) — eşitlik iddiasının kaynağı."""
    a = text.index("function determinismTrendFamilyOf(row) {")
    b = text.index("\n}\n",
                   text.index("function determinismTrendRowTitle(r) {")) + 3
    return text[a:b]


NODE_RUNNER = """
const fs = require("fs");
const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const out = {
  badges: cases.badges.map((r) => determinismTrendBadge(r)),
  titles: cases.titles.map((r) => determinismTrendRowTitle(r)),
};
fs.writeFileSync(process.argv[3], JSON.stringify(out));
"""


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


class TestFamilyBadge(unittest.TestCase):
    """Aile ayrımı: taze/temiz bir aile, diğer ailenin kırmızısını kapatamaz."""

    def test_fresh_canvas_cannot_mask_failing_manuscript(self):
        # BAŞLIK fail-open regresyonu: rows[-1] canvas satırı PASS → eski
        # (aile ayrımı yok) kod yeşil dönerdi.
        rows = [_row("2026-09-17", "darwin", "a75c3409" * 8, gate="FAIL"),
                _crow(date="2026-10-08", platform="darwin", gate="PASS")]
        b = dtb.badge(rows)
        self.assertEqual(b["cls"], "warn")
        self.assertIn("manuscript FAIL", b["text"])
        self.assertNotEqual(b["cls"], "ok")

    def test_failing_canvas_is_named(self):
        rows = [_row("2026-10-01", "linux", "092154a0" * 8),
                _crow(date="2026-10-08", gate="FAIL")]
        b = dtb.badge(rows)
        self.assertEqual(b["cls"], "warn")
        self.assertIn("canvas FAIL", b["text"])

    def test_all_pass_keeps_total_count(self):
        rows = [_row("2026-09-17", "darwin", "a75c3409" * 8),
                _row("2026-09-21", "linux", "092154a0" * 8),
                _crow(date="2026-10-08")]
        self.assertEqual(dtb.badge(rows),
                         {"cls": "ok",
                          "text": "✓ DETERMİNİZM PASS · 3 ölçüm"})

    def test_row_level_badge_stays_single_family(self):
        # build_json / handler satır-başına badge üretir (tek satır = tek
        # aile) → biçim eskisiyle birebir aynı.
        self.assertEqual(
            dtb.badge([_crow(date="2026-10-08", gate="FAIL")]),
            {"cls": "warn", "text": "⚠️ determinizm gate FAIL · 1 ölçüm"})

    def test_family_rule_matches_recorder(self):
        # İki bağımsız uygulama (badge + üretici) aynı kurala uymalı:
        # alan yoksa/boşsa/düşükse → manuscript.
        for row in ({}, {"family": ""}, {"family": "canvas"}, {"family": 42},
                    dict(ROW), _crow()):
            self.assertEqual(dtb.family_of(row), rdt.family_of(row),
                             repr(row))
        self.assertEqual(dtb.family_of({"family": "canvas"}), "canvas")

    def test_row_title_family_and_missing_leg(self):
        t = dtb._row_title(_crow(date="2026-10-08"))
        self.assertIn("canvas", t)
        self.assertIn("tectonic ad8fca69", t)
        self.assertNotIn("texlive", t)   # canvas'ta texlive bacağı yoktur
        m = dtb._row_title(_row("2026-09-17", "darwin", "a75c3409" * 8))
        self.assertIn("manuscript", m)
        self.assertIn("texlive a75c3409", m)

    def test_svg_chain_skips_cross_family(self):
        # İZOLE fixture: canvas satırına texlive alanı BİLEREK eklenir. Gerçek
        # şemada canvas texlive taşımaz, yani alan-varlığı-farkı zaten çizgiyi
        # keserdi ve guard'ın kendisi sınanmazdı (mutation: guard kaldırılınca
        # test yeşil kalıyordu — bu düzeltme onu kırmızıya çevirdi). Artık tek
        # farklanan değişken AİLE'dir: aile eşitliği olmasa 2. çift de çizilir.
        same_tex, same_tec = "a75c3409" * 8, "ad8fca69" * 8
        rows = [_row("2026-10-01", "darwin", same_tex, tectonic=same_tec),
                _crow(date="2026-10-05", texlive_canonical_sha256=same_tex,
                      tectonic=same_tec),
                _crow(date="2026-10-08", texlive_canonical_sha256=same_tex,
                      tectonic=same_tec)]
        self.assertEqual(dtb.svg(rows).count("<line "), 1)   # yalnız canvas içi
        # Pozitif kontrol: tek aile, aynı hash → zincir gerçekten çizilir (2).
        same_family = [_crow(date="2026-10-05", tectonic=same_tec),
                       _crow(date="2026-10-06", tectonic=same_tec),
                       _crow(date="2026-10-08", tectonic=same_tec)]
        self.assertEqual(dtb.svg(same_family).count("<line "), 2)


class TestJsPythonParity(unittest.TestCase):
    """JS ikizi: metin eşitliği (statik, node'suz) + node davranışı eşitliği."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(SCRIPT_DIR, "preview.js"), encoding="utf-8") as f:
            cls.preview_src = f.read()
        cls.js_preview = _js_block(cls.preview_src)
        cls.js_code = _js_block(dtb.JS_CODE)

    def test_js_functions_byte_identical_to_js_code(self):
        # preview.js (çalışan) ile JS_CODE (--update-preview kaynağı) birebir
        # aynı: biri değişince/elle bozulunca kırmızı. Statik katman — node
        # olmadan da çalışır.
        self.assertEqual(self.js_preview, self.js_code)
        self.assertIn("determinismTrendFamilyOf", self.js_preview)
        self.assertIn("determinismTrendRowTitle", self.js_preview)

    def test_js_render_is_family_aware(self):
        # Zincir koşulu ve tooltip gövde içinde (üç fonksiyonun DIŞINDA) —
        # o yüzden statik olarak ayrı kilitlenir.
        for src in (self.preview_src, dtb.JS_CODE):
            self.assertIn(
                "determinismTrendFamilyOf(a) === determinismTrendFamilyOf(b2)",
                src)
            self.assertIn("${determinismTrendRowTitle(r)}", src)

    @unittest.skipUnless(shutil.which("node"), "node yok — statik test yeter")
    def test_js_and_python_agree_on_fixtures(self):
        badge_cases = [
            [],
            [_row("2026-09-17", "darwin", "a75c3409" * 8)],
            [_row("2026-09-17", "darwin", "a75c3409" * 8),
             _row("2026-09-20", "linux", "092154a0" * 8),
             _row("2026-09-21", "linux", "092154a0" * 8)],
            [_row("2026-09-17", "darwin", "a75c3409" * 8, gate="FAIL"),
             _crow(date="2026-10-08", gate="PASS")],
            [_row("2026-10-01", "linux", "092154a0" * 8, gate="PASS"),
             _crow(date="2026-10-08", gate="FAIL")],
            [_row("2026-10-01", "linux", "092154a0" * 8),
             _crow(date="2026-10-08")],
            [_crow(date="2026-10-08", gate="FAIL")],
            [{"family": "canvas", "gate": "PASS"}],
            [{"family": "", "gate": None}],
        ]
        title_cases = [
            _row("2026-09-17", "darwin", "a75c3409" * 8),
            _crow(date="2026-10-08", platform="linux"),
            {"date": "2026-10-08", "family": "canvas",
             "tectonic_canonical_sha256": "abcdef12" * 8},
            {"family": "", "date": "2026-10-08"},
        ]
        expected = {"badges": [dtb.badge(r) for r in badge_cases],
                    "titles": [dtb._row_title(r) for r in title_cases]}
        with tempfile.TemporaryDirectory() as td:
            js = os.path.join(td, "parity.js")
            with open(js, "w", encoding="utf-8") as f:
                f.write(self.js_preview + "\n" + NODE_RUNNER)
            payload = os.path.join(td, "in.json")
            out = os.path.join(td, "out.json")
            with open(payload, "w", encoding="utf-8") as f:
                json.dump({"badges": badge_cases, "titles": title_cases}, f)
            r = subprocess.run(["node", js, payload, out],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            with open(out, encoding="utf-8") as f:
                got = json.load(f)
        self.assertEqual(got, expected)


if __name__ == "__main__":
    unittest.main()
