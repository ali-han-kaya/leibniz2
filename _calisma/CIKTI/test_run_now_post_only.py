"""test_run_now_post_only.py — /api/run-now POST-only sözleşmesi.

GET /api/run-now bir verify run'ı *başlatıyordu* (state-changing GET:
tarayıcı prefetch'i, crawler ve cache katmanları run tetikleyebiliyordu).
Yeni sözleşme: GET → 405 + Allow: POST; tetikleme yalnızca POST.

Test gerçek bir in-process HTTPServer üzerinde koşar (handler seviyesi
mock değil) — böylece BaseHTTPRequestHandler'ın 405/Allow davranışı
bütünüyle doğrulanır. trigger_run_now stub'lanır: test ağ/verify
çalıştırmaz, yalnızca method-routing'i ölçer.
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


class _StubRunNow(HTTPServer):
    """trigger_run_now çağrılarını sayan HTTPServer; gerçek run başlatmaz.

    Stub, setUpClass'ta düz bir closure olarak ps.Handler.trigger_run_now'a
    bağlanır (bound method atamak self=handler bind etmez — parametre
    sıfır kalır; ilk kırmızı koşuda yakalandı).
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.run_now_calls = 0


class TestRunNowPostOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = _StubRunNow(("127.0.0.1", 0), ps.Handler)

        def _stub(handler, _srv=cls.server):
            _srv.run_now_calls += 1
            handler._send(200, json.dumps({"status": "started"}),
                          content_type="application/json; charset=utf-8")

        cls._old_trigger = ps.Handler.trigger_run_now
        ps.Handler.trigger_run_now = _stub
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        ps.Handler.trigger_run_now = cls._old_trigger

    def _request(self, method):
        import urllib.request
        import urllib.error
        url = f"http://127.0.0.1:{self.server.server_address[1]}/api/run-now"
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

    def test_get_does_not_trigger_run(self):
        before = self.server.run_now_calls
        self._request("GET")
        self.assertEqual(self.server.run_now_calls, before)

    def test_post_triggers_run(self):
        status, headers, body = self._request("POST")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body).get("status"), "started")
        self.assertGreaterEqual(self.server.run_now_calls, 1)

    def test_unsupported_method_does_not_trigger_run(self):
        # PUT standart olarak 501 (Unsupported method) alır; sözleşme
        # "run tetiklenmez"tir — 405 yalnızca GET için zorunlu.
        before = self.server.run_now_calls
        status, headers, _ = self._request("PUT")
        self.assertEqual(self.server.run_now_calls, before)
        self.assertNotEqual(status, 200)

    # ── source contract: GET dispatch'i yasak ──

    def test_do_get_does_not_dispatch_run_now(self):
        source = ps.__file__ and pathlib.Path(ps.__file__).read_text(
            encoding="utf-8")
        get_body = source.split("def do_GET(self):", 1)[1].split(
            "def do_POST(self):", 1)[0]
        # run_now rotası do_GET'te kalabilir (açık 405 için) ama tetikleme
        # çağrısı bulunmamalı.
        self.assertNotIn("trigger_run_now", get_body,
                         "do_GET run_now'u tetiklememeli (405 dönmeli)")
        run_now_branch = get_body.split('route == "run_now":', 1)[1].split(
            "elif", 1)[0]
        self.assertIn("_reject_method", run_now_branch)

    def test_do_post_keeps_run_now_dispatch(self):
        source = pathlib.Path(ps.__file__).read_text(encoding="utf-8")
        post_body = source.split("def do_POST(self):", 1)[1].split(
            "def ", 1)[0]
        self.assertIn("run-now", post_body)
        self.assertIn("trigger_run_now", post_body)


if __name__ == "__main__":
    unittest.main()
