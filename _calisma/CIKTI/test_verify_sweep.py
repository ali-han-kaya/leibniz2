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
import time
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import local_verify as local  # noqa: E402
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


class LocalVerifyStepTableTest(unittest.TestCase):
    """`local_verify` adım tablosu: kapsam ve tek-kaynak kablolama pinleri."""

    def test_steps_cover_the_requested_four_surfaces(self):
        self.assertEqual(local.STEP_NAMES,
                         ("env", "build", "sweep", "hooks", "tree"))

    def test_sweep_scope_is_derived_from_verify_sweep_and_excludes_build(self):
        # Kopyalanmış liste drift eder: süpürmeye eklenen yeni kapı buraya
        # otomatik gelmeli, `build` ise BURADA koştuğu için dışlanmalı.
        names = local.SWEEP_ONLY.split(",")
        self.assertNotIn("build", names)
        for step in sweep.STEPS:
            if step.name != "build":
                self.assertIn(step.name, names)
        self.assertIn("battery", names)

    def test_only_filter_validates_and_preserves_canonical_order(self):
        self.assertEqual(local.select_steps(None), list(local.STEP_NAMES))
        self.assertEqual(local.select_steps("tree,build"), ["build", "tree"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(local.select_steps("build,nope"), [])

    def test_makefile_local_verify_target_delegates(self):
        text = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("local-verify:", text)
        self.assertIn("_calisma/CIKTI/local_verify.py", text)
        # Recipe TAB ile başlamalı (boşluk → 'missing separator' → hedef ölür).
        lines = text.splitlines()
        start = lines.index("local-verify:")
        self.assertTrue(lines[start + 1].startswith("\t"))


class FakeGitReader:
    """Sahte `git …` okuyucusu: komut anahtarı → (rc, stdout)."""

    def __init__(self, responses=None, rc=0):
        self.responses = responses or {}
        self.rc = rc
        self.calls = []

    def __call__(self, args):
        key = " ".join(args)
        self.calls.append(key)
        return self.responses.get(key, (self.rc, ""))


class InventoryTest(unittest.TestCase):
    """Çalışma ağacı envanteri: sınıflandırma, rename, KARMA, kesme."""

    STAGED = "diff --cached --name-status -z"
    UNSTAGED = "diff --name-status -z"
    UNTRACKED = "ls-files --others --exclude-standard -z"

    def _inventory(self, staged="", unstaged="", untracked=""):
        reader = FakeGitReader({
            self.STAGED: (0, staged),
            self.UNSTAGED: (0, unstaged),
            self.UNTRACKED: (0, untracked),
        })
        return local.working_tree_inventory("/tmp/x", reader)

    def test_classifies_and_detects_mixed_state(self):
        inventory = self._inventory(
            staged="A\0docs/a.md\0M\0docs/b.md\0",
            unstaged="M\0docs/b.md\0",
            untracked="scratch/notes.txt\0")
        self.assertEqual(inventory["staged"],
                         [("A", "docs/a.md"), ("M", "docs/b.md")])
        self.assertEqual(inventory["unstaged"], [("M", "docs/b.md")])
        self.assertEqual(inventory["untracked"], ["scratch/notes.txt"])
        # Aynı dosya hem stage hem işlenmemiş → commit kapısı bloklar.
        self.assertEqual(inventory["mixed"], ["docs/b.md"])
        self.assertNotIn("error", [k for k in inventory if inventory[k]])

    def test_rename_pair_consumes_both_paths(self):
        # `-z` biçiminde rename iki yol taşır; yanlış tüketim sonraki kaydı
        # kaydırır ve sahte yollar üretir.
        inventory = self._inventory(
            staged="R100\0old/name.py\0new/name.py\0A\0docs/x.md\0")
        self.assertEqual(inventory["staged"], [
            ("R100", "new/name.py"), ("A", "docs/x.md")])

    def test_read_failure_is_reported_not_silently_empty(self):
        reader = FakeGitReader({}, rc=128)
        inventory = local.working_tree_inventory("/tmp/x", reader)
        self.assertIn("git okunamadı", inventory["error"])
        rendered = "\n".join(local.render_inventory(inventory))
        self.assertIn("ÖLÇÜLEMEDİ", rendered)

    def test_render_counts_mixed_warning_and_truncation(self):
        inventory = self._inventory(
            staged="".join("A\0docs/%02d.md\0" % i for i in range(10)),
            unstaged="M\0docs/00.md\0",
            untracked="scratch/a\0")
        rendered = "\n".join(local.render_inventory(inventory, max_paths=3))
        self.assertIn("12 dosya", rendered)
        self.assertIn("KARMA", rendered)
        self.assertIn("ilk 3 / 10", rendered)
        self.assertIn("dizinler", rendered)
        self.assertIn("docs (10)", rendered)
        full = "\n".join(local.render_inventory(inventory, max_paths=0))
        self.assertNotIn("ilk 3", full)
        self.assertIn("docs/09.md", full)

    def test_inventory_delta_names_what_the_gates_changed(self):
        before = self._inventory(staged="A\0docs/a.md\0")
        after = self._inventory(staged="A\0docs/a.md\0M\0README.md\0")
        delta = local.inventory_delta(before, after)
        self.assertEqual(delta, {"added": ["README.md"], "removed": [],
                                 "modified": []})

    def test_content_only_edit_is_detected_by_signature(self):
        """Yol kümesi aynı kalsa da hook'un YAZMASI görünmeli."""
        import tempfile
        tmp = tempfile.mkdtemp(prefix="inventory_sig_")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        path = os.path.join(tmp, "docs", "a.md")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            f.write("bir\n")
        inventory = self._inventory(staged="M\0docs/a.md\0")
        before = local.tree_signature(inventory, tmp)
        with open(path, "w", encoding="utf-8") as f:
            f.write("bir\niki\n")  # aynı yol, farklı içerik
        after = local.tree_signature(inventory, tmp)
        delta = local.inventory_delta(inventory, inventory, before, after)
        self.assertEqual(delta["modified"], ["docs/a.md"])
        self.assertEqual(delta["added"], [])
        # Değişmemiş imza → yanlış pozitif yok.
        self.assertEqual(
            local.inventory_delta(inventory, inventory, before, before)
            ["modified"], [])


class FakeCommandRunner:
    """Sahte komut koşucusu: npm build başarılıysa BUILD_ID'yi tazeler."""

    def __init__(self, build_id=None, touch=True, rc=0):
        self.build_id = build_id
        self.touch = touch
        self.rc = rc
        self.calls = []

    def __call__(self, cmd, cwd, verbose=False):
        self.calls.append(list(cmd))
        if cmd[:2] == ["npm", "run"]:
            if self.rc != 0:
                return self.rc, "npm hata çıktısı"
            if self.touch and self.build_id:
                stamp = time.time()
                os.utime(self.build_id, (stamp, stamp))
            return 0, "derlendi"
        return 0, "ok"


class RunCommandTest(unittest.TestCase):
    """Gerçek koşucu yolu: akış + hata kuyruğu, ve OSError = kırık adım."""

    def test_keeps_a_failure_tail(self):
        script = ("import sys; print('satir1'); "
                  "print('hata', file=sys.stderr); sys.exit(3)")
        rc, output = local.run_command(["python3", "-c", script],
                                       str(ROOT), verbose=False)
        self.assertEqual(rc, 3)
        self.assertIn("satir1", output)
        self.assertIn("hata", output)

    def test_missing_command_is_a_broken_step_not_a_crash(self):
        with self.assertRaises(OSError):
            local.run_command(["definitely-not-a-real-binary-xyz"], str(ROOT))

        class Missing:
            def __call__(self, cmd, cwd, verbose=False):
                raise OSError("komut yok")

        records, _before, _after, _delta = local.run_steps(
            ["env", "tree"], runner=Missing(), reader=FakeGitReader(),
            verbose=False)
        self.assertFalse(records[0]["ok"])
        self.assertEqual(records[0]["rc"], 127)
        # Kalan adımlar koşmaya devam eder (fail-fast kapalı).
        self.assertTrue(records[1]["ok"])


class RefreshBuildTest(unittest.TestCase):
    """Derleme tazeleme: tazede npm ÇAĞRILMAZ; bayatta zorla + yeniden ölç."""

    def _tree(self, gap=5000):
        import tempfile
        tmp = tempfile.mkdtemp(prefix="local_verify_")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        build_dir = os.path.join(tmp, ".next")
        os.makedirs(build_dir)
        build_id = os.path.join(build_dir, "BUILD_ID")
        with open(build_id, "w", encoding="utf-8") as f:
            f.write("b1")
        now = time.time()
        os.utime(build_id, (now - 2 * gap, now - 2 * gap))
        src_dir = os.path.join(tmp, "app")
        os.makedirs(src_dir)
        src = os.path.join(src_dir, "page.tsx")
        with open(src, "w", encoding="utf-8") as f:
            f.write("export default 1;\n")
        os.utime(src, (now - gap, now - gap))
        inputs = [("app/page.tsx", src, now - gap)]
        return tmp, build_id, inputs

    def test_fresh_build_does_not_run_npm(self):
        tmp, build_id, _inputs = self._tree()
        now = time.time()
        os.utime(build_id, (now, now))  # derleme kaynaktan YENİ
        runner = FakeCommandRunner(build_id)
        result = local.refresh_build(runner=runner, next_dir=tmp,
                                     build_id=build_id, inputs=[])
        self.assertTrue(result["ok"])
        self.assertFalse(result["rebuilt"])
        self.assertEqual(runner.calls, [], "taze derlemede npm koşmamalı")

    def test_stale_build_is_rebuilt_then_rechecked(self):
        tmp, build_id, inputs = self._tree()
        runner = FakeCommandRunner(build_id)
        result = local.refresh_build(runner=runner, next_dir=tmp,
                                     build_id=build_id, inputs=inputs)
        self.assertTrue(result["ok"], result["detail"])
        self.assertTrue(result["rebuilt"])
        self.assertEqual(runner.calls, [local.NEXT_BUILD_CMD])
        self.assertIn("yeniden derlendi", result["detail"])

    def test_force_rebuilds_even_when_fresh(self):
        tmp, build_id, inputs = self._tree()
        now = time.time()
        os.utime(build_id, (now, now))
        runner = FakeCommandRunner(build_id)
        result = local.refresh_build(runner=runner, next_dir=tmp,
                                     build_id=build_id, inputs=inputs,
                                     force=True)
        self.assertTrue(result["ok"])
        self.assertEqual(len(runner.calls), 1)

    def test_failed_build_is_a_failure_not_a_pass(self):
        tmp, build_id, inputs = self._tree()
        runner = FakeCommandRunner(build_id, rc=1)
        result = local.refresh_build(runner=runner, next_dir=tmp,
                                     build_id=build_id, inputs=inputs)
        self.assertFalse(result["ok"])
        self.assertIn("BAŞARISIZ", result["detail"])

    def test_build_that_leaves_the_tree_stale_is_a_failure(self):
        # "npm koştu" yeşil DEĞİLDİR: yeniden ölçüm hâlâ bayatsa fail-closed.
        tmp, build_id, inputs = self._tree()
        runner = FakeCommandRunner(build_id, touch=False)
        result = local.refresh_build(runner=runner, next_dir=tmp,
                                     build_id=build_id, inputs=inputs)
        self.assertFalse(result["ok"])
        self.assertIn("hâlâ bayat", result["detail"])


class LocalVerifyCliTest(unittest.TestCase):
    """CLI sözleşmesi: dry-run planı, tek JSON belgesi, exit kodları."""

    def _run(self, argv, runner=None, reader=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            rc = local.main(argv, runner=runner or FakeCommandRunner(),
                            reader=reader or FakeGitReader())
        return rc, buf.getvalue()

    def test_dry_run_prints_plan_and_tree_without_running_steps(self):
        runner = FakeCommandRunner()
        rc, out = self._run(["--dry-run"], runner=runner)
        self.assertEqual(rc, 0)
        self.assertIn("LOCAL PLAN", out)
        self.assertIn("verify_sweep.py", out)
        self.assertIn("pre-commit run --all-files", out)
        self.assertEqual(runner.calls, [], "dry-run hiçbir adımı koşmamalı")

    def test_json_mode_emits_one_document_and_keeps_diagnostics_off_stdout(self):
        reader = FakeGitReader({
            InventoryTest.STAGED: (0, "A\0docs/a.md\0"),
            InventoryTest.UNSTAGED: (0, ""),
            InventoryTest.UNTRACKED: (0, ""),
        })
        rc, out = self._run(["--json", "--only", "tree"], reader=reader)
        self.assertEqual(rc, 0)
        payload = json.loads(out)  # tek belge: parse edilebilmeli
        self.assertEqual(payload["verdict"], "PASS")
        self.assertEqual(payload["tree"]["staged"],
                         [{"status": "A", "path": "docs/a.md"}])

    def test_failing_step_sets_exit_1_and_names_the_step(self):
        class Failing(FakeCommandRunner):
            def __call__(self, cmd, cwd, verbose=False):
                self.calls.append(list(cmd))
                return 3, "kapı kırmızı"

        rc, out = self._run(["--only", "env"], runner=Failing())
        self.assertEqual(rc, 1)
        self.assertIn("LOCAL: FAIL", out)
        self.assertIn("env", out)
        self.assertIn("kapı kırmızı", out)

    def test_fast_marks_the_hook_step_skipped_explicitly(self):
        rc, out = self._run(["--fast", "--only", "hooks"])
        self.assertEqual(rc, 0)
        self.assertIn("SKIP", out)
        self.assertIn("--fast", out)

    def test_unknown_only_returns_usage_error(self):
        rc, _out = self._run(["--only", "nope"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
