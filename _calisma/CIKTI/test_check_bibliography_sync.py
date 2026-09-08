#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_bibliography_sync.py regresyon testleri — tez References ↔ PDF senkronu.

Canlı tez↔PDF PASS yolu + fail-closed drift senaryoları (V5j Popkin
133-147 / Priest tam altbaşlık varyantları) + layout tireleme / başharf
boşluk toleransı; hiçbir test ağ kullanmaz (override'lar üzerinden).
"""

import io
import json
import pathlib
import shutil
import sys
import unittest
from unittest import mock

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import check_bibliography_sync as cbs  # noqa: E402

REAL_TEX = cbs.DEFAULT_TEX
REAL_PDF = cbs.DEFAULT_PDF


def _has_pdftotext() -> bool:
    return shutil.which("pdftotext") is not None or pathlib.Path("/opt/homebrew/bin/pdftotext").exists()


class TestTexParse(unittest.TestCase):
    def test_tex_items_count_is_64(self):
        items = cbs.tex_items()
        self.assertEqual(len(items), 64, f"tex References {len(items)} != 64")

    def test_tex_contains_v5j_popkin_and_priest(self):
        items = cbs.tex_items()
        # entry 45: Popkin 1952 High Road 133-147
        self.assertIn("133-147", items[44])
        self.assertIn("High Road to Pyrrhonism", items[44])
        # entry 48: Priest 2018 full subtitle
        self.assertIn("An Essay on Buddhist Metaphysics and the Catuskoti", items[47])

    def test_tex_to_plain_strips_commands(self):
        self.assertEqual(cbs._tex_to_plain(r"``foo''"), '"foo"')
        self.assertEqual(cbs._tex_to_plain(r"In M.~Burnyeat"), "In M. Burnyeat")
        self.assertIn("Repr. in", cbs._tex_to_plain(r"Repr.\ in"))


class TestNormalize(unittest.TestCase):
    def test_normalize_strips_accents_and_ligatures(self):
        self.assertEqual(cbs.normalize("Catu\u0161ko\u1e6di"), "catuskoti")
        self.assertEqual(cbs.normalize("De\uFB01nition"), "definition")
        self.assertEqual(cbs.normalize("133\u2013147"), "133-147")

    def test_eq_forgiving_allows_spacing_only(self):
        a = cbs.normalize("Beauchamp, T. L. (ed.)")
        b = cbs.normalize("Beauchamp, T.L. (ed.)")
        self.assertNotEqual(a, b)
        self.assertTrue(cbs._eq_forgiving(a, b))

    def test_eq_forgiving_does_not_forgive_wording(self):
        a = cbs.normalize("Repr. in The High Road to Pyrrhonism, 133-147.")
        b = cbs.normalize("Repr. in The High Road to Pyrrhonism, 133-148.")
        self.assertFalse(cbs._eq_forgiving(a, b))
        c = cbs.normalize("The Fifth Corner of Four: An Essay on Buddhist Metaphysics and the Catuskoti.")
        d = cbs.normalize("The Fifth Corner of Four.")
        self.assertFalse(cbs._eq_forgiving(c, d))

    def test_normalize_trims_punct(self):
        self.assertEqual(cbs.normalize("Nijhoff."), "nijhoff")
        self.assertEqual(cbs.normalize("  Foo   Bar  "), "foo bar")


class TestPdfParse(unittest.TestCase):
    @unittest.skipUnless(_has_pdftotext(), "pdftotext yok — CI poppler görüntüsünde koşar")
    def test_pdf_items_count_is_64(self):
        items = cbs.pdf_items()
        self.assertIsNotNone(items)
        assert items is not None
        self.assertEqual(len(items), 64, f"pdf References {len(items)} != 64")

    @unittest.skipUnless(_has_pdftotext(), "pdftotext yok")
    def test_pdf_dehyphenation(self):
        items = cbs.pdf_items()
        assert items is not None
        # layout mode without de-hyphenation would leave "Mathe- maticae" etc.
        joined = " ".join(items)
        self.assertNotIn("Mathe- maticae", joined)
        self.assertIn("Mathematicae", joined)


class TestCheck(unittest.TestCase):
    def _live_lists(self):
        tex = cbs.tex_items()
        pdf = cbs.pdf_items()
        if pdf is None:
            self.skipTest("pdftotext yok — live check atlandı")
        return tex, pdf  # type: ignore[return-value]

    def test_live_sync_passes(self):
        tex, pdf = self._live_lists()
        ok, findings, meta = cbs.check(tex_override=tex, pdf_override=pdf)
        self.assertTrue(ok, findings)
        self.assertEqual(meta["tex_count"], 64)
        self.assertEqual(meta["pdf_count"], 64)
        self.assertEqual(len(findings), 0)

    def test_detects_popkin_page_drift(self):
        tex, pdf = self._live_lists()
        stale_tex = tex[:]
        stale_tex[44] = stale_tex[44].replace("133-147", "133-148")
        ok, findings, _ = cbs.check(tex_override=stale_tex, pdf_override=pdf)
        self.assertFalse(ok)
        kinds = {f["kind"] for f in findings}
        self.assertIn("entry_mismatch", kinds)
        idxs = {f["idx"] for f in findings if f["kind"] == "entry_mismatch"}
        self.assertIn(45, idxs)

    def test_detects_priest_truncation(self):
        tex, pdf = self._live_lists()
        truncated = "Priest, G. (2018). The Fifth Corner of Four. Oxford University Press."
        stale_tex = tex[:]
        stale_tex[47] = truncated
        ok, findings, _ = cbs.check(tex_override=stale_tex, pdf_override=pdf)
        self.assertFalse(ok)
        idxs = {f["idx"] for f in findings if f["kind"] == "entry_mismatch"}
        self.assertIn(48, idxs)

        # ters yön: tex tam, pdf kırpılmış da yakalanır
        stale_pdf = pdf[:]
        stale_pdf[47] = truncated
        ok2, findings2, _ = cbs.check(tex_override=tex, pdf_override=stale_pdf)
        self.assertFalse(ok2)
        idxs2 = {f["idx"] for f in findings2 if f["kind"] == "entry_mismatch"}
        self.assertIn(48, idxs2)

    def test_detects_count_mismatch(self):
        tex, pdf = self._live_lists()
        ok, findings, meta = cbs.check(tex_override=tex[:60], pdf_override=pdf)
        self.assertFalse(ok)
        self.assertEqual(meta["tex_count"], 60)
        kinds = {f["kind"] for f in findings}
        self.assertIn("tex_count_mismatch", kinds)

    def test_hyphenation_and_spacing_are_not_drift(self):
        # layout tireleme ("Mathe- maticae" / "Mil- lican") ve "T.L." vs
        # "T. L." varyantları drift sayılmaz — normalize + de-hyphenation +
        # _eq_forgiving ile tolere edilir.
        tex = ["Beauchamp, T. L. (ed.) (1999). Foo.", "Beth, E. W. (1953). Indagationes Mathematicae"]
        pdf = ["Beauchamp, T.L. (ed.) (1999). Foo.", "Beth, E.W. (1953). Indagationes Mathe- maticae"]
        # pdf tarafındaki tireleme gerçek check_bibliography_sync.pdf_items
        # tarafından "Mathematicae"ye dönüştürülür; burada doğrudan
        # normalize/_eq_forgiving katmanını doğruluyoruz.
        # pdf_items de-hyphenation'ı taklit et:
        pdf_dehyph = [p.replace("- ", "") for p in pdf]
        for a, b in zip(tex, pdf_dehyph):
            self.assertTrue(cbs._eq_forgiving(cbs.normalize(a), cbs.normalize(b)))

    def test_pdf_tool_missing_is_skip_not_fail(self):
        tex = cbs.tex_items()
        with mock.patch.object(cbs, "pdf_items", return_value=None):
            ok, findings, meta = cbs.check(tex_override=tex, pdf_override=None)
            # pdf_items None → check() de None döner ve skip eder
            # doğrudan check() çağrısı pdf_override=None ile skip yolunu tetikler
            pass
        # gerçek skip yolu: pdf_items None → check() True, findings boş
        ok, findings, meta = cbs.check(tex_override=tex, pdf_override=None)  # type: ignore[arg-type]
        # mypy için: pdf_override list[str]|None — None skip'i temsil eder mi?
        # check() imzasında pdf_override None → pdf_items() çağrılır; ama
        # burada mock'suz None iletince check() onu overridesanacak ve skip edecek.
        # Doğrudan `_has_pdftotext` yokluğunu simüle edelim:
        with mock.patch.object(cbs, "_find_pdftotext", return_value=None):
            ok2, findings2, meta2 = cbs.check(tex_override=tex)
            self.assertTrue(ok2)
            self.assertEqual(findings2, [])
            self.assertIn("skipped", meta2)

    def test_tex_parse_error_is_p0(self):
        ok, findings, meta = cbs.check(tex_path="/tmp/yok_bir_tex_yolu_12345.tex", pdf_override=["a"] * 64)
        self.assertFalse(ok)
        self.assertTrue(any(f["priority"] == "P0" for f in findings))


class TestMain(unittest.TestCase):
    @unittest.skipUnless(_has_pdftotext(), "pdftotext yok")
    def test_main_pass_exit_zero(self):
        rc = cbs.main([])
        self.assertEqual(rc, 0)

    @unittest.skipUnless(_has_pdftotext(), "pdftotext yok")
    def test_main_json_shape(self):
        buf = io.StringIO()
        with mock.patch.object(sys, "stdout", buf):
            rc = cbs.main(["--json"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertTrue(data["ok"])
        self.assertEqual(data["meta"]["tex_count"], 64)
        self.assertEqual(data["meta"]["pdf_count"], 64)

    def test_main_json_reports_drift(self):
        tex = cbs.tex_items()
        stale = tex[:]
        stale[44] = stale[44].replace("133-147", "133-148")
        # main() canlı PDF'yi okur — stale tex'i diske yazmadan da
        # json yolunu doğrulamak için check() üzerinden test ediyoruz:
        ok, findings, meta = cbs.check(tex_override=stale, pdf_override=cbs.pdf_items() or stale)
        if cbs.pdf_items() is None:
            self.skipTest("pdftotext yok")
        self.assertFalse(ok)
        self.assertTrue(any(f["kind"] == "entry_mismatch" for f in findings))


if __name__ == "__main__":
    unittest.main()
