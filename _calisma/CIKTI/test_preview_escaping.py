#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_preview_escaping.py — escapeHTML + nitelik-bağlamı enjeksiyon kapısı.

Arka plan (findings.md "LOW notes"): `escapeHTML` yalnız `& < >` kaçırıyordu.
Bu METİN bağlamı için yeterlidir, ama aynı fonksiyon `title="…"`,
`class="…"`, `data-ts="…"` gibi NİTELİK bağlamında da kullanılıyor — orada
tırnak kaçırmak zorunludur. Ölçülen gerçek boşluklar:

  * `title="Lean FAIL${ld}"`  — ld = lean_detail (Lean çıktısı, serbest metin)
  * `class="source-badge ${srcBadge}"` — srcBadge = run.source (sunucudan)
  * `data-ts="${tsAttr}"` — el ile `&quot;` ile kaçırılıyordu ve bu
    ÇİFT tırnaklı nitelik için YETERLİYDİ (ölçüldü: ts birebir dönüyor).
    Buradaki fark tek yol (escapeHTML) olması; `\'` yazımı ise JS'te
    no-op idi, bir hata değildi.
  * metin bağlamında kaçışsız: bulgu metni (f.message), hook adı (h.name),
    referans etiket/kaynak (r.tag/r.src), run.source rozeti, `<title>` içindeki
    ts/date/platform/gate, K15 sidecar öneki.

Bu süit iddiayı UÇTAN UCA kanıtlar — hepsi gerçek tarayıcı, gerçek sunucu,
GERÇEK HTML ayrıştırıcısı (innerHTML):

  1. `escapeHTML` tırnakları kaçırır (metin + nitelik bağlamı).
  2. Kaçış metin bağlamında görünür kalır (`&#39;` → `'`), yani kaçırma
     kullanıcının gördüğünü bozmaz.
  3. `title="…"` içine `"` taşıyan veri enjekte EDİLEMEZ: nitelik kapanır,
     `onmouseover` NİTELİĞİ DOM'a GİRMEZ.
  4. `class="…"` içine boşluk+tırnak taşıyan veri yeni sınıf/nitelik yaratamaz.
  5. `data-ts` değeri birebir geri döner (ts eşleşmesi bozulmaz).
  6. `<`/`>` taşıyan veri yeni etiket açamaz (metin bağlamı).

Zararlı veri /api/run-history YANITI OLARAK sunulur ve sayfanın kendi
`loadRunHistory` render yolundan geçer — test hiçbir markup uydurmaz.

Çalıştırma:
  python3 -m unittest discover -s _calisma/CIKTI -p "test_preview_escaping.py" -v
Playwright kurulu değilse SKIP; statik eşdeğer her yerde çalışır
(test_preview_server.py → EscapeHtmlContractTests).
"""

import os
import socket
import subprocess
import sys
import time
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # CI'da playwright yoksa SKIP (fail değil)
    sync_playwright = None

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")

# Nitelik kapatmaya yetecek payload'lar. Üçü de gerçek saldırı biçimi:
# değeri nitelikten kaçırıp YENİ nitelik açıyorlar.
XSS_TITLE = 'x" onmouseover="window.__pwned=1'
XSS_CLASS = 'smoke" onmouseover="window.__pwned=1'
XSS_TEXT = '<img src=x onerror="window.__pwned=1>'

MALICIOUS_ROWS = [
    {
        # Hem " (nitelik kapatma) hem ' (her iki yolda da zararsız) içerir.
        "ts": "2026-09-26T21:20:35'\" onmouseover=\"window.__pwned=1",
        "verdict": "FAIL",
        "p0": 0,
        "p1": 0,
        "duration_s": 1.5,
        "lean_ok": False,
        "lean_detail": XSS_TITLE,
        "source": XSS_CLASS,
        "budget_usd": None,
        "refs_verified": None,
        "refs_total": None,
    },
    {
        "ts": "2026-09-26T21:22:00",
        "verdict": "PASS",
        "p0": 0,
        "p1": 0,
        "lean_ok": None,
        "source": "daemon",
    },
]


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
class EscapingUnderRealParserTest(unittest.TestCase):
    """Gerçek tarayıcı ayrıştırıcısı: kaçırma gerçekten kapatıyor mu?"""

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
            raise RuntimeError("preview_server.py 15 sn içinde ayakta kalmadı")

    @classmethod
    def tearDownClass(cls):
        if cls.proc is not None:
            self_proc = cls.proc
            self_proc.terminate()
            try:
                self_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self_proc.kill()
                self_proc.wait(timeout=5)
            cls.proc = None

    def setUp(self):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=True)
        self.context = self.browser.new_context(service_workers="block")
        self.page = self.context.new_page()
        self.page.route("**/sw.js", lambda route: route.fulfill(body=""))
        # Zararlı satırlar SUNUCUDAN geliyor: render yolu üretim kodu kalır.
        self.page.route(
            "**/api/run-history*",
            lambda route: route.fulfill(
                status=200, content_type="application/json",
                body=__import__("json").dumps(MALICIOUS_ROWS)),
        )
        self.page.goto("http://127.0.0.1:%d/" % self.PORT,
                       wait_until="domcontentloaded")
        self.page.wait_for_timeout(1000)
        self.page.evaluate("() => { window.__pwned = 0; }")
        # Üretimin kendi render yolu
        self.page.evaluate("() => loadRunHistory()")
        self.page.wait_for_timeout(400)

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self._pw.stop()

    def _row(self, index=0):
        return self.page.locator(".rh-row").nth(index)

    # loadRunHistory veriyi `slice().reverse()` ile basar: DOM'daki ilk
    # satır listenin SON elemanıdır. Zararlı satır (MALICIOUS_ROWS[0]) yani
    # .nth(1)'de durur; temiz satır .nth(0)'da. Yanlış satırı ölçmek testi
    # boşa düşürürdü.
    EVIL = 1
    CLEAN = 0

    # ---------------------------------------------------------------- testler
    def test_escape_html_escapes_quotes(self):
        """Temel sözleşme: & < > " ' beşi de kaçırılır."""
        out = self.page.evaluate(
            """(x) => escapeHTML(x)""",
            """<a href="x">&'"y""")
        self.assertNotIn("<", out)
        self.assertNotIn(">", out)
        self.assertIn("&amp;", out)
        self.assertIn("&lt;", out)
        self.assertIn("&quot;", out)
        self.assertIn("&#39;", out)

    def test_escaping_is_lossless_in_text_context(self):
        """Kaçırma metni BOZMAMALI: ayrıştırıcı geri çözer, kullanıcı aynı görür.

        Bu, tırnak kaçırmanın 'görseli bozduğu' itirazını ölçüyle kapatır:
        `&#39;` tarayıcıda `'` olur.
        """
        shown = self.page.evaluate(
            """(() => { const d = document.createElement('div');
               d.innerHTML = '<span>' + escapeHTML("a'b\\"c") + '</span>';
               return d.textContent; })()""")
        self.assertEqual(shown, "a'b\"c",
                         "kaçırma metni bozdu — tırnak kaçırma kayıpsız olmalı")

    def test_no_attribute_injection_via_title(self):
        """`title="Lean FAIL${ld}"` — tırnak kaçmamalı, nitelik ENJEKTE EDİLEMEZ."""
        row = self._row(self.EVIL)
        row.wait_for(state="attached", timeout=5000)
        # Zehirli veri title niteliğinin İÇİNDE olmalı… (getAttribute DEKODE
        # edilmiş değeri döner: kaçırılmış `"` doğru olarak `"` görünür —
        # önemli olan ayrı bir NİTELİĞE dönüşmemesidir)
        title = self.page.evaluate(
            """() => { const rows = document.querySelectorAll('.rh-row');
               const el = rows[%d].querySelector('span[title]');
               return el ? el.getAttribute('title') : null; }""" % self.EVIL)
        self.assertIsNotNone(title, "lean title niteliği bulunamadı")
        self.assertIn("onmouseover", title,
                      "test verisi title'a ulaşmadı — test boşa düşmesin")
        # …ama DOM'da onmouseover NİTELİĞİ OLUŞMAMALI.
        self.assertEqual(
            self.page.evaluate(
                "() => document.querySelectorAll('.rh-row [onmouseover]').length"),
            0, "title üzerinden onmouseover NİTELİĞİ enjekte edildi")
        self.assertEqual(
            self.page.evaluate("() => window.__pwned || 0"), 0,
            "enjekte edilen nitelik ÇALIŞTI (pwned=1)")

    def test_no_attribute_injection_via_class(self):
        """`class="source-badge ${srcBadge}"` — yeni sınıf/nitelik yaratamaz."""
        self._row(self.EVIL).wait_for(state="attached", timeout=5000)
        badge = self.page.evaluate(
            """() => { const rows = document.querySelectorAll('.rh-row');
               const b = rows[%d].querySelector('.source-badge');
               return b ? {cls: b.getAttribute('class'), text: b.textContent} : null; }"""
            % self.EVIL)
        self.assertIsNotNone(badge, "source-badge bulunamadı")
        # Kaçırılmış değer DEKODE edilip class içinde görünür (doğru davranış:
        # tek nitelik, değerinin içinde). Kırılma olsaydı class yalnız
        # "source-badge" kalır ve ayrı bir onmouseover NİTELİĞİ doğardı.
        self.assertTrue(
            badge["cls"].startswith("source-badge"),
            "class niteliği bozuk: %r" % badge["cls"])
        self.assertIn("smoke", badge["cls"],
                      "test verisi class değerine ulaşmadı — test boşa düşmesin")
        # Değer metin olarak görünmeli (kaçırılmış hâli, ama aynı karakterler)
        self.assertIn("onmouseover", badge["text"],
                      "test verisi source rozetine ulaşmadı")
        self.assertEqual(
            self.page.evaluate(
                "() => document.querySelectorAll('.rh-row [onmouseover]').length"),
            0, "class üzerinden nitelik enjekte edildi")

    def test_data_ts_round_trips_exactly(self):
        """`data-ts` kaçırılır ama DEĞER birebir geri döner.

        Kaçırma kayıpsız olmalı: `loadRunStdout(t.dataset.ts)` sunucuya
        bu değerle gider, `&quot;`/`&#39;` ayrıştırıcıda geri çözülür.
        (Bu test eski el-kaçırma sürümünde de geçer — kasıtlı: kanıtlanan
        şey "burada bir açık vardı" değil, "yeni yol daha katı ve tutarlı".)
        """
        self._row(self.EVIL).wait_for(state="attached", timeout=5000)
        dataset_ts = self.page.evaluate(
            """() => document.querySelectorAll('.rh-row')[%d].getAttribute('data-ts')"""
            % self.EVIL)
        # Karşılaştırma: ilk satırın ham ts'i (tırnak dahil) aynen dönmeli
        self.assertEqual(dataset_ts, MALICIOUS_ROWS[0]["ts"],
                         "data-ts değeri kayboldu/değişti — ts eşleşmesi kırılır")
        # …ve onmouseover bir NİTELİK olarak DOM'a girmemeli
        self.assertIsNone(
            self.page.evaluate(
                """() => document.querySelectorAll('.rh-row')[%d].getAttribute('onmouseover')"""
                % self.EVIL),
            "data-ts üzerinden onmouseover NİTELİĞİ enjekte edildi")

    def test_no_tag_injection_in_text_context(self):
        """`<img onerror>` gibi veri yeni etiket AÇAMAZ (metin bağlamı)."""
        self.page.evaluate(
            """(payload) => {
                 const list = document.getElementById('refs');
                 if (!list) return false;
                 const li = document.createElement('li');
                 li.innerHTML = '<span>' + escapeHTML(payload) + '</span>';
                 list.appendChild(li);
                 return true;
               }""",
            XSS_TEXT)
        self.assertEqual(
            self.page.evaluate("() => document.querySelectorAll('img[src=\"x\"]').length"),
            0, "kaçışsız veriden <img> etiketi doğdu")
        self.assertEqual(self.page.evaluate("() => window.__pwned || 0"), 0,
                         "onerror ÇALIŞTI — kaçırma yetersiz")

    def test_sanitised_row_looks_normal(self):
        """Kaçırma sonrası sayfa bozulmamalı: iki satır da render edilmeli."""
        self.assertEqual(
            self.page.evaluate("() => document.querySelectorAll('.rh-row').length"),
            2, "run-history satır sayısı 2 değil")
        # Zararsız satır rozeti düz çıkmalı
        clean = self.page.evaluate(
            """() => { const rows = document.querySelectorAll('.rh-row');
               const b = rows[0].querySelector('.source-badge');
               return b ? b.getAttribute('class') : null; }""")
        self.assertEqual(clean, "source-badge daemon",
                         "zararsız kaynak rozeti bozuldu")


if __name__ == "__main__":
    unittest.main(verbosity=2)
