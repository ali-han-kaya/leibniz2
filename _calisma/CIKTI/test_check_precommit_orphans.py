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

AUTO-QUARANTINE tour (2026-09-28) — residue ACCUMULATES, and hand-cleaning
does not scale, but blind deletion is DATA LOSS. Proven-redundant orphans are
MOVED (never deleted) with a MANIFEST; the rest stay fail-closed:
- `rev-apply` proof: `git apply --reverse --check` clean → the tree is already
  the patch's post-state.
- `+lines` proof: every substantive added line is present in its target file.
- a patch with NO `@@` hunk is never moved — measured: `git apply --check`
  returns 0 on a hunk-less diff (nothing to apply), so it would look
  "redundant"; the gate's own legacy fixture is exactly `diff --git a/x b/x`.
- trivial added lines (`}`, blank) are not evidence (false positives).
- KNOWN-INCIDENT / WEAK patches are never moved: the label is a WARNING, never
  an exemption, and those records prove the incident RECURRED.
- fresh patches are never touched (live recovery window).
"""
import importlib.util
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import unittest

BANNER = "BİLİNEN OLAY PARMAK-İZİ"
WEAK_BANNER = "ZAYIF-PARMAK-İZİ ÇAKIŞMASI"
MD5_HEX = "[0-9a-f]{32}"

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


def _load_gate():
    """Kapıyı modül olarak yükler (saf fonksiyon dalları için CLI'sız seam)."""
    spec = importlib.util.spec_from_file_location("orphan_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = HERE.parent.parent
TOKEN = "unique-token-abcdef123456"


def run_gate_args(cache_dir, *args) -> subprocess.CompletedProcess:
    """Kapıyı ek CLI argümanlarıyla koşar (otomatik-karantina testleri)."""
    env = dict(os.environ, PRE_COMMIT_HOME=str(cache_dir))
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        capture_output=True, text=True, timeout=30, env=env,
    )


def make_root(line_present: bool = True) -> pathlib.Path:
    """Sahte ölçüm kökü: hedef dosya + içinde (istenirse) kanıt satırı."""
    root = pathlib.Path(tempfile.mkdtemp())
    body = f"alpha\n{TOKEN}\nomega\n" if line_present else "alpha\nomega\n"
    (root / "sample.txt").write_text(body, encoding="utf-8")
    return root


def make_patch(cache, name, added_lines, age_h, rel="sample.txt"):
    """Gerçek `git diff` biçiminde, hunk'lı, tek dosyalık fixture patch."""
    plus = "".join(f"+{line}\n" for line in added_lines)
    patch = cache / name
    patch.write_text(
        f"diff --git a/{rel} b/{rel}\n"
        "index 1111111..2222222 100644\n"
        f"--- a/{rel}\n"
        f"+++ b/{rel}\n"
        "@@ -1,2 +1,3 @@\n"
        " alpha\n"
        f"{plus}"
        " omega\n",
        encoding="utf-8",
    )
    old = time.time() - age_h * HOUR
    os.utime(patch, (old, old))
    return patch


def _find_redundant_archive_patch():
    """Arşivde AYNI ZAMANDA kanıtlanmış-redundant bir patch (policy testi için)."""
    gate = _load_gate()
    for archive in sorted(HERE.glob("recovery_patches_*")):
        for patch in sorted(p for p in archive.glob("patch*") if p.is_file()):
            if gate.redundancy_evidence(patch, ROOT) is not None:
                return patch
    return None


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
        # Dinamik: her arşiv dizininden en az bir parmak-izi yüklenmeli —
        # ve İKİ haritaya da (sha256 otorite, md5 ikinci sinyal).
        known = _load_gate().archive_fingerprints()
        archives = sorted(p for p in HERE.glob("recovery_patches_*") if p.is_dir())
        self.assertTrue(archives, "arşiv dizini yok — test anlamsızlaşır")
        for name in ("sha256", "md5"):
            table = getattr(known, name)
            seen = {loc.split("/", 1)[0] for locs in table.values() for loc in locs}
            for d in archives:
                self.assertIn(d.name, seen,
                              f"{name} parmak-izi yüklenmedi: {d.name}")
        self.assertEqual(
            known.patch_count,
            sum(1 for d in archives for p in d.glob("patch*") if p.is_file()),
            "arşiv patch sayısı sayımı tutarsız")

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

    def test_known_incident_prints_dedicated_warning_block(self):
        # Bilinen-olay eşleşmesi yetim listesinin içine gömülü satır
        # olmaktan çıkmalı: scroll'layıp geçilen bir uyarı uyarı değildir.
        # Taze/yetim fark etmez — TEK özel blok, dosya adıyla birlikte.
        incident = next(ARCHIVE.glob("patch1789754982*"))
        td = make_cache(None)
        try:
            p = td / "patch9999000003-77777"
            p.write_bytes(incident.read_bytes())
            old = time.time() - 30 * HOUR
            os.utime(p, (old, old))
            r = run_gate(td)
            out = r.stdout + r.stderr
            self.assertEqual(r.returncode, 1, out)
            self.assertIn(BANNER, out, "özel bilinen-olay uyarı bloğu yok")
            self.assertIn("KNOWN-INCIDENT", out)
            self.assertIn("patch1789754982-84993", out,
                          "eşleşen arşiv dosyası adıyla anılmalı")
            # blok kendi satırında, eşleşen patch altında gruplanmalı
            self.assertRegex(out, re.escape(BANNER) + r"[\s\S]*patch9999000003-77777")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_known_incident_block_reports_both_digests(self):
        # İki parmak-izi: sha256 (otorite, birebir) + md5 (32 hex, kısa —
        # olay notlarına yapıştırılabilir). İkisi de görünmeli ki eşleşme
        # sonradan elle doğrulanabilsin.
        import hashlib
        incident = next(ARCHIVE.glob("patch1789754982*"))
        td = make_cache(None)
        try:
            p = td / "patch9999000004-77777"
            p.write_bytes(incident.read_bytes())
            old = time.time() - 30 * HOUR
            os.utime(p, (old, old))
            r = run_gate(td)
            out = r.stdout + r.stderr
            self.assertRegex(out, MD5_HEX, "md5 (32 hex) basılmalı")
            self.assertRegex(out, "[0-9a-f]{64}", "sha256 (64 hex) basılmalı")
            self.assertEqual(
                hashlib.md5(incident.read_bytes()).hexdigest() in out, True,
                "arşiv içeriğinin md5'si çıktıda olmalı")
            self.assertEqual(
                hashlib.sha256(incident.read_bytes()).hexdigest() in out, True,
                "arşiv içeriğinin sha256'sı çıktıda olmalı")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_md5_match_alone_never_labels_known_incident(self):
        # md5 tek başına ORACLE olamaz: kasıtlı çakıştırılabilir. sha256
        # eşleşmediyse etiket düşer, sonuç ayrı bir tanıya iner. Gerçek bir
        # md5 çakışması üretmek üretim-dışı olduğundan bu dal SAF fonksiyon
        # (classify) üzerinden kilitlenir — CLI aynı sınıflandırmayı kullanır.
        gate = _load_gate()
        prints = gate.Fingerprints(
            sha256={"a" * 64: ["recovery_patches_X/patch1"]},
            md5={"b" * 32: ["recovery_patches_Y/patch2"]},
            archives=["recovery_patches_X"], patch_count=1)
        label, locs = gate.classify(prints, "c" * 64, "b" * 32)
        self.assertNotEqual(label, gate.KNOWN,
                            "sha256 eşleşmeden KNOWN-INCIDENT üretilemez")
        self.assertEqual(label, gate.WEAK, "zayif-eşleşme tanısı beklenir")
        self.assertEqual(locs, ["recovery_patches_Y/patch2"])
        # sha256 birebir eşleşirse md5'ye bakılmaz (otorite sırası)
        label, locs = gate.classify(prints, "a" * 64, "0" * 32)
        self.assertEqual(label, gate.KNOWN)
        self.assertEqual(locs, ["recovery_patches_X/patch1"])
        # hiç eşleşme yok → etiket yok
        self.assertEqual(gate.classify(prints, "d" * 64, "e" * 32),
                         (gate.NONE, []))

    def test_unknown_orphan_prints_no_digest_noise(self):
        # Eşleşme yokken parmak-izi basmak gürültüdür: operatör kırmızıyı
        # gerçekten kaçırır. Tanı boşken hiçbir etiket/özet satırı olmamalı.
        td = make_cache([30.0])
        try:
            r = run_gate(td)
            out = r.stdout + r.stderr
            self.assertNotIn(BANNER, out)
            self.assertNotIn(WEAK_BANNER, out)
            self.assertNotIn("KNOWN-INCIDENT", out)
            self.assertNotRegex(out, MD5_HEX, "eşleşme yokken md5 basılmamalı")
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

    def test_empty_archive_blinds_both_digests(self):
        # Arşiv kaybolursa iki harita da boşalır — kontrol körleşmemeli:
        # kapı bunu görünürce "parmak-izi üretilemedi" demeli.
        src = GATE.read_text(encoding="utf-8")
        self.assertIn("parmak-izi üretilemedi", src)


class TestAutoQuarantine(unittest.TestCase):
    """Kanıtlanmış gereksiz yetim TAŞINIR (silinmez), kanıtlanamayan BLOKLAR."""

    def test_redundant_orphan_is_quarantined_and_unblocks(self):
        cache = make_cache(None)
        root = make_root(line_present=True)
        try:
            patch = make_patch(cache, "patch1789000001-2000", [TOKEN], 30.0)
            r = run_gate_args(cache, "--root", str(root))
            out = r.stdout + r.stderr
            self.assertEqual(r.returncode, 0, out)   # kanıt var → commit bloklanmaz
            self.assertIn("OTOMATİK KARANTİNA", out)
            self.assertIn(patch.name, out)
            self.assertFalse(patch.exists(), "taşınmış olmalı")
            dest = _load_gate().quarantine_dir(cache)
            self.assertTrue((dest / patch.name).is_file(), "karantinada olmalı")
            self.assertTrue((dest / "MANIFEST.md").is_file(), "MANIFEST yazılmalı")
        finally:
            shutil.rmtree(cache, ignore_errors=True)
            shutil.rmtree(root, ignore_errors=True)

    def test_quarantine_is_reversible_move_not_delete(self):
        # AGENTS.md: "silme yerine karantina" — taşıma geri alınabilmeli.
        gate = _load_gate()
        cache = make_cache(None)
        root = make_root(line_present=True)
        try:
            patch = make_patch(cache, "patch1789000002-2001", [TOKEN], 40.0)
            original = patch.read_bytes()
            run_gate_args(cache, "--root", str(root))
            moved = gate.quarantine_dir(cache) / patch.name
            self.assertEqual(moved.read_bytes(), original,
                             "taşınan kopya bayt-birebir aynı olmalı")
        finally:
            shutil.rmtree(cache, ignore_errors=True)
            shutil.rmtree(root, ignore_errors=True)

    def test_manifest_records_digests_and_evidence(self):
        import hashlib
        gate = _load_gate()
        cache = make_cache(None)
        root = make_root(line_present=True)
        try:
            patch = make_patch(cache, "patch1789000003-2002", [TOKEN], 30.0)
            data = patch.read_bytes()
            run_gate_args(cache, "--root", str(root))
            manifest = (gate.quarantine_dir(cache) / "MANIFEST.md").read_text(
                encoding="utf-8")
            self.assertIn(hashlib.sha256(data).hexdigest(), manifest)
            self.assertIn(hashlib.md5(data).hexdigest(), manifest)
            self.assertIn(gate.EVIDENCE_LINES, manifest)
            self.assertIn(patch.name, manifest)
        finally:
            shutil.rmtree(cache, ignore_errors=True)
            shutil.rmtree(root, ignore_errors=True)

    def test_digests_stay_out_of_stdout(self):
        # Eşleşme yokken özet basmak gürültüdür; kayıt MANIFEST'e gider.
        cache = make_cache(None)
        root = make_root(line_present=True)
        try:
            make_patch(cache, "patch1789000004-2003", [TOKEN], 30.0)
            r = run_gate_args(cache, "--root", str(root))
            out = r.stdout + r.stderr
            self.assertNotRegex(out, MD5_HEX, "md5 stdout'a sızmamalı")
            self.assertNotRegex(out, "[0-9a-f]{64}", "sha256 stdout'a sızmamalı")
        finally:
            shutil.rmtree(cache, ignore_errors=True)
            shutil.rmtree(root, ignore_errors=True)

    def test_unproven_orphan_is_kept_and_blocks(self):
        cache = make_cache(None)
        root = make_root(line_present=False)   # eklenen satır ağaçta YOK
        try:
            patch = make_patch(cache, "patch1789000005-2004",
                               ["brand-new-line-not-in-tree"], 30.0)
            r = run_gate_args(cache, "--root", str(root))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertTrue(patch.exists(), "kanıtlanamayan patch yerinde kalmalı")
            self.assertNotIn("OTOMATİK KARANTİNA", r.stdout + r.stderr)
        finally:
            shutil.rmtree(cache, ignore_errors=True)
            shutil.rmtree(root, ignore_errors=True)

    def test_partial_cleanup_moves_redundant_blocks_on_unknown(self):
        gate = _load_gate()
        cache = make_cache(None)
        root = make_root(line_present=True)
        try:
            good = make_patch(cache, "patch1789000006-2005", [TOKEN], 30.0)
            bad = make_patch(cache, "patch1789000007-2006",
                             ["line-that-is-absent"], 30.0)
            r = run_gate_args(cache, "--root", str(root))
            out = r.stdout + r.stderr
            self.assertEqual(r.returncode, 1, out)   # hâlâ incelenecek yetim var
            self.assertFalse(good.exists(), "kanıtlı olan taşınmalı")
            self.assertTrue(bad.exists(), "kanıtsız olan kalmalı")
            self.assertIn(bad.name, out, "kalan yetim adıyla anılmalı")
            self.assertIsNotNone(gate.quarantine_dir(cache).glob("patch*"))
        finally:
            shutil.rmtree(cache, ignore_errors=True)
            shutil.rmtree(root, ignore_errors=True)

    def test_hunkless_patch_is_never_quarantined(self):
        # ÖLÇÜLDÜ: `git apply --check` hunk'sız diff'te 0 döndürür → guard
        # olmadan "redundant" sanılıp taşınırdı (kapının eski fixture biçimi).
        cache = make_cache([30.0])   # içerik: "diff --git a/x b/x\n" — hunk YOK
        try:
            r = run_gate_args(cache, "--root", str(ROOT))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertTrue((cache / "patch1789000000-1000").exists())
            self.assertNotIn("OTOMATİK KARANTİNA", r.stdout + r.stderr)
        finally:
            shutil.rmtree(cache, ignore_errors=True)

    def test_trivial_added_lines_are_not_evidence(self):
        # `}` ve boş satır her dosyada var → kanıt sayılmamalı (yoksa
        # anlamsız patch'ler taşınırdı).
        gate = _load_gate()
        cache = make_cache(None)
        root = make_root(line_present=True)
        try:
            patch = make_patch(cache, "patch1789000008-2007", ["}", ""], 30.0)
            self.assertIsNone(gate.redundancy_evidence(patch, root),
                              "önemsiz satırlar kanıt üretmemeli")
            r = run_gate_args(cache, "--root", str(root))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertTrue(patch.exists())
        finally:
            shutil.rmtree(cache, ignore_errors=True)
            shutil.rmtree(root, ignore_errors=True)

    def test_fresh_redundant_patch_is_untouched(self):
        # Kurtarma penceresi: taze patch uçuş-içi stash olabilir → dokunulmaz.
        cache = make_cache(None)
        root = make_root(line_present=True)
        try:
            patch = make_patch(cache, "patch1789000009-2008", [TOKEN], 1.0)
            r = run_gate_args(cache, "--root", str(root))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(patch.exists(), "taze patch taşınmamalı")
            self.assertNotIn("OTOMATİK KARANTİNA", r.stdout + r.stderr)
        finally:
            shutil.rmtree(cache, ignore_errors=True)
            shutil.rmtree(root, ignore_errors=True)

    def test_no_clean_flag_disables_quarantine(self):
        cache = make_cache(None)
        root = make_root(line_present=True)
        try:
            patch = make_patch(cache, "patch1789000010-2009", [TOKEN], 30.0)
            r = run_gate_args(cache, "--root", str(root), "--no-clean")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertTrue(patch.exists())
            self.assertNotIn("OTOMATİK KARANTİNA", r.stdout + r.stderr)
        finally:
            shutil.rmtree(cache, ignore_errors=True)
            shutil.rmtree(root, ignore_errors=True)

    def test_known_incident_is_never_quarantined(self):
        """Etiket UYARI'dır, muafiyet değil: kanıtlı olsa bile TAŞINMAZ.

        Bu kayıtlar olayın TEKRARLADIĞININ kanıtıdır; otomatik taşımak
        tekrar-sinyalini silerdi (AGENTS.md).
        """
        gate = _load_gate()
        archive_patch = _find_redundant_archive_patch()
        self.assertIsNotNone(
            archive_patch,
            "arşivde kanıtlanmış-redundant patch yok — policy testi kurulamaz")
        # Ön koşul: bu patch GERÇEKTEN kanıtlı (yoksa test yanlış nedenle geçer).
        self.assertIsNotNone(gate.redundancy_evidence(archive_patch, ROOT))
        cache = make_cache(None)
        try:
            copy = cache / "patch9999000009-55555"
            copy.write_bytes(archive_patch.read_bytes())
            old = time.time() - 30 * HOUR
            os.utime(copy, (old, old))
            r = run_gate_args(cache, "--root", str(ROOT))
            out = r.stdout + r.stderr
            self.assertEqual(r.returncode, 1, out)
            self.assertTrue(copy.exists(), "bilinen-olay kaydı taşınmamalı")
            self.assertIn("KNOWN-INCIDENT", out)
            self.assertNotIn("OTOMATİK KARANTİNA", out)
        finally:
            shutil.rmtree(cache, ignore_errors=True)

    def test_policy_is_pinned_even_without_a_dynamic_fixture(self):
        # Dinamik fixture kurulamazsa bile politika kodda çivili kalsın.
        gate = _load_gate()
        self.assertIn(gate.KNOWN, gate.PROTECTED_LABELS)
        self.assertIn(gate.WEAK, gate.PROTECTED_LABELS)

    def test_quarantine_dir_is_sibling_of_cache(self):
        # AGENTS.md'nin adlandırdığı dizin: <cache>-orphans-quarantine-<tarih>.
        gate = _load_gate()
        cache = pathlib.Path("/tmp/pre-commit")
        dest = gate.quarantine_dir(cache)
        self.assertEqual(dest.parent, cache.parent)
        self.assertTrue(dest.name.startswith("pre-commit" + gate.QUARANTINE_SUFFIX))
        self.assertRegex(dest.name, r"\d{8}$")


if __name__ == "__main__":
    unittest.main()
