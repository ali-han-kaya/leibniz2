#!/usr/bin/env python3
"""test_check_design_tokens.py — design-system/scripts/check_tokens.py regression gate.

Contracts:
- preview.html imports design-system/tokens.css (no stray inline :root drift)
- tokens.css :root + light block mirror tokens.json (tints included)
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


def run_check_copy(tmp_script: pathlib.Path):
    return subprocess.run(
        [sys.executable, str(tmp_script)],
        capture_output=True, text=True, timeout=10)


def _tmp_repo() -> pathlib.Path:
    td = pathlib.Path(tempfile.mkdtemp())
    (td / "_calisma" / "CIKTI").mkdir(parents=True)
    (td / "design-system" / "scripts").mkdir(parents=True)
    shutil.copy(CSS, td / "design-system" / "tokens.css")
    shutil.copy(REPO / "design-system" / "tokens.json", td / "design-system" / "tokens.json")
    shutil.copy(SCRIPT, td / "design-system" / "scripts" / "check_tokens.py")
    shutil.copy(HTML, td / "_calisma" / "CIKTI" / "preview.html")
    return td


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


if __name__ == "__main__":
    unittest.main()
