#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SECURITY-TIER: static
"""test_local_security_surface.py — yerel-daemon güvenlik-yüzeyi sözleşmesi.

Tehdit-modeli denetiminin sabitlediği iki boşluk + mevcut savunma-paritesi:

  G1) DNS-rebinding: GET-API'ler (/api/latest, /api/history, SSE dahil)
      trusted-request (Host/Origin) kapısından geçmiyordu — saldırgan
      sayfası evil.example→127.0.0.1 rebinding'iyle yerel verify verisini
      okuyabilirdi. Sözleşme: query'den arındırılmış yolu /api/ önekiyle
      başlayan her GET/HEAD isteği, Host/Origin 127.0.0.1/localhost/::1
      dışında ise 403 (statik varlıklar hariç). Kapı kararı yol önekinden
      verilir; `_API_GET_ROUTES` yalnız ilan edilen yüzeyi belgeler.
  G2) Peer-paritesi: /api/run-now state-changing — /api/stop'taki
      sahtelenemez TCP-peer kapısına sahip olmalı (güven-sırası: peer →
      trusted → auth). Sandbox-dışı bind'ta dış-proses run
      tetikleyemez.

P0-01 regresyonu: elle tutulan `_API_GET_ROUTES` kümesi `_route()`'nun
token adlarıyla senkron kalmayı bırakmıştı — `run_stdout`, `det_trend` ve
`equations_api` düşmüştü, `determinism_trend` ise var olmayan bir addı.
`TestGuardedGetRouteSet` kümeyi `API_CONTRACT` üzerinden iki yönlü pinler:
yeni bir /api/* route'u kümeden düşerse süit kırmızı düşer.

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
from test_api_method_contract import API_CONTRACT, LIVE_URLS  # noqa: E402

ATTACKER_HOST = "evil.example"
ATTACKER_ORIGIN = "https://evil.example"


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
        h, sent = _handler("/api/latest", {"Host": ATTACKER_HOST})
        h.do_GET()
        self.assertEqual(sent[0][0], 403)
        self.assertEqual(sent[0][1]["error"], "forbidden host")

    def test_get_history_rejects_untrusted_host(self):
        h, sent = _handler("/api/history", {"Host": ATTACKER_HOST})
        h.do_GET()
        self.assertEqual(sent[0][0], 403)

    def test_get_run_stream_rejects_untrusted_host(self):
        h, sent = _handler("/api/run-stream", {"Host": ATTACKER_HOST})
        h.do_GET()
        self.assertEqual(sent[0][0], 403)

    def test_get_api_rejects_untrusted_origin(self):
        h, sent = _handler("/api/latest",
                           {"Host": "127.0.0.1:8000",
                            "Origin": ATTACKER_ORIGIN})
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

    def test_unknown_api_path_rejects_untrusted_host(self):
        # Kapı, `_route()`'un tanımadığı /api/* yolunu da kapsar: token
        # kümesine eklenmeyi unutmak veri sızdırmaz (fail-closed önek).
        h, sent = _handler("/api/henuz-tanimli-degil", {"Host": ATTACKER_HOST})
        h.do_GET()
        self.assertEqual(sent[0][0], 403)
        self.assertEqual(sent[0][1]["error"], "forbidden host")

    def test_head_api_rejects_untrusted_host(self):
        # HEAD gövde taşımaz ama başlıkları teşhir eder; GET ile aynı kapı.
        h, sent = _handler("/api/latest", {"Host": ATTACKER_HOST})
        h.do_HEAD()
        self.assertEqual(sent[0][0], 403)
        self.assertEqual(sent[0][1]["error"], "forbidden host")

    def test_head_unknown_api_path_rejects_untrusted_host(self):
        # HEAD de route-token kümesinden değil /api/ önekinden karar verir:
        # tanınmayan bir /api/* yolu aksi halde 404 ile rota yoklamasına açılır.
        h, sent = _handler("/api/henuz-tanimli-degil", {"Host": ATTACKER_HOST})
        h.do_HEAD()
        self.assertEqual(sent[0][0], 403)
        self.assertEqual(sent[0][1]["error"], "forbidden host")

    def test_head_static_asset_ungated(self):
        # Statik yol _send kullanmaz; do_HEAD'in başlık yazımını sahteleyip
        # yalnız kapı kararını gözleriz (403 _send'i tetiklenmemeli).
        h, sent = _handler("/guide.html", {"Host": ATTACKER_HOST})
        h.send_response = lambda status: None
        h.send_header = lambda name, value: None
        h.end_headers = lambda: None
        h.do_HEAD()
        self.assertEqual(sent, [])

    def test_static_assets_ungated(self):
        # Statik varlıklar data-taşımaz — kapı dışı (minimal-değişim sözleşmesi).
        old_dir = getattr(ps, "PREVIEW_DIR", None)
        ps.PREVIEW_DIR = str(CIKTI)
        # OKUMA repo'dan, YAZIM geçici dizinden: in-process kapı testi
        # repo'ya history.jsonl/logs/runs bırakmasın (preview_test_env).
        from preview_test_env import in_process_runtime
        runtime = in_process_runtime(ps, "local-security")
        try:
            h, sent = _handler("/guide.html", {"Host": "127.0.0.1:8000"})
            h.do_GET()
            self.assertNotEqual(sent[0][0], 403)
        finally:
            runtime.restore(ps)
            if old_dir is None:
                if hasattr(ps, "PREVIEW_DIR"):
                    del ps.PREVIEW_DIR
            else:
                ps.PREVIEW_DIR = old_dir


class TestGuardedGetRouteSet(unittest.TestCase):
    """P0-01: `_API_GET_ROUTES` ile `_route()`'nun /api/* token'ları iki yönlü
    senkron olmalı.

    Yol listesi `test_api_method_contract.API_CONTRACT`'tan gelir; o tablo
    kendi testiyle `_route()`'daki /api/* literallerine karşı pinlidir. Böylece
    yeni bir /api/* route'u eklendiğinde ya contract testi ya da bu süit
    kırmızı düşer — route adı sessizce kapı dışında kalamaz.
    """

    API_PATHS = sorted(p for p in API_CONTRACT if p.startswith("/api/"))

    def _api_route_tokens(self):
        return {ps._route(path) for path in self.API_PATHS}

    def test_contract_paths_are_real_api_paths(self):
        self.assertGreaterEqual(len(self.API_PATHS), 16)

    def test_every_api_route_token_is_guarded(self):
        missing = sorted(self._api_route_tokens() - ps._API_GET_ROUTES)
        self.assertEqual(missing, [],
                         f"DNS-rebinding kapısından düşen route: {missing}")

    def test_guarded_set_has_no_stale_tokens(self):
        # `determinism_trend` gibi _route()'da karşılığı olmayan adlar da
        # hatadır: kapıyı genişletmez, gerçek route'u korumasız bırakır.
        extra = sorted(ps._API_GET_ROUTES - self._api_route_tokens())
        self.assertEqual(extra, [],
                         f"_route()'da karşılığı olmayan route adı: {extra}")

    def test_p0_01_regression_routes_are_guarded(self):
        """Kümeden düşen üç uç: run_stdout, det_trend ve equations_api."""
        for token, path in (("run_stdout", "/api/run-stdout"),
                            ("det_trend", "/api/determinism-trend"),
                            ("equations_api", "/api/equations")):
            with self.subTest(token=token):
                self.assertEqual(ps._route(path), token)
                self.assertIn(token, ps._API_GET_ROUTES)

    def test_p0_01_named_routes_reject_attacker_host_and_origin(self):
        """Adı geçen iki bypass ucu, gerçek query-şekliyle 403 vermeli.

        `run-stdout` üretimde `?ts=` ile, `determinism-trend` ise cache-buster
        query'siyle çağrılır; kapı `self.path`'in ham haline değil `_route()`
        çıktısına bakmalı. Bu test tam o şekli sınar.
        """
        for path in ("/api/run-stdout?ts=2024-01-01T00:00:00Z",
                     "/api/determinism-trend",
                     "/api/determinism-trend?limit=5"):
            for headers, error in (
                    ({"Host": ATTACKER_HOST}, "forbidden host"),
                    ({"Host": "127.0.0.1:8000",
                      "Origin": ATTACKER_ORIGIN}, "forbidden origin")):
                with self.subTest(path=path, error=error):
                    h, sent = _handler(path, headers)
                    h.do_GET()
                    self.assertEqual(sent[0][0], 403, path)
                    self.assertEqual(sent[0][1]["error"], error, path)

    def test_every_data_route_rejects_attacker_host_with_live_query(self):
        """Kontrattaki her veri rotası, üretim URL şekliyle 403 dönmeli.

        `LIVE_URLS` prefix uçları (`/api/run-stdout?ts=…`) ve SSE yollarını
        gerçek istek biçimleriyle taşır. Host kapısı stream açılmadan önce
        dönmelidir; bu yüzden SSE yolları da güvenle sınanır.
        """
        for path in self.API_PATHS:
            live = LIVE_URLS.get(path, path)
            with self.subTest(path=path, live=live):
                h, sent = _handler(live, {"Host": ATTACKER_HOST})
                h.do_GET()
                self.assertEqual(sent[0][0], 403, path)
                self.assertEqual(sent[0][1]["error"], "forbidden host", path)

    def test_every_contract_path_rejects_attacker_host(self):
        for path in self.API_PATHS:
            with self.subTest(path=path):
                h, sent = _handler(path, {"Host": ATTACKER_HOST})
                h.do_GET()
                self.assertEqual(sent[0][0], 403, path)
                self.assertEqual(sent[0][1]["error"], "forbidden host", path)

    def test_every_contract_path_rejects_attacker_origin(self):
        for path in self.API_PATHS:
            with self.subTest(path=path):
                h, sent = _handler(path, {"Host": "127.0.0.1:8000",
                                          "Origin": ATTACKER_ORIGIN})
                h.do_GET()
                self.assertEqual(sent[0][0], 403, path)
                self.assertEqual(sent[0][1]["error"], "forbidden origin", path)

    def test_static_assets_are_not_in_guarded_set(self):
        for path in ("/preview.js", "/sw.js", "/guide.html",
                     "/design-system/tokens.css", "/equations/add.png",
                     "/slides_z3/1.png", "/video.html", "/video/player.js"):
            with self.subTest(path=path):
                route = ps._route(path)
                self.assertIsNotNone(route)
                self.assertNotIn(route, ps._API_GET_ROUTES)
                self.assertFalse(ps._api_get_gate_applies(path))

    def test_gate_predicate_is_path_prefix_not_set_membership(self):
        for path in self.API_PATHS:
            with self.subTest(path=path):
                self.assertTrue(ps._api_get_gate_applies(path))
        # `_route()` bilmese de /api/ öneki kapıyı açar (fail-closed).
        self.assertTrue(ps._api_get_gate_applies("/api/tanimlanmamis"))
        self.assertTrue(ps._api_get_gate_applies("/api/latest?x=1"))


class TestRunNowPeerParity(unittest.TestCase):
    """G2: /api/run-now, /api/stop ile aynı TCP-peer kapısına sahip olmalı."""

    def _with_token(self, fn):
        old = os.environ.get("PREVIEW_RUN_NOW_TOKEN")
        old_busy = ps.VERIFY_BUSY
        try:
            os.environ["PREVIEW_RUN_NOW_TOKEN"] = "secret-token"
            ps.VERIFY_BUSY = threading.Lock()
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
                                "Host": ATTACKER_HOST},
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


class TestRunNowTokenlessFailClosed(unittest.TestCase):
    """tokensız-mod: PREVIEW_RUN_NOW_TOKEN yoksa /api/run-now /api/stop
    hiçbir koşulda açma → fail-closed (401). localhost+trusted dışında
    (G1) ve peer dışında (G2) zaten 403; token yoksa da üstüne 401."""

    def _no_token(self):
        old = os.environ.get("PREVIEW_RUN_NOW_TOKEN")
        if old is None:
            os.environ.pop("PREVIEW_RUN_NOW_TOKEN", None)
        else:
            os.environ["PREVIEW_RUN_NOW_TOKEN"] = old
        return old

    def test_run_now_requires_token(self):
        old = self._no_token()
        try:
            h, sent = _handler("/api/run-now",
                               {"Host": "127.0.0.1:8000"},
                               peer=("127.0.0.1", 55555))
            h.trigger_run_now()
            self.assertEqual(sent[0][0], 401)
            self.assertEqual(sent[0][1]["error"], "unauthorized")
        finally:
            if old is None:
                os.environ.pop("PREVIEW_RUN_NOW_TOKEN", None)
            else:
                os.environ["PREVIEW_RUN_NOW_TOKEN"] = old


class TestLiveRebindProbe(unittest.TestCase):
    """G1 uçtan-uca: gerçek in-process sunucuda sahte-Host GET 403 dönmeli."""

    def _live_status(self, port, path):
        with socket.create_connection(("127.0.0.1", port), timeout=5) as c:
            c.sendall(("GET %s HTTP/1.1\r\n"
                       "Host: evil.example\r\nConnection: close\r\n\r\n"
                       % path).encode("ascii"))
            buf = io.BytesIO()
            while True:
                chunk = c.recv(4096)
                if not chunk:
                    break
                buf.write(chunk)
        head = buf.getvalue().split(b"\r\n\r\n", 1)[0].decode("latin-1")
        return head.split("\r\n")[0]

    def test_live_evil_host_get_403(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        srv = ps.ThreadingHTTPServer(("127.0.0.1", port), ps.Handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            self.assertIn("403", self._live_status(port, "/api/latest"))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_live_named_bypass_routes_return_403(self):
        """P0-01 uçtan-uca: run-stdout ve det-trend sahte Host'la 403.

        Gerçek HTTP/1.1 isteği, gerçek ThreadingHTTPServer; query şekilleri
        üretimdeki çağrılarla aynı. Guard dosya okumadan ÖNCE dönmeli.
        """
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        srv = ps.ThreadingHTTPServer(("127.0.0.1", port), ps.Handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            for path in ("/api/run-stdout?ts=2024-01-01T00:00:00Z",
                         "/api/determinism-trend?limit=5"):
                with self.subTest(path=path):
                    self.assertIn("403", self._live_status(port, path))
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
