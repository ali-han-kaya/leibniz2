#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dashboard_panel_isolation.py — PANEL ve AKIŞ BAĞIMSIZLIĞI (E2E).

Bu süit bir /tmp Playwright betiğinden taşındı. Taşınan hâli CI'da koşamazdı:
elle mutasyona uğratılmış bir kaynak ağacına ve elle başlatılmış bir dev
sunucusuna dayanıyordu (`python3 /tmp/panel_isolation.py http://localhost:3100`).
Şimdi kendi upstream'ini ve kendi `next start`'ını kurar; arıza senaryoları
TEST KUMANDASIYLA (stub uçları) üretilir — kaynak kodu değiştirmek gerekmez.

Ölçülen iddia: **bir kaynağın/akışın düşmesi diğer panelleri düşürmez.**

Üç ayrı kaynak, üç ayrı yüzey:
  * `/api/latest` → verdict kartı (`@verdict` slotu)
  * `/api/trend`  → kompakt koşum tablosu (`@trend` slotu)
  * `/api/run`    → SSE tüneli (`/api/events`); paneller SSR verisinde yaşar,
                    canlı olmak zorunlu değil

Her senaryo ÜÇ adımı ölçer: (1) arıza gerçekten servis edildi mi (hit sayacı —
vakum denetimi), (2) sağlam paneller yerinde mi, (3) kaynak dönünce retry
veriyi geri getiriyor mu.

KAPSAM SINIRI (dürüstçe): `/trend` sayfasındaki ÜÇ panel aynı upstream'i
(`/api/trend`) ve aynı istek-içi `cache()` girdisini paylaşır; bir veri arızası
üçünü birlikte vurur. Panel-başına izolasyon orada ancak KOD düzeyinde bir
arıza ile ölçülebilir (mutasyonla kanıtlandı, kalıcı test olarak koşamaz);
o sözleşme statik tarafta `test_dashboard_next_ui_contract.PanelBoundaryTest`
ile sabitlenmiştir. Bu dosya kaynak/akış düzeyindeki bağımsızlığı ölçer.

Çalıştırma:
    _calisma/.venv_z3/bin/python -m unittest _calisma.CIKTI.test_dashboard_panel_isolation -v

Ön koşullar: `apps/dashboard-next/node_modules` + derlenmiş `.next` + Chromium
(Playwright). Eksikse SKIP — CI'da `dashboard-smoke` job'ı derlemeyi ve
tarayıcıyı zaten hazırlar.
"""

import sys
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Ortak kablo TEK kaynaktan: yayınlayan upstream + `next start` + panel
# gözlem yardımcıları. Kopyalamak, iki süitin fixture sözleşmesini ayırırdı
# (biri düzeltilir, diğeri eski varsayımla yeşil kalır).
from test_dashboard_next_live_stream import (  # noqa: E402
    _NextPanelE2E,
    sync_playwright,
)


@unittest.skipIf(sync_playwright is None, "Playwright/Chromium yok")
class PanelIsolationTest(_NextPanelE2E):
    """Kaynak/akış arızaları panel sınırlarını AŞMAMALI."""

    UPSTREAM_ROWS = 3

    # ── yardımcılar ─────────────────────────────────────────────────────

    def _open(self, browser, path="/"):
        page = browser.new_page()
        page.goto(self.base + path, wait_until="domcontentloaded")
        return page

    def _error_titles(self, page):
        return page.evaluate(
            "() => [...document.querySelectorAll('[role=alert]')]"
            ".map(e => e.textContent.trim().slice(0, 60)).filter(Boolean)")

    def _h2_texts(self, page):
        """`textContent` (CSS `text-transform` uygulanmamış hâli).

        `all_inner_texts()` RENDER edilmiş metni döndürür; başlıklar CSS'te
        büyük harfe çevrildiği için "GÜVENLİK YÜZEYİ" gelir ve sözleşme
        metniyle eşleşmez (ilk ölçümdeki yanlış kırmızının sebebi buydu).
        """
        return page.evaluate(
            "() => [...document.querySelectorAll('h2')]"
            ".map(e => e.textContent.trim())")

    def _wait_alert(self, page, needle, timeout=25000):
        page.wait_for_function(
            "needle => [...document.querySelectorAll('[role=alert]')]"
            ".some(e => e.textContent.includes(needle))",
            arg=needle, timeout=timeout)

    def _wait_verdict_card(self, page, timeout=25000):
        page.wait_for_function(
            "() => [...document.querySelectorAll('h2')]"
            ".some(e => e.textContent.trim() === 'Son Koşum')",
            timeout=timeout)

    # ── 1. /api/latest düşer: verdict kartı tekil kalır ─────────────────

    def test_verdict_source_outage_leaves_table_and_security_card_alive(self):
        self._fail_latest(True)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = self._open(browser)
                    self._wait_alert(page, "Verdict paneli yüklenemedi")

                    # Vakum denetimi: arıza gerçekten o uca gitti.
                    self.assertGreaterEqual(
                        self.upstream.hits["/api/latest"], 1,
                        "upstream /api/latest hiç çağrılmadı — ölçüm vakum")

                    # İzolasyon: tablo SSR satırlarını basmaya devam ediyor,
                    # güvenlik kartı (kendi ucu) ayakta.
                    self.assertGreater(
                        page.locator("tbody tr").count(), 0,
                        "verdict kaynağı düştüğünde koşum tablosu da düştü")
                    h2s = self._h2_texts(page)
                    self.assertIn("Güvenlik Yüzeyi", h2s,
                                  "verdict arızası güvenlik kartını düşürdü")
                    self.assertIn("Son 5 Koşum", h2s,
                                  "verdict arızası koşum tablosunu düşürdü")

                    # Kaynak döner + retry → kart veriyle geri gelir.
                    self._fail_latest(False)
                    page.get_by_role(
                        "button", name="Tekrar dene").first.dispatch_event(
                            "click")
                    self._wait_verdict_card(page)
                    self.assertEqual(self._error_titles(page), [],
                                     "retry sonrası hata kartı kaldı")
                finally:
                    browser.close()
        finally:
            self._fail_latest(False)

    # ── 2. /api/trend düşer: verdict kartı bunu duymaz ─────────────────

    def test_trend_source_outage_leaves_the_verdict_card_alive(self):
        self._fail_trend(True)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = self._open(browser)
                    self._wait_alert(page, "Koşum geçmişi yüklenemedi")

                    self.assertGreaterEqual(
                        self.upstream.hits["/api/trend"], 1,
                        "upstream /api/trend hiç çağrılmadı — ölçüm vakum")

                    # Verdict kendi ucundan beslenir: tablo ölürken YAŞAMALI.
                    state = self._panel(page, "Son Koşum", None)
                    self.assertIsNotNone(state["verdict"],
                                         "trend arızası verdict kartını düşürdü")
                    self.assertIn(state["verdict"]["status"], ("PASS", "FAIL"),
                                  "verdict kartı veri basmıyor: %r"
                                  % (state["verdict"],))

                    # Retry yalnız tabloyu geri getirmeli, verdict'i bozmadan.
                    self._fail_trend(False)
                    page.get_by_role(
                        "button", name="Tekrar dene").first.dispatch_event(
                            "click")
                    page.wait_for_function(
                        "() => document.querySelectorAll('tbody tr').length > 0",
                        timeout=30000)
                    after = self._panel(page, "Son Koşum", None)
                    self.assertEqual(after["verdict"]["status"],
                                     state["verdict"]["status"],
                                     "tablo retry'si verdict kartını değiştirdi")
                finally:
                    browser.close()
        finally:
            self._fail_trend(False)

    # ── 3. SSE düşer: paneller SSR verisinde kalır ─────────────────────

    def test_live_stream_outage_keeps_server_rendered_panels(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = self._open(browser)
                page.wait_for_function(
                    "() => document.querySelectorAll('tbody tr').length > 0",
                    timeout=25000)
                self._wait_live(page)  # akış önce SAĞLAMDI (kanıt)
                rows = page.locator("tbody tr").count()
                pageerrors = []
                page.on("pageerror", lambda e: pageerrors.append(str(e)))

                self._fail_sse(True)
                try:
                    # Tünel kapanır; tablo "canlı bağlantı bekleniyor"a düşer
                    # ama SSR penceresi ekranda kalır (fail-closed davranış).
                    page.wait_for_function(
                        "() => document.body.innerText"
                        ".includes('canlı bağlantı bekleniyor')",
                        timeout=25000)
                    self.assertGreaterEqual(
                        page.locator("tbody tr").count(), rows,
                        "akış düştüğünde sunucudan gelen satırlar kayboldu")
                    self.assertEqual(self._error_titles(page), [],
                                     "akış arızası hata kartına dönüştü")
                    self.assertEqual(pageerrors, [],
                                     "akış arızası sayfa hatası üretti: %r"
                                     % pageerrors)
                    self.assertGreaterEqual(
                        self.upstream.hits["/api/run"], 1,
                        "upstream /api/run hiç çağrılmadı — ölçüm vakum")
                finally:
                    self._fail_sse(False)
                # EventSource kendi yeniden bağlanır: akış geri gelince canlı.
                self._wait_live(page, timeout=30000)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
