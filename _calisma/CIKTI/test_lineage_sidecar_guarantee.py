#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_lineage_sidecar_guarantee.py — §7.1 anti-cascade regresyon kapısı.

Kök neden: lineage_findings.json yalnızca --check-lineage koşulduğunda
yazılıyordu; check koşmadıysa/script yarıda kaldıysa dosya eksik kalıyor,
verify job'unun upload adımı (if-no-files-found) + reports/reproducibility
job'larına cascade FAIL bulaşıyordu.

Düzeltme (kök): verify_delivery.write_lineage_sidecar() --lineage-out'u HER
ZAMAN yazar — check koşmadıysa dürüst {"ok": false, ...} kaydı (yanlış PASS
yok, eksik dosya yok). Ayrıca verify.yml'deki "Guarantee summary sidecars
exist" adımı diğer üç sidecar (k0/klayers/budget) için placeholder üretir.

Bu test iki sözleşmeyi sabitler:
1. write_lineage_sidecar: report=None → dosya YAZILIR + ok:false (koşmadı).
2. Tüketici uyumu: placeholder {"ok": false, "placeholder": true} biçimi
   run_summary_lineage.status() tarafından FAIL (çökme değil) olarak okunur.
"""
import json
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery as vd  # noqa: E402
import run_summary_lineage as rsl  # noqa: E402


class WriteLineageSidecarTest(unittest.TestCase):
    def test_writes_when_report_none(self):
        """--check-lineage koşulmadıysa bile sidecar YAZILIR (ok:false)."""
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "lineage_findings.json"
            ok, detail = vd.write_lineage_sidecar(str(out), None)
            self.assertTrue(ok, detail)
            self.assertTrue(out.is_file())
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(data["ok"])
            self.assertEqual(data["detail"], "check_lineage koşulmadı")
            self.assertEqual(data["generations"], [])

    def test_writes_given_report(self):
        report = {"ok": True, "detail": "x", "count": 2,
                  "generations": [{"gen": "current", "status": "PASS"}]}
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "lineage_findings.json"
            ok, _ = vd.write_lineage_sidecar(str(out), report)
            self.assertTrue(ok)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(data["ok"])
            self.assertEqual(len(data["generations"]), 1)

    def test_unwritable_path_reports_failure(self):
        with tempfile.TemporaryDirectory() as td:
            bad = pathlib.Path(td) / "nope" / "sub" / "x.json"  # eksik dizin
            ok, detail = vd.write_lineage_sidecar(str(bad), None)
            self.assertFalse(ok)
            self.assertIn("yazılamadı", detail)


class PlaceholderConsumerCompatTest(unittest.TestCase):
    """verify.yml 'Guarantee summary sidecars exist' placeholder'ı tüketici
    tarafından çökmeden FAIL olarak okunmalı (MISSING yerine)."""

    def test_placeholder_reads_as_fail(self):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "lineage_findings.json"
            p.write_text(json.dumps(
                {"ok": False, "error": "verify run üretmedi "
                                        "(anti-cascade placeholder)",
                 "placeholder": True}), encoding="utf-8")
            self.assertEqual(rsl.status(str(p)), "FAIL")

    def test_placeholder_renders_without_crash(self):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "lineage_findings.json"
            p.write_text(json.dumps(
                {"ok": False, "error": "x", "placeholder": True,
                 "generations": []}), encoding="utf-8")
            import io
            buf = io.StringIO()
            rsl.render(buf, str(p))
            self.assertIn("doğrulama başarısız", buf.getvalue())

    def test_missing_file_still_missing(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(rsl.status(str(pathlib.Path(td) / "yok.json")),
                             "MISSING")


if __name__ == "__main__":
    unittest.main()