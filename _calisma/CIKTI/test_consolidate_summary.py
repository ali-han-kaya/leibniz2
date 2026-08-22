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
        (d / "logs" / "PRECOMMIT_RAPORU.json").write_text(
            json.dumps({"generated_at": "2026-08-20T12:00:00Z",
                        "exit_code": 0, "verdict": "PASS", "role": "advisory",
                        "hooks": [{"name": "hook1", "status": "Passed"},
                                   {"name": "hook2", "status": "Passed"}],
                        "findings": [],
                        "counts": {"hooks": 5, "passed": 5, "failed": 0,
                                   "p0": 0, "p1": 0}}), encoding="utf-8")
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
            "precommit": d / "logs" / "PRECOMMIT_RAPORU.json",
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
        # Durum panosu en üstte, tek satırda, beş ✅ ile.
        self.assertTrue(
            out.startswith("## 📊 Durum panosu: Pre-commit ✅ · K0 ✅ · Bütçe ✅ · Soy hattı ✅ · K katmanları ✅\n"),
            repr(out[:120]))
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
            paths["precommit"] = dd / "logs" / "PRECOMMIT_RAPORU.json"
            code, out = self._run(paths)
        self.assertEqual(code, 0)
        # Panoda eksik sidecar ⚠️ olarak görünür (tek satır korunur).
        self.assertTrue(out.startswith(
            "## 📊 Durum panosu: Pre-commit ⚠️ · K0 ⚠️ · Bütçe ⚠️ · Soy hattı ⚠️ · K katmanları ⚠️\n"),
            repr(out[:120]))
        self.assertIn("Pre-commit: rapor bulunamadı", out)
        self.assertIn("K0 bayat zip: sidecar bulunamadı", out)
        self.assertIn("Bütçe kalkanı: sidecar bulunamadı", out)
        self.assertIn("Soy hattı: sidecar bulunamadı", out)

    def test_github_step_summary_file_sink_fallback(self):
        # GITHUB_STEP_SUMMARY env'i set iken main() çıktıyı STDOUT'a değil
        # o dosyaya yazar (CI gerçek davranışı); env yoksa stdout'a düşer
        # (yerel/fallback — yukarıdaki _run testleri bunu kapsar).
        with tempfile.TemporaryDirectory() as d:
            dd = pathlib.Path(d)
            paths = self._sidecars(d)
            summary_file = dd / "step_summary.md"
            os.environ["GITHUB_STEP_SUMMARY"] = str(summary_file)
            try:
                buf = io.StringIO()
                argv = []
                for key, p in paths.items():
                    argv += [f"--{key}", str(p)]
                with contextlib.redirect_stdout(buf):
                    code = cs.main(argv)
            finally:
                os.environ.pop("GITHUB_STEP_SUMMARY", None)
            self.assertEqual(code, 0)
            # stdout'a YAZILMADI (yalnızca sonuç satırı), asıl içerik dosyada.
            self.assertNotIn("Durum panosu", buf.getvalue())
            file_txt = summary_file.read_text(encoding="utf-8")
            self.assertTrue(file_txt.startswith(
                "## 📊 Durum panosu: Pre-commit ✅ · K0 ✅ · Bütçe ✅ · Soy hattı ✅ · K katmanları ✅\n"),
                repr(file_txt[:120]))
            for h in ("## ✅ Pre-commit: bulgu yok",
                      "## ✅ K0 bayat zip: temiz",
                      "## ✅ Bütçe kalkanı: limit içinde"):
                self.assertIn(h, file_txt)

    def test_dashboard_fail_states(self):
        with tempfile.TemporaryDirectory() as d:
            dd = pathlib.Path(d)
            (dd / "logs").mkdir(parents=True, exist_ok=True)
            (dd / "logs" / "PRECOMMIT_RAPORU.json").write_text(
                json.dumps({"generated_at": "2026-08-20T12:00:00Z",
                            "exit_code": 1, "verdict": "FAIL", "role": "advisory",
                            "hooks": [{"name": "hook1", "status": "Passed"},
                                       {"name": "hook2", "status": "Failed"}],
                            "findings": [{"priority": "P1",
                                           "message": "bir bulgu"}],
                            "counts": {"hooks": 5, "passed": 4, "failed": 1,
                                       "p0": 0, "p1": 1}}),
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
                "precommit": dd / "logs" / "PRECOMMIT_RAPORU.json",
                "k0": dd / "k0_findings.json",
                "budget": dd / "budget_verify.json",
                "lineage": dd / "lineage_findings.json",
                "klayers": dd / "klayers.json",
            }
            code, out = self._run(paths)
        self.assertEqual(code, 0)
        self.assertIn("Durum panosu", out)
        self.assertIn("Pre-commit 🔴", out)
        self.assertIn("K0 🔴", out)
        self.assertIn("Bütçe 🔴", out)
        self.assertIn("Soy hattı ✅", out)
        self.assertIn("K katmanları ✅", out)


class TestDashboardOnlyAndSkip(unittest.TestCase):
    """--dashboard-only ve --skip-dashboard flag davranışları."""

    def setUp(self):
        self._saved = os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["GITHUB_STEP_SUMMARY"] = self._saved

    def _run(self, argv):
        buf = io.StringIO()
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
                        "tokens_est": 175990, "verdict": "OK"}),
            encoding="utf-8")
        (d / "lineage_findings.json").write_text(
            json.dumps({"ok": True, "count": 1, "generations": [
                {"gen": "current", "note": "V5m", "hash": "a" * 64,
                 "commit": None, "status": "PASS"}]}),
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

    def test_dashboard_only_writes_only_dashboard(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            argv = []
            for key, p in paths.items():
                argv += [f"--{key}", str(p)]
            argv.append("--dashboard-only")
            code, out = self._run(argv)
        self.assertEqual(code, 0)
        # Yalnızca dashboard satırı yazılır (detay bölüm yok).
        self.assertTrue(out.startswith("## 📊 Durum panosu:"), repr(out[:80]))
        self.assertNotIn("Pre-commit bulguları", out)
        self.assertNotIn("K0 bayat zip", out)
        self.assertNotIn("Bütçe kalkanı", out)
        self.assertNotIn("Soy hattı (zip_lineage", out)
        self.assertNotIn("K1 X", out)

    def test_skip_dashboard_skips_dashboard(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            argv = []
            for key, p in paths.items():
                argv += [f"--{key}", str(p)]
            argv.append("--skip-dashboard")
            code, out = self._run(argv)
        self.assertEqual(code, 0)
        # Dashboard satırı YAZILMAZ (yalnızca detay bölümler).
        self.assertNotIn("Durum panosu", out)
        self.assertIn("Pre-commit:", out)
        self.assertIn("K0", out)
        self.assertIn("Bütçe", out)
        self.assertIn("Soy hattı", out)
        self.assertIn("K1 X", out)

    def test_dashboard_only_then_skip_creates_correct_flow(self):
        # CI akışı: önce --dashboard-only, sonra --skip-dashboard.
        # İkisi birlikte tam çıktıyı üretmeli (dashboard üstte, detay altta).
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            argv = []
            for key, p in paths.items():
                argv += [f"--{key}", str(p)]

            # Adım 1: dashboard-only
            code1, out1 = self._run(argv + ["--dashboard-only"])
            # Adım 2: skip-dashboard
            code2, out2 = self._run(argv + ["--skip-dashboard"])
        self.assertEqual(code1, 0)
        self.assertEqual(code2, 0)
        # out1 dashboard içerir ama detay içermez.
        self.assertTrue(out1.startswith("## 📊 Durum panosu:"))
        self.assertNotIn("Pre-commit bulguları", out1)
        # out2 dashboard içermez ama detay içerir.
        self.assertNotIn("Durum panosu", out2)
        self.assertIn("Pre-commit:", out2)
        # Birleştirilmiş çıktı: dashboard üstte, detay altta.
        combined = out1 + out2
        dashboard_pos = combined.index("Durum panosu")
        detail_pos = combined.index("Pre-commit:")
        self.assertLess(dashboard_pos, detail_pos)


class TestSectionContentValidation(unittest.TestCase):
    """Soy hattı + K katmanları bölümlerinin SATIR BAZLI içerik doğrulaması.

    Sıra + başlık dışında gerçek satırlar denetlenir: nesil tablosu
    (gen/note/hash-kırpma/ikon), FAIL bulgu mermileri (priority/check/
    issue/evidence), SKIP ve eksik katman satırları, footer notları.
    """

    def setUp(self):
        self._saved = os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["GITHUB_STEP_SUMMARY"] = self._saved

    def _sidecars(self, d):
        d = pathlib.Path(d)
        (d / "logs").mkdir(parents=True, exist_ok=True)
        (d / "logs" / "PRECOMMIT_RAPORU.json").write_text(
            json.dumps({"verdict": "PASS", "hooks": [], "findings": [],
                        "counts": {"p0": 0, "p1": 0}}), encoding="utf-8")
        (d / "k0_findings.json").write_text(
            json.dumps({"count": 0, "findings": []}), encoding="utf-8")
        (d / "budget_verify.json").write_text(
            json.dumps({"limit": 30.0, "estimated_usd": 1.08,
                        "verdict": "OK"}), encoding="utf-8")
        (d / "lineage_findings.json").write_text(json.dumps({
            "ok": True, "count": 3, "generations": [
                {"gen": "g1", "note": "V5m", "hash": "a" * 64,
                 "commit": "abc123",
                 "status": "PASS (canlı dosya ile aynı)"},
                {"gen": "g2", "note": "pre-git kaynak",
                 "hash": "b" * 64, "commit": None,
                 "status": "UNVERIFIED (iCloud)"},
                {"gen": "g3", "note": "bozuk", "hash": "c" * 64,
                 "commit": None, "status": "FAIL — hash uyuşmaz"},
            ]}), encoding="utf-8")
        (d / "klayers.json").write_text(json.dumps({
            "verdict": "FAIL", "counts": {"P0": 1, "P1": 1},
            "layers": {
                "K1": {"label": "Dış zip sidecar", "status": "PASS",
                        "ran": True, "findings": []},
                "K2": {"label": "Klasör checksum", "status": "FAIL",
                        "ran": True, "findings": [
                            {"priority": "P0", "check": "K2-HASH",
                             "issue": "checksum uyuşmaz",
                             "evidence": "a1b2"},
                            {"priority": "P1", "check": "K2-SIDECAR",
                             "issue": "sidecar yok", "evidence": ""}]},
                "K3": {"label": "İç zip sidecar", "status": "SKIP",
                        "ran": False, "findings": []},
            }}), encoding="utf-8")
        return {
            "precommit": d / "logs" / "PRECOMMIT_RAPORU.json",
            "k0": d / "k0_findings.json",
            "budget": d / "budget_verify.json",
            "lineage": d / "lineage_findings.json",
            "klayers": d / "klayers.json",
        }

    def _run(self, paths):
        buf = io.StringIO()
        argv = []
        for key, p in paths.items():
            argv += [f"--{key}", str(p)]
        with contextlib.redirect_stdout(buf):
            code = cs.main(argv)
        return code, buf.getvalue()

    def test_lineage_rows_content(self):
        """Nesil tablosu satırları: gen/note/hash-16 kırpma + durum ikonu."""
        with tempfile.TemporaryDirectory() as d:
            code, out = self._run(self._sidecars(d))
        self.assertEqual(code, 0)
        self.assertIn("## ✅ Soy hattı (zip_lineage.json): 3 nesil doğrulandı", out)
        self.assertIn("| NESİL | NOTE | HASH | DURUM |", out)
        # Satır bazlı: hash 16 karaktere kırpılır, ikon duruma göre.
        self.assertIn("| g1 | V5m | `aaaaaaaaaaaaaaaa…` | ✅ PASS (canlı dosya ile aynı) |", out)
        self.assertIn("| g2 | pre-git kaynak | `bbbbbbbbbbbbbbbb…` | ℹ️ UNVERIFIED (iCloud) |", out)
        self.assertIn("| g3 | bozuk | `cccccccccccccccc…` | 🔴 FAIL — hash uyuşmaz |", out)
        # Kırpılmamış hash asla satırda görünmemeli (64 char).
        self.assertNotIn("a" * 17, out)
        # Footer: PASS dalı.
        self.assertIn(
            "> Fail-closed: tüm commit'li nesiller `git show` ile, "
            "`current` nesil canlı dosya ile doğrulandı.", out)

    def test_lineage_fail_state_rows(self):
        """ok=False: başlık 🔴 + FAIL footer, tablo yine satır satır."""
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            data = json.loads(pathlib.Path(paths["lineage"]).read_text(
                encoding="utf-8"))
            data["ok"] = False
            pathlib.Path(paths["lineage"]).write_text(
                json.dumps(data), encoding="utf-8")
            code, out = self._run(paths)
        self.assertEqual(code, 0)
        self.assertIn("## 🔴 Soy hattı (zip_lineage.json): doğrulama başarısız (3 nesil)", out)
        self.assertIn("| g1 | V5m | `aaaaaaaaaaaaaaaa…` | ✅ PASS (canlı dosya ile aynı) |", out)
        self.assertIn(
            "> Fail-closed: P0/P1 bulgusu olarak işaretlendi; "
            "kanonik hash/soy hattı sapması var.", out)

    def test_klayers_pass_fail_skip_missing_rows(self):
        """K katmanları: PASS/FAIL(+bulgu mermileri)/SKIP/eksik satırları."""
        with tempfile.TemporaryDirectory() as d:
            code, out = self._run(self._sidecars(d))
        self.assertEqual(code, 0)
        self.assertIn("## ✅ K1 Dış zip sidecar: PASS", out)
        self.assertIn("## 🔴 K2 Klasör checksum: 2 bulgu", out)
        # FAIL bulguları satır bazlı: priority + check + issue (+ evidence).
        self.assertIn("- [P0] K2-HASH: checksum uyuşmaz (a1b2)", out)
        # P1 bulgusunda evidence boş — tam satır eşleşmesi (a1b2) içermediğini kanıtlar.
        self.assertIn("- [P1] K2-SIDECAR: sidecar yok", out)
        self.assertNotIn("- [P1] K2-SIDECAR: sidecar yok (a1b2)", out)
        # SKIP satırı (label ile) ve eksik katman satırı (labelsiz).
        self.assertIn("## ⏭️ K3 İç zip sidecar: bu job'da koşmadı (N/A)", out)
        self.assertIn("## ⏭️ K4: sidecar'da yok", out)
        self.assertIn("## ⏭️ K17: sidecar'da yok", out)

    def test_klayers_rows_in_render_order(self):
        """K katmanı başlıkları RENDER_LAYERS sırasıyla görünmeli (satır bazlı)."""
        with tempfile.TemporaryDirectory() as d:
            code, out = self._run(self._sidecars(d))
        self.assertEqual(code, 0)
        import run_summary_klayers as _kl
        last = -1
        for key in _kl.RENDER_LAYERS:
            marker = f"## ✅ {key} " if key in ("K1",) else \
                (f"## 🔴 {key} " if key == "K2" else
                 (f"## ⏭️ {key} " if key == "K3" else f"## ⏭️ {key}:"))
            pos = out.index(marker)
            self.assertGreater(pos, last, f"katman sırası bozuk: {key}")
            last = pos


if __name__ == "__main__":
    unittest.main()
