#!/usr/bin/env python3
"""test_api_method_contract.py — /api/* allowed-method contract.

Her /api/* yolunun izin verilen HTTP metot kümesini pinler; gelecekte bir
handler yanlışlıkla GET'i POST'e çevirirse (veya tersi) test pre-commit'te
kızarır — runtime'da değil.

Kapsam:
  - Kaynak sözleşmesi: preview_server.py'nin _route + do_GET/do_POST gövdeleri
    API_CONTRACT ile eşleşmeli
  - Canlı sözleşme: gerçek HTTPServer üzerinde GET/POST prob'ları (SSE hariç)

Sözleşme tablosu tek kaynaktır; yeni endpoint eklenirse bu dosya + preview_server.py
aynı commit'te güncellenmeli.
"""
import json
import os
import pathlib
import re
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer

CIKTI = pathlib.Path(__file__).resolve().parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import preview_server as ps  # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# Tek kaynak: her /api/* yolunun izin verilen metot kümesi
# ──────────────────────────────────────────────────────────────────────────────
# Prefix/routed endpoint'ler normalleştirilmiş path ile temsil edilir:
#   /api/run-now      → startswith("/api/run-now")
#   /api/run-stdout   → startswith("/api/run-stdout")
# Diğerleri tam eşleşme (==).
API_CONTRACT = {
    "/api/latest": {"GET"},
    "/api/run": {"GET"},           # SSE — canlı stream (served by serve_sse)
    "/api/run-now": {"POST"},      # tek POST endpoint (state-changing)
    "/api/run-stream": {"GET"},    # SSE — satır akışı
    "/api/history": {"GET"},
    "/api/refs-trend": {"GET"},
    "/api/override-trend": {"GET"},
    "/api/run-history": {"GET"},
    "/api/run-stdout": {"GET"},    # prefix — ?ts= ile
    "/api/health": {"GET"},
}

# SSE endpoint'leri canlı prob'da sonsuz stream üretir — urlopen asılır.
# Kaynak sözleşmesi üzerinden doğrulanır, canlı katmanda kısa header prob'u
# ile ayrıca kontrol edilir.
SSE_PATHS = {"/api/run", "/api/run-stream"}

# Canlı prob'lar için gerçek URL'ler (prefix endpoint'ler query ile)
LIVE_URLS = {
    "/api/latest": "/api/latest",
    "/api/run-now": "/api/run-now",
    "/api/history": "/api/history",
    "/api/refs-trend": "/api/refs-trend",
    "/api/override-trend": "/api/override-trend",
    "/api/run-history": "/api/run-history",
    "/api/run-stdout": "/api/run-stdout?ts=2024-01-01T00:00:00Z",
    "/api/health": "/api/health",
    # SSE path'ler canlıda ayrı test edilir (header-only)
    "/api/run": "/api/run",
    "/api/run-stream": "/api/run-stream",
}


class TestApiMethodContractSource(unittest.TestCase):
    """Kaynak-seviyesi sözleşme — dosya parse, HTTP server gerekmez."""

    def _source(self):
        return pathlib.Path(ps.__file__).read_text(encoding="utf-8")

    def test_contract_covers_all_api_routes(self):
        """API_CONTRACT, _route'un tanıdığı tüm /api/* yollarını kapsamalı."""
        src = self._source()
        # _route içindeki /api/* literal'lerini çıkar
        route_block = src.split("def _route(path):", 1)[1].split("\nclass Handler", 1)[0]
        found = set(re.findall(r'"/api/[^"]+"', route_block))
        # startswith prefix'lerini normalleştir
        # "/api/run-now" → /api/run-now, "/api/run-stdout" → /api/run-stdout
        normalized = set()
        for lit in found:
            lit = lit.strip('"')
            # prefix match'ler de aynı contract key'e düşsün
            # (mevcut kod: startswith("/api/run-now"), startswith("/api/run-stdout"),
            #  startswith("/slides_z3/") hariç)
            if lit.startswith("/api/"):
                normalized.add(lit)
        # /api/run-stdout prefix'i kodda "/api/run-stdout" literali olarak geçmez
        # ama startswith kontrolünde var — manuel olarak dahil et
        # Zaten regex ile yakalanıyor (startswith arg'ında da "/api/..." var)
        missing = normalized - set(API_CONTRACT.keys())
        extra = set(API_CONTRACT.keys()) - normalized
        self.assertEqual(missing, set(),
                         f"API_CONTRACT eksik — _route'da var ama contract'ta yok: {missing}")
        self.assertEqual(extra, set(),
                         f"API_CONTRACT fazla — contract'ta var ama _route'da yok: {extra}")

    def test_do_get_dispatch_matches_contract(self):
        src = self._source()
        get_body = src.split("def do_GET(self):", 1)[1].split("def do_POST(self):", 1)[0]
        for path, methods in API_CONTRACT.items():
            route_token = {
                "/api/latest": '"latest"',
                "/api/run": '"sse"',
                "/api/run-now": '"run_now"',
                "/api/run-stream": '"run_stream"',
                "/api/history": '"history"',
                "/api/refs-trend": '"refs_trend"',
                "/api/override-trend": '"override_trend"',
                "/api/run-history": '"run_history"',
                "/api/run-stdout": '"run_stdout"',
                "/api/health": '"health"',
            }[path]
            self.assertIn(route_token, get_body,
                          f"do_GET {route_token} ({path}) dalı bulunamadı")
            if "GET" in methods:
                # GET-izinli yollar _reject_method çağırmamalı
                branch = get_body.split(f"route == {route_token}", 1)
                if len(branch) == 2:
                    snippet = branch[1].split("elif", 1)[0]
                    self.assertNotIn("_reject_method", snippet,
                                     f"{path} GET-izinli ama do_GET _reject_method çağırıyor")
            else:
                # POST-only (run-now) GET'te 405 dönmeli
                branch = get_body.split(f"route == {route_token}", 1)[1].split("elif", 1)[0]
                self.assertIn("_reject_method", branch,
                              f"{path} POST-only ama do_GET _reject_method içermiyor (GET → 405 beklenir)")

    def test_do_post_dispatch_matches_contract(self):
        src = self._source()
        post_body = src.split("def do_POST(self):", 1)[1].split("\n    def ", 1)[0]
        for path, methods in API_CONTRACT.items():
            if "POST" in methods:
                # POST-izinli yol do_POST'ta handle edilmeli
                self.assertIn(path.split("?")[0], post_body,
                              f"do_POST {path} için handler içermeli")
                self.assertIn("trigger_run_now", post_body,
                              "do_POST run-now trigger_run_now çağırmalı")
            else:
                # GET-only yollar do_POST'ta explicit route olarak görünmemeli
                # (yalnızca 404 fallback'i var)
                # run-now dışındaki api path'leri post_body'de literal olarak bulunmamalı
                # (health/history vb. yanlışlıkla POST'a açılırsa sözleşme kırmızı olmalı)
                literal = f'"{path}"'
                # prefix endpoint'lerde literal yerine startswith check'i var — run-stdout için de geçerli
                if path not in ("/api/run-stdout",):
                    self.assertNotIn(literal, post_body,
                                     f"{path} GET-only ama do_POST'ta literal {literal} var")

    def test_unknown_api_returns_404_branch_exists(self):
        src = self._source()
        get_body = src.split("def do_GET(self):", 1)[1].split("def do_POST(self):", 1)[0]
        self.assertIn('startswith("/api/")', get_body,
                      "Bilinmeyen /api/* için 404 dalı bulunamadı")
        self.assertIn('"not found"', get_body)


class _StubRunNow(HTTPServer):
    """Threaded stub — SSE gibi uzun bağlantılar tek thread'i kilitlemesin."""
    def __init__(self, *a, **kw):
        import socketserver
        class _ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
            daemon_threads = True
        self.__class__ = _ThreadedHTTPServer
        HTTPServer.__init__(self, *a, **kw)
        self.run_now_calls = 0


class TestApiMethodContractLive(unittest.TestCase):
    """Canlı HTTP sözleşmesi — gerçek TCP socket üzerinden method routing."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        # Preview globals'ı tmp'ye yönlendir — serve_* dosya I/O'su izole olsun
        # PREVIEW_DIR yalnızca main()'de tanımlanır; import anında yok olabilir.
        cls._old_preview = getattr(ps, "PREVIEW_DIR", None)
        cls._old_verify = ps.VERIFY_DIR
        cls._old_history = ps.HISTORY_PATH
        cls._old_runs = ps.RUNS_DIR
        cls._old_refs = ps.REFS_TREND_PATH
        cls._old_override = ps.OVERRIDE_TREND_PATH
        ps.PREVIEW_DIR = cls.tmp.name
        ps.VERIFY_DIR = cls.tmp.name
        ps.HISTORY_PATH = os.path.join(cls.tmp.name, "history.jsonl")
        ps.RUNS_DIR = os.path.join(cls.tmp.name, "runs")
        ps.REFS_TREND_PATH = None
        ps.OVERRIDE_TREND_PATH = None
        os.makedirs(ps.RUNS_DIR, exist_ok=True)
        # Token kapalı — run-now 401 değil 200/409 dönsün
        cls._old_token = os.environ.pop("PREVIEW_RUN_NOW_TOKEN", None)

        cls.server = _StubRunNow(("127.0.0.1", 0), ps.Handler)

        def _stub(handler, _srv=cls.server):
            _srv.run_now_calls += 1
            handler._send(200, json.dumps({"status": "started"}),
                          content_type="application/json; charset=utf-8")

        cls._old_trigger = ps.Handler.trigger_run_now
        ps.Handler.trigger_run_now = _stub
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
            cls.thread.join(timeout=5)
        finally:
            ps.Handler.trigger_run_now = cls._old_trigger
            if cls._old_preview is None:
                try:
                    del ps.PREVIEW_DIR
                except AttributeError:
                    pass
            else:
                ps.PREVIEW_DIR = cls._old_preview
            ps.VERIFY_DIR = cls._old_verify
            ps.HISTORY_PATH = cls._old_history
            ps.RUNS_DIR = cls._old_runs
            ps.REFS_TREND_PATH = cls._old_refs
            ps.OVERRIDE_TREND_PATH = cls._old_override
            if cls._old_token is not None:
                os.environ["PREVIEW_RUN_NOW_TOKEN"] = cls._old_token
            else:
                os.environ.pop("PREVIEW_RUN_NOW_TOKEN", None)
            cls.tmp.cleanup()

    def _request(self, method, path):
        import urllib.request
        import urllib.error
        url = f"http://127.0.0.1:{self.server.server_address[1]}{path}"
        req = urllib.request.Request(url, method=method)
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status, dict(r.headers), r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read().decode("utf-8")

    def _request_with_headers_only(self, method, path, timeout=2):
        """SSE gibi stream endpoint'ler için header-only prob (body okumadan)."""
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=timeout)
        try:
            conn.request(method, path)
            resp = conn.getresponse()
            # Header'ları oku, body'yi tüketmeden status'ü döndür
            headers = dict(resp.getheaders())
            # SSE body sonsuz — okumadan kapat
            return resp.status, headers
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ── GET-only endpoint'ler ──

    def test_get_only_endpoints_accept_get(self):
        get_only = [p for p, m in API_CONTRACT.items() if m == {"GET"} and p not in SSE_PATHS]
        for path in get_only:
            url = LIVE_URLS[path]
            status, headers, body = self._request("GET", url)
            # /api/run-stdout kaynak yoksa 404 döner — yine de GET-izinli demektir
            if path == "/api/run-stdout":
                self.assertIn(status, (200, 404), f"GET {url} → {status}, body={body[:200]}")
            else:
                self.assertEqual(status, 200, f"GET {url} → {status}, body={body[:200]}")
            # POST aynı yola 404 dönmeli (yalnızca run-now POST)
            p_status, _, p_body = self._request("POST", url)
            self.assertEqual(p_status, 404, f"POST {url} GET-only iken {p_status} döndü (404 beklenir)")

    def test_post_only_endpoint_rejects_get_with_405(self):
        status, headers, body = self._request("GET", "/api/run-now")
        self.assertEqual(status, 405)
        self.assertEqual(headers.get("Allow"), "POST")
        payload = json.loads(body)
        self.assertEqual(payload.get("error"), "method not allowed")

    def test_post_only_endpoint_accepts_post(self):
        before = self.server.run_now_calls
        status, headers, body = self._request("POST", "/api/run-now")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body).get("status"), "started")
        self.assertGreaterEqual(self.server.run_now_calls, before + 1)
        # POST query-string varyantı da aynı
        status2, _, body2 = self._request("POST", "/api/run-now?budget=1&budget_method=universal")
        self.assertEqual(status2, 200)

    def test_post_only_endpoint_get_does_not_trigger(self):
        before = self.server.run_now_calls
        self._request("GET", "/api/run-now")
        self.assertEqual(self.server.run_now_calls, before)

    def test_unknown_api_returns_404(self):
        for method in ("GET", "POST"):
            status, _, body = self._request(method, "/api/unknown-endpoint-xyz")
            self.assertEqual(status, 404, f"{method} /api/unknown → {status}")
            if body:
                try:
                    payload = json.loads(body)
                    self.assertEqual(payload.get("error"), "not found")
                except json.JSONDecodeError:
                    pass

    def test_unsupported_method_does_not_trigger_run(self):
        before = self.server.run_now_calls
        status, _, _ = self._request("PUT", "/api/run-now")
        self.assertEqual(self.server.run_now_calls, before)
        self.assertNotEqual(status, 200)

    def test_sse_endpoints_are_get_only(self):
        for path in SSE_PATHS:
            url = LIVE_URLS[path]
            # GET → 200 + event-stream (header-only, body sonsuz)
            status, headers = self._request_with_headers_only("GET", url)
            self.assertEqual(status, 200, f"GET {url} → {status}")
            ctype = headers.get("Content-Type", "") or headers.get("Content-type", "")
            self.assertIn("text/event-stream", ctype, f"{url} Content-Type {ctype!r}")
            # POST → 404
            p_status, _, _ = self._request("POST", url)
            self.assertEqual(p_status, 404, f"POST {url} SSE iken {p_status} (404 beklenir)")

    def test_contract_is_exhaustive_no_extra_api_route_accepts_post(self):
        """Contract dışındaki hiçbir /api/* POST ile 200 almamalı (run-now hariç)."""
        for path in API_CONTRACT:
            if path == "/api/run-now":
                continue
            url = LIVE_URLS[path]
            p_status, _, _ = self._request("POST", url)
            self.assertNotEqual(p_status, 200, f"POST {url} beklenmedik 200 — contract'ta GET-only")


if __name__ == "__main__":
    unittest.main()
