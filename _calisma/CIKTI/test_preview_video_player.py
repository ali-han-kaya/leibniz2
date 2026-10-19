#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_preview_video_player.py — preview sunucusu LeibnizChain oynatma yuzeyi.

Kapsanan sozlesmeler:
  1. Rota kaydi: `/video.html` ve `/video/*` dogru rotaya duser; `/video`
     (sonu olmayan) ve `/video/...` disi yollar 404 kalir.
  2. Allowlist: yalnizca player.js / player.css / leibniz.json servis edilir.
     Yol kacisi (`..`), dizin listelemesi ve dis uzantilar 404.
  3. Fail-closed: paket (dist/) uretilmemisse sayfa 404 doner ve ne yapilacagini
     soyleyen mesaj verir — bos sayfa degil.
  4. CSP: sayfada INLINE script yoktur (sunucu `script-src 'self' 'nonce-…'`
     uygular; nonce'siz inline script calismaz). Paket harici dosyadan gelir,
     veri `data-src` niteligiyle tasinir.
  5. Icerik turu: player.js metin/javascript olarak servis edilir.

Gercek paket uretilmemis olabilir (node_modules/dist ignore'da) — bu yuzden
testler gecici bir dist ağaci kurar, canli dist'e BAKMAZ; boylece temiz
klonda da anlamli sonuc verir.
"""

import os
import pathlib
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import preview_server as ps  # noqa: E402

PLAYER_JS = b"/* player bundle */\n"
PLAYER_CSS = b"body{color:#fff}\n"
DATA = b'{"meta":{"frames":760}}\n'
PAGE = (b'<!doctype html><html><body>'
        b'<div id="root" data-src="/video/leibniz.json"></div>'
        b'<script src="/video/player.js" defer></script></body></html>')


def _fake_handler(path, sent):
    h = object.__new__(ps.Handler)
    h.path = path
    h._send = lambda status, body, content_type="", extra_headers=None: sent.append(
        (status, body, content_type))
    return h


class VideoRouteTestBase(unittest.TestCase):
    def setUp(self):
        self._saved = getattr(ps, "VIDEO_DIST", None)
        self.tmp = tempfile.TemporaryDirectory(prefix="video-dist-")
        self.addCleanup(self.tmp.cleanup)
        self.dist = pathlib.Path(self.tmp.name)
        ps.VIDEO_DIST = self.tmp.name
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            del ps.VIDEO_DIST
        else:
            ps.VIDEO_DIST = self._saved

    def _write_all(self):
        (self.dist / "player.js").write_bytes(PLAYER_JS)
        (self.dist / "player.css").write_bytes(PLAYER_CSS)
        (self.dist / "leibniz.json").write_bytes(DATA)
        (self.dist / "player.html").write_bytes(PAGE)

    def _get(self, path):
        sent = []
        handler = _fake_handler(path, sent)
        return handler, sent


class TestRouteTable(VideoRouteTestBase):
    def test_page_route(self):
        self.assertEqual(ps._route("/video.html"), "video")
        self.assertEqual(ps._route("/video.html?_t=1"), "video")

    def test_asset_route(self):
        for name in ("player.js", "player.css", "leibniz.json"):
            self.assertEqual(ps._route("/video/" + name), "video_asset", name)

    def test_bare_video_is_not_a_route(self):
        """`/video` (sonu olmayan) bir sayfa DEGIL — 404 kalmali."""
        self.assertIsNone(ps._route("/video"))

    def test_unknown_video_path_still_matches_asset_branch(self):
        """Rota `video_asset` doner; dosya bazli karar serve icinde verilir."""
        self.assertEqual(ps._route("/video/secrets.txt"), "video_asset")


class TestServePage(VideoRouteTestBase):
    def test_serves_html_when_built(self):
        self._write_all()
        _, sent = self._get("/video.html")
        ps.Handler.serve_video(_fake_handler("/video.html", sent))
        self.assertEqual(sent[-1][0], 200)
        self.assertEqual(sent[-1][2], "text/html; charset=utf-8")
        self.assertIn('id="root"', sent[-1][1])  # _send metni str olarak saklar

    def test_fail_closed_404_with_instructions_when_not_built(self):
        """Paket yoksa bos sayfa degil, YOL GOSTEREN mesaj doner."""
        sent = []
        ps.Handler.serve_video(_fake_handler("/video.html", sent))
        self.assertEqual(sent[-1][0], 404)
        self.assertIn("build:player", sent[-1][1])

    def test_page_has_no_inline_script(self):
        """CSP `script-src 'self' 'nonce-…'`: nonce'siz inline script calismaz.

        Kaynak `_calisma/video/build/player.html` denetlenir (dist kopyasi
        degil) — derleme sirasinda kopya degismez.
        """
        src = pathlib.Path(HERE).parent / "video" / "build" / "player.html"
        html = src.read_text(encoding="utf-8")
        for line in html.splitlines():
            if "<script" in line and "src=" not in line:
                self.fail(f"inline script bulundu (CSP'ye aykir): {line.strip()}")
        self.assertIn('src="/video/player.js"', html)
        self.assertIn('data-src="/video/leibniz.json"', html)

    def test_page_mount_point_matches_bundle(self):
        """Sayfa #root bekliyor; paket #root yoksa gorunur hata basar."""
        src = pathlib.Path(HERE).parent / "video" / "build" / "player.html"
        self.assertIn('id="root"', src.read_text(encoding="utf-8"))
        entry = pathlib.Path(HERE).parent / "video" / "src" / "player.tsx"
        code = entry.read_text(encoding="utf-8")
        self.assertIn('getElementById("root")', code)
        self.assertIn("data-src", code)


class TestServeAssets(VideoRouteTestBase):
    def test_serves_each_allowlisted_asset(self):
        self._write_all()
        for name, ctype, body in (
            ("player.js", "text/javascript; charset=utf-8", PLAYER_JS),
            ("player.css", "text/css; charset=utf-8", PLAYER_CSS),
            ("leibniz.json", "application/json; charset=utf-8", DATA),
        ):
            sent = []
            ps.Handler.serve_video_asset(_fake_handler("/video/" + name, sent))
            self.assertEqual(sent[-1][0], 200, name)
            self.assertEqual(sent[-1][2], ctype, name)
            self.assertEqual(sent[-1][1], body, name)

    def test_traversal_and_unknown_names_404(self):
        self._write_all()
        for bad in ("secrets.txt", "player.js.map", "", "sub/player.js",
                    "../package.json", "player.HTML"):
            sent = []
            ps.Handler.serve_video_asset(_fake_handler("/video/" + bad, sent))
            self.assertEqual(sent[-1][0], 404, bad)

    def test_missing_file_404(self):
        """Allowlist'te ama diskte yoksa 404 (bos govde degil)."""
        sent = []
        ps.Handler.serve_video_asset(_fake_handler("/video/player.js", sent))
        self.assertEqual(sent[-1][0], 404)

    def test_allowlist_is_explicit_and_minimal(self):
        """Yeni varlik eklenirse burasi da guncellenmeli — gizli genislemeye kapi yok."""
        self.assertEqual(set(ps.VIDEO_ASSETS),
                         {"player.js", "player.css", "leibniz.json"})


class TestSecurityHeaders(unittest.TestCase):
    def test_csp_allows_self_scripts_only(self):
        csp = dict(ps.Handler._SECURITY_HEADERS).get("Content-Security-Policy", "")
        self.assertIn("script-src 'self'", csp)
        self.assertIn("default-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_video_routes_are_outside_host_origin_gate(self):
        """Statik varliklar veri tasimaz; DNS-rebinding kapisi disinda kalmali."""
        self.assertNotIn("video", ps._API_GET_ROUTES)
        self.assertNotIn("video_asset", ps._API_GET_ROUTES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
