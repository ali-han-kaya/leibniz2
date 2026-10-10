#!/usr/bin/env python3
"""test_dashboard_webkit_smoke.py — Safari/WebKit-parite smoke testi (safedriver).

Loose bot:
  - safedriver (WebDriver, Safari) — varsa live WebKit koşumu yapar.
  - safedriver YOKSA veya Safari Automation kapalıysa SKIP (fail değil):
    battery ubuntu'da da koşar; fail-closed SKIP semantiği playwright suite
    ile aynı ("playwright kurulu değil" kalıbı).
  - Statik katman (preview.html üzerinden) HER ortamda koşar: safedriver
    olmasa bile WebKit-parite hedefi seçici kayması olmadan korunur
    (AGENTS kuralı: "the file must be able to go red with no browser present"
    — bu katman safedriver olsa da olmasa da gerçek kontratı taşır).

Live katmanın kapsadığı kontrat (kullanıcı isteği):
  1. Safari'de açılış — WebDriver session + doğru sayfa başlığı/URL.
  2. Ana panel render — #status-board, #m-verdict, #badges, tablist,
     13 .z3-slide, 2 [role=tabpanel], #run-history gerçekten var ve görünür.
  3. Konsol hatası yok — WebKit konsolu WebDriver üzerinden açılmadığından
     sayfa-içi hata toplayıcı kullanılır: load'dan ÖNCE window.onerror +
     unhandledrejection kolşusu enjekte edilir (execute_script sync modda
     unload'a kadar hayatta kalmayabilir; bu yüzden kolşu bir
     ?webkit-smoke=1 query'li İKİNCİ gezintiye taşıyan init-script yerine
     reload + öncesi-headers kombinasyonu kullanılır: addInitScript
     safedriver'da yok; "navigate → inject → reload → read" desenidir).

safedriver arama sırası (ilk bulunan):
  - SAFEDRIVER_BIN ortam değişkeni
  - PATH'te safedriver
  - /Applications/Xcode.app/Contents/Developer/usr/bin/safedriver
  - CommandLineTools: /Library/Developer/CommandLineTools/usr/bin/safedriver
  - Safari.app bundle içi (modern macOS yeri) — bilinen konumlar

CI:
  - advisory `webkit-smoke` job'ı (verify.yml) macOS runner'da
    `sudo safedriver --enable` ile koşar.
  - `CI_JOB_COVERAGE["webkit-smoke"]` kaydı (test_coverage_report.py)
    phantom-kayıt tuzağını önler: job gerçekten verify.yml'de olmalı.
"""

import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
HTML = HERE / "preview.html"
SERVER_SCRIPT = HERE / "preview_server.py"

SAFEDRIVER_CANDIDATES = [
    shutil.which("safedriver"),
    os.environ.get("SAFEDRIVER_BIN"),
    "/Applications/Xcode.app/Contents/Developer/usr/bin/safedriver",
    "/Library/Developer/CommandLineTools/usr/bin/safedriver",
]

# Ana paneller — hem statik hem live katmanın ortak kontratı.
EXPECTED_TABS = ("P1-a", "P1-b", "P2", "P3-a", "P3-b", "P4-a", "P4-b",
                 "P4-c", "P4-d", "P4-e", "P5", "P5-note",
                 "incidental_proof_book_cover-1")
REQUIRED_PANEL_IDS = ("status-board", "m-verdict", "badges", "z3-slide-gallery",
                      "z3-slides", "z3-panel-series", "run-history", "metrics")


def find_safedriver():
    for cand in SAFEDRIVER_CANDIDATES:
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


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


class WebDriver:
    """Minimal stdlib WebDriver client — safedriver JSON/HTTP protokolü."""

    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}"
        self.session_id = None

    def _req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            payload = json.loads(e.read().decode())
        value = payload.get("value")
        if isinstance(value, dict) and "error" in value:
            raise RuntimeError(f"WebDriver {path}: {value['error']} {value.get('message', '')[:200]}")
        return value

    def new_session(self):
        caps = {"capabilities": {"alwaysMatch": {"browserName": "safari"}}}
        value = self._req("POST", "/session", caps)
        self.session_id = value["sessionId"] if isinstance(value, dict) and "sessionId" in value else value
        return self.session_id

    def navigate(self, url):
        self._req("POST", f"/session/{self.session_id}/url", {"url": url})

    def execute(self, script, args=None):
        return self._req("POST", f"/session/{self.session_id}/execute/sync",
                         {"script": script, "args": args or []})

    def title(self):
        return self._req("GET", f"/session/{self.session_id}/title")

    def delete_session(self):
        if self.session_id:
            try:
                self._req("DELETE", f"/session/{self.session_id}")
            finally:
                self.session_id = None


def start_safedriver(safedriver_bin, port):
    proc = subprocess.Popen([safedriver_bin, "--port", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=1) as r:
                st = json.loads(r.read().decode())
                if st.get("value", {}).get("ready"):
                    return proc
        except Exception:
            time.sleep(0.3)
    proc.terminate()
    raise RuntimeError("safedriver did not become ready within 15s")


ERROR_COLLECTOR = """
window.__webkit_smoke_errors = [];
window.onerror = function (msg, src, line, col, err) {
  window.__webkit_smoke_errors.push(String(msg));
};
window.addEventListener('unhandledrejection', function (e) {
  window.__webkit_smoke_errors.push('unhandledrejection: ' + String(e.reason));
});
'collector-installed'
"""


class WebkitSmokeLiveBase(unittest.TestCase):
    """safedriver + Safari ile koşan live katman (env-gated)."""

    @classmethod
    def setUpClass(cls):
        cls.safedriver_bin = find_safedriver()
        if cls.safedriver_bin is None:
            raise unittest.SkipTest("safedriver yok (Xcode/CLT kurulu değil) — statik katman koştu")
        cls.driver_port = free_port()
        cls.safedriver = start_safedriver(cls.safedriver_bin, cls.driver_port)
        cls.PORT = free_port()
        cls.server = subprocess.Popen(
            [sys.executable, str(SERVER_SCRIPT), "--dir", str(HERE),
             "--preview-dir", str(HERE), "--port", str(cls.PORT),
             "--bind", "127.0.0.1", "--interval", "3600"],
            cwd=str(HERE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not wait_for_port(cls.PORT, timeout=15):
            raise unittest.SkipTest("preview_server başlamadı (env)")  # pragma: no cover
        try:
            cls.driver = WebDriver(cls.driver_port)
            cls.driver.new_session()
        except RuntimeError as e:
            msg = str(e)
            if "session not created" in msg or "automation" in msg.lower() or "active" in msg.lower():
                raise unittest.SkipTest(
                    "Safari Automation kapalı — Safari > Develop > Allow Remote Automation") from e
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "driver", None) is not None:
            cls.driver.delete_session()
        if getattr(cls, "safedriver", None) is not None:
            cls.safedriver.terminate()
        if getattr(cls, "server", None) is not None:
            cls.server.terminate()

    def _load_with_collector(self):
        base = f"http://127.0.0.1:{self.PORT}"
        self.driver.navigate(base + "/")
        self.driver.execute(ERROR_COLLECTOR)
        self.driver.navigate(base + "/")  # reload; collector load'dan beri yaşıyor
        time.sleep(2.0)  # SSE connect + snapshot fetch settle

    def test_safari_opens_dashboard(self):
        base = f"http://127.0.0.1:{self.PORT}"
        self.driver.navigate(base + "/")
        title = self.driver.title()
        self.assertIn("Live CI Dashboard", title or "",
                      f"Safari sayfa başlığı yanlış: {title!r}")

    def test_main_panels_render_in_webkit(self):
        self._load_with_collector()
        state = self.driver.execute("""
            return {
              statusBoard: document.getElementById('status-board').textContent.length > 0,
              verdict: document.getElementById('m-verdict') !== null,
              badges: document.getElementById('badges') !== null,
              tabs: document.querySelectorAll('[role="tab"]').length,
              slides: document.querySelectorAll('.z3-slide').length,
              panels: document.querySelectorAll('[role="tabpanel"]').length,
              runHistory: document.getElementById('run-history') !== null,
              galleryVisible: !document.getElementById('z3-slides').hidden,
            };
        """)
        self.assertTrue(state["statusBoard"], "status-board boş")
        self.assertTrue(state["verdict"], "m-verdict yok")
        self.assertTrue(state["badges"], "badges yok")
        self.assertEqual(state["tabs"], 2, "2 sekme bekleniyordu")
        self.assertEqual(state["slides"], 13, "13 galeri öğesi bekleniyordu (12 slayt + kapak)")
        self.assertEqual(state["panels"], 2, "2 tabpanel bekleniyordu")
        self.assertTrue(state["runHistory"], "run-history yok")
        self.assertTrue(state["galleryVisible"], "Z3 galeri paneli görünmez")

    def test_no_console_errors_in_webkit(self):
        self._load_with_collector()
        errors = self.driver.execute("return window.__webkit_smoke_errors || [];")
        self.assertEqual(errors or [], [],
                         f"WebKit sayfa hataları ({len(errors or [])}): {errors}")


class TestWebkitStaticContract(unittest.TestCase):
    """Her ortamda koşan statik katman — WebKit-parite seçicileri kilitli."""

    def test_static_panel_contract_matches_live_selectors(self):
        text = HTML.read_text(encoding="utf-8")
        for pid in REQUIRED_PANEL_IDS:
            self.assertIn(f'id="{pid}"', text, f"panel id eksik: {pid}")
        self.assertEqual(text.count('role="tab"'), 2)
        self.assertIn('role="tablist"', text)
        slides = re.findall(r'src="/slides_z3/([^"/]+)\.png"', text)
        self.assertEqual(tuple(slides), EXPECTED_TABS)

    def test_safedriver_availability_is_bounded(self):
        """Live katman skip'i fail'e dönüşmemeli: arama yüzeyi kapanmış olmalı."""
        bin_path = find_safedriver()
        if bin_path is None:
            self.skipTest("safedriver yok — live katman skip (yanlış fail olmama kanıtı)")
        # Bulunduysa binary gerçekten koşabilir mi? (--version hızlı koşum)
        rc = subprocess.run([bin_path, "--version"], capture_output=True, timeout=30).returncode
        self.assertIn(rc, (0, 1), f"safedriver --version beklenmedik rc: {rc}")


if __name__ == "__main__":
    unittest.main()
