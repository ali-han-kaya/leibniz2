#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SECURITY-TIER: static
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
  6. Pano karti: `preview.html` oynatma yuzeyini KART olarak tasir;
     player.js lazy (gorunurluk / dugme) enjekte edilir, enjeksiyon
     basarisizsa build talimatli hata kutusu acilir.

Gercek paket uretilmemis olabilir (node_modules/dist ignore'da) — bu yuzden
testler gecici bir dist ağaci kurar, canli dist'e BAKMAZ; boylece temiz
klonda da anlamli sonuc verir.
"""

import json
import os
import pathlib
import re
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


class PreviewVideoCardTests(unittest.TestCase):
    """Pano video kartı: lazy yükleme + fail-closed build talimatı.

    Oynatma yüzeyi ayrı sekme (`/video.html`) olarak da duruyor; pano içinde
    ise KART olarak yaşar. Kartın sözleşmesi:
      - `player.js` sayfaya sabit <script> ile GÖMÜLMEZ (pano açılışına
        React + @remotion/player eklemek her ziyaretçiye ~1 MB indirirdi);
        paket yalnız kart viewport'a yaklaşınca ya da düğmeyle enjekte edilir.
      - Montaj noktası `#root` + `data-src` player paketinin beklediğiyle
        birebir aynıdır (player.tsx `getElementById("root")` / `data-src`).
      - Paket derlenmemişse (temiz klon → `_calisma/video/dist/` yok →
        `/video/player.js` 404) `onerror` build talimatlı hata kutusunu açar:
        boş kutu yok, fail-closed.

    Davranış katmanı (tıklama → enjeksiyon → onload/onerror) tarayıcısız
    `test_preview_interaction_dom.js` içinde gerçek preview.js koşularak
    ölçülür; burada yalnız kaynak sözleşmesi pinlenir.
    """

    @classmethod
    def setUpClass(cls):
        here = pathlib.Path(HERE)
        cls.html = (here / "preview.html").read_text(encoding="utf-8")
        cls.js = (here / "preview.js").read_text(encoding="utf-8")

    def _card(self):
        start = self.html.index('id="video-card"')
        return self.html[start:self.html.index("</section>", start)]

    def test_card_mounts_player_root_with_data_src(self):
        """Kart, player paketinin beklediği montaj noktasını taşır."""
        card = self._card()
        self.assertIn('id="root" data-src="/video/leibniz.json"', card)
        self.assertIn('<div id="video-stage" hidden>', card)

    def test_player_bundle_is_not_eagerly_linked(self):
        """`<script src="/video/player.js">` sabit değil — lazy enjeksiyon."""
        self.assertNotIn('src="/video/player.js"', self.html)
        self.assertIn('script.src = "/video/player.js"', self.js)

    def test_lazy_trigger_and_delegation_are_wired(self):
        """Görünürlük tetikleyicisi + CSP-uyumlu delege tıklaması."""
        self.assertIn("IntersectionObserver", self.js)
        self.assertIn("initVideoCard();", self.js)
        self.assertIn('t.dataset.act === "video-load"', self.js)
        self.assertIn('data-act="video-load"', self._card())

    def test_error_path_is_hidden_until_failure_and_names_build(self):
        """Hata kutusu `hidden` başlar; build komutu metnin İÇİNDE durur.

        JS yalnız görünürlüğü çevirir; talimatın kendisi HTML'de yoksa
        "yükleme başarısızlığında talimat göster" iddiası boş olurdu.
        """
        card = self._card()
        self.assertIn('<div id="video-error" class="err" role="alert" hidden',
                      card)
        self.assertIn('id="video-error-detail"', card)
        for cmd in ("cd _calisma/video", "npm ci", "npm run build:player"):
            self.assertIn(cmd, card)

    def test_error_handler_and_state_guard_exist(self):
        """`onerror` GERÇEKTEN talimatı açar; çift enjeksiyon durumla kesilir.

        `script.onerror` alt-dizisi tek başına yetmez: `script.onerror = null`
        da onu içerir. Bu yüzden handler gövdesi ve çağırdığı fonksiyon pinlenir.
        """
        self.assertIn("script.onerror = () => {", self.js)
        self.assertIn(
            'showVideoBuildInstructions("/video/player.js yüklenemedi")', self.js)
        self.assertIn('videoLoadState === "loaded"', self.js)
        self.assertIn('videoLoadState = "failed"', self.js)


class TestPlayerA11ySource(unittest.TestCase):
    """/video.html oynatıcı yüzeyinin erişilebilirlik sözleşmesi.

    a11y_gate bu yüzeyi tarar (a11y_gate_config.json `/video.html`). Kapının
    yeşil kalmasının nedeni ÖLÇÜLEBİLİR olması: kontroller bizim çubuğumuzda
    (Remotion'in hazır `controls` çubuğu İngilizce sabit etiketler taşır ve
    `aria-pressed` yaymaz), çubuk OPAK zeminlidir (yarı saydam katmanda axe
    color-contrast'ı "incomplete" yapar) ve odak halkası 2px'tir.

    Bu testler kaynak sözleşmesini pinler; canlı doğrulama a11y_gate'in
    /video.html koşumudur (rapor: theme, node sayıları, aria etiketleri).
    """

    ROOT = pathlib.Path(HERE).parent / "video"

    def _read(self, rel):
        return (self.ROOT / rel).read_text(encoding="utf-8")

    @staticmethod
    def _code(text):
        """Yorumları ayıkla.

        Gerekçe ÖLÇÜLDÜ: `PlayerControls.tsx` docstring'i İngilizce etiketleri
        REGRESYON olarak anıyor; ham metinde arayan bir `assertNotIn` kendi
        gerekçesini yakalayıp sahte kırmızı verdi. İddia kod üzerinedir.
        """
        without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        without_line = re.sub(r"//[^\n]*", "", without_block)
        return re.sub(r"<!--.*?-->", "", without_line, flags=re.S)

    def test_player_uses_own_controls_not_remotion_english_bar(self):
        code = self._code(self._read("src/player.tsx"))
        self.assertIn("controls={false}", code)
        self.assertIn("PlayerControls", code)
        # Regresyon: `controls` açılırsa Remotion "Play video"/"Mute sound"
        # etiketleri Türkçe sayfaya geri döner (WCAG 3.1.2).
        self.assertNotIn("controls\n", code.replace("controls={false}", ""))

    def test_control_labels_are_turkish_and_stateful(self):
        src = self._code(self._read("src/PlayerControls.tsx"))
        for label in ('"Oynat"', '"Duraklat"', '"Sesi kapat"', '"Sesi aç"',
                      '"Tam ekran"', '"Tam ekrandan çık"'):
            self.assertIn(label, src)
        self.assertNotIn('"Play video"', src)
        self.assertNotIn('"Enter Fullscreen"', src)

    def test_controls_expose_state_and_group_name(self):
        src = self._code(self._read("src/PlayerControls.tsx"))
        self.assertIn('role="group"', src)
        self.assertIn('aria-label="Oynatıcı kontrolleri"', src)
        self.assertEqual(src.count("aria-pressed="), 2,
                         "ses + tam ekran düğmeleri durum bildirmeli")
        self.assertIn("aria-valuetext={position}", src)
        self.assertIn('aria-label="Oynatma konumu"', src)
        self.assertIn('aria-hidden="true"', src)

    def test_control_bar_is_opaque_and_focus_ring_is_2px(self):
        css = self._read("build/player.css")
        bar = css.split(".lc-controls {", 1)[1].split("}", 1)[0]
        self.assertIn("background: var(--panel)", bar)
        self.assertNotIn("rgba(", bar.split("background:", 1)[1].split(";", 1)[0])
        focus = css.split(".lc-controls__button:focus-visible", 1)[1]
        self.assertIn("outline: 2px solid", focus)
        self.assertIn("outline-offset: 2px", focus)

    def test_page_has_main_landmark_and_single_h1(self):
        html = self._code(self._read("build/player.html"))
        self.assertEqual(html.count("<main>"), 1)
        self.assertEqual(html.count("<h1>"), 1)
        self.assertIn('lang="tr"', html)
        # a11y_gate witness'ı gövde metninden doğrular.
        self.assertIn("LeibnizChain", html)


class TestPlayerRouteGate(unittest.TestCase):
    """`_calisma/video/check_player_routes.py` — paket + /video/* rota kapısı.

    `dist/` gitignore'da olduğu için "paket yok" durumu sessizce yeşil
    kalabilirdi; bu sınıf kapının gerçek HTTP üzerinden 200/404 sözleşmesini
    ve fail-closed dallarını sınar. Sahte dist testte kurulur (canlı dist'e
    BAKMAZ) — temiz klonda da anlamlı.
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util

        path = pathlib.Path(HERE).parent / "video" / "check_player_routes.py"
        spec = importlib.util.spec_from_file_location("check_player_routes", path)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="player-dist-")
        self.addCleanup(self.tmp.cleanup)
        self.dist = pathlib.Path(self.tmp.name)

    def _write_dist(self, frames=760, js_markers=True, main_count=1):
        main = "<main>" * main_count
        html = ('<!doctype html><html lang="tr"><body>' + main +
                '<div id="root" data-src="/video/leibniz.json"></div>' +
                '<script src="/video/player.js" defer></script></main></body></html>')
        (self.dist / "player.html").write_text(html, encoding="utf-8")
        # esbuild ASCII modu: Türkçe karakterler \uXXXX olarak yazılır.
        labels = ("Oynat\u0131c\u0131 kontrolleri" if js_markers else "")
        bundle = "/*bundle*/" + labels + "Oynatma konumu Sesi kapat" + "x" * 120_000
        (self.dist / "player.js").write_text(bundle, encoding="utf-8")
        (self.dist / "player.css").write_text(".bar{color:#fff}\n", encoding="utf-8")
        (self.dist / "leibniz.json").write_text(
            json.dumps({"meta": {"frames": frames}}), encoding="utf-8")

    def test_package_and_routes_pass_on_real_http(self):
        self._write_dist()
        rc, report = self.mod.run(dist=self.dist)
        self.assertEqual(rc, 0, report["problems"])
        self.assertEqual(report["verdict"], "PASS")
        statuses = {row["route"]: row["status"] for row in report["routes"]}
        self.assertEqual(statuses["/video.html"], 200)
        self.assertEqual(statuses["/video/player.js"], 200)
        self.assertEqual(statuses["/video/player.css"], 200)
        self.assertEqual(statuses["/video/leibniz.json"], 200)
        # Allowlist: adı listede olmayan /video/* yolu 404.
        self.assertEqual(statuses["/video/yok.js"], 404)
        self.assertEqual(statuses["/video/../README.md"], 404)

    def test_missing_artifact_fails_closed(self):
        self._write_dist()
        (self.dist / "player.js").unlink()
        rc, report = self.mod.run(dist=self.dist)
        self.assertEqual(rc, 1)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertTrue(any("paket eksik" in p for p in report["problems"]))

    def test_stale_bundle_without_control_markers_fails(self):
        self._write_dist(js_markers=False)
        rc, report = self.mod.run(dist=self.dist)
        self.assertEqual(rc, 1)
        self.assertTrue(any("bayat paket" in p for p in report["problems"]))

    def test_frame_contract_and_main_landmark_are_enforced(self):
        self._write_dist(frames=700, main_count=0)
        rc, report = self.mod.run(dist=self.dist)
        self.assertEqual(rc, 1)
        problems = " ".join(report["problems"])
        self.assertIn("meta.frames=700", problems)
        self.assertIn("main landmark", problems)

    def test_missing_dist_fails_before_any_server(self):
        empty = self.dist / "empty"
        empty.mkdir()
        rc, report = self.mod.run(dist=empty)
        self.assertEqual(rc, 1)
        self.assertIsNone(report["base_url"])
        self.assertEqual(report["routes"], [])


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
