#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_verify_sweep.py — süpürme koşucusunun (verify_sweep.py) sözleşme testleri.

Seam'ler:
  - `run_sweep(steps, runner=…)`: koşucu enjekte edilebilir → ağır adımlar
    (npm build, batarya) TESTTE KOŞMAZ; verdict mantığı hermetik ölçülür.
  - `main(argv)`: CLI sözleşmesi (exit 0/1/2, tek verdict satırı, --json).
  - Gerçek-repo invariant'ları: adımların hedef dosyaları var mı, Makefile
    entry-point'i koşucuya mı delege ediyor (drift pin'i).

Kritik sözleşme: **fail-fast KAPALI** — bir adım kırılsa da kalanlar koşar
(zincir sözleşmesiyle aynı), ve koşucu OSError'ı crash değil KIRIK ADIM sayar.
"""

import contextlib
import io
import json
import os
import pathlib
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import verify_sweep as sweep  # noqa: E402

ROOT = CIKTI.parent.parent
MAKEFILE = ROOT / "Makefile"

# İstenen dört alan: cache-clean (iki kapı), token, build, batarya.
EXPECTED_STEPS = ["cache-precommit", "cache-cleanup-log", "merge-pre",
                  "tokens", "build", "battery"]


def _capture(argv, runner=None):
    """main'i çalıştırır; (rc, stdout) döndürür. runner verilirse koşucuyu
    değiştirir (test sonrası geri alınır)."""
    original = sweep.subprocess_runner
    if runner is not None:
        sweep.subprocess_runner = runner
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            rc = sweep.main(argv)
    finally:
        sweep.subprocess_runner = original
    return rc, buf.getvalue()


class FakeRunner:
    """Sahte koşucu: ad → rc haritası; çağrıları kaydeder."""

    def __init__(self, rcs=None, default=0):
        self.rcs = rcs or {}
        self.default = default
        self.calls = []

    def __call__(self, cmd, verbose):
        self.calls.append(list(cmd))
        joined = " ".join(cmd)
        for needle, rc in self.rcs.items():
            if needle in joined:
                return rc, f"sahte çıktı: {needle}\n"
        return self.default, "sahte çıktı: varsayılan\n"


class StepTableTest(unittest.TestCase):
    def test_covers_the_four_requested_domains(self):
        self.assertEqual([s.name for s in sweep.STEPS], EXPECTED_STEPS)

    def test_cache_clean_runs_first_and_battery_last(self):
        # Sıra nedenseldir: kirli cache sonraki ölçümü yanıltır → en başta;
        # en yavaş adım (batarya) en sonda.
        self.assertTrue(sweep.STEPS[0].name.startswith("cache-"))
        self.assertEqual(sweep.STEPS[-1].name, "battery")

    def test_steps_are_argv_lists_not_shell_strings(self):
        # Kabuk yok: her adım argv listesi olmalı (enjeksiyon/kotasyon yüzeyi yok).
        for step in sweep.STEPS:
            self.assertIsInstance(step.cmd, list)
            self.assertTrue(all(isinstance(part, str) for part in step.cmd))
            self.assertGreaterEqual(len(step.cmd), 2)

    def test_step_names_are_unique(self):
        names = [s.name for s in sweep.STEPS]
        self.assertEqual(len(names), len(set(names)))

    def test_commands_reference_existing_repo_paths(self):
        """Gerçek-repo invariant'ı: her adımın hedef yolu var olmalı.

        Bir kapı yeniden adlandırılırsa süpürme sessizce 'FAIL' üretmek yerine
        burada kırmızıya düşer (yol yazım hatası da yakalanır). Dosya da
        dizin de olabilir (build adımı `apps/dashboard-next` dizinini hedefler).
        """
        for step in sweep.STEPS:
            paths = [p for p in step.cmd if not p.startswith("-") and "/" in p]
            self.assertTrue(paths, f"{step.name}: göreli repo yolu yok")
            for rel in paths:
                self.assertTrue(os.path.exists(ROOT / rel),
                                f"{step.name}: hedef yok → {rel}")


class VerdictTest(unittest.TestCase):
    def test_all_pass_yields_pass_and_exit_zero(self):
        runner = FakeRunner()
        rc, out = _capture([], runner)
        self.assertEqual(rc, 0)
        self.assertIn(f"SWEEP: PASS — {len(sweep.STEPS)}/{len(sweep.STEPS)} adım yeşil", out)
        self.assertEqual(len(runner.calls), len(sweep.STEPS))

    def test_single_failure_yields_fail_and_exit_one(self):
        runner = FakeRunner({"check_tokens.py": 1})
        rc, out = _capture([], runner)
        self.assertEqual(rc, 1)
        self.assertIn("SWEEP: FAIL", out)
        self.assertIn("tokens", out.splitlines()[-1])

    def test_no_fail_fast_chain_runs_to_the_end(self):
        # İLK adım kırılsa da sonraki adımlar koşmalı (zincir sözleşmesi).
        runner = FakeRunner({"check_precommit_orphans.py": 1})
        rc, _ = _capture([], runner)
        self.assertEqual(rc, 1)
        self.assertEqual(len(runner.calls), len(sweep.STEPS))
        self.assertIn("check_unit_tests_hook.sh", runner.calls[-1][-1])

    def test_failed_step_output_tail_is_printed(self):
        runner = FakeRunner({"check_tokens.py": 1})
        _, out = _capture([], runner)
        self.assertIn("son 15 satır", out)
        self.assertIn("sahte çıktı: check_tokens.py", out)

    def test_runner_oserror_is_a_failed_step_not_a_crash(self):
        def exploding(cmd, verbose):
            raise OSError("komut yok")

        rc, out = _capture([], exploding)
        self.assertEqual(rc, 1)
        self.assertIn("SWEEP: FAIL", out)
        self.assertNotIn("Traceback", out)


class CliTest(unittest.TestCase):
    def test_dry_run_plans_without_executing(self):
        def must_not_run(cmd, verbose):  # pragma: no cover - çağrılırsa test kırılır
            raise AssertionError(f"--dry-run bir adımı koştu: {cmd}")

        rc, out = _capture(["--dry-run"], must_not_run)
        self.assertEqual(rc, 0)
        self.assertIn("SWEEP PLANI", out)
        for step in sweep.STEPS:
            self.assertIn(" ".join(step.cmd), out)

    def test_list_prints_every_step_and_command(self):
        rc, out = _capture(["--list"])
        self.assertEqual(rc, 0)
        for step in sweep.STEPS:
            self.assertIn(step.name, out)
            self.assertIn(" ".join(step.cmd), out)

    def test_only_filters_to_requested_steps(self):
        runner = FakeRunner()
        rc, out = _capture(["--only", "tokens,build"], runner)
        self.assertEqual(rc, 0)
        self.assertEqual(len(runner.calls), 2)
        self.assertIn("2/2 adım yeşil", out)

    def test_only_with_unknown_step_is_usage_error(self):
        rc, _ = _capture(["--only", "nope"], FakeRunner())
        self.assertEqual(rc, 2)

    def test_json_is_one_machine_readable_document(self):
        runner = FakeRunner({"check_tokens.py": 1})
        rc, out = _capture(["--json"], runner)
        self.assertEqual(rc, 1)
        payload = json.loads(out)          # tek JSON belgesi: ayrıştırılabilir
        self.assertEqual(payload["verdict"], "FAIL")
        names = [s["name"] for s in payload["steps"]]
        self.assertEqual(names, EXPECTED_STEPS)
        failed = [s for s in payload["steps"] if not s["ok"]]
        self.assertEqual([s["name"] for s in failed], ["tokens"])
        # Kırılan adım için çıktı kuyruğu JSON'a gömülür; geçende yok.
        self.assertIn("output_tail", failed[0])

    def test_json_on_success_has_pass_verdict(self):
        rc, out = _capture(["--json"], FakeRunner())
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["verdict"], "PASS")


class MakefileEntryPointTest(unittest.TestCase):
    """Makefile ince giriş noktasıdır ve koşucuya DELEGE etmelidir (drift pini)."""

    def setUp(self):
        self.assertTrue(MAKEFILE.exists(), "kök Makefile yok — make verify kayboldu")
        self.text = MAKEFILE.read_text(encoding="utf-8")

    def test_verify_target_delegates_to_the_sweep_runner(self):
        self.assertIn("verify:", self.text)
        self.assertIn("_calisma/CIKTI/verify_sweep.py", self.text)

    def _recipes(self, target):
        """`target:` satırından sonraki TAB'lı recipe satırları."""
        lines = self.text.splitlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{target}:"):
                out = []
                for follow in lines[i + 1:]:
                    if not follow.startswith("\t"):
                        break
                    out.append(follow)
                return out
        return []

    def test_verify_recipe_is_tab_indented(self):
        # Makefile sözleşmesi: recipe satırları TAB ile başlar. Boşlukla
        # başlarsa make 'missing separator' verir ve entry point sessizce
        # ölür — bu yüzden ölçüm hedef-güdümlüdür (`SWEEP := …` gibi değişken
        # satırları recipe sanılmaz).
        recipes = self._recipes("verify")
        self.assertTrue(recipes,
                        "verify recipe'si TAB ile başlamıyor (missing separator)")
        self.assertTrue(any("DRY" in line for line in recipes),
                        "DRY=1 planlama yolu recipe'de yok")

    def test_verify_list_target_is_a_recipe(self):
        self.assertTrue(self._recipes("verify-list"))

    def test_declares_phony_targets(self):
        self.assertIn(".PHONY:", self.text)
        for target in ("verify", "verify-list"):
            self.assertIn(target, self.text.split(".PHONY:", 1)[1].splitlines()[0])


if __name__ == "__main__":
    unittest.main()
