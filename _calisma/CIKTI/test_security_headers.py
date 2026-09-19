"""test_security_headers.py — güvenlik-başlık sözleşmesi.

Node.js-backend-patterns skill'inin denetimi preview_server.py'de üç boşluk
buldu: X-Content-Type-Options, Referrer-Policy, CSP (rate-limit gereksiz —
ALLOWED_HOSTS localhost-tekil; gzip gereksiz — pano lokal).

Uygulama tek-funnel: Handler.end_headers() override'ı BaseHTTPRequestHandler'ın
tüm yanıt yollarını (_send, serve_preview, SSE dahil) kapsar — serve_preview
kendi başlıklarını yazsa bile.

Test gerçek bir in-process HTTPServer üzerinde koşar (handler seviyesi mock
değil) — test_run_now_post_only.py'nin deseni birebir izler: ağ/verify
çalıştırmaz, gerçek handler üzerinden HTTP yanıtı ölçer.
"""

import os
import os
import pathlib
import re
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import HTTPServer

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import preview_server as ps  # noqa: E402


class TestSecurityHeaders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # serve_preview diskteki PREVIEW_DIR/preview.html'i okur — test diske
        # bağımlı olmasın: minimal bir preview.html'i tmp'ye yaz.
        cls._tmp = tempfile.TemporaryDirectory()
        # PREVIEW_DIR main()'de set edilen global — import anında yok.
        # test_api_method_contract.py ile aynı desen: dinamik set.
        cls._old_preview_dir = getattr(ps, "PREVIEW_DIR", None)
        ps.PREVIEW_DIR = cls._tmp.name
        with open(os.path.join(cls._tmp.name, "preview.html"), "w",
                  encoding="utf-8") as f:
            f.write("<!doctype html><html><body>"
                    "<script data-build-ts></script>"
                    "</body></html>")
        cls.server = HTTPServer(("127.0.0.1", 0), ps.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        if cls._old_preview_dir is None:
            delattr(ps, "PREVIEW_DIR")
        else:
            ps.PREVIEW_DIR = cls._old_preview_dir
        cls._tmp.cleanup()

    def _headers(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as r:
                return dict(r.headers)
        except urllib.error.HTTPError as e:
            return dict(e.headers)

    def test_404_also_carries_headers(self):
        # 404 yanıtları da başlıkları taşımalı — saldırgan-kontrol 404 body'si
        # text/html olarak esnetilirse XSS vektörü açılır.
        h = self._headers("/api/nonexistent")
        self.assertEqual(h.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(h.get("Referrer-Policy"), "no-referrer")
        self.assertIn("default-src 'none'", h.get("Content-Security-Policy"))

    def test_405_carries_headers(self):
        # _reject_method → _send → end_headers override'ı
        h = self._headers("/api/run-now")
        self.assertEqual(h.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("frame-ancestors 'none'", h.get("Content-Security-Policy"))

    def test_405_allow_header(self):
        h = self._headers("/api/run-now")
        self.assertEqual(h.get("Allow"), "POST")

    def test_static_root_carries_headers(self):
        # serve_preview kendi send_header zincirini kullanır — override yine de
        # end_headers'e girer; başlıklar statik yanıtta da olmalı.
        h = self._headers("/preview.html")
        self.assertEqual(h.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("script-src 'self'", h.get("Content-Security-Policy"))

    def test_head_has_bodyless_200(self):
        # do_HEAD: GET başlıkları, gövdesiz.
        req = urllib.request.Request(self.base + "/preview.html", method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.read(), b"")

    def test_csp_nonce_covers_injected_build_stamp(self):
        # Enjekte edilen inline script (window.BUILD_TS) nonce'lu olmalı ve
        # nonce, CSP başlığındaki nonce ile birebir aynı olmalı — aksi halde
        # tarayıcı damgayı engeller ve pano build tazesini kaybeder.
        h = self._headers("/preview.html")
        csp = h.get("Content-Security-Policy", "")
        m = re.search(r"'nonce-([A-Za-z0-9_-]+)'", csp)
        self.assertIsNotNone(m, f"CSP'de nonce yok: {csp}")
        csp_nonce = m.group(1)
        body = urllib.request.urlopen(self.base + "/preview.html",
                                      timeout=10).read().decode("utf-8")
        sm = re.search(r'<script nonce="([A-Za-z0-9_-]+)">', body)
        self.assertIsNotNone(sm, f"gövdede nonce'lu script yok: {body}")
        self.assertEqual(sm.group(1), csp_nonce,
                         "script nonce ≠ CSP nonce — damga engellenir")
        self.assertIn("window.BUILD_TS", body)


if __name__ == "__main__":
    unittest.main()
