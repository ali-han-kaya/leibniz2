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
        # K13 ayrı-step sidecar (advisory; ok=true → PASS).
        (d / "logs" / "k13_repro_manifest.json").write_text(
            json.dumps({"layer": "K13", "ok": True, "exit": 0,
                        "detail": "[K13] repro manifest: PASS — senaryolar: "
                                   "eksik-dosya PASS, bozuk-hash PASS",
                        "scenarios": [{"name": "eksik-dosya", "status": "PASS"},
                                       {"name": "bozuk-hash", "status": "PASS"}]}),
            encoding="utf-8")
        return {
            "precommit": d / "logs" / "PRECOMMIT_RAPORU.json",
            "k0": d / "k0_findings.json",
            "budget": d / "budget_verify.json",
            "lineage": d / "lineage_findings.json",
            "klayers": d / "klayers.json",
            "k13": d / "logs" / "k13_repro_manifest.json",
        }

    def test_all_sections_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            code, out = self._run(paths)
        self.assertEqual(code, 0)
        # Durum panosu en üstte, tek satırda, altı ✅ ile (K13 ayrı-step dahil).
        self.assertTrue(
            out.startswith("## 📊 Durum panosu: Pre-commit ✅ · K0 ✅ · Bütçe ✅ · Soy hattı ✅ · K katmanları ✅ · K13 ayrı-step ✅\n"),
            repr(out[:160]))
        headers = [
            "## ✅ Pre-commit: bulgu yok",
            "## ✅ K0 bayat zip: temiz",
            "## ✅ Bütçe kalkanı: limit içinde",
            "## ✅ Soy hattı (zip_lineage.json): 1 nesil doğrulandı",
            "## ✅ K1 X: PASS",
            "## ✅ K13 repro-manifest: PASS",
        ]
        last = -1
        for h in headers:
            self.assertIn(h, out)
            pos = out.index(h)
            self.assertGreater(pos, last, f"sıra bozuk: {h}")
            last = pos
        # K13 bölümü negatif senaryo tablosunu da içerir.
        self.assertIn("Negatif senaryolar:", out)
        self.assertIn("`eksik-dosya` :white_check_mark:", out)

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
            "## 📊 Durum panosu: Pre-commit ⚠️ · K0 ⚠️ · Bütçe ⚠️ · Soy hattı ⚠️ · K katmanları ⚠️ · K13 ayrı-step ⚠️\n"),
            repr(out[:160]))
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
                "## 📊 Durum panosu: Pre-commit ✅ · K0 ✅ · Bütçe ✅ · Soy hattı ✅ · K katmanları ✅ · K13 ayrı-step ✅\n"),
                repr(file_txt[:160]))
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


class TestRunSummaryK13(unittest.TestCase):
    """run_summary_k13 — K13 ayrı-step sidecar'ından durum + render."""

    def _write(self, d, ok=True, scenarios=None, exit_code=0):
        d = pathlib.Path(d)
        (d / "logs").mkdir(parents=True, exist_ok=True)
        (d / "logs" / "k13_repro_manifest.json").write_text(
            json.dumps({"layer": "K13", "ok": ok, "exit": exit_code,
                        "detail": "[K13] repro manifest: "
                                   + ("PASS" if ok else "FAIL"),
                        "scenarios": scenarios or []}),
            encoding="utf-8")
        return d / "logs" / "k13_repro_manifest.json"

    def test_status_pass_fail_missing(self):
        import run_summary_k13 as rk13
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, ok=True)
            self.assertEqual(rk13.status(str(p)), "PASS")
            p = self._write(d, ok=False, exit_code=1)
            self.assertEqual(rk13.status(str(p)), "FAIL")
            self.assertEqual(rk13.status(str(d) + "/yok.json"), "MISSING")

    def test_render_pass_with_scenarios(self):
        import run_summary_k13 as rk13
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, ok=True, scenarios=[
                {"name": "eksik-dosya", "status": "PASS"},
                {"name": "bozuk-hash", "status": "PASS"}])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rk13.render(sys.stdout, str(p))
            out = buf.getvalue()
            self.assertIn("## ✅ K13 repro-manifest: PASS", out)
            self.assertIn("exit=0", out)
            self.assertIn("Negatif senaryolar:", out)
            self.assertIn("`eksik-dosya` :white_check_mark:", out)
            self.assertIn("`bozuk-hash` :white_check_mark:", out)

    def test_render_fail_marks_scenario_fail(self):
        import run_summary_k13 as rk13
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, ok=False, exit_code=1, scenarios=[
                {"name": "eksik-dosya", "status": "YAKALANMADI"}])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rk13.render(sys.stdout, str(p))
            out = buf.getvalue()
            self.assertIn("## 🔴 K13 repro-manifest: FAIL", out)
            self.assertIn("`eksik-dosya` :x:", out)

    def test_render_missing_advisory(self):
        import run_summary_k13 as rk13
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rk13.render(sys.stdout, "/yok/k13_repro_manifest.json")
        self.assertIn("## ⚠️ K13 repro-manifest: sidecar bulunamadı",
                      buf.getvalue())


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


class TestPrecommitAndK0Content(unittest.TestCase):
    """Pre-commit + K0 bölümlerinin SATIR BAZLI içerik doğrulaması.

    Sıra + başlık dışında gerçek satırlar denetlenir: hook durum satırları
    (Passed → :white_check_mark:, Failed → :x:, tek `> Hook'lar:` satırında),
    bulgu mermileri (priority + message), K0 bayat-zip bulgu satırları
    (rel + sha256-16 kırpma), fail-closed/clean footer'lar ve eksik sidecar
    advisory notları.
    """

    def setUp(self):
        self._saved = os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["GITHUB_STEP_SUMMARY"] = self._saved

    def _sidecars(self, d, precommit=None, k0=None):
        d = pathlib.Path(d)
        (d / "logs").mkdir(parents=True, exist_ok=True)
        # Varsayılan pre-commit: PASS, hook1 Passed + hook2 Failed (karışık).
        default_pre = {
            "generated_at": "2026-08-20T12:00:00Z", "exit_code": 0,
            "verdict": "PASS", "role": "advisory",
            "hooks": [{"name": "hook1", "status": "Passed"},
                       {"name": "hook2", "status": "Failed"}],
            "findings": [],
            "counts": {"hooks": 5, "passed": 4, "failed": 1,
                       "p0": 0, "p1": 0},
        }
        pre = precommit if precommit is not None else default_pre
        (d / "logs" / "PRECOMMIT_RAPORU.json").write_text(
            json.dumps(pre), encoding="utf-8")
        # Varsayılan K0: 2 bayat zip bulgusu.
        default_k0 = {"count": 2, "findings": [
            {"rel": "dış/ESKI_V4.zip", "sha256": "a" * 64},
            {"rel": "dış/BAYAT.zip", "sha256": "b" * 64},
        ]}
        k = k0 if k0 is not None else default_k0
        (d / "k0_findings.json").write_text(json.dumps(k), encoding="utf-8")
        (d / "budget_verify.json").write_text(
            json.dumps({"limit": 30.0, "estimated_usd": 1.08,
                        "verdict": "OK"}), encoding="utf-8")
        (d / "lineage_findings.json").write_text(json.dumps({
            "ok": True, "count": 0, "generations": []}), encoding="utf-8")
        (d / "klayers.json").write_text(json.dumps({
            "verdict": "PASS", "counts": {"P0": 0, "P1": 0},
            "layers": {}}), encoding="utf-8")
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

    def test_precommit_pass_hooks_rows(self):
        """PASS: hook durumları tek satırda, Passed→✓ Failed→✗ (satır bazlı)."""
        with tempfile.TemporaryDirectory() as d:
            code, out = self._run(self._sidecars(d))
        self.assertEqual(code, 0)
        self.assertIn("## ✅ Pre-commit: bulgu yok (tüm hook'lar geçti)", out)
        self.assertIn("> Sonuç: PASS", out)
        # Karışık durum: hook1 ✓, hook2 ✗ — tek `> Hook'lar:` satırında.
        self.assertIn("> Hook'lar: `hook1` :white_check_mark: | `hook2` :x:", out)
        # Hata durumu yanlış ikonla görünmemeli (hook1 ✗, hook2 ✓ olmamalı).
        self.assertNotIn("`hook1` :x:", out)
        self.assertNotIn("`hook2` :white_check_mark:", out)

    def test_precommit_fail_findings_rows(self):
        """FAIL: bulgu mermileri priority+message, advisory footer, Sonuç: FAIL."""
        pre = {
            "generated_at": "2026-08-20T12:00:00Z", "exit_code": 1,
            "verdict": "FAIL", "role": "advisory",
            "hooks": [{"name": "hook1", "status": "Passed"}],
            "findings": [{"priority": "P1", "message": "check-python3-shell bulgu"},
                          {"priority": "P0", "message": "check-plist-drift başarısız"}],
            "counts": {"hooks": 5, "passed": 4, "failed": 1,
                       "p0": 1, "p1": 1},
        }
        with tempfile.TemporaryDirectory() as d:
            code, out = self._run(self._sidecars(d, precommit=pre))
        self.assertEqual(code, 0)
        self.assertIn("## 🔴 Pre-commit bulguları: 2 bulgu", out)
        # Satır bazlı: `- **PRI**: message` — priority bold + mesaj.
        self.assertIn("- **P1**: check-python3-shell bulgu", out)
        self.assertIn("- **P0**: check-plist-drift başarısız", out)
        self.assertIn("> Sonuç: FAIL", out)
        # Advisory footer.
        self.assertIn("> Advisory — build'i bloke etmez; denetim içindir. "
                      "Detay: `precommit-logs` artifact'ındaki PRECOMMIT_RAPORU.md.", out)

    def test_precommit_missing_sidecar(self):
        """Sidecar yoksa advisory 'rapor bulunamadı' notu (satır bazlı)."""
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            paths["precommit"].unlink()
            code, out = self._run(paths)
        self.assertEqual(code, 0)
        self.assertIn("## 🔍 Pre-commit: rapor bulunamadı", out)
        self.assertIn("> `logs/PRECOMMIT_RAPORU.json` üretilmedi "
                      "(pre-commit kurulumu başarısız?).", out)

    def test_k0_clean_rows(self):
        """K0 temiz: başlık + 'CIKTI dışında zip bulunamadı' notu."""
        k0 = {"count": 0, "findings": []}
        with tempfile.TemporaryDirectory() as d:
            code, out = self._run(self._sidecars(d, k0=k0))
        self.assertEqual(code, 0)
        self.assertIn("## ✅ K0 bayat zip: temiz (bulgu yok)", out)
        self.assertIn("> CIKTI dışında zip bulunamadı.", out)
        # Bulgu satırı olmamalı.
        self.assertNotIn("- `", out)

    def test_k0_findings_rows(self):
        """K0 bayat: bulgu satırları rel + sha256-16 kırpma + fail-closed footer."""
        with tempfile.TemporaryDirectory() as d:
            code, out = self._run(self._sidecars(d))
        self.assertEqual(code, 0)
        self.assertIn("## 🔴 K0 bayat zip: 2 bulgu", out)
        # Satır bazlı: `rel`  (`sha256[0:16]…`) — iki boşluk ayraç.
        self.assertIn("- `dış/ESKI_V4.zip`  (`aaaaaaaaaaaaaaaa…`)", out)
        self.assertIn("- `dış/BAYAT.zip`  (`bbbbbbbbbbbbbbbb…`)", out)
        # Kırpılmamış hash (17+ char) satırda görünmemeli.
        self.assertNotIn("a" * 17, out)
        # Fail-closed footer.
        self.assertIn("> Fail-closed: P1 bulgusu olarak işaretlendi. "
                      "Kanonik kopya yalnızca `_calisma/CIKTI/` altında "
                      "olmalıdır.", out)

    def test_k0_missing_sidecar(self):
        """K0 sidecar yoksa advisory 'sidecar bulunamadı' notu."""
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            paths["k0"].unlink()
            code, out = self._run(paths)
        self.assertEqual(code, 0)
        self.assertIn("## 🔍 K0 bayat zip: sidecar bulunamadı", out)
        self.assertIn("> `verify_delivery.py` `--k0-out` üretmedi "
                      "(verify job'u çalışmadı?).", out)

    def test_precommit_before_k0_in_output(self):
        """Pre-commit bölümü K0'dan önce (render sırası, satır bazlı)."""
        with tempfile.TemporaryDirectory() as d:
            code, out = self._run(self._sidecars(d))
        self.assertEqual(code, 0)
        p = out.index("## ✅ Pre-commit:")
        k = out.index("## 🔴 K0 bayat zip:")
        self.assertLess(p, k)


class TestFileSink(unittest.TestCase):
    """GITHUB_STEP_SUMMARY dosya sink'i — dosyaya yazılmış haliyle satır bazlı.

    stdout testleri çıktıyı doğrular; bu sınıf aynı içeriğin GITHUB_STEP_SUMMARY
    env'i işaret ettiği dosyaya (append) yazıldığını denetler. Kapsam:
    - Dosya içeriği, stdout çıktısıyla birebir aynı (satır bazlı)
    - Append modu: ikinci çalıştırma dosyayı ezmeden EKLER
    - `--dashboard-only` / `--skip-dashboard` modları dosya sink'te de çalışır
    - Dosya sink'te de tüm bölümler sırayla görünür
    """

    def setUp(self):
        self._saved = os.environ.get("GITHUB_STEP_SUMMARY")

    def tearDown(self):
        if self._saved is not None:
            os.environ["GITHUB_STEP_SUMMARY"] = self._saved
        else:
            os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def _run_file(self, paths, summary_file):
        """GITHUB_STEP_SUMMARY=summary_file ile main() koş; dosya içeriğini döndür."""
        os.environ["GITHUB_STEP_SUMMARY"] = str(summary_file)
        buf = io.StringIO()
        argv = []
        for key, p in paths.items():
            argv += [f"--{key}", str(p)]
        with contextlib.redirect_stdout(buf):
            code = cs.main(argv)
        content = summary_file.read_text(encoding="utf-8")
        return code, content

    def _run_stdout(self, paths):
        """Aynı sidecar'larla stdout sink'i koş (karşılaştırma için)."""
        os.environ.pop("GITHUB_STEP_SUMMARY", None)
        buf = io.StringIO()
        argv = []
        for key, p in paths.items():
            argv += [f"--{key}", str(p)]
        with contextlib.redirect_stdout(buf):
            code = cs.main(argv)
        return code, buf.getvalue()

    def _sidecars(self, d):
        """Karışık durum: pre-commit PASS (hook1 ✓ + hook2 ✗) + K0 2 bayat zip."""
        d = pathlib.Path(d)
        (d / "logs").mkdir(parents=True, exist_ok=True)
        (d / "logs" / "PRECOMMIT_RAPORU.json").write_text(
            json.dumps({"generated_at": "2026-08-20T12:00:00Z",
                        "exit_code": 0, "verdict": "PASS", "role": "advisory",
                        "hooks": [{"name": "hook1", "status": "Passed"},
                                   {"name": "hook2", "status": "Failed"}],
                        "findings": [],
                        "counts": {"hooks": 5, "passed": 4, "failed": 1,
                                   "p0": 0, "p1": 0}}), encoding="utf-8")
        (d / "k0_findings.json").write_text(
            json.dumps({"count": 2, "findings": [
                {"rel": "dış/ESKI_V4.zip", "sha256": "a" * 64},
                {"rel": "dış/BAYAT.zip", "sha256": "b" * 64},
            ]}), encoding="utf-8")
        (d / "budget_verify.json").write_text(
            json.dumps({"limit": 30.0, "estimated_usd": 1.08,
                        "verdict": "OK"}), encoding="utf-8")
        (d / "lineage_findings.json").write_text(json.dumps({
            "ok": True, "count": 0, "generations": []}), encoding="utf-8")
        (d / "klayers.json").write_text(json.dumps({
            "verdict": "PASS", "counts": {"P0": 0, "P1": 0},
            "layers": {}}), encoding="utf-8")
        return {
            "precommit": d / "logs" / "PRECOMMIT_RAPORU.json",
            "k0": d / "k0_findings.json",
            "budget": d / "budget_verify.json",
            "lineage": d / "lineage_findings.json",
            "klayers": d / "klayers.json",
        }

    def test_file_sink_matches_stdout(self):
        """Dosya içeriği stdout çıktısıyla birebir aynı (satır bazlı)."""
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            summary_file = pathlib.Path(d) / "summary.md"
            code_f, file_content = self._run_file(paths, summary_file)
            code_s, stdout_content = self._run_stdout(paths)
        self.assertEqual(code_f, code_s)
        # stdout'a ayrıca "Consolidated summary written (full)" print edilir
        # (dosyaya yazılmaz) — karşılaştırmadan önce o satırı çıkar.
        stdout_body = stdout_content.rsplit(
            "\nConsolidated summary written (full)\n", 1)[0]
        # Sink son bölümü "\n\n" ile bitirir; print ekstra "\n" ekler —
        # sondaki yeni satırları eşitle (içerik birebir aynı olmalı).
        self.assertEqual(file_content.rstrip("\n"), stdout_body.rstrip("\n"))
        # Satır bazlı: kritik satırlar dosyada da var.
        self.assertIn("## 📊 Durum panosu: Pre-commit ✅ · K0 🔴 · Bütçe ✅ · Soy hattı ✅ · K katmanları ✅ · K13 ayrı-step ⚠️\n",
                      file_content)
        self.assertIn("> Hook'lar: `hook1` :white_check_mark: | `hook2` :x:\n",
                      file_content)
        self.assertIn("- `dış/ESKI_V4.zip`  (`aaaaaaaaaaaaaaaa…`)\n",
                      file_content)

    def test_file_sink_append_mode(self):
        """İkinci çalıştırma dosyayı ezmez — içeriğe EKLER (append)."""
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            summary_file = pathlib.Path(d) / "summary.md"
            code1, c1 = self._run_file(paths, summary_file)
            code2, c2 = self._run_file(paths, summary_file)
        self.assertEqual(code1, 0)
        self.assertEqual(code2, 0)
        # Append: ikinci içerik birincinin iki katı (dashboard + 5 bölüm × 2).
        self.assertTrue(c2.startswith(c1))
        self.assertEqual(c2.count("## 📊 Durum panosu:"), 2)
        self.assertEqual(c2.count("## ✅ Pre-commit:"), 2)
        self.assertEqual(c2.count("## 🔴 K0 bayat zip:"), 2)

    def test_file_sink_dashboard_only(self):
        """--dashboard-only: dosyaya yalnızca durum panosu yazılır."""
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            summary_file = pathlib.Path(d) / "summary.md"
            os.environ["GITHUB_STEP_SUMMARY"] = str(summary_file)
            buf = io.StringIO()
            argv = ["--dashboard-only"]
            for key, p in paths.items():
                argv += [f"--{key}", str(p)]
            with contextlib.redirect_stdout(buf):
                code = cs.main(argv)
            content = summary_file.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("## 📊 Durum panosu:", content)
        self.assertNotIn("## ✅ Pre-commit:", content)
        self.assertNotIn("## 🔴 K0 bayat zip:", content)

    def test_file_sink_skip_dashboard(self):
        """--skip-dashboard: dosyaya panosuz yalnızca bölümler yazılır."""
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            summary_file = pathlib.Path(d) / "summary.md"
            os.environ["GITHUB_STEP_SUMMARY"] = str(summary_file)
            buf = io.StringIO()
            argv = ["--skip-dashboard"]
            for key, p in paths.items():
                argv += [f"--{key}", str(p)]
            with contextlib.redirect_stdout(buf):
                code = cs.main(argv)
            content = summary_file.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertNotIn("## 📊 Durum panosu:", content)
        self.assertIn("## ✅ Pre-commit:", content)
        self.assertIn("## 🔴 K0 bayat zip:", content)

    def test_file_sink_sections_in_order(self):
        """Dosyada bölümler SECTIONS sırasıyla görünür (satır bazlı)."""
        with tempfile.TemporaryDirectory() as d:
            paths = self._sidecars(d)
            summary_file = pathlib.Path(d) / "summary.md"
            code, content = self._run_file(paths, summary_file)
        self.assertEqual(code, 0)
        markers = ["## 📊 Durum panosu:", "## ✅ Pre-commit:",
                   "## 🔴 K0 bayat zip:", "## ✅ Bütçe kalkanı:",
                   "## ✅ Soy hattı", "## ⏭️ K1: sidecar'da yok"]
        last = -1
        for m in markers:
            self.assertIn(m, content)
            pos = content.index(m)
            self.assertGreater(pos, last, f"dosya sırası bozuk: {m}")
            last = pos


if __name__ == "__main__":
    unittest.main()
