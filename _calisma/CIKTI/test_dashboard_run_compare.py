#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dashboard_run_compare.py — /trend koşum karşılaştırması + süre/bütçe grafiği.

İki katman:

  1. STATİK (her ortamda): sayfa kablolaması, bileşenin erişilebilirlik/token
     kuralları (hex renk yok, `role="img"`, `<title>`/`<desc>`, metin tablosu),
     saf modülün React/Next/DB importu TAŞIMAMASI ve DB okuma katmanında
     karşılaştırmanın AYNI `findMany` satırlarından türetilmesi (ikinci sorgu
     yok).
  2. DAVRANIŞSAL: `lib/run-compare.ts` gerçek `tsx` ile koşulur — medyan,
     delta, eksik alan (`null`, sıfır değil), pencere kırpma ve gerileme
     nedenleri ölçülür. node/tsx yoksa vaka atlanır (TestTrendDbDryRun deseni);
     atlama özet satırında ayrıca görünür.

Koşum: python3 -m unittest _calisma.CIKTI.test_dashboard_run_compare -v
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
APP = NEXT / "app"
COMPONENTS = NEXT / "components"
LIB = NEXT / "lib"

TREND_PAGE = APP / "trend" / "page.tsx"
COMPARE_CARD = COMPONENTS / "RunCompareCard.tsx"
COMPARE_LIB = LIB / "run-compare.ts"
COMPARE_PANEL = COMPONENTS / "RunComparePanel.tsx"
DB_READ = LIB / "trend-db.ts"
FORMAT_LIB = LIB / "format.ts"

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _read(path):
    return path.read_text(encoding="utf-8")


class PageWiringTest(unittest.TestCase):
    def test_trend_page_renders_compare_card_from_the_bundle(self):
        # Veri çekmesi panele taşındı (PanelBoundary altında); sayfa yalnız
        # paneli 20 penceresiyle kurar. Aynı upstream turu cache'ten gelir.
        page = _read(TREND_PAGE)
        self.assertIn("<RunComparePanel limit={20} />", page)
        self.assertIn('title="Son 20 Koşum"', page)
        panel = _read(COMPARE_PANEL)
        self.assertIn("getTrendBundle(limit)", panel)
        self.assertIn("const { compare } = await getTrendBundle(limit);", panel)
        self.assertIn("<RunCompareCard rows={compare} />", panel)

    def test_compare_reads_postgres_through_the_single_query(self):
        """Veri Postgres'ten: `compare` aynı `rows`tan, ikinci sorgu yok."""
        src = _read(DB_READ)
        self.assertEqual(src.count("findMany("), 1,
                         "trend-db.ts tek sorgu kuralı bozuldu")
        self.assertRegex(src, r"const compare: CompareRow\[\] = rows\.map")
        self.assertIn("return { history, refs, compare };", src)


class CompareLibTest(unittest.TestCase):
    def test_lib_is_pure(self):
        src = _read(COMPARE_LIB)
        for banned in ("react", "next/", "prisma", "server-only"):
            self.assertNotIn(
                f'from "{banned}', src,
                "run-compare saf olmalı (React/Next/DB importu yasak)")
        self.assertIn("export const COMPARE_WINDOW = 20;", src)
        self.assertIn("export function runCompare(", src)
        self.assertIn("export function median(", src)
        self.assertIn("export function delta(", src)


class ComponentContractTest(unittest.TestCase):
    def test_chart_is_labelled_with_text_alternative(self):
        src = _read(COMPARE_CARD)
        self.assertIn('role="img"', src)
        self.assertIn("<title id=", src)
        self.assertIn("<desc id=", src)
        self.assertIn("<caption", src)
        self.assertIn("formatTimestamp(", src)
        self.assertIn("formatUsd(", src)

    def test_no_hex_colors_and_repo_tokens_only(self):
        src = _read(COMPARE_CARD)
        match = HEX_COLOR.search(src)
        self.assertIsNone(
            match, "RunCompareCard ham hex renk taşıyor (%s)"
                   % (match.group(0) if match else ""))
        for token in ("stroke-accent", "stroke-ok", "stroke-err"):
            self.assertIn(token, src)

    def test_missing_values_are_visible_not_zero(self):
        src = _read(COMPARE_CARD)
        self.assertIn("süre/bütçe verisi yok", src)
        self.assertIn("EMPTY_VALUE", src)
        self.assertIn("tabular-nums", src)

    def test_dual_axis_legend_is_stated_in_text(self):
        src = _read(COMPARE_CARD)
        self.assertIn("sol eksen", src)
        self.assertIn("sağ eksen", src)


class FormatHelpersTest(unittest.TestCase):
    def test_usd_and_duration_helpers_exist_with_fixed_locale(self):
        src = _read(FORMAT_LIB)
        self.assertIn("export function formatUsd(", src)
        self.assertIn("export function formatDuration(", src)
        self.assertIn("Intl.NumberFormat(TIMESTAMP_LOCALE", src)


class CompareBehaviorTest(unittest.TestCase):
    """Gerçek TS koşusu: hesap iddiaları yeşil olduğu için değil, doğru olduğu için."""

    NODE = shutil.which("node")
    TSX = NEXT / "node_modules" / ".bin" / "tsx"
    FALLBACK_TSX = REPO / "apps" / "trend-db" / "node_modules" / ".bin" / "tsx"

    def setUp(self):
        tsx = self.TSX if self.TSX.exists() else self.FALLBACK_TSX
        if self.NODE is None or not tsx.exists():
            self.skipTest("node/tsx yok (dashboard-next veya trend-db node_modules)")
        self.tsx = tsx
        self.tmp = tempfile.TemporaryDirectory(prefix="run-compare-")
        self.addCleanup(self.tmp.cleanup)
        self.driver = NEXT / (".run_compare_driver_%d.ts" % os.getpid())
        self.addCleanup(self._cleanup)
        self.driver.write_text(
            'import { delta, median, runCompare } from "./lib/run-compare";\n'
            "const rows = JSON.parse(process.argv[2]);\n"
            "console.log(JSON.stringify({\n"
            "  summary: runCompare(rows),\n"
            "  delta5_0: delta(5, 0),\n"
            "  deltaNull: delta(null, 3),\n"
            "  median4: median([3, 1, 2, 4]),\n"
            "  medianEmpty: median([]),\n"
            "}));\n",
            encoding="utf-8",
        )

    def _cleanup(self):
        try:
            self.driver.unlink()
        except OSError:
            pass

    def _run(self, rows):
        res = subprocess.run(
            [self.NODE, str(self.tsx), str(self.driver), json.dumps(rows)],
            cwd=str(NEXT), capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(res.stdout)

    @staticmethod
    def _row(ts, duration=None, budget=None, limit=None, verdict="PASS",
             p0=0, p1=0, z3=10):
        row = {"ts": ts, "verdict": verdict, "p0": p0, "p1": p1,
               "z3_total": z3}
        if duration is not None:
            row["duration_s"] = duration
        if budget is not None:
            row["budget_usd"] = budget
        if limit is not None:
            row["budget_limit"] = limit
        return row

    def test_deltas_median_utilization_and_regression_reasons(self):
        out = self._run([
            self._row("t1", 40, 1.0, 30),
            self._row("t2", 50, 1.0, 30),
            self._row("t3", 60, 1.2, 30, verdict="FAIL", p0=1, p1=2),
        ])
        s = out["summary"]
        self.assertEqual(s["medianDuration"], 50)
        self.assertEqual(s["medianBudget"], 1.0)
        self.assertEqual(s["duration"]["absolute"], 10)
        self.assertEqual(s["duration"]["pct"], 20)
        self.assertEqual(s["duration"]["direction"], "up")
        self.assertEqual(s["budget"]["absolute"], 0.2)
        self.assertEqual(round(s["budgetUtilization"], 2), 4.0)
        self.assertTrue(s["regressed"])
        joined = " | ".join(s["reasons"])
        for needle in ("süre", "bütçe", "P0", "P1", "PASS → FAIL"):
            self.assertIn(needle, joined)

    def test_missing_fields_stay_null_and_do_not_shift_median(self):
        out = self._run([
            self._row("t1", 40, 1.0, 30),
            self._row("t2", 60, 2.0, 30),
            self._row("t3"),  # süre/bütçe yok → null, sıfır DEĞİL
        ])
        s = out["summary"]
        self.assertIsNone(s["latest"]["duration"])
        self.assertIsNone(s["latest"]["budget"])
        self.assertEqual(s["medianDuration"], 50)
        self.assertEqual(s["medianBudget"], 1.5)
        self.assertEqual(s["duration"]["direction"], "unknown")
        self.assertIsNone(s["duration"]["pct"])

    def test_zero_base_does_not_invent_percentage(self):
        out = self._run([self._row("t1", 40, 0, 30)])
        self.assertIsNone(out["delta5_0"]["pct"])
        self.assertEqual(out["delta5_0"]["absolute"], 5)
        self.assertEqual(out["deltaNull"]["direction"], "unknown")

    def test_window_trims_from_the_newest_end(self):
        rows = [self._row("t%d" % i, 40 + i, 1.0, 30) for i in range(21)]
        s = self._run(rows)["summary"]
        self.assertEqual(len(s["points"]), 20)
        self.assertEqual(s["points"][0]["ts"], "t1")   # en eski düştü
        self.assertEqual(s["points"][-1]["ts"], "t20")  # en yeni kaldı

    def test_rows_without_ts_are_dropped(self):
        out = self._run([{"duration_s": 40}, self._row("t2", 40, 1.0, 30)])
        self.assertEqual(len(out["summary"]["points"]), 1)

    def test_median_of_even_and_empty_sets(self):
        out = self._run([])
        self.assertEqual(out["median4"], 2.5)
        self.assertIsNone(out["medianEmpty"])


if __name__ == "__main__":
    unittest.main()
