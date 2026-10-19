#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_equation_gallery_tab.py — denklem galerisi sekme sözleşmesi (statik).

Kanonik makalenin denklem galerisi (render_equation_gallery.py →
equation_gallery/) canlı dashboard'a responsive sekme olarak bağlanır.
Bu dosya HER ortamda koşar (tarayıcı gerekmez) ve şu sözleşmeleri pin'ler:

  1. ARIA tabs: tablist ↔ iki tab ↔ iki tabpanel kablosu (aria-controls /
     aria-labelledby / id birebir); denklem paneli varsayılan olarak gizli.
  2. Envanter: manifest.json 16 denklem taşır ve HER png disktedir.
  3. İstemci: preview.js /api/equations'ı çeker, sekme + lightbox
     klavye sözleşmesini (Esc/ok/focus-trap) içerir.
  4. Sunucu: _route() /api/equations ve /equations/ rotalarını eşler.
  5. Token disiplini: yeni CSS bloğunda renk literalı YOK
     (check-design-tokens contract 9).
"""
import json
import pathlib
import re
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import preview_server as ps  # noqa: E402

HTML = HERE / "preview.html"
JS = HERE / "preview.js"
GALLERY = HERE / "equation_gallery"
MANIFEST = GALLERY / "manifest.json"


class TestAriaTabsWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = HTML.read_text(encoding="utf-8")

    def test_tablist_has_exactly_two_wired_tabs(self):
        tabs = re.findall(
            r'<button type="button" role="tab" id="([^"]+)" '
            r'aria-controls="([^"]+)"', self.text)
        self.assertEqual(tabs, [
            ("tab-panel", "view-panel"),
            ("tab-equations", "view-equations"),
        ])

    def test_panels_are_labelled_by_their_tabs(self):
        self.assertIn(
            'id="view-panel" role="tabpanel" aria-labelledby="tab-panel"',
            self.text)
        self.assertIn(
            'id="view-equations" role="tabpanel" '
            'aria-labelledby="tab-equations"', self.text)

    def test_equations_panel_hidden_by_default(self):
        match = re.search(
            r'<section id="view-equations"[^>]*>', self.text)
        self.assertIsNotNone(match)
        self.assertIn("hidden", match.group(0))
        self.assertIn('aria-selected="true"', self.text.split(
            "<section id=")[0].split('role="tablist"')[1])

    def test_panel_surface_ids_exist(self):
        for element_id in ("equation-grid", "equations-status",
                           "equations-ts", "eq-lightbox", "eq-lightbox-image",
                           "eq-lightbox-title", "eq-prev", "eq-next",
                           "eq-close"):
            self.assertIn(f'id="{element_id}"', self.text, element_id)

    def test_lightbox_is_a_modal_dialog(self):
        match = re.search(r'<div id="eq-lightbox"[^>]*>', self.text)
        self.assertIsNotNone(match)
        self.assertIn('role="dialog"', match.group(0))
        self.assertIn('aria-modal="true"', match.group(0))


class TestManifestIntegrity(unittest.TestCase):
    def test_manifest_has_sixteen_source_bound_equations(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        equations = data["equations"]
        self.assertEqual(len(equations), 16)
        self.assertTrue(data["source"].endswith("core_section.tex"))
        self.assertRegex(data["source_sha256"], r"^[0-9a-f]{64}$")
        for entry in equations:
            self.assertRegex(entry["body_sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue((GALLERY / entry["png"]).is_file(), entry["png"])

    def test_png_names_are_asset_safe(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for entry in data["equations"]:
            self.assertRegex(entry["png"], r"^[A-Za-z0-9._-]+\.png$")


class TestClientAndServerWiring(unittest.TestCase):
    def test_preview_js_consumes_api_and_implements_contracts(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn('fetch("/api/equations")', js)
        self.assertIn("initDashTabs", js)
        self.assertIn("equationGallery", js)
        # Klavye sözleşmeleri (z3 lightbox ile aynı desen):
        for needle in ('"eq-close"', '"eq-prev"', '"eq-next"',
                       "Escape", "ArrowLeft", "ArrowRight", "focusables"):
            self.assertIn(needle, js, needle)

    def test_js_has_no_inline_event_handlers(self):
        # CSP (VERIFY-001): nitelik handler'lar CSP altında sessiz ölür.
        js = JS.read_text(encoding="utf-8")
        appended = js[js.index("initDashTabs") - 200:]
        self.assertNotRegex(appended, r"\son(click|keydown|mouseover)=")

    def test_server_routes_equations_endpoints(self):
        self.assertEqual(ps._route("/api/equations"), "equations_api")
        self.assertEqual(ps._route("/api/equations?_t=1"), "equations_api")
        self.assertEqual(ps._route("/equations/l0-sorts.png"),
                         "equations_asset")
        self.assertEqual(ps._route("/equations/../secret.png"),
                         "equations_asset")  # guard handler'da (404)

    def test_handlers_exist_and_use_realpath_guard(self):
        source = (HERE / "preview_server.py").read_text(encoding="utf-8")
        self.assertIn("def serve_equations_api", source)
        self.assertIn("def serve_equations_asset", source)
        asset = source.split("def serve_equations_asset")[1].split(
            "def serve_slides")[0]
        self.assertIn("os.path.commonpath", asset)
        self.assertIn("os.path.realpath", asset)


class TestTokenDiscipline(unittest.TestCase):
    def test_new_css_block_has_no_color_literals(self):
        text = HTML.read_text(encoding="utf-8")
        start = text.index(".dash-tabs {")
        end = text.index("View Transitions")
        block = text[start:end]
        literals = re.findall(r"#[0-9a-fA-F]{3,8}(?![A-Za-z-])", block)
        self.assertEqual(literals, [],
                         "yeni CSS bloğu yalnız token tüketmeli "
                         "(check-design-tokens contract 9)")
        self.assertIn("var(--accent)", block)
        self.assertIn("var(--surface)", block)


if __name__ == "__main__":
    unittest.main()
