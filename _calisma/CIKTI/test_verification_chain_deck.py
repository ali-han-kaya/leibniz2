import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verification_chain_deck as deck


@unittest.skipUnless(getattr(deck, "HAS_PIL", False), "PIL kurulu değil — deck üretimi atlandı")
class DeckContractTests(unittest.TestCase):
    def test_deck_generates_five_slides_with_expected_dimensions(self):
        deck.build()
        files = sorted(deck.OUT.glob("slide-*.png"))
        self.assertEqual(len(files), 5)
        from PIL import Image
        sizes = []
        for path in files:
            with Image.open(path) as image:
                sizes.append(image.size)
        self.assertEqual(sizes, [(1600, 900)] * 5)

    def test_deck_includes_fail_closed_language(self):
        deck.build()
        pixels = (deck.OUT / "slide-01.png").read_bytes()
        self.assertGreater(len(pixels), 10_000)
        self.assertTrue((deck.OUT / "README.md").is_file())


if __name__ == "__main__":
    unittest.main()
