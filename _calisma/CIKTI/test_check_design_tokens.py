#!/usr/bin/env python3
"""test_check_design_tokens.py — design-system/scripts/check_tokens.py regression gate.

Contracts:
- preview.html imports design-system/tokens.css (no stray inline :root drift)
- tokens.css :root + light block mirror tokens.json (tints included)
- dashboard-next/app/globals.css: no token-name shadow, no literal copy, no
  hard-coded colour literal — in ANY block (second :root, .dark, @media …)
- check_tokens.py is ~0.05s and stdlib-only
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
