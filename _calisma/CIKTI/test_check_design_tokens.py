#!/usr/bin/env python3
"""test_check_design_tokens.py — design-system/scripts/check_tokens.py regression gate.

Contracts:
- preview.html imports design-system/tokens.css (no stray inline :root drift)
- tokens.css :root + light block mirror tokens.json (tints included)
- dashboard-next/app/globals.css: no token-name shadow, no literal copy, no
  hard-coded colour literal — in ANY block (second :root, .dark, @media …)
- dashboard-next UYGULAMA KAYNAĞI (.tsx/.ts/.jsx/.js) ve globals.css DIŞINDAKİ
  her .css: koda gömülü hex/rgb/hsl literali, arbitrary renk utility'si ya da
  Tailwind varsayılan paleti olamaz (contract 8f/8g) — aksi halde tema
  koyu/açık/stripe varyantlarında donar. Ölçü arbitrary değerleri, var()
  türetmeleri ve gölge içi rgba meşrudur (karşı-testlerle pinlenir).
- check_tokens.py is OFFLINE and stdlib-only; gezinme node_modules/.next
  ağaçlarını budar, yani sonuç kurulu paketlerden bağımsızdır (ölçüldü
  2026-09-28: budama öncesi 24.917 dosya → ~1,4s; sonrası ~0,15s).
"""
import importlib.util
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
HTML = REPO / "_calisma" / "CIKTI" / "preview.html"
CSS = REPO / "design-system" / "tokens.css"
SCRIPT = REPO / "design-system" / "scripts" / "check_tokens.py"
STRIPE_GEN_NAME = "generate_stripe_theme.py"
STRIPE_THEME = REPO / "design-system" / "stripe" / "theme.css"
PREVIEW_HTML = REPO / "_calisma" / "CIKTI" / "preview.html"
PREVIEW_JS = REPO / "_calisma" / "CIKTI" / "preview.js"
PREVIEW_SERVER = REPO / "_calisma" / "CIKTI" / "preview_server.py"
SYNC_MIRROR = REPO / "_calisma" / "CIKTI" / "sync_verify_mirror.sh"
MIRROR_COVERAGE = REPO / "_calisma" / "CIKTI" / "check_mirror_coverage.py"
BUILD_LANDING = REPO / "_calisma" / "landing" / "build_landing.py"
LANDING_SRC = REPO / "_calisma" / "landing" / "landing_src.html"
GLOBALS = REPO / "apps" / "dashboard-next" / "app" / "globals.css"


def run_check_copy(tmp_script: pathlib.Path):
    return subprocess.run(
        [sys.executable, str(tmp_script)],
        capture_output=True, text=True, timeout=10)


def _load_gate(script_path: pathlib.Path):
    """check_tokens.py'yi yol üzerinden modül olarak yükle (fonksiyon testi)."""
    spec = importlib.util.spec_from_file_location("check_tokens_fixture",
                                                  script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tmp_repo() -> pathlib.Path:
    td = pathlib.Path(tempfile.mkdtemp())
    (td / "_calisma" / "CIKTI").mkdir(parents=True)
    (td / "design-system" / "scripts").mkdir(parents=True)
    (td / "apps" / "dashboard-next" / "app").mkdir(parents=True)
    shutil.copy(CSS, td / "design-system" / "tokens.css")
    shutil.copy(REPO / "design-system" / "tokens.json", td / "design-system" / "tokens.json")
    # the Tailwind bridge is part of the gate's contract-6 (verbatim :root)
    shutil.copy(REPO / "design-system" / "tailwind.css", td / "design-system" / "tailwind.css")
    shutil.copy(SCRIPT, td / "design-system" / "scripts" / "check_tokens.py")
    shutil.copy(HTML, td / "_calisma" / "CIKTI" / "preview.html")
    # contract 5/7 live on dashboard-next — without this file the gate skips
    # them (next_ok False) and every drift test below would pass vacuously
    shutil.copy(GLOBALS, td / "apps" / "dashboard-next" / "app" / "globals.css")
    # contract 9: stripe tema varyantı (ayna + GENERATED çıktı + jeneratör)
    stripe = td / "design-system" / "stripe"
    (stripe / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "design-system" / "stripe" / "tokens.css",
                stripe / "tokens.css")
    shutil.copy(REPO / "design-system" / "stripe" / "theme.css",
                stripe / "theme.css")
    shutil.copy(REPO / "design-system" / "stripe" / "scripts" / STRIPE_GEN_NAME,
                stripe / "scripts" / STRIPE_GEN_NAME)
    # contract 9 ayrıca varyantı tüketen yüzeyleri denetler (preview + landing
    # kaynağı); fixture'da yoksa kapı "kablolama denetlenemedi" der.
    landing = td / "_calisma" / "landing"
    landing.mkdir(parents=True)
    shutil.copy(LANDING_SRC, landing / "landing_src.html")
    return td


def _run_with_globals(append: str, replace: str = None):
    """Run the gate against a temp repo whose globals.css is mutated."""
    td = _tmp_repo()
    try:
        tmp_script = td / "design-system" / "scripts" / "check_tokens.py"
        target = td / "apps" / "dashboard-next" / "app" / "globals.css"
        text = GLOBALS.read_text(encoding="utf-8")
        if replace is not None:
            text = text.replace(replace, append, 1)
        else:
            text = text + append
        target.write_text(text, encoding="utf-8")
        return run_check_copy(tmp_script)
    finally:
        shutil.rmtree(td, ignore_errors=True)


class TestDesignTokensGate(unittest.TestCase):
    def test_real_repo_pass(self):
        r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK", r.stdout)

    def test_inline_root_drift_fails(self):
        text = HTML.read_text(encoding="utf-8")
        td = _tmp_repo()
        try:
            tmp_script = td / "design-system" / "scripts" / "check_tokens.py"
            drift_html = text.replace("<style>", "<style>\n  :root { --bg: #000; }", 1)
            (td / "_calisma" / "CIKTI" / "preview.html").write_text(drift_html, encoding="utf-8")
            r = run_check_copy(tmp_script)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("inline :root", r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_missing_import_fails(self):
        text = HTML.read_text(encoding="utf-8")
        td = _tmp_repo()
        try:
            tmp_script = td / "design-system" / "scripts" / "check_tokens.py"
            no_import = text.replace("design-system/tokens.css", "missing.css")
            (td / "_calisma" / "CIKTI" / "preview.html").write_text(no_import, encoding="utf-8")
            r = run_check_copy(tmp_script)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("does not import", r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_tint_drift_fails(self):
        css_text = CSS.read_text(encoding="utf-8")
        td = _tmp_repo()
        try:
            tmp_script = td / "design-system" / "scripts" / "check_tokens.py"
            broken = css_text.replace("rgba(63, 185, 80, .15)", "rgba(0,0,0,.01)")
            (td / "design-system" / "tokens.css").write_text(broken, encoding="utf-8")
            r = run_check_copy(tmp_script)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("tint.ok-bg", r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_light_block_must_exist(self):
        css_text = CSS.read_text(encoding="utf-8")
        td = _tmp_repo()
        try:
            tmp_script = td / "design-system" / "scripts" / "check_tokens.py"
            no_light = re.sub(r':root\[data-theme="light"\]\s*\{[^}]+\}', '', css_text)
            (td / "design-system" / "tokens.css").write_text(no_light, encoding="utf-8")
            r = run_check_copy(tmp_script)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("light", (r.stdout + r.stderr).lower())
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_no_inline_root_shadows_import(self):
        text = HTML.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"<style>.*?:root\s*\{[^}]*--bg", msg="inline :root --bg shadows import")
        self.assertIn("design-system/tokens.css", text)

    # ── contract 7: dashboard-next copy drift ──────────────────────────────

    def test_dashboard_next_globals_passes(self):
        """The migrated globals.css is the shape the gate enforces."""
        r = _run_with_globals("")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("copy-drift OK", r.stdout)

    def test_second_root_shadow_fails(self):
        """A SECOND :root block — invisible to the old `:root {...}` regex."""
        r = _run_with_globals("\n:root { --bg: #000; }\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--bg", r.stdout + r.stderr)

    def test_dark_block_shadow_fails(self):
        """`.dark` re-declaring a token name is shadowing too — this is the
        block that used to sit in globals.css unflagged (and dead)."""
        r = _run_with_globals("\n.dark { --border: #fff; }\n")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("re-defines token", out)
        self.assertIn("--border", out)
        self.assertIn(".dark", out)

    def test_literal_value_copy_fails(self):
        """A written-out value that IS a tokens.css value = two sources."""
        r = _run_with_globals("\n:root { --card: #161b22; }\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("copies the value", r.stdout + r.stderr)

    def test_colour_literal_fails(self):
        """A colour that is NOT in tokens.css is just as much a bypass."""
        r = _run_with_globals("\n:root { --sidebar: oklch(1 0 0); }\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("colour literal", r.stdout + r.stderr)

    def test_comment_mentioning_root_does_not_trip(self):
        """Prose about `:root { --bg }` must neither trip nor mask the gate."""
        r = _run_with_globals(
            "\n/* see :root { --bg: #000; } below — historical, not a token */\n"
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_theme_block_is_exempt(self):
        """`@theme` holds utility MAPPINGS, not document custom properties:
        `--font-mono: var(--font-mono)` is the bridge, not a shadow."""
        r = _run_with_globals(
            "\n@theme inline { --font-mono: var(--font-mono); --tw-x: #123456; }\n"
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # ── contract 8: preset bağımsızlığı + referans kapanışı ────────────────

    def test_preset_import_fails(self):
        """shadcn preset sheet'i ikinci tema kaynağıdır — import edilemez."""
        r = _run_with_globals('\n@import "shadcn/tailwind.css";\n')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("preset sheet", r.stdout + r.stderr)

    def test_preset_import_is_gone_from_real_globals(self):
        text = GLOBALS.read_text(encoding="utf-8")
        self.assertNotRegex(
            text, r'@import\s+["\']shadcn/',
            msg="shadcn preset CSS importu geri gelmemeli (contract 8)")

    def test_written_out_slot_value_fails(self):
        """Yazıyla verilmiş değer = kopya adayı; köprüye referans şart."""
        # 9px tokens.css'te YOK (8px olsaydı contract 7 kopya olarak yakalardı).
        r = _run_with_globals("\n:root { --sidebar: 9px; }\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("yazıyla verilmiş değer", r.stdout + r.stderr)

    def test_dangling_var_reference_fails(self):
        """Çürük referans sessiz stil kaybıdır (ne token ne yuva)."""
        r = _run_with_globals("\n:root { --sidebar: var(--yok-boyle-token); }\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("çürük referans", r.stdout + r.stderr)

    def test_slot_without_theme_alias_fails(self):
        """Yeni yuva @theme'de --color-<yuva> alias'ı olmadan eklenemez."""
        r = _run_with_globals("\n:root { --brand-x: var(--accent); }\n")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--brand-x", out)
        self.assertIn("--color-brand-x", out)

    def test_preset_only_utility_in_source_fails(self):
        """Preset silindi: onun utility'sini kullanmak sessiz stilsizlik."""
        td = _tmp_repo()
        try:
            tmp_script = td / "design-system" / "scripts" / "check_tokens.py"
            ui = td / "apps" / "dashboard-next" / "components" / "ui"
            ui.mkdir(parents=True)
            (ui / "yeni.tsx").write_text(
                'export const X = () => <div className="no-scrollbar" />;\n',
                encoding="utf-8")
            r = run_check_copy(tmp_script)
            self.assertNotEqual(r.returncode, 0)
            out = r.stdout + r.stderr
            self.assertIn("preset-only", out)
            self.assertIn("no-scrollbar", out)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    # ── contract 9: stripe HDS tema varyantı ───────────────────────────

    def test_stripe_variant_passes_on_real_repo(self):
        r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True,
                           text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stripe HDS varyantı", r.stdout)
        self.assertIn("32 yuva", r.stdout)

    def test_stripe_variant_hand_edit_fails(self):
        td = _tmp_repo()
        try:
            tmp_script = td / "design-system" / "scripts" / "check_tokens.py"
            theme = td / "design-system" / "stripe" / "theme.css"
            theme.write_text(
                theme.read_text(encoding="utf-8").replace(
                    "--accent: var(--hds-color-action-bg-solid);",
                    "--accent: #533afd;"),
                encoding="utf-8")
            r = run_check_copy(tmp_script)
            self.assertNotEqual(r.returncode, 0)
            out = r.stdout + r.stderr
            self.assertIn("jeneratörle birebir değil", out)
            self.assertIn("--accent renk literal", out)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_stripe_variant_scope_leak_fails(self):
        td = _tmp_repo()
        try:
            tmp_script = td / "design-system" / "scripts" / "check_tokens.py"
            theme = td / "design-system" / "stripe" / "theme.css"
            theme.write_text(
                theme.read_text(encoding="utf-8")
                + '\n:root { --sizinti: var(--hds-color-core-brand-600); }\n',
                encoding="utf-8")
            r = run_check_copy(tmp_script)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("beklenmeyen blok", r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_stripe_variant_dangling_hds_reference_fails(self):
        """Çürük HDS referansı: ne dosyada ne aynada tanımlı."""
        td = _tmp_repo()
        try:
            module = _load_gate(td / "design-system" / "scripts"
                                / "check_tokens.py")
            theme = td / "design-system" / "stripe" / "theme.css"
            theme.write_text(
                theme.read_text(encoding="utf-8").replace(
                    "  --accent: var(--hds-color-action-bg-solid);",
                    "  --accent: var(--hds-color-action-bg-solid);\n"
                    "  --tint-yeni: var(--hds-color-yok-boyle-token);"),
                encoding="utf-8")
            findings = module._stripe_variant_findings()
            self.assertTrue(any("çürük HDS referansı" in f for f in findings),
                            findings)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_stripe_variant_mirror_value_drift_fails(self):
        """theme.css'teki HDS ön-koşulu aynadaki değerle birebir olmalı."""
        td = _tmp_repo()
        try:
            module = _load_gate(td / "design-system" / "scripts"
                                / "check_tokens.py")
            theme = td / "design-system" / "stripe" / "theme.css"
            theme.write_text(
                theme.read_text(encoding="utf-8").replace(
                    "--hds-color-core-brand-600: #533afd;",
                    "--hds-color-core-brand-600: #533afe;"),
                encoding="utf-8")
            findings = module._stripe_variant_findings()
            self.assertTrue(any("aynadan farklı" in f for f in findings),
                            findings)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_stripe_variant_missing_slot_fails(self):
        """REQUIRED_SLOTS eksik bağlanırsa jeneratör render'ı reddeder."""
        td = _tmp_repo()
        try:
            module = _load_gate(td / "design-system" / "scripts"
                                / "check_tokens.py")
            gen = module._load_stripe_generator()
            gen.SLOT_MAP.pop("--budget")
            with self.assertRaises(SystemExit):
                gen.render()
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_stripe_surface_override_with_literal_fails(self):
        """Yüzeydeki stripe override'ı literal renkle HDS paletini kesemez."""
        td = _tmp_repo()
        try:
            module = _load_gate(td / "design-system" / "scripts"
                                / "check_tokens.py")
            surface = td / "_calisma" / "CIKTI" / "preview.html"
            surface.write_text(
                surface.read_text(encoding="utf-8").replace(
                    ':root[data-theme="stripe"] .z3-slide { background:var(--surface);',
                    ':root[data-theme="stripe"] .z3-slide { background:#fffdf8;'),
                encoding="utf-8")
            findings = module._stripe_variant_findings()
            self.assertTrue(any("renk literal" in f for f in findings),
                            findings)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    # ── contract 9 wiring: yüzey + servis + mirror zinciri ──────────────

    def test_stripe_variant_is_wired_into_preview_and_landing(self):
        preview_html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn('/design-system/stripe-theme.css', preview_html,
                      "preview.html vrariant stylesheet'ini yüklemiyor")

        preview_js = PREVIEW_JS.read_text(encoding="utf-8")
        self.assertIn('const THEMES = ["dark", "light", "stripe"]', preview_js)
        self.assertIn("THEMES.includes(requested)", preview_js)

        server = PREVIEW_SERVER.read_text(encoding="utf-8")
        self.assertIn('return "design_tokens_stripe"', server)
        self.assertIn("def serve_stripe_theme(self):", server)
        self.assertIn('"design-system-stripe-theme.css"', server)

        mirror = SYNC_MIRROR.read_text(encoding="utf-8")
        self.assertIn(
            '"design-system/stripe/theme.css|design-system-stripe-theme.css"',
            mirror, "mirror eşlemesi yok — sunucu rotası 404'e düşer")

        coverage = MIRROR_COVERAGE.read_text(encoding="utf-8")
        self.assertIn('STRIPE_THEME_REL = "design-system/stripe/theme.css"',
                      coverage)
        self.assertIn("expected.add(STRIPE_THEME_REL)", coverage)

        landing = BUILD_LANDING.read_text(encoding="utf-8")
        self.assertIn('STRIPE_THEME = ROOT / "design-system" / "stripe" '
                      '/ "theme.css"', landing)
        self.assertIn('THEMES = ("dark", "light", "stripe")', landing)

    # ── contract 8(f): gömülü renk sızması (köprü utility'i varken) ──

    def _source_repo(self, rel: str, content: str):
        """Geçici repoya verilen kaynağı yaz → (sonuç, out) döner."""
        td = _tmp_repo()
        try:
            tmp_script = td / "design-system" / "scripts" / "check_tokens.py"
            target = td / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            r = run_check_copy(tmp_script)
            return r, r.stdout + r.stderr
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_arbitrary_hex_utility_fails(self):
        """`bg-[#0e1116]` köprü token'ını baypas eder → kapı kırmızı."""
        r, out = self._source_repo(
            "apps/dashboard-next/components/kart.tsx",
            'export const X = () => <div className="bg-[#0e1116] text-fg" />;\n')
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("arbitrary renk utility", out)
        self.assertIn("bg-bg", out, "bulgu köprü utility'sini önermeli")
        self.assertIn("kart.tsx:1", out, "bulgu dosya:satır bildirmeli")

    def test_inline_style_hex_fails(self):
        """JSX inline stilinde gömülü hex de aynı sınıftır → kırmızı."""
        r, out = self._source_repo(
            "apps/dashboard-next/app/kart.tsx",
            'export const X = () => <div style={{ color: "#e6edf3" }} />;\n')
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("koda gömülü renk literali", out)

    def test_raw_hex_in_globals_css_fails(self):
        """globals.css'e yazıyla verilmiş ton → kırmızı (yuva var(--…) olmalı)."""
        td = _tmp_repo()
        try:
            tmp_script = td / "design-system" / "scripts" / "check_tokens.py"
            target = td / "apps" / "dashboard-next" / "app" / "globals.css"
            target.write_text(
                GLOBALS.read_text(encoding="utf-8")
                + "\n.kart { background: #161b22; }\n", encoding="utf-8")
            r = run_check_copy(tmp_script)
            out = r.stdout + r.stderr
            self.assertNotEqual(r.returncode, 0, out)
            self.assertIn("globals.css", out)
            self.assertIn("renk literali", out)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_source_walk_prunes_installed_trees(self):
        """Kaynak gezinmesi node_modules/.next içine GİRMEZ.

        İki iddia birlikte: (1) kurulu bağımlılıkların içindeki renk
        literalleri kapıyı kirletmez (aksi halde her `npm ci` sonrası kapı
        kırmızı olurdu — node_modules'te hex kaçınılmaz), (2) gezinme o
        ağaçlara girmediği için kapının süresi kurulu paket sayısından
        bağımsızdır.
        """
        gate = _load_gate(SCRIPT)
        walked = list(gate._app_source_files({".tsx", ".ts", ".js", ".jsx"}))
        self.assertTrue(walked, "gezinme boş — kapı hiçbir kaynağı görmüyor")
        bad = [str(p) for p in walked
               if {"node_modules", ".next"} & set(p.parts)]
        self.assertEqual(bad, [], "gezinme kurulu ağaca giriyor: %s" % bad[:3])

    def test_hex_in_other_css_file_fails(self):
        """globals.css DIŞINDAKİ bir .css de aynı kapıdan geçmeli (8g).

        Ölçüldü (2026-09-28): bu dal olmadan panoya YENİ bir .css dosyası
        açıp içine hex yazmak kapıyı YEŞİL bırakıyordu — yani kural teknik
        olarak vardı ama yeni bir dosyayla sessizce atlatılabiliyordu.
        """
        r, out = self._source_repo(
            "apps/dashboard-next/components/kart.css",
            ".kart { background: #ff0000; }\n")
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("kart.css:1", out, "bulgu dosya:satır bildirmeli")
        self.assertIn("renk literali", out)

    def test_other_css_var_values_and_theme_block_do_not_trip(self):
        """Karşı-test: yeni .css aşırı-geniş cezalandırılmamalı (8g).

        `@theme` bloğu bir utility EŞLEMESİdir (belge custom property'si
        değil; globals.css dalındaki muafiyetin aynısı) ve `var()` tabanlı
        değerler zaten token'a bağlıdır — kırmızı olmamalı.
        """
        r, out = self._source_repo(
            "apps/dashboard-next/components/kart.css",
            "@theme { --color-brand: #ff0000; }\n"
            ".kart { background: var(--surface-raised); }\n"
            ".kart:hover { border-color: var(--border); }\n")
        self.assertEqual(r.returncode, 0, out)

    def test_app_source_hex_literal_fails(self):
        """Uygulama kaynağında çıplak hex (inline stil) kırmızı olmalı (8f).

        `bg-[#…]` biçimi ayrı bir dala düşer; buradaki iddia çıplak literali
        pinler (üretimde `style={{ color: "#e6edf3" }}` gibi görünür).
        """
        r, out = self._source_repo(
            "apps/dashboard-next/components/kart.ts",
            'export const S = { color: "#e6edf3" };\n')
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("kart.ts:1", out)
        self.assertIn("renk literali", out)

    def test_tailwind_palette_colour_fails(self):
        """`bg-slate-900` de köprü dışı renk kaynağıdır → kırmızı.

        Arbitrary değer DEĞİL ama aynı hata sınıfı: jeneratörden kopuk sabit
        ton, koyu/açık/stripe varyantında donar.
        """
        r, out = self._source_repo(
            "apps/dashboard-next/components/kart.tsx",
            'export const X = () => <div className="bg-slate-900 text-white" />;\n')
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("varsayılan palet rengi", out)
        self.assertIn("slate-900", out, "bulgu sınıfı adıyla bildirmeli")
        self.assertIn("kart.tsx:1", out, "bulgu dosya:satır bildirmeli")
        self.assertIn("bg-bg", out, "bulgu köprü utility'sini önermeli")

    def test_palette_shade_required_so_metrics_do_not_trip(self):
        """Karşı-test: palet deseni renk ailesi + TON şartı arar.

        `border-0` / `ring-3` ölçü utility'si, `border-transparent` ve
        `text-current` (renk devralır) meşrudur — kırmızı olmamalı.
        """
        r, out = self._source_repo(
            "apps/dashboard-next/components/ui/kart.tsx",
            'export const X = () => (\n'
            '  <div className="border-0 border-b-0 ring-3 border-transparent"\n'
            '       data-x="text-current" data-y="grid grid-cols-2" />\n'
            ');\n')
        self.assertEqual(r.returncode, 0, out)

    def test_token_derived_and_metric_arbitrary_values_do_not_trip(self):
        """Karşı-test: kapı aşırı-geniş olmamalı.

        Ölçü/harf-aralığı arbitrary değerleri (`text-[11px]`,
        `tracking-[0.22em]`), `var()` tabanlı türetmeler
        (`bg-[color-mix(…var(--secondary)…)]`, `rounded-[min(var(--radius-md)…)]`)
        ve ölçü değeri içinde rgba taşıyan gölgeler meşrudur — kırmızı
        olmamalı. Aksi halde kapı kullanılamaz hale gelir (her satır ihlal).
        """
        r, out = self._source_repo(
            "apps/dashboard-next/components/ui/kart.tsx",
            'export const X = () => (\n'
            '  <div className="text-[11px] tracking-[0.22em] rounded-[min(var(--radius-md),10px)]"\n'
            '       data-bg="bg-[color-mix(in_oklch,var(--secondary),var(--foreground)_5%)]"\n'
            '       data-shadow="shadow-[0_8px_24px_rgba(0,0,0,.5)]"\n'
            '       data-entity="&#8212;" />\n'
            ');\n')
        self.assertEqual(r.returncode, 0, out)

    def test_colour_literal_gate_is_wired(self):
        """Kapı gerçekten kurulu mu: desen + mesaj + çağrı tek yerde."""
        src = SCRIPT.read_text(encoding="utf-8")
        for token in ("_ARBITRARY_COLOR_UTIL", "_RAW_COLOR_LITERAL",
                      "_NON_BRIDGE_PALETTE_UTIL",
                      "_color_literal_findings", "_blank_out_comments"):
            self.assertIn(token, src, "kapı bağlantısı eksik: %s" % token)
        self.assertIn("bg-[#", src + "bg-[#0e1116]",
                      "mesaj somut utility örneği vermeli")

    def test_preset_only_word_in_comment_does_not_trip(self):
        """Yorumdaki yüzey adı bloke etmez (yorum-sonrası metin taranır)."""
        td = _tmp_repo()
        try:
            tmp_script = td / "design-system" / "scripts" / "check_tokens.py"
            ui = td / "apps" / "dashboard-next" / "components" / "ui"
            ui.mkdir(parents=True)
            (ui / "yorum.tsx").write_text(
                '// shimmer efekti ileride\nexport const X = 1;\n',
                encoding="utf-8")
            r = run_check_copy(tmp_script)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
