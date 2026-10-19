#!/usr/bin/env python3
"""Button hover backgrounds should use surfaces, not the muted text token."""
import unittest
from pathlib import Path

BUTTON = (Path(__file__).resolve().parents[2] / "apps" / "dashboard-next" /
          "components" / "ui" / "button.tsx")


class TestButtonHoverSurface(unittest.TestCase):
    def test_hover_backgrounds_use_surface_tokens(self):
        button = BUTTON.read_text(encoding="utf-8")
        self.assertNotIn("bg-muted", button)
        self.assertIn("hover:bg-surface-raised", button)
        self.assertIn("aria-expanded:bg-surface-raised", button)


if __name__ == "__main__":
    unittest.main()
