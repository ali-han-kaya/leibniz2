"""`apps/trend-db` JS test koşucusunu kapı altına alır (rot koruması).

Neden bu dosya var: JS tarafındaki sözleşme testleri (`test/*.test.mjs`)
`.mjs` olduğu için `test_coverage_report.py` keşfine GİRMEZ ve
`check_unit_tests.list` manifesti Python dosyalarıyla sınırlıdır — yani
koşucu yalnız `npm test`'e bağlı kalırsa sessizce çürür (kimse koşmaz,
kırılır, fark edilmez). Bu sarmalayıcı onu mevcut fail-closed kapıya bağlar:
manifest bu dosyayı koşar, bu dosya `node test/run.mjs`'i koşar.

Kural: JS tarafında ikinci bir koşucu/ikinci bir kapı YOK. Kayıt, koşum,
raporlama `apps/trend-db/test/mini.mjs`in işidir; burada yalnız (a) yeşil
olmasını ve (b) yeni bir test modülü unutulmamasını denetleriz.
"""
import os
import pathlib
import re
import shutil
import subprocess
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1] if HERE.name == "CIKTI" else HERE.parents[2]
TREND_DB = REPO_ROOT / "apps" / "trend-db"
TEST_DIR = TREND_DB / "test"
RUNNER = TEST_DIR / "run.mjs"
# `mini.mjs` koşucu altyapısıdır, test modülü DEĞİLDİR: glob'a girmez.
MIN_KURULU_VAKA = 5


class TestTrendDbJsRunner(unittest.TestCase):
    """`npm test`'i (node test/run.mjs) pre-commit kapısına bağlar."""

    NODE = shutil.which("node")
    TSX = TREND_DB / "node_modules" / ".bin" / "tsx"

    def setUp(self):
        if self.NODE is None or not self.TSX.exists():
            self.skipTest("node/tsx yok (apps/trend-db/node_modules kurulmalı)")

    def _run_suite(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("DATABASE_URL", "DATABASE_URL_UNPOOLED")}
        return subprocess.run(
            [self.NODE, str(RUNNER)], cwd=str(TREND_DB), env=env,
            capture_output=True, text=True, timeout=300)

    def test_js_suite_is_green(self):
        res = self._run_suite()
        self.assertEqual(res.returncode, 0,
                         "JS sözleşme testleri kırık:\n%s\n%s"
                         % (res.stdout, res.stderr))
        m = re.search(r"^# (\d+)/(\d+) geçti", res.stdout, re.M)
        self.assertIsNotNone(m, "özet satırı yok (koşucu bozulmuş?):\n%s"
                             % res.stdout)
        passed, total = int(m.group(1)), int(m.group(2))
        self.assertEqual(passed, total, "kırmızı vaka var:\n%s" % res.stdout)
        # Boş/eksik koşu "hepsi geçti" görünür: eşik sözleşmenin alt sınırı.
        self.assertGreaterEqual(
            total, MIN_KURULU_VAKA,
            "JS sözleşme testleri beklenenden az: %d < %d (süreç bozulmuş?)"
            % (total, MIN_KURULU_VAKA))

    def test_every_test_module_is_registered_in_runner(self):
        """Yeni `*.test.mjs` eklenip run.mjs'e yazılmazsa → rot sessiz kalır."""
        self.assertTrue(RUNNER.exists(), "giriş noktası yok: %s" % RUNNER)
        src = RUNNER.read_text(encoding="utf-8")
        m = re.search(r"const MODULES = \[(.*?)\]", src, re.S)
        self.assertIsNotNone(m, "run.mjs MODULES listesi kayboldu:\n%s" % src)
        registered = set(re.findall(r"\"(\./[^\"]+)\"", m.group(1)))
        on_disk = {"./" + p.name for p in sorted(TEST_DIR.glob("*.test.mjs"))}
        self.assertTrue(on_disk, "test_*.test.mjs bulunamadı: %s" % TEST_DIR)
        self.assertEqual(
            on_disk - registered, set(),
            "run.mjs'e kayıt edilmemiş test modülü var (koşulmayacak):\n%s"
            % "\n".join(sorted(on_disk - registered)))

    def test_runner_cleans_up_its_temp_dir(self):
        """run.mjs geçici dizini koşu sonunda SİLMEZSE /tmp şişer (sessiz rot)."""
        self.assertIn("rmSync", RUNNER.read_text(encoding="utf-8"),
                      "geçici dizin temizliği kayboldu")


if __name__ == "__main__":
    unittest.main()
