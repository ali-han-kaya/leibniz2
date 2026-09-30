#!/usr/bin/env python3
"""test_record_determinism_trend.py — determinizm trend kaydı davranış kapısı.

record_determinism_trend.py sözleşmelerini OFFLINE sabitler:

  1) Rapor extract: kanıt alanlarından ölçüm çıkarımı; bozuk raporda
     fail-closed ValueError (verdict != PASS, eksik alan, 64-hex olmayan
     hash, rapor-içi koşum çelişkisi, kanıtlanmamış çok-geçiş).
  2) --update: gerçek rapor yoksa fail-closed rc=1 (deney koşulmadan
     kayıt üretilmez); rapor varsa ölçüm eklenir (passes alanı dahil).
  3) --check değişmezleri (trend_invariant): boş trend geçici-FAIL; bayat
     ölçüm FAIL; aynı kaynak+platform+GEÇİŞ MODUNDA hash sapması FAIL
     (uzlaşma ihlali); kaynak/PLATFORM/MOD değişince serbest; platform
     kapsamı (cutoff sonrası darwin+linux) eksikse FAIL; iki platform aynı
     kaynak+hash'i paylaşırsa OK.
  4) jsonl yalnız eklenir; bozuk satırda ValueError.

Tarihler cutoff'tan (2026-09-17) SONRA seçilir ki yalnız hedeflenen
değişmez ihlal edilsin (izole senaryolar). stdlib-only, OFFLINE.
"""
import datetime
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
        "passes": 1,
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

    def test_extract_carries_pass_mode(self):
        # Faz 4: ölçümün kaç geçişle alındığı kayda geçer; çok-geçişte
        # hizalama kanıtı (rerun_left=0 ×2) ZORUNLU.
        report = {
            "tectonic_sha256": "a" * 64,
            "texlive_canonical_run1_sha256": "b" * 64,
            "texlive_canonical_run2_sha256": "b" * 64,
            "passes": "3",
            "texlive_run1_rerun_left": "0",
            "texlive_run2_rerun_left": "0",
            "verdict": "PASS",
        }
        self.assertEqual(rdt._extract_report_data(report)["passes"], 3)
        # passes alanı olmayan eski raporlar tek-geçiş kabul edilir.
        del report["passes"]
        del report["texlive_run1_rerun_left"]
        del report["texlive_run2_rerun_left"]
        self.assertEqual(rdt._extract_report_data(report)["passes"], 1)

    def test_extract_rejects_unproven_multi_pass(self):
        base = {
            "tectonic_sha256": "a" * 64,
            "texlive_canonical_run1_sha256": "b" * 64,
            "texlive_canonical_run2_sha256": "b" * 64,
            "passes": "3",
            "verdict": "PASS",
        }
        # rerun kanıtı yok → kaydedilmez (hizalama iddiası üretilemez).
        with self.assertRaises(ValueError):
            rdt._extract_report_data(dict(base))
        # rerun kaldı → kaydedilmez.
        with self.assertRaises(ValueError):
            rdt._extract_report_data(dict(
                base, texlive_run1_rerun_left="0",
                texlive_run2_rerun_left="2"))
        for bad in ("abc", "0", "-1"):
            with self.assertRaises(ValueError):
                rdt._extract_report_data(dict(base, passes=bad))

    def test_extract_residual_none_falls_back_to_raw(self):
        # Hızlı yol (ham hash'ler baştan eşit) kanonik alanları YAZMAZ;
        # o durumda ham = kanonik (Faz 3 kabul üreticisiyle aynı kural).
        report = {
            "tectonic_sha256": "a" * 64,
            "texlive_run1_sha256": "b" * 64,
            "texlive_run2_sha256": "b" * 64,
            "residual": "none",
            "verdict": "PASS",
        }
        self.assertEqual(rdt._extract_report_data(report)["texlive_canonical_sha256"],
                         "b" * 64)
        # /ID kalıntısı varken kanonik alanlar yoksa kanıt eksiktir → FAIL.
        with self.assertRaises(ValueError):
            rdt._extract_report_data(dict(report, residual="content"))
        # Koşumlar çelişkiliyse fallback de yapılmaz.
        with self.assertRaises(ValueError):
            rdt._extract_report_data(dict(report, texlive_run2_sha256="e" * 64))


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

    def test_update_records_pass_mode_end_to_end(self):
        # Hermetik: sahte rapor + sahte trend; passes alanı jsonl'a yazılır.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "sample.tex"
            source.write_text("\\documentclass{article}\n", encoding="utf-8")
            report = root / "report.txt"
            report.write_text(
                f"source={source}\n"
                f"tectonic_sha256={'a' * 64}\n"
                "passes=3\n"
                "texlive_run1_sha256=" + "b" * 64 + "\n"
                "texlive_run2_sha256=" + "b" * 64 + "\n"
                "texlive_canonical_run1_sha256=" + "b" * 64 + "\n"
                "texlive_canonical_run2_sha256=" + "b" * 64 + "\n"
                "texlive_run1_rerun_left=0\n"
                "texlive_run2_rerun_left=0\n"
                "residual=/ID\nverdict=PASS\n",
                encoding="utf-8")
            orig_report, orig_trend = rdt.REPORT, rdt.TREND
            rdt.REPORT = str(report)
            rdt.TREND = os.path.join(td, "trend.jsonl")
            try:
                self.assertEqual(rdt.main(["--update"]), 0)
                row = rdt._records(rdt.TREND)[0]
            finally:
                rdt.REPORT, rdt.TREND = orig_report, orig_trend
        self.assertEqual(row["passes"], 3)
        self.assertEqual(row["gate"], "PASS")

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

    def test_mode_change_is_a_rebaseline_not_a_violation(self):
        # Faz 4 re-baseline'ı: aynı kaynak+platform ama FARKLI geçiş modu →
        # kanonik farkı BEKLENENdir (çapraz ref/bib çözümü). İhlal sayılmaz,
        # nota yazılır. Aynı mod içindeki sapma yine yakalanır.
        recs = [_rec(platform="darwin", passes=1),
                _rec(platform="linux", passes=1),
                _rec(platform="darwin", passes=3,
                     texlive_canonical_sha256="e" * 64)]
        v = rdt.trend_invariant(recs, now=NOW)
        self.assertEqual(v, "OK")
        self.assertIn("geçiş modu değişti 1 → 3", rdt._mode_note(recs))
        # Aynı modda (3 → 3) sapma yakalanır.
        drift = recs + [_rec(platform="darwin", passes=3,
                             texlive_canonical_sha256="f" * 64)]
        self.assertIn("aynı kaynakta değişti", rdt.trend_invariant(drift, now=NOW))

    def test_mode_note_silent_without_change(self):
        self.assertIsNone(rdt._mode_note([_rec(passes=1)]))
        self.assertIsNone(rdt._mode_note([_rec(passes=3), _rec(passes=3)]))
        # `passes` alanı olmayan eski satırlar 1 kabul edilir → değişim yok.
        self.assertIsNone(rdt._mode_note([_rec(), _rec(passes=1)]))

    def test_concordance_free_cross_platform(self):
        # Aynı kaynak, FARKLI platform, farklı hash → ihlal DEĞİL
        # (CI Debian TeXLive vs lokal Homebrew — R3: ölçmeden varsayma).
        recs = [_rec(platform="darwin"),
                _rec(platform="linux",
                     tectonic_canonical_sha256="d" * 64,
                     texlive_canonical_sha256="e" * 64)]
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
                _rec(source_sha256="f" * 64, platform="linux")]
        v = rdt.trend_invariant(recs, now=NOW)
        # Kaynak değişti → uzlaşma serbest; tarihler cutoff sonrası ve iki
        # platform da mevcut olduğundan kapsam dolu → tamamen OK.
        self.assertNotIn("aynı kaynakta değişti", v)
        self.assertEqual(v, "OK")

    def test_concordance_cross_platform_same_hash_ok(self):
        recs = [_rec(platform="darwin"), _rec(platform="linux")]
        v = rdt.trend_invariant(recs, now=NOW)
        self.assertEqual(v, "OK")

    def test_fresh_two_platform_chain_ok(self):
        recs = [_rec(date="2026-09-20", platform="darwin"),
                _rec(date="2026-09-22", platform="linux")]
        v = rdt.trend_invariant(recs, now=NOW)
        self.assertEqual(v, "OK")


if __name__ == "__main__":
    unittest.main()
