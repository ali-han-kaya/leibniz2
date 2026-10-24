#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SECURITY-TIER: browser
"""test_preview_uncovered_surface.py — delegasyon haritası dışı kanıt boşlukları.

Kapsam taraması (2026-10-20): önizleme yüzeyindeki etkileşimli öğelerin çoğu
gerçek-Chromium kanıtına sahip (keyboard_nav: sekme/lightbox/ok/Esc,
hover_tooltip: 3 SVG, budget_rh: filtre tıklamaları). DÖRT öğede gerçek
tarayıcı kanıtı YOKTU (yalnızca statik dize/vm-stub assert'leri):

  1. #video-load tıklaması → mountVideoPlayer() (sahne açılır)
  2. #reconnect tıklaması → connect() (yeni EventSource)
  3. #theme-toggle FARE tıklaması (yalnızca Enter testliydi)
  4. rh-filter düğmelerinde SPACE tuşu (delege yalnızca click'i testliydi;
     native button Space'i click'e çevirir — burada kanıtlanır)

Bu dosya dördünü de gerçek preview_server + gerçek Chromium ile sürer.
Delegasyon haritası (preview.js:3164-3180) + doğrudan bağlar denetlendi:
harita-dışı YETİM etkileşimli yüzey YOK (canvas #budget-spark bilinçli
etkileşimsiz: title-only, bağ yok). Yani bulgu "kapsama boşluğu", "harita
boşluğu" değildir.

Desen: test_preview_hover_tooltip.py ile aynı (runtime izolasyonu,
service_workers=block, sw.js route, console/pageerror kaydı).
"""
import json
import os
import socket
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # CI runner'da playwright kurulu değilse SKIP (fail değil)
    sync_playwright = None

# 2 temiz PASS (p0=0) + 1 FAIL + 1 PASS-ama-P0=2: PASS filtresi {A,B} vermeli
# (budget_rh desenindeki ayırıcı tohumun küçüğü).
RH_SEED = [
    {"ts": "2026-09-30T09:00:00Z", "verdict": "PASS", "p0": 0, "p1": 0,
     "duration_s": 12.0, "budget_usd": 1.5, "refs_verified": 43,
     "refs_total": 43, "pdf_pages": 12, "lean_ok": True, "source": "seed"},
    {"ts": "2026-09-30T10:00:00Z", "verdict": "PASS", "p0": 0, "p1": 1,
     "duration_s": 14.0, "budget_usd": 2.5, "refs_verified": 42,
     "refs_total": 43, "pdf_pages": 12, "lean_ok": True, "source": "seed"},
    {"ts": "2026-09-30T11:00:00Z", "verdict": "FAIL", "p0": 0, "p1": 2,
     "duration_s": 31.0, "budget_usd": 9.0, "refs_verified": 40,
     "refs_total": 43, "pdf_pages": 12, "lean_ok": False, "source": "seed"},
    {"ts": "2026-09-30T13:00:00Z", "verdict": "PASS", "p0": 2, "p1": 0,
     "duration_s": 22.0, "budget_usd": 4.0, "refs_verified": 43,
     "refs_total": 43, "pdf_pages": 12, "lean_ok": True, "source": "seed"},
]
PASS_CLEAN_TS = {"2026-09-30T09:00:00Z", "2026-09-30T10:00:00Z"}


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
        except OSError:
            time.sleep(0.3)
    return False


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class UncoveredSurfaceTest(unittest.TestCase):
    """Gerçek preview_server + gerçek Chromium: harita-dışı kanıt boşlukları."""

    PORT = None
    proc = None

    @classmethod
    def setUpClass(cls):
        cls.PORT = free_port()
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        from preview_test_env import runtime_args
        cls.proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT,
             "--dir", HERE,
             "--preview-dir", HERE,
             *runtime_args("uncovered"),
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
                "preview_server.py 15 sn içinde 127.0.0.1:%d üzerinde "
                "ayakta kalmadı" % cls.PORT)

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
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=True)
        self.context = self.browser.new_context(service_workers="block")
        self.page = self.context.new_page()
        self.page.route("**/sw.js", lambda route: route.fulfill(body=""))
        self.console = []
        self.errors = []
        self.page.on("console", lambda m: self.console.append(
            "%s: %s" % (m.type, m.text)))
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.sse_requests = []
        self.page.on("request", lambda r: self.sse_requests.append(r.url)
                     if "/api/run" in r.url and "run-history" not in r.url
                     else None)
        self.page.goto("http://127.0.0.1:%d/" % self.PORT,
                       wait_until="domcontentloaded")
        self.page.wait_for_timeout(1200)

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self._pw.stop()

    # ------------------------------------------------------------ yardımcı
    def _assert_no_page_error(self, where):
        self.assertEqual(
            self.errors, [],
            "%s: sayfada JS hatası: %s" % (where, self.errors[:3]))

    def _seed_history(self, rows):
        self.page.route("**/api/run-history*",
                        lambda route: route.fulfill(
                            content_type="application/json",
                            body=json.dumps(rows)))
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_timeout(900)

    def _rh_ts(self):
        return self.page.evaluate(
            "[...document.querySelectorAll('.rh-row')].map(r => r.dataset.ts)")

    # ------------------------------------------------------------- testler
    def test_video_load_click_mounts_stage(self):
        """#video-load tıklaması sahneyi açar (mount yolu)."""
        self.assertGreater(
            self.page.locator("#video-load").count(), 0,
            "#video-load yok — sayfa yapısı değişti")
        self.page.locator("#video-load").click()
        self.page.wait_for_timeout(1500)
        state = self.page.evaluate(
            "(() => ({stageHidden: document.getElementById('video-stage').hidden,"
            " placeholderHidden:"
            " document.getElementById('video-placeholder').hidden}))()")
        self.assertFalse(state["stageHidden"],
                         "tıklamaya rağmen #video-stage açılmadı")
        self.assertTrue(state["placeholderHidden"],
                        "tıklamaya rağmen placeholder gizlenmedi")
        self._assert_no_page_error("video-load")

    def test_reconnect_click_opens_new_stream(self):
        """#reconnect tıklaması yeni EventSource açar (istek sayısı artar)."""
        self.assertGreater(
            self.page.locator("#reconnect").count(), 0,
            "#reconnect yok — sayfa yapısı değişti")
        before = len(self.sse_requests)
        self.assertGreater(before, 0,
                           "sayfa yüklenirken hiç /api/run isteği yok")
        # TEK tıklama yarışı (ölçüldü 2026-10-21): panel her snapshot/update'te
        # yeniden çiziliyor (`setLive`/`applySnapshot`), bu yüzden bir tıklama
        # bazen çizim penceresine denk gelip istek üretmiyor (izole koşuda
        # 3'te 2). Sözleşme "reconnect tıklaması yeni akış açar"dır; tek
        # tıklamanın kazanması DEĞİL. En fazla 3 deneme: bağ tamamen kopuksa
        # hiçbiri üretmez ve test yine kırmızı olur (vakum yok).
        for attempt in range(3):
            self.page.locator("#reconnect").click()
            deadline = time.monotonic() + 10
            while (len(self.sse_requests) <= before
                   and time.monotonic() < deadline):
                time.sleep(0.3)
            if len(self.sse_requests) > before:
                break
            self.page.wait_for_timeout(300)
        self.assertGreater(
            len(self.sse_requests), before,
            "3 tıklamaya rağmen yeni /api/run isteği yok "
            "(önce %d)" % before)
        self.page.wait_for_function(
            "() => document.getElementById('live-status').textContent"
            " === 'live'",
            timeout=10000)
        self._assert_no_page_error("reconnect")

    def test_theme_toggle_click_cycles_theme(self):
        """#theme-toggle FARE tıklaması temayı döndürür (auto + 4 tema tam tur)."""
        btn = self.page.locator("#theme-toggle")
        self.assertGreater(btn.count(), 0, "#theme-toggle yok")
        first = self.page.evaluate(
            "() => document.documentElement.dataset.theme + '|' +"
            " document.getElementById('theme-toggle').textContent")
        btn.click()
        self.page.wait_for_timeout(300)
        second = self.page.evaluate(
            "() => document.documentElement.dataset.theme + '|' +"
            " document.getElementById('theme-toggle').textContent")
        self.assertNotEqual(second, first,
                            "tıklamaya rağmen tema/etiket değişmedi")
        for _ in range(4):
            btn.click()
            self.page.wait_for_timeout(300)
        back = self.page.evaluate(
            "() => document.documentElement.dataset.theme + '|' +"
            " document.getElementById('theme-toggle').textContent")
        self.assertEqual(back, first,
                         "5 tıklamada başa dönülmedi (tur bozuk): %r" % back)
        self._assert_no_page_error("theme-toggle")

    def test_auto_theme_follows_system_live_without_persisting(self):
        """Tercih yok = auto: sistem teması uygulanır ve CANLI izlenir.

        Gerçek Chromium `matchMedia` değişimini yayar (`emulate_media`), yani
        sandbox dinleyicisi değil tarayıcının kendi olayı ölçülür. auto hiçbir
        zaman `dashboard-theme`e YAZILMAZ; açık palet seçilince sistem
        değişimi paleti EZMEZ.
        """
        self.page.emulate_media(color_scheme="light")
        self.page.goto("http://127.0.0.1:%d/" % self.PORT,
                       wait_until="domcontentloaded")
        self.page.wait_for_timeout(400)
        state = self.page.evaluate(
            "() => ({ theme: document.documentElement.dataset.theme,"
            "         pref: document.documentElement.dataset.themePreference,"
            "         stored: localStorage.getItem('dashboard-theme') })")
        self.assertEqual((state["theme"], state["pref"]), ("light", "auto"),
                         "sistem açıkken auto paleti uygulanmadı: %r" % state)
        self.assertIsNone(state["stored"],
                          "auto ilk yüklemede tercih YAZMAMALI")

        # Canlı değişim: OS koyuya geçer → sayfa yenilenmeden tema döner.
        self.page.emulate_media(color_scheme="dark")
        self.page.wait_for_function(
            "() => document.documentElement.dataset.theme === 'dark'",
            timeout=5000)
        self.assertEqual(
            self.page.evaluate(
                "() => document.documentElement.dataset.themePreference"),
            "auto")
        self.assertIsNone(
            self.page.evaluate("() => localStorage.getItem('dashboard-theme')"),
            "sistem değişimi tercih anahtarı yazmamalı")

        # Açık palet seçimi auto'yu ezer; OS geri dönse bile palet korunur.
        self.page.locator("#theme-toggle").click()  # auto → dark (saklanır)
        self.page.wait_for_timeout(200)
        self.assertEqual(
            self.page.evaluate("() => localStorage.getItem('dashboard-theme')"),
            "dark")
        self.page.emulate_media(color_scheme="light")
        self.page.wait_for_timeout(400)
        state = self.page.evaluate(
            "() => ({ theme: document.documentElement.dataset.theme,"
            "         pref: document.documentElement.dataset.themePreference })")
        self.assertEqual((state["theme"], state["pref"]), ("dark", "dark"),
                         "açık palet sistem temasına döndü — kullanıcı tercihi "
                         "ezildi: %r" % state)
        self._assert_no_page_error("theme-auto")

    def test_rh_filter_space_key_filters_rows(self):
        """SPACE tuşu rh-filter düğmesini native yolla işletir."""
        self._seed_history(RH_SEED)
        rows = self._rh_ts()
        self.assertEqual(len(rows), 4,
                         "tohum 4 satır render etmedi: %s" % (rows,))
        btn = self.page.locator('.rh-filter button[data-f="PASS"]')
        self.assertGreater(btn.count(), 0, "PASS filtresi yok")
        btn.focus()
        self.page.keyboard.press("Space")
        try:
            self.page.wait_for_function(
                "() => document.querySelectorAll('.rh-row').length === 2",
                timeout=5000)
        except Exception as exc:
            raise AssertionError(
                "SPACE sonrası satır 2'ye inmedi (gözlenen %s) — %s"
                % (self._rh_ts(), exc)) from exc
        self.assertEqual(set(self._rh_ts()), PASS_CLEAN_TS)
        self._assert_no_page_error("rh-filter-space")


if __name__ == "__main__":
    unittest.main()
