#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_precommit_doctor.py — doctor'ın KENDİ sözleşmesi.

Sözleşme (precommit_doctor modül docstring'inden):
  * git_states/state_label : işlenmemiş durum haritası (stage'li/unstaged/takipsiz)
  * parse_hooks            : stdlib config ayrıştırma (PyYAML yok)
  * extract_owners         : çıkıntı → sahip dosya (tam yol + dosya adı turları,
                             sınır-kontrollü; remedy satırları hariç)
  * attribute              : sahiplik hiyerarşisi cikti > desen > sahipsiz
                             (uydurma YOK; çözüm satırındaki Araç sahip sayılmaz)
  * run_doctor             : commit-eşdeğer evren (stage'li), yan-etki gözcüsü,
                             bilinmeyen hook id = rc 2
  * main --json            : stdout TEK JSON doküman

Tüm testler çevrimdışı: sahte runner + sahte config + (git için) scratch repo.
Her atıf assertion'ı KIRILABİLİR: sahip listesi, evren listesi ve sınır
kontrolü bilinçli olarak yanlış kurulsa kırmızıya döner.
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import precommit_doctor as pdc  # noqa: E402

REPO = HERE.parents[1]
REAL_CONFIG = REPO / ".pre-commit-config.yaml"

# Gerçek koşumdan yakalanmış çıktı (fixture kendi sözleşmesiyle tutarlı:
# header → hook id → exit code → KOŞUM gövdesi → remedy).
FIXTURE_DELTA = """\
Block commits while unstaged tracked changes exist (fail-closed)................Failed
- hook id: check-unstaged-delta
- duration: 0.06s
- exit code: 1

COMMIT BLOKE — unstaged izlenen dosya değişikliği var (ağaç KİRLİ).
  bekleyen dosyalar:
    docs/a.md
    other/b.py

Çözüm:
  git add <dosyalar>                 # bu commit'e dahil et
  ya da
  git stash push -m wip <dosyalar>   # ayrı tut, sonra geri al
sonra commit'i yeniden dene.
"""

FIXTURE_SYNC = """\
Unit tests for new gates (fail-closed manifest, incremental)..................Failed
- hook id: check-unit-tests
- duration: 0.9s
- exit code: 1

YENİ test dosyası check-unit-tests listesinde YOK: test_a11y_summary.py, test_x.py
Çözüm: python3 _calisma/CIKTI/sync_check_unit_tests.py --update (stage eder) — sonra yeniden commit et.
  remedy: python3 _calisma/CIKTI/sync_check_unit_tests.py --update
check-unit-tests: manifest/HOOK_COVERAGE drift (veya glob-kapsam) — commit bloke.
"""

CONFIG_FIXTURE = """\
repos:
  - repo: local
    hooks:
      - id: hook-red
        name: Red hook (fixture)
        entry: python3 nowhere.py
        language: system
        pass_filenames: false
        always_run: true
      - id: hook-green
        name: Green hook (fixture)
        entry: python3 nowhere.py
        language: system
        files: ^docs/
"""


def _git(repo, *args):
    proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True)
    if proc.returncode != 0:
        raise AssertionError("git %s failed: %s" % (args, proc.stderr))
    return proc.stdout


def _git_scaffold(td):
    _git(td, "init", "-q")
    _git(td, "config", "user.email", "doctor@test")
    _git(td, "config", "user.name", "doctor")
    _git(td, "config", "commit.gpgsign", "false")


def _states(entries):
    """Sözlük literalinden durum haritası (git GEREKTİRMEYEN testler için)."""
    return dict(entries)


class TestParseHooks(unittest.TestCase):
    def test_real_config_pins_known_hooks(self):
        """Gerçek .pre-commit-config.yaml ayrışır; bilinen hook nitelikleri sabit."""
        if not REAL_CONFIG.is_file():
            self.skipTest("gerçek config yok")
        hooks = pdc.parse_hooks(REAL_CONFIG.read_text(encoding="utf-8"))
        by_id = {h["id"]: h for h in hooks}
        self.assertIn("check-unstaged-delta", by_id)
        self.assertIn("check-absolute-paths", by_id)
        self.assertIn("check-verify-jobs-map", by_id)
        # files deseni OLMAYAN kapılar match-all'dir (aday atfı vermez).
        self.assertIsNone(by_id["check-unstaged-delta"]["files"])
        self.assertIsNone(by_id["check-absolute-paths"]["files"])
        self.assertFalse(by_id["check-unstaged-delta"]["pass_filenames"])
        self.assertTrue(by_id["check-absolute-paths"]["pass_filenames"])
        # Daraltan desen ham olarak korunur ve doğru eşler.
        pattern = by_id["check-verify-jobs-map"]["files"]
        self.assertIn("\\.github", pattern)
        hook = by_id["check-verify-jobs-map"]
        self.assertTrue(pdc.hook_matches(hook, ".github/workflows/verify.yml"))
        self.assertTrue(pdc.hook_matches(
            hook, "docs/superpowers/specs/2026-09-24-verify-jobs-map.excalidraw"))
        self.assertFalse(pdc.hook_matches(hook, "README.md"))
        self.assertFalse(hook["pass_filenames"])

    def test_double_quoted_files_unescapes(self):
        """Çift tırnaklı YAML `files: \"\\\\.(js|ts)$\"` → tek-ters-bağlı regex."""
        text = (
            "repos:\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: h1\n"
            "        files: \"\\\\.(js|ts)$\"\n"
        )
        hook = pdc.parse_hooks(text)[0]
        self.assertEqual(hook["files"], "\\.(js|ts)$")
        self.assertTrue(pdc.hook_matches(hook, "a.ts"))
        self.assertFalse(pdc.hook_matches(hook, "a.py"))

    def test_defaults_pass_filenames_true(self):
        text = ("repos:\n  - repo: local\n    hooks:\n"
                "      - id: h1\n        entry: x\n")
        hook = pdc.parse_hooks(text)[0]
        self.assertTrue(hook["pass_filenames"])
        self.assertFalse(hook["always_run"])
        self.assertIsNone(hook["files"])

    def test_broken_pattern_is_measurement_error_not_silent_match(self):
        """Bozuk desen → files_error; kör 'her şeyi eşler' YOK."""
        hook = {"id": "h", "files": "^(unclosed", "exclude": None}
        f_c, _ex_c, err = pdc.hook_patterns(hook)
        self.assertIsNone(f_c)
        self.assertTrue(err)


class TestStates(unittest.TestCase):
    def test_state_label_combinations(self):
        self.assertEqual(pdc.state_label({"staged": "M"}),
                         "stage'li(M değişiklik)")
        self.assertEqual(pdc.state_label({"staged": "D"}),
                         "stage'li(D silme)")
        self.assertEqual(pdc.state_label({"unstaged": "M"}), "unstaged(M)")
        self.assertEqual(pdc.state_label({"untracked": True}), "takipsiz(??)")
        self.assertIn("stage'li(A ekleme) + takipsiz(??)",
                      pdc.state_label({"staged": "A", "untracked": True}))
        self.assertEqual(pdc.state_label({}), "?")

    def test_parse_name_status_rename_takes_new_path(self):
        out = pdc._parse_name_status("R100\0old/a\0new/a\0M\0b.py\0")
        self.assertEqual(out, [("R", "new/a"), ("M", "b.py")])

    def test_git_states_scratch_repo(self):
        """Scratch repo: stage'li ekleme + unstaged değişiklik + takipsiz."""
        td = pathlib.Path(tempfile.mkdtemp(prefix="docstates_"))
        self.addCleanup(shutil.rmtree, td, True)
        _git_scaffold(td)
        (td / "committed.txt").write_text("v1\n", encoding="utf-8")
        _git(td, "add", "committed.txt")
        _git(td, "commit", "-qm", "init")
        (td / "staged.txt").write_text("s\n", encoding="utf-8")
        _git(td, "add", "staged.txt")
        (td / "committed.txt").write_text("v2\n", encoding="utf-8")  # unstaged
        (td / "loose.txt").write_text("u\n", encoding="utf-8")  # untracked

        states = pdc.git_states(td)
        self.assertEqual(states["staged.txt"].get("staged"), "A")
        self.assertEqual(states["committed.txt"].get("unstaged"), "M")
        self.assertTrue(states["loose.txt"].get("untracked"))
        self.assertIsNone(states["committed.txt"].get("staged"))


class TestOwners(unittest.TestCase):
    def test_full_path_and_basename_ordered_and_boundary_checked(self):
        states = _states({
            "docs/a.md": {"staged": "M"},
            "other/b.py": {"unstaged": "M"},
            "c.py": {"untracked": True},
        })
        out = ("şiddet: docs/a.md sonra c.py patladı; "
               "suçlu other/b.py satırında\n")
        owners = pdc.extract_owners(out, states)
        # Sıra = ilk geçiş pozisyonu (docs/a.md < c.py < other/b.py).
        self.assertEqual(owners, ["docs/a.md", "c.py", "other/b.py"])
        # Sınır: alt-süzülme yolu sahip sayılmaz.
        states2 = _states({"docs/x.md": {"staged": "M"}})
        self.assertEqual(pdc.extract_owners("other/docs/x.md patladı", states2),
                         [])
        self.assertEqual(pdc.extract_owners("prefixdocs/x.md", states2), [])
        # Sınır-pozitif: ayraçla geçen tam yol sahiptir.
        self.assertEqual(
            pdc.extract_owners("bkz: (docs/x.md) notu", states2),
            ["docs/x.md"])

    def test_remedy_lines_are_not_causal(self):
        """Çözüm satırındaki Araç dosyası sahip sayılmaz (attribute katmanı)."""
        states = _states({
            "_calisma/CIKTI/test_a11y_summary.py": {"untracked": True},
            "_calisma/CIKTI/sync_check_unit_tests.py": {"unstaged": "M"},
        })
        hook = {"id": "check-unit-tests", "files": None, "exclude": None}
        att = pdc.attribute(hook, FIXTURE_SYNC, states, [])
        self.assertEqual(att["verdict"], "sahipli")
        paths = [o["path"] for o in att["owners"]]
        self.assertIn("_calisma/CIKTI/test_a11y_summary.py", paths)
        self.assertNotIn("_calisma/CIKTI/sync_check_unit_tests.py", paths)
        self.assertTrue(att["remedy"])
        self.assertIn("sync_check_unit_tests.py --update", att["remedy"][0])

    def test_delta_fixture_attributes_unstaged_owners(self):
        """Gerçek kapı çıktısı: bekleyen dosya listesi unstaged sahipleri verir."""
        states = _states({
            "docs/a.md": {"unstaged": "M"},
            "other/b.py": {"unstaged": "M"},
        })
        hook = {"id": "check-unstaged-delta", "files": None, "exclude": None}
        att = pdc.attribute(hook, FIXTURE_DELTA, states, ["docs/a.md"])
        self.assertEqual(att["verdict"], "sahipli")
        self.assertEqual([o["path"] for o in att["owners"]],
                         ["docs/a.md", "other/b.py"])
        self.assertTrue(all("unstaged" in o["state"] for o in att["owners"]))
        self.assertTrue(att["remedy"])

    def test_verdict_hierarchy(self):
        # 1) çıktı kanıtı → sahipli (files deseni olsa bile çıktı kazanır)
        states = _states({"docs/a.md": {"staged": "M"}})
        hook = {"id": "h", "files": "^docs/", "exclude": None}
        att = pdc.attribute(hook, "FAIL: docs/a.md bayat", states, ["docs/a.md"])
        self.assertEqual(att["verdict"], "sahipli")
        self.assertEqual(att["owners"][0]["proof"], "cikti")

        # 2) çıktı yok ama açık desen var → aday (desen kanıtı)
        att = pdc.attribute(hook, "kapı kırıldı (dosya adı yok)", states,
                            ["docs/a.md"])
        self.assertEqual(att["verdict"], "aday")
        self.assertEqual(len(att["candidates"]), 1)
        self.assertEqual(att["candidates"][0]["path"], "docs/a.md")

        # 3) desen yok + çıktı yok → sahipsiz (uydurma YOK)
        hook_all = {"id": "h2", "files": None, "exclude": None}
        att = pdc.attribute(hook_all, "ölçüm imkânsız (rc=2)", states, [])
        self.assertEqual(att["verdict"], "sahipsiz")
        self.assertEqual(att["owners"], [])

    def test_committed_path_in_output_is_honest_note_not_owner(self):
        states = _states({"docs/a.md": {"staged": "M"}})
        hook = {"id": "h", "files": None, "exclude": None}
        att = pdc.attribute(hook, "FAIL: only/committed.py bayat", states, [])
        self.assertEqual(att["verdict"], "sahipsiz")
        self.assertTrue(any("COMMITTED" in n for n in att["notes"]))


class TestRunDoctor(unittest.TestCase):
    def _repo(self):
        """stage'li docs/a.md + takipsiz loose.txt + takipsiz config."""
        td = pathlib.Path(tempfile.mkdtemp(prefix="docroot_"))
        self.addCleanup(shutil.rmtree, td, True)
        _git_scaffold(td)
        (td / "docs").mkdir()
        (td / "docs" / "a.md").write_text("x\n", encoding="utf-8")
        _git(td, "add", "docs/a.md")
        (td / "loose.txt").write_text("u\n", encoding="utf-8")  # takipsiz
        (td / ".pre-commit-config.yaml").write_text(CONFIG_FIXTURE,
                                                    encoding="utf-8")
        return td

    def test_end_to_end_attribution_and_commit_universe(self):
        root = self._repo()
        seen = {}

        def runner(hook_id, files):
            seen[hook_id] = list(files)
            if hook_id == "hook-red":
                return 1, "FAIL: docs/a.md sahibi burada\nÇözüm: git add docs/a.md"
            return 0, "Passed\n"

        rc, report = pdc.run_doctor(
            root, root / ".pre-commit-config.yaml", runner)
        self.assertEqual(rc, 1)
        self.assertFalse(report["ok"])
        # Evren COMMIT-EŞDEĞER: yalnız stage'li (takipsiz dosya koşuma girmez)
        self.assertEqual(seen["hook-red"], ["docs/a.md"])
        self.assertEqual(seen["hook-green"], ["docs/a.md"])
        red = report["red"]
        self.assertEqual(len(red), 1)
        self.assertEqual(red[0]["id"], "hook-red")
        self.assertEqual(red[0]["verdict"], "sahipli")
        self.assertEqual(red[0]["owners"][0]["path"], "docs/a.md")
        self.assertIn("stage'li(A ekleme)", red[0]["owners"][0]["state"])
        self.assertEqual(report["clean"], ["hook-green"])
        self.assertEqual(report["yan_etkiler"], [])
        # Evren sayımları: stage'li 1 (docs/a.md); takipsiz 2 (config + loose)
        self.assertEqual(report["universe"]["kosum"], 1)
        self.assertEqual(report["universe"]["stage'li"], 1)
        self.assertEqual(report["universe"]["takipsiz-only"], 2)
        self.assertEqual(report["universe"]["unstaged-only"], 0)
        # Metin raporu da sahipli/kanıt bloğu basar
        blob = "\n".join(pdc.render(report))
        self.assertIn("hook-red", blob)
        self.assertIn("SAHİP (kanıt: hook çıktısı)", blob)
        self.assertIn("SONUÇ: KIRMIZI", blob)

    def test_untracked_file_can_own_via_output_but_not_universe(self):
        root = self._repo()
        seen = {}

        def runner(hook_id, files):
            seen[hook_id] = list(files)
            if hook_id == "hook-red":
                return 1, "YENİ test dosyası YOK: loose.txt"
            return 0, ""

        rc, report = pdc.run_doctor(root, root / ".pre-commit-config.yaml",
                                    runner)
        self.assertEqual(rc, 1)
        # Sahiplik kanıtı = takipsiz(??) ...
        owners = {o["path"]: o["state"] for o in report["red"][0]["owners"]}
        self.assertIn("loose.txt", owners)
        self.assertIn("takipsiz", owners["loose.txt"])
        # ... ama evren COMMIT-EŞDEĞER: takipsiz dosya argüman olarak VERİLMEZ.
        self.assertNotIn("loose.txt", seen["hook-red"])
        self.assertEqual(seen["hook-red"], ["docs/a.md"])

    def test_side_effect_watcher_reports_hook_modified_file(self):
        root = self._repo()

        def runner(hook_id, files):
            if hook_id == "hook-red":
                (root / "hook_made.md").write_text("yan etki\n",
                                                   encoding="utf-8")
                return 1, "FAIL"
            return 0, ""

        rc, report = pdc.run_doctor(root, root / ".pre-commit-config.yaml",
                                    runner)
        self.assertEqual(rc, 1)
        touched = [t["path"] for t in report["yan_etkiler"]]
        self.assertEqual(touched, ["hook_made.md"])
        self.assertEqual(report["yan_etkiler"][0]["once"], "yok")

    def test_unknown_hook_id_is_rc2(self):
        root = self._repo()
        rc, report = pdc.run_doctor(root, root / ".pre-commit-config.yaml",
                                    lambda h, f: (0, ""), only=["nope"])
        self.assertEqual(rc, 2)
        self.assertIn("bilinmeyen hook id", report["error"])

    def test_no_changes_early_exit_with_note(self):
        td = pathlib.Path(tempfile.mkdtemp(prefix="docclean_"))
        self.addCleanup(shutil.rmtree, td, True)
        _git_scaffold(td)
        (td / "f.txt").write_text("x\n", encoding="utf-8")
        _git(td, "add", "f.txt")
        _git(td, "commit", "-qm", "init")
        (td / ".pre-commit-config.yaml").write_text(CONFIG_FIXTURE,
                                                    encoding="utf-8")

        def runner_must_not_run(hook_id, files):
            raise AssertionError("stage'siz ağaçta hook koşmamalı")

        rc, report = pdc.run_doctor(td, td / ".pre-commit-config.yaml",
                                    runner_must_not_run)
        self.assertEqual(rc, 0)
        self.assertTrue(report["ok"])
        self.assertIn("--all-files", report["note"])

    def test_include_unstaged_adds_preview_paths(self):
        """Varsayılan: unstaged-only girmez. --all-changes: girer."""
        td = pathlib.Path(tempfile.mkdtemp(prefix="docprev_"))
        self.addCleanup(shutil.rmtree, td, True)
        _git_scaffold(td)
        (td / "docs").mkdir()
        (td / ".pre-commit-config.yaml").write_text(CONFIG_FIXTURE,
                                                    encoding="utf-8")
        (td / "docs" / "base.md").write_text("b\n", encoding="utf-8")
        (td / "docs" / "b.md").write_text("y\n", encoding="utf-8")
        _git(td, "add", ".pre-commit-config.yaml", "docs/base.md", "docs/b.md")
        _git(td, "commit", "-qm", "base")
        (td / "docs" / "a.md").write_text("a\n", encoding="utf-8")
        _git(td, "add", "docs/a.md")            # stage'li
        (td / "docs" / "b.md").write_text("y2\n", encoding="utf-8")  # unstaged-only

        seen_default = {}

        def runner_default(hook_id, files):
            seen_default[hook_id] = list(files)
            return 0, ""

        rc, report = pdc.run_doctor(td, td / ".pre-commit-config.yaml",
                                    runner_default)
        self.assertEqual(rc, 0)
        self.assertEqual(seen_default["hook-green"], ["docs/a.md"])
        self.assertEqual(report["universe"]["unstaged-only"], 1)

        seen_all = {}

        def runner_all(hook_id, files):
            seen_all[hook_id] = list(files)
            return 0, ""

        rc, report = pdc.run_doctor(td, td / ".pre-commit-config.yaml",
                                    runner_all, include_unstaged=True)
        self.assertEqual(rc, 0)
        self.assertIn("docs/b.md", seen_all["hook-green"])
        self.assertEqual(report["universe"]["kosum"], 2)
        self.assertEqual(report["universe"]["include_unstaged"], True)

    def test_skip_excludes_hook(self):
        """--skip: atlanan hook hiç koşmaz; kalan tek kırmızı yoksa rc 0."""
        root = self._repo()
        ran = []

        def runner(hook_id, files):
            ran.append(hook_id)
            if hook_id == "hook-red":
                return 1, "FAIL: docs/a.md"
            return 0, ""

        rc, report = pdc.run_doctor(root, root / ".pre-commit-config.yaml",
                                    runner, skip=["hook-red"])
        # Kırılabilirlik: skip çalışmasa hook-red koşar ve rc 1 olurdu.
        self.assertEqual(ran, ["hook-green"])
        self.assertEqual(rc, 0)
        self.assertEqual(report["clean"], ["hook-green"])

    def test_runner_timeout_is_rc124_and_red_not_hang(self):
        """make_runner süre aşımı: asma yok → rc 124 + not; run_doctor onu
        kırmızı sayar ama 'beklenmeyen çıkış' uydurmaz."""
        runner = pdc.make_runner(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            ".", timeout=1)
        t0 = time.monotonic()
        rc, out = runner("slow-hook", ["f.txt"])
        self.assertEqual(rc, 124)
        self.assertIn("SÜRE AŞIMI", out)
        self.assertLess(time.monotonic() - t0, 15)

        root = self._repo()
        rc, report = pdc.run_doctor(
            root, root / ".pre-commit-config.yaml",
            lambda h, f: (124, "SÜRE AŞIMI: slow-hook 1s içinde bitmedi"))
        # Kırılabilirlik: 124 beyaz-listeden çıkarılsa 'beklenmeyen' notu düşerdi.
        self.assertEqual(rc, 1)
        self.assertEqual(report["red"][0]["exit"], 124)
        self.assertFalse(any("beklenmeyen" in n
                             for n in report["red"][0]["notes"]))


class TestMainJson(unittest.TestCase):
    def _root(self):
        td = pathlib.Path(tempfile.mkdtemp(prefix="docjson_"))
        self.addCleanup(shutil.rmtree, td, True)
        _git_scaffold(td)
        (td / "docs").mkdir()
        (td / "docs" / "a.md").write_text("x\n", encoding="utf-8")
        _git(td, "add", "docs/a.md")
        (td / ".pre-commit-config.yaml").write_text(CONFIG_FIXTURE,
                                                    encoding="utf-8")
        return td

    def test_json_mode_stdout_is_single_document(self):
        """--json: stdout TEK JSON doküman; rc=1 (kırmızı hook var)."""
        td = self._root()

        def fake_runner(hook_id, files):
            if hook_id == "hook-red":
                return 1, "FAIL: docs/a.md"
            return 0, ""

        buf, err = io.StringIO(), io.StringIO()
        with mock.patch.object(pdc, "resolve_runner",
                               return_value=["fake-pre-commit"]), \
                mock.patch.object(pdc, "make_runner",
                                  return_value=fake_runner), \
                contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(err):
            rc = pdc.main(["--root", str(td), "--json"])
        payload = json.loads(buf.getvalue())  # fazladan çıktı olsa patlardı
        self.assertEqual(rc, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["rc"], 1)
        self.assertEqual(payload["red"][0]["id"], "hook-red")
        self.assertEqual(payload["red"][0]["owners"][0]["path"], "docs/a.md")

    def test_json_mode_rc2_is_still_single_document(self):
        td = self._root()
        buf = io.StringIO()
        with mock.patch.object(pdc, "resolve_runner", return_value=None), \
                contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            rc = pdc.main(["--root", str(td), "--json"])
        payload = json.loads(buf.getvalue())
        self.assertEqual(rc, 2)
        self.assertEqual(payload["rc"], 2)
        self.assertIn("pre-commit", payload["error"])


class TestMeta(unittest.TestCase):
    def test_doctor_source_has_no_absolute_user_paths(self):
        """Kendi kaynağı mutlak kullanıcı yolu taşımaz (check-absolute-paths aynası)."""
        src = (HERE / "precommit_doctor.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"/Users/[a-zA-Z][a-zA-Z0-9_-]+/", src))
        self.assertIsNone(re.search(r"/home/[a-zA-Z][a-zA-Z0-9_-]+/", src))


if __name__ == "__main__":
    unittest.main()
