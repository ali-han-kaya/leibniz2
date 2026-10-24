"""test_dev_bootstrap.py — dev_bootstrap.sh sözleşme-testleri (stdlib-only).

Kapsam: --check exit-kontratı (fail-closed), --help rc=0, arg-kontratı
(rc=2), idempotence, pin-paritesi.
Çalıştırma: venv_z3 python ile (battery listesine girer).

Ortam-guard: venv/node_modules yoksa ortama-bağlı testler SKIP eder —
CI'nın venv'siz `unittest discover` koşumunda süit kırmızıya düşmez
(2026-09-19 adversarial-tur düzeltmesi).

Not: fail-closed testi gerçek .venv_z3'ü geçici-adla gizler; finally bloğu
her durumda geri koyar. Test venv'in kendi yorumlayıcısı altında koştuğu
için rename çalışan süreci bozmaz (açık dosya-tutamaçları inode-bağlıdır).
"""
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir, os.pardir))
SCRIPT = os.path.join(ROOT, "_calisma", "dev_bootstrap.sh")
VENV = os.path.join(ROOT, "_calisma", ".venv_z3")
VENV_PY = os.path.join(VENV, "bin", "python")

PINS = ("z3-solver==5.1.0.0", "PyYAML==6.0.3", "pre_commit==4.3.0")
PPTX_LIB = os.path.join(ROOT, "_calisma", "pptx", "node_modules", "pptxgenjs")
DASH_TSC = os.path.join(ROOT, "apps", "dashboard-next", "node_modules", ".bin", "tsc")


def _run(args, timeout=None, **kw):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kw)


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
        )
        for label, target, hidden, present in cases:
            with self.subTest(unit=label):
                if not present:
                    self.skipTest(label + " kurulu değil — tam-kurulumda koşar")
                os.rename(target, hidden)
                try:
                    r = _run(["bash", SCRIPT, "--check"])
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                finally:
                    if os.path.exists(hidden):
                        os.rename(hidden, target)


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


class TestPptxLockFailClosed(unittest.TestCase):
    """check_pptx lock-drift'te kapanmalı: gerçek script, geçici kopya."""

    def _check_with_lock(self, lock_bytes, pkg_range=None):
        import json
        import shutil
        import tempfile

        tmp = tempfile.mkdtemp(prefix="pptx_lock_")
        try:
            pptx = os.path.join(tmp, "_calisma", "pptx")
            os.makedirs(pptx)
            shutil.copy(os.path.join(ROOT, "_calisma", "pptx", "package.json"), pptx)
            if pkg_range is not None:
                pj = os.path.join(pptx, "package.json")
                with open(pj) as f:
                    pkg = json.load(f)
                pkg["dependencies"]["pptxgenjs"] = pkg_range
                with open(pj, "w") as f:
                    json.dump(pkg, f)
            if lock_bytes is not None:
                with open(os.path.join(pptx, "package-lock.json"), "wb") as f:
                    f.write(lock_bytes)
            # Stub kütüphane: require.resolve kârarı çözülsün, böylece
            # yalnız lock-kapısı karar verir (bağımsız kanıt).
            stub = os.path.join(pptx, "node_modules", "pptxgenjs")
            os.makedirs(stub)
            with open(os.path.join(stub, "package.json"), "w") as f:
                f.write('{"name": "pptxgenjs", "main": "index.js"}')
            with open(os.path.join(stub, "index.js"), "w") as f:
                f.write("module.exports = {};\n")
            # Gerçek check_pptx gövdesini script'ten çek (sourcing script
            # usage/exit yapar; yalnız fonksiyon tanımı alınır).
            body = _run(["bash", "-c", (
                f'awk "/^lock_ok\\(\\) \\{{/,/^\\}}/" "{SCRIPT}"; '
                f'awk "/^check_pptx\\(\\) \\{{/,/^\\}}/" "{SCRIPT}"')])
            driver = f'PPTX="{pptx}"\n{body.stdout}\ncheck_pptx\n'
            return _run(["bash", "-c", driver])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_valid_lock_passes(self):
        with open(os.path.join(ROOT, "_calisma", "pptx", "package-lock.json"), "rb") as f:
            valid = f.read()
        r = self._check_with_lock(valid)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_lock_fails_closed(self):
        r = self._check_with_lock(None)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_drifted_lock_fails_closed(self):
        """package.json'a dep eklenip lock güncellenmemiş = senkronsuz."""
        import json

        with open(os.path.join(ROOT, "_calisma", "pptx", "package-lock.json"), "rb") as f:
            lock = f.read()
        self.assertIsNotNone(json.loads(lock))  # kontrol: geçerli lock
        # Drift: lock'un kök dep'lerinden birini söküyoruz, package.json
        # henüz eski haliyle kalıyor → npm ci --dry-run EUSAGE.
        data = json.loads(lock)
        data["packages"][""]["dependencies"].pop("pptxgenjs", None)
        r = self._check_with_lock(json.dumps(data).encode())
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_version_range_drift_fails_closed(self):
        """Adı lock'ta duran ama aralığı uymayan dep: yalnız npm dry-run yakalar."""
        import json

        with open(os.path.join(ROOT, "_calisma", "pptx", "package-lock.json"), "rb") as f:
            data = json.loads(f.read())
        # package.json'da aralık değişir (lock'ta adı var, isabet etmez).
        # Bu sınıf yalnız npm ci --dry-run ile yakalanır.
        r = self._check_with_lock(json.dumps(data).encode(), pkg_range="^9.0.0")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_corrupt_lock_fails_closed(self):
        r = self._check_with_lock(b'{"name": "x", "lockfileVersion": 3,')
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)


class TestAllNpmUnitsLockGate(unittest.TestCase):
    """Beş npm unit'in check_<unit> kapısı gerçek script'ten alınır;
    bozuk lock (kök dep silinmiş) geçici kopyada rc=1 vermeli."""

    UNITS = {
        "pptx": ("_calisma/pptx", "_calisma/pptx"),
        "dashboard_next": ("apps/dashboard-next", "apps/dashboard-next"),
        "video": ("_calisma/video", "_calisma/video"),
        "dashboard_shadcn": ("apps/dashboard-shadcn", "apps/dashboard-shadcn"),
        "trend_db": ("apps/trend-db", "apps/trend-db"),
    }

    def _probe(self, unit, lock_mutator=None):
        import json
        import shutil
        import tempfile

        rel = self.UNITS[unit][0]
        tmp = tempfile.mkdtemp(prefix="unit_lock_")
        try:
            t = os.path.join(tmp, rel)
            os.makedirs(t)
            for name in ("package.json", "package-lock.json"):
                shutil.copy(os.path.join(ROOT, rel, name), t)
            if lock_mutator is not None:
                lp = os.path.join(t, "package-lock.json")
                with open(lp) as f:
                    data = json.load(f)
                lock_mutator(data)
                with open(lp, "w") as f:
                    json.dump(data, f, indent=2)
            # Gerçek script'ten lock_ok + check_<unit> gövdesi; binary/require
            # kapıları geçici kopyada yok, o yüzden yalnız lock kapısı karar verir.
            body = _run(["bash", "-c",
                         f'awk "/^lock_ok\\(\\)/,/^\\}}/" "{SCRIPT}"; '
                         f'awk "/^check_{unit}\\(\\)/,/^\\}}/" "{SCRIPT}"'])
            driver = (
                f'ROOT="{tmp}"; PPTX="{tmp}/_calisma/pptx"; DASH="{tmp}/apps/dashboard-next"; '
                f'VIDEO="{tmp}/_calisma/video"; SHADCN="{tmp}/apps/dashboard-shadcn"; '
                f'TRENDDB="{tmp}/apps/trend-db"\n{body.stdout}\n'
                f'lock_ok "{t}" && echo LOCK_OK || echo LOCK_BAD\n'
            )
            return _run(["bash", "-c", driver])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _drop_root_dep(data):
        root = data["packages"][""]
        for key in ("dependencies", "devDependencies"):
            if root.get(key):
                root[key].pop(next(iter(root[key])))
                return
        raise AssertionError("root dep yok")

    def test_valid_locks_pass_for_every_unit(self):
        for unit in self.UNITS:
            with self.subTest(unit=unit):
                r = self._probe(unit)
                self.assertIn("LOCK_OK", r.stdout, r.stdout + r.stderr)

    def test_dropped_root_dep_fails_for_every_unit(self):
        for unit in self.UNITS:
            with self.subTest(unit=unit):
                r = self._probe(unit, lock_mutator=self._drop_root_dep)
                self.assertIn("LOCK_BAD", r.stdout, r.stdout + r.stderr)


class TestProvisionDiePath(unittest.TestCase):
    """Runtime sözleşme: GERÇEK script (provision yolu) bozuk lock'ta
    `|| die` mesajıyla rc=1 dönmeli. `|| die` silinirse mesaj kaybolur → klırmzı.
    venv_z3 sahte python ile “kurulu” görünür (pip ağı yok); pptx gerçek
    npm ci'ye düşer ve bozuk lock'ta ölür."""

    DIE_MSG = "BOOTSTRAP FAIL: _calisma/pptx npm ci"

    def _run_script_with_lock(self, lock_bytes, pkg_range=None):
        import json
        import shutil
        import tempfile

        tmp = tempfile.mkdtemp(prefix="bootstrap_die_")
        try:
            os.makedirs(os.path.join(tmp, "_calisma"))
            shutil.copy(SCRIPT, os.path.join(tmp, "_calisma", "dev_bootstrap.sh"))
            # venv_z3: sahte python (freeze çıktısı pinleri verir, install no-op)
            vbin = os.path.join(tmp, "_calisma", ".venv_z3", "bin")
            os.makedirs(vbin)
            fake = os.path.join(vbin, "python")
            with open(fake, "w") as f:
                f.write("#!/bin/sh\ncase \"$*\" in *freeze*) printf '%s\\n' "
                        + " ".join(PINS) + " ;; esac\nexit 0\n")
            os.chmod(fake, 0o755)
            pptx = os.path.join(tmp, "_calisma", "pptx")
            os.makedirs(pptx)
            shutil.copy(os.path.join(ROOT, "_calisma", "pptx", "package.json"), pptx)
            if pkg_range is not None:
                pj = os.path.join(pptx, "package.json")
                with open(pj) as f:
                    pkg = json.load(f)
                pkg["dependencies"]["pptxgenjs"] = pkg_range
                with open(pj, "w") as f:
                    json.dump(pkg, f)
            if lock_bytes is not None:
                with open(os.path.join(pptx, "package-lock.json"), "wb") as f:
                    f.write(lock_bytes)
            # dashboard_next'e hiç ulaşmadan pptx'te durmalı; ulaşırsa da döngü yok.
            return _run(["bash", os.path.join(tmp, "_calisma", "dev_bootstrap.sh")],
                        timeout=180)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_lock_dies_with_message(self):
        r = self._run_script_with_lock(None)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(self.DIE_MSG, r.stderr, r.stdout + r.stderr)

    def test_corrupt_lock_dies_with_message(self):
        r = self._run_script_with_lock(b'{"name": "x", "lockfileVersion": 3,')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(self.DIE_MSG, r.stderr, r.stdout + r.stderr)

    def test_out_of_sync_lock_dies_with_message(self):
        with open(os.path.join(ROOT, "_calisma", "pptx", "package-lock.json"), "rb") as f:
            lock = f.read()
        r = self._run_script_with_lock(lock, pkg_range="^9.0.0")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(self.DIE_MSG, r.stderr, r.stdout + r.stderr)


@unittest.skipUnless(os.path.isfile(VENV_PY), "venv_z3 kurulu değil")
class TestPinParity(unittest.TestCase):
    def test_venv_pins_match_matrix(self):
        r = _run([VENV_PY, "-m", "pip", "freeze"])
        frozen = set(r.stdout.splitlines())
        for pin in PINS:
            self.assertIn(pin, frozen, "pin eksik: " + pin)


if __name__ == "__main__":
    unittest.main()
