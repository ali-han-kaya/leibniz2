"""test_pptx_export.py — verification_chain.pptx üretim + yapı sözleşmesi.

PNG deck'i gerçek .pptx'e çeviren jeneratörün (skill: pptx / pptxgenjs)
sözleşmesi:
  - jeneratör kaynağı mevcut
  - node mevcutsa pptx üretilebilir (üretilmemişse test kendisi üretir)
  - yapı: 5 slayt + 5 not + >=5 medya; presentation.xml'de 5 sldId;
    notesSlide1'te 01/thesis metni; slayt sayısı sldIdLst ile birebir.

.pptx üretilen çıktıdır (gitignore'lu); test node varsa taze üretir, node
yoksa yapı-testi SKIP (fail değil — CI koşucularında node sözleşme dışı).
"""

import pathlib
import re
import shutil
import subprocess
import unittest
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
PPTX_DIR = HERE.parent / "pptx"
PPTX = PPTX_DIR / "verification_chain.pptx"
GEN = PPTX_DIR / "verification_chain_pptx.js"


class TestVerificationChainPptx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if cls.node and GEN.is_file() and not PPTX.is_file():
            subprocess.run(
                [cls.node, str(GEN)], cwd=str(PPTX_DIR), check=True,
                timeout=60, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_generator_source_exists(self):
        self.assertTrue(GEN.is_file(), f"generator kaynağı eksik: {GEN}")
        src = GEN.read_text(encoding="utf-8")
        # skill sözleşmesi: layout set edilmeden slayt eklenmez
        self.assertIn('pres.layout = "LAYOUT_16x9"', src)
        # notlar slide.addNotes ile taşınır (görünmez metin-kutusu hilesi yasak)
        self.assertIn("addNotes", src)

    @unittest.skipIf(shutil.which("node") is None, "node yok")
    def test_pptx_built_and_structured(self):
        self.assertTrue(PPTX.is_file(), "pptx üretilemedi")
        with zipfile.ZipFile(PPTX) as z:
            names = z.namelist()
            slides = [n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)]
            notes = [n for n in names if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", n)]
            media = [n for n in names if n.startswith("ppt/media/")]
            self.assertEqual(len(slides), 5, "5 slayt beklenir")
            self.assertEqual(len(notes), 5, "her slaytta not beklenir")
            self.assertGreaterEqual(len(media), 5, "5 PNG medya beklenir")
            pres = z.read("ppt/presentation.xml").decode("utf-8", "replace")
            self.assertEqual(pres.count("<p:sldId "), 5,
                             "sldIdLst slayt sayısıyla birebir olmalı")
            n1 = z.read("ppt/notesSlides/notesSlide1.xml").decode("utf-8", "replace")
            self.assertIn("Integrity is a chain", n1,
                          "slayt-1 notu thesis metnini taşımalı")
            # hex renk sözleşmesi: '#' ile başlayan renk değeri sızmasın
            self.assertNotIn('val="#', pres)


if __name__ == "__main__":
    unittest.main()
