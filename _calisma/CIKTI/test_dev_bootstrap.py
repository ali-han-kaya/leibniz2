"""test_dev_bootstrap.py — dev_bootstrap.sh sözleşme-testleri (stdlib-only).

Kapsam: --check exit-kontratı (fail-closed), --help rc=0, arg-kontratı
(rc=2), idempotence, pin-paritesi, --full batarya-kablolaması.
Çalıştırma: venv_z3 python ile (battery listesine girer).

--full testleri SAHTE batarya enjekte eder (LEIBNIZ2_BOOTSTRAP_BATTERY):
bu test dosyası zaten bataryanın İÇİNDEdir, gerçek bataryayı koşmak
özyineleme olurdu. Sözleşme bataryanın kendisi değil, çağrı-kablolamasıdır
(yeşil → BOOTSTRAP OK, kırmızı → fail-closed, batarya-içi → red).

Ortam-guard: venv/node_modules yoksa ortama-bağlı testler SKIP eder —
CI'nın venv'siz `unittest discover` koşumunda süit kırmızıya düşmez
(2026-09-19 adversarial-tur düzeltmesi).

Not: fail-closed testi gerçek .venv_z3'ü geçici-adla gizler; finally bloğu
her durumda geri koyar. Test venv'in kendi yorumlayıcısı altında koştuğu
için rename çalışan süreci bozmaz (açık dosya-tutamaçları inode-bağlıdır).
"""
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir, os.pardir))
SCRIPT = os.path.join(ROOT, "_calisma", "dev_bootstrap.sh")
VENV = os.path.join(ROOT, "_calisma", ".venv_z3")
VENV_PY = os.path.join(VENV, "bin", "python")

PINS = ("z3-solver==5.1.0.0", "PyYAML==6.0.3", "pre_commit==4.3.0",
        "jsonschema==4.25.1", "pillow==11.3.0")
PPTX_LIB = os.path.join(ROOT, "_calisma", "pptx", "node_modules", "pptxgenjs")
DASH_TSC = os.path.join(ROOT, "apps", "dashboard-next", "node_modules", ".bin", "tsc")
# Batarya manifestindeki testlerin istediği ortam-sentinelleri: biri eksikse
# ilgili test SKIP eder, yani taze checkout'ta yeşil batarya sessizce kapsam
# kaybeder. Bu yüzden her biri bir unit'e bağlı ve --check fail-closed.
TREND_DB_TSX = os.path.join(ROOT, "apps", "trend-db", "node_modules", ".bin", "tsx")
VIDEO_TSC = os.path.join(ROOT, "_calisma", "video", "node_modules", ".bin", "tsc")
VERIFY_YML = os.path.join(ROOT, ".github", "workflows", "verify.yml")


def _run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestCheckContract(unittest.TestCase):
    def test_check_passes_on_provisioned_checkout(self):
        if not os.path.isdir(VENV):
            self.skipTest("araç-kümesi eksik — provisioned-ortam testi tam-kurulumda koşar")
        r = _run(["bash", SCRIPT, "--check"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_check_fail_closed_on_broken_unit(self):
        """Kontrat: herhangi bir unit bozulunca --check rc=1 (işlev-ölçümü)."""
        cases = (
            ("venv", VENV, VENV + ".hidden_by_test", os.path.isdir(VENV)),
            ("pptx", PPTX_LIB, PPTX_LIB + ".hidden_by_test", os.path.isdir(PPTX_LIB)),
            ("dash-tsc", DASH_TSC, DASH_TSC + ".hidden_by_test", os.path.isfile(DASH_TSC)),
            ("trend-db-tsx", TREND_DB_TSX, TREND_DB_TSX + ".hidden_by_test",
             os.path.isfile(TREND_DB_TSX)),
            ("video-tsc", VIDEO_TSC, VIDEO_TSC + ".hidden_by_test",
             os.path.isfile(VIDEO_TSC)),
        )
        for label, target, hidden, present in cases:
            with self.subTest(unit=label):
                if not present:
                    self.skipTest(label + " kurulu değil — tam-kurulumda koşar")
                os.rename(target, hidden)
                try:
                    r = _run(["bash", SCRIPT, "--check"])
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertIn("CHECK FAIL", r.stdout)
                finally:
                    if os.path.exists(hidden):
                        os.rename(hidden, target)
                r2 = _run(["bash", SCRIPT, "--check"])
                self.assertEqual(r2.returncode, 0, "geri-koyma sonrası --check yeşil olmalı")

    def test_check_fail_closed_without_browser_layer(self):
        """Tarayıcı katmanı ÖLÇÜMÜ işlevsel: boş `PLAYWRIGHT_BROWSERS_PATH`
        chromium'u bulunamaz kılar → rc=1. Ölçüm gerçek venv'e dokunmaz
        (paketi gizlemek yerine arama yolunu değiştirir), bu yüzden koşum
        sırasında paralel bir tarayıcı testini bozmaz."""
        if _run(["bash", SCRIPT, "--check"]).returncode != 0:
            self.skipTest("araç-kümesi eksik — tam-kurulumda koşar")
        empty = tempfile.mkdtemp(prefix="no-browsers-")
        self.addCleanup(shutil.rmtree, empty, True)
        env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=empty)
        r = _run(["bash", SCRIPT, "--check"], env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CHECK FAIL: browsers", r.stdout)


class TestArgContract(unittest.TestCase):
    """Arg-kontratı: bilinmeyen/ekstra bayrak rc=2; "" no-args'la-özdeş."""

    def test_bad_usage_exits_two(self):
        for argv in (["--version"], ["--check", "extra"]):
            r = _run(["bash", SCRIPT, *argv])
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("--check", r.stderr)

    def test_empty_string_arg_is_install_not_error(self):
        """${1:-} sözleşmesi: "" bayrağısız-koşumla-özdeş (kurulum-yolu)."""
        check = _run(["bash", SCRIPT, "--check"])
        if check.returncode != 0:
            self.skipTest("araç-kümesi eksik")
        r = _run(["bash", SCRIPT, ""])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("BOOTSTRAP OK", r.stdout)


class TestHelpAndIdempotence(unittest.TestCase):
    def test_help_exits_zero(self):
        r = _run(["bash", SCRIPT, "--help"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("--check", r.stdout)

    def test_bootstrap_twice_is_noop_second_run(self):
        check = _run(["bash", SCRIPT, "--check"])
        if check.returncode != 0:
            self.skipTest("araç-kümesi eksik — idempotence tam-kurulumda koşar")
        r = _run(["bash", SCRIPT])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("up to date", r.stdout)
        self.assertTrue(r.stdout.rstrip().endswith("BOOTSTRAP OK"))


def _provisioned_or_skip(testcase):
    """--full kurulum döngüsü KOŞAR: tam-kurulum yoksa npm/venv indirmeye
    kalkışırdı (ağ + dakikalar). Mevcut sözleşmeyle aynı kapı: --check rc!=0
    → SKIP (CI'nın çıplak unittest discover'ı kırmızıya düşmesin)."""
    if _run(["bash", SCRIPT, "--check"]).returncode != 0:
        testcase.skipTest("araç-kümesi eksik — --full kablolaması tam-kurulumda koşar")


class TestFullFlag(unittest.TestCase):
    """`--full` = kurulum + temel batarya (uçtan uca yeşil koşum)."""

    def setUp(self):
        _provisioned_or_skip(self)

    def _battery(self, body):
        """Sahte batarya betiği (gerçeği dakikalar sürer ve bu testi içerir)."""
        d = tempfile.mkdtemp(prefix="boot-battery-")
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "fake_battery.sh")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/bash\n" + body + "\n")
        return p

    def _run_full(self, battery, in_battery=None):
        env = dict(os.environ)
        env["LEIBNIZ2_BOOTSTRAP_BATTERY"] = battery
        env.pop("LEIBNIZ2_IN_BATTERY", None)  # dış ortam sızmasın
        if in_battery is not None:
            env["LEIBNIZ2_IN_BATTERY"] = in_battery
        return _run(["bash", SCRIPT, "--full"], env=env)

    def test_green_battery_reports_ok_last(self):
        r = self._run_full(self._battery('echo "sahte batarya: 180 dosya PASS."'))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("temel batarya:", r.stdout)
        self.assertIn("sahte batarya", r.stdout, "batarya çıktısı akışa karışmalı")
        self.assertTrue(r.stdout.rstrip().endswith("BOOTSTRAP OK"), r.stdout)

    def test_red_battery_blocks_bootstrap_ok(self):
        r = self._run_full(self._battery('echo "FAILED: test_x" >&2; exit 7'))
        self.assertNotEqual(r.returncode, 0, "kırmızı batarya rc=0 dönemez")
        self.assertIn("BOOTSTRAP FAIL", r.stderr)
        self.assertIn("FAILED: test_x", r.stderr, "bataryanın kendi hatası görünmeli")
        self.assertNotIn("BOOTSTRAP OK", r.stdout, "kırmızı bataryada OK basılmamalı")

    def test_recursion_is_refused_inside_battery(self):
        """Batarya içinden --full: özyineleme, hiç başlamadan reddedilir."""
        r = self._run_full(self._battery("exit 0"), in_battery="1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("özyineleme", r.stderr)
        self.assertNotIn("temel batarya:", r.stdout, "batarya hiç başlamamalı")


class TestFullArgContract(unittest.TestCase):
    """Arg-kontratı: fazladan argüman kuruluma girmeden rc=2."""

    def test_full_rejects_extra_arg(self):
        r = _run(["bash", SCRIPT, "--full", "extra"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--check", r.stderr)

    def test_help_lists_full(self):
        r = _run(["bash", SCRIPT, "--help"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("--full", r.stdout)


@unittest.skipUnless(os.path.isfile(VENV_PY), "venv_z3 kurulu değil")
class TestPinParity(unittest.TestCase):
    def test_venv_pins_match_matrix(self):
        r = _run([VENV_PY, "-m", "pip", "freeze"])
        frozen = set(r.stdout.splitlines())
        for pin in PINS:
            self.assertIn(pin, frozen, "pin eksik: " + pin)

    def test_pins_cover_the_battery_imports(self):
        """Pin listesi bataryanın GERÇEKTEN istediği paketleri kapsamalı:
        manifestte jsonschema/PIL isteyen testler var; pin eksikse taze
        checkout'ta o testler SKIP eder (sessiz kapsam kaybı)."""
        script = _read(SCRIPT)
        for pin in PINS:
            self.assertIn(pin, script, "scriptte pin yok: " + pin)
        battery = os.path.join(ROOT, "_calisma", "CIKTI", "check_unit_tests.list")
        listed = set(_read(battery).split())
        consumers = {
            "jsonschema==4.25.1": "test_validate_config_schema.py",
            "pillow==11.3.0": "test_verification_chain_deck.py",
        }
        for pin, test in consumers.items():
            self.assertIn(test, listed,
                          "%s bataryada değil — pin gerekçesi boşa düşmüş" % test)
            self.assertIn(pin, PINS)


# ── tarayıcı katmanı: sahte kök ile hermetik kurulum testi ───────────────

def _script_pins():
    """Script'in PINS dizisi (tek kaynak) — sahte venv aynı satırları basar."""
    m = re.search(r"PINS=\(([^)]*)\)", _read(SCRIPT), re.S)
    if not m:
        raise AssertionError("PINS dizisi bulunamadı")
    return m.group(1).split()


FAKE_VENV_PY = '''#!/usr/bin/env python3
"""Sahte venv python'u — scriptin çağırdığı dört yolu taklit eder."""
import os, sys
log = os.environ.get("FAKE_LOG")
args = sys.argv[1:]
if args[:2] == ["-m", "pip"] and args[2:3] == ["freeze"]:
    print(os.environ.get("FAKE_FREEZE", ""))
    sys.exit(0)
if args[:2] == ["-m", "pip"] and args[2:3] == ["install"]:
    open(log, "a").write("pip " + " ".join(args) + "\\n")
    sys.exit(0)
if args[:2] == ["-m", "playwright"]:
    open(log, "a").write("playwright " + " ".join(args) + "\\n")
    sys.exit(0)
if args[:1] == ["-"]:                     # stdin programı: check_browsers
    sys.stdin.read()
    sys.exit(0 if os.environ.get("FAKE_BROWSER_OK") == "1" else 1)
sys.exit(1)                              # beklenmeyen çağrı = gürültülü fail
'''

FAKE_NODE = '#!/bin/bash\nexit 0\n'
FAKE_NPM = '#!/bin/bash\nprintf "npm %s\\n" "$*" >> "$FAKE_LOG"\n'


def _fake_bootstrap_root():
    """Script'i sahte bir köke kopyalar; her unit'in sentineli hazır.

    Gerçek ağaçtaki kurulum yolunu (pip/playwright install) AĞA ÇIKMADAN ve
    gerçek venv'e dokunmadan sınamanın tek yolu: ROOT scriptin kendi
    konumundan türetilir, dolayısıyla kopya kendi kökünü kurar.
    """
    td = tempfile.mkdtemp(prefix="boot-fakeroot-")
    root = pathlib.Path(td)
    (root / "_calisma").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "_calisma" / "dev_bootstrap.sh")
    # node/npm sahte PATH'ten gelir: ortamda node olmasa da test koşar.
    bindir = root / "bin"
    bindir.mkdir()
    for name, body in (("node", FAKE_NODE), ("npm", FAKE_NPM)):
        p = bindir / name
        p.write_text(body, encoding="utf-8")
        p.chmod(0o755)
    vbin = root / "_calisma" / ".venv_z3" / "bin"
    vbin.mkdir(parents=True)
    vpy = vbin / "python"
    vpy.write_text(FAKE_VENV_PY, encoding="utf-8")
    vpy.chmod(0o755)
    for rel in ("_calisma/pptx/node_modules/pptxgenjs/package.json",
                "_calisma/docx/node_modules/docx/package.json"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"name":"fake"}\n', encoding="utf-8")
    for rel in ("apps/dashboard-next/node_modules/.bin/tsc",
                "apps/dashboard-next/node_modules/.bin/next",
                "apps/trend-db/node_modules/.bin/tsx",
                "_calisma/video/node_modules/.bin/tsc"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        p.chmod(0o755)
    return root


class TestBrowserLayerProvisioning(unittest.TestCase):
    """`browsers` unit'i iki adımlı (pip pin + chromium indirme) ve ağa
    çıkar; bu yüzden ölçümü sahte kökte yapılır."""

    def setUp(self):
        self.root = _fake_bootstrap_root()
        self.addCleanup(shutil.rmtree, str(self.root), True)
        self.log = str(self.root / "calls.log")
        self.env = dict(os.environ)
        self.env["FAKE_LOG"] = self.log
        self.env["FAKE_FREEZE"] = "\n".join(_script_pins())
        self.env["PATH"] = str(self.root / "bin") + os.pathsep + self.env["PATH"]
        self.env.pop("LEIBNIZ2_IN_BATTERY", None)
        battery = self.root / "fake_battery.sh"
        battery.write_text('#!/bin/bash\necho "sahte batarya: 3 dosya PASS."\n',
                           encoding="utf-8")
        self.env["LEIBNIZ2_BOOTSTRAP_BATTERY"] = str(battery)
        pathlib.Path(self.log).write_text("", encoding="utf-8")

    def _run_boot(self, *argv):
        script = str(self.root / "_calisma" / "dev_bootstrap.sh")
        return _run(["bash", script, *argv], env=self.env)

    def test_full_provisions_pin_and_chromium(self):
        self.env["FAKE_BROWSER_OK"] = "0"
        r = self._run_boot("--full")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = _read(self.log)
        self.assertIn("pip install --quiet playwright==1.63.0", calls)
        self.assertIn("playwright install chromium", calls)
        self.assertIn("browsers:", r.stdout)
        self.assertTrue(r.stdout.rstrip().endswith("BOOTSTRAP OK"), r.stdout)

    def test_working_browser_is_not_reinstalled(self):
        """Çalışan chromium varsa indirme TETİKLENMEZ (idempotence)."""
        self.env["FAKE_BROWSER_OK"] = "1"
        r = self._run_boot()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("browsers: up to date", r.stdout)
        self.assertEqual(_read(self.log), "")

    def test_missing_browser_layer_fails_check_closed(self):
        self.env["FAKE_BROWSER_OK"] = "0"
        r = self._run_boot("--check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CHECK FAIL: browsers", r.stdout)

    def test_browser_pin_matches_ci(self):
        """İkinci kaynak yok: scriptin tarayıcı pini CI'daki `playwright==`
        piniyle AYNI olmalı (verify.yml'de iki adım aynı sürümü kurar)."""
        m = re.search(r'BROWSER_PIN="playwright==([^"]+)"', _read(SCRIPT))
        self.assertIsNotNone(m, "BROWSER_PIN bulunamadı")
        pins = set(re.findall(r"playwright==([0-9.]+)", _read(VERIFY_YML)))
        self.assertEqual(pins, {m.group(1)},
                         "script ile CI pinleri ayrıştı: %s vs %s" % (pins, m.group(1)))


if __name__ == "__main__":
    unittest.main()
