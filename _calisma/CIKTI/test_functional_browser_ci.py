#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_functional_browser_ci.py — dashboard-smoke'un Playwright icra sözleşmesi.

Neden bu test: `verify` job'ı Playwright süitlerini `unittest discover` ile
KEŞFEDER ama orada Chromium yoktur; süitler `skipIf` ile atlanır. "Keşfedildi"
"koştu" değildir. Bu sözleşme, Chromium'un gerçekten kurulduğu
`dashboard-smoke` job'ında iki fonksiyonel yüzeyin (CSP+nonce ve klavye)
koşulmasını ve SKIP/0-test ile yeşile dönememesini pinler.

Kontroller:
  * iki adım da dashboard-smoke içinde, "Install Chromium" +
    "Verify Chromium is functional" adımlarından SONRA;
  * `continue-on-error` YOK;
  * CSP adımı `LEIBNIZ2_REQUIRE_BROWSER=1` taşır (Playwright/Chromium
    yoksa import hatası — SKIP değil);
  * her adım `Ran N tests` pozitif sayısını ve `OK (skipped=0)` durumunu
    doğrular; `Ran 0` / `skipped=[1-9]` KIRMIZI.

`verify` işi için ayrı sözleşme (`VerifyHoverCspContractTests`, dosya sonu):
Chromium orada birim-test bataryasından SONRA kurulur ve hover-tooltip CSP
süiti `check_zero_check_fail_open.py --unittest-log` ile SKIP = red koşar —
böylece bu kanıt tek bir işe (a11y-gate) bağlı kalmaz.

Adımların shell gövdeleri sahte bir `python3` ile GERÇEKTEN koşulur: sentetik
"Ran 0", "OK (skipped=N)" ve temiz "Ran N / OK" logları adımın kendi
hükmünden geçirilir. Böylece test yalnız string eşleşmesi değil, gerçek
fail-closed davranışı ölçer.

stdlib unittest — yaml gerekir (repo bataryasında kurulu).
"""
import os
import pathlib
import subprocess
import tempfile
import unittest

import yaml

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"

JOB = "dashboard-smoke"
INSTALL_CHROMIUM = "Install Chromium"
CHROMIUM_STEP = "Verify Chromium is functional"
CSP_STEP = "Dashboard CSP+nonce smoke (Playwright)"
KEYBOARD_STEP = "Keyboard functional suite (Playwright, SKIP = red)"


def _job_steps():
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return wf["jobs"][JOB]["steps"]


def _named(steps):
    return {str(s.get("name", "")): s for s in steps}


def _run_step(step, output, returncode=0):
    """Adımın shell gövdesini sahte `python3` ile koş (cwd = geçici dizin)."""
    with tempfile.TemporaryDirectory() as td:
        fake = pathlib.Path(td) / "python3"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$FAKE_OUT\"\n"
            "exit \"${FAKE_RC:-0}\"\n",
            encoding="utf-8")
        fake.chmod(0o755)
        env = dict(os.environ)
        for key, value in (step.get("env") or {}).items():
            env[str(key)] = str(value)
        env["PATH"] = td + os.pathsep + env.get("PATH", "")
        env["FAKE_OUT"] = output
        env["FAKE_RC"] = str(returncode)
        return subprocess.run(["bash", "-c", step["run"]], cwd=td, env=env,
                              capture_output=True, text=True, timeout=30)


class TestFunctionalBrowserJob(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.steps = _job_steps()
        cls.named = _named(cls.steps)
        cls.names = [str(s.get("name", "")) for s in cls.steps]

    def test_both_suites_run_after_verified_chromium(self):
        for name in (CSP_STEP, KEYBOARD_STEP):
            self.assertIn(name, self.named, "adım yok: %s" % name)
            self.assertIn(INSTALL_CHROMIUM, self.names,
                          "job Chromium kurmuyor — süitler SKIP'e düşer")
            self.assertIn(CHROMIUM_STEP, self.names,
                          "Chromium doğrulanmıyor — kurulum sessizce eksik "
                          "kalabilir")
            self.assertLess(self.names.index(CHROMIUM_STEP),
                            self.names.index(name),
                            "%s Chromium doğrulamasından ÖNCE" % name)

    def test_steps_are_fail_closed(self):
        for name in (CSP_STEP, KEYBOARD_STEP):
            step = self.named[name]
            self.assertNotIn("continue-on-error", step,
                             "%s continue-on-error taşıyor" % name)
            self.assertFalse(step.get("continue-on-error"),
                             "%s continue-on-error taşıyor" % name)

    def test_csp_step_requires_browser(self):
        env = self.named[CSP_STEP].get("env") or {}
        self.assertEqual(str(env.get("LEIBNIZ2_REQUIRE_BROWSER", "")), "1",
                         "CSP adımı zorunlu-tarayıcı bayrağını taşımıyor")

    def test_steps_run_the_verbose_real_modules(self):
        for name, module in (
                (CSP_STEP, "_calisma.CIKTI.test_dashboard_csp_nonce"),
                (KEYBOARD_STEP, "_calisma.CIKTI.test_dashboard_keyboard_nav")):
            run = self.named[name]["run"]
            self.assertIn(module, run, "%s yanlış modülü koşuyor" % name)
            self.assertIn("unittest -v", run,
                          "%s unittest -v kullanmıyor" % name)

    def test_keyboard_step_rejects_zero_test_run(self):
        proc = _run_step(self.named[KEYBOARD_STEP],
                         "Ran 0 tests in 0.1s\n\nOK\n")
        self.assertNotEqual(proc.returncode, 0,
                            "0 test 'başarı' sayıldı (ölçüm yok)")

    def test_keyboard_step_rejects_skipped_run(self):
        proc = _run_step(self.named[KEYBOARD_STEP],
                         "Ran 20 tests in 0.1s\n\nOK (skipped=18)\n")
        self.assertNotEqual(proc.returncode, 0,
                            "SKIP eden klavye süiti yeşile döndü")

    def test_keyboard_step_passes_clean_run(self):
        proc = _run_step(self.named[KEYBOARD_STEP],
                         "Ran 20 tests in 0.1s\n\nOK\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_csp_step_rejects_zero_and_skipped_runs(self):
        for log in ("Ran 0 tests in 0.1s\n\nOK\n",
                    "Ran 5 tests in 0.1s\n\nOK (skipped=3)\n"):
            proc = _run_step(self.named[CSP_STEP], log)
            self.assertNotEqual(proc.returncode, 0,
                                "CSP adımı ölçümsüz koşumu kabul etti: %r"
                                % log)

    def test_csp_step_passes_clean_run(self):
        proc = _run_step(self.named[CSP_STEP],
                         "Ran 5 tests in 0.1s\n\nOK\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)


VERIFY_JOB = "verify"
HOVER_STEP = "Hover tooltip CSP suite (Chromium, SKIP = red)"
HOVER_INSTALL = "Install Chromium (hover CSP suite)"
UNIT_BATTERY = "Run CIKTI unit tests (test_*.py)"


class VerifyHoverCspContractTests(unittest.TestCase):
    """Hover-tooltip CSP kanıtı tek işe bağlı kalmamalı.

    a11y-gate'teki koşum durur/atlanırsa kanıt tümüyle kaybolurdu; `verify`
    kendi Chromium'unu kurup aynı süiti SKIP = red olarak koşar.
    """

    @classmethod
    def setUpClass(cls):
        wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        cls.steps = wf["jobs"][VERIFY_JOB]["steps"]
        cls.names = [str(s.get("name", "")) for s in cls.steps]
        cls.named = {str(s.get("name", "")): s for s in cls.steps}

    def _index(self, name):
        self.assertIn(name, self.names, "verify işinde adım yok: %s" % name)
        return self.names.index(name)

    def test_chromium_install_is_after_unit_battery(self):
        """Kurulum bataryadan ÖNCE olursa batarya tarayıcı süitlerini de koşar."""
        self.assertLess(self._index(UNIT_BATTERY), self._index(HOVER_INSTALL))
        self.assertLess(self._index(HOVER_INSTALL), self._index(HOVER_STEP))

    def test_install_step_really_installs_chromium(self):
        run = self.named[HOVER_INSTALL]["run"]
        self.assertIn("playwright install", run)
        self.assertIn("chromium", run)
        self.assertIn("--with-deps", run)

    def test_hover_step_is_fail_closed(self):
        step = self.named[HOVER_STEP]
        self.assertNotIn("continue-on-error", step,
                         "%s continue-on-error taşıyor" % HOVER_STEP)
        run = step["run"]
        self.assertIn("pipefail", run, "tee'li hatta düşen süit gizlenir")
        self.assertIn("discover -s _calisma/CIKTI", run,
                      "yanlış dizin = 0 test = vakuum")
        self.assertIn("test_design_preview_hover_csp.py", run)
        self.assertIn("check_zero_check_fail_open.py", run)
        self.assertIn("--unittest-log", run)

    def test_suite_has_a_single_skip_path(self):
        """`--unittest-log` yalnız 0-test (tam skip) vakumunu yakalar.

        Hover süitinin TEK skip koşulu modül düzeyindedir, bu yüzden tam-skip
        tespiti yeterli. Kısmi skip yolu eklenirse (ör. tek bir testte
        `skipIf`) bu kontrol kırmızıya düşer → `check_security_posture.sh`
        (her skip = red) kullanılmalı.
        """
        src = (ROOT / "_calisma" / "CIKTI"
               / "test_design_preview_hover_csp.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("skipIf("), 1,
                         "süitte ikinci bir skip koşulu var")
        self.assertEqual(src.count("skipTest("), 0,
                         "kipTest ile kısmi skip eklenmiş")

    def test_hover_evidence_names_both_jobs(self):
        """Kanıt tek işe bağlı kalmasın: a11y-gate + verify."""
        wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        a11y = wf["jobs"]["a11y-gate"]["steps"]
        blob = "\n".join(str(s.get("run", "")) for s in a11y)
        self.assertIn("check_security_posture.sh", blob,
                      "a11y-gate browser tier'ı kaybolmuş")
        self.assertIn("check_security_browser.list", blob)


if __name__ == "__main__":
    unittest.main()
