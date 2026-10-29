#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_advisory_exit_sidecars.py sözleşmesi.

Kapının amacı: advisory bir adımın exit sidecar'ı kaybolduğunda (errexit,
çökme veya atlanan adım) CI KIRMIZI olsun. Testler bu sınıfın her iki
modunu da gerçek giriş noktasından sürer:

  * runtime — eksik/boş/ayrıştırılamaz/aralık-dışı dosya FAIL,
  * static  — yazıcısı olmayan, errexit-güvensiz, kayıtsız veya çift
              yazıcılı sidecar FAIL (gerçek verify.yml PASS kalır).
"""
import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

CIKTI = pathlib.Path(__file__).resolve().parent
ROOT = CIKTI.parents[1]
sys.path.insert(0, str(CIKTI))

import check_advisory_exit_sidecars as gate  # noqa: E402

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

VERIFY_YML = ROOT / ".github" / "workflows" / "verify.yml"

SAMPLE = (
    {"name": "precommit", "path": "logs/precommit.exit",
     "step": "Run pre-commit (advisory)"},
)


def run_gate(argv):
    """Gate'i gerçek main() üzerinden koş; (rc, stdout) döndür."""
    out = io.StringIO()
    with redirect_stdout(out):
        rc = gate.main(argv)
    return rc, out.getvalue()


def write_sidecars(directory, values):
    for name, value in values.items():
        (pathlib.Path(directory) / f"{name}.exit").write_text(value,
                                                             encoding="utf-8")


class TestRuntimeMode(unittest.TestCase):
    def test_all_sidecars_present_passes_even_with_nonzero_verdicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_sidecars(tmp, {"precommit": "1", "k13_repro_manifest": "0",
                                 "k12_repro_manifest": "2",
                                 "check_unit_tests": "0"})
            rc, out = run_gate(["--dir", tmp])
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS", out)

    def test_missing_sidecar_fails_and_names_the_lost_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_sidecars(tmp, {"precommit": "0", "k13_repro_manifest": "0",
                                 "k12_repro_manifest": "0"})
            rc, out = run_gate(["--dir", tmp, "--json"])
        payload = json.loads(out)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["verdict"], "FAIL")
        self.assertEqual(payload["missing"], ["check_unit_tests"])
        self.assertEqual(payload["invalid"], [])
        detail = [f for f in payload["findings"]
                  if f["kind"] == "missing-sidecar"]
        self.assertEqual(len(detail), 1)
        self.assertIn("check_unit_tests.exit", detail[0]["path"])

    def test_empty_sidecar_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_sidecars(tmp, {"precommit": "", "k13_repro_manifest": "0",
                                 "k12_repro_manifest": "0",
                                 "check_unit_tests": "0"})
            rc, out = run_gate(["--dir", tmp, "--json"])
        payload = json.loads(out)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["invalid"], ["precommit"])
        self.assertEqual(payload["missing"], [])

    def test_non_numeric_sidecar_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_sidecars(tmp, {"precommit": "Traceback (most recent call last)",
                                 "k13_repro_manifest": "0",
                                 "k12_repro_manifest": "0",
                                 "check_unit_tests": "0"})
            rc, out = run_gate(["--dir", tmp, "--json"])
        payload = json.loads(out)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["invalid"], ["precommit"])

    def test_out_of_range_exit_code_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_sidecars(tmp, {"precommit": "999", "k13_repro_manifest": "0",
                                 "k12_repro_manifest": "0",
                                 "check_unit_tests": "0"})
            rc, out = run_gate(["--dir", tmp, "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["invalid"], ["precommit"])

    def test_json_out_writes_one_document_and_keeps_stdout_human(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_sidecars(tmp, {"precommit": "0", "k13_repro_manifest": "0",
                                 "k12_repro_manifest": "0",
                                 "check_unit_tests": "0"})
            report = pathlib.Path(tmp) / "reported" / "sidecars.json"
            rc, out = run_gate(["--dir", tmp, "--json-out", str(report)])
            self.assertEqual(rc, 0)
            self.assertNotIn('"verdict"', out)
            self.assertEqual(json.loads(report.read_text())["verdict"], "PASS")

    def test_expect_subset_only_checks_named_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_sidecars(tmp, {"precommit": "0"})
            rc, out = run_gate(["--dir", tmp, "--expect", "precommit", "--json"])
        self.assertEqual(rc, 0, out)
        self.assertEqual(json.loads(out)["expected"], ["precommit"])

    def test_unknown_expect_name_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out = run_gate(["--dir", tmp, "--expect", "nope"])
        self.assertEqual(rc, 2)


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli (statik mod)")
class TestStaticMode(unittest.TestCase):
    def _workflow(self, tmp, steps, job="verify"):
        path = pathlib.Path(tmp) / "wf.yml"
        path.write_text(yaml.safe_dump({"jobs": {job: {"steps": steps}}}),
                        encoding="utf-8")
        return path

    def _advisory_step(self, run, name="Run pre-commit (advisory)"):
        return {"name": name, "if": "always()", "continue-on-error": True,
                "shell": "bash", "run": run}

    def _findings_for(self, workflow_path, registry=None):
        registry = gate.SIDECARS if registry is None else registry
        findings = []
        details = gate.check_static(workflow_path, registry, findings)
        return findings, details

    def test_real_verify_yml_registry_is_in_sync(self):
        findings, details = self._findings_for(VERIFY_YML)
        self.assertEqual(findings, [])
        self.assertTrue(all(item["status"] == "ok" for item in details))

    def test_set_plus_e_writer_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._workflow(tmp, [self._advisory_step(
                "set +e\npre-commit run --all-files > logs/precommit.log 2>&1\n"
                "status=$?\nset -e\necho \"$status\" > logs/precommit.exit\n"
                "exit $status\n")])
            findings, _ = self._findings_for(path, SAMPLE)
        self.assertEqual(findings, [])

    def test_if_else_writer_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._workflow(tmp, [self._advisory_step(
                "if python3 x.py > logs/precommit.log 2>&1; then\n"
                "  status=0\nelse\n  status=$?\nfi\n"
                "echo \"$status\" > logs/precommit.exit\n")])
            findings, _ = self._findings_for(path, SAMPLE)
        self.assertEqual(findings, [])

    def test_bare_command_writer_is_errexit_unsafe(self):
        # Tam olarak ölçülen olay: errexit `status=$?` satırını yutar.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._workflow(tmp, [self._advisory_step(
                "pre-commit run --all-files > logs/precommit.log 2>&1\n"
                "status=$?\necho \"$status\" > logs/precommit.exit\n")])
            findings, _ = self._findings_for(path, SAMPLE)
        self.assertEqual([f["kind"] for f in findings], ["unsafe-writer"])
        self.assertIn("errexit", findings[0]["detail"])

    def test_missing_writer_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._workflow(tmp, [{"name": "other", "run": "echo hi"}])
            findings, _ = self._findings_for(path, SAMPLE)
        self.assertEqual([f["kind"] for f in findings], ["no-writer"])

    def test_two_writers_is_ambiguous(self):
        run = ("set +e\ncmd\nstatus=$?\nset -e\n"
               "echo \"$status\" > logs/precommit.exit\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = self._workflow(tmp, [self._advisory_step(run),
                                        self._advisory_step(run, name="dup")])
            findings, _ = self._findings_for(path, SAMPLE)
        self.assertEqual([f["kind"] for f in findings], ["ambiguous-writer"])

    def test_writer_that_is_not_advisory_fails(self):
        step = self._advisory_step(
            "set +e\ncmd\nstatus=$?\nset -e\n"
            "echo \"$status\" > logs/precommit.exit\n")
        step["continue-on-error"] = False
        with tempfile.TemporaryDirectory() as tmp:
            path = self._workflow(tmp, [step])
            findings, _ = self._findings_for(path, SAMPLE)
        self.assertEqual([f["kind"] for f in findings], ["unsafe-writer"])
        self.assertIn("advisory", findings[0]["detail"])

    def test_step_name_drift_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._workflow(tmp, [self._advisory_step(
                "set +e\ncmd\nstatus=$?\nset -e\n"
                "echo \"$status\" > logs/precommit.exit\n", name="Renamed")])
            findings, _ = self._findings_for(path, SAMPLE)
        self.assertEqual([f["kind"] for f in findings], ["unsafe-writer"])
        self.assertIn("adım adı", findings[0]["detail"])

    def test_partial_registry_does_not_flag_other_known_writers(self):
        # `--expect precommit` yalnız precommit'i denetler; K13 yazıcısı
        # "kayıtsız" diye yanlış kırmızı üretmemeli.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._workflow(tmp, [self._advisory_step(
                "set +e\ncmd\nstatus=$?\nset -e\n"
                "echo \"$status\" > logs/precommit.exit\n")])
            findings = []
            gate.check_static(path, SAMPLE, findings,
                              known_paths={e["path"] for e in gate.SIDECARS})
        self.assertEqual(findings, [])

    def test_unregistered_exit_writer_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._workflow(tmp, [
                self._advisory_step("set +e\ncmd\nstatus=$?\nset -e\n"
                                    "echo \"$status\" > logs/precommit.exit\n"),
                {"name": "new gate", "run": "echo 0 > logs/extra.exit"},
            ])
            findings, _ = self._findings_for(path, SAMPLE)
        kinds = sorted(f["kind"] for f in findings)
        self.assertEqual(kinds, ["unregistered-writer"])
        self.assertIn("extra.exit", findings[0]["path"])


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli (CI kablolaması)")
class TestCiWiring(unittest.TestCase):
    """CI adımı gerçekten hatayı job'a taşıyor mu (continue-on-error YOK)?"""

    def _steps(self):
        data = yaml.safe_load(VERIFY_YML.read_text(encoding="utf-8"))
        return [step for job in (data.get("jobs") or {}).values()
                if isinstance(job, dict)
                for step in (job.get("steps") or [])
                if isinstance(step, dict)]

    def test_verify_job_runs_the_sidecar_check_fail_closed(self):
        matches = [s for s in self._steps()
                   if "check_advisory_exit_sidecars.py"
                   in (s.get("run") or "")]
        self.assertEqual(len(matches), 1, "tam olarak bir denetim adımı olmalı")
        step = matches[0]
        self.assertEqual(step.get("if"), "always()")
        self.assertFalse(step.get("continue-on-error"),
                         "denetim adımı advisory olamaz — hatayı job'a taşımalı")
        self.assertIn("--dir logs", step["run"])
        self.assertIn("--workflow .github/workflows/verify.yml", step["run"])

    def test_check_step_is_ordered_after_every_producer(self):
        steps = self._steps()
        runs = [s.get("run") or "" for s in steps]
        check_idx = next(i for i, run in enumerate(runs)
                         if "check_advisory_exit_sidecars.py" in run)
        for entry in gate.SIDECARS:
            sidecar = pathlib.Path(entry["path"]).name
            producers = [i for i, run in enumerate(runs)
                         if f"> logs/{sidecar}" in run]
            self.assertTrue(producers, f"{sidecar} yazıcısı yok")
            self.assertLess(max(producers), check_idx,
                            f"{sidecar} yazıcısı denetimden SONRA koşuyor")


if __name__ == "__main__":
    unittest.main()
