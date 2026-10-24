#!/usr/bin/env python3
"""test_prettier_ci_gate.py — Prettier kapısının CI/yerel sözleşmesi.

İki tarafı birlikte pin'ler, çünkü asıl hata sınıfı "yerelde SKIP, CI'da
sessiz yeşil":

  CI (verify.yml → quality-gates):
    * adım `Install dashboard-next deps` (npm ci) adımından SONRA koşar —
      prettier ikilisi oraya kurulur;
    * adımın TEK yuvası vardır (2026-10-21'de dashboard-smoke'tan taşındı):
      aynı kapının iki job'da farklı bayraklarla koşması drift'tir —
      `test_step_has_single_home` dashboard-smoke'ta kalırsa kırmızı olur;
    * `continue-on-error` YOK (fail-closed);
    * `--all-tracked` (tüm takipli yüzey) + `--require-prettier` (prettier
      yoksa rc=2) KULLANILIR — değişim yüzeyi değil, yani sıfır dosyalı bir
      PR'da "hüküm yok" diyip geçemez;
    * çıktıda `check-prettier-format: OK (N dosya)` cümlesi ve N > 0 aranır —
      script dosyaları yok sayıp "SKIP" + rc=0 dönerse adım KIRMIZI olur.

  Yerel (pre-commit):
    * `check-prettier-format*` hook'ları `--require-prettier` GEÇMEZ:
      prettier kurulu değilse SKIP etmeleri bilinçli (ortam-bağımlı kapı
      yerelde commit'i bloke etmesin) — advisory yalnız burada.

Adımın shell gövdesi sahte bir `python3` ile GERÇEKTEN koşulur: "OK (0
dosya)" ve "SKIP" çıktıları kırmızıya düşmeli, "OK (N>0 dosya)" geçmeli.

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
PRECOMMIT = ROOT / ".pre-commit-config.yaml"

STEP_NAME = "Prettier format check — all tracked (fail-closed)"
NPM_STEP = "Install dashboard-next deps"


JOB = "quality-gates"


def _job_steps(job=JOB):
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return wf["jobs"][job]["steps"]


def _steps_by_name():
    steps = _job_steps()
    return steps, {str(s.get("name", "")): s for s in steps}


def _run_step(run, output, returncode=0):
    """Adımın shell gövdesini sahte `python3` ile koş.

    Gerçek prettier/node gerekmez: adımın kendi çıktı-hükmü (OK + N>0)
    sınanır. Sahte ikili PATH'in başına konur, böylece tee/sed/grep gerçek
    kalır.
    """
    with tempfile.TemporaryDirectory() as td:
        fake = pathlib.Path(td) / "python3"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$FAKE_OUT\"\n"
            "exit \"${FAKE_RC:-0}\"\n",
            encoding="utf-8")
        fake.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = td + os.pathsep + env.get("PATH", "")
        env["FAKE_OUT"] = output
        env["FAKE_RC"] = str(returncode)
        return subprocess.run(["bash", "-c", run], env=env,
                              capture_output=True, text=True, timeout=30)


class TestCiPrettierStep(unittest.TestCase):
    def test_step_exists_and_runs_after_npm_ci(self):
        steps, named = _steps_by_name()
        names = [str(s.get("name", "")) for s in steps]
        self.assertIn(STEP_NAME, named, "CI prettier adımı yok")
        self.assertIn(NPM_STEP, named, "npm ci adımı yok — sıra iddiası boş")
        self.assertLess(names.index(NPM_STEP), names.index(STEP_NAME),
                        "prettier adımı npm ci'DEN ÖNCE koşuyor: prettier "
                        "kurulmamış olur ve kapı ölçemez")

    def test_step_has_single_home(self):
        """Kapı TEK job'da koşar: ikinci bir kopya bayrak drift'i üretir."""
        for job in ("dashboard-smoke",):
            names = [str(s.get("name", "")) for s in _job_steps(job)]
            self.assertNotIn(STEP_NAME, names,
                             "prettier adımı %s içinde ikinci kez koşuyor "
                             "(tek yuvası quality-gates)" % job)

    def test_step_is_fail_closed_not_advisory(self):
        _steps, named = _steps_by_name()
        step = named[STEP_NAME]
        self.assertNotIn("continue-on-error", step,
                         "CI'da continue-on-error advisory'ye çevirir")
        self.assertFalse(step.get("continue-on-error"),
                         "CI'da continue-on-error advisory'ye çevirir")
        run = step["run"]
        self.assertIn("--all-tracked", run,
                      "değişim yüzeyi taraması: 0 dosyalı PR sessizce geçer")
        self.assertIn("--require-prettier", run,
                      "prettier yokluğu CI'da SKIP'e dönüşür (fail-open)")
        self.assertNotIn("--diff", run,
                         "değişim yüzeyi modu hâlâ kullanılıyor")

    def test_step_cannot_pass_on_skip_or_zero_file_output(self):
        _steps, named = _steps_by_name()
        run = named[STEP_NAME]["run"]
        self.assertIn("check-prettier-format: OK \\(", run,
                      "OK (N dosya) koruması yok — SKIP çıktısı sessizce "
                      "geçerdi")
        self.assertIn("exit 1", run)

    def test_zero_file_output_is_red(self):
        run = _steps_by_name()[1][STEP_NAME]["run"]
        proc = _run_step(run, "check-prettier-format: OK (0 dosya)")
        self.assertNotEqual(proc.returncode, 0,
                            "0 dosya 'temiz' sayıldı (ölçüm yok)")

    def test_skip_output_is_red(self):
        run = _steps_by_name()[1][STEP_NAME]["run"]
        proc = _run_step(run, "check-prettier-format: SKIP")
        self.assertNotEqual(proc.returncode, 0,
                            "SKIP çıktısı adımı yeşile döndürdü")

    def test_positive_measurement_passes(self):
        run = _steps_by_name()[1][STEP_NAME]["run"]
        proc = _run_step(run, "check-prettier-format: OK (153 dosya)")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_script_failure_is_propagated(self):
        run = _steps_by_name()[1][STEP_NAME]["run"]
        proc = _run_step(run, "check-prettier-format: HATA", returncode=2)
        self.assertNotEqual(proc.returncode, 0,
                            "script rc=2 adımda yutuldu")
        self.assertIn("check-prettier-format: HATA", proc.stdout,
                      "script tanısı yutuldu (rc yolu çıktıyı basmıyor)")


class TestLocalHookStaysAdvisory(unittest.TestCase):
    def test_hooks_do_not_require_prettier(self):
        cfg = yaml.safe_load(PRECOMMIT.read_text(encoding="utf-8"))
        hooks = {h["id"]: h for repo in cfg["repos"] for h in repo["hooks"]}
        for hook_id in ("check-prettier-format", "check-prettier-format-all"):
            self.assertIn(hook_id, hooks, "hook silinmiş: %s" % hook_id)
            entry = str(hooks[hook_id]["entry"])
            self.assertNotIn(
                "--require-prettier", entry,
                "%s hook'u --require-prettier geçiyor: yerelde prettier "
                "kurulu değilken commit bloklanır; SKIP yalnız yerel "
                "advisory olarak kalmalı (fail-closed tarafı CI'dır)"
                % hook_id)


if __name__ == "__main__":
    unittest.main()
