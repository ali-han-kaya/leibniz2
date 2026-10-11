#!/usr/bin/env python3
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
HTML = ROOT / "preview.html"
JS = ROOT / "preview.js"
SLIDES = ROOT / "slides_z3"
EXPECTED = ("P1-a", "P1-b", "P2", "P3-a", "P3-b", "P4-a", "P4-b",
            "P4-c", "P4-d", "P4-e", "P5", "P5-note",
            "incidental_proof_book_cover-1")


class TestZ3SlideGallery(unittest.TestCase):
    def test_gallery_references_all_generated_slides(self):
        text = HTML.read_text(encoding="utf-8")
        refs = re.findall(r'src="/slides_z3/([^"/]+)\.png"', text)
        self.assertEqual(tuple(refs), EXPECTED)
        self.assertTrue(all((SLIDES / f"{name}.png").is_file() for name in EXPECTED))

    def test_gallery_is_accessible_and_lazy(self):
        text = HTML.read_text(encoding="utf-8")
        self.assertIn('id="z3-slide-gallery"', text)
        self.assertEqual(text.count('loading="lazy"'), len(EXPECTED))
        for name in EXPECTED:
            self.assertIn(f'src="/slides_z3/{name}.png"', text)
            self.assertRegex(text, rf'<img src="/slides_z3/{re.escape(name)}\.png" alt="[^"]+"( width="\d+" height="\d+")? loading="lazy">')

    def test_series_tab_uses_aria_tab_contract(self):
        text = HTML.read_text(encoding="utf-8")
        # Aynı galeride tek tablist; iki sekme, tam biri seçili.
        self.assertIn('role="tablist" aria-label="Galeri sekmeleri"', text)
        self.assertEqual(text.count('role="tab"'), 2)
        # CSS seçicisi de aynı metni taşır; sayım yalnız düğüm işaretlemesinde.
        selected = re.findall(r'<button[^>]*aria-selected="true"', text)
        self.assertEqual(len(selected), 1)
        # Seri sekmesi kayan tabindex ile başlar (seçili sekme dışında).
        self.assertIn(
            'id="z3-tab-series" aria-selected="false" '
            'aria-controls="z3-panel-series" tabindex="-1"', text)
        # Her tabpanel kimliği bir sekmeye; seçili olmayan panel gizli.
        self.assertRegex(
            text,
            r'<div id="z3-panel-series"[^>]*role="tabpanel" '
            r'aria-labelledby="z3-tab-series" hidden>')
        self.assertRegex(
            text,
            r'<div id="z3-slides"[^>]*role="tabpanel" '
            r'aria-labelledby="z3-tab-slides">')
        # aria-controls kırık bağlantı göstermemeli.
        for target in re.findall(r'aria-controls="([^"]+)"', text):
            self.assertIn(f'id="{target}"', text)

    def test_series_cover_keeps_slide_a11y_contract(self):
        text = HTML.read_text(encoding="utf-8")
        match = re.search(r'<div id="z3-panel-series".*?</div>', text, re.S)
        self.assertIsNotNone(match)
        panel = match.group(0)
        self.assertIn('src="/slides_z3/incidental_proof_book_cover-1.png"', panel)
        self.assertIn('alt="Incidental Proof kitap kapağı — '
                      'Leibniz2 verification series"', panel)
        self.assertIn('width="681" height="851"', panel)
        self.assertIn('loading="lazy"', panel)
        self.assertIn('aria-label="Seri kapağını büyüt"', panel)

    def test_gallery_js_wires_tabs_and_cover_lightbox(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn('#z3-slide-gallery .z3-tab', js)
        self.assertIn('function selectTab(tab)', js)
        self.assertIn('e.key === "Home"', js)
        self.assertIn('e.key === "End"', js)
        self.assertIn('setAttribute("aria-selected"', js)
        self.assertIn('incidental_proof_book_cover-1', js)


if __name__ == "__main__":
    unittest.main()
