"""test_stop_post_only.py — /api/stop POST-only sözleşmesi.

/api/stop daemon'ı durdurur (state-changing). Kardeş uç /api/run-now ile
aynı sözleşme: GET → 405 + Allow: POST (tarayıcı prefetch'i, crawler ve
cache katmanları sunucuyu durduramamalı); tetikleme yalnızca POST.
Beklenen ilk koşum KIRMIZI'dır: _route'ta /api/stop girişi olmadığından
GET JSON-404 döner — test bu boşluğu sabitler.

Test gerçek bir in-process HTTPServer üzerinde koşar (handler seviyesi
mock değil). stop_server stub'lanır: test gerçek bir daemon kapatmaz,
yalnızca method-routing'i ölçer.
"""

import json
import pathlib
import sys
import threading
import unittest
from http.server import HTTPServer

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import preview_server as ps  # noqa: E402


class _StubStop(HTTPServer):
    """stop_server çağrılarını sayan HTTPServer; gerçek daemon kapatmaz."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.stop_calls = 0


class TestStopPostOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = _StubStop(("127.0.0.1", 0), ps.Handler)

        def _stub(handler, _srv=cls.server):
            _srv.stop_calls += 1
            handler._send(200, json.dumps({"status": "stopping"}),
                          content_type="application/json; charset=utf-8")

        cls._old_stop = ps.Handler.stop_server
        ps.Handler.stop_server = _stub
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        ps.Handler.stop_server = cls._old_stop

    def _request(self, method):
        import urllib.request
        import urllib.error
        url = f"http://127.0.0.1:{self.server.server_address[1]}/api/stop"
        req = urllib.request.Request(url, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, dict(r.headers), r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read().decode("utf-8")

    # ── behavioral: gerçek HTTP katmanı ──

    def test_get_returns_405_with_allow_post(self):
        status, headers, body = self._request("GET")
        self.assertEqual(status, 405)
        self.assertEqual(headers.get("Allow"), "POST")
        payload = json.loads(body)
        self.assertEqual(payload.get("error"), "method not allowed")

    def test_get_does_not_stop(self):
        before = self.server.stop_calls
        self._request("GET")
        self.assertEqual(self.server.stop_calls, before)

    def test_post_stops(self):
        status, headers, body = self._request("POST")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body).get("status"), "stopping")
        self.assertGreaterEqual(self.server.stop_calls, 1)

    def test_unsupported_method_does_not_stop(self):
        # PUT standart olarak 501 (Unsupported method) alır; sözleşme
        # "sunucu durmaz"dır — 405 yalnızca GET için zorunlu.
        before = self.server.stop_calls
        status, headers, _ = self._request("PUT")
        self.assertEqual(self.server.stop_calls, before)
        self.assertNotEqual(status, 200)

    # ── source contract: GET dispatch'i yasak ──

    def test_do_get_does_not_dispatch_stop(self):
        source = ps.__file__ and pathlib.Path(ps.__file__).read_text(
            encoding="utf-8")
        get_body = source.split("def do_GET(self):", 1)[1].split(
            "def do_POST(self):", 1)[0]
        self.assertNotIn("stop_server", get_body,
                         "do_GET stop'u tetiklememeli (405 dönmeli)")
        stop_branch = get_body.split('route == "stop":', 1)[1].split(
            "elif", 1)[0]
        self.assertIn("_reject_method", stop_branch)

    def test_do_post_keeps_stop_dispatch(self):
        source = pathlib.Path(ps.__file__).read_text(encoding="utf-8")
        post_body = source.split("def do_POST(self):", 1)[1].split(
            "def ", 1)[0]
        self.assertIn("/api/stop", post_body)
        self.assertIn("stop_server", post_body)


if __name__ == "__main__":
    unittest.main()
