#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_override_trend_badge.py — preview.html overrideTrendBadge() senkron kapısı.

Dashboard'un "CLI override trend" panelindeki rozet mantığını sabitler:
son run warning=true ise "⚠️ override VAR (N · keys)" (amber), değilse
"✓ override YOK" (yeşil); veri yoksa gri. Ayrıca panel elemanlarının
(ovr-trend-badge / ovr-trend svg) ve /api/override-trend fetch'inin
preview.html'de var olduğunu doğrular (drift guard).

overrideTrendBadge() preview.html'deki saf JS fonksiyonuyla BİREBİR senkron
tutulmalıdır — bu dosya JS'in Python karşılığını + HTML'de varlığı sabitler.
stdlib unittest — ek bağımlılık yok.
"""
import json
import pathlib
import re
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PREVIEW_HTML = SCRIPT_DIR / "preview.html"


def override_trend_badge(rows):
    """preview.html overrideTrendBadge() ile aynı mantık (Python karşılığı)."""
    have = [r for r in (rows or [])
            if isinstance(r, dict) and isinstance(r.get("warning"), bool)]
    if not have:
        return {"cls": "unknown", "text": "override: veri yok"}
    last = have[-1]
    if last.get("warning"):
        keys = [k for k in (last.get("override_keys") or []) if k]
        text = "⚠️ override VAR (%d" % (last.get("override_count") or 0)
        if keys:
            text += " · " + ",".join(keys)
        text += ")"
        return {"cls": "warn", "text": text}
    return {"cls": "ok", "text": "✓ override YOK"}


def _row(warning, count=0, keys=None):
    return {"warning": warning, "override_count": count,
            "override_keys": keys or []}


class TestOverrideTrendBadge(unittest.TestCase):
    def test_no_data_unknown(self):
        self.assertEqual(override_trend_badge(None),
                         {"cls": "unknown", "text": "override: veri yok"})
        self.assertEqual(override_trend_badge([]),
                         {"cls": "unknown", "text": "override: veri yok"})

    def test_non_boolean_warning_filtered(self):
        # warning alanı boolean olmayan satırlar seriden çıkarılır (bozuk veri).
        rows = [{"warning": "evet"}, _row(False)]
        b = override_trend_badge(rows)
        self.assertEqual(b["cls"], "ok")
        self.assertEqual(b["text"], "✓ override YOK")

    def test_last_warning_marks_badge(self):
        rows = [_row(False), _row(True, count=1, keys=["budget"])]
        b = override_trend_badge(rows)
        self.assertEqual(b["cls"], "warn")
        self.assertEqual(b["text"], "⚠️ override VAR (1 · budget)")

    def test_warning_without_keys(self):
        b = override_trend_badge([_row(True, count=2)])
        self.assertEqual(b["text"], "⚠️ override VAR (2)")

    def test_last_clean_ok_even_if_older_warning(self):
        rows = [_row(True, count=1, keys=["budget"]), _row(False)]
        b = override_trend_badge(rows)
        self.assertEqual(b["cls"], "ok")
        self.assertEqual(b["text"], "✓ override YOK")


class TestHtmlSync(unittest.TestCase):
    """preview.html'de panel + rozet fonksiyonu var; JS, Python'la aynı doku."""

    def test_js_function_present(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn("const OVERRIDE_COLOR_RULES", html)
        self.assertIn("OVERRIDE_COLOR_RULES.warning.color", html)
        self.assertIn("OVERRIDE_COLOR_RULES.clean.color", html)
        self.assertIn("function overrideTrendBadge(rows)", html)
        self.assertIn("function renderOverrideTrend(rows)", html)

    def test_panel_elements_present(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn('id="ovr-trend-badge"', html)
        self.assertIn('id="ovr-trend"', html)
        self.assertIn('id="ovr-trend-legend"', html)

    def test_fetch_endpoint_wired(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn('fetch("/api/override-trend")', html)

    def test_legend_uses_canonical_rule_labels(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn("OVERRIDE_COLOR_RULES.warning.label", html)
        self.assertIn("OVERRIDE_COLOR_RULES.clean.label", html)

    def test_js_uses_same_text_shapes(self):
        # Rozet metin kalıpları iki dilde birebir (drift guard).
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        for frag in ('"override: veri yok"', 'OVERRIDE_COLOR_RULES.clean.label',
                     '"⚠️ override VAR ("', "typeof r.warning === \"boolean\""):
            self.assertIn(frag, html, f"preview.html'de {frag!r} eksik")


if __name__ == "__main__":
    unittest.main()
