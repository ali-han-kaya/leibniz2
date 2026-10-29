#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_repack_canonical_binding.py — Faz 4 kalan kalem: repack sidecar
yenilemesi ↔ kanonik kabul defteri (fail-closed).

Sözleşme
--------
`docs/ID_RESIDUAL_ACCEPTANCE.md` §5: PDF'in ham hash'i motor değişiminde
değişir, bu yüzden sidecar **tek seferlik bilinçli** yenilenir (V5l reuse
kuralı: ham hash değişmediyse sidecar'a dokunulmaz — qpdf'in kendi
kararsızlığı pakete hash gürültüsü eklemesin).

Faz 4 kalan kalemi: o yenileme **kanonik deftere bağlı** olmalı. Yani
`repack_delivery.py` sidecar'ı yenilerken

  1. yeni `/ID`-kanonik hash'i ÖLÇER (tek uygulama: `pdf_id_canonical.py`),
  2. defterin "Kanonik (referans)" sütununda ARAR,
  3. defterde YOKSA sidecar'a HİÇ yazmaz ve exit 1 verir (yarım/bağsız kayıt
     bırakmak, kaydın defterle çelişmesine yol açardı),
  4. kabul edilirse sidecar üç satır olur: stripped + `# raw:` + `# canonical:`.

Bu dosya iki tarafı senkron tutan kapıdır:

  * Birim/davranış: yenileme reddi sidecar'ı DEĞİŞTİRMEZ; kabulde `# canonical:`
    satırı ölçülen hash'i taşır ve `id_canonical.sidecar_canonical` onu okur.
  * Reuse yolu: kayıtta `# canonical:` varsa defterde kayıtlı olmak ve PDF'in
    ölçülen kanoniğiyle eşleşmek zorunda (aksi halde repack durur).
  * Commit'li artefaktlar: teslim PDF'inin kanonik hash'i defterde olmak
    zorunda; motor geçişi bugün yapılsa `renew_sidecar` kabul eder (repo
    dosyalarına yazmadan, yalnız temp kopyada ölçülür).

stdlib-only, OFFLINE. Repo artefaktlarına yazmaz; qpdf gerekmez (strip enjekte
edilir).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CALISMA = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(CALISMA))

import check_id_residual_doc_sync as doc_sync  # noqa: E402
import id_canonical  # noqa: E402
import pdf_id_canonical  # noqa: E402
import repack_delivery as rd  # noqa: E402

PDF_NAME = "ingiliz_empirizmi_v3.pdf"
RAW = "f" * 64
STRIPPED = "e" * 64


def pdf_bytes(id_a=b"1" * 32, id_b=b"2" * 32):
    """Minimal PDF: kanonik yüzeyi yalnız trailer `/ID` çifti taşır."""
    return (b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
            b"trailer\n<< /Size 2 /ID [<" + id_a + b"><" + id_b + b">] >>\n"
            b"%%EOF\n")


def ledger_doc(*canonicals):
    """`pdf_id_canonical` ayrıştırıcısının beklediği Kanonik sütun tablosu."""
    lines = ["| Motor | Ham (bilgi) | Kanonik (referans) |", "|---|---|---|"]
    for i, canonical in enumerate(canonicals):
        lines.append("| motor-%d | `%s` | `%s` |" % (i, RAW, canonical))
    return "\n".join(lines) + "\n"


def write(path, text):
    Path(path).write_text(text, encoding="utf-8")
    return Path(path)


class Fixture:
    def __init__(self, tmpdir):
        self.dir = Path(tmpdir)
        self.pdf = self.dir / PDF_NAME
        self.pdf.write_bytes(pdf_bytes())
        self.canonical, found = pdf_id_canonical.canonical_sha256_bytes(
            self.pdf.read_bytes())
        assert found, "sentetik PDF /ID taşımalı"
        # İçerik farklı OLMALI: yalnız `/ID` farkı kanonikte nötrlenir, yani
        # aynı hash'i verirdi (mismatch senaryosu boş geçerdi).
        self.other_pdf = self.dir / "other.pdf"
        self.other_pdf.write_bytes(
            pdf_bytes(b"3" * 32, b"4" * 32).replace(
                b"/Type /Catalog", b"/Type /Pages"))
        self.other_canonical, _ = pdf_id_canonical.canonical_sha256_bytes(
            self.other_pdf.read_bytes())

        self.ledger_ok = write(self.dir / "ledger-ok.md",
                               ledger_doc(self.canonical))
        self.ledger_other = write(self.dir / "ledger-other.md",
                                  ledger_doc(RAW))
        self.ledger_empty = write(self.dir / "ledger-empty.md",
                                  "| Motor | Kanonik (referans) |\n|---|---|\n")
        self.ledger_missing = self.dir / "ledger-yok.md"
        self.sidecar = self.dir / (PDF_NAME + ".metadata.sha256")

    def write_sidecar(self, raw, canonical=None):
        text = "%s  %s.metadata\n# raw: %s  %s\n" % (
            STRIPPED, PDF_NAME, raw, PDF_NAME)
        if canonical:
            text += "# canonical: %s  %s\n" % (canonical, PDF_NAME)
        return write(self.sidecar, text)


class RenewalBindingTests(unittest.TestCase):
    """Motor geçişi: kabul → üç satır; ret → HİÇ yazmama (fail-closed)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="repack-bind-")
        self.addCleanup(self._tmp.cleanup)
        self.fx = Fixture(self._tmp.name)

    def _renew(self, ledger_paths, sidecar=None):
        return rd.renew_sidecar(
            str(self.fx.pdf), str(sidecar or self.fx.sidecar),
            STRIPPED, RAW, ledger_paths=ledger_paths)

    def test_renewal_writes_canonical_line_and_binds_ledger(self):
        ok, detail = self._renew([self.fx.ledger_ok])
        self.assertTrue(ok, detail)
        self.assertIn("deftere bağlandı", detail)
        text = self.fx.sidecar.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 3, "sidecar 3 satır olmalı: %r" % lines)
        self.assertTrue(lines[0].startswith(STRIPPED))
        self.assertTrue(lines[1].startswith("# raw: %s" % RAW))
        self.assertTrue(lines[2].startswith("# canonical: %s" % self.fx.canonical))
        # Okuma tarafı ile yazma tarafı AYNI değeri görmeli (tek kaynak).
        self.assertEqual(
            id_canonical.sidecar_canonical(str(self.fx.sidecar)),
            self.fx.canonical)

    def test_renewal_refused_when_canonical_not_registered(self):
        ok, detail = self._renew([self.fx.ledger_other])
        self.assertFalse(ok, "defterde olmayan kanonik kabul edildi")
        self.assertIn("defterde YOK", detail)
        self.assertIn("make -f docs/Makefile.texlive accept", detail,
                      "çıkış yolu kullanıcıya gösterilmeli")
        self.assertFalse(self.fx.sidecar.exists(),
                         "ret varken sidecar yazılmamalı (yarım kayıt)")

    def test_renewal_refused_without_ledger(self):
        ok, detail = self._renew([self.fx.ledger_missing])
        self.assertFalse(ok)
        self.assertIn("defteri yok", detail)
        self.assertFalse(self.fx.sidecar.exists())

    def test_renewal_refused_with_empty_ledger(self):
        ok, detail = self._renew([self.fx.ledger_empty])
        self.assertFalse(ok)
        self.assertIn("okunamadı/boş", detail)
        self.assertFalse(self.fx.sidecar.exists())

    def test_refusal_preserves_existing_record(self):
        # Motor geçişi reddedilirse ESKİ kayıt bozulmadan kalmalı.
        sentinel = self.fx.write_sidecar(RAW, "a" * 64)
        before = sentinel.read_bytes()
        ok, _detail = self._renew([self.fx.ledger_other])
        self.assertFalse(ok)
        self.assertEqual(sentinel.read_bytes(), before,
                         "ret sonrası eski sidecar değişti")


class ReusePathBindingTests(unittest.TestCase):
    """V5l reuse: kayıt varsa defter ve PDF ile ÇELİŞEMEZ."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="repack-reuse-")
        self.addCleanup(self._tmp.cleanup)
        self.fx = Fixture(self._tmp.name)
        self.raw = rd.sha256(str(self.fx.pdf))

    def test_reuse_is_clean_for_registered_sidecar(self):
        self.fx.write_sidecar(self.raw, self.fx.canonical)
        self.assertIsNone(rd.sidecar_binding_problem(
            str(self.fx.pdf), str(self.fx.sidecar),
            [self.fx.ledger_ok]))
        ok, detail = rd.sync_metadata_sidecar(
            str(self.fx.pdf), str(self.fx.sidecar),
            ledger_paths=[self.fx.ledger_ok])
        self.assertTrue(ok, detail)
        self.assertIn("reuse", detail)

    def test_reuse_flags_unregistered_canonical(self):
        self.fx.write_sidecar(self.raw, "b" * 64)
        problem = rd.sidecar_binding_problem(
            str(self.fx.pdf), str(self.fx.sidecar), [self.fx.ledger_ok])
        self.assertIsNotNone(problem, "defterde olmayan sidecar kanoniği geçti")
        self.assertIn("defterde yok", problem)
        ok, _detail = rd.sync_metadata_sidecar(
            str(self.fx.pdf), str(self.fx.sidecar),
            ledger_paths=[self.fx.ledger_ok])
        self.assertFalse(ok, "reuse yolu defter çelişkisinde durmalı")

    def test_reuse_flags_sidecar_pdf_mismatch(self):
        # Kayıt defterde VAR ama başka bir PDF'in kanoniği → PDF ile çelişki.
        ledger = write(self.fx.dir / "ledger-both.md",
                       ledger_doc(self.fx.canonical, self.fx.other_canonical))
        self.fx.write_sidecar(self.raw, self.fx.other_canonical)
        problem = rd.sidecar_binding_problem(
            str(self.fx.pdf), str(self.fx.sidecar), [ledger])
        self.assertIsNotNone(problem)
        self.assertIn("uyuşmuyor", problem)

    def test_legacy_two_line_record_is_not_a_finding(self):
        # tectonic-era kayıt: `# canonical:` yok → §6 bilgi düzeyi.
        self.fx.write_sidecar(self.raw)
        self.assertIsNone(rd.sidecar_binding_problem(
            str(self.fx.pdf), str(self.fx.sidecar), [self.fx.ledger_ok]))


class EngineChangeFlowTests(unittest.TestCase):
    """Adım 0 kararı uçtan uca (qpdf enjekte edilir, gerçek qpdf gerekmez)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="repack-engine-")
        self.addCleanup(self._tmp.cleanup)
        self.fx = Fixture(self._tmp.name)

    def test_engine_change_accepted_writes_three_lines(self):
        self.fx.write_sidecar("a" * 64)          # bayat raw → yenileme
        strip = lambda src, dst: (Path(dst).write_bytes(  # noqa: E731
            Path(src).read_bytes()) or True)
        ok, detail = rd.sync_metadata_sidecar(
            str(self.fx.pdf), str(self.fx.sidecar),
            ledger_paths=[self.fx.ledger_ok], strip=strip)
        self.assertTrue(ok, detail)
        self.assertEqual(
            id_canonical.sidecar_canonical(str(self.fx.sidecar)),
            self.fx.canonical)

    def test_engine_change_rejected_when_ledger_lacks_canonical(self):
        self.fx.write_sidecar("a" * 64)
        before = self.fx.sidecar.read_bytes()
        strip = lambda src, dst: (Path(dst).write_bytes(  # noqa: E731
            Path(src).read_bytes()) or True)
        ok, detail = rd.sync_metadata_sidecar(
            str(self.fx.pdf), str(self.fx.sidecar),
            ledger_paths=[self.fx.ledger_other], strip=strip)
        self.assertFalse(ok)
        self.assertIn("defterde YOK", detail)
        self.assertEqual(self.fx.sidecar.read_bytes(), before,
                         "ret sonrası eski sidecar değişti")

    def test_strip_failure_fails_closed(self):
        self.fx.write_sidecar("a" * 64)
        ok, detail = rd.sync_metadata_sidecar(
            str(self.fx.pdf), str(self.fx.sidecar),
            ledger_paths=[self.fx.ledger_ok],
            strip=lambda _src, _dst: False)
        self.assertFalse(ok)
        self.assertIn("stripping başarısız", detail)

    def test_missing_qpdf_on_engine_change_fails_closed(self):
        self.fx.write_sidecar("a" * 64)
        original = rd._find_qpdf
        rd._find_qpdf = lambda: None
        try:
            ok, detail = rd.sync_metadata_sidecar(
                str(self.fx.pdf), str(self.fx.sidecar),
                ledger_paths=[self.fx.ledger_ok])
        finally:
            rd._find_qpdf = original
        self.assertFalse(ok)
        self.assertIn("qpdf yok", detail)


class SidecarLedgerHandshakeTests(unittest.TestCase):
    """YAZMA (repack) ↔ OKUMA (doc-sync kapısı) tek sözleşme.

    `renew_sidecar`ın yazdığı üç satırlık kayıt, `check_id_residual_doc_sync`
    kapısından **temiz** geçmek zorunda; reddedilen yenilemenin karşılığı da
    aynı kapıda `canonical` sütununda kırmızı olmalı. Aksi halde iki yüzey
    farklı gerçeklik taşır: repack kabul eder, kapı reddeder (ya da tersi).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="repack-handshake-")
        self.addCleanup(self._tmp.cleanup)
        self.fx = Fixture(self._tmp.name)
        self.raw = rd.sha256(str(self.fx.pdf))

    def _doc(self, canonical):
        """§4 alt-tablo şekli: sütun adları kapının kendi ayrıştırıcısına uygun."""
        text = ("| Dönem | Ham PDF (bilgi) | Metadata-stripped | "
                "Kanonik `/ID`-nötr (referans) | Durum |\n"
                "|---|---|---|---|---|\n"
                "| tectonic-era teslim (V5l; mevcut) | `%s` | `%s` | `%s` "
                "| yanındaki sidecar |\n" % (self.raw, STRIPPED, canonical))
        return write(self.fx.dir / "ID_RESIDUAL_ACCEPTANCE.md", text)

    def _gate(self, canonical):
        return doc_sync.check(self._doc(canonical), self.fx.sidecar, PDF_NAME)

    def test_renewed_record_passes_the_doc_sync_gate(self):
        ok, detail = rd.renew_sidecar(
            str(self.fx.pdf), str(self.fx.sidecar), STRIPPED, self.raw,
            ledger_paths=[self.fx.ledger_ok])
        self.assertTrue(ok, detail)
        findings, notes, _facts = self._gate(self.fx.canonical)
        self.assertEqual(findings, [],
                         "repack'in yazdığı kayıt kapıda kırmızı: %r" % findings)
        self.assertEqual(notes, [],
                         "iki taraf da kanonik taşıyor; NOT kalmamalı: %r" % notes)

    def test_legacy_record_is_note_but_renewal_closes_it(self):
        # Yenilemeden ÖNCE: kayıtta `# canonical:` yok → kapı NOT üretir.
        self.fx.write_sidecar(self.raw)
        findings, notes, _facts = self._gate(self.fx.canonical)
        self.assertEqual(findings, [])
        self.assertEqual([n["kind"] for n in notes],
                         ["canonical_not_in_record"])
        # Yenileme sonrası aynı kapı NOT'suz ve temiz olmalı.
        ok, detail = rd.renew_sidecar(
            str(self.fx.pdf), str(self.fx.sidecar), STRIPPED, self.raw,
            ledger_paths=[self.fx.ledger_ok])
        self.assertTrue(ok, detail)
        findings, notes, _facts = self._gate(self.fx.canonical)
        self.assertEqual((findings, notes), ([], []))

    def test_unregistered_record_fails_both_surfaces(self):
        # Defter başka bir kanonik taşıyor: repack yazmayı reddeder...
        self.fx.write_sidecar(self.raw)
        before = self.fx.sidecar.read_bytes()
        ok, _detail = rd.renew_sidecar(
            str(self.fx.pdf), str(self.fx.sidecar), STRIPPED, self.raw,
            ledger_paths=[self.fx.ledger_other])
        self.assertFalse(ok)
        self.assertEqual(self.fx.sidecar.read_bytes(), before)
        # ...ve elle yazılmış olsa kapı da aynı sütunda kırmızı verir.
        self.fx.write_sidecar(self.raw, "b" * 64)
        findings, _notes, _facts = self._gate(self.fx.canonical)
        self.assertEqual([f["column"] for f in findings], ["canonical"])
        self.assertEqual(findings[0]["kind"], "doc_value_mismatch")


class CommittedArtifactsStayInSync(unittest.TestCase):
    """Gerçek teslim artefaktları: PDF ↔ defter ↔ sidecar tek hizada."""

    PDF = (ROOT / "_calisma" / "V5_ICERIK" / "TESLIM_V5_FINAL_2026-08-17"
           / "stoic_hume_package" / "Stoic_Hume_Formal_Section_2026-08-17"
           / PDF_NAME)
    SIDECAR = PDF.parent / (PDF_NAME + ".metadata.sha256")
    LEDGER = ROOT / "docs" / "ID_RESIDUAL_ACCEPTANCE.md"

    def setUp(self):
        if not self.PDF.is_file() or not self.LEDGER.is_file():
            self.skipTest("teslim PDF'i veya defter yok")
        self.accepted = rd.ledger_canonicals(str(self.LEDGER))
        self.measured, self.id_found = rd.measure_canonical(str(self.PDF))

    def test_delivery_pdf_canonical_is_registered(self):
        self.assertTrue(self.accepted, "kabul defteri boş — bağ kurulamaz")
        self.assertTrue(self.measured, "teslim PDF'inin kanoniği ölçülemedi")
        self.assertIn(
            self.measured, self.accepted,
            "teslim PDF'i kanonik hash'i defterde YOK — motor geçişi "
            "fail-closed durur (make -f docs/Makefile.texlive accept)")

    def test_sidecar_canonical_matches_ledger_and_pdf(self):
        if not self.SIDECAR.is_file():
            self.skipTest("donmuş kayıt yok")
        recorded = id_canonical.sidecar_canonical(str(self.SIDECAR))
        if recorded is None:
            self.skipTest("tectonic-era iki satırlı kayıt (§6: bilgi düzeyi)")
        self.assertIn(recorded, self.accepted,
                      "sidecar kanoniği defterde yok")
        self.assertEqual(recorded, self.measured,
                         "sidecar kanoniği PDF'le uyuşmuyor")

    def test_reuse_binding_is_clean_on_committed_package(self):
        if not self.SIDECAR.is_file():
            self.skipTest("donmuş kayıt yok")
        self.assertIsNone(
            rd.sidecar_binding_problem(str(self.PDF), str(self.SIDECAR),
                                       [str(self.LEDGER)]),
            "commit'li sidecar ↔ defter/PDF çelişkisi (repack reuse durur)")

    def test_engine_change_would_be_accepted_today(self):
        # Motor geçişi bugün yapılsa yenileme kabul edilmeli; yalnız TEMP
        # kopyaya yazılır, repo artefaktı değişmez.
        with tempfile.TemporaryDirectory(prefix="repack-committed-") as tmp:
            sidecar = Path(tmp) / (PDF_NAME + ".metadata.sha256")
            if self.SIDECAR.is_file():
                sidecar.write_bytes(self.SIDECAR.read_bytes())
            ok, detail = rd.renew_sidecar(
                str(self.PDF), str(sidecar), STRIPPED,
                rd.sha256(str(self.PDF)), ledger_paths=[str(self.LEDGER)])
            self.assertTrue(ok, detail)
            self.assertEqual(
                id_canonical.sidecar_canonical(str(sidecar)), self.measured)


if __name__ == "__main__":
    unittest.main()
