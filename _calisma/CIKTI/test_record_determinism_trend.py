#!/usr/bin/env python3
"""test_record_determinism_trend.py — determinizm trend kaydı davranış kapısı.

record_determinism_trend.py sözleşmelerini OFFLINE sabitler:

  1) Rapor extract: kanıt alanlarından ölçüm çıkarımı; bozuk raporda
     fail-closed ValueError (verdict != PASS, eksik alan, 64-hex olmayan
     hash, rapor-içi koşum çelişkisi).
  2) --update: gerçek rapor yoksa fail-closed rc=1 (deney koşulmadan
     kayıt üretilmez); rapor varsa ölçüm eklenir.
  3) --check değişmezleri (trend_invariant): boş trend geçici-FAIL; bayat
     ölçüm FAIL; aynı kaynakta hash sapması FAIL (uzlaşma ihlali); kaynak
     değişince serbest; platform kapsamı (cutoff sonrası darwin+linux)
     eksikse FAIL; iki platform aynı kaynak+hash'i paylaşırsa OK.
  4) jsonl yalnız eklenir; bozuk satırda ValueError.
  5) AİLELER (2026-10-08): canvas satırı ayrı seridir. Değişmezler aile
     BAŞINA uygulanır — taze canvas satırı bayat manuscript serisini yeşile
     boyayamaz (fail-open regresyon testi); her iki aile de trendde bulunmalı;
     şema-dışı `family` değeri kırmızıdır. Canvas modu yalnız apex (kitap)
     kaynağını kabul eder ve aile SDE sabitini (1700000000) zorlar.

Tarihler cutoff'tan (2026-09-17) SONRA seçilir ki yalnız hedeflenen
değişmez ihlal edilsin (izole senaryolar). stdlib-only, OFFLINE.
"""
import contextlib
import datetime
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

CIKTI = Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))
import record_determinism_trend as rdt  # noqa: E402

ROOT = CIKTI.parent.parent
REAL_REPORT = ROOT / "docs" / "ci_simulate" / "texlive_determinism" / \
    "texlive_determinism_report.txt"
NOW = datetime.date(2026, 9, 24)  # cutoff'tan sonra; taze pencere içi


def _crec(**over):
    """Canvas ailesi satırı: tectonic tek bacağı (`texlive_*` ALANINI TAŞIMAZ).

    Bu eksiklik bilinçlidir — uzlaşma değişmezi ailenin ORTAK alanlarını
    denetler; texlive alanı canvas'ta yok diye kırmızı çıkmamalı.
    """
    base = {
        "date": "2026-09-22",
        "family": "canvas",
        "source_mtime": 1758000100,
        "tectonic_bin": "/opt/homebrew/bin/tectonic",
        "tectonic_canonical_sha256": "e" * 64,
        "source_sha256": "d" * 64,
        "sde": 1700000000,
        "platform": "darwin",
        "gate": "PASS",
    }
    base.update(over)
    return base


def _canvas_pair():
    """Canvas serisi: darwin + linux, taze (NOW penceresi) + cutoff sonrası +
    aynı kaynak/hash → aile tam OK (yalnız hedeflenen ihlal izole edilir)."""
    return [_crec(date="2026-09-22", platform="darwin"),
            _crec(date="2026-09-23", platform="linux")]


def _ms_pair():
    """Manuscript serisi: darwin + linux, taze + cutoff sonrası + temiz."""
    return [_rec(date="2026-09-23", platform="darwin"),
            _rec(date="2026-09-23", platform="linux")]


def _rec(**over):
    base = {
        "date": "2026-09-18",
        "source_mtime": 1758000000,
        "tectonic_bin": "/opt/homebrew/bin/tectonic",
        "texlive_bin": "/opt/homebrew/bin/pdflatex",
        "tectonic_canonical_sha256": "a" * 64,
        "texlive_canonical_sha256": "b" * 64,
        "source_sha256": "c" * 64,
        "sde": 0,
        "platform": "darwin",
        "gate": "PASS",
    }
    base.update(over)
    return base


def _canvas_report(**over):
    """canvas_determinism_test.sh raporu — anahtarlar GERÇEK raporla birebir
    (gerçek örnek: docs/ci_simulate/canvas_determinism/*.determinism.txt)."""
    base = {
        "source": "",
        "tectonic": "/opt/homebrew/bin/tectonic",
        "source_date_epoch": "1700000000",
        "hash_form": "canonical (/ID notr; tek uygulama pdf_id_canonical.py)",
        "id_form": "id_found",
        "tectonic_raw_run1_sha256": "a" * 64,
        "tectonic_raw_run2_sha256": "a" * 64,
        "tectonic_run1_sha256": "c" * 64,
        "tectonic_run2_sha256": "c" * 64,
        "residual": "none",
        "verdict": "PASS",
    }
    base.update(over)
    return base


class TestParseAndExtract(unittest.TestCase):
    def test_extract_ok(self):
        report = {
            "tectonic_sha256": "a" * 64,
            "texlive_canonical_run1_sha256": "b" * 64,
            "texlive_canonical_run2_sha256": "b" * 64,
            "verdict": "PASS",
        }
        data = rdt._extract_report_data(report)
        self.assertEqual(data["tectonic_canonical_sha256"], "a" * 64)
        self.assertEqual(data["texlive_canonical_sha256"], "b" * 64)

    def test_extract_fail_closed(self):
        bad = [
            {},  # boş rapor
            {"tectonic_sha256": "a" * 64,  # verdict FAIL
             "texlive_canonical_run1_sha256": "b" * 64,
             "texlive_canonical_run2_sha256": "b" * 64,
             "verdict": "FAIL"},
            {"tectonic_sha256": "zz",  # hash biçimi bozuk
             "texlive_canonical_run1_sha256": "b" * 64,
             "texlive_canonical_run2_sha256": "b" * 64,
             "verdict": "PASS"},
            {"tectonic_sha256": "a" * 64,  # rapor-içi koşum çelişkisi
             "texlive_canonical_run1_sha256": "b" * 64,
             "texlive_canonical_run2_sha256": "e" * 64,
             "verdict": "PASS"},
        ]
        for report in bad:
            with self.assertRaises(ValueError):
                rdt._extract_report_data(report)

    def test_read_report_keyvalue(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "report.txt"
            p.write_text("a=1\nb=iki bir\n#c yorum\n\n", encoding="utf-8")
            fields = rdt._read_report(p)
        self.assertEqual(fields, {"a": "1", "b": "iki bir"})


class TestUpdateMode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="trend-test-")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_update_appends_real_report(self):
        # Gerçek kanıt raporuyla --update: jsonl'a ölçüm ekler (izolasyon:
        # TREND temp'e yönlendirilir — test asla gerçek trend dosyasına
        # yazmaz; aksi halde her batarya koşumu kanıta sahte ölçüm ekler).
        if not REAL_REPORT.exists():
            self.skipTest("gerçek deney raporu yok (deney koşulmamış)")
        with tempfile.TemporaryDirectory() as td:
            fake_trend = os.path.join(td, "trend.jsonl")
            orig_trend = rdt.TREND
            rdt.TREND = fake_trend
            try:
                rc = rdt.main(["--update"])
                self.assertEqual(rc, 0)
                lines = rdt._records(fake_trend)
                self.assertEqual(len(lines), 1)  # append-only + tek ölçüm
                self.assertEqual(lines[0]["gate"], "PASS")
                self.assertIn("platform", lines[0])
            finally:
                rdt.TREND = orig_trend

    def test_records_rejects_corrupt_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "trend.jsonl"
            p.write_text('{"date": "2026-09-18"}\n{bozuk\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                rdt._records(p)

    def test_trend_path_is_versioned(self):
        # Trend dosyası git-takipli konumda olmalı — versiyonlanma asıl amaç;
        # docs/ci_simulate ignore edilmiş konumda kayıt (asla) versiyonlanmaz.
        self.assertIn("docs/determinism_trend", rdt.TREND)

    def test_stale_evidence_is_recorded(self):
        # 48h bayat-kanıt koruması kaldırıldı: --update, rapor bayat olsa bile
        # ölçümü ekler. Kaydın dürüstlüğü date alanındadır; tazelik iddiası
        # --check kapısının işidir. Temp trend'e yazar (gerçek dosyaya dokunmaz).
        if not REAL_REPORT.exists():
            self.skipTest("gerçek deney raporu yok (deney koşulmamış)")
        orig_trend = rdt.TREND
        with tempfile.TemporaryDirectory() as td:
            rdt.TREND = os.path.join(td, "trend.jsonl")
            try:
                self.assertEqual(rdt.main(["--update"]), 0)  # bayat da olsa kaydolur
                self.assertEqual(len(rdt._records(rdt.TREND)), 1)
            finally:
                rdt.TREND = orig_trend


class TestTrendInvariant(unittest.TestCase):
    def test_empty_trend_temporary_fail(self):
        v = rdt.trend_invariant([])
        self.assertIn("trend boş", v)

    def test_current_single_platform_flags_scope_only(self):
        # Taze tek platform: gençlik/uzlaşma OK; yalnız kapsam FAIL der.
        v = rdt.trend_invariant([_rec(platform="darwin")], now=NOW)
        self.assertIn("platform kapsamı eksik", v)
        self.assertNotIn("bayat", v)
        self.assertNotIn("aynı kaynakta değişti", v)

    def test_stale_latest_record_fails(self):
        v = rdt.trend_invariant(
            [_rec(date="2026-09-18", platform="darwin"),
             _rec(date="2026-09-10", platform="linux")],
            now=NOW)
        self.assertIn("bayat", v)
        self.assertIn("platform kapsamı eksik", v)  # linux cutoff ÖNCESİ değil —
        # 09-10 < cutoff → kapsam sayılmaz; darwin tek başına kapsam dışı bırakır.

    def test_concordance_violation_same_platform(self):
        # Aynı platform + aynı kaynak + farklı hash → uzlaşma ihlali.
        recs = [_rec(platform="darwin"),
                _rec(platform="darwin",
                     tectonic_canonical_sha256="d" * 64)]
        v = rdt.trend_invariant(recs, now=NOW)
        self.assertIn("aynı kaynakta değişti", v)

    def test_concordance_free_cross_platform(self):
        # Aynı kaynak, FARKLI platform, farklı hash → ihlal DEĞİL
        # (CI Debian TeXLive vs lokal Homebrew — R3: ölçmeden varsayma).
        recs = [_rec(platform="darwin"),
                _rec(platform="linux",
                     tectonic_canonical_sha256="d" * 64,
                     texlive_canonical_sha256="e" * 64)] + _canvas_pair()
        v = rdt.trend_invariant(recs, now=NOW)
        self.assertEqual(v, "OK")  # kapsam dolu, uzlaşma cross-platform yok

    def test_cross_platform_note_equal_and_unequal(self):
        # Not fonksiyonu: eşitlik → güçlü kanıt notu; eşitsizlik → beklenen
        # fark notu; tek platform → None.
        self.assertIsNone(rdt._cross_platform_note([_rec()]))
        eq = rdt._cross_platform_note(
            [_rec(platform="darwin"), _rec(platform="linux")])
        self.assertIn("birebir eşit", eq)
        ne = rdt._cross_platform_note(
            [_rec(platform="darwin"),
             _rec(platform="linux",
                  tectonic_canonical_sha256="d" * 64)])
        self.assertIn("beklenen", ne)

    def test_concordance_free_when_source_changed(self):
        recs = [_rec(source_sha256="c" * 64),
                _rec(source_sha256="f" * 64, platform="linux")] + _canvas_pair()
        v = rdt.trend_invariant(recs, now=NOW)
        # Kaynak değişti → uzlaşma serbest; tarihler cutoff sonrası ve iki
        # platform da mevcut olduğundan kapsam dolu → tamamen OK.
        self.assertNotIn("aynı kaynakta değişti", v)
        self.assertEqual(v, "OK")

    def test_concordance_cross_platform_same_hash_ok(self):
        recs = [_rec(platform="darwin"), _rec(platform="linux")] + _canvas_pair()
        v = rdt.trend_invariant(recs, now=NOW)
        self.assertEqual(v, "OK")

    def test_fresh_two_platform_chain_ok(self):
        recs = [_rec(date="2026-09-20", platform="darwin"),
                _rec(date="2026-09-22", platform="linux")] + _canvas_pair()
        v = rdt.trend_invariant(recs, now=NOW)
        self.assertEqual(v, "OK")


class TestFamilyAwareInvariants(unittest.TestCase):
    """Aile ayrımı: taze/temiz bir aile, diğer ailenin ihlalini kapatamaz."""

    def test_fresh_canvas_cannot_mask_stale_manuscript(self):
        # BAŞLIK fail-open regresyonu: canvas satırı taze + kapsamı tam,
        # manuscript 10 gün bayat → eski (aile ayrımı yok) kod `rows[-1]`e
        # bakıp yeşil çıkabilirdi.
        recs = [_rec(date="2026-09-01", platform="linux")] + _canvas_pair()
        v = rdt.trend_invariant(recs, now=NOW)
        self.assertNotEqual(v, "OK")
        self.assertIn("[manuscript] son ölçüm bayat", v)
        self.assertNotIn("[canvas]", v)  # canvas ailesi tertemiz

    def test_stale_canvas_is_reported_under_canvas(self):
        recs = _ms_pair() + [_crec(date="2026-09-01", platform="darwin")]
        v = rdt.trend_invariant(recs, now=NOW)
        self.assertIn("[canvas] son ölçüm bayat", v)
        self.assertNotIn("[manuscript]", v)

    def test_missing_canvas_family_fails_closed(self):
        # Eski dosya biçimi (yalnız manuscript satırları) artık yeterli değil:
        # canvas serisi hiç başlamamışsa kırmızı — sessiz aile kaybı.
        v = rdt.trend_invariant(_ms_pair(), now=NOW)
        self.assertIn("[canvas] kayıt yok", v)
        self.assertNotEqual(v, "OK")

    def test_unknown_family_fails_closed(self):
        recs = (_ms_pair() + _canvas_pair()
                + [_crec(family="canvass", date="2026-09-23")])
        v = rdt.trend_invariant(recs, now=NOW)
        self.assertIn("[canvass] şema-dışı aile", v)

    def test_canvas_platform_scope_requires_linux(self):
        # İlk canvas ölçümü darwin; linux kaydı CI koşumundan gelir —
        # o gelene kadar aile kapsamı eksik (bilinçli fail-closed kırmızı).
        recs = _ms_pair() + [_crec(date="2026-09-23", platform="darwin")]
        v = rdt.trend_invariant(recs, now=NOW)
        self.assertIn("[canvas] platform kapsamı eksik", v)
        self.assertIn("linux", v)
        self.assertNotIn("[manuscript]", v)

    def test_canvas_concordance_covers_tectonic_leg(self):
        # canvas'ta texlive bacağı yok; uzlaşma yine de tectonic'i denetler
        # (dinamik hash_keys) ve kapsam/gencilik ihlali üretmez.
        recs = _ms_pair() + [
            _crec(date="2026-09-21", platform="linux"),
            _crec(date="2026-09-22", platform="darwin"),
            _crec(date="2026-09-23", platform="darwin",
                  tectonic_canonical_sha256="f" * 64)]
        v = rdt.trend_invariant(recs, now=NOW)
        self.assertIn(
            "[canvas] tectonic_canonical_sha256 aynı kaynakta değişti", v)
        self.assertNotIn("platform kapsamı eksik", v)


class TestFamilySchema(unittest.TestCase):
    """family_of / hash_keys: geriye dönük okuma + dinamik alan kapsamı."""

    def test_family_of_defaults_to_manuscript(self):
        self.assertEqual(rdt.family_of(_rec()), rdt.FAMILY_MANUSCRIPT)
        self.assertEqual(rdt.family_of({}), rdt.FAMILY_MANUSCRIPT)
        self.assertEqual(rdt.family_of({"family": ""}), rdt.FAMILY_MANUSCRIPT)
        self.assertEqual(rdt.family_of({"family": 42}), rdt.FAMILY_MANUSCRIPT)
        self.assertEqual(rdt.family_of(_crec()), rdt.FAMILY_CANVAS)

    def test_hash_keys_is_per_family_and_dynamic(self):
        self.assertEqual(rdt.hash_keys(_rec()),
                         ("tectonic_canonical_sha256",
                          "texlive_canonical_sha256"))
        self.assertEqual(rdt.hash_keys(_crec()),
                         ("tectonic_canonical_sha256",))
        fut = _crec()
        fut["future_canonical_sha256"] = "a" * 64
        self.assertIn("future_canonical_sha256", rdt.hash_keys(fut))

    def test_cross_platform_note_is_family_scoped(self):
        # Karışık seride kıyas SADECE aynı aile içinde yapılır: canvas
        # darwin+linux eşitken manuscript'siz dönmeli (eşitlik kanıtı yok).
        note = rdt._cross_platform_note(_canvas_pair())
        self.assertIsNone(note)  # varsayılan aile manuscript
        note = rdt._cross_platform_note(_canvas_pair(), rdt.FAMILY_CANVAS)
        self.assertIn("birebir eşit", note)
        self.assertIn("[canvas]", note)


class TestCanvasExtract(unittest.TestCase):
    """_extract_canvas_data: kanonik + /ID + aile-SDE fail-closed."""

    def test_extract_ok(self):
        data = rdt._extract_canvas_data(_canvas_report())
        self.assertEqual(data["tectonic_canonical_sha256"], "c" * 64)
        self.assertEqual(data["tectonic_bin"], "/opt/homebrew/bin/tectonic")

    def test_extract_fail_closed(self):
        no_sde = _canvas_report()
        del no_sde["source_date_epoch"]
        bad = [
            {},                                             # boş rapor
            _canvas_report(verdict="FAIL"),                 # deney düşmüş
            _canvas_report(hash_form="raw (/ID dahil)"),    # kanonik değil
            _canvas_report(id_form="id_absent"),            # /ID nötrlenmemiş
            _canvas_report(tectonic_run1_sha256="d" * 64),  # koşumlar zıt
            _canvas_report(tectonic_run1_sha256="zz"),      # 64-hex değil
            _canvas_report(source_date_epoch="1786924800"), # el yazması SDE'si
            _canvas_report(source_date_epoch="now"),        # sayı değil
            no_sde,                                         # SDE alanı yok
        ]
        for report in bad:
            with self.assertRaises(ValueError, msg=repr(report)):
                rdt._extract_canvas_data(report)

    def test_build_canvas_record_shape(self):
        with tempfile.TemporaryDirectory() as td:
            tex = Path(td) / "incidental_proof_book.tex"
            tex.write_text("% apex\n", encoding="utf-8")
            rec = rdt._build_canvas_record(_canvas_report(), str(tex))
        self.assertEqual(rec["family"], rdt.FAMILY_CANVAS)
        self.assertEqual(rec["gate"], "PASS")
        self.assertEqual(rec["sde"], rdt.CANVAS_SDE)
        self.assertEqual(rec["platform"], sys.platform)
        self.assertNotIn("texlive_canonical_sha256", rec)
        self.assertEqual(rec["tectonic_canonical_sha256"], "c" * 64)
        self.assertEqual(rec["source_sha256"],
                         hashlib.sha256(b"% apex\n").hexdigest())
        self.assertEqual(rdt.hash_keys(rec), ("tectonic_canonical_sha256",))


class TestUpdateCanvasMode(unittest.TestCase):
    """--update --family canvas: apex raporu → canvas satırı; değilse kırmızı."""

    @staticmethod
    def _write_report(td, source):
        p = Path(td) / "book.determinism.txt"
        fields = _canvas_report(source=str(source))
        p.write_text("".join("%s=%s\n" % item for item in fields.items()),
                     encoding="utf-8")
        return str(p)

    def test_canvas_update_appends_apex_row(self):
        with tempfile.TemporaryDirectory() as td:
            report = self._write_report(td, rdt.CANVAS_APEX_TEX)
            trend = os.path.join(td, "trend.jsonl")
            with unittest.mock.patch.object(rdt, "CANVAS_REPORT", report), \
                 unittest.mock.patch.object(rdt, "TREND", trend):
                rc = rdt.main(["--update", "--family", "canvas"])
            self.assertEqual(rc, 0)
            rows = rdt._records(trend)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["family"], "canvas")
        self.assertEqual(row["sde"], rdt.CANVAS_SDE)
        self.assertEqual(row["gate"], "PASS")
        self.assertEqual(row["tectonic_canonical_sha256"], "c" * 64)
        self.assertNotIn("texlive_canonical_sha256", row)
        # Kaynak parmak izi GERÇEK apex .tex'e ait.
        self.assertEqual(
            row["source_sha256"],
            hashlib.sha256(Path(rdt.CANVAS_APEX_TEX).read_bytes()).hexdigest())

    def test_canvas_update_rejects_non_apex_source(self):
        # Levha kaynağını gösteren rapor apex (kitap) satırı değildir —
        # kitap hash'i olmayan ölçüm aileyi temsil edemez: fail-closed.
        plate = Path(rdt.CIKTI) / "canvas" / "incidental_proof_plate02.tex"
        if not plate.exists():
            self.skipTest("levha kaynağı yok")
        with tempfile.TemporaryDirectory() as td:
            report = self._write_report(td, plate)
            trend = os.path.join(td, "trend.jsonl")
            err = io.StringIO()
            with unittest.mock.patch.object(rdt, "CANVAS_REPORT", report), \
                 unittest.mock.patch.object(rdt, "TREND", trend), \
                 contextlib.redirect_stderr(err):
                rc = rdt.main(["--update", "--family", "canvas"])
            self.assertEqual(rc, 1)
            self.assertIn("apex", err.getvalue())
            self.assertFalse(os.path.exists(trend))  # hiç satır yazılmadı

    def test_canvas_update_without_report_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            err = io.StringIO()
            with unittest.mock.patch.object(
                    rdt, "CANVAS_REPORT",
                    os.path.join(td, "yok.determinism.txt")), \
                 contextlib.redirect_stderr(err):
                rc = rdt.main(["--update", "--family", "canvas"])
        self.assertEqual(rc, 1)
        self.assertIn("plate-book-check", err.getvalue())  # yönerge yazılır

    def test_default_family_stays_manuscript(self):
        # --family verilmezse eski davranış birebir aynı (geriye dönük uyum).
        with tempfile.TemporaryDirectory() as td:
            err = io.StringIO()
            with unittest.mock.patch.object(
                    rdt, "REPORT", os.path.join(td, "yok.txt")), \
                 contextlib.redirect_stderr(err):
                rc = rdt.main(["--update"])
        self.assertEqual(rc, 1)
        self.assertIn("texlive_determinism_hook.sh", err.getvalue())


class TestCanvasContractAcrossArtifacts(unittest.TestCase):
    """SDE ve rapor yolu birden çok dosyada aynı olmalı (diller arası)."""

    def test_canvas_epoch_constant_agrees(self):
        # Neden test: tek gerçeklik diller arası türülenemiyor; biri kayarsa
        # başka bir epoch ile üretilen hash trende sızar ve commit'li baytlar
        # yeniden üretilemez (Makefile'ın adlandırdığı risk).
        self.assertEqual(rdt.CANVAS_SDE, 1700000000)
        mk = (ROOT / "docs" / "Makefile.texlive").read_text(encoding="utf-8")
        self.assertIn("PLATE_BOOK_EPOCH ?= 1700000000", mk)
        sh = (CIKTI / "canvas_determinism_test.sh").read_text(encoding="utf-8")
        self.assertIn("SOURCE_DATE_EPOCH:-1700000000", sh)

    def test_canvas_report_path_matches_harness_default(self):
        sh = (CIKTI / "canvas_determinism_test.sh").read_text(encoding="utf-8")
        self.assertIn('canvas_determinism/$(basename "${SRC%.tex}")'
                      '.determinism.txt', sh)
        self.assertTrue(str(rdt.CANVAS_REPORT).endswith(
            "docs/ci_simulate/canvas_determinism/"
            "incidental_proof_book.determinism.txt"))

    def test_apex_source_name_is_stable(self):
        # `source=` değeri bu addan gelir; ad değişirse rapor eşleşmez.
        self.assertTrue(os.path.exists(rdt.CANVAS_APEX_TEX))
        self.assertEqual(os.path.basename(rdt.CANVAS_APEX_TEX),
                         rdt.CANVAS_APEX_STEM + ".tex")


if __name__ == "__main__":
    unittest.main()
