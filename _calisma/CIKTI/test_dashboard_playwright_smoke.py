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

import os
import socket
import subprocess
import sys
import time
import unittest
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")


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
            # Serve the Z3 slide images (slides_z3/ lives one level up from
            # CIKTI/; the dashboard references /slides_z3/*.png which the
            # preview-dir-rooted server cannot resolve). This makes the smoke
            # test realistic: real assets render, no spurious 404 noise.
            slide_root = os.path.abspath(
                os.path.join(HERE, os.pardir, "slides_z3"))
            def _slide(route):
                import posixpath
                url = route.request.url
                # url = http://127.0.0.1:PORT/slides_z3/P1-a.png
                path = url.split("/slides_z3/", 1)[-1]  # P1-a.png
                fp = os.path.join(slide_root, path)
                if os.path.isfile(fp):
                    route.fulfill(path=fp)
                else:
                    route.fulfill(body="", status=404)
            page.route("/slides_z3/**", _slide)
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
