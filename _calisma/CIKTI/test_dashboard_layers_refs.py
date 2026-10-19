#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dashboard_layers_refs.py — /layers sayfası + refs trend grafiği
STATİK sözleşmeleri.

Kapsam (tarayıcısız; her ortamda koşar):
  1. Rotalar var ve veri kapılarını kullanıyor (`getLayers`, `getTrendBundle`).
  2. `LAYER_ORDER` K0..K21'i TAM ve TEK kez kapsıyor — eksik katman sessizce
     kaybolmaz, tabloya bir daha "K21" yazılmasına da gerek kalmaz.
  3. Bilinmeyen durum `UNKNOWN`a düşer (yeşile boyanmaz) — kapalı küme.
  4. Grafik erişilebilir: `role="img"`, `<title>`/`<desc>` ve altında metin
     alternatifi tablo.
  5. Grafik/ızgara renkleri repo token'larıdır: kaynakta hex renk YOK
     (preview.html'in ham `#3fb950` değerleri buraya taşınmaz).
  6. `/trend` hâlâ `limit={20}` literalini taşır (pencere sözleşmesi) ve refs
     yarımı AYNI tel yanıtından gelir: `getTrend` dönüş tipi `{history}` olarak
     dar kalır, `getTrendBundle` geniş kapıdır (refs + compare; tip testi
     sözleşmesi `getTrend` üzerinde dondurulmuş).

Koşum: python3 -m unittest _calisma.CIKTI.test_dashboard_layers_refs -v
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

LAYERS_PAGE = APP / "layers" / "page.tsx"
TREND_PAGE = APP / "trend" / "page.tsx"
LAYOUT = APP / "layout.tsx"
LAYERS_LIB = LIB / "layers.ts"
REFS_LIB = LIB / "refs-trend.ts"
PREVIEW_LIB = LIB / "preview.ts"
CHART = COMPONENTS / "RefsTrendChart.tsx"
GRID = COMPONENTS / "LayerStatusGrid.tsx"
COMPARE_PANEL = COMPONENTS / "RunComparePanel.tsx"
REFS_PANEL = COMPONENTS / "RefsTrendPanel.tsx"
RUNS_DATA = COMPONENTS / "RunsTableData.tsx"
DB_READ = LIB / "trend-db.ts"
PANEL_STYLE = COMPONENTS / "panel-style.ts"

EXPECTED_LAYERS = [f"K{i}" for i in range(22)]
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _read(path):
    return path.read_text(encoding="utf-8")


def _limits_in(text):
    return [int(n) for n in re.findall(r"limit=\{(\d+)\}", text)]


class RouteAndWiringTest(unittest.TestCase):
    """1. Yeni yüzeyler doğru veri kapılarına bağlı."""

    def test_layer_page_exists_and_uses_the_layers_gate(self):
        self.assertTrue(LAYERS_PAGE.is_file(), "/layers/page.tsx yok")
        src = _read(LAYERS_PAGE)
        self.assertIn("getLayers(", src)
        self.assertIn("normalizeLayers(", src)
        self.assertIn("<LayerStatusGrid", src)

    def test_layer_page_distinguishes_missing_data_from_zero_layers(self):
        """Veri yok ile \"0 katman\" aynı ekran olmamalı (fail-closed)."""
        src = _read(LAYERS_PAGE)
        self.assertIn("result.ok", src)
        self.assertIn("katman verisi yok", src)

    def test_trend_page_keeps_the_twenty_row_window_literal(self):
        # Sayfa artık veri çekmez; her panel kendi server component'inde
        # `limit` alır. Pencere üç yerde de 20 olmalı (kırpma sessizce
        # değişirse grafik/tablo farklı pencereler gösterir).
        limits = _limits_in(_read(TREND_PAGE))
        self.assertEqual(len(limits), 3)
        self.assertEqual(set(limits), {20})
        self.assertIn('title="Son 20 Koşum"', _read(TREND_PAGE))

    def test_each_trend_panel_fetches_inside_its_own_boundary(self):
        "Panel başına veri çekme: sayfa await etseydi sınır kurtaramazdı."
        page = _read(TREND_PAGE)
        self.assertEqual(page.count("<PanelBoundary"), 3)
        for component in ("RunsTableData", "RunComparePanel", "RefsTrendPanel"):
            self.assertIn("<%s" % component, page)
        compare = _read(COMPARE_PANEL)
        self.assertIn("getTrendBundle(limit)", compare)
        self.assertIn("<RunCompareCard rows={compare} />", compare)
        refs = _read(REFS_PANEL)
        self.assertIn("getTrendBundle(limit)", refs)
        self.assertIn("<RefsTrendChart", refs)
        table = _read(RUNS_DATA)
        self.assertIn("getTrend(limit)", table)

    def test_refs_and_table_share_one_upstream_turn(self):
        """`getTrend` dar dönüş tipini korur; bundle ayrı kapıdır."""
        src = _read(PREVIEW_LIB)
        self.assertRegex(src, r"export const getTrendBundle = cache\(")
        self.assertIn("history: TrendRow[];", src)
        self.assertIn("refs: RefsRow[];", src)
        self.assertIn("compare: CompareRow[];", src, "koşum karşılaştırması "
                      "aynı tel yanıtından beslenmeli")
        self.assertRegex(src, r"export const getTrend = cache\(")
        # getTrend gövdesi yalnız `history` döndürür (tip testi dondurmuş).
        self.assertRegex(src, r"const \{ history \} = await getTrendBundle")
        self.assertIn("return { history };", src)

    def test_nav_links_to_layers_with_next_link(self):
        src = _read(LAYOUT)
        self.assertIn('from "next/link"', src)
        self.assertRegex(src, r'<Link[^>]*href="/layers"')
        self.assertNotRegex(src, r'<a\s[^>]*href="/layers"')


class LayersDbSourceTest(unittest.TestCase):
    """Katman fotoğrafı Postgres'ten: `trend_runs.layers` + `findings`."""

    def test_db_gateway_reads_the_newest_row_snapshot(self):
        src = _read(DB_READ)
        start = src.index("export const getLayersFromDb")
        block = src[start:start + 2000]
        self.assertIn("findFirst(", block,
                      "katman fotoğrafı tek satır (en yeni koşum) olmalı")
        self.assertIn('orderBy: { ts: "desc" }', block)
        self.assertIn("layers: true", block)
        self.assertIn("findings: true", block)
        # `layers` boşsa sıfır katman uydurulmaz.
        self.assertIn("ok: false", block)
        self.assertIn("katman fotoğrafı yok", block)

    def test_facade_routes_the_layer_gate_by_source(self):
        src = _read(PREVIEW_LIB)
        start = src.index("export const getLayers = cache(")
        block = src[start:start + 1600]
        self.assertIn("trendSource()", block)
        self.assertIn('source === "db"', block)
        self.assertIn("getLayersFromDb", block,
                      "DB kaynağında katmanlar preview_server'dan DEĞİL, "
                      "trend_runs'tan okunmalı")

    def test_layer_page_shows_finding_details_and_source(self):
        src = _read(LAYERS_PAGE)
        self.assertIn("normalizeFindings(", src)
        self.assertIn("P0/P1 Bulgu Ayrıntıları", src)
        self.assertIn('result.source === "db"', src)
        self.assertIn("Postgres arşivi", src)
        self.assertIn("formatTimestamp(", src)

    def test_priority_badge_is_a_closed_variant_table(self):
        src = _read(PANEL_STYLE)
        block = src[src.index("export const findingBadge"):
                    src.index("// ── kart ↔ tablo armonisi")]
        for priority in ("P0", "P1", "UNKNOWN"):
            self.assertIn(priority, block)
        # P1 uyarı, P0 hata tonu — ikisi aynı renge düşmemeli.
        self.assertRegex(block, r"P0:[^\n]*text-err")
        self.assertRegex(block, r"P1:[^\n]*text-warn")


class FindingsBehaviorTest(unittest.TestCase):
    """Gerçek TS koşusu: bulgu normalizasyonu ve sıralaması."""

    NODE = shutil.which("node")
    TSX = NEXT / "node_modules" / ".bin" / "tsx"
    FALLBACK_TSX = REPO / "apps" / "trend-db" / "node_modules" / ".bin" / "tsx"

    def setUp(self):
        tsx = self.TSX if self.TSX.exists() else self.FALLBACK_TSX
        if self.NODE is None or not tsx.exists():
            self.skipTest("node/tsx yok (dashboard-next veya trend-db node_modules)")
        self.tsx = tsx
        self.driver = NEXT / (".layers_findings_driver_%d.ts" % os.getpid())
        self.addCleanup(self._cleanup)
        self.driver.write_text(
            'import { normalizeFindings } from "./lib/layers";\n'
            "const rows = JSON.parse(process.argv[2]);\n"
            "console.log(JSON.stringify(normalizeFindings(rows)));\n",
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

    def test_p0_sorts_before_p1_and_fields_are_kept(self):
        out = self._run([
            {"id": "K18", "priority": "P1", "check": "Daemon",
             "issue": "HTTP smoke başarısız", "evidence": "exit 1"},
            {"id": "K8", "priority": "P0", "check": "Z3",
             "issue": "z3-solver yok", "evidence": ""},
        ])
        self.assertEqual([row["id"] for row in out], ["K8", "K18"])
        self.assertEqual(out[0]["priority"], "P0")
        self.assertEqual(out[0]["check"], "Z3")
        self.assertEqual(out[0]["evidence"], "")
        self.assertEqual(out[1]["evidence"], "exit 1")

    def test_unknown_priority_stays_neutral_and_junk_is_dropped(self):
        out = self._run([
            {"id": "X", "priority": "P7", "issue": "bilinmeyen"},
            None,
            "metin",
            {"priority": "P0"},
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["priority"], "UNKNOWN")
        self.assertEqual(out[0]["id"], "X")

    def test_missing_issue_falls_back_without_inventing_text(self):
        out = self._run([{"id": "K1", "priority": "P0"}])
        self.assertEqual(out[0]["issue"], "—")
        self.assertEqual(out[0]["check"], "K1")


class LayerOrderTest(unittest.TestCase):
    """2. Katman sırası K0..K21 — eksiksiz ve tekrarsız."""

    def test_layer_order_covers_every_k_layer_exactly_once(self):
        src = _read(LAYERS_LIB)
        block = re.search(
            r"export const LAYER_ORDER = \[(.*?)\] as const;",
            src,
            re.S,
        )
        self.assertIsNotNone(block, "LAYER_ORDER bloğu bulunamadı")
        found = re.findall(r'"(K\d+)"', block.group(1))
        self.assertEqual(found, EXPECTED_LAYERS)

    def test_layer_order_is_the_single_order_source(self):
        """Normalizasyon sıralamayı kendi içinde yeniden yazmamalı."""
        src = _read(LAYERS_LIB)
        self.assertIn("LAYER_ORDER.filter", src)


class LayerStateTest(unittest.TestCase):
    """3. Durum kümesi KAPALI; tanınmayan değer yeşile düşmez."""

    def test_state_union_is_closed(self):
        src = _read(LAYERS_LIB)
        self.assertIn(
            'export type LayerState = "PASS" | "FAIL" | "SKIP" | "UNKNOWN";',
            src,
        )

    def test_unknown_is_the_fallback(self):
        src = _read(LAYERS_LIB)
        self.assertRegex(
            src,
            r'if \(value === "PASS" \|\| value === "FAIL" \|\| value === "SKIP"\)'
            r'\s*return value;\s*return "UNKNOWN";',
        )

    def test_grid_maps_unknown_to_neutral_tone(self):
        src = _read(GRID)
        self.assertRegex(src, r"UNKNOWN:\s*\"none\"")
        self.assertNotRegex(src, r"UNKNOWN:\s*\"pass\"")


class ChartAccessibilityTest(unittest.TestCase):
    """4-5. Grafik erişilebilir ve token renkli."""

    def test_chart_is_a_labelled_image_with_text_alternative(self):
        src = _read(CHART)
        self.assertIn('role="img"', src)
        self.assertRegex(src, r"<title[^>]*>")
        self.assertRegex(src, r"<desc[^>]*>")
        # Metin alternatifi: son N koşumun tablosu aynı ekranda.
        self.assertIn("<TableHeader>", src)
        self.assertIn("formatTimestamp(", src)

    def test_no_hex_colors_in_new_surfaces(self):
        for path in (CHART, GRID):
            with self.subTest(path=path.name):
                match = HEX_COLOR.search(_read(path))
                self.assertIsNone(
                    match,
                    "%s ham hex renk taşıyor (%s) — repo token'ı kullanın"
                    % (path.name, match.group(0) if match else ""),
                )

    def test_chart_uses_repo_token_classes(self):
        src = _read(CHART)
        for token in ("stroke-ok", "stroke-accent", "stroke-err"):
            self.assertIn(token, src, "grafik %s token'ını kullanmalı" % token)


class RefsSeriesTest(unittest.TestCase):
    """6. Refs serisi: eksik alan nokta üretmez, pencere kırpılır."""

    def test_missing_refs_fields_do_not_produce_points(self):
        src = _read(REFS_LIB)
        self.assertIn("typeof verified !== \"number\"", src)
        self.assertIn("typeof total !== \"number\"", src)
        self.assertIn("continue;", src)

    def test_window_is_trimmed_from_the_newest_end(self):
        src = _read(REFS_LIB)
        self.assertRegex(src, r"points\.slice\(-Math\.max\(1, limit\)\)")

    def test_coverage_is_null_for_an_empty_series(self):
        src = _read(REFS_LIB)
        self.assertRegex(src, r"if \(!points\.length\) return null;")


if __name__ == "__main__":
    unittest.main()
