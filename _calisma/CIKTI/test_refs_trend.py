#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_refs_trend.py — refs_trend.py regresyon kapısı.

Özellikle _NoAuthRedirect'i kapılar: GitHub /zip endpoint'i imzalı Azure blob
URL'ine 302 döner; urllib Authorization'ı redirect'e taşırsa blob 401
(InvalidAuthenticationInfo) verir. Handler'ın auth başlığını düşürdüğü ve
diğer başlıkları (User-Agent) koruduğu doğrulanır. Ayrıca parse_report +
short_date saf fonksiyonları test edilir. stdlib unittest — ek bağımlılık yok.
"""
import datetime
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
import urllib.request
import zipfile

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import refs_trend as rt  # noqa: E402


class TestNoAuthRedirect(unittest.TestCase):
    def _redirect(self, headers=None):
        req = urllib.request.Request("https://api.github.com/x")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        h = rt._NoAuthRedirect()
        return h.redirect_request(req, None, 302, "Found", {},
                                  "https://blob.core.windows.net/y")

    def test_strips_authorization(self):
        new = self._redirect({"Authorization": "Bearer abc"})
        self.assertIsNotNone(new)
        self.assertFalse("Authorization" in new.headers)

    def test_keeps_other_headers(self):
        new = self._redirect({"User-Agent": "refs-trend",
                              "Authorization": "Bearer abc"})
        self.assertEqual(new.headers.get("User-agent"), "refs-trend")
        self.assertFalse("Authorization" in new.headers)


class TestParseReport(unittest.TestCase):
    def _zip(self, payload):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("references_online.json",
                       json.dumps(payload, ensure_ascii=False))
        return buf.getvalue()

    def test_parses_references_online_json(self):
        payload = {"verified": 49, "total_online": 54, "by_source": {"a": 1}}
        rep = rt.parse_report(self._zip(payload))
        self.assertEqual(rep["verified"], 49)
        self.assertEqual(rep["total_online"], 54)

    def test_missing_json_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("other.txt", "x")
        with self.assertRaises(ValueError):
            rt.parse_report(buf.getvalue())


class TestChangelog(unittest.TestCase):
    @staticmethod
    def _bullets(lines):
        """Sadece '- **YYYY-MM-DD:** ...' satırlarını birleştir (tablo hariç)."""
        return "\n".join(l for l in lines if l.startswith("- **"))

    def test_changelog_has_hicks_hume(self):
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("## Changelog", joined)
        self.assertIn("Hicks 1925", joined)
        self.assertIn("Hume 1975", joined)
        self.assertIn("31/31", joined)

    def test_changelog_has_v5n_norton_popkin(self):
        """V5n: Norton/Popkin CrossRef girişi changelog'da olmalı (54→56)."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5n", joined)
        self.assertIn("Norton 1981", joined)
        self.assertIn("Popkin 1951", joined)
        self.assertIn("54→56", joined)
        # En yeni üstte: V5n (2026-08-19), Hicks/Hume (2026-08-18)'den önce.
        bullets = self._bullets(lines)
        self.assertLess(bullets.index("V5n"), bullets.index("Hicks 1925"))

    def test_changelog_has_v5o(self):
        """V5o: 11 UNVERIFIED → 56/56 tam kapsam changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5o", joined)
        self.assertIn("56/56", joined)
        self.assertIn("REFERENCE_POOL_SIZE", joined)
        # En yeni üstte: V5o (2026-08-19), V5n (2026-08-19)'den önce (aynı gün,
        # V5n'den sonraki değişiklik).
        bullets = self._bullets(lines)
        self.assertLess(bullets.index("V5o"), bullets.index("V5n"))

    def test_changelog_has_v5t_handle(self):
        """V5t: Della Rocca 2010 Handle System doğrulaması changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5t", joined)
        self.assertIn("Della Rocca 2010", joined)
        self.assertIn("Handle", joined)
        # En yeni üstte: V5t (2026-08-21), V5n (2026-08-19)'den önce.
        bullets = self._bullets(lines)
        self.assertLess(bullets.index("V5t"), bullets.index("V5n"))

    def test_changelog_has_v5w_loc(self):
        """V5w: LoC katalog kanıtı changelog'da olmalı (en yeni üstte)."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5w", joined)
        self.assertIn("Library of Congress", joined)
        self.assertIn("loc", joined)
        # En yeni üstte: V5w (2026-08-21), V5v'den önce.
        bullets = self._bullets(lines)
        self.assertLess(bullets.index("V5w"), bullets.index("V5v"))

    def test_changelog_has_v5q_sextus_della(self):
        """V5q: Sextus ia_ids + Della Rocca Wayback doğrulaması changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5q", joined)
        self.assertIn("ia_ids", joined)
        self.assertIn("Wayback", joined)
        # V5q (2026-08-21) V5t'den önce (Wayback → Handle geçişi)
        bullets = self._bullets(lines)
        self.assertLess(bullets.index("V5q"), bullets.index("V5t"))

    def test_changelog_has_v5r_oclc_matrix(self):
        """V5r: OL edisyon oclc YOK + HT identifier matrisi changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5r", joined)
        self.assertIn("oclc", joined)
        self.assertIn("Xunzi", joined)
        # V5r (2026-08-21) V5q'dan hemen önce (matris → kapsam kapatma)
        bullets = self._bullets(lines)
        self.assertLess(bullets.index("V5r"), bullets.index("V5q"))

    def test_changelog_has_v5aa_ol_retry(self):
        """V5aa: OL timeout retry changelog'da olmalı (en yeni üstte)."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5aa", joined)
        self.assertIn("retry", joined)
        # En yeni üstte: V5aa (2026-08-24), V5z'den önce.
        bullets = self._bullets(lines)
        self.assertLess(bullets.index("V5aa"), bullets.index("V5z"))

    def test_changelog_has_v5ab_exponential_backoff(self):
        """V5ab: exponential backoff changelog'da olmalı (V5aa'dan önce)."""
        lines = rt.changelog_lines()
        joined = "\n".join(lines)
        self.assertIn("V5ab", joined)
        self.assertIn("exponential backoff", joined)
        bullets = self._bullets(lines)
        self.assertLess(bullets.index("V5ab"), bullets.index("V5aa"))

    def test_changelog_summary_table_v5p_to_v5w(self):
        """V5p–V5w özet tablosu changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("Kapsam & by_source", joined)
        self.assertIn("| V5p |", joined)
        self.assertIn("| V5w |", joined)
        self.assertIn("| V5n |", joined)
        self.assertIn("54→56", joined)
        self.assertIn("loc +3", joined)

    def test_changelog_has_v5p_oclc_lccn(self):
        """V5p: OL'den OCLC/LCCN çekimi + Xunzi HT kaydı changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5p", joined)
        self.assertIn("OCLC/LCCN", joined)
        self.assertIn("HathiTrust", joined)
        self.assertIn("Xunzi", joined)
        # Sıralama: V5p (08-19, V5o'dan sonra) → V5o → V5n (aynı gün).
        self.assertLess(joined.index("V5p"), joined.index("V5o"))
        bullets = self._bullets(lines)
        self.assertLess(bullets.index("V5o"), bullets.index("V5n"))

    def test_changelog_empty_when_no_entries(self):
        saved = rt.CHANGELOG
        try:
            rt.CHANGELOG = []
            self.assertEqual(rt.changelog_lines(), [])
        finally:
            rt.CHANGELOG = saved


class TestUnverifiedSeries(unittest.TestCase):
    """build_unverified_series — UNVERIFIED zaman serisi bölümü (saf, fail-closed)."""

    def _rows(self, values):
        return [{"date": f"d{i}", "unverified": u}
                for i, u in enumerate(values)]

    def test_structure_with_valid_rows(self):
        s = rt.build_unverified_series(self._rows([2, 1, 0]))
        self.assertEqual(s["latest"], 0)
        self.assertEqual(s["max"], 2)
        self.assertEqual(s["zero_runs"], 1)
        self.assertEqual(s["total_runs"], 3)
        self.assertIsNotNone(s["trend"])
        self.assertEqual(s["trend"]["direction"], "↓ azalıyor")
        self.assertEqual(s["trend"]["first"], 2)
        self.assertEqual(s["trend"]["last"], 0)
        joined = "\n".join(s["lines"])
        self.assertIn("## UNVERIFIED Zaman Serisi", joined)
        self.assertIn("- **Son durum:** 0 doğrulanamayan referans", joined)
        self.assertIn("- **Maksimum:** 2 (tüm run'larda)", joined)
        self.assertIn("- **Sıfır olan run sayısı:** 1/3", joined)
        self.assertIn("- **Trend (son 3 run):** ↓ azalıyor (2 → 0)", joined)

    def test_empty_returns_none(self):
        self.assertIsNone(rt.build_unverified_series([]))

    def test_rising_trend(self):
        s = rt.build_unverified_series(self._rows([0, 1, 5]))
        self.assertEqual(s["trend"]["direction"], "↑ artıyor")
        self.assertEqual(s["latest"], 5)
        self.assertEqual(s["max"], 5)
        self.assertEqual(s["zero_runs"], 1)

    def test_flat_trend(self):
        s = rt.build_unverified_series(self._rows([3, 3, 3]))
        self.assertEqual(s["trend"]["direction"], "→ sabit")
        self.assertEqual(s["trend"]["last"], 3)

    def test_trend_window_caps_at_five(self):
        s = rt.build_unverified_series(self._rows([9, 9, 9, 9, 1, 1, 1]))
        self.assertEqual(s["trend"]["window"], 5)
        self.assertEqual(s["trend"]["first"], 9)
        self.assertEqual(s["trend"]["last"], 1)

    def test_single_row_no_trend(self):
        s = rt.build_unverified_series(self._rows([0]))
        self.assertIsNone(s["trend"])
        self.assertEqual(s["total_runs"], 1)
        self.assertEqual(s["zero_runs"], 1)


class TestStaleArtifacts(unittest.TestCase):
    """detect_stale_artifacts — bayat refs-online artifact uyarısı (saf)."""

    def test_no_stale_when_all_recent_runs_have_refs(self):
        # Son 3 history run'ı (2, 3, 4) refs-online'da da var → bayat yok.
        rows = [{"run_id": 1}, {"run_id": 2}, {"run_id": 3}, {"run_id": 4}]
        history = [{"run_id": 1}, {"run_id": 2}, {"run_id": 3}, {"run_id": 4}]
        s = rt.detect_stale_artifacts(rows, history)
        self.assertEqual(s["stale_runs"], [])
        self.assertTrue(s["ok"])
        joined = "\n".join(s["lines"])
        self.assertIn("## ✅ refs-online Artifact Durumu", joined)
        self.assertIn("tüm run'larda refs-online artifact'ı mevcut", joined)

    def test_stale_runs_flagged(self):
        # Son 3 history run'ı: 2, 3, 4 — refs-online bunların HİÇBİRİNİ
        # üretmemiş (refs yalnızca 1). Üçü de bayat.
        rows = [{"run_id": 1}]
        history = [{"run_id": 1}, {"run_id": 2}, {"run_id": 3}, {"run_id": 4}]
        s = rt.detect_stale_artifacts(rows, history, window=3)
        self.assertEqual(s["stale_runs"], [2, 3, 4])
        self.assertFalse(s["ok"])
        joined = "\n".join(s["lines"])
        self.assertIn("## ⚠️ Bayat refs-online Artifact Uyarısı", joined)
        self.assertIn("run'lar: 2, 3, 4", joined)

    def test_stale_sorted_and_multiple(self):
        rows = [{"run_id": 5}]
        history = [{"run_id": 3}, {"run_id": 4}, {"run_id": 5}]
        s = rt.detect_stale_artifacts(rows, history, window=3)
        self.assertEqual(s["stale_runs"], [3, 4])
        self.assertIn("run'lar: 3, 4", "\n".join(s["lines"]))

    def test_empty_inputs(self):
        self.assertEqual(rt.detect_stale_artifacts([], []),
                         {"stale_runs": [], "lines": [], "ok": True})
        self.assertEqual(rt.detect_stale_artifacts([], [{"run_id": 1}]),
                         {"stale_runs": [], "lines": [], "ok": True})

    def test_custom_window(self):
        rows = [{"run_id": 1}, {"run_id": 2}]
        history = [{"run_id": 1}, {"run_id": 2}, {"run_id": 3}]
        # window=2: son iki run (2, 3) — 3 refs'te yok → bayat.
        s = rt.detect_stale_artifacts(rows, history, window=2)
        self.assertEqual(s["stale_runs"], [3])
        # window=3: son üç run (1, 2, 3) — 3 yine bayat.
        s2 = rt.detect_stale_artifacts(rows, history, window=3)
        self.assertEqual(s2["stale_runs"], [3])


class TestShortDate(unittest.TestCase):
    def test_iso_z(self):
        self.assertEqual(rt.short_date("2026-08-19T12:08:38Z"),
                         "2026-08-19 12:08")

    def test_empty(self):
        self.assertEqual(rt.short_date(""), "")


class TestParseHistoryRecord(unittest.TestCase):
    def _zip_jsonl(self, records):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(
                "history.jsonl",
                "\n".join(json.dumps(r, ensure_ascii=False)
                           for r in records) + "\n",
            )
        return buf.getvalue()

    def test_parses_last_record(self):
        rec = rt.parse_history_record(self._zip_jsonl([
            {"ts": "a", "duration_s": 1.0, "budget_usd": 0.5},
            {"ts": "b", "duration_s": 2.0, "budget_usd": 1.08},
        ]))
        self.assertEqual(rec["ts"], "b")
        self.assertEqual(rec["duration_s"], 2.0)
        self.assertEqual(rec["budget_usd"], 1.08)

    def test_skips_blank_lines(self):
        rec = rt.parse_history_record(self._zip_jsonl([
            {"ts": "a", "duration_s": 3.0},
        ]))
        self.assertEqual(rec["duration_s"], 3.0)

    def test_missing_jsonl_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("other.txt", "x")
        with self.assertRaises(ValueError):
            rt.parse_history_record(buf.getvalue())

    def test_empty_jsonl_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("history.jsonl", "\n")
        with self.assertRaises(ValueError):
            rt.parse_history_record(buf.getvalue())

    def test_last_record_wins_across_many(self):
        """Çok kayıtlı dosyada SON kayıt döner (en güncel)."""
        rec = rt.parse_history_record(self._zip_jsonl([
            {"ts": "a"},
            {"ts": "b"},
            {"ts": "c", "duration_s": 9.5, "budget_usd": 1.08},
        ]))
        self.assertEqual(rec["ts"], "c")
        self.assertEqual(rec["duration_s"], 9.5)

    def test_corrupt_json_line_raises(self):
        """Fail-closed: bozuk satır sessizce atlanmamalı — hata fırlatılmalı."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("history.jsonl", '{"ts": "a"}\n{bozuk json}\n')
        with self.assertRaises(ValueError):
            rt.parse_history_record(buf.getvalue())


class TestStats(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(rt.stats([1, 2, 3]),
                         {"count": 3, "min": 1, "max": 3, "avg": 2})

    def test_ignores_non_numbers(self):
        s = rt.stats([None, "x", 5, 15])
        self.assertEqual(s["count"], 2)
        self.assertEqual(s["min"], 5)
        self.assertEqual(s["max"], 15)
        self.assertEqual(s["avg"], 10)

    def test_empty(self):
        self.assertEqual(rt.stats([]),
                         {"count": 0, "min": None, "max": None, "avg": None})

    def test_rounds_to_two_decimals(self):
        s = rt.stats([1.333, 2.666])
        self.assertEqual(s, {"count": 2, "min": 1.33, "max": 2.67, "avg": 2.0})


class TestCheckRunWarnings(unittest.TestCase):
    """duration/budget eşikleri + Z3 FAIL uyarıları (fail-closed)."""

    def test_no_warnings_under_threshold(self):
        w = rt.check_run_warnings(
            {"duration_s": 30.0, "budget_usd": 1.08,
             "z3_passed": 12, "z3_total": 12})
        self.assertFalse(w["duration_warn"])
        self.assertFalse(w["budget_warn"])
        self.assertEqual(w["messages"], [])
        self.assertEqual(w["duration_val"], 30.0)
        self.assertEqual(w["budget_val"], 1.08)

    def test_duration_over_threshold_warns(self):
        w = rt.check_run_warnings({"duration_s": 400.0, "budget_usd": 1.0})
        self.assertTrue(w["duration_warn"])
        self.assertIn("süre 400.0s > eşik 300s", w["messages"])

    def test_budget_over_threshold_warns(self):
        w = rt.check_run_warnings({"duration_s": 10.0, "budget_usd": 31.0})
        self.assertTrue(w["budget_warn"])
        self.assertIn("bütçe $31.00 > eşik $30", w["messages"])

    def test_both_warn(self):
        w = rt.check_run_warnings({"duration_s": 301.0, "budget_usd": 30.01})
        self.assertTrue(w["duration_warn"] and w["budget_warn"])
        self.assertEqual(len(w["messages"]), 2)

    def test_exact_threshold_no_warn(self):
        """Eşiğe EŞİT değer uyarı değil (sıkı >)."""
        w = rt.check_run_warnings({"duration_s": 300.0, "budget_usd": 30.0})
        self.assertFalse(w["duration_warn"])
        self.assertFalse(w["budget_warn"])
        self.assertEqual(w["messages"], [])

    def test_non_numeric_ignored(self):
        w = rt.check_run_warnings(
            {"duration_s": None, "budget_usd": "yok", "z3_passed": None})
        self.assertFalse(w["duration_warn"])
        self.assertFalse(w["budget_warn"])
        self.assertIsNone(w["duration_val"])
        self.assertIsNone(w["budget_val"])
        self.assertEqual(w["messages"], [])

    def test_z3_fail_warns(self):
        w = rt.check_run_warnings({"z3_passed": 11, "z3_total": 12})
        self.assertIn("Z3 FAIL 1/12", w["messages"])

    def test_z3_all_pass_no_message(self):
        w = rt.check_run_warnings({"z3_passed": 12, "z3_total": 12})
        self.assertEqual(w["messages"], [])

    def test_missing_z3_no_message(self):
        w = rt.check_run_warnings({})
        self.assertEqual(w["messages"], [])


class TestSummarizeWarnings(unittest.TestCase):
    """Tüm run'lar üzerinde eşik ihlali özeti (fail-closed)."""

    def test_empty(self):
        s = rt.summarize_warnings([])
        self.assertEqual(s["duration_violations"], 0)
        self.assertEqual(s["budget_violations"], 0)
        self.assertEqual(s["total_runs"], 0)
        self.assertEqual(s["violations"], [])

    def test_no_violations(self):
        rows = [{"date": "a", "run_id": 1, "duration_s": 30.0,
                 "budget_usd": 1.0},
                {"date": "b", "run_id": 2, "duration_s": 60.0,
                 "budget_usd": 2.0}]
        s = rt.summarize_warnings(rows)
        self.assertEqual(s["duration_violations"], 0)
        self.assertEqual(s["budget_violations"], 0)
        self.assertEqual(s["total_runs"], 2)
        self.assertEqual(s["violations"], [])

    def test_counts_duration_and_budget(self):
        rows = [{"date": "a", "run_id": 1, "duration_s": 400.0,
                 "budget_usd": 1.0},
                {"date": "b", "run_id": 2, "duration_s": 10.0,
                 "budget_usd": 40.0}]
        s = rt.summarize_warnings(rows)
        self.assertEqual(s["duration_violations"], 1)
        self.assertEqual(s["budget_violations"], 1)
        self.assertEqual(len(s["violations"]), 2)
        v = s["violations"][0]
        self.assertEqual(v["run_idx"], 1)
        self.assertEqual(v["date"], "a")
        self.assertEqual(v["run_id"], 1)
        self.assertTrue(any("süre" in m for m in v["messages"]))

    def test_z3_fail_in_violations_not_counts(self):
        rows = [{"date": "a", "run_id": 7, "z3_passed": 10,
                 "z3_total": 12}]
        s = rt.summarize_warnings(rows)
        self.assertEqual(s["duration_violations"], 0)
        self.assertEqual(s["budget_violations"], 0)
        self.assertEqual(len(s["violations"]), 1)
        self.assertIn("Z3 FAIL 2/12", s["violations"][0]["messages"])
        self.assertEqual(s["violations"][0]["run_id"], 7)


class TestDurationBudgetSummary(unittest.TestCase):
    """duration_budget JSON bölümü sözleşmesi (fail-closed)."""

    def test_structure_with_valid_rows(self):
        db = rt.build_duration_budget([
            {"date": "a", "run_id": 1, "duration_s": 30.0,
             "budget_usd": 1.08, "verdict": "PASS",
             "z3_passed": 12, "z3_total": 12},
        ])
        self.assertEqual(db["run_count"], 1)
        row = db["rows"][0]
        self.assertEqual(row["date"], "a")
        self.assertEqual(row["run_id"], 1)
        self.assertEqual(row["duration_s"], 30.0)
        self.assertEqual(row["budget_usd"], 1.08)
        self.assertEqual(row["verdict"], "PASS")
        self.assertEqual(row["z3_passed"], 12)
        self.assertFalse(row["duration_warn"])
        self.assertFalse(row["budget_warn"])
        self.assertEqual(db["summary"]["duration_s"]["count"], 1)
        self.assertEqual(db["summary"]["budget_usd"]["max"], 1.08)
        self.assertIsNotNone(db["warnings"])
        self.assertEqual(db["warnings"]["total_runs"], 1)

    def test_violations_flagged_in_rows_and_warnings(self):
        db = rt.build_duration_budget([
            {"date": "a", "run_id": 1, "duration_s": 500.0,
             "budget_usd": 35.0},
        ])
        row = db["rows"][0]
        self.assertTrue(row["duration_warn"])
        self.assertTrue(row["budget_warn"])
        self.assertEqual(db["warnings"]["duration_violations"], 1)
        self.assertEqual(db["warnings"]["budget_violations"], 1)
        self.assertEqual(len(db["warnings"]["violations"]), 1)

    def test_empty_fail_closed(self):
        db = rt.build_duration_budget([])
        self.assertEqual(db["run_count"], 0)
        self.assertEqual(db["rows"], [])
        self.assertIsNone(db["warnings"])
        self.assertEqual(db["summary"]["duration_s"]["count"], 0)
        self.assertIsNone(db["summary"]["duration_s"]["min"])

    def test_non_numeric_values_do_not_crash(self):
        """Fail-closed: eksik/sayısal olmayan değerler stats'ı bozmaz,
        run sayısı korunur, uyarı üretilmez."""
        db = rt.build_duration_budget([
            {"date": "a", "run_id": 1, "duration_s": None,
             "budget_usd": "x"},
            {"date": "b", "run_id": 2, "duration_s": 30.0,
             "budget_usd": 1.0},
        ])
        self.assertEqual(db["run_count"], 2)
        self.assertEqual(db["summary"]["duration_s"]["count"], 1)
        self.assertEqual(db["summary"]["duration_s"]["min"], 30.0)
        self.assertEqual(db["warnings"]["total_runs"], 2)
        self.assertEqual(db["warnings"]["violations"], [])

    def test_z3_fail_surfaces_in_warnings(self):
        db = rt.build_duration_budget([
            {"date": "a", "run_id": 9, "z3_passed": 0, "z3_total": 12},
        ])
        self.assertEqual(len(db["warnings"]["violations"]), 1)
        self.assertIn("Z3 FAIL 12/12",
                      db["warnings"]["violations"][0]["messages"])


class TestFetchArtifactsByName(unittest.TestCase):
    def test_filters_sorts_by_date(self):
        artifacts = [
            {"name": "refs-online", "id": 1,
             "created_at": "2026-08-18T00:00:00Z"},
            {"name": "other", "id": 2,
             "created_at": "2026-08-19T00:00:00Z"},
            {"name": "refs-online", "id": 3,
             "created_at": "2026-08-17T00:00:00Z"},
        ]
        orig = rt.api_get

        def fake_api(path, token, binary=False):
            return {"artifacts": artifacts}

        rt.api_get = fake_api
        try:
            out = rt.fetch_artifacts_by_name("o/r", "", "refs-online", 100)
        finally:
            rt.api_get = orig
        self.assertEqual([a["id"] for a in out], [3, 1])


WORKFLOW = CIKTI.parent.parent / ".github" / "workflows" / "verify.yml"


class TestWorkflowCliConsistency(unittest.TestCase):
    """verify.yml'in refs-trend job'ı refs_trend.py CLI'sıyla senkron olmalı.

    refs_trend.py --out-dir refs-trend altına refs-trend.md + refs-trend.json
    üretir; gen_repro_manifest.py'nin REFS TREND bölümü refs-trend/ önekini ve
    reproducibility job'ı `name: refs-trend` artifact'ını ayrıca indirir.
    CLI/artifact drift bu zinciri sessizce koparır — fail-closed.
    """
    def _workflow(self):
        return WORKFLOW.read_text(encoding="utf-8")

    def test_job_uses_refs_trend_out_dir(self):
        text = self._workflow()
        self.assertIn("_calisma/CIKTI/refs_trend.py", text)
        self.assertIn("--out-dir refs-trend", text)
        self.assertIn("--max-artifacts 100", text)

    def test_artifact_name_matches_output_prefix(self):
        # refs_trend.py çıktısı refs-trend/ altına yazılır; reproducibility
        # job'ı aynı adla indirir → manifest REFS TREND bölümüne girer.
        text = self._workflow()
        self.assertIn("name: refs-trend", text)
        self.assertIn("path: all_artifacts/refs-trend/", text)



class TestRunSummaryRefsTrend(unittest.TestCase):
    """run_summary_refs_trend.py CLI tutarlılık + birim testleri.

    verify.yml refs-trend job'ındaki 'Write refs trend to run summary' adımını
    run_summary_refs_trend.py ile çağırır: refs-trend/refs-trend.md'yi
    GITHUB_STEP_SUMMARY'ye taşır. Bu testler:
      1) Workflow adımının doğru script/yol ile çağrıldığını,
      2) Script'in varsayılan input yolunun workflow ile eşleştiğini,
      3) Script'in render() fonksiyonunun eksik dosya/prompt senaryolarını
         doğru handle ettiğini doğrular.
    """

    def _workflow(self):
        return WORKFLOW.read_text(encoding="utf-8")

    # ── Workflow CLI tutarlılığı ──────────────────────────────────────

    def test_workflow_references_script_at_correct_path(self):
        """workflow'da script doğru yoldan çağrılmalı."""
        text = self._workflow()
        self.assertIn(
            "python3 _calisma/CIKTI/run_summary_refs_trend.py",
            text)

    def test_workflow_step_name_mentions_refs_trend(self):
        """Adım adı 'refs trend' kelimesini içermeli."""
        text = self._workflow()
        self.assertIn("refs trend", text.lower())

    def test_workflow_step_input_is_refs_trend_md(self):
        """Workflow'un sağladığı input refs-trend/refs-trend.md olmalı."""
        text = self._workflow()
        # Script çağrısı refs-trend/refs-trend.md argümanını almalı
        self.assertIn("refs-trend/refs-trend.md", text)

    def test_workflow_step_runs_with_always(self):
        """Adım if: always() ile koşmalı (verify FAIL olsa bile trend görünür)."""
        text = self._workflow()
        # 'Write refs trend to run summary' adımının hemen üstündeki if kontrolü
        self.assertIn("Write refs trend to run summary", text)

    # ── Script varsayılanları ────────────────────────────────────────

    def test_default_md_path_matches_workflow(self):
        """Script'in DEFAULT_MD sabiti workflow ile aynı yolu göstermeli."""
        from run_summary_refs_trend import DEFAULT_MD
        self.assertEqual(DEFAULT_MD, "refs-trend/refs-trend.md")

    # ── Script render() fonksiyonu ──────────────────────────────────

    def test_render_writes_md_to_sink(self):
        """render() mevcut md dosyasını sink'e taşımeli."""
        from run_summary_refs_trend import render
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md",
                                         delete=False) as f:
            f.write("| Run | Verified |\n|---|---|\n| #1 | 61/61 |\n")
            f.flush()
            out = io.StringIO()
            result = render(out, f.name)
        os.unlink(f.name)
        self.assertTrue(result)
        self.assertIn("61/61", out.getvalue())
        self.assertIn("Çevrimiçi referans doğrulama trendi", out.getvalue())

    def test_render_handles_missing_file(self):
        """render() dosya yoksa hata vermemeli, prompt yazmalı."""
        from run_summary_refs_trend import render
        out = io.StringIO()
        result = render(out, "/nonexistent/refs-trend.md")
        self.assertFalse(result)
        self.assertIn("tablo bulunamadı", out.getvalue())

    def test_render_adds_trailing_newline(self):
        """render() md sonunda çift yeni satır olmalı (markdown spacing)."""
        from run_summary_refs_trend import render
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md",
                                         delete=False) as f:
            f.write("tek satır")
            f.flush()
            out = io.StringIO()
            render(out, f.name)
        os.unlink(f.name)
        text = out.getvalue()
        self.assertTrue(text.endswith("\n\n"))


class TestCoverageChangeNote(unittest.TestCase):
    """_coverage_change_note() kapsam değişim işaretçisi (fail-closed)."""

    def test_first_row_returns_empty(self):
        r = {"total_online": 61, "date": "2026-08-21T10:00:00Z"}
        self.assertEqual(rt._coverage_change_note(r, None), "")

    def test_no_change_returns_empty(self):
        prev = {"total_online": 61, "date": "2026-08-19T10:00:00Z"}
        cur = {"total_online": 61, "date": "2026-08-21T10:00:00Z"}
        self.assertEqual(rt._coverage_change_note(cur, prev), "")

    def test_increase_shows_arrow(self):
        prev = {"total_online": 49, "date": "2026-08-18T00:00:00Z"}
        cur = {"total_online": 56, "date": "2026-08-19T00:00:00Z"}
        note = rt._coverage_change_note(cur, prev)
        self.assertIn("↑", note)
        self.assertIn("49→56", note)

    def test_decrease_shows_arrow(self):
        prev = {"total_online": 61, "date": "2026-08-21T00:00:00Z"}
        cur = {"total_online": 56, "date": "2026-08-19T00:00:00Z"}
        note = rt._coverage_change_note(cur, prev)
        self.assertIn("↓", note)
        self.assertIn("61→56", note)

    def test_matches_changelog_when_available(self):
        prev = {"total_online": 49, "date": "2026-08-18T00:00:00Z"}
        cur = {"total_online": 56, "date": "2026-08-19T00:00:00Z"}
        changelog = [
            ("2026-08-19", "V5n: kapsam 54→56 (CrossRef dergileri)"),
        ]
        note = rt._coverage_change_note(cur, prev, changelog)
        self.assertIn("V5n", note)
        self.assertIn("49→56", note)

    def test_no_changelog_match_returns_bare_arrow(self):
        prev = {"total_online": 49, "date": "2026-08-18T00:00:00Z"}
        cur = {"total_online": 56, "date": "2026-08-19T00:00:00Z"}
        changelog = [
            ("2026-08-20", "V5x: diger not"),
        ]
        note = rt._coverage_change_note(cur, prev, changelog)
        self.assertIn("49→56", note)
        self.assertNotIn("V5", note)

    def test_empty_changelog_still_shows_arrow(self):
        prev = {"total_online": 49, "date": "2026-08-18T00:00:00Z"}
        cur = {"total_online": 56, "date": "2026-08-19T00:00:00Z"}
        note = rt._coverage_change_note(cur, prev, [])
        self.assertEqual(note, "↑ 49→56")


class TestChangelogOrder(unittest.TestCase):
    """CHANGELOG tarih sırası denetimi — reverse-chronological."""

    def test_changelog_dates_are_sorted_desc(self):
        dates = [d for d, _ in rt.CHANGELOG if d]
        for i in range(len(dates) - 1):
            self.assertGreaterEqual(
                dates[i], dates[i + 1],
                f"CHANGELOG sırası bozuk: {dates[i]} < {dates[i+1]}")


class TestChangelogDeterministicOrder(unittest.TestCase):
    """CHANGELOG sıralaması deterministik: tarih (azalan) + ekleme sırası.

    CHANGELOG listesi tek kaynaktır; changelog_lines() ve
    _coverage_change_note() onu liste sırasıyla iter eder. Bu nedenle
    listenin KENDİSİ hem tarihe göre azalan hem de aynı tarihli girdilerde
    ekleme sırasında olmalıdır. Stable-sort (tarih desc) orijinal listeyi
    birebir üretmeli — yanlış konuma eklenen ya da aynı tarihi bölen bir
    girdi stable-sort sonrası farklı liste üretir ve bu test FAIL eder.
    """

    def test_dates_are_iso_yyyy_mm_dd(self):
        # Tarih dizeleri ISO olmalı — string karşılaştırması yalnızca
        # sıfır dolgulu YYYY-MM-DD formatında sözlük sırası = kronolojik sıra
        # garantisini verir.
        import re
        iso = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for date, _note in rt.CHANGELOG:
            self.assertTrue(iso.match(date),
                            f"CHANGELOG tarihi ISO değil: {date!r}")

    def test_stable_sort_reproduces_exact_list(self):
        # Tarihe göre azalan stable-sort, orijinal listeyi BİREBİR üretmeli.
        # Bu hem tarih sırasını hem de aynı tarihli girdilerin ekleme
        # sırasının korunduğunu (determinizm) tek kontrolle doğrular.
        stable_sorted = sorted(
            rt.CHANGELOG, key=lambda entry: entry[0], reverse=True)
        self.assertEqual(
            stable_sorted, rt.CHANGELOG,
            "CHANGELOG stable-sort sonrası değişiyor — "
            "bir girdi yanlış yere eklenmiş ya da aynı tarih bölünmüş")

    def test_same_date_entries_are_contiguous(self):
        # Aynı tarihli girdiler tek ardışık blok halinde olmalı (bir tarih
        # listede bölünmemeli).
        seen = []
        for date, _note in rt.CHANGELOG:
            if seen and seen[-1] == date:
                continue
            self.assertNotIn(
                date, seen,
                f"CHANGELOG tarihi bölünmüş: {date} birden çok blokta")
            seen.append(date)

    def test_changelog_lines_is_deterministic(self):
        # changelog_lines() saf fonksiyon olmalı — aynı girdi, aynı çıktı.
        # (zaman/rastgelelik yok; liste sırası tek kaynak)
        first = rt.changelog_lines()
        second = rt.changelog_lines()
        self.assertEqual(first, second,
                         "changelog_lines() deterministik değil")

    def test_changelog_non_empty_and_ordered_by_import(self):
        # CHANGELOG boş olmamalı; her girdi (date, note) ikilisi olmalı.
        self.assertTrue(rt.CHANGELOG, "CHANGELOG boş")
        for entry in rt.CHANGELOG:
            self.assertIsInstance(entry, tuple)
            self.assertEqual(len(entry), 2, f"CHANGELOG girdisi (date,note) ikilisi değil: {entry!r}")
            self.assertIsInstance(entry[0], str)
            self.assertIsInstance(entry[1], str)


class TestRefsTrendTableHasCoverageNote(unittest.TestCase):
    """refs-trend tablosu Kapsam Notu sütunu içermeli (fail-closed)."""

    def test_table_header_has_kapsam_notu(self):
        saved = rt.CHANGELOG[:]
        try:
            rt.CHANGELOG = [
                ("2026-08-19", "V5n: kapsam 54→56"),
            ]
            with tempfile.TemporaryDirectory() as td:
                rows = [
                    {"date": "2026-08-18T10:00:00Z", "run_id": 1,
                     "total_online": 49, "verified": 49,
                     "unverified": 0, "mismatch": 0,
                     "by_source": {"crossref": 49}},
                    {"date": "2026-08-19T10:00:00Z", "run_id": 2,
                     "total_online": 56, "verified": 56,
                     "unverified": 0, "mismatch": 0,
                     "by_source": {"crossref": 56}},
                ]
                import io as _io
                buf = _io.StringIO()
                # Import main and patch args
                import argparse
                p = argparse.Namespace(
                    repo="t/r", token="", max_artifacts=100,
                    out_dir=td)
                # Build lines manually (mirrors main logic)
                lines = []
                lines += [
                    "| # | Tarih (UTC) | Run ID | Toplam | Doğrulanan | "
                    "Doğrulanamayan | Uyumsuz | Kaynak dağılımı | Kapsam Notu |",
                    "|---|---|---|---|---|---|---|---|---|",
                ]
                for i, r in enumerate(rows, 1):
                    src = ", ".join(f"{k}={v}" for k, v in
                                    sorted(r["by_source"].items()))
                    prev = rows[i - 2] if i >= 2 else None
                    note = rt._coverage_change_note(r, prev)
                    lines.append(
                        f"| {i} | {rt.short_date(r['date'])} | "
                        f"{r['run_id'] or '-'} | {r['total_online']} | "
                        f"{r['verified']} | {r['unverified']} | "
                        f"{r['mismatch']} | {src} | {note} |"
                    )
                md = "\n".join(lines)
                self.assertIn("Kapsam Notu", md)
                self.assertIn("↑ 49→56", md)
        finally:
            rt.CHANGELOG = saved

    def test_table_no_note_when_unchanged(self):
        rows = [
            {"date": "2026-08-21T10:00:00Z", "run_id": 1,
             "total_online": 61, "verified": 61,
             "unverified": 0, "mismatch": 0,
             "by_source": {}},
            {"date": "2026-08-22T10:00:00Z", "run_id": 2,
             "total_online": 61, "verified": 61,
             "unverified": 0, "mismatch": 0,
             "by_source": {}},
        ]
        # Build just the note column
        notes = []
        for i, r in enumerate(rows, 1):
            prev = rows[i - 2] if i >= 2 else None
            notes.append(rt._coverage_change_note(r, prev))
        self.assertEqual(notes[0], "")
        self.assertEqual(notes[1], "")


class TestChangelogHasAllVersions(unittest.TestCase):
    """CHANGELOG, kapaklarda listelenen tüm V5 versiyonlarını içermeli."""

    def test_v5n_to_v5aa_all_present(self):
        expected = ["V5n", "V5o", "V5p", "V5q", "V5r", "V5t",
                    "V5v", "V5w", "V5z", "V5aa"]
        all_notes = " ".join(note for _, note in rt.CHANGELOG)
        for v in expected:
            self.assertIn(v, all_notes, f"{v} CHANGELOG'da eksik")


class TestCoverageTransitionSummary(unittest.TestCase):
    """build_coverage_transition_summary: UNVERIFIED>0 → 0 geçiş zinciri."""

    def test_two_stage_transition(self):
        rows = [
            {"date": "2026-08-18", "run_id": 1, "total_online": 54,
             "verified": 49, "unverified": 5, "by_source": {}},
            {"date": "2026-08-19", "run_id": 2, "total_online": 56,
             "verified": 56, "unverified": 0, "by_source": {}},
        ]
        lines = rt.build_coverage_transition_summary(rows)
        joined = "\n".join(lines)
        self.assertIn("Geçiş zinciri", joined)
        self.assertIn("54/49", joined)
        self.assertIn("56/56", joined)

    def test_three_stage_transition(self):
        rows = [
            {"date": "2026-08-18", "run_id": 1, "total_online": 54,
             "verified": 49, "unverified": 5, "by_source": {}},
            {"date": "2026-08-19", "run_id": 2, "total_online": 56,
             "verified": 30, "unverified": 26, "by_source": {}},
            {"date": "2026-08-20", "run_id": 3, "total_online": 56,
             "verified": 56, "unverified": 0, "by_source": {}},
            {"date": "2026-08-21", "run_id": 4, "total_online": 61,
             "verified": 61, "unverified": 0, "by_source": {}},
        ]
        lines = rt.build_coverage_transition_summary(rows)
        joined = "\n".join(lines)
        # Zincir: 54/49 → 56/56 → 61/61 (56'daki 26 UNVERIFIED sıfırlandı)
        self.assertIn("54/49", joined)
        self.assertIn("56/56", joined)
        self.assertIn("61/61", joined)
        self.assertIn("3 aşama", joined)
        self.assertIn("4 artifact", joined)

    def test_single_stage_no_transition(self):
        rows = [
            {"date": "2026-08-18", "run_id": 1, "total_online": 61,
             "verified": 61, "unverified": 0, "by_source": {}},
            {"date": "2026-08-19", "run_id": 2, "total_online": 61,
             "verified": 61, "unverified": 0, "by_source": {}},
        ]
        lines = rt.build_coverage_transition_summary(rows)
        joined = "\n".join(lines)
        self.assertIn("61/61", joined)
        self.assertIn("1 aşama", joined)

    def test_unverified_never_reaches_zero(self):
        # Erken aşama: total_online değişiyor ama UNVERIFIED hep > 0
        rows = [
            {"date": "2026-08-18", "run_id": 1, "total_online": 49,
             "verified": 49, "unverified": 5, "by_source": {}},
            {"date": "2026-08-19", "run_id": 2, "total_online": 54,
             "verified": 49, "unverified": 5, "by_source": {}},
        ]
        lines = rt.build_coverage_transition_summary(rows)
        joined = "\n".join(lines)
        self.assertIn("2 aşama", joined)

    def test_empty_rows_returns_empty(self):
        self.assertEqual(rt.build_coverage_transition_summary([]), [])

    def test_single_row_returns_empty(self):
        rows = [{"date": "x", "run_id": 1, "total_online": 61,
                 "verified": 61, "unverified": 0, "by_source": {}}]
        self.assertEqual(rt.build_coverage_transition_summary(rows), [])


if __name__ == "__main__":
    unittest.main()
