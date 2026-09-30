#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_security_header_matrix.py — güvenlik başlığı MATRİS beyanı.

`test_security_headers.py` tek tek birkaç yolu ölçer (404, 405, statik kök,
HEAD). Bu modül onu **kapsayıcı** yapar: rota listesi `_route()`'un KENDİ
kaynağından türetilir, yani `_route()`'a yeni bir `return "x"` eklendiğinde
bu test o rotayı da kapsamaya alır. Kapsam listesi elle tutulduğu için
`test_every_route_has_a_representative_url` gate'i boş kalmayı reddeder —
yeni rota ekleyip buraya girmeyi unutan değişiklik fail-closed olur.

SSE (`/api/run`, `/api/run-stream`) ayrı ele alınır: sonsuz akış olduğu için
gövde okunmaz, yalnız BAŞLIKLAR okunup bağlantı kapatılır. Bu iki yol kendi
`send_header` blogunu taşır (preview_server.py serve_run_stream, serve_sse)
— yani `end_headers()` hunisinden geçtikleri ayrıca kanıtlanmalıdır.

Huni tek başına yeter: `Handler.end_headers()` override'ı tüm yanıt yollarını
kapsar. Matrisin amacı O İDDİYI boşluksuz sınamaktır — 25 rotanın her biri
ölçülür.
"""

import http.client
import os
import pathlib
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import preview_server as ps  # noqa: E402

# Zorunlu başlıklar — (ad, zorunlu alt-dize veya None)
# None → başlığın var olması yeterli, içerik serbest.
REQUIRED_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Content-Security-Policy", None),
)

# SSE rotaları: sonsuz akış — gövde okunmaz, sadece başlıklar.
SSE_ROUTES = ("sse", "run_stream")

# Her rota adı için temsil eden istek yolu. `test_every_route_has_a_
# representative_url` bu eşlemeyi _route() ile karşılaştırır.
ROUTE_URLS = {
    "sw": "/sw.js",
    "preview": "/",
    "preview_js": "/preview.js",
    "vendor_axe": "/vendor/axe.min.js",
    "design_tokens": "/design-system/tokens.css",
    "design_tokens_stripe": "/design-system/stripe-theme.css",
    "guide": "/guide.html",
    "landing": "/landing.html",
    "landing_assets": "/landing/assets/yok.png",
    "latest": "/api/latest",
    "sse": "/api/run",
    "run_now": "/api/run-now",
    "run_stream": "/api/run-stream",
    "history": "/api/history",
    "refs_trend": "/api/refs-trend",
    "trend": "/api/trend",
    "override_trend": "/api/override-trend",
    "det_trend": "/api/determinism-trend",
    "run_history": "/api/run-history",
    "run_stdout": "/api/run-stdout?ts=1970-01-01T00%3A00%3A00",
    "health": "/api/health",
    "stop": "/api/stop",
    "slides": "/slides_z3/yok.png",
    "video": "/video.html",
    "video_asset": "/video/player.js",
}


def _routes_declared_by_source():
    """_route() kaynağından rota adlarını çıkar.

    Kaynaktan okunur (sabit listeden değil) — yeni rota eklendiğinde
    matrisi kendiliğinden büyür ve kapsam listesinde karşılığı aranır.
    """
    src = (CIKTI / "preview_server.py").read_text(encoding="utf-8")
    start = src.index("def _route(path):")
    end = src.index("\nclass ", start)
    body = src[start:end]
    return set(re.findall(r'return "([a-z_]+)"', body))


class SecurityHeaderMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # serve_preview diskteki PREVIEW_DIR/preview.html'i okur — testin
        # diske bagimli olmamasi icin minimal bir sayfa tmp'ye yazilir.
        # Placeholder `<script data-build-ts>` şart: build-damga enjekte
        # edilebilsin (CSP nonce beyanı buna bagli).
        cls._tmp = tempfile.TemporaryDirectory()
        cls._old_preview_dir = getattr(ps, "PREVIEW_DIR", None)
        ps.PREVIEW_DIR = cls._tmp.name
        with open(os.path.join(cls._tmp.name, "preview.html"), "w",
                  encoding="utf-8") as fh:
            fh.write('<!doctype html><html><body><script data-build-ts>'
                     '</script></body></html>')
        # ThreadingHTTPServer — üretimdeki sunucuyla AYNI sınıf
        # (preview_server.py main(): ThreadingHTTPServer). Tek iş parçacıklı
        # HTTPServer, SSE gibi sonsuz akışlarda iş parçacığını kalıcı olarak
        # meşgul eder ve MATRİSİN KENDİSİ kilitlenir — üretimden sapma
        # ölçtüğümüz şeyi ölçmezdi.
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ps.Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        if cls._old_preview_dir is None:
            if hasattr(ps, "PREVIEW_DIR"):
                del ps.PREVIEW_DIR
        else:
            ps.PREVIEW_DIR = cls._old_preview_dir
        cls._tmp.cleanup()

    def _get(self, path):
        """(status, headers) — gövde okunmaz."""
        req = urllib.request.Request(self.base + path,
                                     headers={"Host": "127.0.0.1"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers

    def _sse_headers(self, path):
        """SSE: yalnizca basliklari oku, sonra baglantiyi kapat.

        urlopen sonsuz akista bloklanir; http.clientOnce ust basliklari
        okur ve `close()` akisi keser — govde hic okunmaz.
        """
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=10)
        try:
            conn.request("GET", path, headers={"Host": "127.0.0.1"})
            resp = conn.getresponse()
            return resp.status, resp.headers
        finally:
            conn.close()

    # ---- kapsam kendi kendini buyutuyor ---------------------------------

    def test_every_route_has_a_representative_url(self):
        """_route()'taki HER rota matriste temsil edilmeli.

        Yeni rota eklenip buraya girilmezse bu test kirmiziya duser —
        kapsam sessizce kuculmez.
        """
        declared = _routes_declared_by_source()
        self.assertGreaterEqual(len(declared), 20,
                                "rota sayisi beklenmedik azaldi — "
                                "_route() cikarildi mi?")
        missing = sorted(declared - set(ROUTE_URLS))
        self.assertEqual(missing, [],
                         "_route()'a eklenen rota, matrise de eklenmeli: "
                         + ", ".join(missing))
        stale = sorted(set(ROUTE_URLS) - declared)
        self.assertEqual(stale, [],
                         "matriste olup _route()'ta olmayan rota: "
                         + ", ".join(stale))

    def test_no_route_is_missing_from_the_matrix_entirely(self):
        """Tuzak: bosluk doldurulup _route() ele alinmasin diye sayim."""
        declared = _routes_declared_by_source()
        covered = {n for n in declared if n in ROUTE_URLS}
        self.assertEqual(len(covered), len(declared),
                         "matris %d/%d rotayi kapsiyor"
                         % (len(covered), len(declared)))

    # ---- matris -----------------------------------------------------------

    def test_every_get_route_carries_all_security_headers(self):
        offenders = []
        for name in sorted(ROUTE_URLS):
            if name in SSE_ROUTES:
                continue
            path = ROUTE_URLS[name]
            status, headers = self._get(path)
            for header, needle in REQUIRED_HEADERS:
                value = headers.get(header)
                if value is None:
                    offenders.append("%-14s %-34s → %s YOK" % (name, path, header))
                elif needle and needle not in value:
                    offenders.append("%-14s %-34s → %s=%r (%s bekleniyordu)"
                                     % (name, path, header, value, needle))
        self.assertEqual(offenders, [],
                         "guvenlik basligi tasimayan rota:\n  "
                         + "\n  ".join(offenders))

    def test_sse_routes_carry_all_security_headers(self):
        """SSE'nin kendi send_header blogu huniden gecmeli."""
        offenders = []
        for name in SSE_ROUTES:
            path = ROUTE_URLS[name]
            status, headers = self._sse_headers(path)
            self.assertEqual(status, 200,
                             "%s 200 vermedi (SSE akisi baslamadi?)" % name)
            for header, needle in REQUIRED_HEADERS:
                value = headers.get(header)
                if value is None:
                    offenders.append("%-14s %s YOK" % (name, header))
                elif needle and needle not in value:
                    offenders.append("%-14s %s=%r (%s bekleniyordu)"
                                     % (name, header, value, needle))
        self.assertEqual(offenders, [],
                         "SSE rotasinda eksik baslik:\n  "
                         + "\n  ".join(offenders))

    def test_unknown_route_404_carries_headers(self):
        """Bilinmeyen yol: 404, ama basliklar yine de tam."""
        for path in ("/yok", "/api/yok", "/derin/yol/yok", "/a/b/c/d"):
            status, headers = self._get(path)
            self.assertEqual(status, 404, path)
            for header, _ in REQUIRED_HEADERS:
                self.assertIsNotNone(headers.get(header),
                                     "%s → 404 yanitinda %s yok"
                                     % (path, header))

    def test_header_value_is_identical_across_routes(self):
        """Huni tek kaynak: baslik degeri rotadan rotaya DEGISMEZ.

        Rota bazli ekleme/cikarma yapilirsa degerler ayrisir ve CSP
        gecerliligini kaybeder (bazi sayfalar gevser).
        """
        seen = {}
        for name in sorted(ROUTE_URLS):
            if name in SSE_ROUTES:
                continue
            status, headers = self._get(ROUTE_URLS[name])
            for header, _ in REQUIRED_HEADERS:
                seen.setdefault(header, set()).add(headers.get(header))
        drifted = {h: sorted(map(repr, v)) for h, v in seen.items() if len(v) > 1}
        self.assertEqual(drifted, {},
                         "baslik degeri rotaya gore degisiyor:\n  "
                         + "\n  ".join("%s: %s" % kv for kv in drifted.items()))

    def test_head_request_carries_headers_without_body(self):
        for path in ("/", "/api/latest", "/api/trend", "/sw.js"):
            conn = http.client.HTTPConnection(
                "127.0.0.1", self.server.server_port, timeout=10)
            try:
                conn.request("HEAD", path, headers={"Host": "127.0.0.1"})
                resp = conn.getresponse()
                body = resp.read()
                self.assertEqual(resp.status, 200, path)
                self.assertEqual(body, b"", path)
                for header, _ in REQUIRED_HEADERS:
                    self.assertIsNotNone(resp.headers.get(header),
                                         "HEAD %s → %s yok" % (path, header))
            finally:
                conn.close()

    def test_state_changing_routes_reject_get_but_keep_headers(self):
        """GET ile state degistirme engelli, basliklar korunuyor."""
        for name in ("run_now", "stop"):
            status, headers = self._get(ROUTE_URLS[name])
            self.assertIn(status, (403, 405),
                          "%s GET ile %d dondu — state degistirme kapisi "
                          "calismiyor" % (name, status))
            for header, _ in REQUIRED_HEADERS:
                self.assertIsNotNone(headers.get(header),
                                     "%s → %s yanitinda %s yok"
                                     % (name, status, header))

    def test_security_header_table_is_not_empty(self):
        """Tuzak: huni bosaltilirsa matris sessizce gecer."""
        self.assertGreaterEqual(len(ps.Handler._SECURITY_HEADERS), 3,
                                "baslik tablosu beklenmedik azaldi")
        names = {h for h, _ in ps.Handler._SECURITY_HEADERS}
        for required, _ in REQUIRED_HEADERS:
            self.assertIn(required, names,
                          "tablo %s icermiyor" % required)


if __name__ == "__main__":
    unittest.main()
