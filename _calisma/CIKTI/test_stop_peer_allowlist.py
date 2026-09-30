#!/usr/bin/env python3
"""test_stop_peer_allowlist.py — /api/stop TCP-peer allowlist sözleşmesi.

Tehdit modeli: Host/Origin başlıkları istemci-kontrolündedir (tarayıcı-dışı
istemci spoof'lar); --bind 127.0.0.1'i terk eden sandbox-dışı ortamlarda
(0.0.0.0, konteyner, tünel) /api/stop peer'ları görür. Kapı TCP-peer
adresine bakar (sahtelenemez), default izin-kümesi yalnız loopback'tir:
PREVIEW_STOP_ALLOWLIST env'i dışında hiçbir ortam kapıyı genişletemez ve
kapı BIND-ADRESİNDEN BAĞIMSIZ olarak her istekte devrededir.

Kırmızı-yeşil sözleşme:
  - load_stop_allowlist: env ayrıştırma; geçersiz girdi düşülür (kapı
    asla genişlemez), geçerli-kalan boşsa default'a düşer (asla boş küme)
  - _stop_peer_allowed: IPv4-mapped IPv6 (::ffff:127.0.0.1) canonical'lanır,
    ayrıştırılamayan peer → deny (fail-closed)
  - canlı: izin-kümesi DARALTILDIĞINDA loopback-peer bile 403 alır —
    kararın peer-tabanlı olduğunu, bind'a bağlanmadığını gerçek sokette
    kanıtlar (sandbox-dışı devre-sözleşmesi)
"""
import json
import pathlib
import sys
import threading
import unittest
from http.server import HTTPServer
import http.client
import socketserver

CIKTI = pathlib.Path(__file__).resolve().parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import preview_server as ps  # noqa: E402

DEFAULT = {"127.0.0.1", "::1"}


class TestStopAllowlistLoader(unittest.TestCase):
    """Env ayrıştırma sözleşmesi (saf)."""

    def test_default_is_loopback_only(self):
        self.assertEqual(ps.DEFAULT_STOP_ALLOWLIST, frozenset(DEFAULT))
        self.assertEqual(ps.load_stop_allowlist(None), frozenset(DEFAULT))
        self.assertEqual(ps.load_stop_allowlist(""), frozenset(DEFAULT))

    def test_env_extends_with_canonical_ips(self):
        got = ps.load_stop_allowlist("192.168.1.10, 10.0.0.5 ,::1")
        self.assertEqual(got, frozenset({"192.168.1.10", "10.0.0.5",
                                         "::1", "127.0.0.1"}))

    def test_invalid_entries_dropped_loopback_kept(self):
        got = ps.load_stop_allowlist("not-an-ip,localhost,300.1.2.3,10.0.0.9")
        self.assertEqual(got, frozenset({"10.0.0.9"} | DEFAULT))

    def test_all_invalid_falls_back_to_default(self):
        got = ps.load_stop_allowlist("not-an-ip,example.host")
        self.assertEqual(got, frozenset(DEFAULT))
        # Kapı asla boş kümeyle dönmez (boş küme = herkese kapalı olurdu ama
        # kontrat: ayrıştırma-boşluğu default'a döner, sessiz kilitlenme yok)
        self.assertTrue(got)


class TestStopPeerDecision(unittest.TestCase):
    """Peer-kararı sözleşmesi (saf — bind adresinden bağımsız)."""

    def test_loopback_peers_allowed_by_default(self):
        for peer in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            self.assertIsNone(ps._stop_peer_allowed((peer, 50000)),
                              f"{peer} loopback — izinli olmalı")

    def test_non_loopback_peers_denied_by_default(self):
        for peer in ("192.168.1.10", "10.0.0.5", "172.16.0.9", "8.8.8.8",
                     "::ffff:192.168.1.10", "fe80::1"):
            self.assertEqual(ps._stop_peer_allowed((peer, 50000)),
                             "forbidden peer", f"{peer} — deny beklenir")

    def test_unparseable_peer_fails_closed(self):
        self.assertEqual(ps._stop_peer_allowed(("weird-peer", 1)),
                         "forbidden peer")

    def test_env_extended_list_admits_remote_operator(self):
        allow = ps.load_stop_allowlist("10.0.0.5")
        self.assertIsNone(ps._stop_peer_allowed(("10.0.0.5", 50000), allow))
        self.assertEqual(ps._stop_peer_allowed(("10.0.0.6", 50000), allow),
                         "forbidden peer")

    def test_gate_independent_of_bind_address(self):
        """Devre-sözleşmesi: karar yalnız peer'a bakar — bind ne olursa olsun."""
        # Aynı peer kararı, sunucu 127.0.0.1'e de 0.0.0.0'a da binse değişmez:
        # fonksiyon bind bilmez (imzasında yok), bu test imza-sabiti.
        import inspect
        params = inspect.signature(ps._stop_peer_allowed).parameters
        self.assertNotIn("bind", params)
        self.assertIsNone(ps._stop_peer_allowed(("127.0.0.1", 1)))


class TestStopPeerAllowlistLive(unittest.TestCase):
    """Canlı soket: gate gerçek HTTPServer üzerinde devrede."""

    @classmethod
    def setUpClass(cls):
        class _T(socketserver.ThreadingMixIn, HTTPServer):
            daemon_threads = True
        cls.server = _T(("127.0.0.1", 0), ps.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls._old_allowlist = ps.STOP_ALLOWLIST

    @classmethod
    def tearDownClass(cls):
        ps.STOP_ALLOWLIST = cls._old_allowlist
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _post_stop(self, host_header=None):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=3)
        try:
            headers = {"Content-Type": "application/json"}
            if host_header:
                headers["Host"] = host_header
            conn.request("POST", "/api/stop", body="{}", headers=headers)
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            return resp.status, body
        finally:
            conn.close()

    def test_default_loopback_peer_passes_gate_to_readiness(self):
        """Loopback-peer + default küme → gate geçilir (403 'forbidden peer' YOK).

        İzole-ortamda STOP_EVENT None → 503 (not-ready); bu, peer-gate'inin
        aşıldığının gözlemlenebilir kanıtıdır.
        """
        status, body = self._post_stop()
        self.assertEqual(status, 503)
        self.assertIn("server not ready", body)

    def test_narrowed_list_denies_loopback_peer_live(self):
        """Sandbox-dışı devre-kanıtı: küme daraltılınca loopback bile 403.

        Kapının kararı peer-tabanlıdır (bind 127.0.0.1 olsa bile) — listede
        olmayan peer, gerçek soketten gelmiş gibi reddedilir.
        """
        ps.STOP_ALLOWLIST = frozenset({"192.0.2.9"})
        status, body = self._post_stop()
        self.assertEqual(status, 403)
        self.assertIn("forbidden peer", body)

    def test_peer_gate_runs_before_host_check(self):
        """Sıra-sözleşmesi: peer-reddi, Host-başlık denetiminden önce gelir."""
        ps.STOP_ALLOWLIST = frozenset({"192.0.2.9"})
        status, body = self._post_stop(host_header="evil.example")
        self.assertEqual(status, 403)
        self.assertIn("forbidden peer", body)
        # Peer izinliyken kötü Host: host-kapısı devrede (aynı 403 gövdesi
        # farklı gerekçe) — iki katman da çalışıyor.
        ps.STOP_ALLOWLIST = self._old_allowlist
        status, body = self._post_stop(host_header="evil.example")
        self.assertEqual(status, 403)
        self.assertIn("forbidden host", body)


if __name__ == "__main__":
    unittest.main()
