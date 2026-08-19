#!/usr/bin/env python3
"""test_consolidate_summary.py — consolidate_summary.py regresyon kapısı.

main() tek sink'te pre-commit + K0 + bütçe + soy hattı + K katmanları
bölümlerini SIRAYLA üretir; her bölümün render'ı ilgili run_summary_*.py
modülündedir. Test, 5 bölümün de sırayla göründüğünü ve eksik sidecar
durumunda advisory (exit 0) davrandığını doğrular.
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

import consolidate_summary as cs  # noqa: E402


class TestConsolidateSummary(unittest.TestCase):
    def setUp(self):
        # CI'da GITHUB_STEP_SUMMARY set olduğunda summary_sink() dosyaya
        # yazar; bu testler stdout çıktısını doğrular — env'i temizle.
        self._saved = os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["GITHUB_STEP_SUMMARY"] = self._saved

    def _run(self, paths):
        buf = io.StringIO()
        argv = []
        for key, p in paths.items():
            argv += [f"--{key}", str(p)]
        with contextlib.redirect_stdout(buf):
            code = cs.main(argv)
        return code, buf.getvalue()

    def _sidecars(self, d):
        d = pathlib.Path(d)
        (d / "logs").mkdir(parents=True, exist_ok=True)
        (d / "logs" / "PRECOMMIT_RAPORU.md").write_text(
            "- **Sonuç:** 5/5 Passed\n", encoding="utf-8")
        (d / "k0_findings.json").write_text(
            json.dumps({"count": 0, "findings": []}), encoding="utf-8")
        (d / "budget_verify.json").write_text(
            json.dumps({"limit": 30.0, "estimated_usd": 1.08,
                        "tokens_est": 175990, "verdict": "OK",
                        "method": "both"}), encoding="utf-8")
        (d / "lineage_findings.json").write_text(
            json.dumps({"ok": True, "count": 1, "generations": [
                {"gen": "current", "note": "V5m", "hash": "a" * 64,
                 "commit": None, "status": "PASS (canlı dosya ile aynı)"}]}),
            encoding="utf-8")
        layers = {f"K{n}": {"label": "X", "status": "PASS", "ran": True,
                            "findings": []} for n in range(1, 11)}
        (d / "klayers.json").write_text(
            json.dumps({"verdict": "PASS", "counts": {"P0": 0, "P1": 0},
                        "layers": layers}), encoding="utf-8")
        return {
            "precommit": d / "logs" / "PRECOMMIT_RAPORU.md",
            "k0": d / "k0_findings.json",
            "budget": d / "budget_verify.json",
            "lineage": d / "lineage_findings.json",
            "klayers": d / "klayers.json",
        }

    def test_all_sections_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            code, out = self._run(paths)
        self.assertEqual(code, 0)
        # Durum panosu en üstte, tek satırda, üç ✅ ile.
        self.assertTrue(
            out.startswith("## 📊 Durum panosu: Pre-commit ✅ · K0 ✅ · Bütçe ✅\n"),
            repr(out[:80]))
        headers = [
            "## ✅ Pre-commit: bulgu yok",
            "## ✅ K0 bayat zip: temiz",
            "## ✅ Bütçe kalkanı: limit içinde",
            "## ✅ Soy hattı (zip_lineage.json): 1 nesil doğrulandı",
            "## ✅ K1 X: PASS",
        ]
        last = -1
        for h in headers:
            self.assertIn(h, out)
            pos = out.index(h)
            self.assertGreater(pos, last, f"sıra bozuk: {h}")
            last = pos

    def test_missing_sidecars_advisory(self):
        with tempfile.TemporaryDirectory() as d:
            dd = pathlib.Path(d)
            paths = {k: dd / f"{k}.json" for k in
                     ("k0", "budget", "lineage", "klayers")}
            paths["precommit"] = dd / "logs" / "PRECOMMIT_RAPORU.md"
            code, out = self._run(paths)
        self.assertEqual(code, 0)
        # Panoda eksik sidecar ⚠️ olarak görünür (tek satır korunur).
        self.assertTrue(out.startswith(
            "## 📊 Durum panosu: Pre-commit ⚠️ · K0 ⚠️ · Bütçe ⚠️\n"),
            repr(out[:80]))
        self.assertIn("Pre-commit: rapor bulunamadı", out)
        self.assertIn("K0 bayat zip: sidecar bulunamadı", out)
        self.assertIn("Bütçe kalkanı: sidecar bulunamadı", out)
        self.assertIn("Soy hattı: sidecar bulunamadı", out)
        self.assertIn("K katmanları: sidecar bulunamadı", out)

    def test_dashboard_fail_states(self):
        with tempfile.TemporaryDirectory() as d:
            dd = pathlib.Path(d)
            (dd / "logs").mkdir(parents=True, exist_ok=True)
            (dd / "logs" / "PRECOMMIT_RAPORU.md").write_text(
                "| P1 | bir bulgu |\n- **Sonuç:** 4/5 Passed\n",
                encoding="utf-8")
            (dd / "k0_findings.json").write_text(
                json.dumps({"count": 1, "findings": [
                    {"rel": "x.zip", "sha256": "b" * 64}]}),
                encoding="utf-8")
            (dd / "budget_verify.json").write_text(
                json.dumps({"limit": 5.0, "estimated_usd": 7.5,
                            "verdict": "FAIL"}), encoding="utf-8")
            (dd / "lineage_findings.json").write_text(
                json.dumps({"ok": True, "count": 0, "generations": []}),
                encoding="utf-8")
            (dd / "klayers.json").write_text(
                json.dumps({"verdict": "PASS", "counts": {"P0": 0, "P1": 0},
                            "layers": {}}), encoding="utf-8")
            paths = {
                "precommit": dd / "logs" / "PRECOMMIT_RAPORU.md",
                "k0": dd / "k0_findings.json",
                "budget": dd / "budget_verify.json",
                "lineage": dd / "lineage_findings.json",
                "klayers": dd / "klayers.json",
            }
            code, out = self._run(paths)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith(
            "## 📊 Durum panosu: Pre-commit 🔴 · K0 🔴 · Bütçe 🔴\n"),
            repr(out[:80]))


if __name__ == "__main__":
    unittest.main()
