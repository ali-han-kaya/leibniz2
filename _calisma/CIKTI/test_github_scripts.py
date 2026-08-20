#!/usr/bin/env python3
"""test_github_scripts.py — github-script JS drift kapısı (fail-closed).

github-script adımlarının inline `script:` blokları `_calisma/CIKTI/
github_scripts/*.js` dosyalarına çıkarıldı (workflow yalnızca `scriptPath`
referanslar). Bu test, drift'in GERİ dönmesini engeller:

  1) verify.yml'de github-script adımlarında inline `script: |` bloğu
     YOK olmalı (inline JS yeniden eklenirse test FAIL).
  2) Her github-script adımının BİR scriptPath'i olmalı ve dosya VAR olmalı.
  3) Her referanslı .js dosyası sözdizimsel geçerli olmalı (node --check;
     top-level await github-script çalışma zamanı özelliği olduğundan dosya
     async IIFE'ye sarılarak denetlenir). node yoksa dürüstçe SKIP.

stdlib unittest + subprocess — ek bağımlılık yok.
"""
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
WF = ROOT / ".github" / "workflows" / "verify.yml"
SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent / "github_scripts"


class TestNoInlineGithubScript(unittest.TestCase):
    def setUp(self):
        self.text = WF.read_text(encoding="utf-8")

    def test_no_inline_script_blocks(self):
        # `script: |` github-script adımlarında kalmamalı (drift = geri dönüş).
        self.assertNotIn("script: |", self.text,
                         "verify.yml'de inline github-script bloğu var — "
                         "scriptPath kullanılmalı")

    def test_every_github_script_step_has_script_path(self):
        uses = self.text.count("uses: actions/github-script")
        paths = re.findall(r"scriptPath:\s*(.+)$", self.text, re.M)
        self.assertGreater(uses, 0, "github-script adımı bekleniyor")
        self.assertEqual(
            uses, len(paths),
            f"{uses} github-script adımı ama {len(paths)} scriptPath "
            "(her adımın birebir bir scriptPath'i olmalı)")

    def test_every_script_path_exists(self):
        paths = re.findall(r"scriptPath:\s*(.+)$", self.text, re.M)
        for rel in paths:
            p = (ROOT / rel.strip()).resolve()
            self.assertTrue(p.is_file(), f"scriptPath dosyası yok: {rel}")

    def test_script_paths_are_under_github_scripts_dir(self):
        paths = re.findall(r"scriptPath:\s*(.+)$", self.text, re.M)
        for rel in paths:
            self.assertIn("github_scripts/", rel,
                          f"scriptPath github_scripts/ altında olmalı: {rel}")


class TestJsSyntax(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")

    @unittest.skipIf(shutil.which("node") is None, "node kurulu değil")
    def test_all_scripts_syntax_valid(self):
        for js in sorted(SCRIPTS_DIR.glob("*.js")):
            body = js.read_text(encoding="utf-8")
            # github-script top-level await kullanır → async IIFE'ye sar.
            wrapped = f"(async () => {{\n{body}\n}})();\n"
            with tempfile.NamedTemporaryFile("w", suffix=".js",
                                             delete=False) as f:
                f.write(wrapped)
                tmp = f.name
            try:
                r = subprocess.run(["node", "--check", tmp],
                                   capture_output=True, text=True)
            finally:
                pathlib.Path(tmp).unlink(missing_ok=True)
            self.assertEqual(r.returncode, 0,
                             f"sözdizimi hatası: {js.name}\n{r.stderr}")


if __name__ == "__main__":
    unittest.main()
