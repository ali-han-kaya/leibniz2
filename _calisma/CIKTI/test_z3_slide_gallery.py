#!/usr/bin/env python3
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
HTML = ROOT / "preview.html"
SLIDES = ROOT.parent / "slides_z3"
EXPECTED = ("P1-a", "P1-b", "P2", "P3-a", "P3-b", "P4-a", "P4-b",
            "P4-c", "P4-d", "P4-e", "P5", "P5-note")


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
            self.assertRegex(text, rf'<img src="/slides_z3/{re.escape(name)}\.png" alt="[^"]+" loading="lazy">')


if __name__ == "__main__":
    unittest.main()
