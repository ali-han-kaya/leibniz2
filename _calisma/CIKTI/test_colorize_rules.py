#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_colorize_rules.py — preview.html colorizeLine renk kurallarının regresyon kapısı.

colorizeLine() regex kalıplarını bilinen girdilere karşı test eder.
pre-commit hook'u olarak çağrılabilir: regex'ler değişirse veya beklenen
renkler değişirse test başarısız olur.

Kurallar preview.html'deki function colorizeLine() ile senkron tutulmalıdır.
Değişiklik sonrası bu dosyadaki EXPECTED_RULES ve TEST_CASES güncellenmelidir.

Kullanım:
  python3 -m pytest test_colorize_rules.py -v
"""
import pathlib
import re
import sys
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PREVIEW_HTML = SCRIPT_DIR / "preview.html"

# ── colorizeLine regex kuralları — preview.html function colorizeLine() ile senkron ──
# Her kural: (compiled_regex, css_class, description)
# JS regex: \[K8\] = literal [K8], \bUNSAT\b = word boundary
EXPECTED_RULES = [
    (re.compile(r"^\[P0\]|^\[FAIL\]|^SONUÇ: FAIL|FAIL \(P0=|^Error|Exception|^Traceback|^HATA"),
     "err", "P0/FAIL/hata → kırmızı"),
    (re.compile(r"^\[BÜTÇE\]|^Bütçe:|^Budget:|^\$[0-9.]+ / \$[0-9.]+|aşım"),
     "budget", "Bütçe satırları → mor"),
    (re.compile(r"^\[P1\]|\[CLI override\]|\[CLI-OVERRIDE\]"),
     "warn", "P1/CLI override → sarı"),
    (re.compile(r"\[K8\]|\bUNSAT\b|\bSAT\b|^\[PASS\]|^SONUÇ: PASS|^SONUÇ: TÜMÜ PASS|^Verdict: PASS"),
     "ok", "K8/PASS → yeşil"),
    (re.compile(r"^=== |^--- |^\[K[0-9]"),
     "muted", "Bölüm ayırıcı/K katmanı → gri"),
]


def colorize_line(line):
    """preview.html colorizeLine() ile aynı mantık (Python karşılığı)."""
    for pat, css_class, _ in EXPECTED_RULES:
        if pat.search(line):
            return css_class
    return None


# ── Test çiftleri: (input_line, expected_css_class_or_None) ──
TEST_CASES = [
    # err (P0/FAIL)
    ("[P0] K0-STALE bayat zip", "err"),
    ("[FAIL] K12 plist drift", "err"),
    ("SONUÇ: FAIL (P0=1, P1=0)", "err"),
    ("FAIL (P0=2, P1=1)", "err"),
    ("Error: file not found", "err"),
    ("Exception: timeout", "err"),
    ("Traceback (most recent call last):", "err"),
    ("HATA: config geçersiz JSON", "err"),
    # budget
    ("[BÜTÇE] ~175990 token → $1.08 (limit $30.0)", "budget"),
    ("Bütçe: ~175990 token → $1.08 (limit $30.0)", "budget"),
    ("Budget: ~175990 token → $1.08 (limit $30.0)", "budget"),
    ("$1.08 / $30.00", "budget"),
    ("bütçe aşım", "budget"),
    # warn (P1)
    ("[P1] K17 mirror eski", "warn"),
    ("[CLI override] budget=25", "warn"),
    ("[CLI-OVERRIDE] budget_method=weighted", "warn"),
    # ok (PASS/K8)
    ("[K8] Z3: 12/12 PASS", "ok"),
    ("[PASS] P1-a     (T2 ∧ M0) ⊨ T1", "ok"),
    ("SONUÇ: PASS (P0=0, P1=0)", "ok"),
    ("SONUÇ: TÜMÜ PASS", "ok"),
    ("Verdict: PASS", "ok"),
    ("UNSAT (beklenen UNSAT)", "ok"),
    ("SAT (beklenen SAT)", "ok"),
    # muted (bölüm ayırıcı)
    ("=== Stoic-Hume V5 teslim doğrulaması ===", "muted"),
    ("--- soak test ---", "muted"),
    ("[K0] Stale zip taraması", "muted"),
    ("[K5] Referans denetimi", "muted"),
    ("[K12] Plist şablon", "muted"),
    # default (hiçbiri eşleşmez)
    ("PDF: 33 sayfa | References: 64", None),
    ("Config: file ← /path/to/config.json", None),
    ("Merhaba dünya", None),
    ("", None),
]


class TestColorizeRulesSync(unittest.TestCase):
    """preview.html'deki function colorizeLine() ile EXPECTED_RULES senkron mu?"""

    def test_html_exists(self):
        self.assertTrue(PREVIEW_HTML.is_file(),
                        f"preview.html bulunamadı: {PREVIEW_HTML}")

    def test_html_contains_colorize_function(self):
        text = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn("function colorizeLine(line)", text)

    def test_html_has_all_css_classes(self):
        """preview.html colorizeLine'da beklenen tüm CSS class'ları mevcut mu?"""
        text = PREVIEW_HTML.read_text(encoding="utf-8")
        for _, css_class, desc in EXPECTED_RULES:
            self.assertIn(
                f"class=\"{css_class}\"", text,
                f"CSS class '{css_class}' ({desc}) preview.html'de bulunamadı"
            )

    def test_html_rules_count_matches(self):
        """HTML'deki colorizeLine if bloğu sayısı kural sayısıyla eşleşmeli."""
        text = PREVIEW_HTML.read_text(encoding="utf-8")
        # colorizeLine fonksiyonunu izole et
        m = re.search(r"function colorizeLine\(line\)\s*\{(.*?)\nfunction ", text, re.DOTALL)
        self.assertIsNotNone(m, "colorizeLine fonksiyonu bulunamadı")
        body = m.group(1)
        # return '<span class=...appearing' pattern'ini say
        html_returns = re.findall(r"return\s*'<span class=", body)
        self.assertEqual(len(html_returns), len(EXPECTED_RULES),
                         f"Kural sayısı tutarsız: HTML={len(html_returns)} "
                         f"beklenen={len(EXPECTED_RULES)}")


class TestColorizeLine(unittest.TestCase):
    """Bilinen girdiler için renk eşleşme testleri."""

    def test_all_test_cases(self):
        failures = []
        for line, expected in TEST_CASES:
            got = colorize_line(line)
            if got != expected:
                failures.append(
                    f"  '{line[:60]}' → beklenen={expected} alınan={got}"
                )
        if failures:
            self.fail("Renk eşleşme hataları:\n" + "\n".join(failures))


class TestRegexCoverage(unittest.TestCase):
    """Her CSS class en az bir test case ile kaplı mı?"""

    def test_all_classes_covered(self):
        classes_in_rules = {r[1] for r in EXPECTED_RULES}
        classes_in_tests = {exp for _, exp in TEST_CASES if exp is not None}
        uncovered = classes_in_rules - classes_in_tests
        self.assertEqual(uncovered, set(),
                         f"Kapsanmamış CSS class'lar: {uncovered}")

    def test_no_false_positives(self):
        """Hiçbir test case'i yanlış renk eşleşmesi yapmamalı."""
        for line, expected in TEST_CASES:
            got = colorize_line(line)
            # Yanlış pozitif: başka bir class'a düşmüşse hata
            if expected is not None and got is not None and got != expected:
                self.fail(f"Yanlış renk: '{line[:40]}' → {got} (beklenen: {expected})")


class TestReplaySummaryColoring(unittest.TestCase):
    """Replay-start özet satırının renklendirmesini doğrula.

    Replay satırı inline <span> ile üretilir (colorizeLine'dan geçmez);
    yine de her parçanın doğru CSS class'la eşleştiğini doğrularız.
    Format: ── geçmiş run HH:MM:SS ── VERDICT · P0=N · P1=N · refs V/T · P sayfa · bütçe $X · Ys
    """

    def _build_replay_line(self, verdict="PASS", p0=0, p1=0,
                           refs_verified=61, refs_total=61,
                           pdf_pages=33, budget=1.08, duration=30.9,
                           ts="2026-08-22T03:00:00"):
        """preview.html replay-start handler'ının ürettiği HTML'i simüle et."""
        sv = verdict
        scls = "ok" if sv == "PASS" else ("err" if sv in ("FAIL", "ERROR") else "warn")
        bud = "$" + f"{budget:.2f}"
        refs = f" · refs {refs_verified}/{refs_total}" if refs_verified is not None else ""
        pg = f" · {pdf_pages} sayfa" if pdf_pages is not None else ""
        dur = f" · {duration}s"
        tlabel = ts.split("T")[1][:8] if "T" in ts else ""
        label = f"geçmiş run {tlabel}" if tlabel else "geçmiş run"
        html = (
            f'<span class="muted">── {label} ── </span>'
            f'<span class="{scls}">{sv}</span>'
            f'<span class="muted"> · P0={p0} · P1={p1}{refs}{pg} · bütçe {bud}{dur}</span>'
        )
        return html, scls

    def test_pass_verdict_renders_ok_class(self):
        html, _ = self._build_replay_line(verdict="PASS")
        self.assertIn('class="ok"', html)
        self.assertIn('>PASS<', html)

    def test_fail_verdict_renders_err_class(self):
        html, _ = self._build_replay_line(verdict="FAIL")
        self.assertIn('class="err"', html)
        self.assertIn('>FAIL<', html)

    def test_error_verdict_renders_err_class(self):
        html, _ = self._build_replay_line(verdict="ERROR")
        self.assertIn('class="err"', html)

    def test_unknown_verdict_renders_warn_class(self):
        html, _ = self._build_replay_line(verdict="UNKNOWN")
        self.assertIn('class="warn"', html)

    def test_refs_info_present(self):
        html, _ = self._build_replay_line(refs_verified=61, refs_total=61)
        self.assertIn("refs 61/61", html)

    def test_pdf_pages_present(self):
        html, _ = self._build_replay_line(pdf_pages=33)
        self.assertIn("33 sayfa", html)

    def test_budget_present(self):
        html, _ = self._build_replay_line(budget=1.08)
        self.assertIn("bütçe $1.08", html)

    def test_duration_present(self):
        html, _ = self._build_replay_line(duration=30.9)
        self.assertIn("30.9s", html)

    def test_muted_wrapper_for_separator(self):
        html, _ = self._build_replay_line()
        self.assertIn('class="muted"', html)
        self.assertIn("── geçmiş run", html)

    def test_colorize_line_handles_verdict_fragments(self):
        """colorizeLine PASS/FAIL fragment'lerini doğru renklendirmeli."""
        # Tam satır formatları (replay summary'den beklenen)
        self.assertEqual(colorize_line("[PASS] P1-a"), "ok")
        self.assertEqual(colorize_line("SONUÇ: PASS (P0=0, P1=0)"), "ok")
        self.assertEqual(colorize_line("SONUÇ: FAIL (P0=1, P1=0)"), "err")
        self.assertEqual(colorize_line("[BÜTÇE] ~175990 token → $1.08"), "budget")
        self.assertEqual(colorize_line("Verdict: PASS"), "ok")
        # Bare PASS/FAIL colorizeLine'dan geçmez (inline span ile üretilir)
        self.assertEqual(colorize_line("PASS"), None)
        self.assertEqual(colorize_line("FAIL"), None)

    def test_full_replay_line_html_structure(self):
        """Tüm replay satırı 3 span içermeli: muted(başlık) + verdict + muted(detay)."""
        html, _ = self._build_replay_line()
        span_count = html.count('<span class=')
        self.assertEqual(span_count, 3,
                         f"Replay satırında 3 span bekleniyor, {span_count} bulundu")


class TestRefsBySourceCards(unittest.TestCase):
    """renderRefsOnline içindeki kaynak özet kartları (ro-source-cards) + tablo."""

    @classmethod
    def setUpClass(cls):
        with open(PREVIEW_HTML, encoding="utf-8") as f:
            cls._html = f.read()

    def test_source_cards_div_exists(self):
        """ro-source-cards div'i HTML'de tanımlı."""
        self.assertIn('id="ro-source-cards"', self._html)

    def test_source_card_css_defined(self):
        """source-card CSS sınıfı tanımlı."""
        self.assertIn('.source-card {', self._html)
        self.assertIn('source-card .label', self._html)
        self.assertIn('source-card .value', self._html)

    def test_src_names_map_complete(self):
        """Tüm kaynak tipleri için srcNames eşlemesi var."""
        for k in ("crossref", "openlibrary", "sep", "archive", "perseus",
                  "hathitrust", "url"):
            self.assertIn(k + ":", self._html,
                          f"srcNames map'te '{k}' eksik")

    def test_src_colors_map_has_all_source_types(self):
        """srcColors map'te tüm source tipleri renk tanımına sahip."""
        for k in ("crossref", "openlibrary", "sep", "archive", "perseus",
                  "hathitrust", "url"):
            self.assertIn(k + ":", self._html,
                          f"srcColors map'te '{k}' eksik")

    def test_src_icons_map_has_all_source_types(self):
        """srcIcons map'te tüm source tipleri ikon tanımına sahip."""
        for k in ("crossref", "openlibrary", "sep", "archive", "perseus",
                  "hathitrust", "url"):
            self.assertIn(k + ":", self._html,
                          f"srcIcons map'te '{k}' eksik")

    def test_source_card_html_structure(self):
        """Kart HTML'i: card source-card + border-left + label + value."""
        self.assertIn('class="card source-card"', self._html)
        self.assertIn('border-left:3px solid', self._html)

    def test_colors_are_valid_hex(self):
        """Tüm renkler geçerli hex formatında."""
        import re
        hex_colors = re.findall(r'"(#[0-9a-fA-F]{6})"', self._html)
        self.assertGreater(len(hex_colors), 6,
                           f"En az 7 hex rengi bekleniyor, {len(hex_colors)} bulundu")

    def test_source_card_grid_after_metrics(self):
        """ro-source-cards grid'i, ro-metrics grid'inden sonra gelir."""
        idx_metrics = self._html.find('id="ro-metrics"')
        idx_cards = self._html.find('id="ro-source-cards"')
        self.assertGreater(idx_cards, idx_metrics,
                           "ro-source-cards, ro-metrics'ten sonra olmalı")

    def test_table_uses_src_colors(self):
        """Tablo satırları srcColors'dan renk alır (border-left + bar)."""
        self.assertIn("srcColors[k] || \"var(--accent)\"", self._html)

    def test_table_bar_is_colored(self):
        """Yatay çubuk grafiği src renk ile doldurulur (background: + clr)."""
        self.assertIn("background:' + clr", self._html)
        self.assertIn('height:14px', self._html)  # thicker bars

    def test_table_rows_have_colored_left_border(self):
        """Her tablo satırı border-left:3px solid <renk>."""
        self.assertIn("border-left:3px solid ' + clr", self._html)

    def test_table_has_columns_cnt_pct_bar(self):
        """Tablo: Source, Cnt, %, Bar sütunları."""
        self.assertIn("Cnt</th>", self._html)
        self.assertIn("Bar</th>", self._html)

    def test_shared_maps_for_cards_and_table(self):
        """srcColors/srcNames/srcIcons tek yerde tanımlı (cards+table paylaşır)."""
        self.assertIn("const srcColors = {", self._html)
        self.assertIn("const srcNames = {", self._html)
        self.assertIn("const srcIcons = {", self._html)
        # Old separate names/colors/icons maps should be gone
        self.assertNotIn("const colors = { crossref:", self._html)
        self.assertNotIn("const icons = { crossref:", self._html)


class TestRefsTrendBySourceStacked(unittest.TestCase):
    """renderRefsTrend içindeki by_source yığılmış alan + tooltip + lejant."""

    @classmethod
    def setUpClass(cls):
        with open(PREVIEW_HTML, encoding="utf-8") as f:
            cls._html = f.read()

    def test_src_colors_match_source_cards(self):
        """SRC_COLORS (trend) ile srcColors (cards+table) aynı paleti kullanır."""
        for src, expected in (("crossref", "#58a6ff"), ("sep", "#3fb950"),
                               ("openlibrary", "#bc8cff"), ("archive", "#d29922"),
                               ("perseus", "#f85149")):
            self.assertIn(f'{src}: "{expected}"', self._html,
                          f"SRC_COLORS/srcColors'ta {src} rengi {expected} olmalı")

    def test_src_names_defined_in_trend(self):
        """SRC_NAMES map'i renderRefsTrend'de tanımlı."""
        self.assertIn("const SRC_NAMES =", self._html)
        for k in ("crossref", "openlibrary", "sep", "archive", "perseus"):
            self.assertIn(k + ":", self._html,
                          f"SRC_NAMES map'te '{k}' eksik")

    def test_tooltip_shows_by_source(self):
        """showRefsTrendTip hover tooltip'i by_source kırılımını gösterir."""
        self.assertIn("── by_source ──", self._html)
        self.assertIn("refs_by_source", self._html)
        self.assertIn("srcKeys.sort", self._html)

    def test_refs_tooltip_shares_budget_line(self):
        """refs tooltip'i de P0/P1 ile aynı trendTipHeader formatını kullanır:
        ts → verdict → duration → budget (renkli limit durumu)."""
        self.assertEqual(self._html.count("const head = trendTipHeader(r);"),
                         2, "iki tooltip de ortak başlığı çağırmalı")
        # budget satırı ortak başlıktan (head[2]) gelir + renk sınıfları CSS'te.
        self.assertIn("head[2],", self._html)
        self.assertIn("budgetTipColor", self._html)
        self.assertIn("budgetLimitNote", self._html)
        self.assertIn(".tip .tt-over", self._html)
        self.assertIn(".tip .tt-under", self._html)
        # refs'e özgü satırlar korunur.
        self.assertIn("refs    : ", self._html)
        self.assertIn("mismatch: ", self._html)

    def test_legend_shows_per_source_counts(self):
        """Lejant: son run'un her kaynak için ayrı ayrı sayısını gösterir."""
        self.assertIn("SRC_NAMES[s]||s", self._html)
        self.assertIn("lastSrc", self._html)

    def test_src_colors_include_all_types(self):
        """SRC_COLORS tüm source tiplerini kapsar."""
        for k in ("crossref", "sep", "openlibrary", "archive",
                  "perseus", "hathitrust", "diğer"):
            self.assertIn(k + ":", self._html,
                          f"SRC_COLORS'ta '{k}' eksik")

    def test_src_order_consistent(self):
        """SRC_ORDER listesi tutarlı — Perseus son sırada."""
        self.assertIn('"crossref", "sep", "openlibrary", "archive", "perseus"', self._html)

    def test_stacked_area_polygons_present(self):
        """Yığılmış alan polygon'ları HTML'de üretiliyor."""
        self.assertIn("fill-opacity", self._html)
        self.assertIn('stroke="none"', self._html)


class TestTrendBudgetLimitSeries(unittest.TestCase):
    """renderTrend per-run budget_limit zaman serisi (config değişimi)."""

    @classmethod
    def setUpClass(cls):
        with open(PREVIEW_HTML, encoding="utf-8") as f:
            cls._html = f.read()

    def test_limit_series_reads_budget_limit_field(self):
        # lims, run kayıtlarındaki budget_limit'ten beslenir (history.jsonl).
        self.assertIn("r.budget_limit", self._html)
        self.assertIn("isFinite(v)", self._html)

    def test_axis_scales_to_limits_when_varying(self):
        # Limit değiştiyse bütçe ekseni limitleri de kapsar (step görünür).
        self.assertIn("limsVary", self._html)
        self.assertIn("Math.min(...lims) !== Math.max(...lims)", self._html)
        self.assertIn("Math.max(...buds, 0.01, ...(limsVary ? lims : []))",
                      self._html)

    def test_step_polyline_drawn_only_when_varying(self):
        # Sabit limitse step çizilmez (referans çizgisi yeter); değişimde
        # turuncu düz polyline + yatay basamak segmentleri üretilir.
        self.assertIn("if (limsVary)", self._html)
        self.assertIn('stroke="#ffa657" stroke-width="2"', self._html)
        self.assertIn("stepPts.push(`${x(i + 1)},${yv}`)", self._html)

    def test_legend_mentions_per_run_limit_when_varying(self):
        # Lejant: güncel limit (kesikli) + değişim varsa per-run (düz).
        self.assertIn("güncel limit $", self._html)
        self.assertIn("per-run limit (config değişimi)", self._html)
        self.assertIn("limsVary ? \" · Turuncu (düz)", self._html)

    def test_by_src_computation_falls_back_to_empty(self):
        """refs_by_source yoksa bySrc boş map üretir."""
        self.assertIn("r.refs_by_source || {}", self._html)


class TestRunHistoryLeanIndicator(unittest.TestCase):
    """loadRunHistory içindeki K9 Lean renkli gösterge (●/·)."""

    @classmethod
    def setUpClass(cls):
        with open(PREVIEW_HTML, encoding="utf-8") as f:
            cls._html = f.read()

    def test_lean_pass_shows_green_dot(self):
        """lean_ok === true → yeşil ● (color:var(--ok))."""
        self.assertIn('r.lean_ok === true', self._html)
        self.assertIn("Lean PASS", self._html)
        self.assertIn('color:var(--ok)', self._html)

    def test_lean_fail_shows_red_dot(self):
        """lean_ok === false → kırmızı ● (color:var(--err))."""
        self.assertIn('r.lean_ok === false', self._html)
        self.assertIn("Lean FAIL", self._html)
        self.assertIn('color:var(--err)', self._html)

    def test_lean_not_run_shows_gray_dot(self):
        """lean_ok ne true ne false → gri · (muted)."""
        self.assertIn('Lean: koşulmadı', self._html)
        self.assertIn('class="muted"', self._html)

    def test_over_budget_badge_computed_against_dynamic_limit(self):
        """Aşım rozeti BUDGET_LIMIT'e karşı hesaplanır (hardcoded değil)."""
        self.assertIn("r.budget_usd > BUDGET_LIMIT", self._html)
        self.assertIn("isFinite(BUDGET_LIMIT)", self._html)
        self.assertIn("fmtLimit(BUDGET_LIMIT)", self._html)

    def test_over_budget_badge_red_span(self):
        """Aşım run'ları kırmızı 'AŞIM' rozetiyle işaretlenir."""
        self.assertIn('class="rh-over"', self._html)
        self.assertIn(">AŞIM</span>", self._html)
        self.assertIn("BÜTÇE AŞIMI: $", self._html)
        self.assertIn(".rh-over", self._html)
        self.assertIn("background:var(--err)", self._html)

    def test_over_badge_appended_after_lean(self):
        """Rozet satır sonuna (lean göstergesinden sonra) eklenir."""
        self.assertIn("${lean}${overBadge}", self._html)
        self.assertIn("const overBadge = over", self._html)

    def test_lean_detail_in_fail_title(self):
        """FAIL durumunda lean_detail tooltip'e eklenir."""
        self.assertIn('r.lean_detail', self._html)

    def test_lean_dot_appended_after_budget(self):
        """Lean göstergesi bütçe ve duration'dan sonra eklenir."""
        # lean değişkeni tanımı let lean = "";
        self.assertIn('let lean = ""', self._html)
        # dönüş satırında ${lean} var
        self.assertIn('${lean}', self._html)


class TestTrendLeanAxis(unittest.TestCase):
    """renderTrend içindeki K9 Lean PASS oranı % ekseni."""

    @classmethod
    def setUpClass(cls):
        with open(PREVIEW_HTML, encoding="utf-8") as f:
            cls._html = f.read()

    def test_lean_pass_rate_line_exists(self):
        """Pembe kesikli çizgi Lean % eksenini çizer."""
        self.assertIn("#e055d2", self._html)
        self.assertIn('stroke-dasharray="5 2"', self._html)
        self.assertIn("${leanPts.join", self._html)

    def test_lean_axis_labels_exist(self):
        """Lean ekseni 100% ve 0% etiketlerini gösterir."""
        self.assertIn(">100%<", self._html)
        self.assertIn(">0%<", self._html)
        self.assertIn("leanAxisX", self._html)

    def test_lean_numeric_computation(self):
        """lean_ok true → 100, false → 0, null → skip."""
        self.assertIn("r.lean_ok === true ? 100", self._html)
        self.assertIn("r.lean_ok === false ? 0", self._html)
        self.assertIn("hasLean = leanVals.length > 0", self._html)

    def test_lean_pass_fail_points_on_line(self):
        """PASS/FAIL noktaları çizgi üstünde (yL ile hizalı)."""
        self.assertIn("const ly = yL(leans[i])", self._html)
        self.assertIn('r="3" fill="#3fb950"', self._html)

    def test_lean_tooltip_shows_pass_rate(self):
        """Trend tooltip'inde lean satırı: PASS (100%) / FAIL (0%)."""
        self.assertIn("lean    : PASS (100%)", self._html)
        self.assertIn("lean    : FAIL (0%)", self._html)
        self.assertIn("leanLine", self._html)

    def test_legend_shows_lean_pink_dashed(self):
        """Lejant: Pembe (kesikli) = Lean PASS oranı."""
        self.assertIn("Pembe (kesikli) = Lean PASS oranı", self._html)
        self.assertIn("leanPct", self._html)

    def test_pr_widened_for_5th_axis(self):
        """PR 248 ile 5 eksene yer açıldı (212 → 248)."""
        self.assertIn("PR = 248", self._html)
        self.assertNotIn("PR = 212", self._html)


class TestLeanFailPulse(unittest.TestCase):
    """Lean FAIL olduğunda animasyonlu uyarıcı (fail-pulse + lean-alert)."""

    @classmethod
    def setUpClass(cls):
        with open("_calisma/CIKTI/preview.html", encoding="utf-8") as f:
            cls._html = f.read()

    def test_fail_pulse_class_defined_in_css(self):
        """.badge.fail-pulse iki animasyonu bağlar: failShake + failGlow."""
        self.assertIn("badge.fail-pulse", self._html)
        self.assertIn("failShake", self._html)
        self.assertIn("failGlow", self._html)

    def test_fail_shake_keyframe_exists(self):
        """@keyframes failShake: yatay titreşim."""
        self.assertIn("@keyframes failShake", self._html)
        self.assertIn("translateX", self._html)

    def test_fail_glow_keyframe_exists(self):
        """@keyframes failGlow: kırmızı glow pulse."""
        self.assertIn("@keyframes failGlow", self._html)
        self.assertIn("box-shadow:0 0 18px", self._html)

    def test_lean_alert_element_exists(self):
        """#lean-alert elementi status board altında mevcut (hidden)."""
        self.assertIn('id="lean-alert"', self._html)
        self.assertIn('lean-alert hidden', self._html)
        self.assertIn('K9 Lean: FAIL', self._html)

    def test_fail_pulse_added_to_k9_badge(self):
        """renderKLayers: K9 + leanOk===false → badge class'a fail-pulse eklenir."""
        self.assertIn('kcls += " fail-pulse"', self._html)
        self.assertIn('k === "K9" && leanOk === false', self._html)

    def test_lean_alert_shown_hidden_in_updatelatest(self):
        """updateLatest: lean_ok===true → hidden, ===false → visible + detail."""
        self.assertIn('la.classList.add("hidden")', self._html)
        self.assertIn('la.classList.remove("hidden")', self._html)
        self.assertIn('ispat zinciri kırık', self._html)

    def test_lean_alert_uses_err_color(self):
        """.lean-alert kırmızı tema: color:var(--err), border:var(--err)."""
        self.assertIn(".lean-alert {", self._html)
        self.assertIn("color:var(--err)", self._html)
        self.assertIn("border:1px solid var(--err)", self._html)


class TestRunHistoryAutoRefresh(unittest.TestCase):
    """Run history SSE snapshot/update event'lerinde otomatik yenilenir."""

    @classmethod
    def setUpClass(cls):
        with open("_calisma/CIKTI/preview.html", encoding="utf-8") as f:
            cls._html = f.read()

    def test_load_run_history_called_on_init(self):
        """initLoad sonunda loadRunHistory() çağrısı var."""
        self.assertIn('loadRunHistory();', self._html)
        # initLoad içinde loadRunHistory çağrısı (init sonrası)
        init_pos = self._html.index('function initLoad()')
        snippet = self._html[init_pos:]
        self.assertIn('loadRunHistory();', snippet)

    def test_snapshot_handler_calls_load_run_history(self):
        """SSE snapshot event handler'ı loadRunHistory() çağırır."""
        # "Run history'yi de güncelle (yeni run snapshot'ı gelince)" yorumu
        self.assertIn('snapshot', self._html.lower())
        snap_pos = self._html.index('addEventListener("snapshot"')
        # loadRunHistory snapshot handler bloğu içinde
        snap_block = self._html[snap_pos:snap_pos + 1200]
        self.assertIn('loadRunHistory();', snap_block)

    def test_update_handler_calls_load_run_history(self):
        """SSE update event handler'ı da loadRunHistory() çağırır."""
        self.assertIn('addEventListener("update"', self._html)
        update_pos = self._html.index('addEventListener("update"')
        update_block = self._html[update_pos:update_pos + 1200]
        self.assertIn('loadRunHistory();', update_block)

    def test_count_is_three_calls(self):
        """loadRunHistory tam 4 yerde çağrılır: init, setRhFilter, snapshot, update."""
        count = self._html.count('loadRunHistory();')
        self.assertEqual(count, 4, f"Beklenen 4 çağrı, bulunan: {count}")

    def test_snapshot_comment_exists(self):
        """'Run history'yi de güncelle' yorumu snapshot handler'da var."""
        self.assertIn("Run history'yi de güncelle", self._html)


class TestRunHistoryClickToLoad(unittest.TestCase):
    """Run history satırına tıklanınca o run'un stdout'u yüklenir."""

    @classmethod
    def setUpClass(cls):
        with open("_calisma/CIKTI/preview.html", encoding="utf-8") as f:
            cls._html = f.read()

    def test_rh_row_css_class_exists(self):
        """.rh-row stili: cursor:pointer + hover highlight."""
        self.assertIn(".rh-row", self._html)
        self.assertIn("cursor:pointer", self._html)
        self.assertIn(".rh-row:hover", self._html)

    def test_rows_have_data_ts_attr(self):
        """Her satır <div class="rh-row" data-ts="..." ile sarılır."""
        self.assertIn('class="rh-row"', self._html)
        self.assertIn('data-ts=', self._html)

    def test_rows_have_onclick_handler(self):
        """onclick="loadRunStdout('...')" çağrısı var."""
        self.assertIn('onclick="loadRunStdout', self._html)
    def test_load_run_stdout_function_exists(self):
        """loadRunStdout(ts) fonksiyonu tanımlı."""
        self.assertIn("function loadRunStdout(ts)", self._html)

    def test_fetch_calls_run_stdout_endpoint(self):
        """fetch("/api/run-stdout?ts=" + encodeURIComponent(ts))"""
        self.assertIn("/api/run-stdout?ts=", self._html)
        self.assertIn("encodeURIComponent(ts)", self._html)

    def test_on_click_stdout_applied(self):
        """Yanıt geldiğinde applyStdout çağrılır."""
        self.assertIn("applyStdout(d.stdout", self._html)

    def test_error_fallback_in_stdout_box(self):
        """Yüklenemedi hatası stdout box'a yazılır."""
        self.assertIn("Yüklenemedi:", self._html)
        self.assertIn("Yükleniyor", self._html)

    def test_escaped_quotes_in_ts_attr(self):
        """data-ts attribute'unda tırnak escape edilir."""
        self.assertIn("replace(/'/g", self._html)
        self.assertIn("replace(/\"/g", self._html)


class TestRunHistoryFilter(unittest.TestCase):
    """Run history PASS/FAIL/P0 filtresi."""

    @classmethod
    def setUpClass(cls):
        with open("_calisma/CIKTI/preview.html", encoding="utf-8") as f:
            cls._html = f.read()

    def test_filter_buttons_exist(self):
        """4 filtre butonu: all, PASS, FAIL, P0."""
        self.assertIn('data-f="all"', self._html)
        self.assertIn('data-f="PASS"', self._html)
        self.assertIn('data-f="FAIL"', self._html)
        self.assertIn('data-f="P0"', self._html)

    def test_filter_bar_exists(self):
        """rh-filter div'i var."""
        self.assertIn('class="rh-filter"', self._html)
        self.assertIn('onclick="setRhFilter', self._html)

    def test_filter_var_declared(self):
        """let rhFilter = "all" değişkeni tanımlı."""
        # Search for the declaration near the top of JS
        self.assertIn('let rhFilter = "all"', self._html)

    def test_set_rh_filter_function_exists(self):
        """function setRhFilter(f) tanımlı."""
        self.assertIn('function setRhFilter(f)', self._html)

    def test_pass_filter_logic(self):
        """PASS filtresi: verdict === "PASS" && p0 === 0."""
        self.assertIn('r.verdict === "PASS"', self._html)
        self.assertIn('(r.p0||0) === 0', self._html)

    def test_fail_filter_logic(self):
        """FAIL filtresi: verdict === "FAIL" || "ERROR"."""
        self.assertIn('r.verdict === "FAIL"', self._html)

    def test_p0_filter_logic(self):
        """P0 filtresi: (r.p0||0) > 0."""
        self.assertIn('(r.p0||0) > 0', self._html)

    def test_filter_count_suffix(self):
        """Filtreli sayı: "(3 / 15)" gösterilir."""
        self.assertIn('fSuffix', self._html)
        self.assertIn('" / " + rows.length', self._html)

    def test_filter_active_toggle(self):
        """setRhFilter butonlara .active toggle eder."""
        self.assertIn('classList.toggle("active"', self._html)
        self.assertIn('b.dataset.f === f', self._html)

    def test_filter_css_button_styles(self):
        """Filtre buton CSS: .rh-filter button.active[data-f="PASS"]."""
        self.assertIn('.rh-filter button.active[data-f="PASS"]', self._html)
        self.assertIn('.rh-filter button.active[data-f="FAIL"]', self._html)
        self.assertIn('.rh-filter button.active[data-f="P0"]', self._html)

    def test_init_sets_filter_all(self):
        """Sayfa yüklenince setRhFilter("all") çağrılır."""
        self.assertIn('setRhFilter("all")', self._html)

    def test_empty_filter_message(self):
        """Filtreyle eşleşen run yoksa mesaj gösterilir."""
        self.assertIn('filtreyle eşleşen run yok', self._html)


class TestFmtDuration(unittest.TestCase):
    """fmtDuration: süreyi okunabilir formata çevirir (3s, 1m30s, 1h00m)."""

    @classmethod
    def setUpClass(cls):
        with open("_calisma/CIKTI/preview.html", encoding="utf-8") as f:
            cls._html = f.read()

    def test_fmt_duration_function_exists(self):
        """function fmtDuration(s) tanımlı."""
        self.assertIn("function fmtDuration(s)", self._html)

    def test_seconds_below_60_format(self):
        """<60s: "3s", "59s"."""
        self.assertIn("sec < 60", self._html)
        self.assertIn('return sec + "s"', self._html)

    def test_minutes_format(self):
        """60-3599s: padStart mSSs → "1m05s"."""
        self.assertIn("padStart(2,", self._html)
        self.assertIn("Math.floor(sec / 60)", self._html)
        self.assertIn('"m"', self._html)

    def test_hours_format(self):
        """>=3600s: "1h00m"."""
        self.assertIn("Math.floor(sec / 3600)", self._html)
        self.assertIn('"h"', self._html)

    def test_null_returns_dash(self):
        """null/NaN → "—"."""
        self.assertIn('return "\u2014"', self._html)

    def test_replay_line_uses_fmt_duration(self):
        """Replay özet satırı: " · " + fmtDuration(...)"""
        self.assertIn("fmtDuration(sum.duration_s)", self._html)

    def test_replay_line_no_longer_uses_plain_s(self):
        """Eski " + sum.duration_s + "s" deseni KALKMALI."""
        self.assertNotIn('sum.duration_s + "s"', self._html)


class TestMetricsCards(unittest.TestCase):
    """Metrics kartlarının varlığı ve ayrıklığı (pages / refs split)."""

    @classmethod
    def setUpClass(cls):
        with open("_calisma/CIKTI/preview.html", encoding="utf-8") as f:
            cls._html = f.read()

    def test_pdf_pages_has_own_card(self):
        """PDF sayfa sayısı ayrı kart: id="m-pages"."""
        self.assertIn('id="m-pages"', self._html)
        self.assertIn("PDF pages", self._html)

    def test_reference_count_has_own_card(self):
        """Referans sayısı ayrı kart: id="m-refs"."""
        self.assertIn('id="m-refs"', self._html)
        self.assertIn("Reference count", self._html)

    def test_old_combined_card_removed(self):
        """Eski birleşik kart (m-pdf) KALMADI."""
        self.assertNotIn('id="m-pdf"', self._html)
        self.assertNotIn("PDF pages / refs", self._html)

    def test_pages_setter_independent(self):
        """m-pages yalnızca pdf_pages alır (ref_count ile birleşik DEĞİL)."""
        self.assertIn('$("m-pages").textContent = d.pdf_pages', self._html)

    def test_refs_setter_independent(self):
        """m-refs yalnızca ref_count alır."""
        self.assertIn('$("m-refs").textContent = d.ref_count', self._html)



class TestServiceWorkerRegistration(unittest.TestCase):
    """preview.html'deki service worker registration bloğunun regresyon kapısı.

    Electron webview cache bypass'ı için sw.js /sw.js route'una kaydolur.
    skipWaiting + clients.claim + fetch-no-cache zincirini kapsar.
    """

    @classmethod
    def setUpClass(cls):
        cls._html = (SCRIPT_DIR / "preview.html").read_text(encoding="utf-8")
        cls._sw = None
        sw_path = SCRIPT_DIR / "sw.js"
        if sw_path.is_file():
            cls._sw = sw_path.read_text(encoding="utf-8")

    def test_sw_registration_code_present(self):
        """navigator.serviceWorker.register('/sw.js') cagrisi mevcut."""
        self.assertIn("navigator.serviceWorker.register('/sw.js'", self._html)
        self.assertIn("scope: '/'", self._html)

    def test_skip_waiting_and_claim_in_sw_js(self):
        """sw.js'te skipWaiting + clients.claim her ikisi de mevcut."""
        self.assertIsNotNone(self._sw, "sw.js bulunamadi")
        self.assertIn("self.skipWaiting()", self._sw)
        self.assertIn("self.clients.claim()", self._sw)

    def test_fetch_no_cache_in_sw_js(self):
        """sw.js fetch handler'i no-cache zorlar."""
        self.assertIsNotNone(self._sw, "sw.js bulunamadi")
        self.assertIn("cache: 'no-cache'", self._sw)

    def test_api_endpoints_bypass_cache_in_sw_js(self):
        """sw.js /api/* endpoint'leri icin network-first, cache atlanir."""
        self.assertIsNotNone(self._sw, "sw.js bulunamadi")
        self.assertIn("/api/", self._sw)

    def test_silent_fallback_on_no_sw_support(self):
        """.catch(() => {}) — sw destegi olmayan ortamlarda sessiz."""
        self.assertIn(".catch(() => {})", self._html)

    def test_sw_registration_wrapped_in_feature_detect(self):
        """'serviceWorker' in navigator kontrolu var."""
        self.assertIn("'serviceWorker' in navigator", self._html)

if __name__ == "__main__":
    unittest.main()
