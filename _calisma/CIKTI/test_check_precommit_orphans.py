#!/usr/bin/env python3
"""test_check_precommit_orphans.py — check_precommit_orphans.py regression gate.

Seam (user-approved, tdd tour 2026-09-19): the gate's CLI — exit code and
stdout. All fixtures run against a TEMP cache dir injected via
PRE_COMMIT_HOME (pre-commit's own env override); the REAL ~/.cache/pre-commit
is never touched by tests.

Contract (root cause: pre-commit never deletes stash patches; orphans older
than the recovery window = accumulating residue + revert-incident evidence):
- a patch file aged > 24h → exit 1, output names the file and the recovery
  protocol (patch = recovery artifact, archive or delete)
- fresh patches (< 24h) are INSIDE the recovery window → exit 0 (a just-
  killed run's patch may be the only recovery artifact; never punish it)
- empty / missing cache dir → exit 0
- age boundary is strict: 24h is OK, 24h+1s trips
- fingerprint source is EVERY `recovery_patches_*` archive, not one pinned
  date (2026-09-27: the 09-20 and 09-26 archives were invisible, so replicas
  of those deltas got no KNOWN-INCIDENT label); a fresh patch whose content
  matches an archive warns without blocking (recurrence signal)
"""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

HERE = pathlib.Path(__file__).resolve().parent
GATE = HERE / "check_precommit_orphans.py"
HOUR = 3600


def run_gate(cache_dir: pathlib.Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PRE_COMMIT_HOME=str(cache_dir))
    return subprocess.run(
        [sys.executable, str(GATE)],
        capture_output=True, text=True, timeout=10, env=env,
    )


def make_cache(patch_ages_h) -> pathlib.Path:
    td = pathlib.Path(tempfile.mkdtemp())
    if patch_ages_h:
        for i, age_h in enumerate(patch_ages_h):
            p = td / f"patch1789000000-{1000 + i}"
            p.write_text("diff --git a/x b/x\n", encoding="utf-8")
            old = time.time() - age_h * HOUR
            os.utime(p, (old, old))
    return td


ARCHIVE = HERE / "recovery_patches_20260918"


def make_cache_with_archive_content(patch_ages_h) -> pathlib.Path:
    """Cache whose patch CONTENT is byte-identical to the archived
    2026-09-18 incident patch (fingerprint match)."""
    td = make_cache(patch_ages_h)
    incident = next(ARCHIVE.glob("patch1789754982*"))
    p = td / "patch9999000000-77777"
    p.write_bytes(incident.read_bytes())
    old = time.time() - patch_ages_h[0] * HOUR
    os.utime(p, (old, old))
    return td


import shutil


class TestPrecommitOrphanGate(unittest.TestCase):
    def test_patch_older_than_24h_fails_with_recovery_guidance(self):
        td = make_cache([25.0])
        try:
            r = run_gate(td)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            out = r.stdout + r.stderr
            self.assertIn("patch1789000000-1000", out, "output must name the orphan")
            self.assertIn("recovery", out.lower(), "output must state the recovery protocol")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_fresh_patch_inside_window_passes(self):
        # a just-killed run's patch may be the only recovery artifact
        td = make_cache([1.0])
        try:
            r = run_gate(td)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_age_boundary_is_strict(self):
        # 24h exactly = inside window; 24h + 1s = orphan
        td = make_cache([24.0 + 1 / HOUR])
        try:
            r = run_gate(td)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_multiple_orphans_all_named(self):
        td = make_cache([30.0, 48.0])
        try:
            r = run_gate(td)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            out = r.stdout + r.stderr
            self.assertIn("patch1789000000-1000", out)
            self.assertIn("patch1789000000-1001", out)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_empty_cache_dir_passes(self):
        td = make_cache(None)
        try:
            r = run_gate(td)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_missing_cache_dir_passes(self):
        td = pathlib.Path(tempfile.mkdtemp()) / "nope"
        try:
            r = run_gate(td)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            shutil.rmtree(td.parent, ignore_errors=True)

    def test_known_incident_fingerprint_gets_recovery_warning(self):
        # orphan content byte-identical to the archived 2026-09-18 incident
        # patch → output must carry the KNOWN-INCIDENT recovery warning
        td = make_cache_with_archive_content([30.0])
        try:
            r = run_gate(td)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            out = r.stdout + r.stderr
            self.assertIn("KNOWN-INCIDENT", out)
            self.assertIn("patch1789754982-84993", out)
            self.assertIn("recovery_patches_20260918", out)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_unknown_orphan_gets_no_known_incident_marker(self):
        td = make_cache([30.0])
        try:
            r = run_gate(td)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertNotIn("KNOWN-INCIDENT", r.stdout + r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_archive_glob_covers_every_dated_archive_dir(self):
        # 2026-09-27: tek dizin sabitlemesi sonraki arşivleri görünmez kılar.
        # Parmak-izi kaynağı glob olmalı; sabit tarih yasağı statik olarak
        # pinlenir (yeni arşiv eklenince kaynak kendiliğinden genişler).
        src = GATE.read_text(encoding="utf-8")
        self.assertIn('ARCHIVE_GLOB = "recovery_patches_*"', src)
        self.assertNotIn('"recovery_patches_2026', src,
                         "arşiv yolu sabitlenmemeli — glob kullan")

    def test_every_archive_contributes_fingerprints(self):
        # Dinamik: her arşiv dizininden en az bir parmak-izi yüklenmeli.
        spec = importlib.util.spec_from_file_location("orphan_gate", GATE)
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        known = gate.archive_fingerprints()
        archives = sorted(p for p in HERE.glob("recovery_patches_*") if p.is_dir())
        self.assertTrue(archives, "arşiv dizini yok — test anlamsızlaşır")
        seen = {loc.split("/", 1)[0] for locs in known.values() for loc in locs}
        for d in archives:
            self.assertIn(d.name, seen, f"arşiv parmak-izi yüklenmedi: {d.name}")

    def test_later_archive_fingerprint_is_recognised(self):
        # 09-18 dışındaki bir arşivden gelen kopya da KNOWN-INCIDENT almalı.
        archive = HERE / "recovery_patches_20260926"
        sample = sorted(p for p in archive.glob("patch*") if p.is_file())
        self.assertTrue(sample, "2026-09-26 arşivi boş — kapsam testi kurulamaz")
        original = sample[0]
        td = make_cache(None)
        try:
            p = td / "patch9999000001-88888"
            p.write_bytes(original.read_bytes())
            old = time.time() - 30 * HOUR
            os.utime(p, (old, old))
            r = run_gate(td)
            out = r.stdout + r.stderr
            self.assertEqual(r.returncode, 1, out)
            self.assertIn("KNOWN-INCIDENT", out)
            self.assertIn(f"{archive.name}/{original.name}", out,
                          "eşleşen arşiv dosyası adıyla anılmalı")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_fresh_recurrence_warns_but_does_not_block(self):
        # Taze patch kurtarma penceresinde → exit 0; ama içerik arşivle aynıysa
        # tekrar-olay sessiz kalmamalı.
        incident = next(ARCHIVE.glob("patch1789754982*"))
        td = make_cache(None)
        try:
            p = td / "patch9999000002-99999"
            p.write_bytes(incident.read_bytes())  # mtime = şimdi
            r = run_gate(td)
            out = r.stdout + r.stderr
            self.assertEqual(r.returncode, 0, out)
            self.assertIn("KNOWN-INCIDENT", out)
            self.assertIn("bloklamaz", out)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_orphan_report_states_archive_surface(self):
        # Yetim bildirirken kaynağın kapsamı görünmeli (kaç dizin/patch) —
        # aksi halde "etiket yok" ile "arşiv boş" ayırt edilemez.
        td = make_cache([30.0])
        try:
            r = run_gate(td)
            out = r.stdout + r.stderr
            self.assertEqual(r.returncode, 1, out)
            self.assertIn("arşiv parmak-izleri:", out)
            self.assertRegex(out, r"arşiv parmak-izleri: [1-9]\d* dizin / [1-9]\d* patch")
        finally:
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
