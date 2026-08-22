#!/usr/bin/env python3
"""test_run_summary_precommit.py — run_summary_precommit.py (rapor ayrıştırma)
regresyon kapısı.

PRECOMMIT_RAPORU.json sidecar'ından P0/P1 bulguları + hook durumları +
sonuç ayrıştırma, durum-panosu özeti ve render çıktısını kapsar.
JSON tek kaynaktır; .md fallback kaldırıldı. stdlib unittest — ek bağımlılık yok.
"""
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import run_summary_precommit as pc  # noqa: E402

JSON_CLEAN = {
    "generated_at": "2026-08-20T12:00:00Z",
    "exit_code": 0,
    "verdict": "PASS",
    "role": "advisory",
    "hooks": [{"name": "Verify Stoic-Hume V5 delivery (fail-closed)",
                "status": "Passed"},
               {"name": "Plist gate unit tests (exit 0/1/2)",
                "status": "Passed"}],
    "findings": [],
    "counts": {"hooks": 2, "passed": 2, "failed": 0, "p0": 0, "p1": 0},
}

JSON_FINDINGS = {
    "generated_at": "2026-08-20T12:00:00Z",
    "exit_code": 1,
    "verdict": "FAIL",
    "role": "advisory",
    "hooks": [{"name": "Verify Stoic-Hume V5 delivery (fail-closed)",
                "status": "Passed"},
               {"name": "Plist gate unit tests (exit 0/1/2)",
                "status": "Failed"}],
    "findings": [{"priority": "P1",
                   "message": "Plist gate testi başarısız (test_plist_gate_exit)"},
                  {"priority": "P1",
                   "message": "K0 taraması bulgu üretti"}],
    "counts": {"hooks": 2, "passed": 1, "failed": 1, "p0": 0, "p1": 2},
}


def _write_json(d, data):
    """PRECOMMIT_RAPORU.json oluştur ve .md yolunu döndür (.md → .json dönüşümü test etmek için)."""
    p = os.path.join(d, "PRECOMMIT_RAPORU.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return os.path.join(d, "PRECOMMIT_RAPORU.md")  # .md yolu ver, _load() .json'a çevirsin


class TestLoad(unittest.TestCase):
    def test_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(pc._load(os.path.join(d, "yok.json")))

    def test_loads_json_when_available(self):
        """JSON varsa JSON'dan yükle."""
        with tempfile.TemporaryDirectory() as d:
            p = _write_json(d, JSON_FINDINGS)
            findings, hooks, verdict = pc._load(p)
        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[0][0], "P1")
        self.assertIn("Plist gate", findings[0][1])
        self.assertEqual(len(hooks), 2)
        self.assertIn("FAIL", verdict)

    def test_loads_clean_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_json(d, JSON_CLEAN)
            findings, hooks, verdict = pc._load(p)
        self.assertEqual(findings, [])
        self.assertEqual(verdict, "PASS")

    def test_no_json_returns_none(self):
        """JSON yoksa None döndür (.md fallback yok)."""
        with tempfile.TemporaryDirectory() as d:
            # Sadece .md oluştur, JSON yok
            md = os.path.join(d, "PRECOMMIT_RAPORU.md")
            with open(md, "w") as f:
                f.write("# rapor\n- **Sonuç:** PASS\n")
            result = pc._load(md)
        self.assertIsNone(result)

    def test_corrupt_json_returns_none(self):
        """Bozuk JSON → None (fallback yok)."""
        with tempfile.TemporaryDirectory() as d:
            jp = os.path.join(d, "PRECOMMIT_RAPORU.json")
            with open(jp, "w") as f:
                f.write("{bad json}")
            result = pc._load(jp)
        self.assertIsNone(result)


class TestStatus(unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(pc.status(os.path.join(d, "yok.json")), "MISSING")

    def test_pass_from_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_json(d, JSON_CLEAN)
            self.assertEqual(pc.status(p), "PASS")

    def test_fail_from_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write_json(d, JSON_FINDINGS)
            self.assertEqual(pc.status(p), "FAIL")


class TestRender(unittest.TestCase):
    def test_clean_from_json(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            pc.render(buf, _write_json(d, JSON_CLEAN))
        out = buf.getvalue()
        self.assertIn("bulgu yok", out)
        self.assertIn("Sonuç: PASS", out)

    def test_findings_from_json(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            pc.render(buf, _write_json(d, JSON_FINDINGS))
        out = buf.getvalue()
        self.assertIn("Pre-commit bulguları: 2 bulgu", out)
        self.assertIn("**P1**: Plist gate", out)
        self.assertIn("Advisory", out)

    def test_missing_advisory(self):
        buf = io.StringIO()
        pc.render(buf, "/yok/PRECOMMIT_RAPORU.json")
        self.assertIn("rapor bulunamadı", buf.getvalue())


class TestSchemaValidation(unittest.TestCase):
    """PRECOMMIT_RAPORU.json schema doğrulaması."""

    def test_valid_json_passes_schema(self):
        """Geçerli JSON schema'dan geçmeli."""
        with tempfile.TemporaryDirectory() as d:
            p = _write_json(d, JSON_CLEAN)
            findings, hooks, verdict = pc._load(p)
        self.assertEqual(findings, [])
        self.assertEqual(verdict, "PASS")

    def test_invalid_json_returns_none(self):
        """Geçersiz JSON → None (fallback yok)."""
        with tempfile.TemporaryDirectory() as d:
            jp = os.path.join(d, "PRECOMMIT_RAPORU.json")
            with open(jp, "w") as f:
                f.write("{bad json}")
            result = pc._load(jp)
        self.assertIsNone(result)

    def test_schema_rejects_missing_required_fields(self):
        """Eksik zorunlu alanlar schema hatası üretmeli."""
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema kurulu değil (CI'da pip install edilir)")
        schema = pc._load_schema()
        if schema is None:
            self.skipTest("schema dosyası yok")
        # verdict alanı eksik
        bad = {"generated_at": "2026-01-01T00:00:00Z", "exit_code": 0,
               "role": "advisory", "hooks": [], "findings": [],
               "counts": {"hooks": 0, "passed": 0, "failed": 0,
                          "p0": 0, "p1": 0}}
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)

    def test_schema_rejects_bad_hook_status(self):
        """Geçersiz hook status alanı schema hatası üretmeli."""
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema kurulu değil (CI'da pip install edilir)")
        schema = pc._load_schema()
        if schema is None:
            self.skipTest("schema dosyası yok")
        bad = {"generated_at": "2026-01-01T00:00:00Z", "exit_code": 0,
               "verdict": "PASS", "role": "advisory",
               "hooks": [{"name": "test", "status": "Invalid"}],
               "findings": [],
               "counts": {"hooks": 1, "passed": 0, "failed": 1,
                          "p0": 0, "p1": 0}}
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)


if __name__ == "__main__":
    unittest.main()
