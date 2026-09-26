#!/usr/bin/env python3
"""test_a11y_gate.py — a11y_gate için tarayıcısız (browser-free) test süiti.

Spec: docs/superpowers/specs/2026-09-17-a11y-gate-design.md (§Testing)
Plan: docs/superpowers/plans/2026-09-17-a11y-gate-implementation.md (T4)

Kapsam: saf-unit (eşikleme, bilinmeyen-severity fail-closed, allowlist,
rapor şekli) + in-process sözleşme testleri (ölü port → FAIL, canlı sunucu →
PASS, checksum uyuşmazlığı → FAIL, geçersiz konfig → FAIL) + sayfa kapsamı
(witness, --page ve üç sayfanın iki-tema axe CI yüzeyi + dashboard'ın
Lighthouse yüzeyi). Tarayıcı entegrasyonu (gerçek
Playwright koşumu) CI job'ının kendisidir; bu süit Playwright'a dokunmaz —
sürücü dikşi `collect` üzerinden sahte bir soket-kanıt sürücüyle
değiştirilir (gerçek TCP davranışı korunur).
"""

import contextlib
import io
import json
import os
import re
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
GUIDE_HTML = os.path.join(
    REPO_ROOT, "docs", "branch-protection-guide", "guide.html")
LANDING_SRC = os.path.join(REPO_ROOT, "_calisma", "landing", "landing_src.html")
LANDING_HTML = os.path.join(REPO_ROOT, "_calisma", "landing", "landing.html")
LANDING_ASSETS = os.path.join(REPO_ROOT, "_calisma", "landing", "assets")
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import a11y_gate  # noqa: E402


# ----------------------------------------------------------------- yardımcılar

def node(target=("body",)):
    return {"target": list(target)}


def axe_v(rule, impact, nodes=None):
    return {"id": rule, "impact": impact, "nodes": nodes if nodes is not None else [node()]}


def base_cfg():
    return {
        "blocking": ["critical", "serious"],
        "warn": ["moderate", "minor"],
        "incomplete": "report-only",
        "allowlist": [],
        "pages": [
            {
                "path": "/preview.html",
                "witness": "Stoic-Hume V5 — Live CI Dashboard",
            },
            {
                "path": "/guide.html",
                "witness": "Ayarlar → Branches — kural listesi boş",
            },
            {
                "path": "/landing.html",
                "witness": "teslim anına kadar.",
            },
        ],
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


def socket_probe_connect(base_url, axe_src, page_path="/preview.html", witness=None,
                         theme="dark"):
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

    def test_incomplete_preserves_node_targets_and_element_html(self):
        results = {"violations": [], "incomplete": [{
            "id": "color-contrast", "impact": "serious", "nodes": [{
                "target": ["#trend", "text"],
                "html": '<text x="38" y="16">1</text>',
            }],
        }]}
        row = a11y_gate.classify_violations(results, base_cfg())[0]
        self.assertEqual(row["node_targets"], [["#trend", "text"]])
        self.assertEqual(row["node_html"], ['<text x="38" y="16">1</text>'])

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

    def test_allowlist_marks_but_does_not_hide_incomplete_seal_nodes(self):
        cfg = base_cfg()
        cfg["allowlist"] = [
            {"rule": "color-contrast", "target": "#seal-ring-path",
             "reason": "SVG halka metni bilinçli imza katmanı"},
            {"rule": "color-contrast", "target": ".seal-verdict",
             "reason": "SVG merkez metni bilinçli imza katmanı"},
            {"rule": "color-contrast", "target": ".seal-hash",
             "reason": "SVG hash metni bilinçli imza katmanı"},
        ]
        results = {"violations": [], "incomplete": [{
            "id": "color-contrast", "impact": "serious", "nodes": [
                {"target": ["#seal-ring-path"],
                 "html": '<textPath id="seal-ring-path">VERIFIED • ABC</textPath>'},
                {"target": [".seal-verdict"],
                 "html": '<text class="seal-verdict">VERIFIED</text>'},
                {"target": [".seal-hash"],
                 "html": '<text class="seal-hash">ABC123…</text>'},
                {"target": ["#unrelated"],
                 "html": '<span id="unrelated">other</span>'},
            ],
        }]}
        row = a11y_gate.classify_violations(results, cfg)[0]
        self.assertEqual(row["level"], "incomplete")
        self.assertEqual(row["nodes"], 1)
        self.assertEqual(row["allowlisted_nodes"], 3)
        self.assertEqual(row["reasons"], [
            "SVG halka metni bilinçli imza katmanı",
            "SVG merkez metni bilinçli imza katmanı",
            "SVG hash metni bilinçli imza katmanı",
        ])
        self.assertEqual(row["node_targets"], [
            ["#seal-ring-path"], [".seal-verdict"], [".seal-hash"], ["#unrelated"],
        ])
        self.assertEqual(row["node_html"], [
            '<textPath id="seal-ring-path">VERIFIED • ABC</textPath>',
            '<text class="seal-verdict">VERIFIED</text>',
            '<text class="seal-hash">ABC123…</text>',
            '<span id="unrelated">other</span>',
        ])
        self.assertEqual(a11y_gate.decide_verdict([row]), "PASS")

    def test_overlapping_allowlist_entries_count_each_node_once(self):
        cfg = base_cfg()
        cfg["allowlist"] = [
            {"rule": "r1", "target": "#seal", "reason": "birinci gerekçe"},
            {"rule": "r1", "target": "#seal", "reason": "ikinci gerekçe"},
        ]
        results = {"violations": [axe_v("r1", "serious", nodes=[node(["#seal"])])],
                   "incomplete": []}
        row = a11y_gate.classify_violations(results, cfg)[0]
        self.assertEqual(row["level"], "allowlisted")
        self.assertEqual(row["nodes"], 0)
        self.assertEqual(row["allowlisted_nodes"], 1)
        self.assertEqual(row["reasons"], ["birinci gerekçe"])


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

    def test_repo_config_declares_dashboard_guide_and_landing_witnesses(self):
        cfg = a11y_gate.load_config(
            os.path.join(SCRIPT_DIR, "a11y_gate_config.json"))
        self.assertEqual(
            [(entry["path"], entry["witness"]) for entry in cfg["pages"]],
            [
                ("/preview.html", "Stoic-Hume V5 — Live CI Dashboard"),
                ("/guide.html", "Ayarlar → Branches — kural listesi boş"),
                ("/landing.html", "teslim anına kadar."),
            ],
        )

    def test_repo_config_allowlists_actual_svg_seal_targets_with_reason(self):
        cfg = a11y_gate.load_config(
            os.path.join(SCRIPT_DIR, "a11y_gate_config.json"))
        seal_entries = [entry for entry in cfg["allowlist"]
                        if entry.get("rule") == "color-contrast"]
        self.assertEqual(
            {entry.get("target") for entry in seal_entries},
            {"#seal-ring-path", ".seal-verdict", ".seal-hash"},
        )
        self.assertTrue(all(entry.get("reason") for entry in seal_entries))
        with open(os.path.join(SCRIPT_DIR, "preview.html"), encoding="utf-8") as f:
            preview = f.read()
        self.assertIn('id="seal-ring-path"', preview)
        self.assertIn('class="seal-verdict"', preview)
        self.assertIn('class="seal-hash"', preview)

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

    def test_page_requires_witness(self):
        bad = base_cfg()
        bad["pages"] = [{"path": "/guide.html"}]
        with self.assertRaises(ValueError):
            a11y_gate.load_config(self.write(bad))

    def test_duplicate_page_path_rejected(self):
        bad = base_cfg()
        bad["pages"].append(dict(bad["pages"][0]))
        with self.assertRaises(ValueError):
            a11y_gate.load_config(self.write(bad))

    def test_non_dict_rejected(self):
        p = os.path.join(self.tmp.name, "cfg.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write("[]")
        with self.assertRaises(ValueError):
            a11y_gate.load_config(p)


# ------------------------------------------------------- landing source invariants

class LandingSourceTests(unittest.TestCase):
    """Landing'in CI sunum/a11y sözleşmesi kaynakta sabitlenir."""

    def test_landing_has_stable_body_witness_and_single_main(self):
        for path in (LANDING_SRC, LANDING_HTML):
            with open(path, encoding="utf-8") as f:
                html = f.read()
            self.assertIn("teslim anına kadar.", html)
            self.assertEqual(html.count("<main"), 1)
            self.assertIn("<h1>", html)

    def test_generated_landing_is_self_contained_and_theme_capable(self):
        with open(LANDING_HTML, encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("{{", html)
        self.assertNotIn("../../CIKTI/slides_z3", html)
        self.assertIn(':root[data-theme="light"]', html)
        for plate in ("P1-a.png", "P2.png", "P3-a.png"):
            self.assertTrue(os.path.isfile(os.path.join(LANDING_ASSETS, plate)), plate)
            self.assertIn('src="assets/%s"' % plate, html)


# ------------------------------------------------------- guide source invariants

class GuideSourceTests(unittest.TestCase):
    """Statik görsel kılavuzun tarayıcısız semantik sözleşmeleri.

    CI axe taraması canlı kanıttır; bu test aynı niyeti kaynakta erken
    yakalar: 39 checkbox'un ve örtük 4 branch-name text input'unun her biri
    erişilebilir ad taşır; sekiz ekran tek bir main landmark altında toplanır.
    """

    def setUp(self):
        with open(GUIDE_HTML, encoding="utf-8") as f:
            self.html = f.read()

    def test_every_checkbox_has_descriptive_aria_label(self):
        tags = re.findall(r"<input\b[^>]*\btype=[\"']checkbox[\"'][^>]*>",
                           self.html, flags=re.I)
        self.assertEqual(len(tags), 39)
        for tag in tags:
            self.assertRegex(tag, r"\baria-label=[\"'][^\"']+[\"']", tag)

    def test_every_text_input_has_accessible_name(self):
        tags = re.findall(r"<input\b[^>]*\btype=[\"']text[\"'][^>]*>",
                           self.html, flags=re.I)
        self.assertEqual(len(tags), 5)  # 1 explicit <label for> + 4 aria-label
        for tag in tags:
            self.assertTrue(
                re.search(r"\baria-label=[\"'][^\"']+[\"']", tag) or
                re.search(r"\bid=[\"'][^\"']+[\"']", tag),
                tag,
            )

    def test_all_screens_share_one_main_landmark(self):
        self.assertEqual(self.html.count("<main "), 1)
        self.assertIn("</main>\n</body>", self.html)


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
        self.assertIn("[SCAN]", out)
        self.assertIn("tarama arızası", report["error"])

    def test_live_server_passes(self):
        with live_server() as url:
            rc, out, report = self.run_gate(["--base-url", url], connect=socket_probe_connect)
        self.assertEqual(rc, 0)
        self.assertIn("verdict: PASS", out)
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["summary"], {"blocking": 0, "warn": 0, "allowlisted": 0, "incomplete": 0})
        self.assertEqual(report["page_url"], url.rstrip("/") + "/preview.html")
        self.assertEqual(report["config"]["blocking"], ["critical", "serious"])  # config echo

    def test_checksum_mismatch_fails_without_scan(self):
        called = []

        def must_not_scan(base_url, axe_src, page_path, witness, theme="dark"):
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
        def no_playwright(base_url, axe_src, page_path, witness, theme="dark"):
            raise ImportError("playwright")

        rc, out, _ = self.run_gate(["--base-url", "http://127.0.0.1:1"], connect=no_playwright)
        self.assertEqual(rc, 2)
        self.assertNotIn("verdict:", out)  # kullanım/ortam hatası — verdict yok
        self.assertIn("playwright", out)

    def test_blocking_violation_report_shape(self):
        def scan(base_url, axe_src, page_path, witness, theme="dark"):
            return ({"violations": [axe_v("color-contrast", "serious", nodes=[node(["#x"])])],
                     "incomplete": []}, base_url + page_path)

        rc, out, report = self.run_gate(["--base-url", "http://127.0.0.1:1"], connect=scan)
        self.assertEqual(rc, 1)
        self.assertEqual(report["summary"]["blocking"], 1)
        self.assertEqual(report["violations"][0]["rule"], "color-contrast")
        self.assertEqual(report["violations"][0]["level"], "blocking")
        self.assertEqual(report["violations"][0]["nodes"], 1)
        self.assertIn("color-contrast", out)  # stdout tablosu

    def test_incomplete_report_contains_node_target_and_html(self):
        def scan(base_url, axe_src, page_path, witness, theme="dark"):
            return ({"violations": [], "incomplete": [{
                "id": "color-contrast", "impact": "serious", "nodes": [{
                    "target": ["#trend", "text"],
                    "html": '<text x="38" y="16">1</text>',
                }],
            }]}, base_url + page_path)

        rc, _, report = self.run_gate(["--base-url", "http://127.0.0.1:1"], connect=scan)
        self.assertEqual(rc, 0)
        self.assertEqual(report["violations"][0]["node_targets"], [["#trend", "text"]])
        self.assertEqual(report["violations"][0]["node_html"], ['<text x="38" y="16">1</text>'])

    def test_allowlisted_violation_reported_not_hidden(self):
        cfg = os.path.join(self.tmp.name, "cfg.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({**base_cfg(), "allowlist": [{"rule": "r1", "reason": "kayitli borc"}]}, f)

        def scan(base_url, axe_src, page_path, witness, theme="dark"):
            return ({"violations": [axe_v("r1", "serious")], "incomplete": []}, base_url + page_path)

        rc, out, report = self.run_gate(["--base-url", "http://127.0.0.1:1", "--config", cfg], connect=scan)
        self.assertEqual(rc, 0)
        self.assertEqual(report["violations"][0]["level"], "allowlisted")
        self.assertEqual(report["violations"][0]["reasons"], ["kayitli borc"])
        self.assertEqual(report["summary"]["allowlisted"], 1)
        self.assertIn("ALLOWLISTED", out)  # borç raporda görünür

    def test_requested_page_uses_configured_witness(self):
        calls = []

        def scan(base_url, axe_src, page_path, witness, theme="dark"):
            calls.append((page_path, witness, theme))
            return ({"violations": [], "incomplete": []}, base_url + page_path)

        rc, out, report = self.run_gate(
            ["--base-url", "http://127.0.0.1:1", "--page", "/guide.html"],
            connect=scan,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [
            ("/guide.html", "Ayarlar → Branches — kural listesi boş", "dark"),
        ])
        self.assertEqual(report["page_url"], "http://127.0.0.1:1/guide.html")
        self.assertIn("verdict: PASS", out)

    def test_landing_page_uses_configured_witness(self):
        calls = []

        def scan(base_url, axe_src, page_path, witness, theme="dark"):
            calls.append((page_path, witness, theme))
            return ({"violations": [], "incomplete": []}, base_url + page_path)

        rc, _, report = self.run_gate(
            ["--base-url", "http://127.0.0.1:1", "--page", "/landing.html"],
            connect=scan,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [("/landing.html", "teslim anına kadar.", "dark")])
        self.assertEqual(report["page_url"], "http://127.0.0.1:1/landing.html")

    def test_unconfigured_page_fails_closed(self):
        rc, out, report = self.run_gate([
            "--base-url", "http://127.0.0.1:1", "--page", "/not-allowed.html",
        ], connect=socket_probe_connect)
        self.assertEqual(rc, 1)
        self.assertIn("[CONFIG]", out)
        self.assertIn("kapsam dışı", report["error"])

    def test_light_theme_is_passed_to_driver_and_reported(self):
        calls = []

        def scan(base_url, axe_src, page_path, witness, theme="dark"):
            calls.append(theme)
            return ({"violations": [], "incomplete": []}, base_url + page_path)

        rc, _, report = self.run_gate(
            ["--base-url", "http://127.0.0.1:1", "--theme", "light"],
            connect=scan,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ["light"])
        self.assertEqual(report["theme"], "light")

    def test_unknown_theme_fails_closed_before_scan(self):
        called = []

        def scan(base_url, axe_src, page_path, witness, theme="dark"):
            called.append(theme)
            return ({"violations": [], "incomplete": []}, base_url + page_path)

        rc, out, report = self.run_gate(
            ["--base-url", "http://127.0.0.1:1", "--theme", "sepia"], connect=scan)
        self.assertEqual(rc, 1)
        self.assertEqual(called, [])
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["theme"], "sepia")
        self.assertIn("dark|light", report["error"])


class ThemeContractTests(unittest.TestCase):
    def test_apply_and_verify_theme_rejects_dom_drift(self):
        page = mock.Mock()
        page.evaluate.return_value = "light"
        a11y_gate._apply_theme(page, "light")
        page.evaluate.assert_called_once()
        a11y_gate._verify_theme(page, "light")

        page.evaluate.return_value = "dark"
        with self.assertRaisesRegex(ValueError, "tema witness"):
            a11y_gate._verify_theme(page, "light")

    def test_init_script_sets_validated_theme_before_navigation(self):
        browser = mock.Mock()
        context = browser.new_context.return_value
        a11y_gate._new_themed_page(browser, "light")
        browser.new_context.assert_called_once_with(bypass_csp=False)
        context.add_init_script.assert_called_once_with(
            script='document.documentElement.dataset.theme = "light";')
        context.new_page.assert_called_once_with()

    def test_dashboard_exposes_validated_theme_query_for_lighthouse(self):
        with open(os.path.join(SCRIPT_DIR, "preview.js"), encoding="utf-8") as f:
            source = f.read()
        self.assertIn("function themeQueryOverride()", source)
        self.assertIn('new URLSearchParams(window.location.search).get("theme")', source)
        self.assertIn('requested === "dark" || requested === "light"', source)
        self.assertIn("setTheme(queryTheme || storedTheme, !queryTheme)", source)


class TestReportVerdictField(unittest.TestCase):
    """a11y_report.json makine-okunur verdict taşimali (spec §Summary).

    Fail-closed sözlesme: alan her zaman mevcut; default "FAIL", yalniz
    basarili-scan sonunda hesaplanan degerle ezilir. Hata-yollari (config,
    checksum, tarama) raporu FAIL ile yazar.
    """

    def _run_invalid_config(self):
        # Eksik-anahtar config: tarayicisiz FAIL-path'e ulasan tek gercek akis
        # (load_config -> ValueError -> fail(1); kanitlanmis mevcut sözlesme).
        with tempfile.TemporaryDirectory() as td:
            cfg = os.path.join(td, "bad.json")
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump({"blocking": ["critical"]}, f)  # eksik anahtarlar
            out = os.path.join(td, "report.json")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = a11y_gate.main(["--base-url", "http://127.0.0.1:1",
                                     "--config", cfg, "--output", out])
            with open(out, encoding="utf-8") as f:
                report = json.load(f)
            return rc, buf.getvalue(), report

    def test_error_path_report_carries_fail_verdict(self):
        rc, out, report = self._run_invalid_config()
        self.assertEqual(rc, 1)
        self.assertIn("[CONFIG]", out)
        self.assertEqual(report["verdict"], "FAIL")

    def test_report_verdict_only_pass_or_fail(self):
        # Sözlesme-pin: rapor-verdict yalniz PASS/FAIL (default-deny).
        # Init dict-literal'de fail-closed default "FAIL"; basari-yolunda
        # hesaplanan degerle ezilir.
        with open(a11y_gate.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('report = {"verdict": "FAIL"', src)
        self.assertIn('report["verdict"] = verdict', src)


WORKFLOW = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))),
    ".github", "workflows", "verify.yml")


class TestWorkflowSummaryStep(unittest.TestCase):
    """Spec §Reporting-3: job özeti GITHUB_STEP_SUMMARY'ye yazılmalı.

    Adim raporu salt-okur render eder (verdict + summary + violations +
    error); if: always() — fail-closed: gate-kiriliminde de özet üretilir.
    """

    def _a11y_block(self):
        with open(WORKFLOW, encoding="utf-8") as f:
            text = f.read()
        block = text.split("  a11y-gate:", 1)[1]
        return block.split("\n  changelog-drift:", 1)[0]

    def _summary_step(self):
        return self._a11y_block().split("- name: Write a11y job summary", 1)[1]

    def test_summary_step_exists(self):
        self.assertIn("Write a11y job summary", self._a11y_block())

    def test_summary_step_always_and_writes_step_summary(self):
        step = self._summary_step()
        self.assertIn("if: always()", step)
        self.assertIn("GITHUB_STEP_SUMMARY", step)

    def test_summary_step_reads_report_verdict(self):
        # Task-1 sözleşmesi: özet, rapordaki verdict alanını okumalı.
        self.assertIn('data.get("verdict"', self._summary_step())

    def test_summary_step_covers_dashboard_guide_and_landing_reports(self):
        step = self._summary_step()
        self.assertIn('"a11y_dashboard_%s.json" % theme', step)
        self.assertIn('"a11y_guide_%s.json" % theme', step)
        self.assertIn('"a11y_landing_%s.json" % theme', step)
        self.assertIn('"lighthouse_dashboard_%s.json" % theme', step)
        self.assertIn("Dashboard", step)
        self.assertIn("Branch protection guide", step)
        self.assertIn("Landing", step)
        self.assertIn("A11Y_THEME", step)

    def test_ci_scans_all_configured_pages_independently(self):
        block = self._a11y_block()
        self.assertIn("needs: [verify]", block)
        self.assertIn("name: run-history", block)
        self.assertIn("path: run-history/", block)
        self.assertIn('"--snapshot-file", "run-history/history.jsonl"',
                      block)
        self.assertIn('"--no-verify"', block)
        self.assertIn(
            "cp docs/branch-protection-guide/guide.html "
            "_calisma/CIKTI/guide.html",
            block,
        )
        self.assertIn("--page /preview.html", block)
        self.assertIn('--output "a11y_dashboard_${{ matrix.theme }}.json"', block)
        self.assertIn("--page /guide.html", block)
        self.assertIn('--output "a11y_guide_${{ matrix.theme }}.json"', block)
        self.assertIn("python3 _calisma/landing/build_landing.py", block)
        self.assertIn('--snapshot-url "http://127.0.0.1:$port/api/latest"',
                      block)
        self.assertIn("--hash-field raw", block)
        self.assertIn("--output _calisma/CIKTI/landing.html", block)
        self.assertIn("--assets-dir _calisma/CIKTI/landing/assets", block)
        self.assertNotIn("qpdf_determinism_output", block)
        self.assertIn("--page /landing.html", block)
        self.assertIn('--output "a11y_landing_${{ matrix.theme }}.json"', block)
        self.assertIn("matrix:", block)
        self.assertIn("theme: [dark, light]", block)
        for step_name in ("guide", "landing"):
            step = block.split("- name: Run a11y gate — %s" % step_name, 1)[1]
            step = step.split("- name:", 1)[0]
            self.assertIn("if: always()", step)

    def test_landing_report_has_theme_suffixed_artifact(self):
        block = self._a11y_block()
        upload = block.split("- name: Upload landing a11y report", 1)[1]
        self.assertIn("name: a11y-landing-report-${{ matrix.theme }}", upload)
        self.assertIn("path: a11y_landing_${{ matrix.theme }}.json", upload)

    def test_guide_report_has_theme_suffixed_artifact(self):
        block = self._a11y_block()
        upload = block.split("- name: Upload guide a11y report", 1)[1]
        self.assertIn("name: a11y-guide-report-${{ matrix.theme }}", upload)
        self.assertIn("path: a11y_guide_${{ matrix.theme }}.json", upload)

    def test_lighthouse_dashboard_scan_is_theme_matrix_fail_closed(self):
        block = self._a11y_block()
        self.assertIn("actions/setup-node@v7", block)
        self.assertIn("Resolve Chromium for Lighthouse", block)
        self.assertIn("npx --yes lighthouse@13.5.0", block)
        self.assertIn("--only-categories=accessibility", block)
        self.assertIn("?theme=${A11Y_THEME}", block)
        self.assertIn('score != 1', block)
        self.assertIn("Lighthouse accessibility score PASS değil", block)
        step = block.split("- name: Run Lighthouse accessibility — dashboard", 1)[1]
        step = step.split("- name:", 1)[0]
        self.assertIn("if: always()", step)

    def test_lighthouse_report_has_theme_suffixed_artifact(self):
        block = self._a11y_block()
        upload = block.split("- name: Upload Lighthouse dashboard report", 1)[1]
        self.assertIn("name: lighthouse-dashboard-${{ matrix.theme }}", upload)
        self.assertIn("path: lighthouse_dashboard_${{ matrix.theme }}.json", upload)


if __name__ == "__main__":
    unittest.main()
