import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import architecture_deepening_deck as deck


@unittest.skipUnless(getattr(deck, "HAS_PIL", False), "PIL kurulu değil — deck üretimi atlandı")
class ArchitectureDeepeningDeckTests(unittest.TestCase):
    def test_generates_five_slides_at_deck_dimensions(self):
        deck.build()
        files = sorted(deck.OUT.glob("slide-*.png"))
        self.assertEqual(len(files), 5)
        from PIL import Image
        for path in files:
            with Image.open(path) as image:
                self.assertEqual(image.size, (1600, 900))

    def test_documents_three_candidates(self):
        deck.build()
        self.assertIn("Three candidates", (deck.OUT / "README.md").read_text(encoding="utf-8"))
        self.assertGreater((deck.OUT / "slide-02.png").stat().st_size, 10_000)
        self.assertGreater((deck.OUT / "slide-03.png").stat().st_size, 10_000)
        self.assertGreater((deck.OUT / "slide-04.png").stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
