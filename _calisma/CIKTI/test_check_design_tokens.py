#!/usr/bin/env python3
"""test_check_design_tokens.py — design-system/scripts/check_tokens.py regression gate.

Contracts:
- preview.html imports design-system/tokens.css (no stray inline :root drift)
- tokens.css :root + light block mirror tokens.json (tints included)
- dashboard-next/app/globals.css: no token-name shadow, no literal copy, no
  hard-coded colour literal — in ANY block (second :root, .dark, @media …)
- check_tokens.py is ~0.05s and stdlib-only
"""
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
GLOBALS = REPO / "apps" / "dashboard-next" / "app" / "globals.css"


def run_check_copy(tmp_script: pathlib.Path):
    return subprocess.run(
        [sys.executable, str(tmp_script)],
        capture_output=True, text=True, timeout=10)


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


if __name__ == "__main__":
    unittest.main()
