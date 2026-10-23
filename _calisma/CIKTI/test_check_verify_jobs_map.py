#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_verify_jobs_map.py — verify.yml jobs-map diyagramı tazelik kapısı.

Kapı: `docs/superpowers/specs/gen_verify_jobs_map.py --check` (pre-commit hook
`check-verify-jobs-map`). Sözleşme: diyagram verify.yml'in `needs`-DAG'inin +
PUBLISH_SCENARIO job tablosunun ÜRETİLMİŞ görüntüsüdür; kaynak değişip
diyagram yeniden üretilmezse kapı fail-closed kırmızı olur.

Pinlenen davranışlar:
  * taze diyagram → rc 0; üretim idempotent (iki yazım aynı baytlar)
  * bayat diyagram (kaynak değişti, diyagram yenilenmedi) → rc 1 + çözüm
    komutu + hangi job'ın değiştiği; diyagram dosyasına YAZILMAZ (read-only)
  * diyagram yok → rc 1 (sessiz PASS yok)
  * workflow ↔ PUBLISH_SCENARIO isim kümesi farklı → rc 1 (ölçüm yapılabilir,
    ama senkron bozuk — rc 2'ye karışmamalı)
  * PyYAML yok / verify.yml yok → rc 2 (ölçüm imkânsız ≠ taze)
  * config tel: `check-verify-jobs-map` hook'u `files:` regex'iyle DÖRT yolu
    (verify.yml, PUBLISH_SCENARIO.md, üretici, diyagram) kapsar, always_run
    DEĞİLDİR (değişim-farkında) ve pass_filenames: false'tır.
  * gerçek ağacın diyagramı TAZE olmalı (kapının kendisi her ortamda
    kırmızıya dönebilen katman — tüm-skip değil)

Hermetik: her davranış testi minik bir ağacı tmp'de kurar (gerçek repo
dosyalarına YAZILMAZ); alt süreç `sys.executable` ile koşar.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT_REL = "docs/superpowers/specs/gen_verify_jobs_map.py"
MAP_REL = "docs/superpowers/specs/2026-09-24-verify-jobs-map.excalidraw"
CONFIG = ROOT / ".pre-commit-config.yaml"
HOOK_ID = "check-verify-jobs-map"

WORKFLOW = """name: verify
on: [push]
jobs:
  core:
    name: "Core gate (required)"
    runs-on: ubuntu-latest
  ext:
    name: "Extension gate (advisory)"
    needs: core
    runs-on: ubuntu-latest
"""

WORKFLOW_EXTRA = """name: verify
on: [push]
jobs:
  core:
    name: "Core gate (required)"
    runs-on: ubuntu-latest
  extra:
    name: "Extra advisory gate"
    needs: core
    runs-on: ubuntu-latest
  ext:
    name: "Extension gate (advisory)"
    needs: core
    runs-on: ubuntu-latest
"""

ROWS = [(1, "A", "Core gate (required)"), (2, "B", "Extension gate (advisory)")]
ROWS_EXTRA = ROWS + [(3, "B", "Extra advisory gate")]


def scenario(rows):
    text = ("# PUBLISH_SCENARIO (fixture)\n\n"
            "| # | Kat | İş |\n|---|-----|----|\n")
    return text + "".join("| %d | %s | %s |\n" % r for r in rows)


def make_tree(tmp, workflow=WORKFLOW, rows=ROWS):
    """Üretici + kaynak + doc iskeletini kurar (diyagram HENÜZ yok)."""
    root = pathlib.Path(tmp)
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "docs" / "superpowers" / "specs").mkdir(parents=True)
    (root / ".github" / "workflows" / "verify.yml").write_text(
        workflow, encoding="utf-8")
    (root / "docs" / "PUBLISH_SCENARIO.md").write_text(
        scenario(rows), encoding="utf-8")
    shutil.copy2(HERE.parent.parent / SCRIPT_REL, root / SCRIPT_REL)
    return root


def run_gate(root, check=True, env=None):
    argv = [sys.executable, SCRIPT_REL] + (["--check"] if check else [])
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(argv, cwd=str(root), capture_output=True, text=True,
                          env=full_env)


def hook_block():
    """Config metninden check-verify-jobs-map bloğunu çıkarır."""
    text = CONFIG.read_text(encoding="utf-8")
    start = text.index("- id: %s" % HOOK_ID)
    nxt = text.find("\n      - id: ", start + 1)
    return text[start:nxt if nxt != -1 else len(text)]


class TestFreshnessGate(unittest.TestCase):
    def test_fresh_diagram_passes_and_generation_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(tmp)
            w = run_gate(root, check=False)
            self.assertEqual(w.returncode, 0, w.stdout + w.stderr)
            first = (root / MAP_REL).read_bytes()
            # Üretim idempotent olmalı: aynı girdi → aynı baytlar.
            self.assertEqual(run_gate(root, check=False).returncode, 0)
            self.assertEqual(first, (root / MAP_REL).read_bytes())
            r = run_gate(root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("PASS", r.stdout)
            # --check READ-ONLY: taze koşumda da dosyaya dokunmaz.
            self.assertEqual(first, (root / MAP_REL).read_bytes())

    def test_stale_diagram_is_blocked_and_check_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(tmp)
            self.assertEqual(run_gate(root, check=False).returncode, 0)
            # Kaynak değişti (workflow + doc senkron), diyagram BAYAT kaldı.
            (root / ".github" / "workflows" / "verify.yml").write_text(
                WORKFLOW_EXTRA, encoding="utf-8")
            (root / "docs" / "PUBLISH_SCENARIO.md").write_text(
                scenario(ROWS_EXTRA), encoding="utf-8")
            before = (root / MAP_REL).read_bytes()
            r = run_gate(root)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("BAYAT", r.stdout)
            self.assertIn(MAP_REL, r.stdout)
            # Çözüm komutu görünür olmalı (aksi halde kapı sadece engeller).
            self.assertIn("gen_verify_jobs_map.py", r.stdout)
            # Hangi job değişti görünür (drift raporu).
            self.assertIn("Extra advisory gate", r.stdout)
            # Fail-closed ama read-only: kapı diyagrama YAZMAMALI.
            self.assertEqual(before, (root / MAP_REL).read_bytes())
            # Çözüm gerçekten çalışıyor: yeniden üret → yeşil.
            self.assertEqual(run_gate(root, check=False).returncode, 0)
            self.assertEqual(run_gate(root).returncode, 0)

    def test_missing_diagram_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(tmp)
            r = run_gate(root)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("diyagram yok", r.stdout)
            self.assertNotIn("PASS", r.stdout)

    def test_workflow_doc_drift_is_sync_error_not_measurement_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(tmp)
            self.assertEqual(run_gate(root, check=False).returncode, 0)
            # Job workflow'a eklendi ama PUBLISH_SCENARIO tablosuna işlenmedi.
            (root / ".github" / "workflows" / "verify.yml").write_text(
                WORKFLOW_EXTRA, encoding="utf-8")
            r = run_gate(root)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("SENKRON HATASI", r.stdout)
            self.assertIn("Extra advisory gate", r.stdout)

    def test_missing_pyyaml_is_measurement_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(tmp)
            shim = pathlib.Path(tmp) / "noyaml"
            shim.mkdir()
            # `import yaml` ImportError atarsa kapı rc=2 vermeli (sessiz PASS yok).
            (shim / "yaml.py").write_text(
                'raise ImportError("simulated missing PyYAML")\n',
                encoding="utf-8")
            r = run_gate(root, env={"PYTHONPATH": str(shim)})
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("PyYAML", r.stdout)

    def test_missing_workflow_is_measurement_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(tmp)
            (root / ".github" / "workflows" / "verify.yml").unlink()
            r = run_gate(root)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("kaynak dosya yok", r.stdout)


class TestHookWiring(unittest.TestCase):
    """Config tel: kapı doğru dört yolda ve değişim-farkında tetikleniyor."""

    def setUp(self):
        self.block = hook_block()

    def test_entry_runs_generator_in_check_mode(self):
        self.assertIn("gen_verify_jobs_map.py --check", self.block)

    def test_hook_is_change_aware_not_always_run(self):
        self.assertNotIn("always_run", self.block)
        self.assertIn("stages: [pre-commit]", self.block)
        self.assertIn("pass_filenames: false", self.block)

    def test_files_regex_covers_all_four_inputs(self):
        m = re.search(r"^        files: (.+)$", self.block, re.M)
        self.assertIsNotNone(m, "hook'ta `files:` yok — kapı sessizce atlanır")
        rx = m.group(1)
        for path in (".github/workflows/verify.yml", "docs/PUBLISH_SCENARIO.md",
                     SCRIPT_REL, MAP_REL):
            self.assertTrue(re.match(rx, path), "%s `files:` ile eşleşmiyor" % path)

    def test_files_regex_does_not_match_unrelated_artifacts(self):
        m = re.search(r"^        files: (.+)$", self.block, re.M)
        rx = m.group(1)
        for other in ("docs/superpowers/specs/2026-09-17-a11y-gate-dataflow.excalidraw",
                      "docs/superpowers/specs/2026-09-17-a11y-gate-design.md",
                      "_calisma/CIKTI/preview.html"):
            self.assertIsNone(re.match(rx, other),
                              "%s yanlışlıkla kapıyı tetikler" % other)

    def test_real_repo_diagram_is_fresh(self):
        """Kapının kendisi her ortamda kırmızıya dönebilen katman."""
        r = run_gate(ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_diagram_in_repo_would_be_red(self):
        """Mutasyon kontrolü: bayat diyagramla aynı kapı kırmızı olur mu?

        Gerçek diyagramı BOZMADAN, --check'in bayatlıkta rc 1 verdiğini
        kopya ağaçta doğrular; aynı kod yolu, aynı girdiler.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(tmp)
            self.assertEqual(run_gate(root, check=False).returncode, 0)
            (root / MAP_REL).write_text("{}\n", encoding="utf-8")
            r = run_gate(root)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("BAYAT", r.stdout)


if __name__ == "__main__":
    unittest.main()
