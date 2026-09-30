#!/usr/bin/env python3
"""test_dashboard_next_style_gates.py — dashboard-next'in pre-commit kapı
çiftinin (check-prettier-format + check-dashboard-typecheck) birim testleri.

Neden tek modül, iki kapı: ikisi de aynı yüzeyin (apps/dashboard-next, JS/TS)
biçim + tip sözleşmesi ve aynı SKIP kültürünü paylaşıyor (ortam yoksa bloklama,
bulgu varsa fail-closed). HOOK_COVERAGE'ta iki hook id'sine de bağlanır.

Sözleşmeler:
  prettier  : sadece EşLEŞEN dosyalar denetlenir; biçim uyumsuzu exit 1 +
              düzeltme reçetesi; prettier ya da dosya yoksa SKIP exit 0.
              READ-ONLY: --check, yazmaz.
  typecheck : `tsc --noEmit` ve BAŞKA HİÇBİR argüman (emit yok); tsc ya da
              tsconfig yoksa SKIP exit 0; tip hatası exit != 0.
  tip-test  : aynı kapının İKİNCİ katmanı (test-d/run_type_tests.py). Geçiş 1
              pozitif iddiaları ve direktif kullanımını denetler; geçiş 2
              direktifleri geçici bir kopyada kapatıp tsc'nin bastığı tanı
              KODUNU etiketle karşılaştırır. Bu vakalar sahte bir tsc ile
              koşar: boru hattının tamamı (kopyalama, kapatma, ayrıştırma,
              eşleştirme, çıkış kodu) gerçek bir derleyici olmadan sınanır.
  wiring    : hook id'leri .pre-commit-config.yaml'da doğru entry/files ile
              durur ve bu modül check-unit-tests bataryasındadır.

Test izolasyonu: her vaka kendi sahte repo ağacını kurar (kapı scriptleri
REPO'yu KENDI konumlarından türetir), bu yüzden gerçek çalışma ağacına
dokunulmaz ve node_modules'suz bir makinede de vakalar anlamlı kalır
(ortama bağlı olanlar skipUnless ile atlanır).
"""
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
PRETTIER_GATE = HERE / "check_prettier_format.py"
TYPECHECK_GATE = HERE / "check_dashboard_typecheck.sh"
PRETTIER_BIN = REPO / "apps" / "dashboard-next" / "node_modules" / ".bin" / "prettier"
NODE_MODULES = REPO / "apps" / "dashboard-next" / "node_modules"
MANIFEST = HERE / "check_unit_tests.list"
PRECOMMIT_CONFIG = REPO / ".pre-commit-config.yaml"
THIS_FILE = "test_dashboard_next_style_gates.py"

needs_prettier = unittest.skipUnless(
    PRETTIER_BIN.is_file(), "prettier yok (apps/dashboard-next/node_modules)")


# ── sahte repo kurulumu ─────────────────────────────────────────────────────

def _fake_repo() -> pathlib.Path:
    """Gate scriptinin REPO'yu kendi konumundan türettiği sahte ağaç."""
    td = pathlib.Path(tempfile.mkdtemp())
    (td / "_calisma" / "CIKTI").mkdir(parents=True)
    shutil.copy(PRETTIER_GATE, td / "_calisma" / "CIKTI" / PRETTIER_GATE.name)
    # prettier config'i dosya yolundan yukarı doğru arar; kopyalanmazsa
    # vakalar builtin default'larla (semi'siz) koşardı.
    shutil.copy(REPO / ".prettierrc", td / ".prettierrc")
    if NODE_MODULES.is_dir():
        link = td / "apps" / "dashboard-next" / "node_modules"
        link.parent.mkdir(parents=True)
        try:
            link.symlink_to(NODE_MODULES, target_is_directory=True)
        except OSError:
            pass
    return td


def _fake_typecheck_repo(exit_code=0, with_tsc=True, with_tsconfig=True) -> pathlib.Path:
    td = pathlib.Path(tempfile.mkdtemp())
    (td / "_calisma" / "CIKTI").mkdir(parents=True)
    gate = td / "_calisma" / "CIKTI" / TYPECHECK_GATE.name
    shutil.copy(TYPECHECK_GATE, gate)
    gate.chmod(gate.stat().st_mode | stat.S_IEXEC)
    app = td / "apps" / "dashboard-next"
    app.mkdir(parents=True)
    if with_tsconfig:
        (app / "tsconfig.json").write_text("{}\n", encoding="utf-8")
    if with_tsc:
        bin_dir = app / "node_modules" / ".bin"
        bin_dir.mkdir(parents=True)
        fake = bin_dir / "tsc"
        fake.write_text(
            '#!/usr/bin/env bash\n'
            'printf "%s\\n" "$*" >> "$FAKE_TSC_LOG"\n'
            'exit "${FAKE_TSC_EXIT:-0}"\n', encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return td


def _run(cmd, cwd=None, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                          cwd=cwd, env=env)


# ── check-prettier-format ───────────────────────────────────────────────────

class PrettierFormatGateTest(unittest.TestCase):
    def test_no_matching_files_skips(self):
        """pre-commit'in `files:` filtresi boş döndüğünde kapı bloklamaz."""
        td = _fake_repo()
        try:
            script = td / "_calisma" / "CIKTI" / PRETTIER_GATE.name
            r = _run([sys.executable, str(script)])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("SKIP", r.stdout)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_missing_file_path_skips(self):
        """Var olmayan yol eşleşme sayılmaz (filtre fail-closed değil)."""
        td = _fake_repo()
        try:
            script = td / "_calisma" / "CIKTI" / PRETTIER_GATE.name
            r = _run([sys.executable, str(script), "yok/olmayan.ts"])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("SKIP", r.stdout)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_missing_prettier_binary_skips(self):
        """node_modules yoksa SKIP — ortam-bağımlı kapı ortam yoksa bloklamaz.

        Dosya GERÇEKTEN var olmalı: aksi halde kapı daha erken, "eşleşen
        dosya yok" dalında çıkar ve bu dal test edilemez.
        """
        td = pathlib.Path(tempfile.mkdtemp())
        try:
            (td / "_calisma" / "CIKTI").mkdir(parents=True)
            shutil.copy(PRETTIER_GATE, td / "_calisma" / "CIKTI" / PRETTIER_GATE.name)
            sample = td / "ornek.ts"
            sample.write_text("export const x: number = 1;\n", encoding="utf-8")
            script = td / "_calisma" / "CIKTI" / PRETTIER_GATE.name
            r = _run([sys.executable, str(script), str(sample)])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("prettier yok", r.stdout)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    @needs_prettier
    def test_formatted_file_passes(self):
        td = _fake_repo()
        try:
            sample = td / "src" / "ornek.ts"
            sample.parent.mkdir(parents=True)
            sample.write_text("export const x: number = 1;\n", encoding="utf-8")
            script = td / "_calisma" / "CIKTI" / PRETTIER_GATE.name
            r = _run([sys.executable, str(script), str(sample)])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("OK (1 dosya)", r.stdout)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    @needs_prettier
    def test_misformatted_file_fails_closed(self):
        """Biçim uyumsuzu bloklar VE düzeltme reçetesi yazdırılır."""
        td = _fake_repo()
        try:
            sample = td / "src" / "bozuk.ts"
            sample.parent.mkdir(parents=True)
            sample.write_text("export const x   =    1\n", encoding="utf-8")
            script = td / "_calisma" / "CIKTI" / PRETTIER_GATE.name
            r = _run([sys.executable, str(script), str(sample)])
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("FAIL", r.stdout)
            self.assertIn("--write", r.stdout)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    @needs_prettier
    def test_json_is_covered_too(self):
        """Hook `files:` sözleşmesi js/jsx/ts/tsx/json — json da denetlenir."""
        td = _fake_repo()
        try:
            sample = td / "src" / "veri.json"
            sample.parent.mkdir(parents=True)
            sample.write_text('{"a":   1}\n', encoding="utf-8")
            script = td / "_calisma" / "CIKTI" / PRETTIER_GATE.name
            r = _run([sys.executable, str(script), str(sample)])
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    @needs_prettier
    def test_gate_does_not_rewrite_files(self):
        """READ-ONLY sözleşmesi: --check asla dosyayı düzeltmez."""
        td = _fake_repo()
        try:
            sample = td / "src" / "bozuk.ts"
            sample.parent.mkdir(parents=True)
            before = "export const x   =    1\n"
            sample.write_text(before, encoding="utf-8")
            script = td / "_calisma" / "CIKTI" / PRETTIER_GATE.name
            _run([sys.executable, str(script), str(sample)])
            self.assertEqual(sample.read_text(encoding="utf-8"), before)
        finally:
            shutil.rmtree(td, ignore_errors=True)


# ── check-dashboard-typecheck ───────────────────────────────────────────────

class DashboardTypecheckGateTest(unittest.TestCase):
    def _run_gate(self, td, exit_code=0):
        log = td / "tsc-args.log"
        env = dict(os.environ, FAKE_TSC_LOG=str(log),
                   FAKE_TSC_EXIT=str(exit_code))
        gate = td / "_calisma" / "CIKTI" / TYPECHECK_GATE.name
        r = _run(["bash", str(gate)], env=env)
        args = log.read_text(encoding="utf-8").strip() if log.is_file() else None
        return r, args

    def test_clean_typecheck_passes(self):
        td = _fake_typecheck_repo(exit_code=0)
        try:
            r, args = self._run_gate(td)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("OK", r.stdout)
            self.assertEqual(args, "--noEmit")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_type_error_fails_closed(self):
        td = _fake_typecheck_repo(exit_code=1)
        try:
            r, _ = self._run_gate(td, exit_code=1)
            self.assertNotEqual(r.returncode, 0)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_emit_is_never_requested(self):
        """`--noEmit` dışında argüman yok: kapı çıktı üretemez (READ-ONLY)."""
        td = _fake_typecheck_repo()
        try:
            _, args = self._run_gate(td)
            self.assertIsNotNone(args)
            self.assertNotIn("--outDir", args)
            self.assertNotIn("--emit", args)
            self.assertFalse((td / "apps/dashboard-next/tsconfig.tsbuildinfo").exists())
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_missing_tsc_skips(self):
        td = _fake_typecheck_repo(with_tsc=False)
        try:
            r, args = self._run_gate(td)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("SKIP", r.stdout)
            self.assertIsNone(args)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_missing_tsconfig_skips(self):
        td = _fake_typecheck_repo(with_tsconfig=False)
        try:
            r, args = self._run_gate(td)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("SKIP", r.stdout)
            self.assertIsNone(args)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_real_repo_gate_is_green(self):
        """Gerçek ağaç: ya tip hatası yok (OK) ya da ortam yok (SKIP)."""
        r = _run(["bash", str(TYPECHECK_GATE)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue("OK" in r.stdout or "SKIP" in r.stdout, r.stdout)


# ── hook wiring (kapı sözleşmesi config'de) ────────────────────────────────

def _hooks() -> dict:
    try:
        import yaml
    except ImportError:  # pragma: no cover — CI'da pyyaml yoksa atlanır
        raise unittest.SkipTest("pyyaml yok — hook wiring okunamadı")
    data = yaml.safe_load(PRECOMMIT_CONFIG.read_text(encoding="utf-8"))
    out = {}
    for repo in data.get("repos", []):
        for hook in repo.get("hooks", []):
            out[hook["id"]] = hook
    return out


class HookWiringTest(unittest.TestCase):
    def test_prettier_hook_wiring(self):
        hook = _hooks()["check-prettier-format"]
        self.assertEqual(hook["entry"], "python3 _calisma/CIKTI/check_prettier_format.py")
        self.assertIn("ts", hook["files"])
        self.assertIn("json", hook["files"])
        self.assertIn("package-lock", hook["exclude"])
        self.assertEqual(hook["stages"], ["pre-commit"])

    def test_typecheck_hook_wiring(self):
        hook = _hooks()["check-dashboard-typecheck"]
        self.assertEqual(hook["entry"], "bash _calisma/CIKTI/check_dashboard_typecheck.sh")
        self.assertTrue(hook["files"].startswith("^apps/dashboard-next/"))
        self.assertEqual(hook["stages"], ["pre-commit"])

    def test_typecheck_gate_runs_both_layers(self):
        """Kapı yalnız `tsc --noEmit` ile kalmamalı: tip-test katmanı da bağlı."""
        src = TYPECHECK_GATE.read_text(encoding="utf-8")
        self.assertIn("test-d/run_type_tests.py", src)
        self.assertIn("--selftest", src)

    def test_module_is_in_the_battery(self):
        """check-unit_tests.list bu modülü koşmalı (sync --update'in işi)."""
        listed = [ln.strip() for ln in MANIFEST.read_text(encoding="utf-8").splitlines()]
        self.assertIn(THIS_FILE, listed)

    def test_hook_coverage_maps_both_hooks(self):
        """HOOK_COVERAGE iki hook id'sine de bu modülü bağlamalı."""
        sys.path.insert(0, str(HERE))
        import test_coverage_report as cov
        for hook_id in ("check-prettier-format", "check-dashboard-typecheck"):
            self.assertIn(hook_id, cov.HOOK_COVERAGE, hook_id)
            self.assertIn(THIS_FILE, cov.HOOK_COVERAGE[hook_id], hook_id)


# ── tip-test koşucusu (check-dashboard-typecheck'ın ikinci katmanı) ──────────

DASHBOARD = REPO / "apps" / "dashboard-next"
TYPE_RUNNER = DASHBOARD / "test-d" / "run_type_tests.py"
DASHBOARD_TSC = DASHBOARD / "node_modules" / ".bin" / "tsc"

needs_dashboard_tsc = unittest.skipUnless(
    DASHBOARD_TSC.is_file(), "tsc yok (apps/dashboard-next/node_modules)")

# Sahte tsc: geçiş 1'de (pozitif config) sessizce başarılı olur, geçiş 2'de
# (negative config) FAKE_DIAGS'i basıp 1 döner. Böylece koşucunun tüm boru
# hattı gerçek bir derleyici olmadan, hızlı ve hermetik sınanır.
FAKE_TSC_SCRIPT = (
    '#!/usr/bin/env bash\n'
    'case "$*" in\n'
    '  *negative*) [ -n "$FAKE_DIAGS" ] && printf "%s\\n" "$FAKE_DIAGS"; exit 1 ;;\n'
    '  *) exit 0 ;;\n'
    'esac\n'
)


def _fake_type_runner_app(diagnostics="", bare=False, configs=True):
    """Koşucunun APP'yi kendi konumundan türettiği izole ağaç."""
    td = pathlib.Path(tempfile.mkdtemp())
    app = td / "apps" / "dashboard-next"
    (app / "test-d").mkdir(parents=True)
    shutil.copy(TYPE_RUNNER, app / "test-d" / TYPE_RUNNER.name)
    if configs:
        (app / "tsconfig.typetests.json").write_text("{}\n", encoding="utf-8")
        (app / "tsconfig.typetests.negative.json").write_text("{}\n", encoding="utf-8")
    directive = ("// @ts-expect-error etiketsiz" if bare
                 else "// @ts-expect-error TS2345 — sahte iddia")
    (app / "test-d" / "negatives.test-d.ts").write_text(
        f"{directive}\nfoo();\nbar();\n", encoding="utf-8")
    bin_dir = app / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    fake = bin_dir / "tsc"
    fake.write_text(FAKE_TSC_SCRIPT, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return td


def _run_type_runner(td, diagnostics=""):
    app = td / "apps" / "dashboard-next"
    env = dict(os.environ, FAKE_DIAGS=diagnostics)
    return _run([sys.executable, str(app / "test-d" / TYPE_RUNNER.name)],
                cwd=app, env=env)


class TypeTestRunnerTest(unittest.TestCase):
    def test_matching_diagnostic_passes(self):
        td = _fake_type_runner_app(
            "test-d/stripped/negatives.test-d.ts(2,1): error TS2345: sahte")
        try:
            r = _run_type_runner(td, "test-d/stripped/negatives.test-d.ts"
                                     "(2,1): error TS2345: sahte")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("0 sorun", r.stdout)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_wrong_code_fails_closed(self):
        """Direktif hâlâ 'kullanılmış' ama BAŞKA bir nedenden: yakalanmalı."""
        diag = "test-d/stripped/negatives.test-d.ts(2,1): error TS2322: başka"
        td = _fake_type_runner_app(diag)
        try:
            r = _run_type_runner(td, diag)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("kod uyuşmuyor", r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_unclaimed_diagnostic_fails_closed(self):
        """İddia edilmemiş tanı = test dışı derleme hatası; sessiz geçemez."""
        diags = ("test-d/stripped/negatives.test-d.ts(2,1): error TS2345: sahte\n"
                 "test-d/stripped/negatives.test-d.ts(3,1): error TS1005: fazladan")
        td = _fake_type_runner_app(diags)
        try:
            r = _run_type_runner(td, diags)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("İDDİA EDİLMEYEN", r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_missing_diagnostic_fails_closed(self):
        """Yasak hiç hata üretmiyorsa etiket doğrulanamaz."""
        td = _fake_type_runner_app("")
        try:
            r = _run_type_runner(td, "")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("doğrulanamadı", r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_bare_directive_is_rejected(self):
        """Kod etiketsiz direktif reddedilir: kimliği doğrulanamayan iddia."""
        td = _fake_type_runner_app(
            "test-d/stripped/negatives.test-d.ts(2,1): error TS2345: sahte",
            bare=True)
        try:
            r = _run_type_runner(td, "test-d/stripped/negatives.test-d.ts"
                                     "(2,1): error TS2345: sahte")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("kod etiketi olmayan", r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_missing_config_skips(self):
        td = _fake_type_runner_app(configs=False)
        try:
            r = _run_type_runner(td)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("SKIP", r.stdout)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_selftest_is_green(self):
        """Ayrıştırıcının kendi testleri (tsc'siz, her ortamda koşar)."""
        r = _run([sys.executable, str(TYPE_RUNNER), "--selftest"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK", r.stdout)

    @needs_dashboard_tsc
    def test_real_suite_is_green(self):
        """Gerçek ağaçta iki geçiş de yeşil olmalı."""
        r = _run([sys.executable, str(TYPE_RUNNER)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("GEÇİŞ 1: OK", r.stdout)
        self.assertIn("GEÇİŞ 2: OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
