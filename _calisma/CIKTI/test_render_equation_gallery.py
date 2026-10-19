#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the source-bound article equation gallery."""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "render_equation_gallery.py"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import render_equation_gallery as gallery  # noqa: E402


class TestSourceBinding(unittest.TestCase):
    def test_selection_is_unique_and_source_bound(self):
        selected = gallery.select_equations(gallery.DEFAULT_SOURCE)
        self.assertEqual(tuple(selected), tuple(spec.ident for spec in gallery.EQUATIONS))
        self.assertEqual(len(selected), 16)
        for spec in gallery.EQUATIONS:
            block = selected[spec.ident]
            self.assertIn(spec.anchor, block.body)
            self.assertLess(block.start_line, block.end_line)

    def test_display_parser_preserves_alignment_environment(self):
        blocks = gallery.extract_display_blocks(gallery.DEFAULT_SOURCE)
        align = [block for block in blocks if block.kind == "align*"]
        self.assertTrue(align)
        self.assertIn("&", align[0].body)
        self.assertIn("\\\\", align[0].body)

    def test_standalone_uses_inline_math_and_removes_nested_tags(self):
        selected = gallery.select_equations(gallery.DEFAULT_SOURCE)
        rendered = selected["mechanism-m0a"].standalone()
        self.assertTrue(rendered.startswith("$\\displaystyle"))
        self.assertNotIn("\\tag", rendered)
        self.assertNotIn("$_{0a}$", rendered)

    def test_missing_anchor_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="equation-anchor-") as td:
            source = pathlib.Path(td) / "article.tex"
            source.write_text("\\[\n x = y\n\\]\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                gallery.select_equations(source, [gallery.EquationSpec("missing", "x", "z")])


class TestGeneratedGallery(unittest.TestCase):
    def setUp(self):
        self.out = HERE / "equation_gallery"
        if not self.out.is_dir():
            self.skipTest("generated gallery not present")

    def test_all_selected_pngs_are_present_and_nonempty(self):
        for spec in gallery.EQUATIONS:
            png = self.out / f"{spec.ident}.png"
            self.assertTrue(png.is_file(), png)
            self.assertGreater(png.stat().st_size, 100, png)
            self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_manifest_matches_source_and_png_hashes(self):
        manifest = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["source"], gallery._portable_path(gallery.DEFAULT_SOURCE))
        self.assertEqual(len(manifest["equations"]), len(gallery.EQUATIONS))
        for item in manifest["equations"]:
            png = self.out / item["png"]
            self.assertEqual(item["png_sha256"], hashlib.sha256(png.read_bytes()).hexdigest())
        self.assertEqual(gallery.check_sync(gallery.DEFAULT_SOURCE, self.out), 0)

    def test_index_references_each_png_and_source_line(self):
        index = (self.out / "index.html").read_text(encoding="utf-8")
        for spec in gallery.EQUATIONS:
            self.assertIn(f'src="{spec.ident}.png"', index)
            self.assertIn(spec.title, index)
        self.assertEqual(index.count('loading="lazy"'), len(gallery.EQUATIONS))
        self.assertIn("core_section.tex", index)


class TestReproducibility(unittest.TestCase):
    def test_one_equation_is_byte_reproducible(self):
        if not gallery.find_tex_engine() or not gallery.find_pdf_to_png():
            self.skipTest("TeX/PDF araçları yok")
        with tempfile.TemporaryDirectory(prefix="equation-repro-") as td:
            outputs = [pathlib.Path(td, "one"), pathlib.Path(td, "two")]
            for output in outputs:
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--out", str(output),
                     "--only", "l0-sorts", "--dpi", "300"],
                    cwd=str(HERE.parent.parent), capture_output=True, text=True,
                    env={**__import__("os").environ, "SOURCE_DATE_EPOCH": "1700000000"},
                    timeout=600,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            hashes = [
                hashlib.sha256((output / "l0-sorts.png").read_bytes()).hexdigest()
                for output in outputs
            ]
            self.assertEqual(hashes[0], hashes[1])


if __name__ == "__main__":
    unittest.main()
