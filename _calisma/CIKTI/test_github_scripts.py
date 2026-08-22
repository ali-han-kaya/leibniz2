#!/usr/bin/env python3
"""test_github_scripts.py — github-script JS drift kapısı (fail-closed).

github-script adımları `_calisma/CIKTI/github_scripts/*.js` dosyalarını
`script:` input'uyla OKUYUP eval eder. NOT: actions/github-script@v8
`scriptPath` input'unu DESTEKLEMEZ (yalnızca `script`) — CI'da
"Input required and not supplied: script" ile patlar. Bu yüzden workflow
selftest harness'ıyla (github_scripts_selftest.js) AYNI deseni kullanır:
`readFileSync(...)` + `(async () => { … })()` sarmalı. Bu test drift'in GERİ
dönmesini engeller:

  1) verify.yml'de `scriptPath:` YOK olmalı (github-script@v8'de patlar).
  2) Her github-script adımı `script: |` ile github_scripts/ altında BİR
     .js dosyasını readFileSync edip eval etmeli; referanslı dosya VAR
     olmalı.
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
    """github-script adımları TEK KAYNAK .js dosyalarını script: ile eval etmeli.

    github-script@v8 scriptPath DESTEKLEMEZ — workflow, selftest harness'ıyla
    aynı deseni kullanır: her adım `script: |` ile bir .js dosyasını
    readFileSync edip (async () => { … })() sarmalında eval eder. Bu test,
    (a) scriptPath geri dönüşünü, (b) dosyasız/eksik inline JS'yi ve
    (c) referanslı dosyanın yokluğunu fail-closed yakalar.
    """
    _JS_RE = re.compile(r"readFileSync\('([^']+github_scripts/[^']+\.js)'")

    def setUp(self):
        self.text = WF.read_text(encoding="utf-8")

    def test_no_script_path_blocks(self):
        # github-script@v8 scriptPath input'unu desteklemez — kullanımı CI'da
        # "Input required and not supplied: script" ile patlar (fail-closed).
        # (Yorumlardaki 'scriptPath' sözü değil, gerçek YAML anahtarı yasak.)
        self.assertNotIn("scriptPath:", self.text,
                         "scriptPath github-script@v8'de yok — 'script' input'uyla "
                         "eval edilmeli (selftest harness deseni)")

    def test_every_github_script_step_reads_at_least_one_js_file(self):
        # Her adım BİR veya DAHA FAZLA .js dosyasını readFileSync edip eval
        # etmeli (inline JS yasak — TEK KAYNAK github_scripts/ dosyaları).
        # Not: manifest + config-diff yorumları TEK adımda birleşiktir (yorum
        # listesi bir kez çekilir); o adım 2 dosya okur — kural "en az 1".
        uses = self.text.count("uses: actions/github-script")
        refs = self._JS_RE.findall(self.text)
        self.assertGreater(uses, 0, "github-script adımı bekleniyor")
        self.assertGreaterEqual(
            len(refs), uses,
            f"{uses} github-script adımı ama {len(refs)} .js referansı "
            "(her adım en az bir dosyayı readFileSync edip eval etmeli)")

    def test_manifest_and_config_diff_share_one_step(self):
        # Birleşik adım iki script'i AYNI github-script kapsamında koşar —
        # yorum listesi bir kez çekilir (API çağrısı 2→1). Bunu sürdürmek
        # için: (a) iki readFileSync arasında başka bir github-script adımı
        # olmamalı, (b) paylaşılan liste çekimi (EXISTING_COMMENTS + tek
        # listComments) manifest readFileSync'inden ÖNCE gelmeli (adım başı).
        mpos = self.text.index(
            "readFileSync('_calisma/CIKTI/github_scripts/manifest_comment.js'")
        cpos = self.text.index(
            "readFileSync('_calisma/CIKTI/github_scripts/config_diff_comment.js'")
        between = self.text[min(mpos, cpos):max(mpos, cpos)]
        self.assertNotIn(
            "uses: actions/github-script", between,
            "manifest_comment.js + config_diff_comment.js AYNI github-script "
            "adımında olmalı (paylaşılan EXISTING_COMMENTS — tek listComments)")
        prefix = self.text[:mpos]
        self.assertIn("EXISTING_COMMENTS", prefix,
                      "paylaşılan yorum listesi adımın başında çekilmeli")
        self.assertIn("listComments", prefix,
                      "yorum listesi BİR KEZ çekilmeli (script içi fallback yok)")

    def test_every_referenced_js_exists(self):
        for rel in self._JS_RE.findall(self.text):
            p = (ROOT / rel).resolve()
            self.assertTrue(p.is_file(), f"js dosyası yok: {rel}")
            self.assertTrue(
                p.is_relative_to(SCRIPTS_DIR),
                f"js github_scripts/ altında olmalı: {rel}")

    def test_every_script_block_has_async_eval_wrap(self):
        # Selftest harness deseni: readFileSync + (async () => { … })() eval.
        # Veya: require() + await eval (standart .js dosyası yönlendirmesi).
        blocks = self.text.split("uses: actions/github-script")
        for i, blk in enumerate(blocks[1:], 1):
            has_readfile = "readFileSync" in blk
            has_require = "require(" in blk and "await eval" in blk
            self.assertTrue(
                has_readfile or has_require,
                f"adım {i}: readFileSync veya require+eval yok")


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
