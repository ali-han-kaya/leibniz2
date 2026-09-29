#!/usr/bin/env python3
"""test_dashboard_playwright_smoke.py — Playwright smoke test for the live dashboard.

Loose bot:
  - Playwright Chromium headless (stdlib unittest, no extra deps).
  - preview_server.py started on a free port for the class; stopped after.
  - --interval 3600 disables periodic verify so the smoke test is fast.

Two assertions (the contract asked for):
  1. Dashboard renders with no JS console errors (error-level).
  2. SSE EventSource connects: onopen fires, onerror does not, snapshot arrives.

Also asserts the key DOM panels are present so "renders" is real, not an
empty page that happened to load without errors.
"""

import datetime
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # CI runner'da playwright kurulu değilse SKIP (fail değil)
    sync_playwright = None

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")

# Dashboard-next canlı smoke'ları ortak sunucu başlatıcısını kullanır; bu
# dosyanın mevcut static preview smoke'larıyla birbirine bağımlı değiller.
sys.path.insert(0, HERE)
import test_surface_cwv_report as cwv  # noqa: E402


def _next_missing_reason():
    next_bin = os.path.join(cwv.NEXT_DIR, "node_modules", ".bin", "next")
    if not os.path.isfile(next_bin):
        return "apps/dashboard-next/node_modules/.bin/next yok"
    if not os.path.isfile(cwv.NEXT_BUILD_ID):
        return "apps/dashboard-next/.next/BUILD_ID yok (next build gerekli)"
    return ""


def _chromium_missing_reason():
    if sync_playwright is None:
        return "playwright kurulu değil"
    try:
        with sync_playwright() as p:
            executable = p.chromium.executable_path
    except Exception as exc:  # bozuk/eksik Playwright kurulumu
        return "Chromium çözülemedi: %s" % exc
    if not os.path.isfile(executable):
        return "Chromium indirilmemiş (playwright install chromium)"
    return ""


_NEXT_MISSING = _next_missing_reason()
_CHROMIUM_MISSING = _chromium_missing_reason()


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_port(port, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.3)
    return False


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class DashboardSmokeTest(unittest.TestCase):
    PORT = None
    proc = None

    @classmethod
    def setUpClass(cls):
        cls.PORT = free_port()
        cls.proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT,
             "--dir", HERE,
             "--preview-dir", HERE,
             "--port", str(cls.PORT),
             "--bind", "127.0.0.1",
             "--interval", "3600"],
            cwd=HERE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_for_port(cls.PORT, timeout=15):
            cls.proc.terminate()
            cls.proc.wait(timeout=5)
            raise RuntimeError(
                f"preview_server.py did not start on 127.0.0.1:{cls.PORT} "
                f"within 15s (cwd={HERE})")

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

    def test_dashboard_renders_with_no_js_console_errors(self):
        base = f"http://127.0.0.1:{self.PORT}"
        js_errors = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.route("/sw.js", lambda route: route.fulfill(body=""))
            # slides_z3/ lives inside CIKTI/ (== PREVIEW_DIR); server now
            # serves /slides_z3/*.png natively via serve_slides — no route
            # trick needed. Keep a lightweight 404 guard so failures surface
            # as real failures, not hidden routing shims.
            page.on("console",
                    lambda msg: js_errors.append(msg.text)
                    if msg.type == "error" and
                    not msg.text.startswith("Failed to load resource")
                    else None)
            page.goto(base + "/", wait_until="domcontentloaded")
            # Dashboard JS runs after DOM load: SSE connect, /api/latest fetch,
            # reflow. Give it time to settle (snapshot event arrives, panels
            # populate). SSE keeps the network active so networkidle never fires.
            page.wait_for_timeout(1500)
            # Key panels must be present — not an empty page that somehow
            # loaded without errors.
            self.assertIsNotNone(
                page.locator("#m-verdict").text_content(),
                "verdict metric card (#m-verdict) missing")
            self.assertIsNotNone(
                page.locator("#status-board").text_content(),
                "status board (#status-board) missing")
            self.assertIsNotNone(
                page.locator("#badges").text_content(),
                "badges panel (#badges) missing")
            browser.close()
        self.assertEqual(js_errors, [],
                         f"JS console errors ({len(js_errors)}): {js_errors}")

    def test_query_theme_overrides_stored_theme_without_persisting(self):
        base = f"http://127.0.0.1:{self.PORT}"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base + "/?theme=light", wait_until="domcontentloaded")
            page.wait_for_timeout(300)
            self.assertEqual(
                page.evaluate("() => document.documentElement.dataset.theme"),
                "light",
            )
            self.assertIsNone(
                page.evaluate("() => localStorage.getItem('dashboard-theme')")
            )
            page.goto(base + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(300)
            self.assertEqual(
                page.evaluate("() => document.documentElement.dataset.theme"),
                "dark",
            )
            browser.close()

    def test_fail_verdict_seal_uses_broken_ring_and_job_name(self):
        base = f"http://127.0.0.1:{self.PORT}"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(400)
            page.evaluate("""() => renderVerdictSeal({
                verdict: 'FAIL',
                job_name: 'a11y-gate',
                stripped_sha256: '0123456789abcdef'
            })""")

            seal = page.locator("#verdict-seal")
            self.assertFalse(seal.evaluate("(el) => el.hidden"))
            self.assertIn("seal-fail", seal.get_attribute("class"))
            self.assertEqual(
                page.locator("#seal-ring-path").text_content(),
                "JOB FAILED • 0123456789AB •",
            )
            self.assertEqual(
                page.locator(".seal-verdict").text_content(),
                "A11Y-GATE",
            )
            self.assertEqual(
                page.locator(".seal-hash").text_content(),
                "012345…",
            )
            self.assertEqual(
                page.locator(".seal-ring-break").evaluate(
                    "(el) => getComputedStyle(el).display"
                ),
                "inline",
            )
            self.assertEqual(
                page.locator(".seal-job-break").evaluate(
                    "(el) => getComputedStyle(el).display"
                ),
                "inline",
            )
            self.assertNotEqual(
                page.locator(".seal-circle").first.evaluate(
                    "(el) => getComputedStyle(el).strokeDasharray"
                ),
                "none",
            )

            page.evaluate("""() => renderVerdictSeal({
                verdict: 'PASS',
                job_name: 'a11y-gate',
                stripped_sha256: '0123456789abcdef'
            })""")
            self.assertNotIn("seal-fail", seal.get_attribute("class"))
            self.assertEqual(
                page.locator("#seal-ring-path").text_content(),
                "VERIFIED • 0123456789AB •",
            )
            self.assertEqual(
                page.locator(".seal-ring-break").evaluate(
                    "(el) => getComputedStyle(el).display"
                ),
                "none",
            )
            browser.close()

    def test_sse_event_source_connects(self):
        base = f"http://127.0.0.1:{self.PORT}"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.route("/sw.js", lambda route: route.fulfill(body=""))
            page.goto(base + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(800)
            # Independent SSE connectivity test: open /api/run from the
            # loaded page context (relative URL resolves against the dashboard
            # origin). onopen + no onerror + snapshot arrival = SSE connects.
            page.evaluate("""() => {
                window.__sse_open = false;
                window.__sse_error = false;
                window.__sse_snapshot = false;
                const es = new EventSource('/api/run');
                es.onopen = () => { window.__sse_open = true; };
                es.onerror = () => { window.__sse_error = true; };
                es.addEventListener('snapshot', () => {
                    window.__sse_snapshot = true;
                });
                window.__sse2 = es;
            }""")
            page.wait_for_function(
                "() => window.__sse_open === true",
                timeout=5000)
            page.wait_for_timeout(600)
            opened = page.evaluate("window.__sse_open")
            erred = page.evaluate("window.__sse_error")
            snapshot = page.evaluate("window.__sse_snapshot")
            page.evaluate("window.__sse2?.close()")
            browser.close()
        self.assertTrue(opened, "SSE EventSource: onopen did not fire")
        self.assertFalse(erred, "SSE EventSource: onerror fired")
        self.assertTrue(snapshot,
                        "SSE EventSource: snapshot event did not arrive")


class _CountingPreviewAPI:
    """Deterministik dashboard-next upstream'ı ve gerçek HTTP istek sayacı."""

    def __init__(self, rows):
        start = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        self._rows = [{
            "ts": (start + datetime.timedelta(seconds=i)).isoformat(
                timespec="seconds").replace("+00:00", "Z"),
            "p0": 0,
            "p1": 0,
            "duration_s": 300.0 + i,
            "budget_usd": 12.0,
            "z3_total": 5,
        } for i in range(rows)]
        self._hits = Counter()
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802 — stdlib arayüz adı
                outer.record(self.path)
                path = self.path.split("?", 1)[0]
                if path == "/api/trend":
                    self._send_json({"history": outer.rows()})
                elif path == "/api/latest":
                    self._send_json(outer.latest())
                elif path == "/api/run":
                    payload = "data: %s\n\n" % json.dumps(outer.latest())
                    raw = payload.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                else:
                    self.send_error(404)

            def _send_json(self, body):
                raw = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", free_port()), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._thread.start()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def rows(self):
        return list(self._rows)

    def latest(self):
        newest = self._rows[-1] if self._rows else {}
        return {
            "verdict": "PASS",
            "ts": newest.get("ts"),
            "p0": 0,
            "p1": 0,
            "budget_usd": 12.0,
            "budget_limit": 30.0,
            "z3_passed": 5,
            "z3_total": 5,
        }

    def record(self, path):
        with self._lock:
            self._hits[path] += 1

    def reset(self):
        with self._lock:
            self._hits.clear()

    def hits(self):
        with self._lock:
            return dict(self._hits)

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=3)


@unittest.skipIf(_NEXT_MISSING,
                 "dashboard-next canlı smoke atlandı: " + _NEXT_MISSING)
class DashboardNextLiveSmokeTest(unittest.TestCase):
    """Trend penceresi, React cache() ve next/link canlı sözleşmeleri."""

    UPSTREAM_ROWS = 25  # 20'lik pencereyi gerçekten kırpmak için >20

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="dashboard_next_smoke_")
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.upstream = _CountingPreviewAPI(rows=cls.UPSTREAM_ROWS)
        cls.addClassCleanup(cls.upstream.stop)
        port = free_port()
        cls.proc = cwv.spawn_next_server(
            port, cls.upstream.url, os.path.join(cls._tmp.name, "next_start.log"))
        cls.addClassCleanup(cwv.terminate, cls.proc)
        cls.base = "http://127.0.0.1:%d" % port

    def setUp(self):
        self.upstream.reset()

    def _render(self, path="/"):
        request = urllib.request.Request(self.base + path, method="GET")
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8")

    def test_react_cache_deduplicates_each_upstream_seam_per_render(self):
        status, html = self._render("/")
        self.assertEqual(status, 200)
        self.assertIn("Son 5 Koşum", html,
                      "ölçüm gerçek dashboard render'ından gelmeli")
        hits = self.upstream.hits()
        self.assertEqual(hits.get("/api/latest"), 1,
                         "bir render /api/latest'e tam bir kez gitmeli: %s" % hits)
        self.assertEqual(hits.get("/api/trend?limit=5"), 1,
                         "bir render /api/trend?limit=5'e tam bir kez gitmeli: %s"
                         % hits)
        self.assertEqual(sum(hits.values()), 2,
                         "dashboard render'ı iki upstream dikişine birer kez "
                         "gitmeli: %s" % hits)

    def test_react_cache_is_scoped_to_the_http_request(self):
        self._render("/")
        self._render("/")
        hits = self.upstream.hits()
        self.assertEqual(hits.get("/api/latest"), 2,
                         "iki ayrı render iki latest isteği yapmalı: %s" % hits)
        self.assertEqual(hits.get("/api/trend?limit=5"), 2,
                         "iki ayrı render iki trend isteği yapmalı: %s" % hits)

    @unittest.skipIf(_CHROMIUM_MISSING,
                     "trend Playwright smoke atlandı: " + _CHROMIUM_MISSING)
    def test_trend_page_renders_twenty_newest_rows(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                # Canlı SSE yan yolu bu iddianın kapsamı değil; yalnızca SSR
                # penceresini ölç ve sayaçları arka plan polling'inden ayır.
                page.route("**/api/events**", lambda route: route.abort())
                page.goto(self.base + "/trend", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => document.querySelectorAll('tbody tr').length > 0",
                    timeout=20000)
                stamps = page.eval_on_selector_all(
                    "tbody tr time", "els => els.map(e => e.getAttribute('datetime'))")
            finally:
                browser.close()

        self.assertEqual(len(stamps), 20,
                         "25 upstream satırından /trend tam 20 satır göstermeli")
        self.assertEqual(stamps[0], self.upstream.rows()[-1]["ts"],
                         "ilk satır en yeni koşum olmalı")
        for newer, older in zip(stamps, stamps[1:]):
            self.assertGreater(newer, older,
                               "koşumlar en yeniden eskiye sıralanmalı: %s" % stamps)

    @unittest.skipIf(_CHROMIUM_MISSING,
                     "soft-nav Playwright smoke atlandı: " + _CHROMIUM_MISSING)
    def test_next_link_navigation_preserves_document_state(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.route("**/api/events**", lambda route: route.abort())
                page.goto(self.base + "/", wait_until="domcontentloaded")
                page.wait_for_selector('a[href="/trend"]', timeout=20000)
                page.evaluate("() => { window.__softNavMarker = 42; }")
                origin_before = page.evaluate("() => performance.timeOrigin")

                page.click('a[href="/trend"]')
                page.wait_for_function(
                    "() => location.pathname === '/trend'", timeout=20000)
                page.wait_for_function(
                    "() => document.querySelectorAll('tbody tr').length > 0",
                    timeout=20000)
                marker = page.evaluate("() => window.__softNavMarker")
                origin_after = page.evaluate("() => performance.timeOrigin")
            finally:
                browser.close()

        self.assertEqual(marker, 42,
                         "window işareti kayboldu; /trend tam sayfa yüklendi")
        self.assertEqual(origin_after, origin_before,
                         "performance.timeOrigin değişti; next/link soft-nav olmadı")
