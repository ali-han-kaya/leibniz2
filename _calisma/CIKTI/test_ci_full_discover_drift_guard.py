#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_ci_full_discover_drift_guard.py — bağlama kapısı (wiring contract).

`ci_full_discover_drift_guard.py` yazıldığında CI'ya bağlı değildi: docstring
"verify.yml'e bağla" diyordu ama hiçbir referansı yoktu
(`docs/DOCKER_SECURITY_GATE_MERGE_REPORT.md` §"Ölçüldü, kapatılmadı" #2).
Bu test bağlanmayı pin'ler ki adım sessizce silinemesin:

  W1. verify.yml `verify` job'unda guard'ı koşan TAM BİR adım var.
  W2. Adım FAIL-CLOSED: `continue-on-error` YOK ve exit kodu dışa aktarılır
      (`exit $status`) — advisory'e sessizce düşürülemez.
  W3. Adım makine-okur kanıt üretir: `--json-out logs/…json` + `.exit`
      dosyası (precommit-logs artifact'ı `logs/` dizinini yükler).
  W4. Batarya ölçümü fail-open değil: dosya adı `.py` uzantısıyla modül gibi
      import EDİLMEZ, koşum repo kökünden `PYTHONPATH=CIKTI` ile yapılır.
      (Ölçülen eski hâl: repo kökünden `python -m unittest test_x.py` →
      her dosya ModuleNotFoundError → "batarya yeşil" hiç sağlanamıyor →
      gate asla FAIL veremiyordu, 0/195.)
  W5. `check_unit_tests.list` yorum satırları kayıt sayılmaz (ölçülen hata:
      iki `#` satırı `orphan_registrations_not_on_disk` içinde "diskte
      olmayan kayıt" gibi raporlanıyordu).

stdlib unittest; ağ/donanım gerektirmez (guard'ın alt süreçleri mock'lanır).
"""
import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

CIKTI = pathlib.Path(__file__).resolve().parent
ROOT = CIKTI.parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"

if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:  # pragma: no cover — bare runner
    HAVE_YAML = False


def _verify_steps():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return data["jobs"]["verify"]["steps"]


def _guard_steps():
    return [s for s in _verify_steps()
            if "ci_full_discover_drift_guard.py" in (s.get("run") or "")]


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli (verify.yml parse)")
class TestWiring(unittest.TestCase):
    """W1-W3: adım var, fail-closed ve kanıt üretiyor."""

    def test_step_exists_exactly_once(self):
        found = _guard_steps()
        self.assertEqual(len(found), 1,
                         "verify job'ında guard'ı koşan tam bir adım olmalı "
                         f"(bulunan: {len(found)})")

    def test_step_is_fail_closed(self):
        step = _guard_steps()[0]
        self.assertNotEqual(step.get("continue-on-error"), True,
                            "guard adımı advisory'e düşürülmüş — drift "
                            "sessizce yeşil görünür (fail-open)")
        run = step["run"]
        self.assertIn("exit $status", run,
                      "adım exit kodunu dışa aktarmıyor → FAIL yutulur")
        # `set +e` yalnız exit kodunu yakalamak için; kararı `exit` verir.
        self.assertIn("status=$?", run)

    def test_step_emits_evidence_sidecars(self):
        run = _guard_steps()[0]["run"]
        self.assertIn("--json-out logs/", run,
                      "JSON sidecar logs/ altında üretilmeli (precommit-logs "
                      "artifact'ı bu dizini yükler)")
        self.assertIn("logs/full_discover_drift_guard.exit", run,
                      "exit kodu kanıt dosyasına yazılmalı")
        self.assertIn("verify_report.txt", run,
                      "kanıt verify_report.txt'ye de eklenmeli")


class TestBatteryInvocationContract(unittest.TestCase):
    """W4: batarya ölçümü modül/ortam sözleşmesi (fail-open regresyonu)."""

    def _run_main(self, per_file_rc=0, files=("test_a.py", "test_b.py")):
        import ci_full_discover_drift_guard as g

        calls = []
        err = io.StringIO()

        class _Result:
            def __init__(self, rc, out):
                self.returncode = rc
                self.stdout = out
                self.stderr = ""

        def fake_run(cmd, **kw):
            calls.append((list(cmd), kw))
            if "discover" in cmd:
                return _Result(per_file_rc, "Ran 7 tests in 0.01s")
            return _Result(per_file_rc, "Ran 1 test in 0.01s")

        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "guard.json"
            with mock.patch.object(g.subprocess, "run", side_effect=fake_run), \
                    mock.patch.object(g, "read_check_unit_tests_list",
                                      return_value=set(files)), \
                    mock.patch.object(g, "read_hook_coverage_check_unit_tests",
                                      return_value=set()), \
                    mock.patch.object(g, "discover_all_py_test_files",
                                      return_value=set(files)), \
                    contextlib.redirect_stderr(err):
                rc = g.main(["--json-out", str(out)])
            summary = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
        return rc, calls, summary, err.getvalue()

    def test_files_run_as_modules_from_repo_root(self):
        rc, calls, _, _ = self._run_main()
        self.assertEqual(rc, 0)
        per_file = [c for c in calls if "discover" not in c[0]]
        self.assertEqual(len(per_file), 2)
        for cmd, kw in per_file:
            self.assertNotIn(".py", cmd[-1],
                             "modül adı `.py` uzantısız olmalı — uzantılı ad "
                             "repo kökünden import edilemez (fail-open)")
            self.assertEqual(kw["cwd"], str(ROOT),
                             "cwd repo kökü olmalı (testler göreli yolları "
                             "cwd'den çözer)")
            self.assertIn(str(CIKTI), kw["env"]["PYTHONPATH"],
                          "PYTHONPATH'te CIKTI olmalı (CI'ın discover "
                          "koşumuyla aynı görünüm)")

    def test_battery_green_is_measured_and_reported(self):
        rc, _, summary, err = self._run_main()
        self.assertEqual(rc, 0)
        self.assertIn("kayıtlı batarya: GREEN (2/2 passed)", err)
        self.assertTrue(summary["registered_battery"]["green"])
        self.assertEqual(summary["registered_battery"]["files_passed"], 2)
        self.assertEqual(summary["registered_battery"]["files_failed"], [])

    def test_red_battery_keeps_gate_from_silently_failing(self):
        # Batarya kırmızıyken gate FAIL hükme varamaz (drift tanımı batarya
        # YEŞİL iken discover KIRMIZI). Bu, ölçümün değil tanımın sınırı:
        # CI'da kırmızı batarya zaten birim test adımında düşer.
        rc, _, summary, err = self._run_main(per_file_rc=1)
        self.assertEqual(rc, 0)
        self.assertFalse(summary["registered_battery"]["green"])
        self.assertFalse(summary["drift_detected"])
        # Kanıt metni çelişkili olmamalı: kırmızı batarya "GREEN" yazmaz.
        self.assertIn("kayıtlı batarya: RED (0/2 passed)", err)


class TestRegisteredListParsing(unittest.TestCase):
    """W5: liste yorumları kayıt sayılmaz."""

    def test_comments_and_blank_lines_ignored(self):
        import ci_full_discover_drift_guard as g
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "check_unit_tests.list"
            path.write_text(
                "# check-unit-tests koşu listesi — otomatik üretilir\n"
                "# elle düzenleme gerekmez\n"
                "\n"
                "test_a.py\n"
                "  test_b.py  \n",
                encoding="utf-8")
            with mock.patch.object(g, "CHECK_UNIT_TESTS_LIST", path):
                entries = g.read_check_unit_tests_list()
        self.assertEqual(entries, {"test_a.py", "test_b.py"})

    def test_repo_list_has_no_comment_entries(self):
        import ci_full_discover_drift_guard as g
        entries = g.read_check_unit_tests_list()
        self.assertTrue(entries)
        for entry in entries:
            self.assertFalse(entry.startswith("#"), f"yorum kayıt sayılmış: {entry}")
            self.assertTrue(entry.endswith(".py"), f"uzantısız kayıt: {entry}")


if __name__ == "__main__":
    unittest.main()
