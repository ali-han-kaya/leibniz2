#!/usr/bin/env python3
"""test_validate_config_schema.py — validate_config_schema.py regresyon kapısı.

Exit sözleşmesi: 0 = geçerli, 1 = şema ihlali / JSON parse hatası (bloke),
2 = ortam hatası (jsonschema yok, şema/konfig yok, şema bozuk).

jsonschema kütüphanesi gerektirir (CI'da `pip install jsonschema`); yerelde
yoksa doğrulama yolu testleri SKIP edilir (ortam yolu testleri her zaman
çalışır — onlar jsonschema'dan ÖNCE döner). stdlib unittest.
"""
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import validate_config_schema as vcs  # noqa: E402

try:
    import jsonschema  # noqa: F401
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

REAL_SCHEMA = os.path.join(CIKTI, "verify_delivery.config.schema.json")


def _run(argv):
    """vcs.main()'i argv ile çağır; (exit, stdout) döner.

    Hata mesajları stderr'e yazılır — çıktı, stdout + stderr birleşimidir.
    """
    buf = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        saved = sys.argv
        sys.argv = ["validate_config_schema.py"] + argv
        try:
            code = vcs.main()
        finally:
            sys.argv = saved
    return code, buf.getvalue() + err.getvalue()


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


@unittest.skipIf(not HAS_JSONSCHEMA, "jsonschema kurulu değil (pip install jsonschema)")
class TestSchemaValidation(unittest.TestCase):
    """Doğrulama yolu — yalnızca jsonschema varsa çalışır."""
    def test_valid_config_exit_0(self):
        # Gerçek şema + repo'nun gerçek config'i → geçerli.
        code, _ = _run([REAL_SCHEMA,
                        os.path.join(CIKTI, "verify_delivery.config.json")])
        self.assertEqual(code, 0)

    def test_schema_violation_exit_1(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            _write_json(bad, {"budget_usd": "otuz",  # sayı olmalı
                              "expected_pages": -5})
            code, out = _run([REAL_SCHEMA, bad])
        self.assertEqual(code, 1)
        self.assertIn("şema doğrulaması başarısız", out)

    def test_config_not_json_exit_1(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("{not json")
            code, out = _run([REAL_SCHEMA, bad])
        self.assertEqual(code, 1)
        self.assertIn("geçerli JSON değil", out)


@unittest.skipIf(not HAS_JSONSCHEMA, "jsonschema kurulu değil (pip install jsonschema)")
class TestEnvErrors(unittest.TestCase):
    """Ortam hataları — jsonschema yokken main() ilk adımda exit 2 döner;
    mesaj sözleşmesi yalnızca jsonschema VAR iken anlamlıdır."""

    def test_schema_missing_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = _run([os.path.join(d, "yok.schema.json"),
                              os.path.join(d, "yok.json")])
        self.assertEqual(code, 2)
        self.assertIn("şema bulunamadı", out)

    def test_config_missing_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = _run([REAL_SCHEMA, os.path.join(d, "yok.json")])
        self.assertEqual(code, 2)
        self.assertIn("konfig bulunamadı", out)

    def test_invalid_schema_json_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            sp = os.path.join(d, "schema.json")
            with open(sp, "w", encoding="utf-8") as f:
                f.write("{not schema")
            cp = os.path.join(d, "cfg.json")
            _write_json(cp, {})
            code, out = _run([sp, cp])
        self.assertEqual(code, 2)
        self.assertIn("şema geçerli JSON değil", out)


if __name__ == "__main__":
    unittest.main()
