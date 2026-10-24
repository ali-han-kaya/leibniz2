#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_trend_buckets.py — `lib/trend-buckets.ts` saflık ve kova sözleşmesi.

Tasarım: `docs/TREND_CHART_READ_PATH.md` §2 (boş kova atlanmaz, granularity),
§5 (UTC kova anahtarı, sıra, `truncated`), §7 (saflık kapısı), §9 adım 1.

İki katman:

  1. STATİK (her ortamda): modül DB/pg/React/Next importu TAŞIMAZ; kova
     anahtarı `toISOString().slice(0, 10|13)` ile üretilir (yerel saatte
     `slice` yapmak kovayı bir gün geriye kaydırıyordu — tasarım §5'te ölçüm).
  2. DAVRANIŞSAL: modül gerçek `tsx` ile koşulur — boş kova, UTC sınırı
     (23:59 / 00:01), `truncated`, toplama, granularity seçimi ve pencere
     dışı satırlar. node/tsx yoksa vaka SKIP edilir (run-compare deseni);
     kapı bu yüzden statik katmanla her ortamda kırmızıya düşebilir.

Koşum: python3 -m unittest _calisma.CIKTI.test_trend_buckets -v
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
NEXT = REPO / "apps" / "dashboard-next"
LIB = NEXT / "lib" / "trend-buckets.ts"

BANNED = ("prisma", "pg", "react", "next/", "server-only")


def _read(path):
    return path.read_text(encoding="utf-8")


class PurityTest(unittest.TestCase):
    """Modül saf olmalı: import yok, DB/React bağı yok (tasarım §7)."""

    def test_module_exists(self):
        self.assertTrue(LIB.is_file(), "lib/trend-buckets.ts eksik")

    def test_module_has_no_imports_at_all(self):
        src = _read(LIB)
        self.assertEqual(
            re.findall(r"^\s*import\s", src, flags=re.M), [],
            "saf modül import taşımamalı (tip importu dahil)")

    def test_module_does_not_touch_db_frameworks_or_react(self):
        src = _read(LIB)
        for banned in BANNED:
            self.assertNotIn(f'from "{banned}', src,
                             f"trend-buckets saf olmalı ({banned} importu yasak)")
            self.assertNotIn(f"require(\"{banned}", src)

    def test_bucket_key_is_an_utc_iso_slice_not_a_local_date(self):
        # Tasarım §5: yerel saat diliminde kova üretimi bir gün kaydırıyordu.
        # Kanıt iki yönlü: (a) anahtar `toISOString()` diliminden gelir
        # (10 = gün, 13 = saat), (b) yerel-saat getter'ları HİÇ kullanılmaz.
        src = _read(LIB)
        self.assertIn("toISOString()", src)
        self.assertEqual(sorted(set(re.findall(r"\.slice\(0, (\d+)\)", src))),
                         ["10", "13"])
        self.assertIn("setUTCHours(", src)
        self.assertIn("setUTCMinutes(", src)
        for local in ("getFullYear(", "getMonth(", "getDate(",
                      "getHours(", "toLocaleDateString("):
            self.assertNotIn(local, src,
                             f"yerel saat getter'ı kova kayması üretir: {local}")

    def test_public_contract_is_exported(self):
        src = _read(LIB)
        for name in ("bucketSeries", "bucketKey", "chooseGranularity",
                     "ROW_CAP", "HOUR_GRANULARITY_MAX_HOURS"):
            self.assertIn(f"export ", src, "export bulunamadı")
            self.assertRegex(src, r"export (function|const|type) "
                                  r"(?:%s\b)" % re.escape(name))


class BucketBehaviorTest(unittest.TestCase):
    """Gerçek TS koşusu: iddialar yeşil olduğu için değil, doğru olduğu için."""

    NODE = shutil.which("node")
    TSX = NEXT / "node_modules" / ".bin" / "tsx"
    FALLBACK_TSX = REPO / "apps" / "trend-db" / "node_modules" / ".bin" / "tsx"

    def setUp(self):
        tsx = self.TSX if self.TSX.exists() else self.FALLBACK_TSX
        if self.NODE is None or not tsx.exists():
            self.skipTest("node/tsx yok (dashboard-next veya trend-db node_modules)")
        self.tsx = tsx
        self.driver = NEXT / (".trend_buckets_driver_%d.ts" % os.getpid())
        self.addCleanup(self._cleanup)
        self.driver.write_text(
            'import { bucketKey, bucketSeries, chooseGranularity } '
            'from "./lib/trend-buckets";\n'
            "const payload = JSON.parse(process.argv[2]);\n"
            "const rows = payload.rows.map((row: any) => ({ ...row, "
            "ts: new Date(row.ts) }));\n"
            "const series = bucketSeries(rows, payload.options);\n"
            "console.log(JSON.stringify({\n"
            "  series,\n"
            "  keys: {\n"
            "    day: bucketKey(new Date('2026-09-26T23:59:59Z'), 'day'),\n"
            "    hour: bucketKey(new Date('2026-09-26T23:59:59Z'), 'hour'),\n"
            "  },\n"
            "}));\n",
            encoding="utf-8",
        )

    def _cleanup(self):
        try:
            self.driver.unlink()
        except OSError:
            pass

    def _run(self, rows, options):
        payload = json.dumps({"rows": rows, "options": options})
        res = subprocess.run(
            [self.NODE, str(self.tsx), str(self.driver), payload],
            cwd=str(NEXT), capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(res.stdout)

    @staticmethod
    def _row(ts, verdict="PASS", p0=0, p1=0, z3=10):
        return {"ts": ts, "verdict": verdict, "p0": p0, "p1": p1,
                "z3Total": z3}

    def test_empty_bucket_is_emitted_not_skipped(self):
        # 26'sında iki koşum, 27'sinde hiç, 28'inde bir koşum → 3 kova.
        out = self._run(
            [self._row("2026-09-26T09:00:00Z"), self._row("2026-09-26T10:00:00Z"),
             self._row("2026-09-28T09:00:00Z")],
            {"from": "2026-09-26T00:00:00Z", "to": "2026-09-28T23:00:00Z"})
        series = out["series"]
        self.assertEqual([b["bucket"] for b in series["buckets"]],
                         ["2026-09-26", "2026-09-27", "2026-09-28"])
        self.assertEqual([b["runs"] for b in series["buckets"]], [2, 0, 1])
        empty = series["buckets"][1]
        self.assertEqual(
            (empty["pass"], empty["fail"], empty["p0"], empty["p1"],
             empty["z3_total"]), (0, 0, 0, 0, 0),
            "koşusuz gün sıfırlarla VAR olmalı (grafik sıkışmasın)")

    def test_utc_boundary_splits_midnight_runs(self):
        out = self._run(
            [self._row("2026-09-26T23:59:00Z", verdict="FAIL", p0=2),
             self._row("2026-09-27T00:01:00Z", verdict="PASS")],
            {"from": "2026-09-26T12:00:00Z", "to": "2026-09-27T12:00:00Z",
             "granularity": "day"})
        series = out["series"]
        self.assertEqual([b["bucket"] for b in series["buckets"]],
                         ["2026-09-26", "2026-09-27"],
                         "23:59 ile 00:01 aynı kovaya düşmemeli")
        self.assertEqual(series["buckets"][0]["fail"], 1)
        self.assertEqual(series["buckets"][1]["pass"], 1)
        # Anahtar üretimi de UTC: gün ve saat dilimleri tasarımdaki biçimde.
        self.assertEqual(out["keys"], {"day": "2026-09-26",
                                       "hour": "2026-09-26T23"})

    def test_same_run_set_at_hour_granularity_lands_in_hour_buckets(self):
        out = self._run(
            [self._row("2026-09-26T23:59:00Z", verdict="FAIL"),
             self._row("2026-09-27T00:01:00Z")],
            {"from": "2026-09-26T22:00:00Z", "to": "2026-09-27T01:00:00Z"})
        series = out["series"]
        self.assertEqual(series["granularity"], "hour")
        self.assertEqual([b["bucket"] for b in series["buckets"]],
                         ["2026-09-26T22", "2026-09-26T23",
                          "2026-09-27T00", "2026-09-27T01"])

    def test_truncated_only_when_row_cap_was_reached(self):
        rows = [self._row("2026-09-26T09:00:00Z") for _ in range(3)]
        capped = self._run(rows, {"from": "2026-09-26T00:00:00Z",
                                  "to": "2026-09-26T23:00:00Z", "rowCap": 3})
        self.assertIs(capped["series"]["truncated"], True,
                      "satır sayısı rowCap'e DAYANDIYSA pencere kırpılmıştır")
        roomy = self._run(rows, {"from": "2026-09-26T00:00:00Z",
                                 "to": "2026-09-26T23:00:00Z", "rowCap": 4})
        self.assertIs(roomy["series"]["truncated"], False)

    def test_aggregation_counts_and_sums_and_nulls(self):
        out = self._run(
            [self._row("2026-09-26T09:00:00Z", "PASS", p0=0, p1=1, z3=5),
             self._row("2026-09-26T10:00:00Z", "FAIL", p0=2, p1=3, z3=7),
             # verdict yok: runs'a girer, ne PASS ne FAIL sayılır
             {"ts": "2026-09-26T11:00:00Z", "verdict": None,
              "p0": None, "p1": None, "z3Total": None}],
            {"from": "2026-09-26T00:00:00Z", "to": "2026-09-26T23:00:00Z",
             "granularity": "day"})
        bucket = out["series"]["buckets"][0]
        self.assertEqual((bucket["runs"], bucket["pass"], bucket["fail"]), (3, 1, 1))
        self.assertEqual((bucket["p0"], bucket["p1"], bucket["z3_total"]),
                         (2, 4, 12), "null alanlar toplamı bozmamalı")

    def test_granularity_follows_the_48_hour_threshold(self):
        short = self._run([], {"from": "2026-09-26T00:00:00Z",
                               "to": "2026-09-27T23:00:00Z"})
        self.assertEqual(short["series"]["granularity"], "hour", "47 saat → saatlik")
        # Eşik KAPSAYICI: tam 48 saat hâlâ saatlik (tasarım §2 "≤ 48").
        boundary = self._run([], {"from": "2026-09-26T00:00:00Z",
                                  "to": "2026-09-28T00:00:00Z"})
        self.assertEqual(boundary["series"]["granularity"], "hour",
                         "48 saat tam sınır → saatlik")
        long = self._run([], {"from": "2026-09-26T00:00:00Z",
                              "to": "2026-09-28T00:01:00Z"})
        self.assertEqual(long["series"]["granularity"], "day", "48sa+1dk → günlük")
        forced = self._run([], {"from": "2026-09-26T00:00:00Z",
                                "to": "2026-09-26T06:00:00Z",
                                "granularity": "day"})
        self.assertEqual(forced["series"]["granularity"], "day",
                         "açık granularity span eşiğini EZMELİ")

    def test_rows_outside_the_window_are_ignored(self):
        out = self._run(
            [self._row("2026-09-25T23:00:00Z"),
             self._row("2026-09-26T09:00:00Z"),
             self._row("2026-09-27T09:00:00Z")],
            {"from": "2026-09-26T00:00:00Z", "to": "2026-09-26T23:00:00Z",
             "granularity": "day"})
        self.assertEqual([b["runs"] for b in out["series"]["buckets"]], [1],
                         "pencere dışı satırlar seriye sızmamalı")

    def test_series_is_oldest_to_newest(self):
        # Sorgu `orderBy: ts desc` verir; kova üretimi sırayı çevirir.
        out = self._run(
            [self._row("2026-09-28T09:00:00Z"),
             self._row("2026-09-26T09:00:00Z")],
            {"from": "2026-09-26T00:00:00Z", "to": "2026-09-28T23:00:00Z"})
        buckets = [b["bucket"] for b in out["series"]["buckets"]]
        self.assertEqual(buckets, sorted(buckets),
                         "seri eskiden-yeniye olmalı (tasarım §5)")
        self.assertEqual(out["series"]["from"], "2026-09-26T00:00:00.000Z")
        self.assertEqual(out["series"]["to"], "2026-09-28T23:00:00.000Z")


if __name__ == "__main__":
    unittest.main()
