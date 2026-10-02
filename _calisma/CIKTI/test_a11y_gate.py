#!/usr/bin/env python3
"""test_a11y_gate.py — a11y_gate için tarayıcısız (browser-free) test süiti.

Spec: docs/superpowers/specs/2026-09-17-a11y-gate-design.md (§Testing)
Plan: docs/superpowers/plans/2026-09-17-a11y-gate-implementation.md (T4)

Kapsam: saf-unit (eşikleme, bilinmeyen-severity fail-closed, allowlist,
rapor şekli) + in-process sözleşme testleri (ölü port → FAIL, canlı sunucu →
PASS, checksum uyuşmazlığı → FAIL, geçersiz konfig → FAIL). Tarayıcı
entegrasyonu (gerçek Playwright koşumu) CI job'ının kendisidir; bu süit
Playwright'a dokunmaz — sürücü dikşi `collect` üzerinden sahte bir
soket-kanıt sürücüyle değiştirilir (gerçek TCP davranışı korunur).
"""

import contextlib
import io
import json
import os
import socket
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import a11y_gate  # noqa: E402

SHIPPED_CONFIG = os.path.join(SCRIPT_DIR, "a11y_gate_config.json")


# ----------------------------------------------------------------- yardımcılar

def node(target=("body",)):
    return {"target": list(target)}


def axe_v(rule, impact, nodes=None):
    return {"id": rule, "impact": impact, "nodes": nodes if nodes is not None else [node()]}


def base_cfg(pages=None):
    return {
        "blocking": ["critical", "serious"],
        "warn": ["moderate", "minor"],
        "incomplete": "report-only",
        "pages": pages if pages is not None else [{"path": "/preview.html"}],
        "allowlist": [],
    }


class _OKHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def live_server():
    srv = HTTPServer(("127.0.0.1", 0), _OKHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield "http://127.0.0.1:%d" % srv.server_address[1]
    finally:
        srv.shutdown()
        srv.server_close()


@contextlib.contextmanager
def dead_port():
    srv = HTTPServer(("127.0.0.1", 0), _OKHandler)
    port = srv.server_address[1]
    srv.server_close()
    yield "http://127.0.0.1:%d" % port


def socket_probe_connect(base_url, axe_src, page_path):
    """Soket-kanıt sahte sürücü: gerçek TCP bağlantısı kurar (tarayıcı yok).

    Bağlantı kurulamazsa exception fırlatır (gerçek sunucu arızası simülasyonu);
    kurulursa boş-tarama sonucu döndürür.
    """
    from urllib.parse import urlsplit

    u = urlsplit(base_url)
    s = socket.create_connection((u.hostname, u.port), timeout=2)
    s.close()
    return ({"violations": [], "incomplete": []},
            base_url.rstrip("/") + page_path)


# ------------------------------------------------------------- saf eşikleme

class ClassifyTests(unittest.TestCase):
    def test_critical_is_blocking(self):
        rows = a11y_gate.classify_violations({"violations": [axe_v("r1", "critical")], "incomplete": []}, base_cfg())
        self.assertEqual(rows[0]["level"], "blocking")
        self.assertEqual(a11y_gate.decide_verdict(rows), "FAIL")

    def test_serious_is_blocking(self):
        rows = a11y_gate.classify_violations({"violations": [axe_v("r1", "serious")], "incomplete": []}, base_cfg())
        self.assertEqual(rows[0]["level"], "blocking")

    def test_moderate_and_minor_are_warn(self):
        for impact in ("moderate", "minor"):
            rows = a11y_gate.classify_violations({"violations": [axe_v("r1", impact)], "incomplete": []}, base_cfg())
            self.assertEqual(rows[0]["level"], "warn", impact)
        rows = a11y_gate.classify_violations(
            {"violations": [axe_v("a", "moderate"), axe_v("b", "minor")], "incomplete": []}, base_cfg())
        self.assertEqual(a11y_gate.decide_verdict(rows), "PASS")

    def test_unknown_impact_is_blocking(self):
        rows = a11y_gate.classify_violations({"violations": [axe_v("r1", "banana")], "incomplete": []}, base_cfg())
        self.assertEqual(rows[0]["level"], "blocking")
        self.assertEqual(a11y_gate.decide_verdict(rows), "FAIL")

    def test_missing_impact_is_blocking(self):
        rows = a11y_gate.classify_violations({"violations": [{"id": "r1", "nodes": [node()]}], "incomplete": []}, base_cfg())
        self.assertEqual(rows[0]["level"], "blocking")

    def test_incomplete_is_report_only(self):
        results = {"violations": [], "incomplete": [{"id": "i1", "impact": None, "nodes": [node(), node()]}]}
        rows = a11y_gate.classify_violations(results, base_cfg())
        self.assertEqual(rows[0]["level"], "incomplete")
        self.assertEqual(rows[0]["nodes"], 2)
        self.assertEqual(a11y_gate.decide_verdict(rows), "PASS")

    def test_empty_scan_passes(self):
        rows = a11y_gate.classify_violations({"violations": [], "incomplete": []}, base_cfg())
        self.assertEqual(a11y_gate.decide_verdict(rows), "PASS")


class AllowlistTests(unittest.TestCase):
    def test_rule_level_allowlist_silences_everywhere(self):
        cfg = base_cfg()
        cfg["allowlist"] = [{"rule": "color-contrast", "reason": "bilinen borç, rokunda"}]
        results = {"violations": [axe_v("color-contrast", "serious", nodes=[node(["#a"]), node(["#b"])])], "incomplete": []}
        rows = a11y_gate.classify_violations(results, cfg)
        self.assertEqual(rows[0]["level"], "allowlisted")
        self.assertEqual(rows[0]["nodes"], 0)
        self.assertEqual(a11y_gate.decide_verdict(rows), "PASS")

    def test_target_scoped_allowlist_covers_matching_nodes_only(self):
        cfg = base_cfg()
        cfg["allowlist"] = [{"rule": "r1", "reason": "legacy sayfa", "target": "#legacy"}]
        results = {"violations": [axe_v("r1", "critical", nodes=[node(["#legacy", "div"]), node(["#main"])])], "incomplete": []}
        rows = a11y_gate.classify_violations(results, cfg)
        self.assertEqual(rows[0]["level"], "blocking")  # kalan node blocking
        self.assertEqual(rows[0]["nodes"], 1)
        self.assertEqual(rows[0]["allowlisted_nodes"], 1)
        self.assertEqual(a11y_gate.decide_verdict(rows), "FAIL")

    def test_allowlist_never_hides_other_rules(self):
        cfg = base_cfg()
        cfg["allowlist"] = [{"rule": "r1", "reason": "sadece r1"}]
        results = {"violations": [axe_v("r1", "serious"), axe_v("r2", "serious")], "incomplete": []}
        rows = a11y_gate.classify_violations(results, cfg)
        levels = {r["rule"]: r["level"] for r in rows}
        self.assertEqual(levels["r1"], "allowlisted")
        self.assertEqual(levels["r2"], "blocking")


class IncompleteAllowlistTests(unittest.TestCase):
    """incomplete girdileri de allowlist'e uymalidir (aksi halde gerekceli
    kayit etkisiz olur — kayit gorunur, kapida hicbirey degismez)."""

    def test_incomplete_allowlist_is_applied(self):
        cfg = base_cfg()
        cfg["allowlist"] = [{"rule": "color-contrast", "reason": "gradyan", "target": "#a"}]
        results = {"violations": [],
                   "incomplete": [{"id": "color-contrast", "impact": "serious",
                                   "nodes": [node(["#a"]), node(["#a", "span"])]}]}
        rows = a11y_gate.classify_violations(results, cfg)
        self.assertEqual(rows[0]["level"], "incomplete_allowlisted")
        self.assertEqual(rows[0]["nodes"], 0)
        self.assertEqual(rows[0]["reasons"], ["gradyan"])

    def test_partial_incomplete_allowlist_keeps_remaining_nodes(self):
        cfg = base_cfg()
        cfg["allowlist"] = [{"rule": "color-contrast", "reason": "gradyan", "target": "#a"}]
        results = {"violations": [],
                   "incomplete": [{"id": "color-contrast", "impact": "serious",
                                   "nodes": [node(["#a"]), node(["#b"])]}]}
        rows = a11y_gate.classify_violations(results, cfg)
        self.assertEqual(rows[0]["level"], "incomplete")
        self.assertEqual(rows[0]["nodes"], 1)
        self.assertEqual(rows[0]["allowlisted_nodes"], 1)

    def test_incomplete_allowlist_cannot_change_verdict(self):
        cfg = base_cfg()
        cfg["allowlist"] = [{"rule": "color-contrast", "reason": "gerekce", "target": "#a"}]
        covered = a11y_gate.classify_violations(
            {"violations": [], "incomplete": [{"id": "color-contrast", "impact": "serious",
                                               "nodes": [node(["#a"])]}]}, cfg)
        bare = a11y_gate.classify_violations(
            {"violations": [], "incomplete": [{"id": "color-contrast", "impact": "serious",
                                               "nodes": [node(["#a"])]}]}, base_cfg())
        self.assertEqual(a11y_gate.decide_verdict(covered),
                         a11y_gate.decide_verdict(bare))

    def test_incomplete_allowlist_does_not_leak_to_violations(self):
        """Ayni kural ihlal tarafinda gelirse kayit onu da susturmamali —
        hedef kapsamli allowlist'in en kotu hali yine de gerekce ister."""
        cfg = base_cfg()
        cfg["allowlist"] = [{"rule": "color-contrast", "reason": "yalnizca incomplete",
                             "target": "#a"}]
        results = {"violations": [axe_v("color-contrast", "serious", nodes=[node(["#a"])])],
                   "incomplete": []}
        rows = a11y_gate.classify_violations(results, cfg)
        self.assertEqual(rows[0]["level"], "allowlisted")
        self.assertIn("yalnizca incomplete", rows[0]["reasons"])


class ShippedConfigTests(unittest.TestCase):
    """a11y_gate_config.json'daki kayitlar ETKIN olmali. Bu sinif, incomplete
    dongusu _allowlisted_nodes'i cagirmazsa kirmiziya doner."""

    CONFIG = SHIPPED_CONFIG

    def setUp(self):
        self.cfg = a11y_gate.load_config(self.CONFIG)

    def test_config_loads(self):
        self.assertIsInstance(self.cfg["allowlist"], list)

    def test_every_entry_has_substantive_reason(self):
        for entry in self.cfg["allowlist"]:
            self.assertTrue(entry["rule"], "rule bos")
            self.assertTrue(entry["target"], "hedefsiz kayit tum agaci susturur")
            self.assertGreaterEqual(
                len(entry["reason"]), 40,
                "gerekce cok kisa — olcum kaniti tasinmali")

    def test_gradient_incomplete_nodes_are_acknowledged(self):
        """main kosumunda (run 37035461060) raporlanan iki node."""
        results = {"violations": [], "incomplete": [
            {"id": "color-contrast", "impact": "serious",
             "nodes": [node(["h1"]), node(["#live-status"])]}]}
        rows = a11y_gate.classify_violations(results, self.cfg)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["level"], "incomplete_allowlisted")
        self.assertEqual(rows[0]["nodes"], 0)
        self.assertEqual(a11y_gate.decide_verdict(rows), "PASS")

    def test_unregistered_selector_still_surfaces(self):
        """Kayit hedefli: yeni/baska bir selector'daki incomplete gizlenmez."""
        results = {"violations": [], "incomplete": [
            {"id": "color-contrast", "impact": "serious", "nodes": [node(["#yeni"])]}]}
        rows = a11y_gate.classify_violations(results, self.cfg)
        self.assertEqual(rows[0]["level"], "incomplete")
        self.assertEqual(rows[0]["nodes"], 1)


class MultiPageTests(unittest.TestCase):
    """Sayfa-bazli kapsam: her sayfa ayri taranir, sayfa FAIL kapiyi dusurur,
    ve allowlist kaydi yalniz kendi sayfasinda gecerlidir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scanned = []

    def cfg(self, pages, allowlist=None):
        return base_cfg(pages=pages) if not allowlist else {
            **base_cfg(pages=pages), "allowlist": allowlist}

    def write_cfg(self, cfg):
        path = os.path.join(self.tmp.name, "cfg.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return path

    def run_gate(self, cfg, connect):
        out = os.path.join(self.tmp.name, "a11y_report.json")
        buf = io.StringIO()
        with mock.patch.object(a11y_gate, "collect", connect):
            with contextlib.redirect_stdout(buf):
                rc = a11y_gate.main([
                    "--base-url", "http://127.0.0.1:1",
                    "--config", self.write_cfg(cfg), "--output", out])
        with open(out, encoding="utf-8") as f:
            return rc, json.load(f), buf.getvalue()

    def ok_connect(self, results=None):
        payload = results if results is not None else {"violations": [], "incomplete": []}

        def connect(base_url, axe_src, page_path):
            self.scanned.append(page_path)
            return payload, base_url + page_path
        return connect

    # -- kapsam -----------------------------------------------------------

    def test_every_configured_page_is_scanned_once(self):
        cfg = self.cfg([{"path": "/preview.html"}, {"path": "/guide.html"}])
        rc, report, _out = self.run_gate(cfg, self.ok_connect())
        self.assertEqual(self.scanned, ["/preview.html", "/guide.html"])
        self.assertEqual(rc, 0)

    def test_page_outside_config_is_not_scanned(self):
        """Kapsam config'te ilan edilir; koddan gizli sayfa taranmaz."""
        cfg = self.cfg([{"path": "/preview.html"}])
        _rc, report, _out = self.run_gate(cfg, self.ok_connect())
        self.assertNotIn("/slides_z3/preview.html", self.scanned)

    # -- fail-closed ------------------------------------------------------

    def test_page_load_error_fails_closed(self):
        """404 sayfa kapiyi dusurur: sessizce atlanan sayfa olmaz."""
        def connect(base_url, axe_src, page_path):
            self.scanned.append(page_path)
            if page_path == "/guide.html":
                raise a11y_gate.PageLoadError("%s → HTTP 404" % page_path)
            return {"violations": [], "incomplete": []}, base_url + page_path

        cfg = self.cfg([{"path": "/preview.html"}, {"path": "/guide.html"}])
        rc, report, out = self.run_gate(cfg, connect)
        self.assertEqual(rc, 1)
        self.assertEqual([p["verdict"] for p in report["pages"]], ["PASS", "FAIL"])
        self.assertIn("HTTP 404", report["pages"][1]["error"])
        self.assertIn("/guide.html", out)
        self.assertEqual(report["pages"][0]["verdict"], "PASS")  # diger sayfa yine tarandi

    def test_unknown_page_in_thresholds_raises(self):
        cfg = a11y_gate.load_config(self.write_cfg(self.cfg([{"path": "/preview.html"}])))
        with self.assertRaises(ValueError):
            a11y_gate.thresholds_for(cfg, "/guide.html")

    # -- sayfa bazli esikler ----------------------------------------------

    def test_page_threshold_override_changes_verdict(self):
        """Varsayilan bu kirilimi blocking sayardi; sayfa override'i warn'a
        indirir → FAIL yerine PASS. Override gercekten uygulanmis demektir."""
        violation = {"violations": [axe_v("r1", "critical", nodes=[node(["#x"])])],
                     "incomplete": []}
        strict = self.cfg([{"path": "/preview.html"}])
        lenient = self.cfg([{"path": "/preview.html", "blocking": [], "warn": ["critical"]}])
        rc_strict, rep_strict, _ = self.run_gate(strict, self.ok_connect(violation))
        rc_lenient, rep_lenient, _ = self.run_gate(lenient, self.ok_connect(violation))
        self.assertEqual((rc_strict, rep_strict["pages"][0]["verdict"]), (1, "FAIL"))
        self.assertEqual((rc_lenient, rep_lenient["pages"][0]["verdict"]), (0, "PASS"))
        self.assertEqual(rep_lenient["summary"]["warn"], 1)

    def test_default_thresholds_apply_to_pages_without_override(self):
        cfg = a11y_gate.load_config(self.write_cfg(
            self.cfg([{"path": "/preview.html"},
                      {"path": "/guide.html", "blocking": [], "warn": ["critical"]}])))
        self.assertEqual(a11y_gate.thresholds_for(cfg, "/preview.html"),
                         ({"critical", "serious"}, {"moderate", "minor"}))
        self.assertEqual(a11y_gate.thresholds_for(cfg, "/guide.html"),
                         (set(), {"critical"}))

    # -- allowlist sayfa kapsami -------------------------------------------

    def test_page_scoped_allowlist_does_not_leak_to_other_page(self):
        """preview.html icin olculmus gerekce, guide.html'de gerekcesiz
        susturmaya donusmemeli."""
        entry = {"page": "/preview.html", "rule": "color-contrast", "target": "#live-status",
                 "reason": "gradyan — olculerek kapatildi"}
        cfg = self.cfg([{"path": "/preview.html"}, {"path": "/guide.html"}], [entry])
        payload = {"violations": [], "incomplete": [
            {"id": "color-contrast", "impact": "serious", "nodes": [node(["#live-status"])]}]}
        rc, report, _out = self.run_gate(cfg, self.ok_connect(payload))
        levels = {p["path"]: p["violations"][0]["level"] for p in report["pages"]}
        self.assertEqual(levels["/preview.html"], "incomplete_allowlisted")
        self.assertEqual(levels["/guide.html"], "incomplete")
        self.assertEqual(report["summary"]["incomplete_allowlisted"], 1)
        self.assertEqual(report["summary"]["incomplete"], 1)

    def test_unscoped_allowlist_applies_to_every_page(self):
        entry = {"rule": "r1", "reason": "her sayfada gecerli"}
        cfg = self.cfg([{"path": "/preview.html"}, {"path": "/guide.html"}], [entry])
        payload = {"violations": [axe_v("r1", "serious")], "incomplete": []}
        _rc, report, _out = self.run_gate(cfg, self.ok_connect(payload))
        self.assertEqual([p["violations"][0]["level"] for p in report["pages"]],
                         ["allowlisted", "allowlisted"])


class _FakeResponse:
    def __init__(self, status):
        self.status = status


class _FakePage:
    def __init__(self, status):
        self._status = status
        self.goto_url = None
        self.injected = False

    def goto(self, url, wait_until=None):
        self.goto_url = url
        return _FakeResponse(self._status)

    def add_script_tag(self, content):
        self.injected = True

    def evaluate(self, script):
        return {"violations": [], "incomplete": []}


class _FakeBrowser:
    def __init__(self, status):
        self.page = _FakePage(status)
        self.closed = False

    def new_context(self, **kwargs):
        self.bypass_csp = kwargs.get("bypass_csp")
        return self

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, status):
        self.browser = _FakeBrowser(status)
        self.closed = False

    def launch(self, headless=True):
        return self.browser

    def close(self):
        self.closed = True


class _FakePlaywright:
    def __init__(self, status):
        self.chromium = _FakeChromium(status)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakePlaywrightPatch:
    """sys.modules'a sahte playwright koyar; gercek tarayici gerekmez.

    Amac: playwright_connect'in HTTP durum KONTROLUNU dogrulamak — 404 bir
    sayfayi gormezden gelir ve kapiyi dusurmezse (bos <body> taranir) test
    bunu yakalar.
    """

    def __init__(self, status):
        self.status = status
        self._saved = {}

    def __enter__(self):
        pw = _FakePlaywright(self.status)
        mod = types.ModuleType("playwright")
        api = types.ModuleType("playwright.sync_api")
        api.sync_playwright = lambda: pw
        mod.sync_api = api
        for name, m in (("playwright", mod), ("playwright.sync_api", api)):
            self._saved[name] = sys.modules.get(name)
            sys.modules[name] = m
        self.pw = pw
        return self

    def __exit__(self, *exc):
        for name, old in self._saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
        return False


class HttpStatusFailClosedTests(unittest.TestCase):
    """Tarayici katmani: 404/5xx sayfa FAIL'e donusmeli.

    OLCUM 2026-10-02: bu satir olmadan /guide.html mirror'da yokken kapinin
    404 sayfasini tarayip '0 ihlal' demesi ve yesil gecmesi mumkundur —
    yani yuzey genisletilmis gibi gorunurken hicbir sey taranmamis olur.
    """

    def test_http_error_status_raises_page_load_error(self):
        for status in (400, 404, 500, 503):
            with self.subTest(status=status):
                with FakePlaywrightPatch(status):
                    with self.assertRaises(a11y_gate.PageLoadError) as ctx:
                        a11y_gate.playwright_connect(
                            "http://127.0.0.1:1", "axe-src", "/guide.html")
                self.assertIn(str(status), str(ctx.exception))
                self.assertIn("/guide.html", str(ctx.exception))

    def test_missing_response_raises(self):
        """response nesnesi yoksa da guvenli varsayilan FAIL."""
        with FakePlaywrightPatch(None):
            with self.assertRaises(a11y_gate.PageLoadError):
                a11y_gate.playwright_connect("http://127.0.0.1:1", "axe", "/guide.html")

    def test_ok_status_scans_and_scans_the_requested_path(self):
        with FakePlaywrightPatch(200):
            results, page_url = a11y_gate.playwright_connect(
                "http://127.0.0.1:1", "axe-src", "/guide.html")
        self.assertEqual(page_url, "http://127.0.0.1:1/guide.html")
        self.assertEqual(results, {"violations": [], "incomplete": []})

    def test_browser_closed_even_when_page_fails(self):
        with FakePlaywrightPatch(404) as fake:
            with self.assertRaises(a11y_gate.PageLoadError):
                a11y_gate.playwright_connect("http://127.0.0.1:1", "axe", "/guide.html")
        self.assertTrue(fake.pw.chromium.browser.closed, "tarayici sizdirilmamali")

    def test_csp_bypass_preserved(self):
        with FakePlaywrightPatch(200) as fake:
            a11y_gate.playwright_connect("http://127.0.0.1:1", "axe", "/preview.html")
        self.assertTrue(fake.pw.chromium.browser.bypass_csp,
                        "preview_server nonce-CSP'si axe injection'ini bloklar")


class PageConfigValidationTests(unittest.TestCase):
    """Kapsam ve esik konfigi — hatalar fail-closed reddedilir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def load(self, cfg):
        path = os.path.join(self.tmp.name, "cfg.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return a11y_gate.load_config(path)

    def assertRejects(self, cfg, needle):
        with self.assertRaises(ValueError) as ctx:
            self.load(cfg)
        self.assertIn(needle, str(ctx.exception))

    def test_pages_required(self):
        cfg = base_cfg()
        del cfg["pages"]
        self.assertRejects(cfg, "eksik anahtar")

    def test_pages_cannot_be_empty(self):
        self.assertRejects(base_cfg(pages=[]), "pages boş olamaz")

    def test_duplicate_path_rejected(self):
        self.assertRejects(base_cfg(pages=[{"path": "/a"}, {"path": "/a"}]),
                           "yineleniyor")

    def test_relative_path_rejected(self):
        self.assertRejects(base_cfg(pages=[{"path": "guide.html"}]), "mutlak rota")

    def test_parent_traversal_rejected(self):
        self.assertRejects(base_cfg(pages=[{"path": "/../etc/passwd"}]), "'..'")

    def test_unknown_page_key_rejected(self):
        self.assertRejects(base_cfg(pages=[{"path": "/a", "axe": "x"}]),
                           "bilinmeyen anahtar")

    def test_page_threshold_overlap_rejected(self):
        self.assertRejects(base_cfg(pages=[{"path": "/a", "warn": ["critical"]}]),
                           "kesişimi")

    def test_page_incomplete_policy_locked(self):
        self.assertRejects(base_cfg(pages=[{"path": "/a", "incomplete": "block"}]),
                           "incomplete yalnız")

    def test_allowlist_page_must_be_scanned(self):
        """Taranmayan sayfaya kayit = olu konfig; gerekce yazsa da etkisiz."""
        cfg = base_cfg(pages=[{"path": "/a"}])
        cfg["allowlist"] = [{"page": "/b", "rule": "r", "reason": "x" * 45}]
        self.assertRejects(cfg, "pages listesinde değil")

    def test_valid_two_page_config_loads(self):
        cfg = base_cfg(pages=[{"path": "/preview.html"},
                              {"path": "/guide.html", "blocking": ["critical"],
                               "warn": ["serious", "moderate", "minor"]}])
        loaded = self.load(cfg)
        self.assertEqual([p["path"] for p in loaded["pages"]],
                         ["/preview.html", "/guide.html"])


# ------------------------------------------------- artefakt semasi sozlesmesi

# CI artifact'ini (`a11y-report`, path: a11y_report.json) tuketiyor. Semasi
# degisirse tuketici sessizce bozulur; bu sinif onu kirmiziya cevirir.
# KAPSAM:anahtarlar birebir (EKLEME de SILMA da kirmizi), tip kapali kume,
# ve asagidaki butunluk esitsizligi.
REPORT_KEYS = {"base_url", "config", "pages", "violations", "summary", "error"}
PAGE_KEYS = {"path", "url", "verdict", "error", "violations", "summary", "raw"}
SUMMARY_KEYS = {
    "blocking", "warn", "allowlisted", "incomplete", "incomplete_allowlisted",
}
LEVELS = {"blocking", "warn", "allowlisted", "incomplete", "incomplete_allowlisted"}
ROW_REQUIRED = {"page", "rule", "impact", "level", "nodes"}
ROW_OPTIONAL = {"reasons", "allowlisted_nodes"}


def _axe_every_level():
    """Bes seviyenin hepsini birden ureten axe ciktisi."""
    return {
        "violations": [
            {"id": "v-blocking", "impact": "critical", "nodes": [node(["#b"])]},
            {"id": "v-warn", "impact": "minor", "nodes": [node(["#w"])]},
            {"id": "v-allowlisted", "impact": "serious", "nodes": [node(["#a"])]},
        ],
        "incomplete": [
            {"id": "i-reported", "impact": "serious", "nodes": [node(["#i"])]},
            {"id": "i-allowlisted", "impact": "serious", "nodes": [node(["#g"])]},
        ],
    }


class ArtifactSchemaContractTests(unittest.TestCase):
    """a11y_report.json semasi. DOGRULAMA YUZEYI: run_gate ciktisini okuyan
    `report` degiskeni dosyadan yuklenmis JSON'dur — yani iddialar CI'in
    yukledigi artefaktin kendisine uygulanir, bellekteki dile degil."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.allowlist = [{"rule": "v-allowlisted", "reason": "olculerek kapatildi",
                           "target": "#a"},
                          {"rule": "i-allowlisted", "reason": "gradyan", "target": "#g"}]

    def run_gate(self, axe_results, cfg):
        out = os.path.join(self.tmp.name, "a11y_report.json")
        cfg_path = os.path.join(self.tmp.name, "cfg.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        def fake_connect(base_url, axe_src, page_path):
            return axe_results, base_url.rstrip("/") + page_path

        buf = io.StringIO()
        with mock.patch.object(a11y_gate, "collect", fake_connect):
            with contextlib.redirect_stdout(buf):
                rc = a11y_gate.main([
                    "--base-url", "http://127.0.0.1:1",  # collect sahte: ag yok
                    "--config", cfg_path, "--output", out,
                ])
        with open(out, encoding="utf-8") as f:  # artefaktin kendisi
            return rc, json.load(f)

    def cfg_with_allowlist(self):
        cfg = base_cfg()
        cfg["allowlist"] = self.allowlist
        return cfg

    # -- ust duzey ---------------------------------------------------

    def test_report_top_level_keys_are_exact(self):
        _rc, report = self.run_gate(_axe_every_level(), self.cfg_with_allowlist())
        self.assertEqual(set(report), REPORT_KEYS,
                         "artefaktin ust duzey anahtarlari degisti")

    def test_report_carries_every_level(self):
        _rc, report = self.run_gate(_axe_every_level(), self.cfg_with_allowlist())
        self.assertEqual({r["level"] for r in report["violations"]}, LEVELS,
                         "bu sinif butun seviyeleri uretmek icin yazildi; "
                         "uretim degistiyse kapsam daralmis olur")

    # -- summary (esik anahtarlari) ----------------------------------

    def test_summary_threshold_keys_are_exact(self):
        _rc, report = self.run_gate(_axe_every_level(), self.cfg_with_allowlist())
        self.assertEqual(set(report["summary"]), SUMMARY_KEYS,
                         "summary esik anahtarlari degisti (eklendi veya silindi)")

    def test_summary_values_are_non_negative_ints(self):
        _rc, report = self.run_gate(_axe_every_level(), self.cfg_with_allowlist())
        for key, value in report["summary"].items():
            self.assertIsInstance(value, int, "%s int olmali" % key)
            self.assertNotIsInstance(value, bool)
            self.assertGreaterEqual(value, 0, "%s negatif olamaz" % key)

    def test_summary_counts_cover_every_row(self):
        """BUTUNLUK ESITLIGI: yeni bir level eklenip summary kovasina
        yazilmazsa burasi kirar. SESSIZCE kaybolan bir satir olmaz."""
        _rc, report = self.run_gate(_axe_every_level(), self.cfg_with_allowlist())
        self.assertEqual(sum(report["summary"].values()), len(report["violations"]),
                         "summary toplami satir sayisiyla esit degil — bir level "
                         "kovaya yazilmadan girmis olabilir")
        for row in report["violations"]:
            self.assertIn(row["level"], set(report["summary"]),
                          "level %r icin summary kovasi yok" % row["level"])

    def test_empty_scan_keeps_full_summary(self):
        """Sifir bulguda da esik anahtarlari tam olmali (yoksa tuketici
        'summary eksik' diye ayirt edemez)."""
        _rc, report = self.run_gate({"violations": [], "incomplete": []},
                                    self.cfg_with_allowlist())
        self.assertEqual(set(report["summary"]), SUMMARY_KEYS)
        self.assertEqual(sum(report["summary"].values()), 0)

    # -- violations girdi-yapisi -------------------------------------

    def test_violation_row_keys_are_closed(self):
        _rc, report = self.run_gate(_axe_every_level(), self.cfg_with_allowlist())
        for row in report["violations"]:
            self.assertTrue(ROW_REQUIRED <= set(row),
                            "zorunlu anahtar eksik: %s" % (ROW_REQUIRED - set(row)))
            self.assertLessEqual(set(row), ROW_REQUIRED | ROW_OPTIONAL,
                                 "bilinmeyen satir anahtari: %s" % (set(row) - ROW_REQUIRED - ROW_OPTIONAL))

    def test_violation_row_types(self):
        _rc, report = self.run_gate(_axe_every_level(), self.cfg_with_allowlist())
        for row in report["violations"]:
            self.assertIsInstance(row["rule"], str)
            self.assertIsInstance(row["nodes"], int)
            self.assertNotIsInstance(row["nodes"], bool)
            self.assertGreaterEqual(row["nodes"], 0)
            self.assertIn(row["level"], LEVELS, "kapali kume disi level")
            self.assertTrue(row["impact"] is None or isinstance(row["impact"], str))
            for reason in row.get("reasons", []):
                self.assertIsInstance(reason, str)
            if "allowlisted_nodes" in row:
                self.assertIsInstance(row["allowlisted_nodes"], int)

    def test_allowlisted_row_shape(self):
        """allowlisted satirinda: nodes=0, reasons dolu, allowlisted_nodes YOK
        (tam kapsam; kismi kapsamda incomplete satirinda gorunur)."""
        _rc, report = self.run_gate(_axe_every_level(), self.cfg_with_allowlist())
        for row in report["violations"]:
            if row["level"] in ("allowlisted", "incomplete_allowlisted"):
                self.assertEqual(row["nodes"], 0)
                self.assertTrue(row.get("reasons"), "gerekcesiz allowlist")
                self.assertNotIn("allowlisted_nodes", row)

    # -- esikler ve ham cikti ----------------------------------------

    def test_shipped_thresholds_are_echoed_into_artifact(self):
        """Esikler artefakta gorunur olmali; tuketici 'neden PASS' sorusunu
        rapordan cevaplayabilmeli."""
        cfg = a11y_gate.load_config(SHIPPED_CONFIG)
        _rc, report = self.run_gate(_axe_every_level(), cfg)
        self.assertEqual(report["config"]["blocking"], ["critical", "serious"])
        self.assertEqual(report["config"]["warn"], ["moderate", "minor"])
        self.assertEqual(report["config"]["incomplete"], "report-only")

    def test_raw_axe_payload_keys_are_pinned(self):
        """classify_violations bu iki listeyi okuyor; yoksa sessizce bos
        sonuc cikar (fail-open yonu). Ham payload ARTA basina tasindi."""
        _rc, report = self.run_gate(_axe_every_level(), self.cfg_with_allowlist())
        for pg in report["pages"]:
            self.assertIsInstance(pg["raw"], dict)
            for key in ("violations", "incomplete"):
                self.assertIsInstance(pg["raw"][key], list)

    def test_page_entry_keys_are_exact(self):
        _rc, report = self.run_gate(_axe_every_level(), self.cfg_with_allowlist())
        for pg in report["pages"]:
            self.assertEqual(set(pg), PAGE_KEYS, "sayfa girisi semasi degisti")
            self.assertIn(pg["verdict"], ("PASS", "FAIL"))
            self.assertEqual(set(pg["summary"]), SUMMARY_KEYS)

    def test_aggregate_equals_union_of_pages(self):
        """Toplam = sayfalarin birlesimi. Sayfa eklenince toplam kendiliğinden
        buyur (toplam elle hesaplanmiyor)."""
        cfg = self.cfg_with_allowlist()
        cfg["pages"] = [{"path": "/preview.html"}, {"path": "/guide.html"}]
        _rc, report = self.run_gate(_axe_every_level(), cfg)
        self.assertEqual(len(report["pages"]), 2)
        union = [row for pg in report["pages"] for row in pg["violations"]]
        self.assertEqual(report["violations"], union)
        self.assertEqual(report["summary"], a11y_gate._summary(union))
        self.assertEqual({r["page"] for r in report["violations"]},
                         {"/preview.html", "/guide.html"})

    def test_error_is_null_on_success(self):
        rc, report = self.run_gate({"violations": [], "incomplete": []},
                                   self.cfg_with_allowlist())
        self.assertEqual(rc, 0)
        self.assertIsNone(report["error"])
        self.assertTrue(report["pages"][0]["url"])


# ------------------------------------------------------------ konfig doğrulama

class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, cfg):
        p = os.path.join(self.tmp.name, "cfg.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return p

    def test_valid_config_loads(self):
        cfg = a11y_gate.load_config(self.write(base_cfg()))
        self.assertEqual(cfg["blocking"], ["critical", "serious"])

    def test_unknown_top_key_rejected(self):
        bad = base_cfg()
        bad["extra"] = 1
        with self.assertRaises(ValueError):
            a11y_gate.load_config(self.write(bad))

    def test_missing_top_key_rejected(self):
        bad = base_cfg()
        del bad["incomplete"]
        with self.assertRaises(ValueError):
            a11y_gate.load_config(self.write(bad))

    def test_blocking_warn_overlap_rejected(self):
        bad = base_cfg()
        bad["warn"] = ["serious"]
        with self.assertRaises(ValueError):
            a11y_gate.load_config(self.write(bad))

    def test_incomplete_policy_locked_to_report_only(self):
        bad = base_cfg()
        bad["incomplete"] = "block"
        with self.assertRaises(ValueError):
            a11y_gate.load_config(self.write(bad))

    def test_allowlist_entry_requires_reason(self):
        bad = base_cfg()
        bad["allowlist"] = [{"rule": "r1"}]
        with self.assertRaises(ValueError):
            a11y_gate.load_config(self.write(bad))

    def test_allowlist_entry_requires_rule(self):
        bad = base_cfg()
        bad["allowlist"] = [{"reason": "neden"}]
        with self.assertRaises(ValueError):
            a11y_gate.load_config(self.write(bad))

    def test_non_dict_rejected(self):
        p = os.path.join(self.tmp.name, "cfg.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write("[]")
        with self.assertRaises(ValueError):
            a11y_gate.load_config(p)


# ------------------------------------------------------------------ checksum

class ChecksumTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def bundle(self, content, pin_content=None):
        p = os.path.join(self.tmp.name, "axe.min.js")
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        import hashlib
        if pin_content is None:
            pin_content = content
        with open(p + ".sha256", "w", encoding="utf-8") as f:
            f.write(hashlib.sha256(pin_content.encode()).hexdigest() + "  axe.min.js\n")
        return p

    def test_matching_pin_passes(self):
        a11y_gate.verify_checksum(self.bundle("axe-source"))

    def test_mismatch_raises(self):
        with self.assertRaises(ValueError):
            a11y_gate.verify_checksum(self.bundle("axe-source", pin_content="farklı"))

    def test_missing_pin_raises(self):
        p = os.path.join(self.tmp.name, "axe.min.js")
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")
        with self.assertRaises(ValueError):
            a11y_gate.verify_checksum(p)


# ---------------------------------------------- main() sözleşme testleri

class GateContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_gate(self, argv, connect=None):
        out = os.path.join(self.tmp.name, "report.json")
        buf = io.StringIO()
        argv = argv + ["--output", out]
        if connect is not None:
            with mock.patch.object(a11y_gate, "collect", connect):
                with contextlib.redirect_stdout(buf):
                    rc = a11y_gate.main(argv)
        else:
            with contextlib.redirect_stdout(buf):
                rc = a11y_gate.main(argv)
        report = {}
        if os.path.exists(out):
            with open(out, encoding="utf-8") as f:
                report = json.load(f)
        return rc, buf.getvalue(), report

    def test_dead_port_fails_closed(self):
        # plan: "in-process HTTPServer contract test: server unreachable → FAIL"
        with dead_port() as url:
            rc, out, report = self.run_gate(["--base-url", url], connect=socket_probe_connect)
        self.assertEqual(rc, 1)
        self.assertIn("verdict: FAIL", out)
        self.assertIn("[ERROR]", out)
        # FAIL sayfa bazinda kaydedilir (ust duzey error yalnizca config/axe hatasi)
        self.assertEqual(report["pages"][0]["verdict"], "FAIL")
        self.assertIn("tarama arızası", report["pages"][0]["error"])

    def test_live_server_passes(self):
        with live_server() as url:
            rc, out, report = self.run_gate(["--base-url", url], connect=socket_probe_connect)
        self.assertEqual(rc, 0)
        self.assertIn("verdict: PASS", out)
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["summary"], {"blocking": 0, "warn": 0, "allowlisted": 0,
                                             "incomplete": 0, "incomplete_allowlisted": 0})
        shipped = a11y_gate.load_config(SHIPPED_CONFIG)
        expected = [pg["path"] for pg in shipped["pages"]]
        self.assertEqual([pg["path"] for pg in report["pages"]], expected)
        self.assertEqual([pg["verdict"] for pg in report["pages"]], ["PASS"] * len(expected))
        self.assertEqual(report["pages"][0]["url"], url.rstrip("/") + expected[0])
        self.assertEqual(report["config"]["blocking"], ["critical", "serious"])  # config echo

    def test_checksum_mismatch_fails_without_scan(self):
        called = []

        def must_not_scan(base_url, axe_src, page_path):
            called.append(True)
            raise AssertionError("checksum uyuşmazlığında taranmamalı")

        p = os.path.join(self.tmp.name, "axe.min.js")
        with open(p, "w", encoding="utf-8") as f:
            f.write("değişmiş-bundle")
        with open(p + ".sha256", "w", encoding="utf-8") as f:
            f.write("0" * 64 + "  axe.min.js\n")
        rc, out, report = self.run_gate(["--base-url", "http://127.0.0.1:1", "--axe", p],
                                        connect=must_not_scan)
        self.assertEqual(rc, 1)
        self.assertFalse(called)
        self.assertIn("[AXE]", out)
        self.assertIn("checksum", report["error"])

    def test_invalid_config_fails(self):
        bad = os.path.join(self.tmp.name, "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            json.dump({"blocking": ["critical"]}, f)  # eksik anahtarlar
        rc, out, report = self.run_gate(["--base-url", "http://127.0.0.1:1", "--config", bad])
        self.assertEqual(rc, 1)
        self.assertIn("[CONFIG]", out)
        self.assertIn("eksik anahtar", report["error"])

    def test_missing_playwright_is_exit_2(self):
        def no_playwright(base_url, axe_src, page_path):
            raise ImportError("playwright")

        rc, out, _ = self.run_gate(["--base-url", "http://127.0.0.1:1"], connect=no_playwright)
        self.assertEqual(rc, 2)
        self.assertNotIn("verdict:", out)  # kullanım/ortam hatası — verdict yok
        self.assertIn("playwright", out)

    def test_blocking_violation_report_shape(self):
        def scan(base_url, axe_src, page_path):
            return ({"violations": [axe_v("color-contrast", "serious", nodes=[node(["#x"])])],
                     "incomplete": []}, base_url + page_path)

        cfg = os.path.join(self.tmp.name, "one_page.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(base_cfg(), f)  # tek sayfa — sayfa sayisi sonucu degistirmesin
        rc, out, report = self.run_gate(
            ["--base-url", "http://127.0.0.1:1", "--config", cfg], connect=scan)
        self.assertEqual(rc, 1)
        self.assertEqual(report["summary"]["blocking"], 1)
        self.assertEqual(report["violations"][0]["page"], "/preview.html")
        self.assertEqual(report["violations"][0]["rule"], "color-contrast")
        self.assertEqual(report["violations"][0]["level"], "blocking")
        self.assertEqual(report["violations"][0]["nodes"], 1)
        self.assertIn("color-contrast", out)  # stdout tablosu

    def test_allowlisted_violation_reported_not_hidden(self):
        cfg = os.path.join(self.tmp.name, "cfg.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({**base_cfg(), "allowlist": [{"rule": "r1", "reason": "kayitli borc"}]}, f)

        def scan(base_url, axe_src, page_path):
            return ({"violations": [axe_v("r1", "serious")], "incomplete": []}, base_url + page_path)

        rc, out, report = self.run_gate(["--base-url", "http://127.0.0.1:1", "--config", cfg], connect=scan)
        self.assertEqual(rc, 0)
        self.assertEqual(report["violations"][0]["level"], "allowlisted")
        self.assertEqual(report["violations"][0]["reasons"], ["kayitli borc"])
        self.assertEqual(report["summary"]["allowlisted"], 1)
        self.assertIn("ALLOWLISTED", out)  # borç raporda görünür


if __name__ == "__main__":
    unittest.main()
