#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_local_security_surface.py — yerel-daemon güvenlik-yüzeyi sözleşmesi.

Tehdit-modeli denetiminin sabitlediği iki boşluk + mevcut savunma-paritesi:

  G1) DNS-rebinding: GET-API'ler (/api/latest, /api/history, SSE dahil)
      trusted-request (Host/Origin) kapısından geçmiyordu — saldırgan
      sayfası evil.example→127.0.0.1 rebinding'iyle yerel verify verisini
      okuyabilirdi. Sözleşme: her /api/* GET'i Host/Origin 127.0.0.1/
      localhost/::1 dışında ise 403 (statik varlıklar ve do_HEAD hariç).
  G2) Peer-paritesi: /api/run-now state-changing — /api/stop'taki
      sahtelenemez TCP-peer kapısına sahip olmalı (güven-sırası: peer →
      trusted → auth). Sandbox-dışı bind'ta dış-proses run
      tetikleyemesin.

Birim-prob'lar handler'ı object.__new__ ile kurar (test_preview_server
deseni); canlı-prob gerçek in-process HTTPServer üzerinden G1'i uçtan-
uca kanıtlar.
"""
import io
import json
import os
import pathlib
import socket
import sys
import threading
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import preview_server as ps  # noqa: E402


def _handler(path, headers, peer=("127.0.0.1", 55555)):
    h = object.__new__(ps.Handler)
    h.path = path
    h.headers = headers
    h.client_address = peer
    sent = []
    h._send = lambda status, body, content_type="", extra_headers=None: \
        sent.append((status, json.loads(body) if body.startswith("{") else body))
    return h, sent


class TestGetApiTrustedGate(unittest.TestCase):
    """G1: /api/* GET'leri Host/Origin kapısından geçmeli."""

    def test_get_latest_rejects_untrusted_host(self):
        h, sent = _handler("/api/latest", {"Host": "evil.example"})
        h.do_GET()
        self.assertEqual(sent[0][0], 403)
        self.assertEqual(sent[0][1]["error"], "forbidden host")

    def test_get_history_rejects_untrusted_host(self):
        h, sent = _handler("/api/history", {"Host": "evil.example"})
        h.do_GET()
        self.assertEqual(sent[0][0], 403)

    def test_get_run_stream_rejects_untrusted_host(self):
        h, sent = _handler("/api/run-stream", {"Host": "evil.example"})
        h.do_GET()
        self.assertEqual(sent[0][0], 403)

    def test_get_api_rejects_untrusted_origin(self):
        h, sent = _handler("/api/latest",
                           {"Host": "127.0.0.1:8000",
                            "Origin": "https://evil.example"})
        h.do_GET()
        self.assertEqual(sent[0][0], 403)
        self.assertEqual(sent[0][1]["error"], "forbidden origin")

    def test_get_api_allows_trusted_host(self):
        h, sent = _handler("/api/latest", {"Host": "127.0.0.1:8000"})
        h.do_GET()
        self.assertNotEqual(sent[0][0], 403)

    def test_health_with_trusted_host_not_403(self):
        h, sent = _handler("/api/health", {"Host": "localhost:8000"})
        h.do_GET()
        self.assertNotEqual(sent[0][0], 403)

    def test_static_assets_ungated(self):
        # Statik varlıklar data-taşımaz — kapı dışı (minimal-değişim sözleşmesi).
        old_dir = getattr(ps, "PREVIEW_DIR", None)
        ps.PREVIEW_DIR = str(CIKTI)
        try:
            h, sent = _handler("/guide.html", {"Host": "127.0.0.1:8000"})
            h.do_GET()
            self.assertNotEqual(sent[0][0], 403)
        finally:
            if old_dir is None:
                if hasattr(ps, "PREVIEW_DIR"):
                    del ps.PREVIEW_DIR
            else:
                ps.PREVIEW_DIR = old_dir


class TestRunNowPeerParity(unittest.TestCase):
    """G2: /api/run-now, /api/stop ile aynı TCP-peer kapısına sahip olmalı."""

    def _with_token(self, fn):
        old = os.environ.get("PREVIEW_RUN_NOW_TOKEN")
        old_busy = ps.VERIFY_BUSY
        try:
            os.environ["PREVIEW_RUN_NOW_TOKEN"] = "secret-token"
            import threading as _t
            ps.VERIFY_BUSY = _t.Lock()
            fn()
        finally:
            ps.VERIFY_BUSY = old_busy
            if old is None:
                os.environ.pop("PREVIEW_RUN_NOW_TOKEN", None)
            else:
                os.environ["PREVIEW_RUN_NOW_TOKEN"] = old

    def test_run_now_rejects_non_loopback_peer(self):
        def body():
            h, sent = _handler("/api/run-now",
                               {"Authorization": "Bearer secret-token",
                                "Host": "127.0.0.1:8000"},
                               peer=("203.0.113.7", 5555))
            h.trigger_run_now()
            self.assertEqual(sent[0][0], 403)
            self.assertEqual(sent[0][1]["error"], "forbidden peer")
        self._with_token(body)

    def test_run_now_peer_gate_precedes_auth_and_trust(self):
        """Güven-sırası stop ile birebir: peer → trusted → auth."""
        def body():
            h, sent = _handler("/api/run-now",
                               {"Authorization": "Bearer secret-token",
                                "Host": "evil.example"},
                               peer=("203.0.113.7", 5555))
            h.trigger_run_now()
            self.assertEqual(sent[0][1]["error"], "forbidden peer")
        self._with_token(body)

    def test_run_now_loopback_peer_trusted_host_reaches_auth(self):
        def body():
            h, sent = _handler("/api/run-now", {"Host": "127.0.0.1:8000"})
            h.trigger_run_now()
            # peer+trusted kapıları geçildi → auth katmanı: 401 (Bearer yok)
            self.assertEqual(sent[0][0], 401)
        self._with_token(body)


class TestLiveRebindProbe(unittest.TestCase):
    """G1 uçtan-uca: gerçek in-process sunucuda sahte-Host GET 403 dönmeli."""

    def test_live_evil_host_get_403(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        srv = ps.ThreadingHTTPServer(("127.0.0.1", port), ps.Handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as c:
                c.sendall(b"GET /api/latest HTTP/1.1\r\n"
                          b"Host: evil.example\r\nConnection: close\r\n\r\n")
                buf = io.BytesIO()
                while True:
                    chunk = c.recv(4096)
                    if not chunk:
                        break
                    buf.write(chunk)
            head = buf.getvalue().split(b"\r\n\r\n", 1)[0].decode("latin-1")
            self.assertIn("403", head.split("\r\n")[0])
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
