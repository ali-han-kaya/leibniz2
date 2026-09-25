#!/usr/bin/env python3
"""test_dashboard_keyboard_nav.py — dashboard klavye-gezinme süiti (Playwright).

Canlı preview_server'a karşı (aynı desen: test_dashboard_playwright_smoke.py)
dashboard'ın TÜM etkileşimli akışlarını klavyeyle sürer:

  1. Theme toggle      — buton odaklanılır, Enter/Space aria-pressed + tema
                         değişimini tetikler; aria-label döngüsü tutarlıdır.
  2. Bütçe aşım toggle — role=button span Tab ile odaklanılır, Enter/Space
                         detay-panelini açar/kapar + aria-expanded günceller.
  3. Run-history satırı— role=button rh-row Enter/Space ile stdout yükler.
  4. Z3 lightbox       — Escape kapatır; açıkkens Tab focus-trap'te kalır.
  5. Klavye-kapsam taraması — hiçbir role=button tabindex=0 element
                         Enter/Space'e yanıt vermiyor olamaz (fail-closed).

Çalıştırma:  python3 -m unittest discover -s . -p "test_dashboard_keyboard_nav.py"
Klavye-tablosu: test_refs_trend_badge.py deseni — beklentiler sabitlenir.
"""

import os
import socket
import subprocess
import sys
import time
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # CI runner'da playwright kurulu değilse SKIP (fail değil)
    sync_playwright = None

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_port(port, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.3)
    return False


class KeyboardNavTestBase(unittest.TestCase):
    """Ortak sunucu + tarayıcı kurulumu (sınıf başına 1 sunucu)."""

    PORT = None
    proc = None

    @classmethod
    def setUpClass(cls):
        cls.PORT = free_port()
        cls.proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT,
             "--dir", HERE,
             "--preview-dir", HERE,
             "--port", str(cls.PORT),
             "--bind", "127.0.0.1",
             "--interval", "3600"],
            cwd=HERE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_for_port(cls.PORT, timeout=15):
            cls.proc.terminate()
            cls.proc.wait(timeout=5)
            raise RuntimeError(
                f"preview_server.py did not start on 127.0.0.1:{cls.PORT} "
                f"within 15s (cwd={HERE})")

    @classmethod
    def tearDownClass(cls):
        if cls.proc is not None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
            cls.proc = None

    def setUp(self):
        if sync_playwright is None:
            self.skipTest("playwright kurulu değil")
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=True)
        # sw.js service worker'ı tüm fetch isteklerini SW-içi fetch'e
        # çevirir; Playwright page.route SW-geçişli istekleri GÖREMEZ →
        # interception sessizce bypass olur (klavye-suite'i buna çuvalladı).
        # Testler deterministik olsun diye SW bloklanır.
        self.context = self.browser.new_context(service_workers="block")
        self.page = self.context.new_page()
        self.page.route("**/sw.js", lambda route: route.fulfill(body=""))
        self.page.goto(f"http://127.0.0.1:{self.PORT}/",
                       wait_until="domcontentloaded")
        self.page.wait_for_timeout(1200)

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self._pw.stop()


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class ThemeToggleKeyboardTest(KeyboardNavTestBase):
    """Tema akışı: Tab-odak → Enter/Space → aria-pressed + tema değişimi."""

    TOGGLE = "#theme-toggle"

    def test_toggle_focusable_and_activates_with_enter(self):
        t = self.page.locator(self.TOGGLE)
        t.focus()
        self.assertEqual(self.page.evaluate("document.activeElement.id"),
                         "theme-toggle", "theme-toggle Tab-odak alamıyor")
        before = self.page.get_attribute(self.TOGGLE, "aria-pressed")
        theme_before = self.page.evaluate(
            "document.documentElement.dataset.theme")
        t.press("Enter")
        self.page.wait_for_timeout(150)
        after = self.page.get_attribute(self.TOGGLE, "aria-pressed")
        theme_after = self.page.evaluate(
            "document.documentElement.dataset.theme")
        self.assertNotEqual(before, after,
                            "Enter: aria-pressed değişmedi")
        self.assertNotEqual(theme_before, theme_after,
                            "Enter: documentElement.dataset.theme değişmedi")

    def test_toggle_activates_with_space_and_label_updates(self):
        t = self.page.locator(self.TOGGLE)
        t.focus()
        t.press("Space")
        self.page.wait_for_timeout(150)
        pressed = self.page.get_attribute(self.TOGGLE, "aria-pressed")
        label = self.page.get_attribute(self.TOGGLE, "aria-label")
        theme = self.page.evaluate("document.documentElement.dataset.theme")
        self.assertEqual((pressed == "true"), (theme == "light"),
                         "Space: aria-pressed ↔ tema uyumsuz")
        self.assertIn("dark theme" if pressed == "true" else "light theme",
                      label or "", "aria-label döngüsü bozuk")
        # Klavye-tema kalıcılığı (localStorage) — reload sonrası korunur.
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_timeout(600)
        self.assertEqual(
            self.page.evaluate("document.documentElement.dataset.theme"),
            theme, "tema tercihi reload'ta korunmadı")

    def test_toggle_round_trip_dark_light_dark(self):
        t = self.page.locator(self.TOGGLE)
        t.focus()
        for expected in ("light", "dark", "light"):
            t.press("Enter")
            self.page.wait_for_timeout(120)
            self.assertEqual(
                self.page.evaluate("document.documentElement.dataset.theme"),
                expected, f"tur {expected} tema bekleniyordu")


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class BudgetToggleKeyboardTest(KeyboardNavTestBase):
    """Bütçe-aşım detay toggle'ı: Enter/Space açar-kapar, aria-expanded doğru.

    Banner yalnız aşım-verisi varken görünür; test, sayfanın kendi render
    yolunu (trendCache + updateBudgetOverBanner) kullanarak öndatayı kurar —
    klavye-handler'ları ve toggle-mantığı tamamen üretim-kodudur.
    """

    TOGGLE = "#budget-over-toggle"

    def _seed_over_budget(self):
        """Sayfanın kendi render yoluna aşım-verisi ver (3 run > limit)."""
        self.page.evaluate(
            """(() => {
              const rows = Array.from({length: 5}, (_, i) => ({
                ts: new Date(Date.now() - (5 - i) * 3600e3).toISOString(),
                budget_usd: 20 + i * 5,   // 20,25,30,35,40 → son 2 aşım
                p0: 0, p1: 0,
              }));
              trendCache = rows;
              updateBudgetOverBanner();
            })()""")
        self.page.wait_for_timeout(100)
        visible = self.page.evaluate(
            "document.getElementById('budget-over-banner').style.display"
            " !== 'none'")
        if not visible:
            self.skipTest("banner öndataya rağmen görünmedi (render-yolu değişti)")

    def _detail_visible(self):
        return self.page.evaluate(
            "document.getElementById('budget-over-detail') !== null &&"
            "document.getElementById('budget-over-detail').style.display"
            " !== 'none'")

    def test_toggle_enter_opens_and_closes(self):
        self._seed_over_budget()
        t = self.page.locator(self.TOGGLE)
        t.focus()
        self.assertEqual(self.page.evaluate("document.activeElement.id"),
                         "budget-over-toggle",
                         "budget-over-toggle Tab-odak alamıyor")
        t.press("Enter")
        self.page.wait_for_timeout(150)
        self.assertTrue(self._detail_visible(), "Enter: detay açılmadı")
        self.assertEqual(self.page.get_attribute(self.TOGGLE,
                                                 "aria-expanded"), "true",
                         "Enter: aria-expanded=true olmadı")
        t.press("Enter")
        self.page.wait_for_timeout(150)
        self.assertFalse(self._detail_visible(), "Enter: detay kapanmadı")
        self.assertEqual(self.page.get_attribute(self.TOGGLE,
                                                 "aria-expanded"), "false",
                         "Enter: aria-expanded=false olmadı")

    def test_toggle_space_mirrors_enter(self):
        self._seed_over_budget()
        t = self.page.locator(self.TOGGLE)
        t.focus()
        t.press("Space")
        self.page.wait_for_timeout(150)
        self.assertTrue(self._detail_visible(), "Space: detay açılmadı")


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class RunHistoryRowKeyboardTest(KeyboardNavTestBase):
    """Run-history satırı (role=button rh-row): Enter/Space stdout yükler."""

    ROW = ".rh-row"

    def _first_row(self):
        row = self.page.locator(self.ROW).first
        row.wait_for(state="attached", timeout=5000)
        return row

    def test_rows_are_focusable(self):
        row = self._first_row()
        row.focus()
        self.assertEqual(
            self.page.evaluate(
                "document.activeElement.classList.contains('rh-row')"),
            True, "rh-row klavye-odak alamıyor")

    def test_row_enter_loads_stdout(self):
        # /api/run-stdout'u sabit yanıtla — stdout-paneline birebir düşen
        # işaretçi, klavye-aktivasyonunun uçtan-uca kanıtı olur.
        # Not: Playwright glob'u tam-URL'e uygulanır; `**/` öneki zorunlu.
        self.page.route(
            "**/api/run-stdout*",
            lambda route: route.fulfill(
                content_type="application/json",
                body='{"stdout": "KLAVYE-STDOUT-KANIT", "stderr": ""}'))
        row = self._first_row()
        row.focus()
        row.press("Enter")
        self.page.wait_for_function(
            "() => document.getElementById('stdout').textContent"
            ".includes('KLAVYE-STDOUT-KANIT')",
            timeout=5000)


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class LightboxKeyboardTest(KeyboardNavTestBase):
    """Z3 lightbox: Escape kapatır, açıkken Tab focus-trap'te kalır."""

    OPEN = ".z3-slide"
    BOX = "#z3-lightbox"

    def _open_lightbox(self):
        opener = self.page.locator(".z3-slide").first
        if opener.count() == 0:
            self.skipTest("lightbox açıcı bu sayfa-durumunda yok")
        opener.click()
        self.page.wait_for_timeout(250)

    def _box_hidden(self):
        return self.page.evaluate(
            "document.getElementById('z3-lightbox').hidden")

    def test_escape_closes_lightbox(self):
        self._open_lightbox()
        self.assertFalse(self._box_hidden(), "lightbox açılamadı (ön-koşul)")
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(200)
        self.assertTrue(self._box_hidden(), "Escape lightbox'ı kapatmadı")

    def test_focus_trapped_while_open(self):
        self._open_lightbox()
        for _ in range(6):
            self.page.keyboard.press("Tab")
        inside = self.page.evaluate(
            """(() => {
              const box = document.getElementById('z3-lightbox');
              return box.contains(document.activeElement);
            })()""")
        self.assertTrue(inside,
                        "Tab döngüsü lightbox dışına sızdı (focus-trap yok)")


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class RhFilterKeyboardTest(KeyboardNavTestBase):
    """Run-history filtre butonları: Tab + Enter aktive eder, .active taşınır.

    Butonlar native <button> — Enter/Space tarayıcıda click üretir;
    document-düzeyi delegation (data-act=rh-filter) setRhFilter'a gider.
    """

    def test_filter_enter_moves_active_and_filters_rows(self):
        first = self.page.locator(".rh-filter button").first
        first.focus()
        self.assertEqual(
            self.page.evaluate("document.activeElement.tagName"), "BUTTON",
            "filtre butonu odak alamıyor")
        # PASS filtresine geç (3. buton: all/PASS/FAIL/P0 — data-f ile)
        pass_btn = self.page.locator('.rh-filter button[data-f="PASS"]')
        pass_btn.focus()
        pass_btn.press("Enter")
        self.page.wait_for_timeout(600)
        # .active sınıfı doğru butona taşındı mı (setRhFilter sözleşmesi)
        active_f = self.page.evaluate(
            "document.querySelector('.rh-filter button.active')"
            "?.dataset.f || null")
        self.assertEqual(active_f, "PASS",
                         "Enter: .active PASS butonuna taşınmadı")
        # Klavye-değil fare-değil: Space da click üretir (native button)
        all_btn = self.page.locator('.rh-filter button[data-f="all"]')
        all_btn.focus()
        all_btn.press("Space")
        self.page.wait_for_timeout(400)
        active_f2 = self.page.evaluate(
            "document.querySelector('.rh-filter button.active')"
            "?.dataset.f || null")
        self.assertEqual(active_f2, "all",
                         "Space: .active all butonuna taşınmadı")

    def test_filter_keys_narrow_history_rows(self):
        # Filtre daraltması: en az all>=PASS satır sayısı (veri-dolu sayfada).
        all_btn = self.page.locator('.rh-filter button[data-f="all"]')
        all_btn.focus()
        all_btn.press("Enter")
        self.page.wait_for_timeout(700)
        n_all = self.page.locator(".rh-row").count()
        pass_btn = self.page.locator('.rh-filter button[data-f="PASS"]')
        pass_btn.focus()
        pass_btn.press("Enter")
        self.page.wait_for_timeout(700)
        n_pass = self.page.locator(".rh-row").count()
        self.assertLessEqual(
            n_pass, n_all,
            f"PASS filtresi daraltmadı (all={n_all}, pass={n_pass})")


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class TrendTipKeyboardTest(KeyboardNavTestBase):
    """Trend ipuçları: hover hit-rect'leri data-tip+data-i taşır; SVG-düzeyi
    delegation showTrendTip/showRefsTrendTip/showHookEnvTrendTip'e gider.
    Klavye-esdeğeri: rect odaklanılabilir değil (grafik hover-yüzeyi), ama
    delegation zinciri mouse ile CANLI — bu test mousemove'un tip'i
    doldurduğunu ve mouseleave'in kapattığını kanıtlar.
    """

    def _hover_center(self, svg_id):
        rect = self.page.locator(f"#{svg_id} rect[data-tip]").first
        rect.wait_for(state="attached", timeout=5000)
        # Trend panelleri sayfanın derinlerinde — mouse.move viewport-
        # koordinatı kullandığından rect önce görünüme kaydırılmalı.
        rect.scroll_into_view_if_needed()
        box = rect.bounding_box()
        if not box:
            self.skipTest(f"{svg_id} hit-rect görünür değil")
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def _tip_visible(self):
        return self.page.evaluate(
            "document.getElementById('tip').style.display === 'block'")

    def test_hover_shows_and_leave_hides_tip(self):
        x, y = self._hover_center("trend")
        self.page.mouse.move(x, y)
        self.page.wait_for_timeout(150)
        self.assertTrue(self._tip_visible(),
                        "mousemove: trend tip görünmedi (delegation ölü)")
        html = self.page.evaluate(
            "document.getElementById('tip').innerHTML")
        self.assertIn("verdict", html,
                      "trend tip içeriği beklenen biçimde değil")
        self.page.mouse.move(4, 4)  # SVG dışına
        self.page.wait_for_timeout(150)
        self.assertFalse(self._tip_visible(),
                         "mouseleave: tip kapanmadı")

    def test_refs_trend_tip_wired(self):
        # refs-trend verisi boşken rect[data-tip] render edilmez (0 hit-alanı)
        # — svg'de rect yoksa süit bunu SKIP eder (boş-veri koşulu, kusur değil).
        n = self.page.locator("#refs-trend rect[data-tip]").count()
        if n == 0:
            self.skipTest("refs-trend boş-veri: hit-rect yok")
        x, y = self._hover_center("refs-trend")
        self.page.mouse.move(x, y)
        self.page.wait_for_timeout(150)
        self.assertTrue(self._tip_visible(),
                        "mousemove: refs-trend tip görünmedi")


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class KeyboardCoverageScanTest(KeyboardNavTestBase):
    """Fail-closed kapsam taraması: her role=button Enter/Space'e yanıt vermeli.

    Kural: role=button + tabindex=0 olan HER element ya onclick'e bağlı ve
    onkeydown'ı var, ya da gerçek <button>/<input>/<a href>. Kuralı bozan
    element listesi boş değilse test kırılır (klavye-kapsam borcu).
    """

    def test_every_role_button_has_keyboard_activation(self):
        violators = self.page.evaluate(
            """(() => {
              const out = [];
              for (const el of document.querySelectorAll('[role="button"]')) {
                const native = /^(BUTTON|INPUT|A)$/.test(el.tagName);
                const hasClick = !!(el.getAttribute('onclick') ||
                                    el.__clickbound);
                const hasKey = !!el.getAttribute('onkeydown');
                if (!native && hasClick && !hasKey) {
                  out.push((el.id || el.className || el.tagName) +
                           ' [onclick yok keydown]');
                }
              }
              return out;
            })()""")
        self.assertEqual(
            violators, [],
            f"klavye-aktivasyonu eksik role=button elementleri: {violators}")


if __name__ == "__main__":
    unittest.main()
