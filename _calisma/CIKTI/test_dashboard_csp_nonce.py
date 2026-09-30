#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dashboard_csp_nonce.py — canlı dashboard'da CSP + nonce smoke'u (Playwright).

Ne kanıtlar (preview_server'ın nonce'lu CSP yüzeyi):

  1. CSP İHLALİ ÜRETMEYEN KONSOL: sayfanın kendi yüklemesi (sunucunun enjekte
     ettiği inline nonce script + dış `preview.js` + SSE EventSource) HİÇ
     `securitypolicyviolation` üretmez ve konsola CSP hatası düşmez.
  2. NONCE'LU SCRIPT ÇALIŞIYOR: `serve_preview`'in enjekte ettiği tek inline
     script (`<script nonce=…>window.BUILD_TS=<mtime></script>`) gerçekten
     execute edilir — `window.BUILD_TS` HTML'deki değere eşit çıkar. Nonce
     yanlış olsaydı tarayıcı inline script'i reddeder ve değer `undefined`
     kalırdı; bu yüzden "değer tanımlı" doğrudan nonce kanıtıdır.
  3. CSP GERÇEKTEN AKTİF (negatif kontrol + eşleşen pozitif): aynı içerikli
     bir inline script nonce'SUZ eklenince BLOKLANIR (violation + global set
     edilmez), AYNI script doğru nonce'LA eklenince ÇALIŞIR. Yani "ihlal yok"
     iddiası CSP'nin yokluğundan değil, doğru nonce'tan gelir.

Kapsam sınırı: `default-src 'none'` altında `script-src` davranışı; ayrıca
başlık↔tag nonce eşleşmesi ham HTTP yanıtından (tarayıcı DOM nonce-gizlemesi
devre dışı kalmadan) byte düzeyinde doğrulanır.

Hedef sunucu:
  - `DASHBOARD_BASE_URL` verilirse: o CANLI sunucu (örn. http://127.0.0.1:8010)
    — erişilemezse test FAIL eder (açıkça istendi, sessiz geçilmez).
  - Verilmezse: taze bir `preview_server.py` ücretsiz portta başlatılır
    (kendi kendine yeterli, CI-güvenli).

Playwright/Chromium yoksa SKIP (fail değil): CI runner'da playwright kurulu
değildir; bu test yerel + canlı doğrulama içindir — kardeşi
`test_dashboard_playwright_smoke.py` gibi `check_unit_tests.list` EXCLUDE'unda
(yerel pre-commit 10 sn bütçesini bu test başlatmayla doldurmasın diye).

Çalıştırma:
  python3 _calisma/CIKTI/test_dashboard_csp_nonce.py                       # spawn
  DASHBOARD_BASE_URL=http://127.0.0.1:8010 \\
    python3 _calisma/CIKTI/test_dashboard_csp_nonce.py                      # canlı
"""

import os
import re
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # CI runner'da playwright kurulu değilse SKIP (fail değil)
    sync_playwright = None

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")
LIVE_BASE = (os.environ.get("DASHBOARD_BASE_URL") or "").strip() or None

# Başlıktaki tek nonce kaynağı: script-src 'self' 'nonce-<token>'
HEADER_NONCE_RE = re.compile(r"script-src\s+'self'\s+'nonce-([A-Za-z0-9_\-]+)'")
# Sunucunun enjekte ettiği inline build-damga script'i (token + ts yakalanır).
INLINE_NONCE_RE = re.compile(
    r'<script nonce="([A-Za-z0-9_\-]+)">\s*window\.BUILD_TS=(\d+);')
# CSP ihlalleri Chromium'da bazen konsola da düşer. Filtre KASITLI olarak
# yalnız "Content Security Policy" ifadesini arar: CSP bloklarının konsol
# metni her zaman bu ifadeyi taşır ("…violates the following Content Security
# Policy directive…"). Genel "Refused to …" ifadeleri (örn. bir 404'ün
# text/plain gövdesinin strict-MIME ile stil olarak reddi) CSP DEĞİLDİR ve
# bunları CSP sanmak yanlış-pozitif üretir. Otoritatif sinyal zaten
# `securitypolicyviolation` olayıdır; bu filtre onu yalnız konsoldan teyit eder.
CSP_CONSOLE_RE = re.compile(r"Content Security Policy")

# Sayfa yüklenmeden ÖNCE kurulur; TÜM `securitypolicyviolation` olaylarını
# toplar. Init script'ler CDP ile enjekte edilir ve CSP'ye TABİ DEĞİLDİR —
# kaydedici her koşulda çalışır (yani "CSP yüzünden kaydedici de bloklandı"
# yanılsaması olmaz).
VIOLATION_RECORDER = """
window.__cspViolations = [];
document.addEventListener('securitypolicyviolation', (e) => {
  window.__cspViolations.push({
    directive: e.violatedDirective,
    blockedURI: e.blockedURI,
    sample: e.sample,
  });
});
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_port(host, port, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.3)
    return False


def split_base(base):
    """http://127.0.0.1:8010 → ("127.0.0.1", 8010)."""
    m = re.match(r"^https?://([^/:]+):(\d+)", base)
    if not m:
        raise RuntimeError(f"DASHBOARD_BASE_URL ayrıştırılamadı (host:port yok): {base}")
    return m.group(1), int(m.group(2))


def fetch_root(base):
    """Ham HTTP yanıtını döndür — nonce eşleşmesi DOM gizlemesinden etkilenmesin."""
    req = urllib.request.Request(base + "/",
                                 headers={"User-Agent": "csp-nonce-smoke"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.headers, r.read().decode("utf-8", "replace")


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class CspNonceSmokeTest(unittest.TestCase):
    base = None
    proc = None

    @classmethod
    def setUpClass(cls):
        cls.proc = None
        if LIVE_BASE:
            host, port = split_base(LIVE_BASE)
            cls.base = LIVE_BASE.rstrip("/")
            if not wait_for_port(host, port, timeout=10):
                raise RuntimeError(
                    f"DASHBOARD_BASE_URL={LIVE_BASE} erişilemedi "
                    f"({host}:{port} dinlemiyor) — canlı sunucu ayakta mı?")
            return

        port = free_port()
        cls.proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT,
             "--dir", HERE,
             "--preview-dir", HERE,
             "--port", str(port),
             "--bind", "127.0.0.1",
             "--interval", "3600"],
            cwd=HERE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_for_port("127.0.0.1", port, timeout=15):
            cls.proc.terminate()
            cls.proc.wait(timeout=5)
            raise RuntimeError(
                f"preview_server.py 127.0.0.1:{port} üzerinde başlamadı "
                f"({SERVER_SCRIPT})")
        cls.base = f"http://127.0.0.1:{port}"

    @classmethod
    def tearDownClass(cls):
        if cls.proc is not None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
            cls.proc = None

    # ── 1) Başlık ↔ HTML nonce eşleşmesi (ham HTTP) ─────────────────────
    def test_1_header_is_nonce_based_and_matches_inline_tag(self):
        status, headers, body = fetch_root(self.base)
        self.assertEqual(status, 200, f"/ 200 dönmedi ({status})")

        csp = headers.get("Content-Security-Policy")
        self.assertIsNotNone(
            csp, "CSP başlığı YOK — dashboard nonce tabanlı korumadan yoksun")
        for must in ("default-src 'none'", "connect-src 'self'",
                     "frame-ancestors 'none'", "base-uri 'none'",
                     "form-action 'none'"):
            self.assertIn(must, csp, f"CSP'de beklenen direktif yok: {must}")

        self.assertNotIn(
            "unsafe-inline", csp.split("style-src")[0],
            "script-src 'unsafe-inline' içeriyor — nonce anlamsızlaşır")

        m = HEADER_NONCE_RE.search(csp)
        self.assertIsNotNone(
            m, f"script-src 'self' 'nonce-…' deseni yok. CSP={csp!r}")
        header_nonce = m.group(1)

        # Placeholder tüketilmiş olmalı (enjeksiyon gerçekleşti).
        self.assertNotIn(
            "<script data-build-ts></script>", body,
            "build-damga placeholder'ı enjekte EDİLMEMİŞ — inline script yok")
        mi = INLINE_NONCE_RE.search(body)
        self.assertIsNotNone(
            mi, "nonce'lu `window.BUILD_TS=…` inline script HTML'de yok")
        self.assertEqual(
            mi.group(1), header_nonce,
            "Başlıktaki nonce ≠ inline <script nonce> değeri")
        self.assertRegex(mi.group(2), r"^\d+$", "build-damga ts sayısal değil")
        self.inline_ts = mi.group(2)

        # Dış bundle nonce'suz ama `script-src 'self'` ile yüklenir.
        self.assertIn('<script src="preview.js">', body,
                      "dış preview.js script etiketi yok")

    # ── 2) Nonce'lu script çalışıyor + sayfa yüklemesi sıfır ihlal ──────
    def test_2_nonce_script_executes_and_page_load_has_no_violations(self):
        _, _, body = fetch_root(self.base)
        mi = INLINE_NONCE_RE.search(body)
        self.assertIsNotNone(mi, "enjekte edilmiş inline nonce script yok")
        expected_ts = mi.group(2)

        csp_console = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.add_init_script(VIOLATION_RECORDER)
            page.on("console",
                    lambda msg: csp_console.append(msg.text)
                    if msg.type == "error" and CSP_CONSOLE_RE.search(msg.text)
                    else None)
            page.goto(self.base + "/", wait_until="domcontentloaded")
            # SSE bağlanır, /api/latest fetch olur, reflow tamamlanır.
            page.wait_for_timeout(1800)
            build_ts = page.evaluate("() => window.BUILD_TS")
            violations = page.evaluate("() => window.__cspViolations")
            external_ok = page.evaluate(
                "() => typeof window.renderVerdictSeal === 'function'")
            browser.close()

        self.assertIsNotNone(
            build_ts,
            "window.BUILD_TS TANIMSIZ — nonce'lu inline script execute edilmedi "
            "(nonce uyuşmuyor ya da script bloklandı)")
        self.assertEqual(
            str(build_ts), str(expected_ts),
            "window.BUILD_TS, HTML'deki enjekte edilmiş değerle uyuşmuyor")
        self.assertEqual(
            violations, [],
            f"Sayfa yüklemesi CSP ihlali üretti ({len(violations)}): {violations}")
        self.assertEqual(
            csp_console, [],
            f"Konsolda CSP hatası: {csp_console}")
        self.assertTrue(
            external_ok,
            "preview.js çalışmadı (window.renderVerdictSeal yok) — "
            "script-src 'self' dış bundle'ı yükleyemedi")

    # ── 3) Negatif kontrol: CSP gerçekten uyguluyor mu? ────────────────
    def test_3_csp_blocks_missing_nonce_and_allows_matching_nonce(self):
        _, headers, _ = fetch_root(self.base)
        csp = headers.get("Content-Security-Policy") or ""
        m = HEADER_NONCE_RE.search(csp)
        self.assertIsNotNone(m, "başlıktan nonce okunamadı")
        nonce = m.group(1)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.add_init_script(VIOLATION_RECORDER)
            page.goto(self.base + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(600)
            # İki özdeş inline script: yalnız nonce'ları farklı. Aynı
            # `document.createElement('script')` + textContent yolu; tek
            # ayrım `s.nonce` set edilip edilmemesi.
            page.evaluate(
                """(nonce) => {
                    const ok = document.createElement('script');
                    ok.nonce = nonce;
                    ok.textContent = 'window.__cspNonceProbeOk = 1';
                    document.body.appendChild(ok);

                    const bad = document.createElement('script');
                    bad.textContent = 'window.__cspNoNonceProbe = 1';
                    document.body.appendChild(bad);
                }""",
                nonce)
            page.wait_for_timeout(600)
            probe_ok = page.evaluate("() => window.__cspNonceProbeOk")
            probe_blocked = page.evaluate("() => window.__cspNoNonceProbe")
            violations = page.evaluate("() => window.__cspViolations")
            browser.close()

        self.assertEqual(
            probe_ok, 1,
            "nonce'LU inline script ÇALIŞMADI — nonce mekanizması bozuk")
        self.assertIsNone(
            probe_blocked,
            "nonce'SUZ inline script BLOKLANMADI — CSP script-src etkisiz "
            "(yani test-2'deki 'ihlal yok' sonucu güvenilmez)")
        script_viol = [
            v for v in violations
            if "script-src" in (v.get("directive") or "")]
        self.assertTrue(
            script_viol,
            f"nonce'suz script için script-src ihlali kaydedilmedi: {violations}")
        # Tek kasıtlı ihlal; sayfanın kendi yüklemesinden sızıntı olmamalı.
        others = [
            v for v in violations
            if "script-src" not in (v.get("directive") or "")]
        self.assertEqual(
            others, [],
            f"Kasıtlı negatif-kontrol DIŞINDA beklenmeyen CSP ihlali: {others}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
