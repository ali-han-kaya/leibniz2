#!/usr/bin/env python3
"""test_k6_determ_canonical.py — K6-DETERM /ID-kanonik determinizm sözleşmesi.

Faz 4 (docs/TEXLIVE_MIGRATION_PLAN.md) uygulamasını OFFLINE sabitler:

  1) `canonical_pdf_sha256` — `/ID` çiftini `<0…0>`'a indirger: farklı /ID
     taşıyan iki PDF aynı kanonik hash'i verir; İÇERİK farkı kanonikte de
     görünür (hiçbir fark gizlenmez); `/ID` deseni yoksa ham hash döner
     (fail-safe); okunamayan dosyada None.
  2) `id_residual_ledger_tokens` — kabul defterindeki ölçülmüş tam kanonik
     hash'leri (ad8fca69/a75c3409/544516b0 + teslim kanoniği d4f67e39)
     toplar; plan-donmuş ÖNEK (47681218) tam hash sayılmaz; defter
     okunamazsa boş küme + hata.
  3) `k6_determ_verdict` — strict OFF hiçbir koşulda P1 üretmez; strict ON
     defterde kayıtlı kanonikte geçer, kayıtlı değilse P1 + remedy verir,
     defter/PDF okunamıyorsa fail-closed P1.
  4) `verify_delivery.py` K6-DETERM gövdesi bu yardımcıları çağırır ve
     metadata-stripped hash'i P1 nedeni YAPMAZ (qpdf kendi /ID'sini rastgele
     üretir: ölçüldü 3 koşum → 3 farklı hash); eski "tectonic
     non-deterministic" teşhisi kaynakta kalmaz.
  5) Ortak çekirdek `id_canonical.py`: aday sırası (env → repo docs →
     mirror drop), kaynak raporlama, `# canonical:` sidecar ayrıştırıcısı ve
     `has_canonical` — verify_delivery + repack_delivery + K14 aynı modülü
     kullandığı için tek sözleşme burada sabitlenir.

stdlib-only, OFFLINE.
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

CIKTI = Path(__file__).resolve().parent
ROOT = CIKTI.parent.parent
sys.path.insert(0, str(CIKTI))
import verify_delivery as vd  # noqa: E402
import id_canonical as idc  # noqa: E402  (ortak determinizm çekirdeği)

LEDGER = ROOT / "docs" / "ID_RESIDUAL_ACCEPTANCE.md"
DELIVERY_PDF = (ROOT / "_calisma" / "V5_ICERIK" / "TESLIM_V5_FINAL_2026-08-17"
                / "stoic_hume_package" / "Stoic_Hume_Formal_Section_2026-08-17"
                / "ingiliz_empirizmi_v3.pdf")

TECTONIC_SINGLE = ("ad8fca69d4e4a2e1d67e497c8a7449f22"
                   "c8564f5e9b3790d0b6f85d90d318e1b")
PDFTEX_SINGLE = ("a75c340911801273b38be6ffb51a3482"
                 "0764b8f812d528dd2705d64117f1aa00")
PDFTEX_3PASS = ("544516b0d9d2f4c12b05b512b79b31ad"
                "238e82d3ca3aff81166a6bac1914f597")
DELIVERY_CANONICAL = ("d4f67e39fd0ef77e8f294ca2195bb1fc"
                      "784716234d0675ab88a4fd8695263a6a")


def _fake_pdf(id_pair, canary=b"govde"):
    """Küçük sahte PDF: trailer /ID çifti + içerik canary baytı."""
    return (b"%PDF-1.5\n" + canary + b"\ntrailer\n/ID [" + id_pair
            + b"]\n%%EOF\n")


class TestCanonicalHash(unittest.TestCase):
    def _write(self, td, name, data):
        p = Path(td) / name
        p.write_bytes(data)
        return str(p)

    def test_id_only_difference_yields_same_canonical(self):
        with tempfile.TemporaryDirectory() as td:
            a = self._write(td, "a.pdf",
                            _fake_pdf(b"<" + b"AA" * 16 + b"> <" + b"AA" * 16 + b">"))
            b = self._write(td, "b.pdf",
                            _fake_pdf(b"<" + b"BB" * 16 + b"> <" + b"CC" * 16 + b">"))
            self.assertNotEqual(vd.sha256_file(a), vd.sha256_file(b),
                                "ham hash'ler /ID yüzünden farklı olmalı")
            self.assertEqual(vd.canonical_pdf_sha256(a),
                             vd.canonical_pdf_sha256(b),
                             "/ID nötrlenince kanonik hash eşit olmalı")

    def test_content_difference_changes_canonical(self):
        # Fail-safe: kanonikleştirme içerik farkını GİZLEMEZ.
        with tempfile.TemporaryDirectory() as td:
            a = self._write(td, "a.pdf", _fake_pdf(b"<" + b"AA" * 16 + b"> <" + b"AA" * 16 + b">",
                                                   canary=b"bir"))
            b = self._write(td, "b.pdf", _fake_pdf(b"<" + b"AA" * 16 + b"> <" + b"AA" * 16 + b">",
                                                   canary=b"iki"))
            self.assertNotEqual(vd.canonical_pdf_sha256(a),
                                vd.canonical_pdf_sha256(b))

    def test_without_id_pattern_canonical_equals_raw(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, "c.pdf", b"%PDF-1.5\nno trailer id here\n")
            self.assertEqual(vd.canonical_pdf_sha256(p), vd.sha256_file(p))

    def test_unreadable_file_returns_none(self):
        self.assertIsNone(vd.canonical_pdf_sha256("/nonexistent/x.pdf"))

    def test_real_delivery_canonical_is_stable_and_pinned(self):
        # Teslim PDF'inin kanonik referansı defterdeki satırla birebir
        # olmalı; ardışık ölçümler aynı değeri vermeli.
        if not DELIVERY_PDF.is_file():
            self.skipTest("teslim PDF'i yok")
        first = vd.canonical_pdf_sha256(str(DELIVERY_PDF))
        self.assertEqual(first, DELIVERY_CANONICAL)
        self.assertEqual(first, vd.canonical_pdf_sha256(str(DELIVERY_PDF)))


class TestLedgerBinding(unittest.TestCase):
    def test_ledger_tokens_include_measured_canonical_hashes(self):
        tokens, err = vd.id_residual_ledger_tokens(str(LEDGER))
        self.assertEqual(err, "")
        for h, etiket in ((TECTONIC_SINGLE, "tectonic tek-geçiş"),
                          (PDFTEX_SINGLE, "pdfTeX tek-geçiş"),
                          (PDFTEX_3PASS, "pdfTeX 3-geçiş"),
                          (DELIVERY_CANONICAL, "teslim kanoniği")):
            self.assertIn(h, tokens, f"defter {etiket} kanonik hash'ini taşımalı")
        # Plan-donmuş önek tam hash değildir → token kümesine girmez.
        self.assertFalse([t for t in tokens if t.startswith("47681218")],
                         "önek sahte tam-hash olarak toplanmamalı")
        self.assertTrue(all(len(t) == 64 for t in tokens))

    def test_ledger_missing_reports_error(self):
        tokens, err = vd.id_residual_ledger_tokens("/nonexistent/defter.md")
        self.assertEqual(tokens, set())
        self.assertIn("defter.md", err)


class TestVerdict(unittest.TestCase):
    def test_strict_off_never_fails(self):
        for canonical in (DELIVERY_CANONICAL, None):
            ok, pri, _ = vd.k6_determ_verdict(False, canonical, set())
            self.assertTrue(ok)
            self.assertIsNone(pri)

    def test_strict_on_accepts_recorded_canonical(self):
        ok, pri, detail = vd.k6_determ_verdict(True, DELIVERY_CANONICAL,
                                               {DELIVERY_CANONICAL})
        self.assertTrue(ok)
        self.assertIsNone(pri)
        self.assertIn("defterinde kayıtlı", detail)

    def test_strict_on_flags_unrecorded_canonical(self):
        ok, pri, detail = vd.k6_determ_verdict(True, DELIVERY_CANONICAL, set())
        self.assertFalse(ok)
        self.assertEqual(pri, "P1")
        self.assertIn("kabul defterinde yok", detail)
        self.assertIn("LEDGER=update", detail)  # uygulanabilir remedy

    def test_strict_on_is_fail_closed_without_reference(self):
        ok, pri, detail = vd.k6_determ_verdict(True, DELIVERY_CANONICAL, set(),
                                               "defter okunamadı")
        self.assertFalse(ok)
        self.assertEqual(pri, "P1")
        self.assertIn("okunamadı", detail)
        # PDF okunamadıysa referans doğrulanamaz → strict'te fail-closed.
        ok2, pri2, _ = vd.k6_determ_verdict(True, None, set())
        self.assertFalse(ok2)
        self.assertEqual(pri2, "P1")


class TestIdCanonicalModule(unittest.TestCase):
    """Ortak çekirdek `id_canonical.py` — üç tüketicinin (verify_delivery,
    repack, K14) paylaştığı defter çözümlemesi + sidecar ayrıştırıcısı.

    Bu sözleşme tek kaynakta tutulduğu için kopya regex/defter mantığı
    çürüyemez; aşağıdaki testler aday sırasını, kaynak raporlamayı ve
    sidecar `# canonical:` ayrıştırmasını sabitler.
    """

    def test_candidate_order_env_then_repo_then_flat(self):
        repo_doc = os.path.join(idc.REPO_ROOT, idc.LEDGER_DOC)
        flat = os.path.join(idc.HERE, idc.LEDGER_FLAT_NAME)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(idc.LEDGER_ENV, None)
            cands = idc.ledger_candidates()
        self.assertEqual(cands[0], repo_doc, "env yoksa ilk aday repo defteri")
        self.assertEqual(cands[-1], flat, "son aday mirror-drop kopyası")
        with mock.patch.dict(os.environ, {idc.LEDGER_ENV: "/tmp/x.md"}):
            cands = idc.ledger_candidates()
        self.assertEqual(cands[0], "/tmp/x.md", "env adayı en başta olmalı")

    def test_ledger_tokens_reports_source(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "ID_RESIDUAL_ACCEPTANCE.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write("xxx %s yyy\n" % ("a" * 64))
            tokens, err, src = idc.ledger_tokens(p)
        self.assertEqual(err, "")
        self.assertEqual(src, p)
        self.assertEqual(tokens, {"a" * 64})

    def test_ledger_tokens_missing_reports_all_candidates(self):
        tokens, err, src = idc.ledger_tokens("/nonexistent/nowhere.md")
        self.assertEqual(tokens, set())
        self.assertIsNone(src)
        self.assertIn("nowhere.md", err)

    def test_has_canonical_none_is_false(self):
        self.assertFalse(idc.has_canonical(None, {"a" * 64}))
        self.assertTrue(idc.has_canonical("a" * 64, {"a" * 64}))

    def test_sidecar_canonical_parses_lowercased(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "x.pdf.metadata.sha256")
            with open(p, "w", encoding="utf-8") as f:
                f.write("deadbeef  x.pdf.metadata\n")
                f.write("# raw: rrr  x.pdf\n")
                f.write(f"# canonical: {'AB' * 32}  x.pdf\n")
            self.assertEqual(idc.sidecar_canonical(p), "ab" * 32)

    def test_sidecar_canonical_none_when_absent_or_missing(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "x.pdf.metadata.sha256")
            with open(p, "w", encoding="utf-8") as f:
                f.write("deadbeef  x.pdf.metadata\n# raw: rrr  x.pdf\n")
            self.assertIsNone(idc.sidecar_canonical(p))
        self.assertIsNone(idc.sidecar_canonical("/nonexistent/sidecar"))


class TestVerifyDeliveryWiring(unittest.TestCase):
    """K6-DETERM gövdesinin kaynak sözleşmesi (adaptör guard'ı)."""

    def setUp(self):
        self.src = (CIKTI / "verify_delivery.py").read_text(encoding="utf-8")

    def test_block_uses_canonical_helpers(self):
        # Faz 4: gövde ortak `id_canonical` modülünü kullanır — defter
        # çözümü `resolve_id_residual_ledger()` (3-değerli: tokens/error/
        # source) ve sidecar referansı `_idc.sidecar_canonical`. Kanonik
        # hash de tek kaynaktan gelir; P1 kararı saftır (k6_determ_verdict).
        for token in ("canonical_pdf_sha256(pdf)", "resolve_id_residual_ledger()",
                      "k6_determ_verdict(", "ID_RESIDUAL_LEDGER_DOC",
                      "_idc.sidecar_canonical", "sidecar_canonical="):
            self.assertIn(token, self.src, f"K6-DETERM gövdesi {token} kullanmalı")

    def test_stale_diagnosis_and_stripped_strict_p1_are_gone(self):
        # Eski teşhis ("tectonic non-deterministic" → strict karşılaştırma
        # yanlış pozitif üretir) ve stripped-hash'e bağlı strict P1 kalmamalı.
        self.assertNotIn("tectonic non-deterministic", self.src)
        self.assertNotIn("metadata-stripped hash drift (strict)", self.src)

    def test_strict_flag_help_names_the_ledger(self):
        # Yardım metni kaynakta satırlara bölünmüş; bitişik string
        # literallerini birleştirip RENDER edilmiş metni denetle.
        joined = re.sub(r'"\s*\n\s*"', "", self.src)
        self.assertIn("kabul defterinde (docs/ID_RESIDUAL_ACCEPTANCE.md)",
                      joined)


if __name__ == "__main__":
    unittest.main()
