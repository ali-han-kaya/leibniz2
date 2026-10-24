#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_browser_skip_audit.py — tarayıcı-atlamalı süitlerin sessiz yeşil denetimi.

Ölçülen boşluk: CI'ın `verify` job'ında Playwright/Chromium yoktur; tarayıcı
gerekirken süitler `skipIf` ile ATLANIR ve unittest rc=0 döner — "keşfedildi"
"koştu" değildir. CSP + klavye için `test_functional_browser_ci.py` bu zinciri
kapatıyordu, ama diğer on süit (escaping, hover, CLS, CWV, capture, battery,
...) için "hangi atlama nerede koşuyor" sorusunun TEK cevabı yoktu. Yeni bir
`skipIf(playwright)` dosyası da sessizce yeşil kalıyordu.

Kural (fail-closed): tarayıcı kapısı taşıyan HER test dosyası kayıtlı bir
hüküm taşımak zorunda; kayıtsız dosya = KIRMIZI. Hüküm tipleri:

  * ci-step   — CI'da tarayıcılı job adımında skip-reddetmeli koşum. Kanıt:
    verify.yml'de job → adım (modülü koşturur) + bekçi (skip reddi /
    zorunlu-tarayıcı env'i / rapor-boşluk kontrolü). Üç parça da metinden
    aranır; biri eksikse kırmızı.
  * static    — aynı dosyada tarayıcısız koşan sınıf. Kanıt: sınıf dosyada
    var VE dosya `check_unit_tests.list`'te (batarya + CI verify'da koşar).
    Denetim sınıfı ÇALIŞTIRMAZ (çalıştırma bataryanın işi; burada hüküm
    kaydı sabitlenir).
  * battery   — yalnız pre-commit bataryasında koşar (venv Chromium,
    fail-closed toolchain). Kanıt: `check_unit_tests.list` üyeliği. CI
    `verify`'da atlar — KAYITLI atlama (sessiz değil).
  * advisory  — bilinçli bloke-dışı (örn. webkit-smoke, doc-üretim PNG'leri).
    Kanıt: dosyadaki "teslim kapısı değildir"/"advisory" işareti veya
    workflow'da `continue-on-error` + advisory adı. Yeni dosya bu hükmü
    gerekçesiz alamaz (kayıt metni zorunlu).

Kapsam: `_calisma/CIKTI/test_*.py` + `docs/branch-protection-guide/test_*.py`
(aynı süpürme, aynı kayıt — doc testleri ikinci sınıf değil).

Süpürme kapı kalıpları (yorum değil, GERÇEK kapı):
  `from playwright` / `import playwright` (satır başı import),
  `sync_playwright is None`, `BROWSER_MISSING`, `CHROMIUM_MISSING`,
  `_chromium_missing()`, `_HAVE_PLAYWRIGHT`, `safedriver`.

stdlib-only, OFFLINE (ağ yok; workflow metni diskten okunur).
"""

import pathlib
import re
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"
MANIFEST = HERE / "check_unit_tests.list"
DOCS_DIR = ROOT / "docs" / "branch-protection-guide"

# ── kapı kalıpları ─────────────────────────────────────────────────────
# Yorum/satır-içi bahis değil, import + kapı ifadesi aranır (`test_gate_*` gibi
# "playwright"ı yalnız anlatan dosyalar eşleşmemeli).
_GATE_RES = [
    re.compile(r"(?m)^\s*from playwright[.\s]"),
    re.compile(r"(?m)^\s*import playwright\b"),
    re.compile(r"sync_playwright is None"),
    re.compile(r"BROWSER_MISSING"),
    re.compile(r"CHROMIUM_MISSING"),
    re.compile(r"_chromium_missing\(\)"),
    re.compile(r"_HAVE_PLAYWRIGHT"),
    # safedriver: line-start anchored to avoid false positive on comments like "# (macOS safedriver)"
    re.compile(r"(?m)^\s*safedriver"),
]

def _has_gate(src):
    return any(rx.search(src) for rx in _GATE_RES)

# Denetim kendine kapı sanmamalı: kalıplar burada yalnız regex/yorum
# literalidir (gerçek `playwright` import'u yok — negatif testelowda sabitli).
_SELF = "test_browser_skip_audit.py"

def _sweep():
    """Tarayıcı kapılı dosyalar: {görünen-yol: kaynak-metin}."""
    found = {}
    for path in sorted(HERE.glob("test_*.py")):
        if path.name == _SELF:
            continue
        src = path.read_text(encoding="utf-8")
        if _has_gate(src):
            found[path.name] = src
    if DOCS_DIR.is_dir():
        for path in sorted(DOCS_DIR.glob("test_*.py")):
            src = path.read_text(encoding="utf-8")
            if _has_gate(src):
                found["docs/branch-protection-guide/" + path.name] = src
    return found

def _manifest_members():
    members = set()
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            members.add(line)
    return members

# ── hüküm kaydı ────────────────────────────────────────────────────────
# dosya → hükümler listesi. Her hüküm (tip, kanıt-sözlüğü).
REGISTRY = {
    # Güvenlik tarayıcı tier'ı (a11y-gate): check_security_posture.sh skip
    # sayısını reddeder (PASS ≠ koştu).
    "test_preview_escaping.py": [
        ("ci-step", {"job": "a11y-gate",
                     "step": "Security browser tier",
                     "module": "check_security_browser.list",
                     "roster": "check_security_browser.list",
                     "runner": "check_security_posture.sh",
                     "guard": "SKIP ETTI"}),
    ],
    "test_preview_hover_tooltip.py": [
        ("ci-step", {"job": "a11y-gate",
                     "step": "Security browser tier",
                     "module": "check_security_browser.list",
                     "roster": "check_security_browser.list",
                     "runner": "check_security_posture.sh",
                     "guard": "SKIP ETTI"}),
    ],
    "test_dashboard_budget_rh_filters.py": [
        ("ci-step", {"job": "a11y-gate",
                     "step": "Security browser tier",
                     "module": "check_security_browser.list",
                     "roster": "check_security_browser.list",
                     "runner": "check_security_posture.sh",
                     "guard": "SKIP ETTI"}),
    ],
    "test_preview_uncovered_surface.py": [
        ("ci-step", {"job": "a11y-gate",
                     "step": "Security browser tier",
                     "module": "check_security_browser.list",
                     "roster": "check_security_browser.list",
                     "runner": "check_security_posture.sh",
                     "guard": "SKIP ETTI"}),
    ],
    # Hover-tooltip CSP süiti: verify job'ında gerçek Chromium'la koşar;
    # tam-skip (0 test) `check_zero_check_fail_open.py --unittest-log` ile reddedilir.
    "test_design_preview_hover_csp.py": [
        ("ci-step", {"job": "verify",
                     "step": "Hover tooltip CSP suite",
                     "module": "test_design_preview_hover_csp.py",
                     "guard": "check_zero_check_fail_open.py"}),
    ],
    "test_dashboard_keyboard_nav.py": [
        ("ci-step", {"job": "dashboard-smoke",
                     "step": "Keyboard functional suite",
                     "module": "test_dashboard_keyboard_nav",
                     "guard": "SKIP etti"}),
    ],
    "test_dashboard_csp_nonce.py": [
        ("ci-step", {"job": "dashboard-smoke",
                     "step": "Dashboard CSP+nonce smoke",
                     "module": "test_dashboard_csp_nonce",
                     "guard": "LEIBNIZ2_REQUIRE_BROWSER"}),
    ],
    "test_dashboard_playwright_smoke.py": [
        ("ci-step", {"job": "dashboard-smoke",
                     "step": "Dashboard render smoke",
                     "module": "test_dashboard_playwright_smoke",
                     "guard": "SKIP etti"}),
    ],
    "test_incidental_banner.py": [
        ("ci-step", {"job": "dashboard-smoke",
                     "step": "Dashboard interaction smoke",
                     "module": "test_incidental_banner.py",
                     "guard": "SKIP etti"}),
    ],
    # Next canlı üçlüsü: derleme + Chromium job'ında skip=red bekçili.
    "test_dashboard_next_surface_smoke.py": [
        ("ci-step", {"job": "dashboard-smoke",
                     "step": "Next live suites",
                     "module": "test_dashboard_next_surface_smoke",
                     "guard": "SKIP etti"}),
    ],
    "test_dashboard_next_live_stream.py": [
        ("ci-step", {"job": "dashboard-smoke",
                     "step": "Next live suites",
                     "module": "test_dashboard_next_live_stream",
                     "guard": "SKIP etti"}),
    ],
    "test_dashboard_panel_isolation.py": [
        ("ci-step", {"job": "dashboard-smoke",
                     "step": "Next live suites",
                     "module": "test_dashboard_panel_isolation",
                     "guard": "SKIP etti"}),
    ],
    "test_preview_interaction_cdp.py": [
        ("ci-step", {"job": "dashboard-smoke",
                     "step": "Interaction E2E",
                     "module": "test_preview_interaction_cdp",
                     "guard": "SKIP etti"}),
        ("static", {"class": "InlineHandlerCspContractTest"}),
        ("static", {"class": "ScrollableRegionFocusContractTest"}),
    ],
    # CLS: rapor-boşluk bekçili (rapor yazılmadı/boşsa adım kırmızı).
    "test_dashboard_cls_budget.py": [
        ("ci-step", {"job": "a11y-gate",
                     "step": "Run CLS budget gate",
                     "module": "test_dashboard_cls_budget",
                     "guard": "themes boş"}),
        ("static", {"class": "ClsBudgetMathTest"}),
        ("static", {"class": "ClsArtifactContractTest"}),
    ],
    # Capture: REQUIRE_LIVE=1 iken canlı katman atlanamaz.
    "test_preview_screenshot_gate.py": [
        ("ci-step", {"job": "a11y-gate",
                     "step": "Run capture gate",
                     "module": "test_preview_screenshot_gate.py",
                     "guard": "CAPTURE_GATE_REQUIRE_LIVE=1"}),
    ],
    # CWV: kayıt vardı, koşum yoktu (phantom) — a11y-gate adımı kaydı
    # gerçek kılar; bekçi skip=red.
    "test_surface_cwv_report.py": [
        ("ci-step", {"job": "a11y-gate",
                     "step": "Run CWV report",
                     "module": "test_surface_cwv_report",
                     "guard": "SKIP etti"}),
        ("static", {"class": "SurfaceCwvReportContractTest"}),
    ],
    # Battery canlıları: ağaçta WIP-kırmızı iken CI'a bağlanmaz; hüküm
    # batarya (venv Chromium) + statik sınıflar. CI verify'daki atlama
    # KAYITLIDIR (sessiz değil).
    "test_dashboard_next_battery_smoke.py": [
        ("battery", {}),
        ("static", {"class": "TrendWindowStaticContractTest"}),
        ("static", {"class": "ReactCacheStaticContractTest"}),
        ("static", {"class": "SoftNavigationStaticContractTest"}),
    ],
    # WebKit: advisory job (continue-on-error + adı); parite kanıtı
    # macOS'te toplanır, merge'i bloke etmez — bilinçli istisna.
    "test_dashboard_webkit_smoke.py": [
        ("advisory", {"evidence": "advisory",
                      "note": "webkit-smoke job'ı continue-on-error + "
                              "advisory adlıdır"}),
        ("static", {"class": "TestWebkitStaticContract"}),
    ],
    # Doc-üretim PNG'leri: teslim kapısı değil (dosya başlığı); statik
    # ikili (`--help`, varsayılan kılavuz) CI verify'da gerçekten koşar.
    # PNG üreten üç test venv ile elle koşulur.
    "docs/branch-protection-guide/test_render_screens.py": [
        ("static", {"class": "TestRenderScreens",
                    "methods": ["test_help_runs",
                                "test_default_guide_is_script_dir"]}),
        ("advisory", {"evidence": "teslim kapısı",
                      "note": "PNG üretimi doc-üretim aracıdır; CI'da "
                              "statik ikili koşar"}),
    ],
}

def _workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


class TestBrowserSkipSweep(unittest.TestCase):
    def test_sweep_matches_registry_exactly(self):
        """Süpürme ≠ kayıt → kırmızı (yeni kapılı dosya sessizce yeşil kalamaz)."""
        found = set(_sweep())
        registered = set(REGISTRY)
        missing = sorted(found - registered)
        extra = sorted(registered - found)
        self.assertEqual(missing, [],
                         "kayitsiz tarayici-kapili dosya (hüküm gerekli): %s" % missing)
        self.assertEqual(extra, [],
                         "kayıt artık kapı taşımıyor (kayıt silinmeli): %s" % extra)

    def test_gate_patterns_do_not_match_mere_mentions(self):
        """Süpürme yalnız GERÇEK kapıyı yakalar (negatif kontrol)."""
        for name in ("test_functional_browser_ci.py",
                     "test_ci_env_independence.py",
                     "test_coverage_report.py"):
            src = (HERE / name).read_text(encoding="utf-8")
            self.assertFalse(_has_gate(src),
                             "%s kapı sanıldı (yalnız bahis olmalı)" % name)

    def test_auditor_itself_has_no_playwright_import(self):
        """Denetim kendini süpürmeden muaf tutar; muafiyetin bedeli: bu
        dosyada GERÇEL playwright import'u yasaktır (kalıplar yalnız
        literal). Muafiyet + import bir arada olursa süpürme körleşir."""
        src = (HERE / _SELF).read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"(?m)^\s*(from playwright[.\s]|import playwright\b)",
                      src),
            "denetim dosyası playwright import ediyor — muafiyet geçersiz")

class TestBrowserSkipEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = _workflow_text()
        cls.manifest = _manifest_members()

    def _check_ci_step(self, filename, proof):
        # assertIn devasa samanlıkta tüm workflow'u kusar; üyelik + kısa
        # ileti (okunabilir kırmızı). Kanıt zinciri: job → adım → modül →
        # bekçi. Roster'lı adımlarda bekçi koşturucu script'tedir (.sh),
        # modül üyeliği roster dosyasındadır (etiket değil, icra kanıtı).
        wf = self.workflow
        self.assertTrue(proof["job"] in wf,
                        "%s: job yok: %s" % (filename, proof["job"]))
        self.assertTrue(proof["step"] in wf,
                        "%s: adım yok: %s" % (filename, proof["step"]))
        self.assertTrue(proof["module"] in wf,
                        "%s: adım modülü koşturmuyor: %s"
                        % (filename, proof["module"]))
        if "roster" in proof:
            roster = (HERE / proof["roster"]).read_text(encoding="utf-8")
            entries = [ln.strip() for ln in roster.splitlines()
                       if ln.strip() and not ln.strip().startswith("#")]
            self.assertIn(filename, entries,
                          "%s roster'da değil: %s"
                          % (filename, proof["roster"]))
            runner = (HERE / proof["runner"]).read_text(encoding="utf-8")
            self.assertTrue(proof["guard"] in runner,
                            "%s: koşturucu bekçisiz: %s (%s)"
                            % (filename, proof["guard"], proof["runner"]))
        else:
            self.assertTrue(proof["guard"] in wf,
                            "%s: bekçi yok (skip reddi kanıtlanamadı): %s"
                            % (filename, proof["guard"]))

    def _check_static(self, filename, proof):
        if filename.startswith("docs/"):
            path = ROOT / filename
        else:
            path = HERE / filename
        src = path.read_text(encoding="utf-8")
        self.assertTrue(("class %s" % proof["class"]) in src,
                        "%s: statik sınıf yok: %s" % (filename, proof["class"]))
        for method in proof.get("methods", ()):
            self.assertTrue(("def %s" % method) in src,
                            "%s: statik metot yok: %s" % (filename, method))
        if not filename.startswith("docs/"):
            self.assertIn(filename, self.manifest,
                          "%s bataryada değil — statik katman koşamaz"
                          % filename)

    def _check_battery(self, filename, _proof):
        self.assertIn(filename, self.manifest,
                      "%s bataryada değil — battery hükmü boş" % filename)

    def _check_advisory(self, filename, proof):
        if filename.startswith("docs/"):
            haystack = (ROOT / filename).read_text(encoding="utf-8")
        else:
            haystack = self.workflow
            if filename == "test_dashboard_webkit_smoke.py":
                self.assertTrue("continue-on-error" in self.workflow,
                                "webkit advisory kanıtı yok")
        self.assertTrue(proof["evidence"] in haystack,
                        "%s: advisory kanıtı yok: %r" % (filename, proof))

    def test_every_ruling_has_its_evidence(self):
        bad = []
        for filename, rulings in sorted(REGISTRY.items()):
            for kind, proof in rulings:
                try:
                    {"ci-step": self._check_ci_step,
                     "static": self._check_static,
                     "battery": self._check_battery,
                     "advisory": self._check_advisory}[kind](filename, proof)
                except AssertionError as exc:
                    bad.append("%s [%s]: %s" % (filename, kind, exc))
        self.assertEqual(bad, [], "kanıtsız hüküm:\n" + "\n".join(bad))

    def test_registry_uses_only_known_ruling_kinds(self):
        for filename, rulings in REGISTRY.items():
            for kind, _proof in rulings:
                self.assertIn(kind, ("ci-step", "static", "battery",
                                     "advisory"),
                              "%s: bilinmeyen hüküm: %s" % (filename, kind))

if __name__ == "__main__":
    unittest.main()