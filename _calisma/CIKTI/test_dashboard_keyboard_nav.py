#!/usr/bin/env python3
# SECURITY-TIER: browser
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

import json
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

# Dashboard satır şekli, ÜRETİM okuyucularıyla birebir (`preview.js`):
# `loadRunHistory()` → verdict/p0/p1/ts/duration_s/budget_usd/source,
# `renderTrend()` → + budget_limit/z3_total, `renderRefsTrend()` → + refs_*.
# 3 PASS + 1 FAIL + 1 P0 → PASS filtresi GERÇEKTEN daraltır; hepsi PASS
# olsaydı `n_pass <= n_all` boşuna geçerdi.
DASHBOARD_ROW_SEED = [
    {"ts": "2026-09-30T09:00:00Z", "verdict": "PASS", "p0": 0, "p1": 0,
     "duration_s": 12.0, "budget_usd": 1.5, "budget_limit": 5.0,
     "z3_total": 120, "refs_total": 43, "refs_verified": 43, "source": "seed"},
    {"ts": "2026-09-30T10:00:00Z", "verdict": "PASS", "p0": 0, "p1": 1,
     "duration_s": 14.0, "budget_usd": 2.5, "budget_limit": 5.0,
     "z3_total": 118, "refs_total": 43, "refs_verified": 42, "source": "seed"},
    {"ts": "2026-09-30T11:00:00Z", "verdict": "PASS", "p0": 0, "p1": 0,
     "duration_s": 11.0, "budget_usd": 1.0, "budget_limit": 5.0,
     "z3_total": 121, "refs_total": 43, "refs_verified": 43, "source": "seed"},
    {"ts": "2026-09-30T12:00:00Z", "verdict": "FAIL", "p0": 0, "p1": 2,
     "duration_s": 31.0, "budget_usd": 9.0, "budget_limit": 5.0,
     "z3_total": 90, "refs_total": 43, "refs_verified": 40, "source": "seed"},
    {"ts": "2026-09-30T13:00:00Z", "verdict": "PASS", "p0": 2, "p1": 0,
     "duration_s": 22.0, "budget_usd": 4.0, "budget_limit": 5.0,
     "z3_total": 110, "refs_total": 43, "refs_verified": 43, "source": "seed"},
]

# Chrome'un CSP ihlali mesajları — nitelik-handler reddi tam olarak bu kalıpla
# gelir (VERIFY-001: `onmousemove="…"` CSP altında SESSİZCE ölür; görünür hata
# yok, yalnız konsolda bir ret satırı). Bu yüzden konsol sayacı şart.
CSP_VIOLATION_MARKERS = (
    "Content Security Policy",
    "Refused to execute inline event handler",
    "Refused to apply inline style",
)


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


def keyboard_scope_verdict(scanned, violators):
    """Klavye-kapsam taramasının fail-closed hükmü.

    0 element taramak "sorun yok" değil "tarama yok" demektir: seçici
    bozulursa (role=button yeniden adlandırılır, sayfa boş render edilir)
    test boş bir liste üzerinde sessizce yeşil kalırdı. Bu yüzden tarama
    önce POZİTİF bir element sayısı kanıtlamalıdır. Saf fonksiyon: gerçek
    tarayıcı olmadan meta-kapı da aynı hükmü koşturur.
    """
    if scanned <= 0:
        raise AssertionError(
            "klavye-kapsam taraması 0 role=button gördü — tarama boş "
            "(fail-closed); seçici/sayfa render'ı bozulmuş olabilir")
    return violators


class KeyboardScopeGuardTest(unittest.TestCase):
    """TARAYICISIZ katman: kapsam taramasının 0-element hükmü.

    Chromium olmayan bir ortamda aşağıdaki Playwright sınıfları skip olur;
    bu sınıf her ortamda koşar ve guard kaldırılırsa kırmızıya düşer
    ("keşfedildi, atlandı, yeşil" zincirini kapatır).
    """

    def test_zero_element_scan_is_fail_closed(self):
        with self.assertRaisesRegex(AssertionError, "0 role=button"):
            keyboard_scope_verdict(0, [])

    def test_positive_scan_preserves_violators(self):
        self.assertEqual(keyboard_scope_verdict(3, ["eksik"]), ["eksik"])


class KeyboardNavTestBase(unittest.TestCase):
    """Ortak sunucu + tarayıcı kurulumu (sınıf başına 1 sunucu)."""

    PORT = None
    proc = None

    @classmethod
    def setUpClass(cls):
        cls.PORT = free_port()
        # Izolasyon: sunucunun YAZDIĞI dosyalar (history.jsonl,
        # runs/, logs/) geçici dizine gider; preview.html okuması
        # repo dizininden kalır — test ağacı temiz kalır.
        if HERE not in sys.path:  # yardımcı modül CIKTI içinde
            sys.path.insert(0, HERE)
        from preview_test_env import runtime_args
        cls.proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT,
             "--dir", HERE,
             "--preview-dir", HERE,
             *runtime_args("keyboard-nav"),
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
        # CSP ihlalleri yalnız konsolda görünür → suite boyunca toplanır.
        # Bu sayaç olmadan "delege çalışıyor" kanıtı, "konsolda CSP reddi
        # yok" iddiasını kanıtlamaz (VERIFY-001'in yarısı eksik kalır).
        self.console = []
        self.errors = []
        self.page.on("console", lambda m: self.console.append(
            "%s: %s" % (m.type, m.text)))
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.response = self.page.goto(f"http://127.0.0.1:{self.PORT}/",
                                       wait_until="domcontentloaded")
        self.page.wait_for_timeout(1200)

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self._pw.stop()

    # ------------------------------------------------------------- yardımcılar
    def _seed_run_history(self, rows=None):
        """Run-history satırlarını ÜRETİM yolundan besle.

        `.rh-row` yalnız `loadRunHistory()` → `/api/run-history` → innerHTML
        zinciriyle doğar. O uç nokta `history.jsonl`'i okur; `history.jsonl`
        çalışma zamanı verisidir (gitignored) → temiz klonda ve CI'da YOKTUR.
        Satırları beklerken bu suite sessizce "0 satır" ölçerdi: `wait_for
        (attached)` zaman aşımı → hata, filtre testi `0 <= 0` ile boşuna
        geçerdi. Aynı gerekçeyle `test_surface_cwv_report.py` SKIP eder;
        burada ölçülecek şey üretim render yolu olduğu için ÖN DATA ÜRETİLİR
        (intercept + reload) — test her ortamda gerçekten bir şey ölçer.
        """
        payload = json.dumps(DASHBOARD_ROW_SEED if rows is None else rows)
        self.page.route("**/api/run-history*",
                        lambda route: route.fulfill(
                            content_type="application/json", body=payload))
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_timeout(600)

    def _seed_trend(self, rows=None):
        """Trend grafiklerini ÜRETİM yolundan besle (`/api/trend` → loadTrend).

        `renderTrend()` veri yoksa `svg.innerHTML = ""` yapar → `#trend`
        içinde `rect[data-tip]` hiç oluşmaz. Aynı gerekçe: `/api/trend` de
        `history.jsonl`'den beslenir, temiz klonda boş döner. Kardeş test
        (`test_refs_trend_tip_wired`) boş-veri hâlinde SKIP ediyordu; burada
        veri tohumlanır ki delegation zinciri gerçekten ölçülsün.
        """
        payload = json.dumps(
            {"history": DASHBOARD_ROW_SEED if rows is None else rows,
             "dbRows": []})
        self.page.route("**/api/trend*",
                        lambda route: route.fulfill(
                            content_type="application/json", body=payload))
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_timeout(600)

    def _csp_header(self):
        return (self.response.headers.get("content-security-policy") or "") \
            if self.response is not None else ""

    def _csp_violations(self):
        return [line for line in (self.console + self.errors)
                if any(m in line for m in CSP_VIOLATION_MARKERS)]

    def _inline_handlers_in_live_dom(self):
        """Canlı DOM'da (üretilen markup dahil) `on*` nitelik-handler taraması.

        Statik tarama runtime-üretilen SVG rect'lerini göremez; burada
        sayfanın kendi render yolu çalıştırıldıktan sonra bakılır.
        """
        return self.page.evaluate(
            """(() => {
              const out = [];
              for (const el of document.querySelectorAll('*')) {
                for (const a of el.attributes) {
                  if (/^on[a-z]+$/.test(a.name)) {
                    out.push(el.tagName + '[' + a.name + '=' +
                             JSON.stringify(a.value.slice(0, 40)) + ']');
                  }
                }
              }
              return out;
            })()""")


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class ThemeToggleKeyboardTest(KeyboardNavTestBase):
    """Tema akışı: Tab-odak → Enter/Space → aria-pressed + tema değişimi."""

    TOGGLE = "#theme-toggle"

    def _seed_theme(self, preference):
        """Başlangıç tercihini SABİTLE: saklı palet ya da anahtarı sil (auto).

        Aksi halde ilk durum ortamın `prefers-color-scheme`ine bağlıdır ve
        "auto → sistem" adımı farklı CI makinelerinde farklı palet üretir.
        """
        self.page.emulate_media(color_scheme="dark")
        self.page.evaluate("() => localStorage.removeItem('dashboard-theme')")
        if preference != "auto":
            self.page.evaluate(
                "(t) => localStorage.setItem('dashboard-theme', t)", preference)
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_timeout(400)

    def test_toggle_focusable_and_activates_with_enter(self):
        self._seed_theme("dark")
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
        self._seed_theme("dark")
        t = self.page.locator(self.TOGGLE)
        t.focus()
        t.press("Space")
        self.page.wait_for_timeout(150)
        pressed = self.page.get_attribute(self.TOGGLE, "aria-pressed")
        label = self.page.get_attribute(self.TOGGLE, "aria-label")
        state = self.page.evaluate(
            "() => ({ theme: document.documentElement.dataset.theme,"
            "         pref: document.documentElement.dataset.themePreference })")
        theme, pref = state["theme"], state["pref"]
        self.assertEqual((pressed == "true"), (theme == "light"),
                         "Space: aria-pressed ↔ tema uyumsuz")
        # Tema kümesi: auto · dark · light · stripe · vercel — hem erişilebilir
        # ad (aria-label) hem görünür etiket güncel SEÇİMİ yazmalı. auto bir
        # palet değil; adı uygulanan paleti parantez içinde taşır.
        expected_label = ("auto (%s)" % theme) if pref == "auto" else pref
        self.assertIn("current: %s" % expected_label, label or "",
                      "aria-label döngüsü bozuk")
        expected_text = ("auto: %s" % theme) if pref == "auto" else {
            "dark": "dark mode", "light": "light mode",
            "stripe": "stripe theme", "vercel": "vercel theme"}[pref]
        self.assertEqual(
            self.page.locator(self.TOGGLE).inner_text().strip(),
            expected_text, "görünür etiket seçimle uyumsuz")
        # Klavye-tema kalıcılığı (localStorage) — reload sonrası korunur.
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_timeout(600)
        self.assertEqual(
            self.page.evaluate("document.documentElement.dataset.theme"),
            theme, "tema tercihi reload'ta korunmadı")

    def test_toggle_round_trip_dark_light_stripe_vercel_auto_dark(self):
        """Döngü 5 adım: light → stripe → vercel → auto → dark.

        auto adımında UYGULANAN palet sistem tercihidir (burada dark'a
        emüle edildi) ama SEÇİM auto'dur; tercih anahtarı silinir.
        """
        self._seed_theme("dark")
        t = self.page.locator(self.TOGGLE)
        t.focus()
        for expected in ("light", "stripe", "vercel", "auto", "dark"):
            t.press("Enter")
            self.page.wait_for_timeout(120)
            state = self.page.evaluate(
                "() => ({ theme: document.documentElement.dataset.theme,"
                "         pref: document.documentElement.dataset.themePreference,"
                "         stored: localStorage.getItem('dashboard-theme') })")
            self.assertEqual(state["pref"], expected,
                             f"tur {expected}: seçim bekleniyordu")
            applied = "dark" if expected == "auto" else expected
            self.assertEqual(state["theme"], applied,
                             f"tur {expected}: uygulanan palet bekleniyordu")
            if expected == "auto":
                self.assertIsNone(state["stored"],
                                  "auto seçimi tercih anahtarını SİLMELİ")
            else:
                self.assertEqual(state["stored"], expected,
                                 "palet seçimi saklanmalı")


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
        self._seed_run_history()
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
        self._seed_run_history()
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
        # Filtre daraltması: all >= PASS satır sayısı. Tohum veri karışık
        # (3 PASS / 1 FAIL / 1 P0) olduğu için PASS gerçekten daraltır;
        # `all` hepsini gösterir.
        self._seed_run_history()
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
        # Önce satır var mı? Yoksa `0 <= 0` her zaman geçer ve test hiçbir
        # şey ölçmeden yeşil görünür (sessiz boşuna-geçme).
        self.assertGreater(n_all, 0,
                           "tohum satırları render edilmedi — all=0")
        self.assertLess(
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
        self._seed_trend()
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
        # Veri tohumlandığı için normalde SKIP'e düşmez; guard yine de duruyor
        # (render yolu değişirse sessizce yeşile çevirmesin).
        self._seed_trend()
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
        scan = self.page.evaluate(
            """(() => {
              const nodes = document.querySelectorAll('[role="button"]');
              const out = [];
              for (const el of nodes) {
                const native = /^(BUTTON|INPUT|A)$/.test(el.tagName);
                const hasClick = !!(el.getAttribute('onclick') ||
                                    el.__clickbound);
                const hasKey = !!el.getAttribute('onkeydown');
                if (!native && hasClick && !hasKey) {
                  out.push((el.id || el.className || el.tagName) +
                           ' [onclick yok keydown]');
                }
              }
              return {scanned: nodes.length, violators: out};
            })()""")
        self.assertEqual(
            keyboard_scope_verdict(scan["scanned"], scan["violators"]), [],
            "klavye-aktivasyonu eksik role=button elementleri: %s"
            % scan["violators"])


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class DelegatedSurfacesUnderCSPTest(KeyboardNavTestBase):
    """VERIFY-001'in TIKLAMA yarısı: delege yüzeyler CSP altında canlı kanıtı.

    Hover yarısı `test_preview_hover_tooltip.py`'de kanıtlanmıştı; aynı sınıfın
    tıklama/klavye yarısı (data-act=rh-filter / budget-toggle / load-stdout)
    burada kanıtlanır. Kendi başına "tıklama işe yarıyor" yetmez: asıl iddia
    "CSP altında işe yarıyor ve konsolda ret yok" — üç test bunu böler:
    (1) sayfa gerçekten sıkı CSP ile servis ediliyor mu (kapı-önce),
    (2) canlı DOM'da (runtime-üretilen markup dahil) hiç inline handler var mı,
    (3) gerçek fare tıklaması durumu değiştiriyor mu + 0 CSP ihlali.
    """

    def _seed_generated_markup(self):
        """Runtime-üretilen yüzeyleri (SVG hit-alanları) oluştur."""
        self.page.evaluate(
            """(() => {
              const rows = Array.from({length: 3}, (_, i) => ({
                ts: new Date(Date.now() - (3 - i) * 3600e3).toISOString(),
                refs_verified: 10 + i, refs_total: 40, refs_mismatch: 0,
                verdict: "PASS", p0: 0, p1: 0,
              }));
              renderRefsTrend(rows);
            })()""")
        self.page.wait_for_timeout(120)

    def test_page_is_served_under_strict_csp(self):
        """Kapı-önce: CSP yoksa/gevşekse aşağıdaki kanıtlar değersiz olurdu."""
        csp = self._csp_header()
        self.assertTrue(csp, "yanıt Content-Security-Policy başlığı taşımıyor")
        self.assertIn("script-src 'self'", csp)
        self.assertIn("'nonce-", csp)
        script_src = csp.split("script-src", 1)[1].split(";", 1)[0]
        self.assertNotIn("unsafe-inline", script_src,
                         "script-src gevşek — CSP kanıtı geçersiz olur")

    def test_live_dom_has_no_inline_event_handlers(self):
        """Canlı DOM (üretilen markup dahil) inline handler taşımamalı."""
        self._seed_generated_markup()
        offenders = self._inline_handlers_in_live_dom()
        self.assertEqual(
            offenders, [],
            "canlı DOM'da inline handler var — CSP altında SESSİZCE ölür: %s"
            % offenders[:5])
        # Delege yüzeyleri data-act taşımalı (nitelik değil, veri).
        acts = self.page.evaluate(
            "[...document.querySelectorAll('[data-act]')]"
            ".map(e => e.dataset.act).sort()")
        for expected in ("budget-toggle", "rh-filter"):
            self.assertIn(expected, acts,
                          "delege yüzeyi kaybolmuş: data-act=%s" % expected)

    def test_real_click_on_delegated_filter_filters_rows_without_csp_violation(self):
        """Gerçek fare tıklaması → delege çalışır + konsolda ret yok."""
        pass_btn = self.page.locator('.rh-filter button[data-f="PASS"]')
        pass_btn.click()
        self.page.wait_for_timeout(400)
        active = self.page.evaluate(
            "document.querySelector('.rh-filter button.active')?.dataset.f"
            " || null")
        self.assertEqual(active, "PASS",
                         "tıklama .active'i PASS butonuna taşımadı — "
                         "data-act delegation ölü")
        all_btn = self.page.locator('.rh-filter button[data-f="all"]')
        all_btn.click()
        self.page.wait_for_timeout(300)
        self.assertEqual(
            self.page.evaluate(
                "document.querySelector('.rh-filter button.active')?.dataset.f"
                " || null"),
            "all", "geri dönüş tıklaması çalışmadı")
        violations = self._csp_violations()
        self.assertEqual(violations, [],
                         "tıklama sırasında CSP ihlali: %s" % violations[:5])

    def test_real_click_on_delegated_budget_toggle_without_csp_violation(self):
        """Aynı sınıfın ikinci yüzeyi: banner toggle'ı gerçek tıklamayla."""
        self.page.evaluate(
            """(() => {
              trendCache = Array.from({length: 5}, (_, i) => ({
                ts: new Date(Date.now() - (5 - i) * 3600e3).toISOString(),
                budget_usd: 20 + i * 5, p0: 0, p1: 0,
              }));
              updateBudgetOverBanner();
            })()""")
        self.page.wait_for_timeout(120)
        if self.page.evaluate(
                "document.getElementById('budget-over-banner').style.display") \
                == "none":
            self.skipTest("banner öndataya rağmen görünmedi (render-yolu değişti)")
        toggle = self.page.locator("#budget-over-toggle")
        toggle.click()
        self.page.wait_for_timeout(150)
        self.assertEqual(self.page.get_attribute("#budget-over-toggle",
                                                 "aria-expanded"), "true",
                         "gerçek tıklama aria-expanded'ı açmadı")
        self.assertEqual(self._csp_violations(), [],
                         "banner toggle'ında CSP ihlali")


EQ_SEED = [
    {"title": "Denklem A", "png": "a.png", "source_lines": [10, 12],
     "pixel_width": 100, "pixel_height": 20},
    {"title": "Denklem B", "png": "b.png", "source_lines": [20, 22],
     "pixel_width": 100, "pixel_height": 20},
    {"title": "Denklem C", "png": "c.png", "source_lines": [30, 32],
     "pixel_width": 100, "pixel_height": 20},
]


class InteractionSurfaceGuardTest(unittest.TestCase):
    """TARAYICISIZ katman: tab + denklem galerisi etkileşim sözleşmesi.

    Chromium yokken aşağıdaki Playwright sınıfları skip olur; bu sınıf her
    ortamda koşar. Kaynakta hedef kimlik/handler kalmazsa kırmızıya düşer.
    """

    def _read(self, name):
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            return f.read()

    def test_tab_and_gallery_hooks_exist(self):
        html = self._read("preview.html")
        js = self._read("preview.js")
        for needle in ('id="tab-equations"', 'aria-controls="view-equations"',
                       'id="view-equations"', 'id="eq-lightbox"',
                       'id="eq-prev"', 'id="eq-next"', 'id="eq-close"'):
            self.assertIn(needle, html, "preview.html eksik: %s" % needle)
        for needle in ('card.addEventListener("click", () => open(i));',
                       'tab.addEventListener("click"',
                       '"ArrowRight"', '"Home"', '"End"'):
            self.assertIn(needle, js, "preview.js eksik: %s" % needle)


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class DashboardTabsInteractionTest(KeyboardNavTestBase):
    """Dashboard sekmeleri (APG tablist): fare tıklaması + ok/Home/End."""

    def _attr(self, sel, name):
        return self.page.get_attribute(sel, name)

    def test_mouse_click_switches_view(self):
        self.page.locator("#tab-equations").click()
        self.page.wait_for_timeout(150)
        self.assertEqual(self._attr("#tab-equations", "aria-selected"), "true")
        self.assertEqual(self._attr("#tab-panel", "aria-selected"), "false")
        self.assertTrue(self.page.locator("#view-equations").is_visible(),
                        "tıklama denklem görünümünü açmadı")
        self.assertTrue(self.page.locator("#view-panel").is_hidden(),
                        "tıklama ana paneli gizlemedi")

    def test_arrow_home_end_move_selection_and_focus(self):
        self.page.locator("#tab-panel").focus()
        self.page.keyboard.press("ArrowRight")
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.evaluate("document.activeElement.id"),
                         "tab-equations", "ArrowRight odağı taşımadı")
        self.assertEqual(self._attr("#tab-equations", "aria-selected"), "true")
        self.assertEqual(self._attr("#tab-equations", "tabindex"), "0")
        self.assertEqual(self._attr("#tab-panel", "tabindex"), "-1")
        self.page.keyboard.press("ArrowRight")  # sarmalama: son -> ilk
        self.assertEqual(self.page.evaluate("document.activeElement.id"),
                         "tab-panel", "ArrowRight sarmalamadı")
        self.page.keyboard.press("End")
        self.assertEqual(self.page.evaluate("document.activeElement.id"),
                         "tab-equations", "End son sekmeye gitmedi")
        self.page.keyboard.press("Home")
        self.assertEqual(self.page.evaluate("document.activeElement.id"),
                         "tab-panel", "Home ilk sekmeye gitmedi")


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class EquationGalleryInteractionTest(KeyboardNavTestBase):
    """Denklem galerisi: kart tıklaması, lightbox klavyesi, hover, odak."""

    def setUp(self):
        super().setUp()
        payload = json.dumps({"source_sha256": "ab" * 32,
                              "equations": EQ_SEED})
        self.page.route("**/api/equations*",
                        lambda route: route.fulfill(
                            content_type="application/json", body=payload))
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_timeout(500)
        self.page.locator("#tab-equations").click()
        self.page.locator(".eq-card").first.wait_for(state="visible",
                                                     timeout=5000)

    def _title(self):
        return self.page.text_content("#eq-lightbox-title")

    def test_mouse_click_opens_lightbox_for_clicked_card(self):
        self.page.locator(".eq-card").nth(1).click()
        self.page.wait_for_timeout(120)
        self.assertFalse(self.page.locator("#eq-lightbox").is_hidden(),
                         "kart tıklaması lightbox'ı açmadı")
        self.assertEqual(self._title(), EQ_SEED[1]["title"])
        self.assertEqual(self.page.evaluate("document.activeElement.id"),
                         "eq-close", "açılışta odak kapat düğmesinde değil")

    def test_buttons_and_arrows_navigate_with_wrap(self):
        self.page.locator(".eq-card").nth(0).click()
        self.page.locator("#eq-next").click()
        self.assertEqual(self._title(), EQ_SEED[1]["title"])
        self.page.keyboard.press("ArrowLeft")
        self.assertEqual(self._title(), EQ_SEED[0]["title"])
        self.page.keyboard.press("ArrowLeft")  # sarmalama: ilk -> son
        self.assertEqual(self._title(), EQ_SEED[2]["title"])
        self.page.locator("#eq-prev").click()
        self.assertEqual(self._title(), EQ_SEED[1]["title"])
        self.page.keyboard.press("ArrowRight")
        self.assertEqual(self._title(), EQ_SEED[2]["title"])

    def test_escape_closes_and_restores_focus_to_card(self):
        self.page.locator(".eq-card").nth(2).click()
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(120)
        self.assertTrue(self.page.locator("#eq-lightbox").is_hidden(),
                        "Escape lightbox'ı kapatmadı")
        focused = self.page.evaluate("document.activeElement.textContent")
        self.assertIn(EQ_SEED[2]["title"], focused,
                      "kapanışta odak açan karta dönmedi")

    def test_backdrop_click_closes(self):
        self.page.locator(".eq-card").nth(0).click()
        self.page.locator("#eq-lightbox").click(position={"x": 4, "y": 4})
        self.page.wait_for_timeout(120)
        self.assertTrue(self.page.locator("#eq-lightbox").is_hidden(),
                        "arka plan tıklaması lightbox'ı kapatmadı")

    def test_tab_focus_stays_inside_dialog(self):
        self.page.locator(".eq-card").nth(0).click()
        inside = {"eq-prev", "eq-next", "eq-close"}
        for _ in range(5):
            self.page.keyboard.press("Tab")
            active = self.page.evaluate("document.activeElement.id")
            self.assertIn(active, inside, "Tab diyalogdan sızdı: %s" % active)

    def test_hover_changes_card_shadow(self):
        card = self.page.locator(".eq-card").nth(0)
        before = card.evaluate("el => getComputedStyle(el).boxShadow")
        card.hover()
        self.page.wait_for_timeout(150)
        after = card.evaluate("el => getComputedStyle(el).boxShadow")
        self.assertNotEqual(before, after,
                            "kart hover'da gölge değiştirmedi (:hover kuralı ölü)")


if __name__ == "__main__":
    unittest.main()
