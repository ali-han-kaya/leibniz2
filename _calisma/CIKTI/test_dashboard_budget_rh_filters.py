#!/usr/bin/env python3
"""test_dashboard_budget_rh_filters.py — bütçe detayı + run-history filtreleri.

Neden ayrı süit: `test_dashboard_keyboard_nav.py` bu iki yüzeye yalnız
"delege çalışıyor mu" gözüyle bakıyordu — `.rh-filter button.active`
sınıfının taşındığını ve `aria-expanded`'ın döndüğünü doğruluyor, ama
**satırların gerçekten daralıp daralmadığını** ve **detay panelinin
içeriğinin** doğru üretildiğini ölçmüyordu. Bir regresyon `setRhFilter`
içindeki `filtered = rows.filter(...)` satırını düşürse (ya da detay
satırlarını ters sırada üretse) o süit yeşil kalırdı. Buradaki iddialar
kullanıcının gördüğü sonuç üzerinedir:

  1. Run history: PASS / FAIL / P0 / all düğmeleri `.rh-row` kümesini
     GERÇEKTEN daraltır (data-ts kümeleri birebir + sayaç metni).
  2. Bütçe şeridi: limit üstü koşum yoksa görünmez; varsa özet + detay
     paneli açar, her aşım satırını (limit metni + tutar) YENİDEN ESKİYE
     sırayla listeler ve kapanır.
  3. Her etkileşimden sonra: inline event-handler sayacı 0 ve konsolda
     0 CSP ihlali (VERIFY-001 sınıfı: nitelik handler'ı CSP altında
     SESSİZCE ölür — sayaç olmadan "çalışıyor" kanıtı eksik kalır).

Çalıştırma:  python3 -m unittest -v _calisma.CIKTI.test_dashboard_budget_rh_filters
Tarayıcı tier: `_calisma/CIKTI/check_security_browser.list` (skip reddi).
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
except ImportError:  # CI runner'da playwright yoksa SKIP (fail değil)
    sync_playwright = None

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")

# Chrome'un CSP ihlali satırları. Nitelik-handler reddi bu kalıpla gelir;
# sayaç olmadan "delege çalışıyor" iddiası eksik kalır.
CSP_VIOLATION_MARKERS = (
    "Content Security Policy",
    "Refused to execute inline event handler",
    "Refused to apply inline style",
)

# Run-history tohumu: /api/run-history'nin DÖNÜŞ SIRASI (eskiden yeniye).
# Dağılım bilinçli: PASS filtresi p0==0 de ister, P0 filtresi verdict'e
# bakmaz — yani "PASS ama P0=2" satırı iki filtreyi ayırt eder. Hepsi PASS
# olsaydı `n_pass <= n_all` boşuna geçerdi.
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
    {"ts": "2026-09-30T12:00:00Z", "verdict": "ERROR", "p0": 0, "p1": 0,
     "duration_s": 3.0, "budget_usd": 0.5, "refs_verified": 0,
     "refs_total": 43, "pdf_pages": 0, "lean_ok": None, "source": "smoke"},
    {"ts": "2026-09-30T13:00:00Z", "verdict": "PASS", "p0": 2, "p1": 0,
     "duration_s": 22.0, "budget_usd": 4.0, "refs_verified": 43,
     "refs_total": 43, "pdf_pages": 12, "lean_ok": True, "source": "seed"},
    {"ts": "2026-09-30T14:00:00Z", "verdict": "FAIL", "p0": 1, "p1": 0,
     "duration_s": 18.0, "budget_usd": 6.0, "refs_verified": 41,
     "refs_total": 43, "pdf_pages": 12, "lean_ok": True, "source": "seed"},
]

PASS_TS = {"2026-09-30T09:00:00Z", "2026-09-30T10:00:00Z"}
FAIL_TS = {"2026-09-30T11:00:00Z", "2026-09-30T12:00:00Z",
           "2026-09-30T14:00:00Z"}
P0_TS = {"2026-09-30T13:00:00Z", "2026-09-30T14:00:00Z"}


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


class BudgetDetailAndRunHistoryFiltersTest(unittest.TestCase):
    """Canlı preview_server + gerçek Chromium; ağ yalnız 127.0.0.1."""

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
                "preview_server.py did not start on 127.0.0.1:%d within 15s"
                % cls.PORT)

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

    # ------------------------------------------------------------- kurulum
    def setUp(self):
        if sync_playwright is None:
            self.skipTest("playwright kurulu değil "
                          "(pip install playwright + chromium)")
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=True)
        # sw.js tüm fetch'leri SW-içi yapar; Playwright page.route bu
        # istekleri göremez → tohumlama sessizce bypass olurdu.
        self.context = self.browser.new_context(service_workers="block")
        self.page = self.context.new_page()
        self.page.route("**/sw.js", lambda route: route.fulfill(body=""))
        self.console = []
        self.errors = []
        self.page.on("console", lambda m: self.console.append(
            "%s: %s" % (m.type, m.text)))
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.response = self.page.goto(
            "http://127.0.0.1:%d/" % self.PORT, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1000)

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self._pw.stop()

    # ------------------------------------------------------------ yardımcı
    def _csp_header(self):
        return (self.response.headers.get("content-security-policy") or "") \
            if self.response is not None else ""

    def _csp_violations(self):
        return [line for line in (self.console + self.errors)
                if any(m in line for m in CSP_VIOLATION_MARKERS)]

    def _inline_handler_count(self):
        """Canlı DOM'daki inline event-handler niteliği SAYACI.

        Statik tarama runtime-üretilen satırları göremez; burada sayfa
        kendi render yolunu koşturduktan sonra sayılır. Sıfırdan farklı
        olması FAIL'dir — CSP `script-src 'self' + nonce` bu nitelikleri
        yetkilendirmez, yani handler sessizce ölür.
        """
        return self.page.evaluate(
            """(() => {
              let n = 0;
              for (const el of document.querySelectorAll('*')) {
                for (const a of el.attributes) {
                  if (/^on[a-z]+$/.test(a.name)) n += 1;
                }
              }
              return n;
            })()""")

    def _budget_limit(self):
        return self.page.evaluate("BUDGET_LIMIT")

    def _seed(self, *, run_history=None, trend=None):
        """Ağ yanıtlarını üretim okuyucularının beklediği şekilde tohumla."""
        for pattern in ("**/api/run-history*", "**/api/trend*"):
            self.page.unroute(pattern)
        if run_history is not None:
            payload = json.dumps(run_history)
            self.page.route("**/api/run-history*", lambda route: route.fulfill(
                content_type="application/json", body=payload))
        if trend is not None:
            body = json.dumps({"history": trend, "dbRows": []})
            self.page.route("**/api/trend*", lambda route: route.fulfill(
                content_type="application/json", body=body))
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_timeout(900)

    def _rh_rows(self):
        return self.page.evaluate(
            "[...document.querySelectorAll('.rh-row')]"
            ".map(r => r.dataset.ts)")

    def _rh_count_text(self):
        return self.page.evaluate(
            "document.getElementById('run-history-count').textContent")

    def _click_filter(self, name):
        self.page.locator('.rh-filter button[data-f="%s"]' % name).click()
        self.page.wait_for_timeout(500)

    def _wait_rows(self, n):
        """Satır sayısı n olana kadar bekle; olmazsa ANLAŞILIR hata ver.

        Playwright'ın ham TimeoutError'ı triyajı zorlaştırıyordu: "filtre
        daraltmadı" ile "sayfa hiç render etmedi" aynı stack'e düşüyordu.
        Burada gözlenen satır kümesi mesaja girer (fail-closed, yutma yok).
        """
        try:
            self.page.wait_for_function(
                "n => document.querySelectorAll('.rh-row').length === n",
                arg=n, timeout=5000)
        except Exception as exc:  # playwright TimeoutError
            rows = self._rh_rows()
            raise AssertionError(
                "run-history %d satıra ulaşmadı (gözlenen %d: %s; filtre "
                "sayaç metni %r) — %s" % (
                    n, len(rows), rows, self._rh_count_text(), exc)) from exc

    # -------------------------------------------------------------- testler
    def test_page_is_served_under_strict_csp(self):
        """Kapı-önce: CSP yoksa/gevşekse aşağıdaki kanıtlar değersiz olurdu."""
        csp = self._csp_header()
        self.assertTrue(csp, "yanıt Content-Security-Policy başlığı taşımıyor")
        self.assertIn("script-src 'self'", csp)
        self.assertIn("'nonce-", csp)
        script_src = csp.split("script-src", 1)[1].split(";", 1)[0]
        self.assertNotIn("unsafe-inline", script_src,
                         "script-src gevşek — CSP kanıtı geçersiz olur")

    def test_run_history_pass_filter_narrows_to_pass_without_p0(self):
        """PASS: yalnız verdict=PASS VE p0=0 satırları kalır."""
        self._seed(run_history=RH_SEED)
        self._wait_rows(len(RH_SEED))
        self._click_filter("PASS")
        self._wait_rows(len(PASS_TS))
        self.assertEqual(
            set(self._rh_rows()), PASS_TS,
            "PASS filtresi yanlış satır kümesi bıraktı "
            "(PASS ama P0>0 satırı sızmamalı)")
        self.assertEqual(
            self._rh_count_text(), "(%d / %d)" % (len(PASS_TS), len(RH_SEED)),
            "sayaç metni filtrelenmiş sayıyı bildirmiyor")
        self.assertEqual(
            self.page.evaluate(
                "document.querySelector('.rh-filter button.active')"
                ".dataset.f"),
            "PASS", "tıklama aktif düğmeyi taşımadı")

    def test_run_history_fail_and_p0_filters_are_distinct(self):
        """FAIL (FAIL+ERROR) ve P0 (p0>0, verdict'ten bağımsız) ayrı kümeler."""
        self._seed(run_history=RH_SEED)
        self._wait_rows(len(RH_SEED))
        self._click_filter("FAIL")
        self._wait_rows(len(FAIL_TS))
        self.assertEqual(set(self._rh_rows()), FAIL_TS,
                         "FAIL filtresi ERROR satırlarını da kapsamalı")
        self.assertEqual(
            self._rh_count_text(), "(%d / %d)" % (len(FAIL_TS), len(RH_SEED)))
        self._click_filter("P0")
        self._wait_rows(len(P0_TS))
        self.assertEqual(
            set(self._rh_rows()), P0_TS,
            "P0 filtresi p0>0 satırlarını verdict'ten bağımsız seçmeli "
            "(PASS+P0 satırı dâhil)")
        self.assertEqual(
            self._rh_count_text(), "(%d / %d)" % (len(P0_TS), len(RH_SEED)))
        self.assertEqual(self._csp_violations(), [],
                         "filtre tıklamalarında CSP ihlali")

    def test_run_history_all_restores_rows_newest_first(self):
        """all: tüm satırlar geri gelir ve sıra YENİDEN ESKİYE olur."""
        self._seed(run_history=RH_SEED)
        self._wait_rows(len(RH_SEED))
        self._click_filter("P0")
        self._wait_rows(len(P0_TS))
        self._click_filter("all")
        self._wait_rows(len(RH_SEED))
        rows = self._rh_rows()
        self.assertEqual(len(rows), len(RH_SEED), "all filtresi satır kaybetti")
        self.assertEqual(
            rows, [r["ts"] for r in reversed(RH_SEED)],
            "run-history satırları yeniden-eskiye sırada değil")
        self.assertEqual(self._rh_count_text(), "(%d)" % len(RH_SEED),
                         "all filtresinde sayaç biçimi bozuk")

    def _over_seed(self):
        """Limitin ALTINDA ve ÜSTÜNDE koşumlar üret (limit sayfadan okunur)."""
        limit = self._budget_limit()
        older_over = round(limit + 10.5, 2)
        newest_over = round(limit + 25.25, 2)
        rows = [
            {"ts": "2026-09-30T08:00:00Z", "budget_usd": round(limit / 2, 2),
             "verdict": "PASS", "p0": 0, "p1": 0, "budget_limit": limit},
            {"ts": "2026-09-30T09:00:00Z", "budget_usd": older_over,
             "verdict": "PASS", "p0": 0, "p1": 0, "budget_limit": limit},
            {"ts": "2026-09-30T10:00:00Z", "budget_usd": round(limit / 3, 2),
             "verdict": "PASS", "p0": 0, "p1": 0, "budget_limit": limit},
            {"ts": "2026-09-30T11:00:00Z", "budget_usd": newest_over,
             "verdict": "PASS", "p0": 0, "p1": 0, "budget_limit": limit},
        ]
        return limit, older_over, newest_over, rows

    def test_budget_banner_hidden_when_no_run_over_limit(self):
        """Limit üstü koşum yokken şerit GÖRÜNMEMELİ (yanlış alarm yok)."""
        limit = self._budget_limit()
        under = [
            {"ts": "2026-09-30T08:00:00Z", "budget_usd": round(limit / 2, 2),
             "verdict": "PASS", "p0": 0, "p1": 0},
            {"ts": "2026-09-30T09:00:00Z", "budget_usd": round(limit / 3, 2),
             "verdict": "PASS", "p0": 0, "p1": 0},
        ]
        self._seed(trend=under)
        self.page.wait_for_timeout(300)
        self.assertEqual(
            self.page.evaluate(
                "document.getElementById('budget-over-banner').style.display"),
            "none", "limit üstü koşum yokken bütçe şeridi görünüyor")

    def test_budget_detail_lists_every_over_run_newest_first(self):
        """Detay paneli her aşımı tutarıyla, YENİDEN ESKİYE listeler."""
        limit, older_over, newest_over, rows = self._over_seed()
        self._seed(trend=rows)
        self.page.wait_for_function(
            "() => document.getElementById('budget-over-banner').style.display"
            " === 'block'", timeout=5000)
        summary = self.page.evaluate(
            "document.getElementById('budget-over-summary').textContent")
        self.assertIn("2 run limiti aştı", summary,
                      "özet aşım sayısını bildirmiyor: %r" % summary)
        self.assertIn("en yüksek $%.2f" % newest_over, summary,
                      "özet en yüksek aşımı bildirmiyor: %r" % summary)
        # Detay önce KAPALI olmalı (şerit açılışta yalnız özet gösterir).
        self.assertEqual(
            self.page.evaluate(
                "document.getElementById('budget-over-detail').style.display"),
            "none", "detay paneli başlangıçta açık")
        self.assertEqual(
            self.page.get_attribute("#budget-over-toggle", "aria-expanded"),
            "false")
        # Gerçek fare tıklaması → delege (data-act=budget-toggle) çalışır.
        self.page.locator("#budget-over-toggle").click()
        self.page.wait_for_timeout(200)
        self.assertEqual(
            self.page.evaluate(
                "document.getElementById('budget-over-detail').style.display"),
            "block", "tıklama detay panelini açmadı — delege ölü")
        self.assertEqual(
            self.page.get_attribute("#budget-over-toggle", "aria-expanded"),
            "true", "aria-expanded güncellenmedi")
        self.assertEqual(
            self.page.evaluate(
                "document.getElementById('budget-over-caret').textContent"),
            "▾", "açık durumda caret güncellenmedi")
        detail = self.page.evaluate(
            "document.getElementById('budget-over-detail').textContent")
        for amount in (older_over, newest_over):
            self.assertIn("$%.2f" % amount, detail,
                          "aşım satırı detayda yok: $%.2f" % amount)
        self.assertIn("limit $%s üstünde" % (
            str(int(limit)) if float(limit).is_integer() else "%.2f" % limit),
            detail, "detay satırı limit bağlamını taşımıyor: %r" % detail)
        self.assertLess(
            detail.index("$%.2f" % newest_over),
            detail.index("$%.2f" % older_over),
            "detay satırları yeniden-eskiye sırada değil: %r" % detail)
        self.assertNotIn("$%.2f" % round(limit / 2, 2), detail,
                         "limit ALTINDAKİ koşum detayda listelenmiş")
        # Kapatma da gerçek tıklamayla.
        self.page.locator("#budget-over-toggle").click()
        self.page.wait_for_timeout(200)
        self.assertEqual(
            self.page.evaluate(
                "document.getElementById('budget-over-detail').style.display"),
            "none", "ikinci tıklama detayı kapatmadı")
        self.assertEqual(
            self.page.get_attribute("#budget-over-toggle", "aria-expanded"),
            "false")
        self.assertEqual(self._csp_violations(), [],
                         "bütçe detayında CSP ihlali")
        self.assertEqual(
            self._inline_handler_count(), 0,
            "canlı DOM'da inline handler var — CSP altında SESSİZCE ölür")

    def test_interactions_leave_zero_inline_handlers_and_csp_violations(self):
        """Tüm yüzeyler sürüldükten sonra sayaçlar sıfır kalmalı."""
        self._seed(run_history=RH_SEED, trend=self._over_seed()[3])
        self._wait_rows(len(RH_SEED))
        for name in ("PASS", "FAIL", "P0", "all"):
            self._click_filter(name)
        self.page.locator("#budget-over-toggle").click()
        self.page.wait_for_timeout(300)
        self.assertEqual(self._inline_handler_count(), 0,
                         "etkileşimlerden sonra inline handler sayacı sıfır "
                         "değil")
        self.assertEqual(self._csp_violations(), [],
                         "etkileşimlerden sonra CSP ihlali: %s"
                         % self._csp_violations()[:5])
        acts = self.page.evaluate(
            "[...document.querySelectorAll('[data-act]')]"
            ".map(e => e.dataset.act)")
        for expected in ("rh-filter", "budget-toggle"):
            self.assertIn(expected, acts,
                          "delege yüzeyi kaybolmuş: data-act=%s" % expected)


if __name__ == "__main__":
    unittest.main()
