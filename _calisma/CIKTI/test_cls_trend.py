#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_cls_trend.py — CLS bütçe trendi + bütçe-altı regresyon kapısı.

Neden: `a11y-gate` CLS'i 0.1 bütçesine karşı ölçer; bütçenin ALTINDA kalan
bir sıçrama (0.0001 → 0.09) o kapıdan YEŞİL geçer. Bu süit, trend modülünün
o boşluğu gerçekten kapattığını pin'ler:

  * taban = önceki run'ların tema başına MEDYANI (tek aykırı run'a duyarlı
    değil), son run tabana girmez;
  * regresyon = göreli eşik VE mutlak taban BİRLİKTE (biri tek başına
    yetmez) — mikro gürültü regresyon sayılmaz, gerçek sıçrama kaçmaz;
  * geçmiş yetersizse SKIP (PASS değil), en güncel rapor okunamıyorsa ERROR;
  * API hatasında HİÇ artifact yazılmaz (fail-closed);
  * koşum geçmişi JSONL'i byte-kararlıdır (sort_keys, tarih sıralı).

stdlib unittest — ağ yok (fetch enjekte edilir), PyYAML yalnızca kontrat
testinde ve yoksa dürüstçe SKIP.
"""
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
import zipfile

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import cls_trend as ct  # noqa: E402

ROOT = CIKTI.parent.parent
WF = ROOT / ".github" / "workflows" / "verify.yml"
DOC = ROOT / "docs" / "PUBLISH_SCENARIO.md"


def row(cls_by_theme, date="2026-10-01T00:00:00Z", run_id=1, budget=0.1,
        verdict="PASS"):
    themes = {t: {"cls": v, "verdict": "PASS"} for t, v in cls_by_theme.items()}
    return {"date": date, "run_id": run_id, "artifact_id": run_id,
            "budget": budget, "verdict": verdict, "themes": themes}


def series(values, budget=0.1):
    """Aynı temada art arda run'lar üretir (tarihler artan)."""
    return [row({"dark": v}, date=f"2026-10-{i + 1:02d}T00:00:00Z",
                run_id=i + 1, budget=budget) for i, v in enumerate(values)]


class TestDetectRegressions(unittest.TestCase):
    def test_no_rows_is_skip_not_pass(self):
        d = ct.detect_regressions([])
        self.assertEqual(d["verdict"], "SKIP")
        self.assertIn("artifact", d["reason"])

    def test_single_run_is_skip(self):
        d = ct.detect_regressions(series([0.001]))
        self.assertEqual(d["verdict"], "SKIP")
        self.assertIn("geçmiş", d["reason"])

    def test_stable_values_pass(self):
        d = ct.detect_regressions(series([0.001, 0.001, 0.001]))
        self.assertEqual(d["verdict"], "PASS")
        self.assertEqual(d["regressions"], [])
        self.assertEqual(d["baseline_runs"], 2)

    def test_sub_budget_jump_regresses(self):
        # 0.001 → 0.05: bütçenin (0.1) ALTINDA, yani a11y-gate YEŞİL;
        # trend kapısı bunu yakalamalı.
        d = ct.detect_regressions(series([0.001, 0.001, 0.05]))
        self.assertEqual(d["verdict"], "REGRESSION")
        self.assertEqual(d["regressions"], ["dark"])
        theme = d["themes"][0]
        self.assertAlmostEqual(theme["baseline"], 0.001)
        self.assertTrue(theme["regressed"])

    def test_relative_threshold_alone_is_not_enough(self):
        # +%74 göreli sıçrama ama mutlak artış 0.000085 < 0.005 → gürültü.
        d = ct.detect_regressions(series([0.000115, 0.000115, 0.0002]))
        self.assertEqual(d["verdict"], "PASS")
        self.assertFalse(d["themes"][0]["regressed"])

    def test_absolute_floor_alone_is_not_enough(self):
        # Δ=0.005 tam mutlak tabanda ama göreli eşik (+%20) aşılmıyor.
        d = ct.detect_regressions(series([0.05, 0.05, 0.055]))
        self.assertEqual(d["verdict"], "PASS")

    def test_both_thresholds_together_regress(self):
        d = ct.detect_regressions(series([0.05, 0.05, 0.07]))
        self.assertEqual(d["verdict"], "REGRESSION")

    def test_baseline_is_median_not_mean(self):
        # Son run tabana girmez; 0.09 tek aykırı önceki run medyanı bozmaz.
        d = ct.detect_regressions(series([0.001, 0.09, 0.001, 0.001, 0.08]))
        self.assertAlmostEqual(d["themes"][0]["baseline"], 0.001)
        self.assertEqual(d["verdict"], "REGRESSION")

    def test_window_limits_baseline(self):
        # window=2 → yalnız son iki önceki run tabana girer (0.09 dışarıda).
        d = ct.detect_regressions(series([0.09, 0.001, 0.001, 0.01]),
                                  window=2, min_delta=0.001)
        self.assertEqual(d["baseline_runs"], 2)
        self.assertAlmostEqual(d["themes"][0]["baseline"], 0.001)
        self.assertEqual(d["verdict"], "REGRESSION")

    def test_missing_theme_in_baseline_has_no_baseline(self):
        # Taban penceresi dolu (2 run) ama yeni tema (`light`) geçmişte yok:
        # karşılaştırılamaz → "taban yok"; regresyon da PASS da uydurulmaz.
        rows = [row({"dark": 0.001}), row({"dark": 0.001}),
                row({"light": 0.05})]
        d = ct.detect_regressions(rows)
        self.assertEqual(d["verdict"], "PASS")
        self.assertIsNone(d["themes"][0]["baseline"])
        self.assertFalse(d["themes"][0]["regressed"])

    def test_budget_breach_is_recorded(self):
        d = ct.detect_regressions(series([0.12, 0.001, 0.001], budget=0.1))
        self.assertEqual(len(d["budget_breaches"]), 1)
        self.assertEqual(d["budget_breaches"][0]["theme"], "dark")
        self.assertAlmostEqual(d["budget_breaches"][0]["cls"], 0.12)

    def test_empty_current_themes_is_error_not_pass(self):
        rows = series([0.001, 0.001]) + [row({})]
        d = ct.detect_regressions(rows)
        self.assertEqual(d["verdict"], "ERROR")
        self.assertIn("tema yok", d["reason"])

    def test_invalid_values_are_not_measurements(self):
        for bad in (True, False, "0.1", float("nan"), float("inf"), -0.1,
                    None, {"x": 1}):
            self.assertIsNone(ct._as_value(bad), f"{bad!r} ölçüm sayılmamalı")
        self.assertEqual(ct._as_value(0.0), 0.0)
        self.assertEqual(ct._as_value(3), 3.0)


class TestParseAndRecord(unittest.TestCase):
    def _zip(self, payload, name="cls_budget.json"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(name, json.dumps(payload))
        return buf.getvalue()

    def test_parse_report_from_nested_path(self):
        blob = self._zip({"budget": 0.1, "verdict": "PASS", "themes": {}},
                         name="nested/cls_budget.json")
        self.assertEqual(ct.parse_cls_report(blob)["verdict"], "PASS")

    def test_parse_report_missing_is_error(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("other.json", "{}")
        with self.assertRaises(ValueError):
            ct.parse_cls_report(buf.getvalue())

    def test_record_row_carries_artifact_identity(self):
        artifact = {"id": 7, "created_at": "2026-10-02T03:04:05Z",
                    "workflow_run": {"id": 4242}}
        report = {"budget": 0.1, "verdict": "PASS",
                  "themes": {"light": {"cls": 0.02, "verdict": "PASS"},
                             "dark": {"cls": 0.01, "verdict": "FAIL"}}}
        r = ct.record_row(artifact, report)
        self.assertEqual(r["run_id"], 4242)
        self.assertEqual(r["date"], "2026-10-02T03:04:05Z")
        self.assertEqual(list(r["themes"]), ["dark", "light"])  # sıralı
        self.assertEqual(r["themes"]["dark"]["verdict"], "FAIL")


class TestFetchRecords(unittest.TestCase):
    """`_fetch_records` — API/zip katmanı (ağ yok, rt fonksiyonları sahte)."""

    def test_fetches_and_skips_unreadable_artifact(self):
        from unittest import mock

        def fake_zip(repo, aid):
            if aid == 2:
                raise RuntimeError("bozuk zip")
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("cls_budget.json", json.dumps({
                    "budget": 0.1, "verdict": "PASS",
                    "themes": {"dark": {"cls": 0.01, "verdict": "PASS"}}}))
            return buf.getvalue()

        artifacts = [
            {"id": 1, "created_at": "2026-10-02T00:00:00Z",
             "workflow_run": {"id": 11}},
            {"id": 2, "created_at": "2026-10-03T00:00:00Z",
             "workflow_run": {"id": 12}},
            {"id": 3, "created_at": "2026-10-01T00:00:00Z",
             "workflow_run": {"id": 10}},
        ]
        with mock.patch.object(ct.rt, "fetch_artifacts_by_name",
                               return_value=artifacts), \
             mock.patch.object(ct.rt, "api_get",
                               side_effect=lambda path, token, binary=False:
                               fake_zip("", int(path.split("/")[-2]))):
            rows = ct._fetch_records("o/r", "", 5)
        self.assertEqual([r["run_id"] for r in rows], [10, 11])  # tarih sıralı
        self.assertEqual(rows[-1]["themes"]["dark"]["cls"], 0.01)


class TestHistory(unittest.TestCase):
    def test_jsonl_is_one_row_per_line_and_sorted_keys(self):
        rows = series([0.001, 0.002])
        text = ct.history_jsonl(rows)
        lines = text.strip().splitlines()
        self.assertEqual(len(lines), 2)
        # sort_keys → her satırda "artifact_id" anahtarı "budget"tan önce.
        self.assertLess(lines[0].index('"artifact_id"'),
                        lines[0].index('"budget"'))
        self.assertEqual(json.loads(lines[0])["run_id"], 1)

    def test_jsonl_empty_is_empty(self):
        self.assertEqual(ct.history_jsonl([]), "")

    def test_build_trend_is_deterministic(self):
        rows = series([0.001, 0.05])
        a = json.dumps(ct.build_trend(rows), sort_keys=True)
        b = json.dumps(ct.build_trend(rows), sort_keys=True)
        self.assertEqual(a, b)
        self.assertNotIn("generated", json.loads(a))


class TestCli(unittest.TestCase):
    """Gerçek `main()` giriş noktası — fetch enjekte edilir (ağ yok)."""

    def _run(self, rows, *extra, fetch=None, run_env=None):
        """main()'i koşar; GITHUB_RUN_ID'yi hermetik yönetir.

        run_env verilmezse değişken kaldırılır (geliştirici makinesinde
        kazara set kalmış bir değer testleri etkilemesin).
        """
        tmp = tempfile.mkdtemp(prefix="cls-trend-")
        old = os.environ.get("GITHUB_RUN_ID")
        if run_env is None:
            os.environ.pop("GITHUB_RUN_ID", None)
        else:
            os.environ["GITHUB_RUN_ID"] = run_env
        try:
            rc = ct.main(["--repo", "o/r", "--out-dir", tmp, *extra],
                         fetch=fetch or (lambda repo, token, n: rows))
        finally:
            if old is None:
                os.environ.pop("GITHUB_RUN_ID", None)
            else:
                os.environ["GITHUB_RUN_ID"] = old
        return rc, pathlib.Path(tmp)

    def test_pass_writes_three_artifacts(self):
        rc, out = self._run(series([0.001, 0.001, 0.001]))
        self.assertEqual(rc, 0)
        data = json.loads((out / "cls-trend.json").read_text(encoding="utf-8"))
        self.assertEqual(data["verdict"], "PASS")
        self.assertEqual(data["run_count"], 3)
        self.assertTrue((out / "cls-trend.jsonl").is_file())
        self.assertIn("CLS bütçe trendi", (out / "cls-trend.md").read_text(
            encoding="utf-8"))

    def test_regression_exits_1_but_still_writes_artifacts(self):
        rc, out = self._run(series([0.001, 0.001, 0.05]))
        self.assertEqual(rc, 1)
        data = json.loads((out / "cls-trend.json").read_text(encoding="utf-8"))
        self.assertEqual(data["verdict"], "REGRESSION")
        self.assertIn("REGRESYON", (out / "cls-trend.md").read_text(
            encoding="utf-8"))

    def test_skip_exits_0(self):
        rc, out = self._run(series([0.001]))
        self.assertEqual(rc, 0)
        data = json.loads((out / "cls-trend.json").read_text(encoding="utf-8"))
        self.assertEqual(data["verdict"], "SKIP")

    def test_fetch_failure_writes_nothing_and_exits_1(self):
        def boom(repo, token, n):
            raise RuntimeError("API down")
        tmp = tempfile.mkdtemp(prefix="cls-trend-")
        rc = ct.main(["--repo", "o/r", "--out-dir", tmp], fetch=boom)
        self.assertEqual(rc, 1)
        self.assertEqual(os.listdir(tmp), [])

    def test_current_run_artifact_present_passes(self):
        rows = series([0.001, 0.001, 0.001])  # en yeni run_id=3
        rc, out = self._run(rows, run_env="3")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads((out / "cls-trend.json").read_text(
            encoding="utf-8"))["verdict"], "PASS")

    def test_missing_current_run_artifact_is_error(self):
        """a11y-gate düştüyse en yeni artifact eski run'dır — PASS yok."""
        rows = series([0.001, 0.001, 0.001])  # en yeni run_id=3
        rc, out = self._run(rows, "--fetch-retries", "0", run_env="99")
        self.assertEqual(rc, 1)
        data = json.loads((out / "cls-trend.json").read_text(encoding="utf-8"))
        self.assertEqual(data["verdict"], "ERROR")
        self.assertIn("99", data["reason"])

    def test_artifact_visibility_retry_recovers(self):
        """Artifact API listesine gecikmeli düşerse backoff ile yakalanır."""
        stale = series([0.001, 0.001])          # en yeni run_id=2
        fresh = series([0.001, 0.001, 0.001])   # en yeni run_id=3
        calls = []

        def flaky(repo, token, n):
            calls.append(1)
            return stale if len(calls) == 1 else fresh

        rc, out = self._run(stale, "--retry-delay", "0", fetch=flaky,
                            run_env="3")
        self.assertEqual(rc, 0, "ikinci denemede güncel run bulunmalı")
        self.assertEqual(len(calls), 2)
        data = json.loads((out / "cls-trend.json").read_text(encoding="utf-8"))
        self.assertEqual(data["verdict"], "PASS")
        self.assertEqual(data["run_count"], 3)

    def test_summary_appends_to_step_summary(self):
        tmp_summary = tempfile.mktemp()
        old = os.environ.get("GITHUB_STEP_SUMMARY")
        os.environ["GITHUB_STEP_SUMMARY"] = tmp_summary
        try:
            rc, _out = self._run(series([0.001, 0.001]), "--summary")
        finally:
            if old is None:
                os.environ.pop("GITHUB_STEP_SUMMARY", None)
            else:
                os.environ["GITHUB_STEP_SUMMARY"] = old
        self.assertEqual(rc, 0)
        self.assertIn("CLS bütçe trendi",
                      pathlib.Path(tmp_summary).read_text(encoding="utf-8"))


class ClsTrendContractTest(unittest.TestCase):
    """Trend job'ı ↔ kontrat yüzeyleri (statik; ağ/Playwright gerekmez)."""

    @classmethod
    def setUpClass(cls):
        if not WF.is_file() or not DOC.is_file():
            raise unittest.SkipTest("repo kökünden koşulmalı")
        try:
            import yaml
        except ImportError:
            raise unittest.SkipTest("PyYAML yok — workflow ayrıştırılamaz")
        with open(WF, encoding="utf-8") as f:
            cls.wf_text = f.read()
            f.seek(0)
            cls.wf = yaml.safe_load(f)

    def test_job_exists_and_uploads_artifact(self):
        job = self.wf["jobs"].get("cls-trend")
        self.assertIsNotNone(job, "verify.yml'de cls-trend job'ı yok")
        self.assertEqual(job["needs"], ["a11y-gate"])
        uploads = [s for s in job["steps"]
                   if s.get("uses", "").startswith("actions/upload-artifact")]
        self.assertEqual(len(uploads), 1, "tek upload adımı bekleniyor")
        self.assertEqual(uploads[0]["with"]["name"], "cls-trend")

    def test_job_has_actions_read_for_cross_run_api(self):
        job = self.wf["jobs"]["cls-trend"]
        self.assertEqual(job.get("permissions", {}).get("actions"), "read",
                         "artifact listeleme için actions: read şart")

    def test_job_is_advisory_in_branch_protection(self):
        import workflow_contract as wc
        self.assertIn("cls-trend", wc.GATE_EXCLUDE)

    def test_artifact_jobs_binds_cls_trend_to_its_job(self):
        import gen_repro_manifest as grm
        self.assertEqual(grm.ARTIFACT_JOBS.get("cls-trend"), "cls-trend")

    def test_merge_pattern_includes_cls_trend(self):
        import re
        m = re.search(r"merge-multiple:\s*true\s*\n\s*pattern:\s*'\{([^}]+)\}'",
                      self.wf_text)
        self.assertIsNotNone(m)
        self.assertIn("cls-trend", {s.strip() for s in m.group(1).split(",")})

    def test_publish_doc_lists_artifact_and_job(self):
        doc = DOC.read_text(encoding="utf-8")
        start = doc.index("**Artifact listesi")
        end = doc.index("\n**", start + 1)
        self.assertIn("`cls-trend`", doc[start:end])
        import re
        rows = re.findall(r"^\|\s*\d+\s*\|\s*[ABCD]\s*\|\s*([^|]+?)\s*\|",
                          doc, re.M)
        self.assertIn("CLS budget trend across runs (sub-budget regression gate)",
                      [r.strip() for r in rows])


if __name__ == "__main__":
    unittest.main()
