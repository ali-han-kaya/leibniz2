#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_build_artifact_overwrite.py — build artefaktı üzerine-yazma kapısı.

Sözleşme (fail-closed):
  1) Korumalı küme YALNIZ izlenen (git ls-files) `_calisma/**` + `.pdf/.zip/
     .sha256` yollarıdır; untracked build çıktısı ve `_calisma/` dışındaki
     izlenen PDF'ler kapsam dışıdır.
  2) Build öncesi snapshot → build sonrası verify: izin verilmeyen her
     değişiklik/silinme FAIL (rc=1). `--allow` yalnız adı verilen çıktıyı
     (dosya veya dizin öneki) muaf tutar, yine de ALLOW satırı basar.
  3) `--check` snapshot'sız denetim: worktree ≠ index ise FAIL; bilinçli
     re-baseline staged ise temiz.
  4) Ölçüm imkânsızsa (git yok, snapshot yok/bozuk, dosya okunamıyor) rc=2 —
     asla sessiz PASS değil.
  5) Snapshot deterministiktir (aynı ağaç → aynı bayt).

Ayrıca docs/Makefile.texlive'ın `pdf` hedefi bu kapıya gerçekten bağlı mı
(giriş noktası testi) burada değil test_makefile_texlive.py'de koşulur.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = HERE / "check_build_artifact_overwrite.py"
MAKEFILE = ROOT / "docs" / "Makefile.texlive"

PROTECTED_PDF = "_calisma/pkg/shipped.pdf"
PROTECTED_ZIP = "_calisma/CIKTI/TESLIM_V5.zip"
PROTECTED_ZIP_SHA = "_calisma/CIKTI/TESLIM_V5.zip.sha256"
PROTECTED_META_SHA = "_calisma/pkg/shipped.pdf.metadata.sha256"
UNPROTECTED_PDF = "docs/notes.pdf"
UNPROTECTED_TXT = "_calisma/pkg/notes.txt"


def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(
            os.environ,
            GIT_AUTHOR_NAME="test",
            GIT_AUTHOR_EMAIL="test@example.invalid",
            GIT_COMMITTER_NAME="test",
            GIT_COMMITTER_EMAIL="test@example.invalid",
        ),
    )


def _run(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), *args],
        capture_output=True,
        text=True,
    )


class BuildArtifactGateTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="artifact-gate-")
        self.repo = pathlib.Path(self._td.name)
        files = {
            PROTECTED_PDF: b"%PDF-shipped-v1\n",
            PROTECTED_ZIP: b"PK-shipped-zip-v1\n",
            PROTECTED_ZIP_SHA: b"deadbeef  TESLIM_V5.zip\n",
            PROTECTED_META_SHA: b"cafebabe  shipped.pdf\n",
            UNPROTECTED_PDF: b"%PDF-docs-input\n",
            UNPROTECTED_TXT: b"not an artifact\n",
        }
        for rel, body in files.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        _git(self.repo, "init", "-q")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "fixture")
        self.snapshot = self.repo / "build" / "snapshot.json"

    def tearDown(self):
        self._td.cleanup()

    def _snapshot(self):
        result = _run(self.repo, "--snapshot", str(self.snapshot))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.snapshot

    # ── 1) kapsam ───────────────────────────────────────────────────────────
    def test_list_is_tracked_and_suffix_scoped(self):
        result = _run(self.repo, "--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        listed = set(result.stdout.split())
        self.assertEqual(
            listed,
            {PROTECTED_PDF, PROTECTED_ZIP, PROTECTED_ZIP_SHA, PROTECTED_META_SHA},
            "korumalı küme = izlenen _calisma/** {pdf,zip,sha256}",
        )
        self.assertNotIn(UNPROTECTED_PDF, listed, "izlenen ama _calisma/ dışı PDF kapsam dışı")
        self.assertNotIn(UNPROTECTED_TXT, listed)

    def test_untracked_new_pdf_is_not_protected(self):
        self._snapshot()
        (self.repo / "_calisma/pkg/local-build.pdf").write_bytes(b"%PDF-local\n")
        result = _run(self.repo, "--verify", str(self.snapshot))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # ── 2) snapshot → verify ────────────────────────────────────────────────
    def test_untouched_tree_verifies_clean(self):
        self._snapshot()
        result = _run(self.repo, "--verify", str(self.snapshot))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)

    def test_pdf_overwrite_fails_and_names_path(self):
        self._snapshot()
        (self.repo / PROTECTED_PDF).write_bytes(b"%PDF-OVERWRITTEN\n")
        result = _run(self.repo, "--verify", str(self.snapshot))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL", result.stdout)
        self.assertIn(PROTECTED_PDF, result.stdout)
        self.assertIn("OVERWRITE=1", result.stdout, "çare/çıkış yolu gösterilmeli")
        self.assertIn("git checkout --", result.stdout)

    def test_zip_and_sidecars_are_all_protected(self):
        self._snapshot()
        for rel in (PROTECTED_ZIP, PROTECTED_ZIP_SHA, PROTECTED_META_SHA):
            (self.repo / rel).write_bytes(b"changed\n")
        result = _run(self.repo, "--verify", str(self.snapshot))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        for rel in (PROTECTED_ZIP, PROTECTED_ZIP_SHA, PROTECTED_META_SHA):
            self.assertIn(rel, result.stdout)

    def test_deleted_protected_artifact_fails_closed(self):
        self._snapshot()
        (self.repo / PROTECTED_PDF).unlink()
        result = _run(self.repo, "--verify", str(self.snapshot))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(PROTECTED_PDF, result.stdout)
        self.assertIn("SİLİNDİ", result.stdout)

    def test_unprotected_tracked_pdf_change_is_ignored(self):
        self._snapshot()
        (self.repo / UNPROTECTED_PDF).write_bytes(b"%PDF-changed-input\n")
        result = _run(self.repo, "--verify", str(self.snapshot))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # ── 3) --allow ─────────────────────────────────────────────────────────
    def test_allow_suppresses_only_the_named_output(self):
        self._snapshot()
        (self.repo / PROTECTED_PDF).write_bytes(b"%PDF-deliberate-rebuild\n")
        (self.repo / PROTECTED_ZIP).write_bytes(b"PK-deliberate-rebuild\n")
        result = _run(
            self.repo, "--verify", str(self.snapshot), "--allow", PROTECTED_PDF
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ALLOW", result.stdout)
        drift = result.stdout.split("FAIL: build sırasında")[1].split(
            "FAIL: izlenen artefakt"
        )[0]
        self.assertNotIn(PROTECTED_PDF, drift, "izinli dosya FAIL listesine girmemeli")
        self.assertIn(PROTECTED_ZIP, drift)

    def test_allow_accepts_directory_prefix(self):
        self._snapshot()
        for rel in (PROTECTED_PDF, PROTECTED_ZIP):
            (self.repo / rel).write_bytes(b"changed\n")
        result = _run(
            self.repo,
            "--verify",
            str(self.snapshot),
            "--allow",
            "_calisma/pkg",
            "--allow",
            "_calisma/CIKTI",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ALLOW", result.stdout)

    # ── 3b) --check-target (pre-flight) ───────────────────────────────────
    def test_check_target_blocks_tracked_output_before_build(self):
        result = _run(self.repo, "--check-target", PROTECTED_PDF)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL", result.stdout)
        self.assertIn(PROTECTED_PDF, result.stdout)
        self.assertIn("OVERWRITE=1", result.stdout)
        self.assertIn("build hiç başlamadı", result.stdout)

    def test_check_target_allows_explicitly_named_output(self):
        result = _run(
            self.repo, "--check-target", PROTECTED_PDF, "--allow", PROTECTED_PDF
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ALLOW", result.stdout)

    def test_check_target_untracked_output_passes(self):
        result = _run(
            self.repo, "--check-target", "_calisma/pkg/build-only.pdf"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("izlenmiyor", result.stdout)

    def test_check_target_unprotected_tracked_pdf_passes(self):
        result = _run(self.repo, "--check-target", UNPROTECTED_PDF)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("kapsam dışı", result.stdout)

    def test_allow_without_verify_is_rejected(self):
        result = _run(self.repo, "--list", "--allow", PROTECTED_PDF)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    # ── 4) --check ─────────────────────────────────────────────────────────
    def test_check_detects_unstaged_overwrite(self):
        (self.repo / PROTECTED_PDF).write_bytes(b"%PDF-accident\n")
        result = _run(self.repo, "--check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(PROTECTED_PDF, result.stdout)

    def test_check_passes_for_deliberate_staged_rebaseline(self):
        (self.repo / PROTECTED_PDF).write_bytes(b"%PDF-deliberate\n")
        _git(self.repo, "add", PROTECTED_PDF)
        result = _run(self.repo, "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_clean_tree_passes(self):
        result = _run(self.repo, "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)

    def test_check_detects_deleted_protected_artifact(self):
        (self.repo / PROTECTED_ZIP).unlink()
        result = _run(self.repo, "--check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(PROTECTED_ZIP, result.stdout)

    # ── 5) ölçüm hataları ──────────────────────────────────────────────────
    def test_missing_snapshot_is_measurement_error(self):
        result = _run(self.repo, "--verify", str(self.repo / "nope.json"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("snapshot yok", result.stderr)

    def test_corrupt_snapshot_is_measurement_error(self):
        self.snapshot.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot.write_text("{not json", encoding="utf-8")
        result = _run(self.repo, "--verify", str(self.snapshot))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("bozuk", result.stderr)

    def test_snapshot_schema_drift_is_measurement_error(self):
        self.snapshot.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot.write_text(
            json.dumps({"version": 999, "artifacts": {}}), encoding="utf-8"
        )
        result = _run(self.repo, "--verify", str(self.snapshot))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_empty_protected_scope_is_measurement_error(self):
        # Boş kapsam sessiz no-op bir kapı olurdu — fail-closed ölçüm hatası.
        with tempfile.TemporaryDirectory(prefix="artifact-empty-") as td:
            repo = pathlib.Path(td)
            (repo / "README.txt").write_text("no artifacts here\n", encoding="utf-8")
            _git(repo, "init", "-q")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "empty")
            for args in (("--snapshot", str(repo / "snap.json")),
                         ("--check",), ("--list",),
                         ("--check-target", "_calisma/pkg/x.pdf")):
                result = _run(repo, *args)
                self.assertEqual(result.returncode, 2,
                                 f"{args}: " + result.stdout + result.stderr)
                self.assertIn("korumalı artefakt bulunamadı", result.stderr)

    def test_non_git_directory_is_measurement_error(self):
        with tempfile.TemporaryDirectory(prefix="artifact-nogit-") as td:
            result = _run(pathlib.Path(td), "--list")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("FAIL", result.stderr)

    # ── 6) determinizm ─────────────────────────────────────────────────────
    def test_snapshot_is_byte_stable(self):
        self._snapshot()
        first = self.snapshot.read_bytes()
        self._snapshot()
        self.assertEqual(first, self.snapshot.read_bytes())
        data = json.loads(first)
        self.assertEqual(data["version"], 1)
        self.assertEqual(
            sorted(data["artifacts"]),
            sorted([PROTECTED_PDF, PROTECTED_ZIP, PROTECTED_ZIP_SHA, PROTECTED_META_SHA]),
        )


class MakefileGuardWiringTest(unittest.TestCase):
    """Statik sözleşme: Makefile kapıyı build'den ÖNCE/ SONRA doğru çağırıyor."""

    def test_texlive_pdf_is_guarded(self):
        text = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("check_build_artifact_overwrite.py", text)
        target = text.index('--check-target "$(OUTPUT)"')
        snap = text.index('--snapshot "$(GUARD_SNAPSHOT)"')
        build = text.index('"$(PDFlatex)" -interaction=nonstopmode')
        copy = text.index('@cp "$(BUILD_DIR)/$(STEM).pdf" "$(OUTPUT)"')
        verify = text.index('--verify "$(GUARD_SNAPSHOT)"')
        self.assertLess(target, build, "pre-flight build'den önce koşmalı")
        self.assertLess(snap, build, "snapshot build'den önce alınmalı")
        self.assertLess(copy, verify, "verify kopyalamadan SONRA koşmalı")
        self.assertIn("OVERWRITE ?=", text)
        self.assertIn('--allow "$(OUTPUT)"', text)

    def test_texlive_check_is_guarded_even_on_failure(self):
        text = MAKEFILE.read_text(encoding="utf-8")
        check = text[text.index("\ncheck:") : text.index("\naccept:")]
        self.assertIn("--snapshot", check)
        self.assertIn("--verify", check)
        # Deney başarısız olsa bile verify koşmalı: rc ayrı tutulur.
        self.assertIn("rc=$$?", check)
        self.assertIn("exit $$rc", check)

    def test_tectonic_pdf_is_guarded_and_check_does_not_overwrite(self):
        text = (ROOT / "docs" / "Makefile.tectonic").read_text(encoding="utf-8")
        self.assertIn("check_build_artifact_overwrite.py", text)
        self.assertIn("--check-target", text)
        self.assertIn("--snapshot", text)
        self.assertIn("--verify", text)
        self.assertIn("OVERWRITE ?=", text)
        check = text[text.index("\ncheck:"):]
        block = check.split("\n\n")[0]
        self.assertNotIn("\t@cp ", block, "check hedefi izlenen OUTPUT'a yazmamalı")
        self.assertIn('--outdir "$(BUILD_DIR)/check"', check)


if __name__ == "__main__":
    unittest.main()
