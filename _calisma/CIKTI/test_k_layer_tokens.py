#!/usr/bin/env python3
import pathlib
import re
import unittest


CSS = pathlib.Path(__file__).with_name("k-layer-tokens.css").read_text(encoding="utf-8")


class KLayerTokenContractTests(unittest.TestCase):
    def test_has_static_root_tokens_and_tailwind_theme_aliases(self):
        for name in ("bg", "surface", "border", "fg", "muted", "accent",
                     "pass", "warn", "fail", "budget", "info"):
            self.assertRegex(CSS, rf"--k-layer-{name}:\s*#[0-9a-fA-F]{{6}};")
            self.assertIn(f"--color-k-layer-{name}: var(--k-layer-{name});", CSS)
        self.assertIn("@theme", CSS)

    def test_semantic_classes_use_the_same_tokens(self):
        for status in ("pass", "warn", "fail", "budget", "info"):
            self.assertIn(f".k-layer-{status}", CSS)
            self.assertIn(f"color: var(--k-layer-{status})", CSS)
            self.assertIn(f"background: var(--k-layer-{status}-bg)", CSS)

    def test_is_build_free_css(self):
        self.assertNotIn("@import", CSS)
        self.assertNotRegex(CSS, r"url\(")


if __name__ == "__main__":
    unittest.main()
