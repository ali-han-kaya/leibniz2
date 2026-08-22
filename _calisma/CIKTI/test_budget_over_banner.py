#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_budget_over_banner.py — 'BÜTÇE AŞIMI' şeridinin regresyon kapısı.

preview.html'deki budget-over-banner davranışını kaynak HTML üzerinden
sabitler (JS runtime yok — deterministik string sözleşmeleri):

  1. Trend panelinin üstünde `budget-over-banner` elementi var, `err`
     class'ı + role="alert" (kırmızı şerit).
  2. updateBudgetOverBanner(): aşım yoksa display=none; varsa display=block
     ve metin '🔴 BÜTÇE AŞIMI' ile başlar; en yüksek aşım değeri + canlı
     (budgetState.est > limit) ibaresi içerir.
  3. Çağrı noktaları: renderTrend sonunda (trend geçmişi), scanBudget'te
     (canlı akış [BÜTÇE] satırı) ve applySnapshot limit değişiminde yeniden
     çizim (config değişince şerit otomatik güncellenir).

Kurallar preview.html ile senkron tutulmalıdır; değişiklik sonrası bu dosya
güncellenmelidir. stdlib unittest — ek bağımlılık yok.
"""
import pathlib
import re
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PREVIEW_HTML = SCRIPT_DIR / "preview.html"

BANNER_ELEMENT_RE = re.compile(
    r'<div id="budget-over-banner" class="err" role="alert"')
FUNC_RE = re.compile(r"function updateBudgetOverBanner\(\)\s*\{")


class TestBudgetOverBannerElement(unittest.TestCase):
    """Element ve sözleşmesi."""

    def setUp(self):
        self.html = PREVIEW_HTML.read_text(encoding="utf-8")

    def test_banner_element_present_above_trend_card(self):
        # Element trend başlığından SONRA, trend kartından ÖNCE olmalı.
        h2 = self.html.index("<h2>P0 / P1 trend")
        banner = self.html.index('id="budget-over-banner"')
        card = self.html.index('<svg id="trend"')
        self.assertLess(h2, banner)
        self.assertLess(banner, card)

    def test_banner_uses_err_class_and_alert_role(self):
        self.assertRegex(self.html, BANNER_ELEMENT_RE)

    def test_banner_hidden_by_default(self):
        m = re.search(BANNER_ELEMENT_RE.pattern + r".*?style=\"([^\"]*)\"",
                      self.html, re.S)
        self.assertIsNotNone(m)
        self.assertIn("display:none", m.group(1).replace(" ", ""))


class TestBudgetOverBannerLogic(unittest.TestCase):
    """updateBudgetOverBanner() fonksiyon sözleşmesi."""

    def setUp(self):
        self.html = PREVIEW_HTML.read_text(encoding="utf-8")
        m = FUNC_RE.search(self.html)
        self.assertIsNotNone(m, "updateBudgetOverBanner bulunamadı")
        # Fonksiyon gövdesi: açılış brace'inden kapanışa (sütun 0'da '}').
        start = m.end()
        depth = 1
        i = start
        while i < len(self.html) and depth:
            if self.html[i] == "{":
                depth += 1
            elif self.html[i] == "}":
                depth -= 1
            i += 1
        self.body = self.html[start:i]

    def test_hides_when_no_overage(self):
        # Aşım yoksa display:none + return (metin yazılmaz).
        self.assertIn('el.style.display = "none";', self.body)
        self.assertIn("return;", self.body)

    def test_shows_block_with_prefix(self):
        self.assertIn('el.style.display = "block";', self.body)
        self.assertIn('"🔴 BÜTÇE AŞIMI — "', self.body)

    def test_trend_overage_detected_against_dynamic_limit(self):
        # BUDGET_LIMIT'e karşı filtre (hardcoded 30 DEĞİL).
        self.assertIn("r.budget_usd > BUDGET_LIMIT", self.body)
        self.assertIn("en yüksek $", self.body)

    def test_live_overage_branch(self):
        self.assertIn("budgetState.est > budgetState.limit", self.body)
        self.assertIn("CANLI $", self.body)

    def test_call_sites(self):
        # renderTrend sonunda + scanBudget'te + applySnapshot limit değişimi.
        self.assertRegex(self.html, r"updateBudgetOverBanner\(\);\s*\n\s*\}")
        self.assertRegex(
            self.html,
            r"updateBudgetOverBanner\(\);\s*// canlı aşım varsa şerit anında görünsün")
        # applySnapshot: limit değişince trendCache yeniden çizilir → şerit de.
        self.assertRegex(
            self.html,
            r"if \(trendCache\.length\) renderTrend\(trendCache\);")


if __name__ == "__main__":
    unittest.main()
