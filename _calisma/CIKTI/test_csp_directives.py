#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_csp_directives.py — CSP sözleşmesi, direktif direktif.

`test_security_headers.py` yalnız `frame-ancestors 'none'` ve nonce'in
build-damga script'ini kapsadığını ölçer. Bu modül **tüm direktif kümesini**
ve hepsinin taşıması gereken güvenlik değişmezlerini sabitler.

Sözleşmenin özü: `default-src 'none'` ile reddet-öne-der, `script-src`
YALNIZCA `'self'` + nonce. Bir gün `script-src 'self' 'unsafe-inline'`
yazılırsa buradaki test kırmızıya düşer — `test_preview_hover_tooltip.py`
o hâlde ancak konsol-ihlali sayacıyla yakalar, ki o test yalnız **o sayfada**
inline handler bulunmadığını kanıtlar; politikanın kendisini değil.

Nonce bağı üç yerde birden doğrulanır:
  1. kaynak dosyada `secrets` ile üretiliyor (sabit literal değil),
  2. yanıt başlığındaki nonce == gövdeye enjekte edilen script'in nonce'i,
  3. nonce tahmin edilemez uzunlukta ve URL-güvenli karakterlerden.
"""

import pathlib
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import preview_server as ps  # noqa: E402

PREVIEW_SRC = CIKTI / "preview_server.py"

# Beklenen direktifler: ad → zorunlu kaynak listesi. Sıra önemsiz,
# ama KÜME sabittir: fazladan direktif (ör. `unsafe-eval` girmesi) da
# `test_directive_set_is_exactly_the_agreed_one` ile yakalanır.
EXPECTED_DIRECTIVES = {
    "default-src": ["'none'"],
    "script-src": ["'self'"],          # + nonce ayrıca doğrulanır
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:"],
    "connect-src": ["'self'"],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'none'"],
    "form-action": ["'none'"],
}


def parse_csp(value):
    """'a b; c d' → {'a': ['b'], 'c': ['d']}"""
    out = {}
    for part in (value or "").split(";"):
        tokens = part.split()
        if not tokens:
            continue
        out[tokens[0].lower()] = [t for t in tokens[1:]]
    return out


class CspDirectiveContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls._old_preview_dir = getattr(ps, "PREVIEW_DIR", None)
        ps.PREVIEW_DIR = cls._tmp.name
        # Placeholder şart: build-damga script'i buraya enjekte edilir ve
        # nonce bağı bu satır üzerinden sınanır.
        (pathlib.Path(cls._tmp.name) / "preview.html").write_text(
            '<!doctype html><html><body><script data-build-ts>'
            '</script></body></html>', encoding="utf-8")
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
        if cls._old_preview_dir is None:
            if hasattr(ps, "PREVIEW_DIR"):
                del ps.PREVIEW_DIR
        else:
            ps.PREVIEW_DIR = cls._old_preview_dir
        cls._tmp.cleanup()

    def _fetch(self, path):
        req = urllib.request.Request(self.base + path,
                                     headers={"Host": "127.0.0.1"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.headers, resp.read().decode(
                    "utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, ""

    def _csp(self, path="/"):
        status, headers, body = self._fetch(path)
        self.assertEqual(status, 200, path)
        return headers.get("Content-Security-Policy"), body

    # ---- direktif kümesi --------------------------------------------------

    def test_directive_set_is_exactly_the_agreed_one(self):
        csp, _ = self._csp()
        self.assertIsNotNone(csp, "CSP başlığı yok")
        got = parse_csp(csp)
        self.assertEqual(sorted(got), sorted(EXPECTED_DIRECTIVES),
                         "direktif kümesi değişmiş.\n  fazla: %s\n  eksik: %s"
                         % (sorted(set(got) - set(EXPECTED_DIRECTIVES)),
                            sorted(set(EXPECTED_DIRECTIVES) - set(got))))

    def test_every_expected_directive_carries_its_sources(self):
        csp, _ = self._csp()
        got = parse_csp(csp)
        offenders = []
        for name, sources in EXPECTED_DIRECTIVES.items():
            if name not in got:
                offenders.append("%s yok" % name)
                continue
            for src in sources:
                if src not in got[name]:
                    offenders.append("%s → %s yok (mevcut: %s)"
                                     % (name, src, got[name]))
        self.assertEqual(offenders, [],
                         "CSP direktif sözleşmesi ihlali:\n  "
                         + "\n  ".join(offenders))

    def test_script_src_allows_no_unsafe_inline_or_eval(self):
        """Politikanın kalbi: script çalıştırma gevşememeli."""
        csp, _ = self._csp()
        script_src = parse_csp(csp).get("script-src", [])
        for banned in ("'unsafe-inline'", "'unsafe-eval'"):
            self.assertNotIn(banned, script_src,
                             "script-src %s içeriyor — CSP çalışma anında "
                             "etkisizleşiyor" % banned)

    def test_default_src_is_deny_all(self):
        """Reddet-önce: kaynak belirtilmeyen her şey kapalı."""
        csp, _ = self._csp()
        self.assertEqual(parse_csp(csp).get("default-src"), ["'none'"],
                         "default-src 'none' olmalı — beyaz-listede "
                         "kalmayan kaynak türleri açık kalıyor")

    def test_no_wildcard_anywhere(self):
        csp, _ = self._csp()
        for name, sources in parse_csp(csp).items():
            self.assertNotIn("*", sources,
                             "%s joker (*) içeriyor — tüm kaynaklara açık"
                             % name)

    def test_no_external_origins_in_any_directive(self):
        """Pano localhost-tekil: hiçbir yerde dış origin olmamalı."""
        csp, _ = self._csp()
        for name, sources in parse_csp(csp).items():
            for src in sources:
                if src in ("'self'", "'none'", "data:") or src.startswith("'nonce-"):
                    continue
                if src in ("'unsafe-inline'",):  # style-src için kasıtlı
                    continue
                self.fail("beklenmeyen kaynak %s → %s" % (name, src))

    # ---- nonce sözleşmesi -------------------------------------------------

    def test_nonce_comes_from_secrets_not_a_literal(self):
        """Nonce kaynak dosyada SABİT olamaz."""
        src = PREVIEW_SRC.read_text(encoding="utf-8")
        self.assertIn("secrets.token_urlsafe", src,
                      "nonce üretimi secrets'tan geçmiyor")
        match = re.search(r'^BUILD_TS_NONCE\s*=\s*"([^"]+)"', src, re.M)
        self.assertIsNone(match,
                          "BUILD_TS_NONCE kaynak dosyada sabit literal: %s"
                          % (match.group(1) if match else "?"))
        # Üretimde kullanılan üretici, tanımda gerçekten kullanılıyor mu:
        self.assertRegex(
            src, r"BUILD_TS_NONCE\s*=\s*secrets\.token_urlsafe\(",
            "BUILD_TS_NONCE = secrets.token_urlsafe(...) olmalı")

    def test_nonce_is_unpredictable_length_and_charset(self):
        nonce = ps.BUILD_TS_NONCE
        self.assertGreaterEqual(len(nonce), 22,
                                "token_urlsafe(16) 22 karakter verir; %d"
                                % len(nonce))
        self.assertRegex(nonce, r"^[A-Za-z0-9_-]+$",
                         "nonce URL-güvenli karakterlerden olmali")

    def test_header_nonce_matches_injected_script_nonce(self):
        """Aynı istekte başlık nonce'u == gövde script nonce'i.

        Ayrışırsa build-damga script'i tarayıcıda bloklanır (sessiz
        kırılma: BUILD_TS undefined → cache-buster bozulur).
        """
        csp, body = self._csp("/")
        csp_nonce = re.search(r"'nonce-([^']+)'", csp)
        self.assertIsNotNone(csp_nonce, "CSP'de nonce yok")
        html_nonce = re.search(r'<script[^>]*\bnonce="([^"]+)"', body)
        self.assertIsNotNone(html_nonce,
                             "gövdede nonce'lu script yok — damga "
                             "enjekte edilmedi")
        self.assertEqual(csp_nonce.group(1), html_nonce.group(1),
                         "başlık nonce'u != gövde nonce'i")

    def test_nonce_is_not_present_in_the_static_source_html(self):
        """Canlı nonce diskteki kaynak HTML'e İŞLENMEMELİ.

        İşlenmişse o nonce bir sonraki süreçte de geçerli olur — yani
        tahmin edilebilir hale gelir (CSP'nin nonce'unun tek işi bu).
        """
        csp, _ = self._csp("/")
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        on_disk = (CIKTI / "preview.html")
        if on_disk.exists():
            self.assertNotIn(nonce, on_disk.read_text(encoding="utf-8"),
                             "canlı nonce diskteki preview.html içinde")

    def test_script_src_exposes_exactly_one_nonce(self):
        csp, _ = self._csp()
        nonces = [s for s in parse_csp(csp)["script-src"]
                  if s.startswith("'nonce-")]
        self.assertEqual(len(nonces), 1,
                         "script-src'te %d nonce var, tam 1 olmali: %s"
                         % (len(nonces), nonces))

    # ---- politika bütünlüğü ----------------------------------------------

    def test_style_unsafe_inline_is_the_only_deliberate_relaxation(self):
        """Bilinen tek gevşeme: style-src 'unsafe-inline' (48 style=).

        Başka bir yerde 'unsafe-*' belirse bu bir sürüklenmedir.
        """
        csp, _ = self._csp()
        got = parse_csp(csp)
        for name, sources in got.items():
            for src in sources:
                if src.startswith("'unsafe-") and not (
                        name == "style-src" and src == "'unsafe-inline'"):
                    self.fail("beklenmeyen gevşeme: %s → %s" % (name, src))

    def test_csp_present_on_every_probeable_surface(self):
        """CSP yalnız HTML sayfasında değil, statik/API/SSE hepsinde.

        Durum kodundan BAĞIMSIZ: 404 bile CSP taşır — başlıksız bir hata
        yanıtı, saldırgan içeriğinin tarayıcı ayrıştırıcısına girebileceği
        yüzeydir. Bu yüzden "200 bekliyorum" değil "başlık var mı" denir;
        test fixture'a (geçici preview.js vb.) bağımlı kalmaz.
        """
        surfaces = ("/", "/index.html", "/preview", "/preview.js", "/sw.js",
                    "/api/latest", "/api/trend", "/api/run-history",
                    "/video.html", "/slides_z3/yok.png", "/yok-boyle-yol")
        missing = []
        for path in surfaces:
            _status, headers, _body = self._fetch(path)
            csp = headers.get("Content-Security-Policy")
            if csp is None:
                missing.append("%s → CSP yok" % path)
            elif parse_csp(csp).get("default-src") != ["'none'"]:
                missing.append("%s → default-src 'none' değil" % path)
        self.assertEqual(missing, [],
                         "CSP taşımayan yüzey:\n  " + "\n  ".join(missing))


if __name__ == "__main__":
    unittest.main()
