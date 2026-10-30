"""test_bootstrap_units_validate.py — check_bootstrap_units.py fail-closed sözleşmesi.

Sözleşme: bootstrap_units.conf'taki her satır repodaki gerçek bir yol/pakete
çözülmeli. Bu test, doğrulayıcının YAZIM HATALARINDA kırmızıya düştüğünü
sentetik fixture'larla kanıtlar (unit adı, değişken adı, yol, paket adı,
metadata anahtarı, UNITS kapsamı) ve gerçek repoda yeşil kaldığını gösterir.

stdlib-only: venv/node gerekmez.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, HERE)

import check_bootstrap_units as v  # noqa: E402

SCRIPT_TEMPLATE = """#!/bin/bash
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEMO="$ROOT/apps/demo"
PINS=(demo-pkg==1.0.0)
say() {{ printf '%s\\n' "$*"; }}
check_demo() {{
  lock_ok "$DEMO" && (cd "$DEMO" && node -e "require.resolve('demo-pkg')" >/dev/null 2>&1)
}}
provision_demo() {{
  say "apps/demo: npm ci"
  npm ci --prefix "$DEMO"
}}
UNITS=(demo)
"""

CONF_TEMPLATE = """# fixture
demo=ok
demo.install_time_s=3
demo.disk_mb=12
"""

PACKAGE_JSON = """{
  "name": "demo",
  "private": true,
  "dependencies": { "demo-pkg": "^1.0.0" }
}
"""


class Fixture:
    """Geçici bir repo kökü: _calisma/{conf,dev_bootstrap.sh} + apps/demo."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="bootstrap-units-")
        self.calisma = os.path.join(self.root, "_calisma")
        self.demo = os.path.join(self.root, "apps", "demo")
        os.makedirs(self.calisma)
        os.makedirs(self.demo)
        self.conf = os.path.join(self.calisma, "bootstrap_units.conf")
        self.script = os.path.join(self.calisma, "dev_bootstrap.sh")
        self.write_package(self.demo, PACKAGE_JSON)
        self.write_conf(CONF_TEMPLATE)
        self.write_script(SCRIPT_TEMPLATE)

    def write_conf(self, text):
        with open(self.conf, "w", encoding="utf-8") as f:
            f.write(text)

    def write_script(self, text):
        with open(self.script, "w", encoding="utf-8") as f:
            f.write(text)

    @staticmethod
    def write_package(dirpath, text):
        os.makedirs(dirpath, exist_ok=True)
        with open(os.path.join(dirpath, "package.json"), "w", encoding="utf-8") as f:
            f.write(text)

    def validate(self):
        return v.validate(self.root, self.conf, self.script)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class TestFailClosedOnTypos(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.cleanup()

    def assertFailsWith(self, marker):
        errors, _ = self.fx.validate()
        self.assertTrue(errors, "yazım hatası sessizce geçti: %s" % marker)
        joined = "\n".join(errors)
        self.assertIn(marker, joined, "beklenen ihlal yok (%s):\n%s" % (marker, joined))

    def test_baseline_fixture_passes(self):
        errors, info = self.fx.validate()
        self.assertEqual(errors, [], "temiz fixture kırmızı: %s" % errors)
        self.assertTrue(info)

    def test_unit_name_typo_fails(self):
        # conf'ta 'demo' yerine 'demoo' — script'te check_demoo yok
        self.fx.write_conf(CONF_TEMPLATE.replace("demo=ok", "demoo=ok"))
        self.assertFailsWith("A1")

    def test_missing_provision_function_fails(self):
        self.fx.write_script(SCRIPT_TEMPLATE.replace("provision_demo() {", "provision_demox() {"))
        self.assertFailsWith("A2")

    def test_undefined_variable_typo_fails(self):
        self.fx.write_script(SCRIPT_TEMPLATE.replace('lock_ok "$DEMO"', 'lock_ok "$DEMOO"'))
        self.assertFailsWith("A3")

    def test_path_typo_fails(self):
        self.fx.write_script(SCRIPT_TEMPLATE.replace('DEMO="$ROOT/apps/demo"', 'DEMO="$ROOT/apps/demoo"'))
        self.assertFailsWith("A5")

    def test_package_name_typo_fails(self):
        self.fx.write_script(
            SCRIPT_TEMPLATE.replace("require.resolve('demo-pkg')", "require.resolve('demo-pkgx')")
        )
        self.assertFailsWith("A5")

    def test_unknown_metadata_key_fails(self):
        self.fx.write_conf(CONF_TEMPLATE.replace("demo.install_time_s=3", "demo.install_times=3"))
        self.assertFailsWith("A7")

    def test_non_integer_metadata_fails(self):
        self.fx.write_conf(CONF_TEMPLATE.replace("demo.disk_mb=12", "demo.disk_mb=12x"))
        self.assertFailsWith("A7")

    def test_units_drift_fails(self):
        self.fx.write_script(SCRIPT_TEMPLATE.replace("UNITS=(demo)", "UNITS=(demo ghost)"))
        self.assertFailsWith("A8")

    def test_unparsable_conf_line_fails(self):
        self.fx.write_conf(CONF_TEMPLATE + "this line is not a row\n")
        self.assertFailsWith("cozulemeyen-satir")


class TestCliModes(unittest.TestCase):
    def test_json_stdout_is_single_document(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            rc = v.main(["--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["errors"], [])

    def test_human_mode_fails_closed(self):
        fx = Fixture()
        try:
            fx.write_conf(CONF_TEMPLATE.replace("demo=ok", "demoo=ok"))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = v.main(["--root", fx.root, "--conf", fx.conf, "--script", fx.script])
            self.assertEqual(rc, 1, "yazım hatası rc=1 döndürmeli")
            self.assertIn("FAIL", err.getvalue())
            self.assertEqual(out.getvalue(), "", "insan modunda stdout boş olmalı")
        finally:
            fx.cleanup()


class TestRealRepo(unittest.TestCase):
    def test_real_bootstrap_units_conf_resolves(self):
        errors, _ = v.validate(
            ROOT,
            os.path.join(ROOT, "_calisma", "bootstrap_units.conf"),
            os.path.join(ROOT, "_calisma", "dev_bootstrap.sh"),
        )
        self.assertEqual(errors, [], "gerçek conf çözümlenemedi: %s" % errors)


if __name__ == "__main__":
    unittest.main()
