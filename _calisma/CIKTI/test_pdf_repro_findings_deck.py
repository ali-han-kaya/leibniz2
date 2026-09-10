import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pdf_repro_findings_deck as deck


@unittest.skipUnless(getattr(deck, "HAS_PIL", False), "PIL kurulu değil — deck üretimi atlandı")
class PdfReproFindingsDeckTests(unittest.TestCase):
    def test_generates_five_report_slides(self):
        deck.build()
        files = sorted(deck.OUT.glob("slide-*.png"))
        self.assertEqual(len(files), 5)
        from PIL import Image
        for path in files:
            with Image.open(path) as image:
                self.assertEqual(image.size, (1600, 900))

    def test_documents_frozen_evidence_source(self):
        deck.build()
        readme = (deck.OUT / "README.md").read_text(encoding="utf-8")
        self.assertIn("qpdf_determinism_output.txt", readme)
        self.assertTrue((deck.OUT / "slide-03.png").stat().st_size > 10_000)


if __name__ == "__main__":
    unittest.main()
