#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_preview_hover_tooltip.py — CSP altında hover-tooltip kanıtı (Playwright).

VERIFY-001: CSP `script-src 'self' + nonce` altında `<script>` bloğu
çalışır ama **nitelik** handler'lar (`onmousemove="…"` ÇALIŞMAZ — nonce
niteliklere uygulanmaz). Bu yüzden refs-trend grafiğinin hover
tooltip'i sessizce ölüydü: görünür bir hata yok, sadece tooltip gelmiyordu.

Bu süit iddiayı UÇTAN UCA kanıtlar; hepsi gerçek tarayıcı + gerçek sunucu:

  1. Yanıt gerçekten CSP taşıyor ve script-src'de 'unsafe-inline' YOK
     (aksi halde "CSP altında çalışıyor" iddiası boş olurdu).
  2. refs-trend hit-alanları DOM'da data-tip/data-i ile ÜRETİLİR (nitelik
     handler değil) — sayfanın kendi render yolundan öndatayla.
  3. Fare bir sütuna girince #tip görünür ve O RUN'IN refs değerlerini
     gösterir (sabit/tooltip değil, indekse bağlı gerçek veri).
  4. Başka bir sütuna girince içerik DEĞİŞİR → delege indeksi doğru.
  5. Grafikten çıkınca tooltip gizlenir (mouseleave yolu).
  6. Konsolda HİÇ CSP ihlali / "Refused to execute inline event handler"
     yok. Düzeltme geri alınsa burası kızar.
  7. Aynı desen trend + hook-env grafiklerinde de çalışır (üçü de aynı
     sınıftı; yarım düzeltme VERIFY-001'i çözmez).

Çalıştırma:
  python3 -m unittest discover -s _calisma/CIKTI -p "test_preview_hover_tooltip.py" -v
Playwright kurulu değilse SKIP (fail değil) — ortam-bağımlı kapı ortamı
bloke etmez, ama statik eşdeğeri (test_preview_server.py →
InlineEventHandlerContractTests) her yerde çalışır.

SKIP'in nerede SESSİZCE işe yaramadığı da not edilmelidir (ölçüldü
2026-09-27): dosya check_unit_tests.list'te olduğu halde `verify` işinin
birim-test adımında Playwright kurulu değil → 8 test SKIP; Playwright
yalnız `a11y-gate` işinde kuruluyor, ama o iş bu süiti KOŞMAMIYORDU. Yani
kanıt hiçbir işte çalışmıyordu. `a11y-gate` işine "VERIFY-001 — hover-tooltip
CSP kanıtı (canlı, fail-closed)" adımı eklendi: süiti koşturur ve SKIP
izini de reddeder (atlanan kanıt geçen kanıt değildir). Statik kapı
çağrılmadıysa ilk iş burasıdır.
"""

import os
import socket
import subprocess
import sys
import time
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # CI runner'da playwright yoksa SKIP (fail değil)
    sync_playwright = None

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")

# Chrome'un CSP ihlali mesajları: nitelik handler reddi tam olarak bu
# kalıpla gelir. "Content Security Policy" genel eşleşmesi de yeterli.
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
        except OSError:  # ConnectionRefusedError da OSError alt sınıfı
            time.sleep(0.3)
    return False


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class HoverTooltipUnderCSPTest(unittest.TestCase):
    """Gerçek preview_server + gerçek Chromium: hover tooltip + CSP kanıtı."""

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
                f"preview_server.py 15 sn içinde 127.0.0.1:{cls.PORT} üzerinde "
                f"ayakta kalmadı (cwd={HERE})")

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
        # sw.js tüm fetch'leri SW içine alır; Playwright interception
        # SW-geçişli istekleri göremez → testler deterministik olsun diye
        # engellenir (test_dashboard_keyboard_nav ile aynı desen).
        self.context = self.browser.new_context(service_workers="block")
        self.page = self.context.new_page()
        self.page.route("**/sw.js", lambda route: route.fulfill(body=""))
        self.console = []
        self.errors = []
        self.page.on("console", lambda m: self.console.append(
            "%s: %s" % (m.type, m.text)))
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        response = self.page.goto("http://127.0.0.1:%d/" % self.PORT,
                                  wait_until="domcontentloaded")
        self.page.wait_for_timeout(1200)
        self.response = response

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self._pw.stop()

    # ---------------------------------------------------------------- yardım
    def _csp_header(self):
        return self.response.headers.get("content-security-policy") or ""

    def _tip_state(self):
        return self.page.evaluate(
            "(() => { const t = document.getElementById('tip');"
            " return {display: t.style.display,"
            " text: t.textContent || '',"
            " visible: getComputedStyle(t).display !== 'none'}; })()")

    def _csp_violations(self):
        blob = "\n".join(self.console + self.errors)
        return [line for line in (self.console + self.errors)
                if any(m in line for m in CSP_VIOLATION_MARKERS)]

    def _seed_refs_trend(self):
        """refs-trend'i sayfanın KENDİ render yolundan 4 run ile doldur.

        Test kodu hiçbir markup uydurmaz: `renderRefsTrend` üretim
        fonksiyonudur, hit-alanları o basar. refs_verified her run'da
        farklı → tooltip içeriğinin indekse bağlı olduğu ayırt edilebilir.
        """
        self.page.evaluate(
            """(() => {
              const rows = Array.from({length: 4}, (_, i) => ({
                ts: new Date(Date.now() - (4 - i) * 3600e3).toISOString(),
                refs_verified: 10 + i * 7,   // 10, 17, 24, 31
                refs_total: 40,
                refs_mismatch: i,
                verdict: "PASS", p0: 0, p1: 0,
              }));
              renderRefsTrend(rows);
            })()""")
        self.page.wait_for_timeout(150)

    def _hit_rects(self, svg_id, expect=None):
        """Hit-alanları locator'ı — `expect` verildiyse SAYISI fail-closed denenir.

        Neden: `expect` yoksa test, hit-alanı hiç üretilmediğinde skip'e
        düşüp yeşil görünebilirdi. Ölçüldü (düzeltme öncesi kod): üç test
        "veri yok" sanıp skip oldu, yani delege kopunca kapı işe yaramaz
        hale geliyordu. Bu yüzden sayı BURADA zorlanır.
        """
        if self.page.locator("#%s" % svg_id).count() == 0:
            self.skipTest("#%s svg yok (sayfa yapısı değişti)" % svg_id)
        rects = self.page.locator("#%s rect[data-tip]" % svg_id)
        if expect is not None:
            self.assertEqual(
                rects.count(), expect,
                "#%s hit-alanı sayısı %d değil — delege/rect üretimi bozuk"
                % (svg_id, expect))
        return rects

    # ---------------------------------------------------------------- testler
    def test_page_is_actually_served_under_strict_csp(self):
        """Önce kapı: CSP gerçekten var mı ve sıkı mı?

        Bu test düşse ("CSP yok"), aşağıdaki tooltip testleri yeşil kalıp
        YANLIŞ kanıt üretirdi. 'unsafe-inline' script-src'da olsaydı da
        iddia çürük olurdu.
        """
        csp = self._csp_header()
        self.assertTrue(csp, "yanıt Content-Security-Policy başlığı taşımıyor")
        self.assertIn("script-src 'self'", csp)
        self.assertIn("'nonce-", csp)
        script_src = csp.split("script-src", 1)[1].split(";", 1)[0]
        self.assertNotIn("unsafe-inline", script_src,
                         "script-src gevşek — CSP kanıtı geçersiz olur")

    def test_refs_trend_hit_areas_carry_data_attributes_not_handlers(self):
        """Hit-alanları NITELİK değil data-* taşımalı (düzeltmenin izi)."""
        self._seed_refs_trend()
        rects = self._hit_rects("refs-trend", expect=4)
        attrs = self.page.evaluate(
            "(() => { const r = document.querySelectorAll("
            "'#refs-trend rect[data-tip]');"
            " return [...r].map(e => ({tip: e.dataset.tip, i: e.dataset.i,"
            " onclick: e.getAttribute('onclick'),"
            " onmousemove: e.getAttribute('onmousemove')})); })()")
        self.assertEqual([a["tip"] for a in attrs], ["refs"] * 4)
        self.assertEqual([a["i"] for a in attrs], ["0", "1", "2", "3"])
        for a in attrs:
            self.assertIsNone(a["onmousemove"])
            self.assertIsNone(a["onclick"])

    def test_hover_shows_tooltip_with_that_runs_refs_values(self):
        """Asıl kanıt: fare sütuna girince tooltip O RUN'IN verisini gösterir."""
        self._seed_refs_trend()
        before = self._tip_state()
        self.assertFalse(before["visible"], "tooltip hover öncesi görünür olmamalı")

        rects = self._hit_rects("refs-trend", expect=4)
        rects.nth(1).hover()
        self.page.wait_for_timeout(200)

        tip = self._tip_state()
        self.assertTrue(tip["visible"],
                        "hover sonrası tooltip GÖRÜNMEDİ — CSP handler "
                        "ölmüş olabilir (VERIFY-001 regresyonu)")
        self.assertIn("refs", tip["text"], "tooltip refs satırı içermiyor")
        # 2. sütun → data-i=1 → refs_verified = 10 + 1*7 = 17
        self.assertIn("17", tip["text"],
                      "tooltip 2. sütunun refs_verified=17 değerini göstermiyor: %r"
                      % tip["text"][:200])
        self.assertIn("40", tip["text"], "tooltip refs_total=40 göstermiyor")

    def test_hover_on_other_column_changes_content(self):
        """Delege İNDEKSİ çalışıyor: sabit tooltip değil, satıra bağlı."""
        self._seed_refs_trend()
        rects = self._hit_rects("refs-trend", expect=4)
        rects.nth(1).hover()
        self.page.wait_for_timeout(200)
        first = self._tip_state()["text"]
        rects.nth(3).hover()
        self.page.wait_for_timeout(200)
        second = self._tip_state()["text"]
        self.assertNotEqual(first, second,
                            "iki farklı sütun aynı tooltip'i gösteriyor — "
                            "data-i ile delege çalışmıyor")
        self.assertIn("31", second, "4. sütun refs_verified=31 göstermiyor")

    def test_leaving_chart_hides_tooltip(self):
        """mouseleave yolu da çalışıyor (yapışkan tooltip olmamalı)."""
        self._seed_refs_trend()
        self._hit_rects("refs-trend", expect=4).first.hover()
        self.page.wait_for_timeout(200)
        self.assertTrue(self._tip_state()["visible"])
        # Grafikten uzak bir noktaya taşı → SVG'nin mouseleave'i tetiklenir.
        self.page.mouse.move(5, 5)
        self.page.wait_for_timeout(250)
        self.assertFalse(self._tip_state()["visible"],
                         "grafikten çıkınca tooltip gizlenmedi")

    def test_no_csp_violation_in_console_during_hover(self):
        """Kanıtın sıfır noktası: konsolda CSP ihlali YOK.

        Düzeltme geri alınırsa (inline onmousemove) burası kızar:
        Chrome "Refused to execute inline event handler" basar.

        Düzeltme ÖNCESİ ölçüldü: hit-alanı sayısı 0'a düştüğü için test
        hiç hover yapmadan "temiz" geçiyordu (boş kapı). Bu yüzden önce
        sayı zorlanır, sonra HER sütun gerçekten gezilir.
        """
        self._seed_refs_trend()
        rects = self._hit_rects("refs-trend", expect=4)
        for i in range(rects.count()):
            rects.nth(i).hover()
            self.page.wait_for_timeout(80)
            self.assertTrue(
                self._tip_state()["visible"],
                "%d. sütunda tooltip görünmedi — konsol temizliği "
                "kanıtlanmadı" % i)
        self.page.mouse.move(5, 5)
        self.page.wait_for_timeout(200)
        violations = self._csp_violations()
        self.assertEqual(
            violations, [],
            "CSP ihlali konsola düştü — %d mesaj:\n%s"
            % (len(violations), "\n".join(violations[:10])))

    def test_trend_chart_hover_tooltip_works(self):
        """Aynı desen trend grafiğinde de çalışır (üçü de aynı sınıftı)."""
        self.page.evaluate(
            """(() => {
              const rows = Array.from({length: 3}, (_, i) => ({
                ts: new Date(Date.now() - (3 - i) * 3600e3).toISOString(),
                duration_s: 2 + i, verdict: "PASS", p0: 0, p1: 0,
                z3_passed: 5 + i, z3_total: 10, z3_failed: 0,
                lean_ok: true, budget_usd: 3 + i,
              }));
              renderTrend(rows);
            })()""")
        self.page.wait_for_timeout(150)
        rects = self._hit_rects("trend", expect=3)
        rects.nth(1).hover()
        self.page.wait_for_timeout(200)
        tip = self._tip_state()
        self.assertTrue(tip["visible"], "trend tooltip görünmedi")
        self.assertIn("z3", tip["text"], "trend tooltip z3 satırı içermiyor")
        self.assertEqual(self._csp_violations(), [])

    def test_hook_env_chart_hover_tooltip_works(self):
        """hook-env grafiği de aynı delege haritasında — o da çalışmalı."""
        self.page.evaluate(
            """(() => {
              const rows = Array.from({length: 3}, (_, i) => ({
                ts: new Date(Date.now() - (3 - i) * 3600e3).toISOString(),
                verdict: "PASS", p0: 0, p1: 0,
                hook_env: {python: "3.%d.1" % (11 + i), z3: "4.8.17"},
              }));
              renderHookEnvTrend(rows);
            })()""")
        self.page.wait_for_timeout(150)
        rects = self._hit_rects("he-trend", expect=3)
        rects.nth(1).hover()
        self.page.wait_for_timeout(200)
        tip = self._tip_state()
        self.assertTrue(tip["visible"], "hook-env tooltip görünmedi")
        self.assertIn("4.8.17", tip["text"],
                      "hook-env tooltip araç sürümünü göstermiyor: %r"
                      % tip["text"][:200])
        self.assertEqual(self._csp_violations(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
