#!/usr/bin/env python3
"""test_incidental_banner.py — Incidental Proof header-banner sözleşmesi.

Banner = canvas/incidental_proof_banner.svg'in preview.html header'ına
data-URI ile gömülü dekoratif-katmanı. Üç sözleşmeyi sabitler:

  1) Tek-kaynak + gömülme: banner-SVG diskte durur; preview.html'deki
     data-URI bunun birebir base64'üdür (drift = fail). Aracı yok —
     el-yazımı base64 bozulursa test kırılır (fail-closed).
  2) CSP/boyut disiplini: img-src data: CSP izniyle uyum (svg+xml),
     katman CSS background-image'dır (AT'ye görünmez → aria-hidden
     eşdeğeri); header interaktif-çocukları z-index:1 ile dokunulmaz.
  3) Kontrast-koruma: her iki temada katman-opaklığı eşik-altında
     (dark ≤ .18, light ≤ .25) — metin-kontrastını düşürmez; ayrıca
     banner-SVG'nin vermilion'u tek (testifies-only) kalır.

Çalıştırma: python3 -m unittest _calisma.CIKTI.test_incidental_banner
"""
import base64
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

BANNER_PATH = os.path.join(HERE, "canvas", "incidental_proof_banner.svg")
HTML_PATH = os.path.join(HERE, "preview.html")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestBannerEmbedding(unittest.TestCase):
    """Tek-kaynak zinciri: banner.svg → data-URI → header::after."""

    def setUp(self):
        self.svg = _read(BANNER_PATH)
        self.html = _read(HTML_PATH)
        self.expected_uri = "data:image/svg+xml;base64," + base64.b64encode(
            self.svg.encode("utf-8")
        ).decode("ascii")

    def test_banner_svg_exists_and_is_svg(self):
        self.assertIn("<svg", self.svg)
        self.assertIn('viewBox="0 0 1440 160"', self.svg)

    def test_data_uri_matches_disk_svg_byte_for_byte(self):
        # Gömülü URI diskteki SVG'in birebir base64'ü olmalı —
        # el-değmesi/drift olmadan yeniden-üretilebilir.
        self.assertIn(self.expected_uri, self.html)

    def test_banner_used_in_header_pseudo_layer(self):
        # Katman header::after'da yaşar (dekoratif; DOM-düğümü yok →
        # aria-hidden gerekmez, AT ağacına hiç girmez).
        m = re.search(r"header::after\s*\{[^}]*\}", self.html)
        self.assertIsNotNone(m, "header::after katmanı yok")
        block = m.group(0)
        self.assertIn("background-image", block)
        self.assertIn("pointer-events:none", block)

    def test_header_children_above_layer(self):
        # Interaktif-çocuklar katmanın üstünde: z-index:1 (tıklama/odak
        # dokunulmazlığı — banner asla hedef çalmaz).
        self.assertRegex(self.html, r"header\s*>\s*\*\s*\{\s*position:relative;\s*z-index:1;")


class TestBannerContrastBudget(unittest.TestCase):
    """Kontrast-koruma: katman opaklığı tema-başına eşiğin altında."""

    def setUp(self):
        self.html = _read(HTML_PATH)

    def _opacity_of(self, selector_fragment):
        m = re.search(
            re.escape(selector_fragment) + r"[^}]*opacity:\s*([0-9.]+)", self.html
        )
        self.assertIsNotNone(m, f"opaklık bulunamadı: {selector_fragment}")
        return float(m.group(1))

    def test_dark_theme_opacity_under_threshold(self):
        self.assertLessEqual(self._opacity_of("header::after"), 0.18)

    def test_light_theme_opacity_under_threshold(self):
        self.assertLessEqual(
            self._opacity_of(':root[data-theme="light"] header::after'), 0.25
        )


class TestBannerVermilionDiscipline(unittest.TestCase):
    """Levha-disiplini banner'da yaşar: vermilion tek, sadece şahitlik."""

    def setUp(self):
        self.svg = _read(BANNER_PATH)

    def test_vermilion_is_the_only_saturated_voice(self):
        # Üç-ses paleti: fathom tonları + vermilion; dördüncü doygun-renk yok.
        colors = {"#" + c.upper() for c in re.findall(r"#([0-9A-Fa-f]{6})", self.svg)}
        verm = "#C1440E"
        self.assertIn(verm, colors)
        saturated = {
            c
            for c in colors
            if c != verm and self._saturation(c) > 0.35
        }
        self.assertEqual(saturated, set(), f"dördüncü doygun-renk: {saturated}")

    @staticmethod
    def _saturation(hex6):
        h = hex6.lstrip("#")
        r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
        mx, mn = max(r, g, b), min(r, g, b)
        return 0 if mx == 0 else (mx - mn) / mx


if __name__ == "__main__":
    unittest.main()
