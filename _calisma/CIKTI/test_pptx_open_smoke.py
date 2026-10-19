#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_pptx_open_smoke.py — headless sunum smoke'unun sözleşmesi.

`pptx_open_smoke.py` deck'i LibreOffice ile açar (PDF) ve metin katmanını
pdftotext ile dışa aktarır. Bu dosya iki katmanı ayrı ayrı çiviler:

  A) SAF KATMAN (her ortamda koşar, araç gerekmez):
     normalize / page_count / missing_markers / deck_paths sözleşmeleri —
     satır bölünmüş tanık ("Integrity is a chain,\\nnot a checkbox") yine
     bulunmalı; 5 sayfalık PDF 5 döndürmeli; boş sayfa sayılmamalı.

  B) ORKESTRASYON KATMANI (sahte `soffice` + `pdftotext` stub'ları):
     exit kodları docx emsaliyle aynı olmalı —
       0 PASS · 1 FAIL (deck açılmadı / sayfa eksik / metin eksik)
       2 ORTAM (araç yok / deck dosyası yok)
     Her başarısızlık türü tek başına kırmızıya düşmeli; "araç yok" sessizce
     yeşile dönmemeli (fail-open'ın en sık görülen biçimi).

  C) GERÇEK KATMAN (yalnız araçlar kuruluysa): gerçek deck'ler gerçek
     LibreOffice'te açılır. Araç yoksa dürüstçe SKIP — CI'da bu sözleşmeyi
     `pptx-export` job'ı AYRICA ve SKIP'SİZ koşar (adım rc'si job'ı düşürür).
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pptx_open_smoke as smoke  # noqa: E402
import test_pptx_export as export  # noqa: E402

REPO = HERE.parent.parent

STUB_SOFFICE = """\
#!/usr/bin/env bash
# Sahte LibreOffice: FAKE_TEXTS/<deck>.pdf varsa onu kopyalar (dönüşüm
# "başarılı"), yoksa rc=1 (deck açılamadı senaryosu).
set -euo pipefail
out=""
expect=0
for a in "$@"; do
  if [ "$expect" = "1" ]; then out="$a"; expect=0; continue; fi
  [ "$a" = "--outdir" ] && expect=1
done
input="${!#}"
stem="$(basename "$input" .pptx)"
cp "$FAKE_TEXTS/$stem.pdf" "$out/$stem.pdf"
"""

STUB_PDFTOTEXT = """\
#!/usr/bin/env bash
# Sahte pdftotext: `-layout <pdf> <txt>` → pdf gövdesini txt'ye kopyalar.
set -euo pipefail
if [ "${1:-}" = "-layout" ]; then
  in="$2"; out="$3"
else
  in="$1"; out="$2"
fi
cp "$in" "$out"
"""


def write_stubs(directory):
    """(soffice, pdftotext) yollarını üretir."""
    d = pathlib.Path(directory)
    paths = []
    for name, body in (("soffice", STUB_SOFFICE), ("pdftotext", STUB_PDFTOTEXT)):
        p = d / name
        p.write_text(body, encoding="utf-8")
        p.chmod(0o755)
        paths.append(str(p))
    return tuple(paths)


def run_quiet(argv):
    """(rc, stdout, stderr) — betiğin konsol çıktısı test log'unu kirletmesin."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = smoke.main(argv)
    return rc, out.getvalue(), err.getvalue()


def deck_text(name, pages=smoke.SLIDES, drop_markers=(), empty=False):
    """Bir deck'in sahte PDF gövdesi: sayfa başına tanık metinleri."""
    if empty:
        return "\f".join(["" for _ in range(pages)]) + "\f"
    markers = [m for m in smoke.DECKS[name] if m not in drop_markers]
    body = []
    for index in range(pages):
        if index == 0:
            chunk = "\n".join(markers)
        else:
            chunk = "slayt %d" % (index + 1)
        body.append(chunk)
    return "\f".join(body) + "\f"


class Fixture:
    """Geçici deck dizini + FAKE_TEXTS + stub araçlar."""

    def __init__(self, tmpdir, texts=None):
        self.root = pathlib.Path(tmpdir)
        self.decks = self.root / "decks"
        self.decks.mkdir()
        self.fake = self.root / "fake"
        self.fake.mkdir()
        self.soffice, self.pdftotext = write_stubs(self.root)
        self.texts = texts if texts is not None else {
            name: deck_text(name) for name in smoke.DECKS}
        for name, body in self.texts.items():
            (self.decks / (name + ".pptx")).write_bytes(b"PK\x03\x04fake")
            if body is not None:
                (self.fake / (name + ".pdf")).write_text(body, encoding="utf-8")

    def main(self, *extra, text_out=None, json_out=None):
        text_out = text_out or str(self.root / "text")
        argv = ["--dir", str(self.decks), "--text-out", text_out,
                "--soffice", self.soffice, "--pdftotext", self.pdftotext]
        if json_out:
            argv += ["--json-out", json_out]
        argv += list(extra)
        old = os.environ.get("FAKE_TEXTS")
        os.environ["FAKE_TEXTS"] = str(self.fake)
        try:
            rc, _out, _err = run_quiet(argv)
            return rc, pathlib.Path(text_out)
        finally:
            if old is None:
                os.environ.pop("FAKE_TEXTS", None)
            else:
                os.environ["FAKE_TEXTS"] = old


class TestPureLayer(unittest.TestCase):
    def test_normalize_collapses_wrapped_lines(self):
        self.assertEqual(
            smoke.normalize("Integrity is a chain,\n   not a checkbox\t"),
            "Integrity is a chain, not a checkbox")

    def test_marker_split_across_lines_is_still_found(self):
        # PDF çıkarımı tanık cümleyi iki satıra böler; ham `in` araması
        # kaçırırdı — bu yüzden normalizasyon sözleşmenin parçası.
        text = "Integrity is a chain,\nnot a checkbox"
        self.assertEqual(
            smoke.missing_markers(text, ("Integrity is a chain, not a checkbox",)),
            [])

    def test_page_count_ignores_trailing_form_feed_and_blank_pages(self):
        self.assertEqual(smoke.page_count("a\fb\fc\f"), 3)
        self.assertEqual(smoke.page_count("a\f\f\f"), 1)
        self.assertEqual(smoke.page_count(""), 0)
        self.assertEqual(smoke.page_count("   \f  \n"), 0)

    def test_expected_decks_and_markers_are_the_packaging_contract(self):
        # Tek kaynak: paket testiyle aynı tanımlar (kopya değil, import).
        self.assertEqual(sorted(smoke.DECKS), sorted(
            deck["name"] for deck in export.DECKS))
        for name, markers in smoke.DECKS.items():
            with self.subTest(deck=name):
                self.assertTrue(markers, "deck için tanık metin yok")


class TestOrchestration(unittest.TestCase):
    def test_pass_exports_text_layer_and_report(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(td)
            report_path = str(pathlib.Path(td) / "out" / "report.json")
            rc, text_out = fixture.main(json_out=report_path)
            self.assertEqual(rc, 0)
            report = json.loads(pathlib.Path(report_path).read_text(encoding="utf-8"))
            self.assertEqual(report["verdict"], "PASS")
            self.assertEqual(len(report["decks"]), 3)
            for row in report["decks"]:
                with self.subTest(deck=row["deck"]):
                    self.assertTrue(row["ok"])
                    self.assertEqual(row["pages"], smoke.SLIDES)
                    self.assertGreater(row["text_bytes"], 0)
                    exported = pathlib.Path(row["txt"])
                    self.assertTrue(exported.is_file(), "metin katmanı dışa aktarılmalı")
                    self.assertEqual(exported.parent, text_out)

    def test_missing_marker_is_red(self):
        texts = {name: deck_text(name) for name in smoke.DECKS}
        dropped = smoke.DECKS["pdf_repro_findings"][0]
        texts["pdf_repro_findings"] = deck_text(
            "pdf_repro_findings", drop_markers=(dropped,))
        with tempfile.TemporaryDirectory() as td:
            rc, _ = Fixture(td, texts).main()
            self.assertEqual(rc, 1, "metin katmanında tanık yoksa FAIL")

    def test_missing_slide_is_red(self):
        texts = {name: deck_text(name) for name in smoke.DECKS}
        texts["architecture_deepening"] = deck_text("architecture_deepening", pages=4)
        with tempfile.TemporaryDirectory() as td:
            rc, _ = Fixture(td, texts).main()
            self.assertEqual(rc, 1, "4 sayfa render edilen deck FAIL olmalı")

    def test_empty_text_layer_is_red(self):
        texts = {name: deck_text(name) for name in smoke.DECKS}
        texts["verification_chain"] = deck_text("verification_chain", empty=True)
        with tempfile.TemporaryDirectory() as td:
            rc, _ = Fixture(td, texts).main()
            self.assertEqual(rc, 1, "yazısız slaytlar 'metin katmanı' iddiasını düşürür")

    def test_conversion_failure_is_red_not_env(self):
        # FAKE_TEXTS'te karşılık yok → sahte soffice rc=1 (deck açılmadı).
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(td)
            (fixture.fake / "verification_chain.pdf").unlink()
            rc, _ = fixture.main()
            self.assertEqual(rc, 1, "'deck açılmadı' ORTAM değil, FAIL'dir")

    def test_missing_tool_is_environment_error(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(td)
            rc, _out, err = run_quiet([
                "--dir", str(fixture.decks),
                "--text-out", str(pathlib.Path(td) / "t"),
                "--soffice", str(pathlib.Path(td) / "yok"),
                "--pdftotext", fixture.pdftotext])
            self.assertEqual(rc, 2, "soffice yok → ORTAM (2), sessiz yeşil değil")
            self.assertIn("soffice", err, "hangi araç eksik olduğu log'da olmalı")

    def test_missing_pdftotext_is_environment_error(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(td)
            rc, _out, err = run_quiet([
                "--dir", str(fixture.decks),
                "--text-out", str(pathlib.Path(td) / "t"),
                "--soffice", fixture.soffice,
                "--pdftotext", str(pathlib.Path(td) / "yok")])
            self.assertEqual(rc, 2)
            self.assertIn("pdftotext", err)

    def test_missing_deck_is_environment_error(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(td)
            (fixture.decks / "verification_chain.pptx").unlink()
            rc, _ = fixture.main()
            self.assertEqual(rc, 2, "deck dosyası yok → ORTAM (2)")


@unittest.skipUnless(shutil.which("soffice") or shutil.which("libreoffice"),
                     "LibreOffice yok — gerçek açılış katmanı CI'da koşar")
@unittest.skipUnless(shutil.which("pdftotext"), "pdftotext yok")
class TestRealOpen(unittest.TestCase):
    """Gerçek deck'ler gerçek sunum motorunda açılır (yerelde araç varsa)."""

    def test_real_decks_open_and_export_text(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "pptx_open_smoke.py"),
             "--dir", str(REPO / "_calisma" / "pptx")],
            capture_output=True, text=True, timeout=600, cwd=str(REPO))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("verdict=PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
