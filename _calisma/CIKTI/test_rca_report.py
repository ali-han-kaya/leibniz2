#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_rca_report.py — RCA tablosunun sözleşme testleri.

Tablo bir kanıt aracıdır: yanlış "required/advisory" ayrımı ya da uydurma
kök neden, okuru olduğundan çok daha fazla yanıltır. Bu yüzden üç şey
kilitleniyor:
  1) önem ayrımı branch protection listesinden gelir (job adına güvenilmez)
  2) kök neden YALNIZ eşleşen job için üretilir; bilinmeyende "bilinmeyen"
  3) hiçbir düşen job yoksa verdict "clean" (advisory-only değil)
"""
import contextlib
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ci_failure_pattern as cfp  # noqa: E402
import rca_report as rca  # noqa: E402


@contextlib.contextmanager
def stub_jobs(jobs):
    """cfp.list_jobs'u sahte job listesine bağla (canlı 'gh' çağrısını keser).

    Tek yardımcı: bu bağlamayı elle kopyalayınca bir kez 'cfp.list_js' gibi
    sessizce yanlış ada yazıldı ve stub geri konmadan diğer testleri bozdu.
    """
    original = cfp.list_jobs
    cfp.list_jobs = lambda repo, run_id: jobs
    try:
        yield
    finally:
        cfp.list_jobs = original


class TestSeverityFromProtection(unittest.TestCase):
    """'advisory' kelimesi işareti DEĞİL — branch protection tek kaynak."""

    def test_job_in_required_list_is_required(self):
        name = "Repack determinism + verify (sidecar sync)"
        window = {name: {"failures": 10, "window": 10}}
        with stub_jobs([{"name": name, "conclusion": "failure"}]):
            rows, hits = rca.build_rows("1", "o/r", "verify-delivery",
                                        [name], window)
        self.assertEqual(hits, 1)
        self.assertEqual(rows[0]["severity"], "required")

    def test_job_with_advisory_word_but_not_required_is_advisory(self):
        """Job adı 'advisory' diyor ama listede yok → advisory (kelime değil,
        liste belirler)."""
        name = "Live CI doc↔GitHub sync audit (advisory)"
        with stub_jobs([{"name": name, "conclusion": "failure"}]):
            rows, hits = rca.build_rows("1", "o/r", "verify-delivery",
                                        ["Commit-msg gate"], {})
        self.assertEqual(hits, 0)
        self.assertEqual(rows[0]["severity"], "advisory")

    def test_empty_protection_list_yields_unknown_not_advisory(self):
        """Liste alınamadıysa "advisory" DEME — bilinmiyor (unknown)."""
        name = "Commit-msg gate"
        with stub_jobs([{"name": name, "conclusion": "failure"}]):
            rows, hits = rca.build_rows("1", "o/r", "verify-delivery", [], {})
        self.assertEqual(hits, 0)
        self.assertEqual(rows[0]["severity"], "unknown")

    def test_benign_conclusions_are_ignored(self):
        with stub_jobs([
            {"name": "Commit-msg gate", "conclusion": "success"},
            {"name": "A11y gate (axe-core, fail-closed)", "conclusion": "skipped"},
            {"name": "Budget shield (aggregated)", "conclusion": "failure"},
        ]):
            rows, hits = rca.build_rows("1", "o/r", "verify-delivery",
                                        ["Budget shield (aggregated)"], {})
        self.assertEqual([r["job"] for r in rows], ["Budget shield (aggregated)"])
        self.assertEqual(hits, 1)

    def test_cancelled_job_is_red_not_clean(self):
        """Canlı koşuda bulunan fail-OPEN: docker-security işleri `cancelled`
        olduğu için tablo `conclusion == "failure"` filtresine takılıp
        "verdict: clean | 0 / 0" yazdı. Koşumun kendisi `failure` idi."""
        jobs = [
            {"name": "Build and scan Docker image", "conclusion": "cancelled"},
            {"name": "Local security smoke (script parity)",
             "conclusion": "timed_out"},
        ]
        with stub_jobs(jobs):
            rows, hits = rca.build_rows("1", "o/r", "docker-security", [], {})
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["conclusion"] for r in rows],
                         ["cancelled", "timed_out"])

    def test_unknown_conclusion_is_red_fail_closed(self):
        """GitHub yeni bir değer eklerse sessizce yeşil sayılmamalı."""
        for concl in (None, "", "startup_failure", "action_required",
                      "stale", "TAMAMEN_YENI_BIR_DEGER"):
            self.assertTrue(rca.is_red(concl), concl)
        for concl in ("success", "skipped", "neutral", "SUCCESS"):
            self.assertFalse(rca.is_red(concl), concl)

    def test_cancelled_required_job_blocks(self):
        name = "Delivery verification — K1-K19 (single entry point)"
        with stub_jobs([{"name": name, "conclusion": "cancelled"}]):
            report = rca.build_report("1", "o/r", "wf", [name], {})
        self.assertEqual(report["verdict"], "blocking")
        self.assertEqual(report["required_failures"], 1)


class TestVerdict(unittest.TestCase):
    def _report(self, required, jobs):
        with stub_jobs(jobs):
            return rca.build_report("1", "o/r", "wf", required, {})

    def test_required_failure_is_blocking(self):
        report = self._report(["X"], [{"name": "X", "conclusion": "failure"}])
        self.assertEqual(report["verdict"], "blocking")
        self.assertEqual(report["required_failures"], 1)
        self.assertEqual(report["advisory_failures"], 0)

    def test_no_rows_is_clean(self):
        report = self._report([], [{"name": "X", "conclusion": "success"}])
        self.assertEqual(report["verdict"], "clean")
        self.assertEqual(report["rows"], [])

    def test_advisory_only_verdict(self):
        report = self._report(["Commit-msg gate"],
                              [{"name": "Adv", "conclusion": "failure"}])
        self.assertEqual(report["verdict"], "advisory-only")
        self.assertEqual(report["required_failures"], 0)
        self.assertEqual(report["advisory_failures"], 1)

    def test_unreadable_protection_is_indeterminate_not_advisory(self):
        """Branch protection okunamayınca 'advisory-only' DEME.

        required listesi boşken 'advisory-only' + 'advisory kırmızı: 0'
        yazmak kendi kendisiyle çelişen bir kanıt olurdu; 'indeterminate'
        dürüst olanı söyler."""
        report = self._report([], [{"name": "Adv", "conclusion": "failure"}])
        self.assertEqual(report["verdict"], "indeterminate")
        self.assertEqual(report["advisory_failures"], 0)
        self.assertEqual(report["unknown_severity"], 1)
        self.assertIn("Önem ayrımı yapılamadı", rca.render(report))

    def test_stub_restores_list_jobs(self):
        """Sessiz bozulmayı yakala: stub sonrası canlı list_jobs geri gelmeli."""
        original = cfp.list_jobs
        with stub_jobs([{"name": "X", "conclusion": "failure"}]):
            self.assertIsNot(cfp.list_jobs, original)
        self.assertIs(cfp.list_jobs, original)


class TestRootCauseMapping(unittest.TestCase):
    def test_known_jobs_have_rca_docs(self):
        cases = {
            "Repack determinism + verify (sidecar sync)": "docs/RCA_REPACK_SIDECAR_DRIFT.md",
            "Live CI doc↔GitHub sync audit (advisory)": "docs/PUBLISH_SCENARIO.md",
            "Build and scan Docker image": "docs/DOCKER_SECURITY_PATCHING.md",
            "Run determinism experiment and record trend": "docs/KNOWN_INCIDENTS.md",
        }
        for job, doc in cases.items():
            with self.subTest(job=job):
                self.assertEqual(rca.rca_for(job)[1], doc)

    def test_unknown_job_gets_no_invented_cause(self):
        cause, doc, action = rca.rca_for("Tezcanlı yeni job")
        self.assertIn("bilinmeyen", cause)
        self.assertEqual(doc, "")
        self.assertTrue(action)

    def test_every_mapped_doc_is_openable_or_declared_artifact(self):
        """TABLODAKI HER satır denetim altında — yeni satır eklendiğinde de
        otomatik açılabilir-yol kuralına girer.

        Kanıt tablosunda okunamayan bir yol, olmayan kanıttan kötüdür: ya
        depoda açılabilir bir dosya olmalı, ya da "run artifact:" ile
        repoda olmadığı açıkça söylenmeli."""
        root = HERE.parents[1]
        for key, _cause, doc, _action in rca.RCA_TABLE:
            with self.subTest(job=key):
                if doc.startswith("run artifact:"):
                    path = doc.split(":", 1)[1].strip()
                    self.assertTrue(path.endswith(".log"), f"{doc}: log yolu olmalı")
                    self.assertFalse((root / path).exists(),
                                     f"{path} run artifact'ı diye işaretli ama depoda var")
                    continue
                self.assertNotIn(" (", doc,
                                 f"{key}: belge alanında yorum/paragraf var, "
                                 f"'bkz. ...' metne konmalı")
                self.assertTrue((root / doc).is_file(),
                                f"{doc} tabloda ama depoda yok")


class TestRequiredSource(unittest.TestCase):
    """Önem listesi NEREDEN geldi — tablo bunu da söylemek zorunda.

    Canlı branch protection okuması GITHUB_TOKEN'a verilemez; ilk canlı
    koşuda liste boş döndü ve tablo required/advisory ayrımını sessizce
    kaybetti. Bu testler o sessiz çöküşü kilitler.
    """

    def _stub_gh(self, returncode, stdout=""):
        class P:
            pass
        p = P()
        p.returncode = returncode
        p.stdout = stdout
        p.stderr = "denied"
        return p

    def test_live_protection_is_preferred(self):
        import json as _json
        payload = _json.dumps({"contexts": ["A", "B"]})
        original = rca.subprocess.run
        rca.subprocess.run = lambda *a, **k: self._stub_gh(0, payload)
        try:
            ctx, src = rca.required_contexts("o/r")
        finally:
            rca.subprocess.run = original
        self.assertEqual(ctx, ["A", "B"])
        self.assertEqual(src, "branch-protection")

    def test_unreadable_protection_falls_back_to_workflow_names(self):
        """CI'da API reddedilir → tablo ÇÖKMEMELİ, azalan doğrulukla devam
        etmeli ve bunu etiketlemeli."""
        original = rca.subprocess.run
        rca.subprocess.run = lambda *a, **k: self._stub_gh(1, "")
        try:
            ctx, src = rca.required_contexts("o/r")
        finally:
            rca.subprocess.run = original
        if not ctx:
            self.skipTest("PyYAML yok (CI) — türetme kaynağı okunamıyor")
        self.assertIn("okunamad", src)
        self.assertNotEqual(src, "branch-protection")

    def test_derivation_excludes_non_gate_jobs(self):
        """GATE_EXCLUDE dışındaki job adları required sayılır."""
        import status_checks as sc
        # GATE_EXCLUDE job *id*'leriyle eşleşir, adlarıyla değil.
        fake = {"jobs": {
            "verify": {"name": "Delivery verification — K1-K19"},
            "plist-check": {"name": "macOS plist-check"},
            "nameless": {},
        }}
        self.assertEqual(rca._derived_required(fake), ["Delivery verification — K1-K19"])
        self.assertIn("plist-check", sc.GATE_EXCLUDE)

    def test_derivation_never_dies_without_yaml(self):
        """PyYAML yokken süreç ÖLMEMELİ (status_checks.sys.exit(2) tuzağı).

        Bu sessiz çöküş ilk canlı CI koşusunda yakalandı: fallback tam
        olarak PyYAML'in bulunmadığı yerde çalışmak zorundaydı."""
        real_yaml = sys.modules.get("yaml")
        original = rca.subprocess.run
        rca.subprocess.run = lambda *a, **k: self._stub_gh(1, "")
        try:
            sys.modules["yaml"] = None  # `import yaml` -> ImportError
            ctx, src = rca.required_contexts("o/r")
        finally:
            if real_yaml is not None:
                sys.modules["yaml"] = real_yaml
            else:
                sys.modules.pop("yaml", None)
            rca.subprocess.run = original
        self.assertEqual(ctx, [])
        self.assertEqual(src, "bilinmiyor")

    def test_fallback_contains_real_gate_job_names(self):
        import status_checks as sc
        try:
            ctx, src = rca.required_contexts("o/r")
        except BaseException:
            self.skipTest("PyYAML yok")
        if not ctx:
            self.skipTest("PyYAML yok — gerçek dosya okunamadı")
        self.assertIn("Delivery verification — K1-K19 (single entry point)", ctx)
        self.assertIn("Delivery verification — K1-K19 (single entry point)",
                      set(sc.gate_jobs().values()))

    def test_render_states_the_source(self):
        report = {"run_id": 1, "workflow": "wf", "verdict": "indeterminate",
                  "required_failures": 0, "advisory_failures": 0, "rows": [],
                  "required_source": "verify.yml job adları (canlı koruma okunamadı)"}
        text = rca.render(report)
        self.assertIn("önem listesi kaynağı:", text)
        self.assertIn("okunamadı", text)


class TestRender(unittest.TestCase):
    def test_render_includes_rows_and_verdict(self):
        report = {"run_id": 42, "workflow": "verify-delivery", "verdict": "blocking",
                  "required_failures": 1, "advisory_failures": 0,
                  "rows": [{"job": "J", "severity": "required", "pattern": "deterministic",
                            "root_cause": "c", "rca_doc": "d", "action": "a"}]}
        text = rca.render(report)
        self.assertIn("verdict: blocking", text)
        self.assertIn("| J | required |", text)

    def test_render_without_rows_says_so(self):
        text = rca.render({"run_id": 1, "workflow": "wf", "verdict": "clean",
                           "required_failures": 0, "advisory_failures": 0, "rows": []})
        self.assertIn("(düşen job yok)", text)


if __name__ == "__main__":
    unittest.main()
