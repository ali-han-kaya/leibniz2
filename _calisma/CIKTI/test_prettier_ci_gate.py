#!/usr/bin/env python3
"""test_prettier_ci_gate.py — Prettier kapısının CI/yerel sözleşmesi.

İki tarafı birlikte pin'ler, çünkü asıl hata sınıfı "yerelde SKIP, CI'da
sessiz yeşil":

  CI (verify.yml → dashboard-smoke):
    * adım `Install dashboard-next deps` (npm ci) adımından SONRA koşar —
      prettier ikilisi oraya kurulur;
    * `continue-on-error` YOK (fail-closed);
    * `--require-prettier` (prettier yoksa rc=2) KULLANILIR;
    * çıktıda `check-prettier-format: OK (N dosya)` cümlesi aranır — script
      sürümü verilen dosyaları yok sayıp "SKIP" + rc=0 dönerse adım yine
      kırmızı olsun (ölçüldü: HEAD'deki script bayrağı tanımıyordu);
    * kapsam deseni `check_prettier_format.INCLUDED_SUFFIXES` /
      `EXCLUDED_NAMES` ile AYNI — kopya sessizce sürüklenemez.
  Yerel (pre-commit):
    * `check-prettier-format*` hook'ları `--require-prettier` GEÇMEZ:
      prettier kurulu değilse SKIP etmeleri bilinçli (ortam-bağımlı kapı
      yerelde commit'i bloke etmesin) — advisory yalnız burada.

stdlib unittest — yaml gerekir (repo bataryasında kurulu).
"""
import importlib.util
import pathlib
import unittest

import yaml

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"
PRECOMMIT = ROOT / ".pre-commit-config.yaml"
SCRIPT = HERE / "check_prettier_format.py"

STEP_NAME = "Prettier format check — change surface (fail-closed)"
NPM_STEP = "Install dashboard-next deps"


def _steps_by_name():
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = wf["jobs"]["dashboard-smoke"]["steps"]
    return steps, {str(s.get("name", "")): s for s in steps}


def _load_script():
    spec = importlib.util.spec_from_file_location("cpf", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCiPrettierStep(unittest.TestCase):
    def test_step_exists_and_runs_after_npm_ci(self):
        steps, named = _steps_by_name()
        names = [str(s.get("name", "")) for s in steps]
        self.assertIn(STEP_NAME, named, "CI prettier adımı yok")
        self.assertIn(NPM_STEP, named, "npm ci adımı yok — sıra iddiası boş")
        self.assertLess(names.index(NPM_STEP), names.index(STEP_NAME),
                        "prettier adımı npm ci'DEN ÖNCE koşuyor: prettier "
                        "kurulmamış olur ve kapı ölçemez")

    def test_step_is_fail_closed_not_advisory(self):
        _steps, named = _steps_by_name()
        step = named[STEP_NAME]
        self.assertNotIn("continue-on-error", step,
                         "CI'da continue-on-error advisory'ye çevirir")
        self.assertFalse(step.get("continue-on-error"),
                         "CI'da continue-on-error advisory'ye çevirir")
        run = step["run"]
        self.assertIn("--require-prettier", run,
                      "prettier yokluğu CI'da SKIP'e dönüşür (fail-open)")
        self.assertIn("apps/dashboard-next/node_modules/.bin/prettier", run,
                      "npm ci'nin kurduğu ikili doğrulanmıyor")

    def test_step_cannot_pass_on_skip_output(self):
        """Script 'SKIP' deyip rc=0 dönerse adım KIRMIZI olmalı."""
        _steps, named = _steps_by_name()
        run = named[STEP_NAME]["run"]
        self.assertIn("check-prettier-format: OK (", run,
                      "OK (N dosya) koruması yok — SKIP çıktısı sessizce "
                      "geçerdi")
        # Koruma gerçekten test ediyor mu: adım SKIP metnini tanıyıp
        # exit 1 vermez, BEKLENEN cümleyi arayıp bulamayınca verir.
        self.assertIn("exit 1", run)

    def test_scope_pattern_matches_the_script(self):
        """CI'daki dosya seçimi script'in kapsam sabitleriyle birebir."""
        mod = _load_script()
        run = _steps_by_name()[1][STEP_NAME]["run"]
        for suffix in mod.INCLUDED_SUFFIXES:
            self.assertIn("*" + suffix, run,
                          "CI kapsamı script'ten koptu: %s" % suffix)
        for name in mod.EXCLUDED_NAMES:
            self.assertIn(name, run,
                          "CI kapsamı script'in hariç tuttuğu dosyayı "
                          "denetliyor: %s" % name)


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
