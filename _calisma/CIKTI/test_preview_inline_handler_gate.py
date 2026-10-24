#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SECURITY-TIER: static
"""test_preview_inline_handler_gate.py — CSP inline-handler kapısı (fail-closed).

VERIFY-001 sınıfı: CSP `script-src 'self' + nonce` altında **nitelik**
handler'lar (`onclick="…"`, `onmousemove="…"`) nonce kapsamına girmez;
tarayıcı bunları sessizce bloklar. Görünür hata yoktur — düğme/hover ölür.

Bu modül sayacı AYRI bir güvenlik kapısına taşır (`check-security-posture`
statik tier'ı). Ölçülen tek şey SAYAÇTIR: preview yüzeylerinde inline
`on*` niteliği varsa `sayac != 0` → FAIL. Kapsam:

  1. Diskteki gerçek `.html` kümesi + `preview.js` + her koşuda üreticiden
     gelen `design_preview.html` (commit dışı kopya bayat olabilir).
  2. Sunucunun GERÇEKTEN gönderdiği baytlar (`/` ve `/preview.js`) —
     enjeksiyon sonrası yüzeyde handler doğmuyorsa kanıt tamamdır.

Fail-closed: üretici çalışmazsa ya da beklenen yüzeyler eksikse test
KIRMIZI olur (SKIP değil). Sayaç `preview_inline_audit.py`'de tek kaynaktır;
`test_preview_server.py` de aynı fonksiyonu kullanır.

Çalıştırma:
    python3 -m unittest _calisma.CIKTI.test_preview_inline_handler_gate -v
"""
from __future__ import annotations

import pathlib
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import preview_inline_audit as audit  # noqa: E402
import preview_server as ps  # noqa: E402


class CounterSelfTest(unittest.TestCase):
    """Sayaç körelirse kapı sessizce yeşile yanmasın."""

    def test_counts_historical_verify_001_markup(self):
        historical = (
            '<rect fill="transparent" onmousemove="showRefsTrendTip(0, event)"'
            ' onmouseleave="hideTrendTip()"/>'
            '<button onclick="setRhFilter(\'PASS\')">PASS</button>'
        )
        self.assertEqual(len(audit.count_inline_handlers(historical)), 3)

    def test_counts_handler_at_start_and_ignores_data_attributes(self):
        self.assertEqual(
            len(audit.count_inline_handlers('onload="boot()"')), 1)
        self.assertEqual(
            len(audit.count_inline_handlers(' data-onclick="x"')), 0)
        self.assertEqual(
            len(audit.count_inline_handlers('connection="keep-alive"')), 0)


class ServedSurfaceInlineHandlerGate(unittest.TestCase):
    def test_static_surfaces_have_zero_inline_handlers(self):
        surfaces = audit.served_surfaces(HERE)
        self.assertGreaterEqual(
            len(surfaces), len(audit.REQUIRED_SURFACES),
            "taranan yüzey sayısı beklenenden az (%d): %s"
            % (len(surfaces), sorted(surfaces)))
        for required in audit.REQUIRED_SURFACES:
            self.assertIn(required, surfaces)
        self.assertGreater(
            len(surfaces["preview.html"]), 10_000,
            "preview.html beklenmedik derecede küçük")

        total = 0
        offenders = {}
        for name, text in surfaces.items():
            hits = audit.count_inline_handlers(text)
            total += len(hits)
            if hits:
                offenders[name] = hits[:5]
        self.assertEqual(
            total, 0,
            "inline-event-handler sayacı %d (sıfır olmalı) — CSP altında bu "
            "handler'lar SESSİZCE ölür. Yüzeyler: %r" % (total, offenders))


class HttpServedSurfaceInlineHandlerGate(unittest.TestCase):
    """Sunucunun gönderdiği baytlar: enjeksiyon sonrası sayaç yine 0."""

    @classmethod
    def setUpClass(cls):
        cls._old_preview_dir = getattr(ps, "PREVIEW_DIR", None)
        ps.PREVIEW_DIR = str(HERE)
        # Okuma yolu repo'da kalır (gerçek sayfa servis edilir) ama sunucunun
        # YAZDIĞI dosyalar geçici dizine gider — in-process test ağacı
        # kirletmesin (history.jsonl / logs/ / runs/).
        from preview_test_env import in_process_runtime
        cls._runtime = in_process_runtime(ps, "inline-handler")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ps.Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls._runtime.restore(ps)
        if cls._old_preview_dir is None:
            if hasattr(ps, "PREVIEW_DIR"):
                del ps.PREVIEW_DIR
        else:
            ps.PREVIEW_DIR = cls._old_preview_dir

    def _fetch(self, path):
        req = urllib.request.Request(self.base + path,
                                     headers={"Host": "127.0.0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")

    def test_served_page_and_bundle_have_zero_inline_handlers(self):
        status, body = self._fetch("/")
        self.assertEqual(status, 200)
        self.assertIn("<script", body, "servis edilen sayfa script taşımıyor")
        self.assertEqual(
            audit.count_inline_handlers(body), [],
            "servis edilen / yüzeyinde inline handler var — CSP altında "
            "SESSİZCE ölür")

        status, bundle = self._fetch("/preview.js")
        self.assertEqual(status, 200)
        self.assertGreater(len(bundle), 50_000,
                           "preview.js beklenmedik derecede küçük")
        self.assertEqual(
            audit.count_inline_handlers(bundle), [],
            "servis edilen /preview.js ürettiği işaretlemede inline handler "
            "var — CSP altında SESSİZCE ölür")


if __name__ == "__main__":
    unittest.main()
