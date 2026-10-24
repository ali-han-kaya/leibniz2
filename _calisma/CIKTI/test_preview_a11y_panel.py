#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_preview_a11y_panel.py — a11y-gate dashboard panelinin regresyon kapısı.

Panel, verdict/summary verisini CI artifact JSON'larından (`a11y_<sayfa>_<tema>.json`,
verify.yml a11y-gate job'ı) okur; `/api/a11y` yalnız verdict + dört özet sayısını
taşır (ham axe payload'ı bilerek dışarı verilmez).

Bu dosya üç katmanı sabitler:

  1. Sunucu mantığı (preview_server.load_a11y_reports): artifact adı, aday
     konumlar (flat + download-artifact alt dizini), eksik/bozuk/taşkın rapor,
     summary varsayılanları — hepsi fail-closed.
  2. Panel kararı: renderA11y()'nin rozet sınıfı/ikon/etiket mantığının Python
     karşılığı (verdict null → asla yeşil değil).
  3. Senkron guard'ları: preview.html iskeleti, preview.js render/load +
     SSE/init çağrıları, verify.yml artifact adları.

stdlib unittest — ek bağımlılık yok.
"""
import json
import os
import pathlib
import sys
import tempfile
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PREVIEW_HTML = SCRIPT_DIR / "preview.html"
PREVIEW_JS = SCRIPT_DIR / "preview.js"
PREVIEW_SERVER = SCRIPT_DIR / "preview_server.py"
VERIFY_YML = SCRIPT_DIR.parent.parent / ".github" / "workflows" / "verify.yml"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import preview_server as ps  # noqa: E402

# ── preview.js renderA11y() ile ortak sabitler (tek yol: escapeHTML) ──────────
PAGE_LABELS = {"dashboard": "dash", "guide": "guide", "landing": "landing"}
SUMMARY_KEYS = ("blocking", "warn", "allowlisted", "incomplete")


# ── renderA11y() mantığının Python karşılığı (preview.js ile senkron) ──────────
def a11y_badge(report):
    """Tek artifact → rozet {cls, ico, label}.

    Fail-closed kural: verdict PASS değilse yeşil (ok) ASLA olmaz —
    okunamayan/eksik rapor `warn` + "·" ikonuna düşer.
    """
    verdict = report.get("verdict")
    if verdict == "PASS":
        cls, ico = "ok", "✓"
    elif verdict == "FAIL":
        cls, ico = "err", "✗"
    else:
        cls, ico = "warn", "·"
    page = report.get("page")
    return {
        "cls": cls,
        "ico": ico,
        "label": "%s/%s" % (PAGE_LABELS.get(page, page), report.get("theme")),
    }


def panel_summary_line(reports):
    """a11y-ts satırı: rapor sayısı + toplam blocking."""
    blocking = sum(
        (r.get("summary") or {}).get("blocking") or 0 for r in reports
    )
    return "%d a11y raporu · blocking %d" % (len(reports), blocking)


def write_report(root, page, theme, payload):
    """Artifact'ı `root` altına a11y_artifact_name() ile yaz; yolu döndür."""
    d = os.path.join(root, "a11y-reports")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, ps.a11y_artifact_name(page, theme))
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(payload, str):
            f.write(payload)
        else:
            json.dump(payload, f, ensure_ascii=False)
    return path


class A11yRootMixin(unittest.TestCase):
    """REPO_ROOT/PREVIEW_DIR'i geçici dizine yönlendir (global state izole)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old_root = ps.REPO_ROOT
        self._old_preview = getattr(ps, "PREVIEW_DIR", None)
        self._had_preview = "PREVIEW_DIR" in vars(ps)
        ps.REPO_ROOT = self.tmp.name
        ps.PREVIEW_DIR = self.tmp.name
        self.addCleanup(self._restore)

    def _restore(self):
        ps.REPO_ROOT = self._old_root
        if self._had_preview:
            ps.PREVIEW_DIR = self._old_preview
        else:
            ps.PREVIEW_DIR = self._old_preview


# ─────────────────────────────────────────────────────────────────────────────
class TestArtifactName(A11yRootMixin):
    """Artifact adı tek kaynaktan (verify.yml ile aynı desen)."""

    def test_name_matches_ci_pattern(self):
        self.assertEqual(ps.a11y_artifact_name("dashboard", "dark"),
                         "a11y_dashboard_dark.json")
        self.assertEqual(ps.a11y_artifact_name("landing", "light"),
                         "a11y_landing_light.json")

    def test_pages_and_themes_are_fixed(self):
        self.assertEqual(ps.A11Y_PAGES, ("dashboard", "guide", "landing"))
        self.assertEqual(ps.A11Y_THEMES, ("dark", "light"))

    def test_candidates_are_deterministic_and_nested(self):
        a = ps._a11y_candidates("a11y_dashboard_dark.json")
        self.assertEqual(a, ps._a11y_candidates("a11y_dashboard_dark.json"),
                         "aday listesi sırası kararsız (panel hangi raporu "
                         "okuyacağı belli olmalı)")
        # Düz konumlar önce gelir (a11y-reports/<name>, <root>/<name>).
        self.assertEqual(
            a[0], os.path.join(self.tmp.name, "a11y-reports",
                               "a11y_dashboard_dark.json"))
        # download-artifact alt dizini de taranır.
        os.makedirs(os.path.join(self.tmp.name, "a11y-reports",
                                 "a11y-report-dark"), exist_ok=True)
        self.assertIn(
            os.path.join(self.tmp.name, "a11y-reports", "a11y-report-dark",
                         "a11y_dashboard_dark.json"),
            ps._a11y_candidates("a11y_dashboard_dark.json"))

    def test_missing_dirs_do_not_raise(self):
        # Hiç a11y-reports yoksa os.listdir OSError verir → sessizce atlanır.
        self.assertTrue(ps._a11y_candidates("a11y_dashboard_dark.json"))


# ─────────────────────────────────────────────────────────────────────────────
class TestLoadReports(A11yRootMixin):
    """load_a11y_reports() — fail-closed artifact okuma."""

    def test_no_artifact_is_not_available(self):
        out = ps.load_a11y_reports()
        self.assertFalse(out["available"], "artifact yokken PASS sayılamaz")
        self.assertEqual(out["reports"], [])
        self.assertIn("kanıt yok", out["note"])
        self.assertIn(ps.a11y_artifact_name("<page>", "<theme>"), out["note"])

    def test_reads_verdict_and_summary(self):
        write_report(self.tmp.name, "dashboard", "dark", {
            "verdict": "PASS",
            "summary": {"blocking": 0, "warn": 2, "allowlisted": 1,
                        "incomplete": 3},
        })
        out = ps.load_a11y_reports()
        self.assertTrue(out["available"])
        self.assertIsNone(out["note"])
        self.assertEqual(len(out["reports"]), 1)
        r = out["reports"][0]
        self.assertEqual(r["page"], "dashboard")
        self.assertEqual(r["theme"], "dark")
        self.assertEqual(r["verdict"], "PASS")
        self.assertEqual(r["summary"],
                         {"blocking": 0, "warn": 2, "allowlisted": 1,
                          "incomplete": 3})
        self.assertIsNone(r["error"])
        self.assertEqual(r["file"], "a11y_dashboard_dark.json")

    def test_missing_summary_keys_default_to_zero(self):
        write_report(self.tmp.name, "guide", "light", {"verdict": "PASS"})
        r = ps.load_a11y_reports()["reports"][0]
        self.assertEqual(r["summary"], {k: 0 for k in SUMMARY_KEYS})

    def test_fail_verdict_is_carried_verbatim(self):
        write_report(self.tmp.name, "landing", "dark", {
            "verdict": "FAIL",
            "summary": {"blocking": 7},
        })
        r = ps.load_a11y_reports()["reports"][0]
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["summary"]["blocking"], 7)

    def test_gate_error_is_carried_and_never_pass(self):
        write_report(self.tmp.name, "dashboard", "light", {
            "verdict": "FAIL", "error": "axe yüklenemedi"})
        r = ps.load_a11y_reports()["reports"][0]
        self.assertEqual(r["error"], "axe yüklenemedi")
        self.assertNotEqual(r["verdict"], "PASS")

    def test_corrupt_json_fails_closed(self):
        write_report(self.tmp.name, "guide", "dark", "{bozuk json")
        r = ps.load_a11y_reports()["reports"][0]
        self.assertIsNone(r["verdict"], "okunamayan rapor PASS olamaz")
        self.assertIn("rapor okunamadı", r["error"])

    def test_non_dict_json_fails_closed(self):
        write_report(self.tmp.name, "guide", "light", [1, 2, 3])
        r = ps.load_a11y_reports()["reports"][0]
        self.assertIsNone(r["verdict"])
        self.assertIn("sözlük değil", r["error"])

    def test_oversize_report_is_refused_not_truncated(self):
        path = write_report(self.tmp.name, "dashboard", "dark", {"verdict": "PASS"})
        os.truncate(path, ps.A11Y_MAX_BYTES + 1)
        r = ps.load_a11y_reports()["reports"][0]
        self.assertIsNone(r["verdict"])
        self.assertIn("tavanı aşıldı", r["error"])

    def test_nested_artifact_directory_is_discovered(self):
        d = os.path.join(self.tmp.name, "a11y-reports", "a11y-guide-report-dark")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, ps.a11y_artifact_name("guide", "dark")),
                  "w", encoding="utf-8") as f:
            json.dump({"verdict": "PASS"}, f)
        out = ps.load_a11y_reports()
        self.assertTrue(out["available"])
        self.assertEqual(out["reports"][0]["page"], "guide")

    def test_all_six_slots_are_covered(self):
        for page in ps.A11Y_PAGES:
            for theme in ps.A11Y_THEMES:
                write_report(self.tmp.name, page, theme, {"verdict": "PASS"})
        out = ps.load_a11y_reports()
        self.assertEqual(len(out["reports"]), 6)
        self.assertEqual(
            sorted({(r["page"], r["theme"]) for r in out["reports"]}),
            sorted((p, t) for p in ps.A11Y_PAGES for t in ps.A11Y_THEMES))

    def test_one_report_per_slot_even_if_duplicated(self):
        # Aynı artifact hem düz hem alt dizinde varsa ilk aday kazanır.
        write_report(self.tmp.name, "dashboard", "dark", {"verdict": "PASS"})
        d = os.path.join(self.tmp.name, "a11y-reports", "a11y-report-dark")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, ps.a11y_artifact_name("dashboard", "dark")),
                  "w", encoding="utf-8") as f:
            json.dump({"verdict": "FAIL"}, f)
        out = ps.load_a11y_reports()
        self.assertEqual(len(out["reports"]), 1)
        self.assertEqual(out["reports"][0]["verdict"], "PASS")


# ─────────────────────────────────────────────────────────────────────────────
class TestPanelDecision(unittest.TestCase):
    """renderA11y() rozet kararı — ölçülmemiş PASS yok."""

    def test_pass_is_ok(self):
        b = a11y_badge({"verdict": "PASS", "page": "dashboard", "theme": "dark"})
        self.assertEqual((b["cls"], b["ico"], b["label"]),
                         ("ok", "✓", "dash/dark"))

    def test_fail_is_err(self):
        b = a11y_badge({"verdict": "FAIL", "page": "guide", "theme": "light"})
        self.assertEqual((b["cls"], b["ico"], b["label"]),
                         ("err", "✗", "guide/light"))

    def test_unreadable_report_is_never_ok(self):
        for verdict in (None, "", "BILINMIYOR", "pass"):
            b = a11y_badge({"verdict": verdict, "page": "landing",
                            "theme": "dark"})
            self.assertNotEqual(b["cls"], "ok",
                                "verdict=%r yeşile düşmemeli" % verdict)
            self.assertEqual(b["cls"], "warn")
            self.assertEqual(b["ico"], "·")

    def test_unknown_page_label_falls_back_to_raw(self):
        b = a11y_badge({"verdict": "PASS", "page": "yeni-sayfa",
                        "theme": "dark"})
        self.assertEqual(b["label"], "yeni-sayfa/dark")

    def test_summary_line_counts_blocking(self):
        self.assertEqual(
            panel_summary_line([
                {"summary": {"blocking": 2}},
                {"summary": {"blocking": 0}},
                {"summary": None},
            ]),
            "3 a11y raporu · blocking 2")

    def test_no_reports_line_still_states_no_evidence(self):
        self.assertEqual(panel_summary_line([]), "0 a11y raporu · blocking 0")


# ─────────────────────────────────────────────────────────────────────────────
class TestPreviewSync(unittest.TestCase):
    """preview.html + preview.js + verify.yml senkron guard'ları."""

    def _js(self):
        return PREVIEW_JS.read_text(encoding="utf-8")

    def test_html_has_panel_skeleton(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn('id="a11y-panel"', html)
        self.assertIn('id="a11y-ts"', html)

    def test_js_defines_render_and_load(self):
        js = self._js()
        self.assertIn("function renderA11y", js)
        self.assertIn("function loadA11y", js)
        self.assertIn('fetch("/api/a11y?_t=" + Date.now())', js)

    def test_js_is_called_on_init_and_on_sse_events(self):
        js = self._js()
        # 1 kez tanım + 1 kez ilk yükleme + snapshot + update = 4 kez "()".
        self.assertEqual(js.count("loadA11y()"), 4,
                         "loadA11y init + SSE snapshot + SSE update'te "
                         "çağrılmalı")
        for evt in ("snapshot", "update"):
            body = js.split('addEventListener("%s"' % evt, 1)[1]
            branch = body.split("evtSource.addEventListener", 1)[0]
            self.assertIn("loadA11y()", branch,
                          "%s olayında a11y paneli yenilenmiyor" % evt)

    def test_js_escapes_every_dynamic_field(self):
        # Nitelik (title) ve metin bağlamı — ikisi de kaçırılmalı.
        js = self._js()
        start = js.index("function renderA11y")
        body = js[start:js.index("function loadA11y")]
        self.assertGreaterEqual(
            body.count("escapeHTML("), 2,
            "label (metin) + tip (nitelik) ikisi de escapeHTML'dan geçmeli")
        self.assertNotIn("${", body,
                         "template literal iç açılışı: kaçış tek yol olmalı")

    def test_js_uses_shared_cls_ico_helpers(self):
        js = self._js()
        body = js[js.index("function renderA11y"):js.index("function loadA11y")]
        self.assertIn("_cls(st)", body)
        self.assertIn("_ico(st)", body)

    def test_panel_never_invents_pass_when_no_artifact(self):
        js = self._js()
        self.assertIn("a11y-gate: kanıt yok", js)

    def test_verify_workflow_writes_the_same_artifact_names(self):
        yml = VERIFY_YML.read_text(encoding="utf-8")
        for page in ps.A11Y_PAGES:
            for theme in ps.A11Y_THEMES:
                name = ps.a11y_artifact_name(page, theme)
                # Tek job iki temayı döngüde tarar; artifact adları artık
                # şablonda değil, doğrudan üretim adımında yazılır.
                self.assertIn(name, yml,
                              "verify.yml %s üretmiyor — panel verisiz kalır"
                              % name)

    def test_server_routes_and_documents_endpoint(self):
        src = PREVIEW_SERVER.read_text(encoding="utf-8")
        self.assertIn('"/api/a11y"', src)
        self.assertIn("def serve_a11y", src)
        self.assertIn("def load_a11y_reports", src)
        self.assertIn("route == \"a11y\"", src)
        # Ham payload dışarı verilmemeli (bellek + gizlilik yüzeyi).
        body = src[src.index("def load_a11y_reports"):src.index("class Handler")]
        self.assertNotIn('"raw"', body,
                         "ham axe payload panel yüküne girmemeli")


class TestApiContractEntry(unittest.TestCase):
    """API_CONTRACT/OpenAPI zinciri — yeni uc unutulmasın."""

    def test_contract_is_get_only(self):
        from test_api_method_contract import API_CONTRACT, LIVE_URLS
        self.assertEqual(API_CONTRACT.get("/api/a11y"), {"GET"})
        self.assertEqual(LIVE_URLS.get("/api/a11y"), "/api/a11y")

    # NOT (kapsam sınırı): `/api/a11y`'nin OpenAPI dokümanında görünmesi
    # `openapi.json` + üreticisi (`gen_openapi.py`) ile birlikte gelir; o
    # ikili bu PR'ın konusu değil (ayrı, henüz commit'lenmemiş bir API
    # sözleşmesi iş parçacığı). Yeni uç, sözleşme tarafında API_CONTRACT/
    # LIVE_URLS girdileriyle bağlanır; doküman üretimi kendi PR'ında bu
    # testi de geri getirmelidir.

    def test_api_contract_route_dispatch_pair(self):
        from test_api_method_contract import API_CONTRACT
        src = PREVIEW_SERVER.read_text(encoding="utf-8")
        # Sözleşmedeki GET-only yollar do_POST'ta literal görünmemeli.
        post_body = src.split("def do_POST(self):", 1)[1].split("\n    def ", 1)[0]
        for path, methods in API_CONTRACT.items():
            if "GET" in methods and path != "/api/run-stdout":
                self.assertNotIn('"%s"' % path, post_body,
                                 "%s GET-only ama do_POST'ta var" % path)


if __name__ == "__main__":
    unittest.main(verbosity=2)