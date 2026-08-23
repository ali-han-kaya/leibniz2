#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_refs_trend_badge.py — preview.html refsTrendBadge() senkron kapısı.

Dashboard'un refs-trend panelindeki "Tam kapsam" rozeti mantığını sabitler:
son run full (refs_verified === refs_total) ise yeşil "✓ TAM KAPSAM" rozeti
+ kesintisiz full run serisi; değilse amber "kapsam eksik"; veri yoksa gri.

refsTrendBadge() preview.html'deki saf JS fonksiyonuyla BİREBİR senkron
tutulmalıdır — bu dosya JS'in Python karşılığını + preview.html'de fonksiyonun
var olduğunu doğrular (drift guard). stdlib unittest — ek bağımlılık yok.
"""
import json
import pathlib
import re
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PREVIEW_HTML = SCRIPT_DIR / "preview.html"


def refs_trend_badge(rows):
    """preview.html refsTrendBadge() ile aynı mantık (Python karşılığı)."""
    have = [r for r in (rows or [])
            if r.get("refs_verified") is not None
            and r.get("refs_total") is not None]
    if not have:
        return {"cls": "unknown", "text": "tam kapsam: veri yok"}
    last = have[-1]

    def full(r):
        return r["refs_verified"] == r["refs_total"]

    streak = 0
    for r in reversed(have):
        if not full(r):
            break
        streak += 1
    if full(last):
        text = ("✓ TAM KAPSAM %d/%d" % (last["refs_verified"], last["refs_total"]))
        if streak > 1:
            text += " · %d run" % streak
        return {"cls": "ok", "text": text}
    return {"cls": "warn",
            "text": "kapsam eksik %d/%d" % (last["refs_verified"],
                                            last["refs_total"])}


def _row(v, t):
    return {"refs_verified": v, "refs_total": t}


class TestRefsTrendBadge(unittest.TestCase):
    def test_no_data_unknown(self):
        self.assertEqual(refs_trend_badge(None), {"cls": "unknown",
                                                  "text": "tam kapsam: veri yok"})
        self.assertEqual(refs_trend_badge([]), {"cls": "unknown",
                                                "text": "tam kapsam: veri yok"})

    def test_none_fields_filtered(self):
        # refs_verified/total None olan satırlar seriden çıkarılır.
        rows = [{"refs_verified": None, "refs_total": None}, _row(61, 61)]
        b = refs_trend_badge(rows)
        self.assertEqual(b["cls"], "ok")
        self.assertEqual(b["text"], "✓ TAM KAPSAM 61/61")

    def test_single_full_run(self):
        # Tek full run → streak 1 → "· N run" SÜFİKSİ YOK.
        b = refs_trend_badge([_row(61, 61)])
        self.assertEqual(b["cls"], "ok")
        self.assertEqual(b["text"], "✓ TAM KAPSAM 61/61")

    def test_consecutive_full_streak(self):
        # Son 2 run kesintisiz full → seri süfiksi (önceki eksik seriyi keser).
        rows = [_row(60, 61), _row(61, 61), _row(61, 61)]
        b = refs_trend_badge(rows)
        self.assertEqual(b["cls"], "ok")
        self.assertEqual(b["text"], "✓ TAM KAPSAM 61/61 · 2 run")

    def test_streak_resets_on_partial(self):
        # Araya eksik kapsam girerse seri sıfırlanır (son full yine ok).
        rows = [_row(60, 61), _row(61, 61), _row(61, 61)]
        b = refs_trend_badge(rows)
        self.assertEqual(b["cls"], "ok")
        self.assertEqual(b["text"], "✓ TAM KAPSAM 61/61 · 2 run")

    def test_last_partial_warn(self):
        rows = [_row(61, 61), _row(60, 61)]
        b = refs_trend_badge(rows)
        self.assertEqual(b["cls"], "warn")
        self.assertEqual(b["text"], "kapsam eksik 60/61")

    def test_today_61_61_series(self):
        # Bugünkü canlı seri: son 3 run 61/61 (önceki eksik seriyi keser).
        rows = [_row(60, 61), _row(61, 61), _row(61, 61), _row(61, 61)]
        b = refs_trend_badge(rows)
        self.assertEqual(b["cls"], "ok")
        self.assertEqual(b["text"], "✓ TAM KAPSAM 61/61 · 3 run")


class TestHtmlSync(unittest.TestCase):
    """preview.html'de fonksiyon + rozet elemanı var; JS, Python'la aynı doku."""

    def test_js_function_present(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn("function refsTrendBadge(rows)", html)

    def test_badge_element_present(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn('id="refs-trend-badge"', html)

    def test_js_uses_same_text_shapes(self):
        # Rozet metin kalıpları iki dilde birebir (drift guard).
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        for frag in ('"✓ TAM KAPSAM "', '"kapsam eksik "',
                     '"tam kapsam: veri yok"', "refs_verified === r.refs_total"):
            self.assertIn(frag, html, f"preview.html'de {frag!r} eksik")


if __name__ == "__main__":
    unittest.main()
