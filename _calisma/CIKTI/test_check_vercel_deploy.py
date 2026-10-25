#!/usr/bin/env python3
"""test_check_vercel_deploy.py — check_vercel_deploy kapisi sozlesmesi.

Gerçek HTTP (ThreadingHTTPServer) ile: PASS senaryosu, bozuk-saglik,
bozuk-sema (eksik alan / gecersiz verdict / JSON degil), slayt-404,
slayt-PNG-degil, uc-olu ve gecersiz-scheme — hepsi fail-closed (exit 1).
Ag-dis: kendi sunucusu.
"""
import contextlib
import importlib.util
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PNG_DEFAULT = b"\x89PNG\r\n\x1a\n" + b"fixture-bytes"
spec = importlib.util.spec_from_file_location(
    "check_vercel_deploy", HERE / "check_vercel_deploy.py")
CVD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CVD)


class _Handler(BaseHTTPRequestHandler):
    health_body = "ok"
    history_body = "[]"
    slide_body = PNG_DEFAULT

    def do_GET(self):
        if self.path == "/api/health":
            body = self.health_body.encode()
            self.send_response(200)
        elif self.path == "/api/run-history":
            body = self.history_body.encode()
            self.send_response(200)
        elif self.path == "/slides_z3/P1-a.png":
            if _Handler.slide_body is None:
                body = b"not found"
                self.send_response(404)
            else:
                body = _Handler.slide_body
                self.send_response(200)
        else:
            body = b"not found"
            self.send_response(404)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TestCheckVercelDeploy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        t.start()
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def _serve(self, health, history, slide=PNG_DEFAULT):
        _Handler.health_body = health
        _Handler.history_body = history
        _Handler.slide_body = slide
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = CVD.main(["--base-url", self.base])
        return rc, buf.getvalue()

    def test_pass_when_all_endpoints_healthy(self):
        rc, out = self._serve("ok", json.dumps(
            [{"ts": "2026-10-08T17:59:52Z", "verdict": "PASS"}]))
        self.assertEqual(rc, 0, out)
        self.assertIn("VERDICT: PASS", out)

    def test_fail_when_health_body_wrong(self):
        rc, out = self._serve("healthy", json.dumps(
            [{"ts": "x", "verdict": "PASS"}]))
        self.assertEqual(rc, 1, out)
        self.assertIn("api/health: **FAIL**", out)

    def test_fail_when_history_schema_missing_key(self):
        rc, out = self._serve("ok", json.dumps([{"ts": "x"}]))
        self.assertEqual(rc, 1, out)
        self.assertIn("sema eksik", out)

    def test_fail_when_history_verdict_invalid(self):
        rc, out = self._serve("ok", json.dumps(
            [{"ts": "x", "verdict": "MAYBE"}]))
        self.assertEqual(rc, 1, out)
        self.assertIn("verdict gecersiz", out)

    def test_fail_when_history_not_json(self):
        rc, out = self._serve("ok", "<html>503</html>")
        self.assertEqual(rc, 1, out)
        self.assertIn("JSON degil", out)

    def test_fail_when_history_empty_list(self):
        rc, out = self._serve("ok", "[]")
        self.assertEqual(rc, 1, out)

    def test_fail_when_slide_missing(self):
        # statik-upload 404 (.vercelignore dir-prune): API'ler yesilken
        # kapinin REDDEDEBILMESI lazim (2026-10-09 arizasinin kendisi).
        rc, out = self._serve("ok", json.dumps(
            [{"ts": "x", "verdict": "PASS"}]), slide=None)
        self.assertEqual(rc, 1, out)
        self.assertIn("slides_z3/P1-a.png: **FAIL**", out)

    def test_fail_when_slide_not_png(self):
        rc, out = self._serve("ok", json.dumps(
            [{"ts": "x", "verdict": "PASS"}]), slide=b"<html>oops</html>")
        self.assertEqual(rc, 1, out)
        self.assertIn("PNG magic yok", out)

    def test_fail_when_host_unreachable(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = CVD.main(["--base-url", "http://127.0.0.1:9"])
        self.assertEqual(rc, 1, buf.getvalue())

    def test_fail_on_invalid_scheme(self):
        rc = CVD.main(["--base-url", "ftp://yanlis"])
        self.assertEqual(rc, 1)


class TestStablePreviewAliasContract(unittest.TestCase):
    """Sabit preview alias sözleşmesi (2026-10-25).

    Aylık `vercel-deploy-check` artık Vercel API'sine bağlı kalmadan TEK bir
    sabit adı denetler (`vars.VERCEL_PREVIEW_URL` =
    `https://leibniz2-preview.vercel.app`). Bu, ancak alias her preview
    deploy'unda ilerletilirse anlamlıdır; ilerletilmezse kapı eski bir
    deployment'ı "preview sağlıklı" diye raporlar (sessiz yanlış-PASS).
    """

    ROOT = HERE.parent.parent
    ALIAS = "leibniz2-preview.vercel.app"

    def _text(self, workflow):
        return (self.ROOT / ".github" / "workflows" / workflow).read_text(
            encoding="utf-8")

    def test_preview_deploy_advances_alias_after_deploy(self):
        text = self._text("vercel-preview-deploy.yml")
        self.assertIn(f"vercel alias set \"$PREVIEW_URL\" {self.ALIAS}", text)
        deploy = text.index("- name: Preview deploy")
        alias = text.index("- name: Sabit preview alias")
        verify = text.index("- name: 4 /api ucu dogrulama")
        self.assertLess(deploy, alias,
                        "alias adımı deploy'dan ÖNCE çalışıyor (URL henüz yok)")
        self.assertLess(alias, verify,
                        "alias adımı /api doğrulamasından sonra (geç kalmış)")

    def test_alias_step_is_fail_closed(self):
        text = self._text("vercel-preview-deploy.yml")
        start = text.index("- name: Sabit preview alias")
        end = text.index("- name: 4 /api ucu dogrulama", start)
        step = text[start:end]
        self.assertIn("set -euo pipefail", step)
        self.assertNotIn("continue-on-error", step,
                         "alias kapısı advisory'e düşürülmüş")
        self.assertIn("exit 1", step,
                      "alias /api/health 200 dönmezse job kırılmalı")
        self.assertIn("/api/health", step)

    def test_monthly_check_reads_variable_and_never_falls_back_to_prod(self):
        text = self._text("vercel-deploy-check.yml")
        self.assertIn("vars.VERCEL_PREVIEW_URL", text)
        self.assertNotIn("https://leibniz2.vercel.app", text,
                         "prod alias'ı fallback olarak gömülmüş "
                         "(2026-10-24 prod-fallback yasağı)")

    def test_docs_name_the_same_alias(self):
        doc = (self.ROOT / "docs" / "VERCEL_DEPLOYMENT.md").read_text(
            encoding="utf-8")
        self.assertIn(self.ALIAS, doc,
                      "sabit alias dokümanda geçmiyor (doc↔workflow drift)")
        self.assertIn("vars.VERCEL_PREVIEW_URL", doc)


if __name__ == "__main__":
    unittest.main()
