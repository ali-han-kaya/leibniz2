#!/usr/bin/env python3
"""test_api_method_matrix.py — /api/* × HTTP-metot matrisi (otomatik, fail-closed).

API_CONTRACT (test_api_method_contract tek-kaynağı) her /api/* yolu için
izinli metot kümesini taşır; bu süit o tablodan TÜM metot-hücrelerini
otomatik üretir ve gerçek HTTPServer üzerinde sabitler:

  200         metot izinli (SSE: 200 + text/event-stream, header-only prob)
  405+Allow   yol biliniyor, GET reddi açık (_reject_method) — yalnız POST-only
  404         do_GET/do_POST fallback — yol yok veya POST dağıtım-dışı (JSON)
  501         BaseHTTPRequestHandler default — do_<METHOD> tanımsız
  HEAD        bilinen yol → 200 (gövdesiz), bilinmeyen → 404
  /api/stop   POST izinli ama auth/ready-guard'lı → 403/503 (routing düzeyinde
              POST dispatch'li: 404/501 ASLA değil)

Yeni bir do_PUT/do_DELETE eklenirse matris 501 hücrelerinde KIRMIZI düşer —
sözleşme değişikliği bilinçli yapılmak zorunda (fail-closed). Kaynak-testi
(test_api_method_contract) tablo↔_route eşleşmesini pinler; bu süit ise
DAVRANIŞI canlı sokette pinler. İkisi birlikte: tablo-drift ve davranış-drift
ikisi de pre-commit'te yakalanır.

Sabitler (bu turun canlı-prob kanıtıyla eşleşir):
  GET /api/run-now  → 405, Allow: POST, {"error": "method not allowed"}
  POST /api/latest  → 404, {"error": "not found"}
  PUT  /api/latest  → 501 (HTML, handler yok)
"""
import json
import os
import pathlib
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer
import http.client
import socketserver

CIKTI = pathlib.Path(__file__).resolve().parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import preview_server as ps  # noqa: E402
from test_api_method_contract import API_CONTRACT, LIVE_URLS, SSE_PATHS  # noqa: E402

# Matrisin taradığı metotlar (HEAD ayrı: gövdesiz sözleşmesi).
METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE")
# do_ handler'ı tanımsız → BaseHTTPRequestHandler 501 döndürür.
UNSUPPORTED = frozenset({"PUT", "DELETE", "PATCH", "OPTIONS", "TRACE"})
# State-changing uçlar: başka metotla ASLA tetiklenmemeli (sayaç-sabiti).
STATE_CHANGING = {"/api/run-now", "/api/stop"}


def expected_for(path, method):
    """Matris hücresinin beklenen durumunu üretir (saf; KeyError = fail-closed).

    API_CONTRACT'ta olmayan yol bu fonksiyona hiç gelmemeli — matris
    kaynağı o tablodur; bilinmeyen yol test_seti hata verir (sessiz PASS yok).
    """
    allowed = API_CONTRACT[path]  # KeyError → fail-closed
    if path in SSE_PATHS and method == "GET":
        return (200,)  # SSE: header-only prob — 200 + event-stream ayrı pinli
    if method in allowed:
        if path == "/api/run-stdout":
            # Veri-bağımlı uç: ts kaynakta yoksa handler kendi alan-404'ünü
            # verir (meşru); yönlendirme-404'ü ise yalnız fallback hücrelerindir.
            return (200, 404)
        return (200,) if path != "/api/stop" else (403, 503)  # guarded POST
    if method == "GET":
        return (405,)  # açık GET-reddi (POST-only uçlar)
    if method == "POST":
        return (404,)  # do_POST fallback — JSON "not found"
    return (501,)  # UNSUPPORTED: do_<METHOD> tanımsız


class _ThreadedStubServer(HTTPServer):
    """Threading server + trigger_run_now sayacı (gerçek run başlatmaz)."""

    def __init__(self, *a, **kw):
        class _T(socketserver.ThreadingMixIn, HTTPServer):
            daemon_threads = True
        self.__class__ = _T
        HTTPServer.__init__(self, *a, **kw)
        self.run_now_calls = 0


class TestApiMethodMatrix(unittest.TestCase):
    """Canlı soket matrisi: her /api/* yolu × tüm metotlar."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls._old = {
            "PREVIEW_DIR": getattr(ps, "PREVIEW_DIR", None),
            "VERIFY_DIR": ps.VERIFY_DIR,
            "HISTORY_PATH": ps.HISTORY_PATH,
            "RUNS_DIR": ps.RUNS_DIR,
            "REFS_TREND_PATH": ps.REFS_TREND_PATH,
            "OVERRIDE_TREND_PATH": ps.OVERRIDE_TREND_PATH,
        }
        ps.PREVIEW_DIR = cls.tmp.name
        ps.VERIFY_DIR = cls.tmp.name
        ps.HISTORY_PATH = os.path.join(cls.tmp.name, "history.jsonl")
        ps.RUNS_DIR = os.path.join(cls.tmp.name, "runs")
        ps.REFS_TREND_PATH = None
        ps.OVERRIDE_TREND_PATH = None
        os.makedirs(ps.RUNS_DIR, exist_ok=True)
        cls._old_token = os.environ.pop("PREVIEW_RUN_NOW_TOKEN", None)

        cls.server = _ThreadedStubServer(("127.0.0.1", 0), ps.Handler)

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
        try:
            cls.server.shutdown()
            cls.server.server_close()
            cls.thread.join(timeout=5)
        finally:
            ps.Handler.trigger_run_now = cls._old_trigger
            for k, v in cls._old.items():
                if v is None and k == "PREVIEW_DIR":
                    try:
                        delattr(ps, k)
                    except AttributeError:
                        pass
                else:
                    setattr(ps, k, v)
            if cls._old_token is not None:
                os.environ["PREVIEW_RUN_NOW_TOKEN"] = cls._old_token
            else:
                os.environ.pop("PREVIEW_RUN_NOW_TOKEN", None)
            cls.tmp.cleanup()

    # ── prob yardımcıları ──

    def _probe(self, method, path, header_only=False):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=3)
        try:
            conn.request(method, path)
            resp = conn.getresponse()
            body = b"" if header_only else resp.read()
            return resp.status, resp.getheader("Allow"), body
        finally:
            conn.close()

    # ── matris ──

    def test_matrix_auto_generated_from_contract(self):
        """Her sözleşme-yolu × tüm metotlar: hücre = expected_for(path, m).

        Otomatik üretim: API_CONTRACT'a yeni yol eklenirse matrise de otomatik
        düşer (bu testin döngüsü kaynağı okur) — iki liste sürdürülmez.
        """
        for path in sorted(API_CONTRACT):
            url = LIVE_URLS[path]
            allowed = API_CONTRACT[path]
            for method in METHODS:
                with self.subTest(path=path, method=method):
                    expected = expected_for(path, method)
                    header_only = path in SSE_PATHS and method == "GET"
                    status, allow, body = self._probe(method, url,
                                                      header_only=header_only)
                    self.assertIn(status, expected,
                                  f"{method} {url} → {status} "
                                  f"(beklenen {expected}); body={body[:120]!r}")
                    if status == 405:
                        self.assertEqual(allow, "POST",
                                         "405 hücresi Allow: POST taşımali")
                        payload = json.loads(body.decode("utf-8"))
                        self.assertEqual(payload.get("error"),
                                         "method not allowed")
                    elif status == 404 and method in allowed:
                        # İzinli-metot hücresinde 404 yalnız domain-hatası
                        # olabilir; yönlendirme-fallback'i ("not found") bu
                        # hücrelerde görmek bir dağıtım-kusurudur (fail-closed).
                        try:
                            payload = json.loads(body.decode("utf-8"))
                        except (ValueError, UnicodeDecodeError):
                            payload = {}
                        self.assertNotEqual(
                            payload.get("error"), "not found",
                            f"{method} {url}: izinli-metot hücresi yönlendirme-"
                            "404 döndürdü — handler alan-hatası vermeli")

    def test_matrix_covers_head_bodyless(self):
        """HEAD: bilinen yol → 200 gövdesiz; bilinmeyen → 404."""
        status, _, body = self._probe("HEAD", "/api/latest")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        status, _, _ = self._probe("HEAD", "/api/unknown-xyz")
        self.assertEqual(status, 404)

    def test_unknown_path_full_method_row(self):
        """Bilinmeyen /api/* satırı: GET/POST→404 JSON, diğerleri→501."""
        path = "/api/unknown-matrix-row"
        status, _, body = self._probe("GET", path)
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body.decode("utf-8")).get("error"),
                         "not found")
        status, _, body = self._probe("POST", path)
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body.decode("utf-8")).get("error"),
                         "not found")
        for method in sorted(UNSUPPORTED):
            with self.subTest(method=method):
                status, _, _ = self._probe(method, path)
                self.assertEqual(status, 501)

    def test_unsupported_methods_stay_501_everywhere(self):
        """501 ayrımı tüm sözleşme-yollarında sabit — yeni do_PUT eklenirse kırmızı."""
        for path in sorted(API_CONTRACT):
            url = LIVE_URLS[path]
            for method in sorted(UNSUPPORTED):
                with self.subTest(path=path, method=method):
                    status, _, _ = self._probe(method, url)
                    self.assertEqual(status, 501,
                                     f"{method} {url} → {status}: do_{method} "
                                     "eklendi mi? Sözleşmeyi bilinçli güncelle")

    def test_state_changing_endpoints_not_triggerable_by_other_methods(self):
        """/api/run-now yalnızca stub'a ulaşabilmeli; diğer tüm metotlar tetiklemez.

        /api/stop dahil edilmez: gerçek stop_server() stub'sız daemon'ı
        kapatır — routing reddi (405/404/501 hücreleri) matriste pinli.
        """
        before = self.server.run_now_calls
        for method in ("GET", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE"):
            with self.subTest(method=method):
                self._probe(method, "/api/run-now")
        self.assertEqual(self.server.run_now_calls, before,
                         "run-now izinli-metot dışında bir yolla tetiklendi")

    def test_matrix_expects_post_allowed_only_on_post_only_paths(self):
        """POST→200 hücresi yalnız POST-only yollarda var olabilir (run-now stub'lı)."""
        for path in sorted(API_CONTRACT):
            if path in STATE_CHANGING:
                continue
            status, _, _ = self._probe("POST", LIVE_URLS[path])
            self.assertNotEqual(status, 200,
                                f"POST {path} → 200: sözleşme-dışı POST-izin")


if __name__ == "__main__":
    unittest.main()
