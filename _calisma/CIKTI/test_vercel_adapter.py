#!/usr/bin/env python3
"""test_vercel_adapter.py — Vercel adaptörü sözleşme süiti.

Vercel'de /api yüzeyinin YEREL-DAEMON sözleşmesiyle yaşamasını sabitler:

  1) Handler-biçemi: her api/*.py top-level `handler` adını
     BaseHTTPRequestHandler-alt-sınıfı olarak tanımlar (Vercel 2026
     dosya-tabanlı Python sözleşmesi — düz-fonksiyon handler YETERSIZ,
     ölçüldü: statik-sayılıp 404 üretilir).
  2) VCS-kapsam: api/ İZLENİR (git ls-files dolu) — Git-push-deployment
     commitlenmiş ağaçtan derler; izleme-dışı api/ push-akışında
     sessizce fonksiyonsuz deploy üretir.
  3) Canlı-HTTP yüzeyi: gerçek soket üzerinden health/trend/determinism-
     trend/run-history (ağ-koşullu) + 405-gating.
  4) run-history şema-paritesi: GH-türetimi yerel satır-şemasının TAM
     anahtar-kümesi (+2 bilinçli ek: workflow, url).
  5) no-local-break: yerel-yüzey sözleşme-süitleri (api-method-matris,
     openapi) değişmeden yeşil.

OFFLINE (1,2,5) + canlı-yerel (3-yerel) + env-koşullu ağ (3-GH, 4).
"""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
API = ROOT / "api"

sys.path.insert(0, str(API))
sys.path.insert(0, str(HERE))   # preview_server + determinism_trend_badge
os.chdir(ROOT)                  # REPO_ROOT = repo-kökü (Vercel-CWD paritesi)

_FILES = ("health.py", "trend.py", "run-history.py", "determinism-trend.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ADAPTER = None
_HANDLERS = {}


def _adapter():
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = importlib.import_module("_adapter")
    return _ADAPTER


def _handler_mod(fname):
    if fname not in _HANDLERS:
        _HANDLERS[fname] = _load(fname[:-3].replace("-", "_"), API / fname)
    return _HANDLERS[fname]


def _serve(fname):
    """Gerçek-HTTP probu: handler'ı ThreadingHTTPServer ile ayağa kaldır."""
    mod = _handler_mod(fname)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), mod.handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    url = "http://127.0.0.1:%d" % srv.server_address[1]
    return srv, url


class TestVercelAdapterContract(unittest.TestCase):
    def test_handlers_are_basehttprequesthandler_subclasses(self):
        # 1) Vercel 2026 dosya-tabanlı sözleşme: top-level `handler`,
        #    BaseHTTPRequestHandler-alt-sınıfı. Düz-fonksiyon handler'lar
        #    Vercel'de statik-sayılır (ölçüldü: /api/* → 404 NOT_FOUND).
        from http.server import BaseHTTPRequestHandler
        for fname in _FILES:
            mod = _handler_mod(fname)
            self.assertTrue(hasattr(mod, "handler"),
                            "%s: top-level handler yok" % fname)
            self.assertTrue(issubclass(mod.handler, BaseHTTPRequestHandler),
                            "%s: handler BaseHTTPRequestHandler değil" % fname)

    def test_api_dir_is_git_tracked(self):
        # 2) Git-push-deployment api/'yi commitlenmiş ağaçtan alır:
        #    izleme-dışı api/ → sessizce fonksiyonsuz deploy (fail-closed).
        tracked = subprocess.run(["git", "ls-files", "api/"], cwd=ROOT,
                                 capture_output=True, text=True,
                                 timeout=10).stdout.split()
        self.assertTrue(tracked, "api/ izlenmiyor — push-deploy fonksiyonsuz olur")
        for fname in _FILES:
            self.assertIn("api/" + fname, tracked)

    def test_local_health_parity_via_real_http(self):
        # 3a) canlı-yerel: GET /api/health → 200 "ok" düz-metin.
        srv, url = _serve("health.py")
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=5) as r:
                self.assertEqual(r.status, 200)
                self.assertEqual(r.read(), b"ok")
        finally:
            srv.shutdown()

    def test_local_trend_parity_via_real_http(self):
        # 3b) canlı-yerel: {history, refs_trend} + boş-durum fallback.
        srv, url = _serve("trend.py")
        try:
            with urllib.request.urlopen(url + "/api/trend", timeout=5) as r:
                self.assertEqual(r.status, 200)
                self.assertTrue(r.headers["Content-Type"].startswith(
                    "application/json"))
                data = json.loads(r.read().decode())
            self.assertEqual(sorted(data), ["history", "refs_trend"])
        finally:
            srv.shutdown()

    def test_local_determinism_trend_via_real_http(self):
        # 3c) canlı-yerel: git'teki gerçek trend → {badge, rows}.
        srv, url = _serve("determinism-trend.py")
        try:
            with urllib.request.urlopen(url + "/api/determinism-trend",
                                        timeout=5) as r:
                data = json.loads(r.read().decode())
            self.assertEqual(sorted(data), ["badge", "rows"])
            self.assertTrue(data["rows"], "trend dosyası boş çıkması beklenmez")
        finally:
            srv.shutdown()

    def test_method_gating_405(self):
        # 3d) POST → 405 (yerel _reject_method kardeşi).
        srv, url = _serve("health.py")
        try:
            req = urllib.request.Request(url + "/api/health", data=b"{}",
                                         method="POST")
            try:
                urllib.request.urlopen(req, timeout=5)
                self.fail("POST 200 döndü")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 405)
        finally:
            srv.shutdown()

    def test_run_history_schema_parity(self):
        # 4) GH-türetimi yerel satır-şeması (+2 bilinçli ek). Ağ-koşullu.
        try:
            socket.getaddrinfo("api.github.com", 443)
        except OSError:
            self.skipTest("ağ yok — canlı-GH-API testi atlandı")
        rows = _adapter().run_history_from_github(limit=3)
        self.assertTrue(rows, "Actions-API boş döndü")
        base = {"ts", "verdict", "p0", "p1", "budget_usd", "budget_limit",
                "budget_method", "duration_s", "refs_verified", "refs_total",
                "pdf_pages", "z3_passed", "z3_total", "lean_ok", "lean_detail"}
        for row in rows:
            self.assertEqual(set(row) - base, {"workflow", "url"})
            self.assertTrue(row["ts"])
            self.assertIn(row["verdict"], {"PASS", "FAIL", "?"})

    def test_no_local_break_api_contract(self):
        # 5) no-local-break: yerel /api sözleşme-süitleri yeşil (api/
        #    dizini yerel root-mukayeselerine karışmamalı).
        for suite in ("test_api_method_contract", "test_openapi_schema"):
            r = subprocess.run(
                [sys.executable, "-m", "unittest", "_calisma.CIKTI." + suite],
                cwd=ROOT, capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0,
                             "%s kırıldı:\n%s" % (suite, r.stderr[-400:]))


if __name__ == "__main__":
    unittest.main()
