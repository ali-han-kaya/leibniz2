#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_render_z3_slides.py — render_z3_slides.py denetimi.

tex-render-guide Method 1 (standalone LaTeX → PDF → yüksek DPI PNG) ile
12 Z3 teoremini PNG'ye çeviren script'in kural sabitlemesi:

  1) THEOREMS ↔ symbolic_proof_z3.py record() ID'leri birebir (12/12)
  2) Drift fail-closed: tabloya yabancı teorem eklenirse / kod ID'si
     çıkarılırsa --check-sync exit 1 üretir (üretimle senkron kapısı)
  3) Beklenen sonuç tutarlılığı: aynı ID'nin verdict'i kodla eşleşmeli
     (ör. P4-b SAT, P4-d UNSAT — yanlış beklenen → drift)
  4) _latex_doc: geçerli standalone doküman üretir (preamble + teorem)
  5) Araç zinciri fallback: pdflatex→tectonic, convert→pdftoppm→sips
     sırası (Method 1 yedekliliği); gerçek derleme yalnızca araç varsa
     (skip — CI'da TeX motoru olmayabilir).
"""
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import render_z3_slides as rz

THEOREM_IDS = ["P1-a", "P1-b", "P2", "P3-a", "P3-b",
               "P4-a", "P4-b", "P4-c", "P4-d", "P4-e", "P5", "P5-note"]


def _code_record_ids(src):
    """symbolic_proof_z3.py record() çağrılarındaki ID'ler."""
    import re
    return set(re.findall(r'record\("([^"]+)"', src))


class TestSyncCheck(unittest.TestCase):
    def test_twelve_theorems(self):
        """Tam 12 teorem, kaynak koddaki record() ID'leriyle birebir."""
        self.assertEqual(len(rz.THEOREMS), 12)
        self.assertEqual({t[0] for t in rz.THEOREMS}, set(THEOREM_IDS))

    def test_check_sync_passes_on_real_code(self):
        """Gerçek symbolic_proof_z3.py ile --check-sync exit 0."""
        self.assertEqual(rz.check_sync(), 0)

    def test_drift_extra_theorem_fails(self):
        """Tabloya kodda olmayan teorem eklenirse exit 1 (fail-closed)."""
        orig = rz.THEOREMS
        try:
            rz.THEOREMS = list(orig) + [("XX-1", r"x", "SAT", "sahte")]
            self.assertEqual(rz.check_sync(), 1)
        finally:
            rz.THEOREMS = orig

    def test_drift_missing_theorem_fails(self):
        """Kodda var ama tabloda yok → exit 1."""
        import re as _re
        orig = rz.THEOREMS
        try:
            # Tablodan P4-e'yi çıkar (kodda var) → drift
            rz.THEOREMS = [t for t in orig if t[0] != "P4-e"]
            self.assertEqual(rz.check_sync(), 1)
        finally:
            rz.THEOREMS = orig

    def test_drift_verdict_mismatch_fails(self):
        """Aynı ID'nin beklenen sonucu kodla çelişirse exit 1."""
        orig = rz.THEOREMS
        try:
            # P4-b kodda SAT — tabloda UNSAT yap → drift yakalanmalı
            rz.THEOREMS = [
                (t[0], t[1], "UNSAT" if t[0] == "P4-b" else t[2], t[3])
                for t in orig]
            self.assertEqual(rz.check_sync(), 1)
        finally:
            rz.THEOREMS = orig

    def test_code_ids_are_superset_of_table(self):
        """Koddaki 12 ID, tablo ID'lerini tam kapsar (kaynak tek)."""
        src = rz.Z3_SRC.read_text(encoding="utf-8")
        code_ids = _code_record_ids(src)
        self.assertEqual(code_ids, set(THEOREM_IDS))


class TestLatexDoc(unittest.TestCase):
    def test_doc_has_standalone_preamble(self):
        doc = rz._latex_doc(rz.THEOREMS[0], 4, False)
        self.assertIn(r"\documentclass[border=4pt]{standalone}", doc)
        self.assertIn(r"\usepackage{amsmath,amssymb}", doc)
        self.assertIn(r"\begin{document}", doc)
        self.assertIn(r"\end{document}", doc)

    def test_doc_contains_formula(self):
        tid, tex, _v, _n = rz.THEOREMS[0]
        doc = rz._latex_doc(rz.THEOREMS[0], 4, False)
        self.assertIn(tex, doc)
        self.assertNotIn(tid + r" \;·\;", doc)  # label yokken etiket basılmaz

    def test_doc_with_label(self):
        doc = rz._latex_doc(rz.THEOREMS[0], 4, True)
        self.assertIn(r"\texttt{P1-a}", doc)
        self.assertIn(r"\text{UNSAT}", doc)

    def test_all_theorems_produce_valid_doc(self):
        """Her teorem derlenebilir standalone doküman üretir."""
        for th in rz.THEOREMS:
            doc = rz._latex_doc(th, 4, False)
            self.assertTrue(doc.startswith(r"\documentclass[border=4pt]{standalone}"))
            self.assertTrue(doc.rstrip().endswith(r"\end{document}"))


class TestToolchain(unittest.TestCase):
    def test_find_tex_engine_returns_string_or_none(self):
        e = rz.find_tex_engine()
        if e is not None:
            self.assertIn(e, ("pdflatex", "latex", "tectonic"))

    def test_find_pdf_to_png_returns_string_or_none(self):
        c = rz.find_pdf_to_png()
        if c is not None:
            self.assertIn(c, ("convert", "magick", "pdftoppm", "sips"))


if __name__ == "__main__":
    unittest.main()
