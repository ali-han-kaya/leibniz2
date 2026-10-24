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

# Tarayıcı tabanı (dev_bootstrap.sh BROWSER_MIN_PY_* ile aynı sözleşme:
# pin'li playwright Python>=3.10 ister). Canlı venv tabanın altındaysa
# bayraksız koşum fail-closed die verir — o testler SKIP eder (ortam eksiği).
BROWSER_FLOOR = (3, 10)


def _live_venv_py_mm():
    """Canlı venv yorumlayıcısının (majör, minör) sürümü; yoksa/bozuksa None."""
    if not os.path.isfile(VENV_PY):
        return None
    try:
        r = _run([VENV_PY, "-c",
                  "import sys; print('%d.%d' % sys.version_info[:2])"],
                 timeout=60)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    parts = r.stdout.strip().split(".")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    return (int(parts[0]), int(parts[1]))


def _live_venv_below_browser_floor():
    mm = _live_venv_py_mm()
    return mm is not None and mm < BROWSER_FLOOR


def _run(args, timeout=None, **kw):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kw)


def _script_units():
    """dev_bootstrap.sh'in UNITS dizisi — tablo/malivet testleri için tek kaynak."""
    import re
    with open(SCRIPT, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^UNITS=\(([^)]*)\)\s*$", text, re.M)
    return m.group(1).split() if m else []


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
        if _live_venv_below_browser_floor():
            self.skipTest("canlı venv tarayıcı tabanının altında — "
                          "bayraksız koşum fail-closed die verir")
        r = _run(["bash", SCRIPT, ""])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("BOOTSTRAP OK", r.stdout)


class TestPlanContract(unittest.TestCase):
    """--check --plan: kurulum yapmadan tahmin tablosu basar, rc=0."""

    def test_plan_lists_units_and_totals(self):
        r = _run(["bash", SCRIPT, "--check", "--plan"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for needle in ("venv_z3", "pptx", "dashboard_next", "TOTAL"):
            self.assertIn(needle, r.stdout, r.stdout + r.stderr)

    def test_plan_bogus_second_arg_exits_two(self):
        r = _run(["bash", SCRIPT, "--check", "--bogus"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_plan_is_report_only_on_broken_unit(self):
        """Bozuk unit'te bile plan rc=0 basar ve kurulum yapmaz."""
        if not os.path.isdir(PPTX_LIB):
            self.skipTest("pptx kurulu değil — tam-kurulumda koşar")
        os.rename(PPTX_LIB, PPTX_LIB + ".hidden_by_test")
        try:
            r = _run(["bash", SCRIPT, "--check", "--plan"])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("fail", r.stdout, r.stdout + r.stderr)
            self.assertTrue(os.path.exists(PPTX_LIB + ".hidden_by_test"),
                            "plan kurulum yapmamalı")
        finally:
            if os.path.exists(PPTX_LIB + ".hidden_by_test"):
                os.rename(PPTX_LIB + ".hidden_by_test", PPTX_LIB)


class TestHelpAndIdempotence(unittest.TestCase):
    def test_help_exits_zero(self):
        r = _run(["bash", SCRIPT, "--help"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("--check", r.stdout)

    def test_bootstrap_twice_is_noop_second_run(self):
        check = _run(["bash", SCRIPT, "--check"])
        if check.returncode != 0:
            self.skipTest("araç-kümesi eksik — idempotence tam-kurulumda koşar")
        if _live_venv_below_browser_floor():
            self.skipTest("canlı venv tarayıcı tabanının altında — "
                          "bayraksız koşum fail-closed die verir")
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
                f'awk "/^node_candidate_dirs\\(\\) \\{{/,/^\\}}/" "{SCRIPT}"; '
                f'awk "/^node_tools\\(\\) \\{{/,/^\\}}/" "{SCRIPT}"; '
                f'awk "/^lock_ok\\(\\) \\{{/,/^\\}}/" "{SCRIPT}"; '
                f'awk "/^check_pptx\\(\\) \\{{/,/^\\}}/" "{SCRIPT}"')])
            driver = (f'NPM_BIN=""; NODE_BIN=""; PPTX="{pptx}"\n'
                      f'{body.stdout}\ncheck_pptx\n')
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
                         f'awk "/^node_candidate_dirs\\(\\)/,/^\\}}/" "{SCRIPT}"; '
                         f'awk "/^node_tools\\(\\)/,/^\\}}/" "{SCRIPT}"; '
                         f'awk "/^lock_ok\\(\\)/,/^\\}}/" "{SCRIPT}"; '
                         f'awk "/^check_{unit}\\(\\)/,/^\\}}/" "{SCRIPT}"'])
            driver = (
                f'NPM_BIN=""; NODE_BIN=""; '
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
                # Sürüm sorgularına 3.11 döner: taban kapısından geçer
                # ("kurulu" artık floor'u da içerir), freeze pin-pariteli.
                f.write("#!/bin/sh\ncase \"$*\" in\n")
                f.write("  *-c*) echo \"3.11\" ;;\n")
                f.write("  *--version*) echo \"Python 3.11.15\" ;;\n")
                f.write("  *freeze*) printf '%s\\n' "
                        + " ".join(PINS) + " ;;\n")
                f.write("esac\nexit 0\n")
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
            # dashboard_next'i “kurulu” yap: UNITS sırası ne olursa olsun ilk
            # kırık unit pptx olsun (testin niyeti: bozuk lock → pptx die mesajı).
            dash = os.path.join(tmp, "apps", "dashboard-next")
            os.makedirs(dash)
            for name in ("package.json", "package-lock.json"):
                shutil.copy(os.path.join(ROOT, "apps", "dashboard-next", name), dash)
            bindir = os.path.join(dash, "node_modules", ".bin")
            os.makedirs(bindir)
            for binary in ("tsc", "next"):
                stub = os.path.join(bindir, binary)
                with open(stub, "w") as f:
                    f.write("#!/bin/sh\nexit 0\n")
                os.chmod(stub, 0o755)
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


class TestPreInstallPlanTable(unittest.TestCase):
    """Bayraksız kurulum yolu: maliyet tablosu (conf ölçümleri) kurulumdan ÖNCE.

    Hermetik fixture: venv_z3 sahte-python ile “kurulu” (ok), pptx lock'suz
    (fail), apps/dashboard-next yok (fail). Tablo her üç satırı da içermeli ve
    kurulum çıktısından önce basılmalı; kurulum yine denenip die ile bitmeli.
    """

    def test_table_printed_before_install(self):
        import shutil
        import tempfile

        tmp = tempfile.mkdtemp(prefix="bootstrap_plan_")
        try:
            os.makedirs(os.path.join(tmp, "_calisma"))
            shutil.copy(SCRIPT, os.path.join(tmp, "_calisma", "dev_bootstrap.sh"))
            vbin = os.path.join(tmp, "_calisma", ".venv_z3", "bin")
            os.makedirs(vbin)
            fake = os.path.join(vbin, "python")
            with open(fake, "w") as f:
                f.write("#!/bin/sh\ncase \"$*\" in\n")
                f.write("  *-c*) echo \"3.11\" ;;\n")
                f.write("  *--version*) echo \"Python 3.11.15\" ;;\n")
                f.write("  *freeze*) printf '%s\\n' " + " ".join(PINS) + " ;;\n")
                f.write("esac\nexit 0\n")
            os.chmod(fake, 0o755)
            pptx = os.path.join(tmp, "_calisma", "pptx")
            os.makedirs(pptx)
            shutil.copy(os.path.join(ROOT, "_calisma", "pptx", "package.json"), pptx)

            r = _run(["bash", os.path.join(tmp, "_calisma", "dev_bootstrap.sh")],
                     timeout=180)
            out = r.stdout

            self.assertIn("PROVISION PLAN", out, out + r.stderr)
            self.assertIn("TO-PROVISION", out, out + r.stderr)
            units = _script_units()
            self.assertTrue(units, "UNITS=(...) okunamadı")
            rows = {}
            for line in out.splitlines():
                parts = line.split()
                if parts and parts[0] in units:
                    rows[parts[0]] = parts[1:]
            self.assertEqual(set(rows), set(units),
                             "tablo her unit'i listemeli: %s" % out)
            self.assertIn("ok", rows["venv_z3"], out)
            self.assertIn("fail", rows["pptx"], out)
            self.assertIn("fail", rows["dashboard_next"], out)
            # Tablo kurulumdan ÖNCE basılmalı.
            self.assertLess(out.index("PROVISION PLAN"), out.index("npm ci"), out)
            # Kurulum yine denenir ve die ile biter.
            self.assertEqual(r.returncode, 1, out + r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestBrowserFloor(unittest.TestCase):
    """Tarayıcı tabanı: die mesajı SAPTANAN yorumlayıcıyı adlandırır.

    Hermetik: gerçek script tmp kopyada, sahte yorumlayıcılarla koşar;
    ağ/pip yok — taban kapısı provizyondan ÖNCE öldüğü için kurulum yapılmaz.
    Saptama tam-yalıtımlı: DEV_BOOTSTRAP_PYTHON_DIRS yalnız sahte dizini
    tarar (gerçek makinedeki yorumlayıcılar sonucu değiştiremez).
    """

    FAKE311_VER = "Python 3.11.15"
    FAKE39_VER = "Python 3.9.6"

    @staticmethod
    def _write_version_fake(path, mm, full):
        """-c sorgusuna mm, --version'a full dönen sahte yorumlayıcı."""
        with open(path, "w") as f:
            f.write("#!/bin/sh\n")
            f.write("if [ \"$1\" = \"-c\" ]; then echo \"%s\"; " % mm)
            f.write("elif [ \"$1\" = \"--version\" ]; then echo \"%s\"; " % full)
            f.write("else exit 1; fi\n")
        os.chmod(path, 0o755)

    @staticmethod
    def _write_venv_fake(path, mm, full):
        """Sürüm sorguları + pin-pariteli freeze dönen sahte venv python'u."""
        with open(path, "w") as f:
            f.write("#!/bin/sh\ncase \"$*\" in\n")
            f.write("  *-c*) echo \"%s\" ;;\n" % mm)
            f.write("  *--version*) echo \"%s\" ;;\n" % full)
            f.write("  *freeze*) printf '%s\\n' " + " ".join(PINS) + " ;;\n")
            f.write("esac\nexit 0\n")
        os.chmod(path, 0o755)

    @staticmethod
    def _write_interpreter_fake(path, mm, full):
        """Sürüm sorguları + `-m venv <dir>` yeteneği olan sahte yorumlayıcı.

        Onarım akışı için gerekli: yetersiz venv silinince betik bu yorumlayıcıyla
        yeni venv kurar (kopyala kendini bin/python'a).
        """
        with open(path, "w") as f:
            f.write("#!/bin/sh\n")
            f.write("if [ \"$1\" = \"-c\" ]; then echo \"%s\"; " % mm)
            f.write("elif [ \"$1\" = \"--version\" ]; then echo \"%s\"; " % full)
            f.write("elif [ \"$1\" = \"-m\" ] && [ \"$2\" = \"venv\" ]; "
                    "then mkdir -p \"$3/bin\" && cp \"$0\" \"$3/bin/python\"; ")
            # Yeniden kurulan venv pinleri İÇERİR: `pip freeze` pin-pariteli.
            f.write("elif [ \"$1\" = \"-m\" ] && [ \"$2\" = \"pip\" ] "
                    "&& [ \"$3\" = \"freeze\" ]; "
                    "then printf '%s\\n' " + " ".join(PINS) + "; ")
            f.write("fi\nexit 0\n")
        os.chmod(path, 0o755)

    @staticmethod
    def _write_creator_fake(path):
        """-m venv'yi taklit eden sahte kurucu (3.11): kopyayla venv kurar."""
        with open(path, "w") as f:
            f.write("#!/bin/sh\n")
            f.write("if [ \"$1\" = \"-c\" ]; then echo \"3.11\"\n")
            f.write("elif [ \"$1\" = \"--version\" ]; then "
                    "echo \"Python 3.11.15\"\n")
            f.write("elif [ \"$1\" = \"-m\" ] && [ \"$2\" = \"venv\" ]; "
                    "then mkdir -p \"$3/bin\" && cp \"$0\" \"$3/bin/python\"\n")
            f.write("fi\nexit 0\n")
        os.chmod(path, 0o755)

    def _stage(self):
        """tmp kök + sahte PATH hazırlar; (root, fakebin, env) döner."""
        import shutil
        import tempfile

        tmp = tempfile.mkdtemp(prefix="bootstrap_floor_")
        self.addCleanup(shutil.rmtree, tmp, True)
        root = os.path.join(tmp, "root")
        os.makedirs(os.path.join(root, "_calisma"))
        shutil.copy(SCRIPT, os.path.join(root, "_calisma", "dev_bootstrap.sh"))
        fakebin = os.path.join(tmp, "fakebin")
        os.makedirs(fakebin)
        self._write_version_fake(os.path.join(fakebin, "python3"),
                                 "3.9", self.FAKE39_VER)
        # python3.11 aynı zamanda `-m venv` kurabilmeli: taban onarımı
        # venv'i KENDİSİ yeniden kurar (komut bastırmaz).
        self._write_interpreter_fake(os.path.join(fakebin, "python3.11"),
                                     "3.11", self.FAKE311_VER)
        self._stage_installed_dashboard_next(root, fakebin)
        env = {
            "PATH": fakebin + ":/usr/bin:/bin",
            "DEV_BOOTSTRAP_PYTHON_DIRS": os.path.join(fakebin, "python3*"),
        }
        return root, fakebin, env

    @staticmethod
    def _stage_installed_dashboard_next(root, fakebin):
        """dashboard_next'i “kurulu” göster ki testler sıradan bağımsız kalsın.

        Sahte npm YALNIZ `--dry-run` (lock kapısı) için 0 döner; gerçek
        provizyon çağrısı (`npm ci --prefix`) 1 döner — böylece UNITS sırası
        ne olursa olsun walk venv_z3'e ulaşır ve pptx'te ölür.
        """
        npm = os.path.join(fakebin, "npm")
        with open(npm, "w") as f:
            f.write("#!/bin/sh\ncase \"$*\" in\n")
            f.write("  *--dry-run*) exit 0 ;;\n")
            f.write("  *) exit 1 ;;\n")
            f.write("esac\n")
        os.chmod(npm, 0o755)
        node = os.path.join(fakebin, "node")
        with open(node, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(node, 0o755)
        bindir = os.path.join(root, "apps", "dashboard-next", "node_modules", ".bin")
        os.makedirs(bindir)
        for binary in ("tsc", "next"):
            stub = os.path.join(bindir, binary)
            with open(stub, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(stub, 0o755)

    def _run_bare(self, root, env):
        return _run(["bash", os.path.join(root, "_calisma", "dev_bootstrap.sh")],
                    timeout=120, env=env)

    def _install_venv_fake(self, root, mm, full):
        vbin = os.path.join(root, "_calisma", ".venv_z3", "bin")
        os.makedirs(vbin)
        self._write_venv_fake(os.path.join(vbin, "python"), mm, full)

    def test_stale_venv_is_rebuilt_with_detected_interpreter(self):
        """Taban-altı venv: betik uygun yorumlayıcıyı bulup venv'i KENDİSİ kurar."""
        root, fakebin, env = self._stage()
        self._install_venv_fake(root, "3.9", self.FAKE39_VER)
        r = self._run_bare(root, env)
        out = r.stdout + r.stderr
        # Onarım yapıldı: venv tabanı sağlayan yorumlayıcıyla yeniden kuruldu
        self.assertIn("YENİDEN kuruluyor", r.stdout, out)
        self.assertIn(os.path.join(fakebin, "python3.11"), r.stdout, out)
        vpy = os.path.join(root, "_calisma", ".venv_z3", "bin", "python")
        self.assertTrue(os.path.isfile(vpy), "venv yeniden kurulmalı:\n" + out)
        # Kullanıcıya komut bastırmaz: onarımı betik yaptı
        self.assertNotIn("ÇÖZÜM:", out)
        self.assertNotIn("DEV_BOOTSTRAP_PYTHON3='", out)
        # Onarım TEK kez: yeniden kurulan venv pinleri taşıdığı için plan
        # onu tekrar “fail” görüp ikinci kez kurmaz.
        self.assertEqual(out.count("venv_z3: kuruluyor"), 1, out)
        # Sonra pptx provizyonunda ölür (npm yok)
        self.assertEqual(r.returncode, 1, out)
        self.assertIn("BOOTSTRAP FAIL: _calisma/pptx npm ci", r.stderr)

    def test_missing_venv_is_created_with_detected_interpreter(self):
        """Venv yok + PATH python3 taban-altı: yine uygun adayla betik kurar."""
        root, fakebin, env = self._stage()
        r = self._run_bare(root, env)
        out = r.stdout + r.stderr
        self.assertIn("venv yok", r.stdout, out)
        self.assertIn(os.path.join(fakebin, "python3.11"), r.stdout, out)
        vpy = os.path.join(root, "_calisma", ".venv_z3", "bin", "python")
        self.assertTrue(os.path.isfile(vpy), "venv kurulmalı:\n" + out)
        self.assertNotIn("ÇÖZÜM:", out)
        self.assertEqual(r.returncode, 1, out)
        self.assertIn("BOOTSTRAP FAIL: _calisma/pptx npm ci", r.stderr)

    def test_no_rebuild_opt_out_dies_naming_candidate(self):
        """DEV_BOOTSTRAP_NO_REBUILD=1: onarım yok, venv'e dokunulmaz."""
        root, fakebin, env = self._stage()
        env = dict(env, DEV_BOOTSTRAP_NO_REBUILD="1")
        self._install_venv_fake(root, "3.9", self.FAKE39_VER)
        r = self._run_bare(root, env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        err = r.stderr
        self.assertIn("BOOTSTRAP FAIL: tarayıcı tabanı", err)
        self.assertIn("DEV_BOOTSTRAP_NO_REBUILD", err)
        self.assertIn(os.path.join(fakebin, "python3.11"), err)
        self.assertNotIn("YENİDEN kuruluyor", r.stdout)
        self.assertTrue(os.path.isdir(os.path.join(root, "_calisma", ".venv_z3")),
                        "opt-out'ta venv silinmemeli")

    def test_no_candidate_dies_without_placeholder_recipe(self):
        """Aday yoksa die dürüstçe 'bulunamadı' der, tarif uydurmaz."""
        root, fakebin, env = self._stage()
        env = dict(env, DEV_BOOTSTRAP_PYTHON_DIRS=os.path.join(fakebin,
                                                                "python3"))
        r = self._run_bare(root, env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        err = r.stderr
        self.assertIn("BOOTSTRAP FAIL: tarayıcı tabanı", err)
        self.assertIn("bulunamadı", err)
        self.assertIn("DEV_BOOTSTRAP_PYTHON_DIRS", err)
        self.assertNotIn("ÇÖZÜM:", err)
        self.assertNotIn("bulunduğu dizin", err)
        # Komut bastırmıyor: çalıştırılabilir tarif yok, yalnız talimat.
        self.assertNotIn("rm -rf", err)
        self.assertNotIn("DEV_BOOTSTRAP_PYTHON3='", err)

    def test_satisfying_venv_passes_floor(self):
        """Tabanı sağlayan venv floor'dan geçer, sonraki unit'te durur."""
        root, fakebin, env = self._stage()
        self._install_venv_fake(root, "3.11", self.FAKE311_VER)
        r = self._run_bare(root, env)
        # npm yok → pptx provizyonu ölür; floor izi olmamalı.
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("venv_z3: up to date", r.stdout)
        self.assertNotIn("tarayıcı tabanı", r.stdout + r.stderr)
        self.assertIn("BOOTSTRAP FAIL: _calisma/pptx npm ci", r.stderr)

    def test_override_creator_is_honored(self):
        """DEV_BOOTSTRAP_PYTHON3 kurucusu tabanı sağlarsa provizyon yürür."""
        root, fakebin, env = self._stage()
        creator = os.path.join(os.path.dirname(fakebin), "creator311")
        self._write_creator_fake(creator)
        env = dict(env, DEV_BOOTSTRAP_PYTHON3=creator)
        r = self._run_bare(root, env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("venv_z3: kuruluyor", r.stdout)
        self.assertNotIn("tarayıcı tabanı", r.stdout + r.stderr)
        self.assertIn("BOOTSTRAP FAIL: _calisma/pptx npm ci", r.stderr)


class TestNoCustomPath(unittest.TestCase):
    """PATH'te npm/node/python3 olmayan makine (nvm/homebrew profili yok,
    cron/launchd, minimal CI PATH).

    Tarayıcı tabanıyla AYNI kanıt deseni: her araç ya PATH dışındaki bilinen
    bir konumdan ÇÖZÜLMELİ ya da EYLEME DÖNÜK fail-closed die vermeli —
    ciplak “command not found” olmamalı.
    """

    BARE_PATH = "/usr/bin:/bin"

    def _stage(self):
        import shutil
        import tempfile

        tmp = tempfile.mkdtemp(prefix="bootstrap_nopath_")
        self.addCleanup(shutil.rmtree, tmp, True)
        root = os.path.join(tmp, "root")
        os.makedirs(os.path.join(root, "_calisma"))
        shutil.copy(SCRIPT, os.path.join(root, "_calisma", "dev_bootstrap.sh"))
        # venv_z3 “kurulu” (taban üstü) → taban kapısı geçsin
        vbin = os.path.join(root, "_calisma", ".venv_z3", "bin")
        os.makedirs(vbin)
        fake = os.path.join(vbin, "python")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\ncase \"$*\" in\n")
            f.write("  *-c*) echo \"3.11\" ;;\n")
            f.write("  *--version*) echo \"Python 3.11.20\" ;;\n")
            f.write("  *freeze*) printf '%s\\n' " + " ".join(PINS) + " ;;\n")
            f.write("esac\nexit 0\n")
        os.chmod(fake, 0o755)
        # npm unit'lerinin çözülmesi için gereken manifestler (repo'dan)
        pptx = os.path.join(root, "_calisma", "pptx")
        os.makedirs(pptx)
        for name in ("package.json", "package-lock.json"):
            shutil.copy(os.path.join(ROOT, "_calisma", "pptx", name), pptx)
        dash = os.path.join(root, "apps", "dashboard-next")
        os.makedirs(dash)
        shutil.copy(os.path.join(ROOT, "apps", "dashboard-next", "package.json"), dash)
        # npm/node: PATH'TE DEĞİL, ayrı bir dizinde.
        # npm GERÇEKÇİ olmalı: gerçek npm bir node betiğidir
        # (#!/usr/bin/env node) — çıplak `#!/bin/sh` stub'ı PATH düzeltmesini
        # kanıtlamaz, çünkü env node'u hiç aramaz.
        nodebin = os.path.join(tmp, "nodebin")
        os.makedirs(nodebin)
        with open(os.path.join(nodebin, "npm"), "w") as f:
            f.write("#!/usr/bin/env node\nprocess.exit(0);\n")
        with open(os.path.join(nodebin, "node"), "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        for name in ("npm", "node"):
            os.chmod(os.path.join(nodebin, name), 0o755)
        return root, nodebin, tmp

    def test_npm_and_node_resolved_outside_path(self):
        """PATH'te npm yok: aday dizinden çözülmeli → pptx ok."""
        import shutil as _shutil
        if _shutil.which("npm", path=self.BARE_PATH):
            self.skipTest("%s zaten npm içeriyor — yalıtım kurulamaz" % self.BARE_PATH)
        root, nodebin, _ = self._stage()
        r = _run(
            ["bash", os.path.join(root, "_calisma", "dev_bootstrap.sh"), "--check"],
            timeout=120,
            env=dict(os.environ, PATH=self.BARE_PATH, DEV_BOOTSTRAP_NODE_DIRS=nodebin),
        )
        self.assertIn('"pptx": "ok"', r.stdout, r.stdout + r.stderr)

    def test_missing_npm_fails_closed_with_actionable_message(self):
        """npm hiçbir yerde yok: die aranan yerleri ve override'ı adlandırmalı."""
        root, nodebin, tmp = self._stage()
        empty = os.path.join(tmp, "emptynode")
        os.makedirs(empty)
        r = _run(
            ["bash", os.path.join(root, "_calisma", "dev_bootstrap.sh")],
            timeout=120,
            env=dict(os.environ, PATH=self.BARE_PATH, DEV_BOOTSTRAP_NODE_DIRS=empty),
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        err = r.stderr
        self.assertIn("npm/node bulunamadı", err)
        self.assertIn("DEV_BOOTSTRAP_NPM", err)
        self.assertIn(empty, err, "aranan aday dizin die mesajında olmalı")
        self.assertNotIn("command not found", err)

    def test_python3_bin_finds_home_local_without_path(self):
        """--validate yorumlayıcısı: PATH'te python3 yokken $HOME/.local/bin."""
        import shutil
        import tempfile

        tmp = tempfile.mkdtemp(prefix="py3bin_")
        self.addCleanup(shutil.rmtree, tmp, True)
        home = os.path.join(tmp, "home")
        bindir = os.path.join(home, ".local", "bin")
        os.makedirs(bindir)
        fake = os.path.join(bindir, "python3")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(fake, 0o755)
        body = _run(["bash", "-c",
                     f'awk "/^python3_bin\\(\\)/,/^\\}}/" "{SCRIPT}"'])
        r = _run(["bash", "-c", body.stdout + "\npython3_bin\n"],
                 env=dict(os.environ, PATH="/bin", HOME=home))
        self.assertEqual(r.stdout.strip(), fake, r.stdout + r.stderr)

    def test_validate_runs_without_python3_on_path(self):
        """`--validate` PATH'te python3 olmadan da koşar (stdlib-only)."""
        import shutil
        import sys

        root, _nodebin, _tmp = self._stage()
        cikti = os.path.join(root, "_calisma", "CIKTI")
        os.makedirs(cikti)
        shutil.copy(os.path.join(ROOT, "_calisma", "CIKTI", "check_bootstrap_units.py"),
                    cikti)
        shutil.copy(os.path.join(ROOT, "_calisma", "bootstrap_units.conf"),
                    os.path.join(root, "_calisma", "bootstrap_units.conf"))
        home = os.path.join(root, "home")
        os.makedirs(os.path.join(home, ".local", "bin"))
        stub = os.path.join(home, ".local", "bin", "python3")
        with open(stub, "w") as f:
            f.write("#!/bin/sh\nexec %s \"$@\"\n" % sys.executable)
        os.chmod(stub, 0o755)
        r = _run(["bash", os.path.join(root, "_calisma", "dev_bootstrap.sh"), "--validate"],
                 timeout=120, env=dict(os.environ, PATH="/bin", HOME=home))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASS", r.stderr, r.stdout + r.stderr)


@unittest.skipUnless(os.path.isfile(VENV_PY), "venv_z3 kurulu değil")
class TestPinParity(unittest.TestCase):
    def test_venv_pins_match_matrix(self):
        r = _run([VENV_PY, "-m", "pip", "freeze"])
        frozen = set(r.stdout.splitlines())
        for pin in PINS:
            self.assertIn(pin, frozen, "pin eksik: " + pin)


if __name__ == "__main__":
    unittest.main()
