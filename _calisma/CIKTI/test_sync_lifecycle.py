#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sync_lifecycle.py — sync aracının TEK yaşam-döngüsü regresyon kapısı.

Bu dosya iki dosyanın bölünmüş kapsamını birleştirir: eski
`test_sync_check_unit_tests.py` (in-process + sandbox, 40 test) ve eski
`test_sync_lifecycle.py` (CLI subprocess, 4 test) → tek dosya, 46 test.
Bölen yerine tek "sözleşme" altında toplanır; aynı hook girişi iki yerde
ayrı ayrı sınanıyordu.

Kapsam:
  1) TestSyncLifecycle — CLI'yi SUBPROCESS ile koşar (in-process import değil),
     temp dizin sandbox'ında tam yaşam-döngüsünü sınar:
       --update → boş başlangıçtan senkron; --check → rc=0; drift → rc=1 + remedy
       ve manifest DEĞİŞMEZ; --update → yeşil; prune → orphan düşer → yeşil
       --list stdout sözleşmesi discover() ile birebir
  2) TestHookEntryFailClosed — gerçek check_unit_tests_hook.sh sandbox'ta:
     yeni dosya manifest'te yok → blok; HOOK_COVERAGE girdisi eksik → blok;
     senkron ağaç → geçer. Üçünde de okuma-hook invariantı (dosya DEĞİŞMEZ).
  3) TestDiscover / TestManifest / TestHookCoverageSync — keşif, manifest ve
     ikinci hedefin (HOOK_COVERAGE) senkron sözleşmeleri; AST parse'ın
     span-sezgisi içermediği ve yeniden üretilen bloğun AST round-trip
     olduğu kilitlenir.
  4) TestRepoConsistency — gerçek repo invariantları: manifest diskle uyumlu,
     her manifest girdisi diskte var, her hook pattern'i gerçek test bulur.
  5) TestExcludeCiBindingGate — EXCLUDE'daki her testin koşma yeri AÇIKÇA
     bildirilmiş ve bildirilen hedef gerçekten var (fail-closed).
  6) TestDriftGuardParsing — ci_full_discover_drift_guard'ın saf çözümlemesi.

Gerçek repo ağacına dokunmaz: tüm yazmalar temp sandbox'ta; gerçek
manifest/coverage'a karşı yalnız okuma modül-yardımcılarıyla yapılır.

stdlib only — OFFLINE, temp dizinlerle izole.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SYNC = os.path.join(HERE, "sync_check_unit_tests.py")
HOOK = os.path.join(HERE, "check_unit_tests_hook.sh")

STUB_TEST_BODY = ("import unittest\n\n\nclass T(unittest.TestCase):\n"
                  "    def test_ok(self):\n        pass\n")

# Sandbox coverage dosyası kendisi keşfedilen bir testtir (gerçek repo düzeni):
# sync-sonrası manifest/HOOK kümesi = stub'lar + bu dosya.
COV_NAME = "test_coverage_report.py"
BASE3 = ["test_a.py", "test_b.py", COV_NAME]

# Birlestirme (2026-10-02): test_sync_check_unit_tests.py bu dosyaya tasindi.
# O dosyanin kullandigi isimler ayni degerlere gore burada tek kere tanimli.
COV_FILE = COV_NAME
BASE = BASE3
HOOK_SCRIPT = HOOK

# Sandbox coverage dosyası: statik-parse formatı (ci_full_discover_drift_guard
# okuyabilsin) + stub test gövdesi (dosyanın kendisi keşfedilen bir test olsun,
# gerçek repodaki test_coverage_report.py düzeni gibi).
COVERAGE_TEMPLATE = '''import pathlib
HOOK_COVERAGE = {
    "other-hook": ["test_other.py"],
    "check-unit-tests": [
{ENTRIES}    ],
}
'''


def _write_coverage(path, entries):
    lines = "".join('        "%s",\n' % e for e in entries)
    with open(path, "w", encoding="utf-8") as f:
        f.write(COVERAGE_TEMPLATE.replace("{ENTRIES}", lines))


if HERE not in sys.path:
    sys.path.insert(0, HERE)
import sync_check_unit_tests as s  # noqa: E402


def _iso(sb):
    """İzole-koşum argümanları: gerçek repo yollarına dokunma."""
    return ["--dir", sb.cikti, "--manifest", sb.manifest, "--coverage", sb.cov]


class Sandbox:
    """Gerçek sync aracı + gerçek hook script'iyle izole repo kökü."""

    def __init__(self, disk=(), manifest=None, coverage=()):
        """disk/manifest/coverage verilirse sandbox HAZIR kurulur (birlestirme
        icin: tek tek add_test yazmadan belirli bir duruma inmek)."""
        self.td = tempfile.TemporaryDirectory()
        self.root = self.td.name
        cikti = self.cikti
        os.makedirs(cikti)
        shutil.copy(SYNC, cikti)
        shutil.copy(HOOK, cikti)
        _write_coverage(self.cov, list(coverage))
        with open(self.cov, "a", encoding="utf-8") as f:
            f.write(STUB_TEST_BODY)
        for name in disk:
            self.add_test(name)
        if manifest is not None:
            s.write_manifest(list(manifest), self.manifest)

    @property
    def cikti(self):
        return os.path.join(self.root, "_calisma", "CIKTI")

    @property
    def manifest(self):
        return os.path.join(self.cikti, "check_unit_tests.list")

    @property
    def cov(self):
        return os.path.join(self.cikti, "test_coverage_report.py")

    def add_test(self, name):
        with open(os.path.join(self.cikti, name), "w", encoding="utf-8") as f:
            f.write(STUB_TEST_BODY)

    def remove_test(self, name):
        os.remove(os.path.join(self.cikti, name))

    def run_cli(self, *args):
        """CLI'yi subprocess ile koşturur; (rc, stdout+stderr) döndürür."""
        r = subprocess.run(
            [sys.executable, SYNC] + list(args),
            capture_output=True, text=True, cwd=self.root, timeout=60,
            check=False)
        return r.returncode, (r.stdout + r.stderr)

    def run_hook(self):
        """check_unit_tests_hook.sh'ı sandbox kökünde koşturur."""
        return subprocess.run(
            ["bash", os.path.join(self.cikti, "check_unit_tests_hook.sh")],
            capture_output=True, text=True, cwd=self.root, timeout=60,
            check=False)

    def cleanup(self):
        self.td.cleanup()


class TestSyncLifecycle(unittest.TestCase):
    """Ad-hoc SYNC_LIFECYCLE_OK kanıt koşumunun kalıcı, sabit sürümü."""

    def test_full_lifecycle_update_check_drift_failclosed_update_green_prune(self):
        sb = Sandbox()
        try:
            # 1) Boş başlangıçtan --update: her iki hedefi doldurur, rc=0.
            sb.add_test("test_a.py")
            sb.add_test("test_b.py")
            rc, out = sb.run_cli("--update", "--no-stage", *_iso(sb))
            self.assertEqual(rc, 0, out)
            self.assertEqual(s.read_manifest(sb.manifest), BASE3)
            self.assertEqual(s.read_hook_coverage(sb.cov), BASE3)

            # 2) Senkron ağaçta --check yeşil.
            rc, out = sb.run_cli("--check", *_iso(sb))
            self.assertEqual(rc, 0, out)

            # 3-4) Drift: yeni test dosyası → --check FAIL-CLOSED, remedy
            # gösterir, manifest'i KENDİSİ DEĞİŞTİRMEZ (okuma-kapısı).
            sb.add_test("test_c.py")
            rc, out = sb.run_cli("--check", *_iso(sb))
            self.assertEqual(rc, 1, out)
            self.assertIn("test_c.py", out)
            self.assertIn("--update", out, "remedy komutu gösterilmeli")
            self.assertEqual(s.read_manifest(sb.manifest), BASE3)

            # 5) --update drift'i yer.
            rc, out = sb.run_cli("--update", "--no-stage", *_iso(sb))
            self.assertEqual(rc, 0, out)
            self.assertIn("test_c.py", s.read_manifest(sb.manifest))

            # 6) Yeniden yeşil.
            rc, out = sb.run_cli("--check", *_iso(sb))
            self.assertEqual(rc, 0, out)

            # 7) Prune: dosya silinir → --update orphan'ı düşürür → yeşil.
            sb.remove_test("test_c.py")
            rc, out = sb.run_cli("--update", "--no-stage", *_iso(sb))
            self.assertEqual(rc, 0, out)
            self.assertNotIn("test_c.py", s.read_manifest(sb.manifest))
            rc, out = sb.run_cli("--check", *_iso(sb))
            self.assertEqual(rc, 0, out)
        finally:
            sb.cleanup()

    def test_list_stdout_matches_discovery(self):
        """--list CLI çıkışı discover() sırasıyla birebir (stdout sözleşmesi)."""
        sb = Sandbox()
        try:
            sb.add_test("test_a.py")
            sb.add_test("test_b.py")
            rc, out = sb.run_cli("--list", "--dir", sb.cikti)
            self.assertEqual(rc, 0, out)
            self.assertEqual(out.split(), BASE3)
        finally:
            sb.cleanup()


class TestHookEntryFailClosed(unittest.TestCase):
    """Gerçek hook script'i sandbox'ta: drift BLOKLANIR, sessizce düzeltilmez."""

    def test_hook_blocks_drift_and_stays_read_only(self):
        sb = Sandbox()
        try:
            sb.add_test("test_a.py")
            sb.add_test("test_b.py")
            with open(sb.manifest, "w", encoding="utf-8") as f:
                f.write("test_a.py\n")
            # Disk 3 keşif, manifest 1 giriş, HOOK bloğu boş → çift-hedef drift.
            r = sb.run_hook()
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("--update", r.stderr + r.stdout,
                          "remedy komutu gösterilmeli")
            self.assertEqual(s.read_manifest(sb.manifest), ["test_a.py"],
                             "okuma-hook invariantı: drift bloklanır, düzeltilmez")
            self.assertEqual(s.read_hook_coverage(sb.cov), [],
                             "okuma-hook invariantı: coverage bloğu değişmez")
        finally:
            sb.cleanup()

    def test_hook_passes_on_synced_tree(self):
        """Senkron ağaçta hook geçer VE hiçbir şeyi değiştirmez (okuma-hook)."""
        sb = Sandbox(disk=["test_a.py"])
        try:
            rc, out = sb.run_cli("--update", "--no-stage", *_iso(sb))
            self.assertEqual(rc, 0, out)
            before_mf = s.read_manifest(sb.manifest)
            before_cov = s.read_hook_coverage(sb.cov)
            r = sb.run_hook()
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("PASS", r.stdout)
            # okuma-hook invariantı: geçiş de YAZMA olmamalı
            self.assertEqual(s.read_manifest(sb.manifest), before_mf)
            self.assertEqual(s.read_hook_coverage(sb.cov), before_cov)
        finally:
            sb.cleanup()

    def test_hook_blocks_when_new_test_missing_from_manifest(self):
        """Diskte yeni test var, manifest senkron değil → hook BLOKLANIR."""
        sb = Sandbox(disk=BASE + ["test_c.py"], manifest=BASE, coverage=BASE)
        try:
            r = sb.run_hook()
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("--update", r.stderr, "remedy komutu gösterilmeli")
            self.assertEqual(s.read_manifest(sb.manifest), BASE,
                             "okuma-hook invariantı: düzeltilmez")
        finally:
            sb.cleanup()

    def test_hook_blocks_when_hook_coverage_missing_entry(self):
        """Manifest senkron AMA HOOK_COVERAGE girdisi eksik → hook yine BLOKLANIR.

        İkinci hedefin (HOOK_COVERAGE) manifest senkronken bile yakalandığını
        kanıtlar; aksi halde "manifest güncel" sanıp geçilirdi.
        """
        sb = Sandbox(disk=BASE, manifest=BASE,
                     coverage=["test_a.py", "test_b.py"])
        try:
            r = sb.run_hook()
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("HOOK_COVERAGE", r.stderr)
        finally:
            sb.cleanup()


class TestDiscover(unittest.TestCase):
    def test_discover_finds_new_test_file(self):
        """Yeni eklenen test_*.py dosyası keşifte yer almalı (kuralın özü)."""
        with tempfile.TemporaryDirectory() as td:
            # Var olan dosyalar
            open(os.path.join(td, "test_a.py"), "w").close()
            open(os.path.join(td, "test_b.py"), "w").close()
            # YENİ dosya — manifeste girmemeli gerekçesiyle önce 2'liyi bekle
            got = s.discover(td)
            self.assertEqual(got, ["test_a.py", "test_b.py"])
            # Yeni dosya eklendiğinde keşfeder
            open(os.path.join(td, "test_c.py"), "w").close()
            got = s.discover(td)
            self.assertEqual(got, ["test_a.py", "test_b.py", "test_c.py"])

    def test_discover_ignores_non_test_files_and_exclude(self):
        with tempfile.TemporaryDirectory() as td:
            open(os.path.join(td, "foo.py"), "w").close()   # test_ öneki yok
            open(os.path.join(td, "test_x.py"), "w").close()
            open(os.path.join(td, "test_plist_gate_exit.py"), "w").close()  # EXCLUDE
            got = s.discover(td)
            self.assertNotIn("test_plist_gate_exit.py", got)
            self.assertNotIn("foo.py", got)
            self.assertEqual(got, ["test_x.py"])

    def test_exclude_each_name_is_real_test_pattern(self):
        """EXCLUDE'deki her isim test_*.py kalıbına uyar (yazım hatası kapısı)."""
        for name in s.EXCLUDE:
            self.assertTrue(name.startswith("test_") and name.endswith(".py"), name)


class TestManifest(unittest.TestCase):
    def _tmp_env(self):
        td = tempfile.TemporaryDirectory()
        for n in ("test_a.py", "test_b.py", "test_c.py"):
            open(os.path.join(td.name, n), "w").close()
        mf = os.path.join(td.name, "mf.list")
        s.write_manifest(["test_a.py", "test_b.py"], mf)
        return td, mf

    def test_check_fails_on_new_file(self):
        """Yeni test dosyası manifest'te yoksa run_check exit 1 (fail-closed)."""
        td, mf = self._tmp_env()
        try:
            self.assertEqual(s.run_check(td.name, mf), 1)
        finally:
            td.cleanup()

    def test_update_adds_new_file(self):
        """--update ile yeni dosya manifest'e otomatik eklenir (kural)."""
        td, mf = self._tmp_env()
        try:
            s.main(["--update", "--no-stage", "--dir", td.name, "--manifest", mf])
            self.assertEqual(s.read_manifest(mf), ["test_a.py", "test_b.py", "test_c.py"])
        finally:
            td.cleanup()

    def test_update_prunes_stale(self):
        """Silinen test dosyaları manifest'ten çıkarılır."""
        td, mf = self._tmp_env()
        try:
            os.remove(os.path.join(td.name, "test_b.py"))
            s.main(["--update", "--no-stage", "--dir", td.name, "--manifest", mf])
            self.assertNotIn("test_b.py", s.read_manifest(mf))
        finally:
            td.cleanup()

    def test_check_passes_after_update(self):
        td, mf = self._tmp_env()
        try:
            s.main(["--update", "--no-stage", "--dir", td.name, "--manifest", mf])
            self.assertEqual(s.run_check(td.name, mf), 0)
        finally:
            td.cleanup()


HOOK_BLOCK_TEMPLATE = '''import pathlib
HOOK_COVERAGE = {
    "other-hook": ["test_other.py"],
    "check-unit-tests": [
{ENTRIES}    ],
}
'''


def _write_coverage(path, entries):
    """Statik-parse formatıyla (drift guard'ın okuduğu) coverage dosyası yazar."""
    lines = "".join('        "%s",\n' % e for e in entries)
    with open(path, "w", encoding="utf-8") as f:
        f.write(HOOK_BLOCK_TEMPLATE.replace("{ENTRIES}", lines))


class TestHookCoverageSync(unittest.TestCase):
    """HOOK_COVERAGE['check-unit-tests'] ikinci hedefin davranış kapıları."""

    def _env(self, entries, extra_tests=("test_new.py",), ghost=None):
        """entries bloğa yazılır; extra_tests + entries(diskte_var) dosya olarak
        oluşturulur. ghost: YALNIZ blokta olan, diskte OLMAYAN girdi."""
        td = tempfile.TemporaryDirectory()
        for e in entries:
            if e != ghost:
                open(os.path.join(td.name, e), "w").close()
        for t in extra_tests:
            open(os.path.join(td.name, t), "w").close()
        cov = os.path.join(td.name, "coverage_report.py")
        _write_coverage(cov, entries)
        return td, cov

    def test_check_fails_when_new_test_missing_from_hook_coverage(self):
        """ÖLÇÜLEN BOŞLUK: manifest güncel, HOOK_COVERAGE unutulmuş → exit 1."""
        td, cov = self._env(["test_a.py", "test_b.py"], ("test_new.py",))
        try:
            mf = os.path.join(td.name, "mf.list")
            s.write_manifest(["test_a.py", "test_b.py", "test_new.py"], mf)
            rc = s.run_check(td.name, mf, cov)
            self.assertEqual(rc, 1, "HOOK_COVERAGE boşluğu fail-closed yakalanmalı")
        finally:
            td.cleanup()

    def test_update_appends_and_preserves_js_and_exclude_entries(self):
        """Yeni keşif eklenir; .js ve EXCLUDE'lu mevcut girdiler KORUNUR."""
        entries = ["test_a.py", "test_budget_scan.js", "test_cleanup.py"]
        td, cov = self._env(entries, ("test_new.py",))
        try:
            s.run_update(stage=False, directory=td.name, manifest=os.path.join(td.name, "mf.list"), coverage=cov)
            got = s.read_hook_coverage(cov)
            self.assertIn("test_new.py", got)
            self.assertIn("test_budget_scan.js", got)  # .js korunur
            self.assertIn("test_cleanup.py", got)      # EXCLUDE'lu korunur
        finally:
            td.cleanup()

    def test_update_removes_orphan_entries(self):
        """Diskte olmayan girdi bloktan çıkarılır (orphan temizliği)."""
        entries = ["test_a.py", "test_ghost.py"]
        td, cov = self._env(entries, ("test_new.py",), ghost="test_ghost.py")
        try:
            s.run_update(stage=False, directory=td.name, manifest=os.path.join(td.name, "mf.list"), coverage=cov)
            got = s.read_hook_coverage(cov)
            self.assertNotIn("test_ghost.py", got)
            self.assertIn("test_a.py", got)
        finally:
            td.cleanup()

    def test_update_is_idempotent_and_check_green_after(self):
        td, cov = self._env(["test_a.py"], ("test_new.py",))
        try:
            mf = os.path.join(td.name, "mf.list")
            s.run_update(stage=False, directory=td.name, manifest=mf, coverage=cov)
            before = s.read_hook_coverage(cov)
            changed = s.run_update(stage=False, directory=td.name, manifest=mf, coverage=cov)
            self.assertFalse(changed, "ikinci update değişiklik üretmemeli")
            self.assertEqual(s.read_hook_coverage(cov), before)
            self.assertEqual(s.run_check(td.name, mf, cov), 0)
        finally:
            td.cleanup()

    def test_missing_block_fails_closed(self):
        """Bloğu olmayan coverage dosyası → run_check exit 1 (sahte PASS yok)."""
        td = tempfile.TemporaryDirectory()
        try:
            open(os.path.join(td.name, "test_a.py"), "w").close()
            cov = os.path.join(td.name, "cov.py")
            with open(cov, "w", encoding="utf-8") as f:
                f.write("HOOK_COVERAGE = {}\n")
            mf = os.path.join(td.name, "mf.list")
            s.write_manifest(["test_a.py"], mf)
            self.assertEqual(s.run_check(td.name, mf, cov), 1)
        finally:
            td.cleanup()

    def test_regenerated_block_is_ast_round_trip(self):
        """Yeniden yazılan blok, AST tabanlı okuyucuyla birebir geri okunmalı
        (yazım-sonrası read == entries sözleşmesi)."""
        entries = ["test_a.py", "test_b.py"]
        td, cov = self._env(entries, ("test_new.py",))
        try:
            s.run_update(stage=False, directory=td.name,
                         manifest=os.path.join(td.name, "mf.list"), coverage=cov)
            self.assertEqual(
                s.read_hook_coverage(cov),
                ["test_a.py", "test_b.py", "test_new.py"])
        finally:
            td.cleanup()

    def test_reader_is_span_heuristic_free(self):
        """KIRILMA-TUZAĞI: blok-içi yorum ']," taşıyorsa span sezgisi kırılır;
        AST tabanlı okuma/yazım bu durumda da doğru çalışmalı (bkz. ölçülen
        2026-09-21 boşluğu: ci_full_discover_drift_guard.py satır 129)."""
        td = tempfile.TemporaryDirectory()
        try:
            cov = os.path.join(td.name, "coverage_report.py")
            with open(cov, "w", encoding="utf-8") as f:
                f.write(
                    "HOOK_COVERAGE = {\n"
                    '    "other-hook": ["test_other.py"],\n'
                    '    "check-unit-tests": [\n'
                    '        # 2026-09-21 boşluğu: ci_full_discover_drift_guard.py\n'
                    '        # ... sorusunun cevabı ], tam burada — tuzak\n'
                    '        "test_a.py",\n'
                    '        "test_b.py",],\n'
                    "}\n")
            open(os.path.join(td.name, "test_a.py"), "w").close()
            open(os.path.join(td.name, "test_b.py"), "w").close()
            open(os.path.join(td.name, "test_c.py"), "w").close()
            # Okuma: eski span sezgisi gövdeyi yorumdaki '],'-da kırpıp boş
            # gövde okur; AST tabanlı okuma gerçek girdileri döndürmeli.
            self.assertEqual(s.read_hook_coverage(cov),
                             ["test_a.py", "test_b.py"])
            # Yazım da sağlam kalmalı (parite: read(update(read)) = yazılan).
            s.run_update(stage=False, directory=td.name,
                         manifest=os.path.join(td.name, "mf.list"),
                         coverage=cov)
            self.assertEqual(s.read_hook_coverage(cov),
                             ["test_a.py", "test_b.py", "test_c.py"])
        finally:
            td.cleanup()

    def test_guard_reader_matches_sync_reader_on_real_repo(self):
        """Parite kapısı: ci_full_discover_drift_guard'ın HOOK_COVERAGE okuması,
        sync aracının okumasıyla gerçek repoda birebir aynı olmalı (guard
        yalnız .py ister; sync .js girdilerini de taşır — py-only küme)."""
        import ci_full_discover_drift_guard as g
        self.assertEqual(
            g.read_hook_coverage_check_unit_tests(),
            {e for e in s.read_hook_coverage() if e.endswith(".py")})

    def test_real_repo_hook_coverage_covers_discovery(self):
        """Gerçek repo regresyon kapısı: keşif, tüm hook listelerinin
        BİRLEŞİMİ + CHECK_EXEMPT muafiyetiyle kapsanmalı.

        (Tek blokcoverage'ı yanlış invariant olur: bazı dosyalar başka
        hook'larca kapsanır — örn. test_check_design_tokens.py →
        check-design-tokens — ve meta dosyalar CHECK_EXEMPT'tedir.)
        """
        with open(s.COVERAGE_FILE, encoding="utf-8") as f:
            src = f.read()
        i = src.find("HOOK_COVERAGE = {")
        j = src.find("CI_JOB_COVERAGE")
        self.assertGreater(i, 0)
        self.assertGreater(j, i)
        all_hooks = set(re.findall(r'"([^"]+\.(?:py|js))"', src[i:j]))
        k = src.find("CHECK_EXEMPT = frozenset({")
        end = src.find("})", k)
        exempt = set(re.findall(r'"([^"]+)"', src[k:end])) if k > 0 and end > k else set()
        missing = [f for f in s.discover()
                   if f not in all_hooks and f not in exempt]
        self.assertEqual(
            missing, [],
            "check-coverage-report kapsamı boşlukta — "
            "`python3 _calisma/CIKTI/sync_check_unit_tests.py --update`")


class TestRepoConsistency(unittest.TestCase):
    """Gerçek repo: manifest disktekilerle uyumlu olmalı (kendi kendini doğrular)."""

    def test_repo_manifest_matches_discovery(self):
        missing, _stale = s.diff(s.discover(), s.read_manifest())
        # Sync edilmemiş yeni dosya VARSA bu test FAIL — kuralın regresyon kapısı.
        self.assertEqual(
            missing, [],
            "check_unit_tests.list güncel değil: şu yeni testler eksik — "
            "`python3 _calisma/CIKTI/sync_check_unit_tests.py --update` çalıştır.",
        )

    def test_repo_manifest_entries_exist(self):
        for name in s.read_manifest():
            self.assertTrue(
                os.path.exists(os.path.join(s.CIKTI, name)),
                f"Manifest'te olan dosya diskte yok: {name}",
            )

    def test_hook_pattern_matches_real_test_for_every_entry(self):
        """check_unit_tests_hook.sh pattern'i her giriş için en az 1 dosya bulmalı.

        Regresyon kapısı: hook `-p "$t.py"` kullanır (t = manifest girişi,
        `.py` sıyrılır). Eski hata: manifest girişi zaten `.py`'liyken bir kez
        daha `.py` ekleniyordu → `test_X.py.py` → 0 eşleşme. Python 3.9-3.11'de
        boş discovery exit 0 döndüğü için hook SESSİZCE hiç test koşmadan
        "PASS" diyordu; Python 3.12+ ise boş discovery'de exit 5 döndürür
        (gh-136442) → CI'da 49/49 BAŞARISIZ. Bu test pattern'in her manifest
        girişi için gerçek bir test dosyasıyla eşleştiğini sabitler.
        """
        import fnmatch

        names = s.read_manifest()
        self.assertTrue(names, "manifest boş — hook hiçbir şey koşmaz")
        files = [f for f in os.listdir(s.CIKTI) if f.endswith(".py")]
        for name in names:
            base = name[:-3] if name.endswith(".py") else name
            pattern = base + ".py"
            self.assertTrue(
                any(fnmatch.fnmatchcase(f, pattern) for f in files),
                f"Hook pattern '{pattern}' hiçbir test dosyasıyla eşleşmiyor "
                f"(çift uzantı/yanlış giriş) — kaynak: {name}",
            )


HOOK_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "check_unit_tests_hook.sh")
STUB_TEST_BODY = ("import unittest\n\n\nclass T(unittest.TestCase):\n"
                  "    def test_ok(self):\n        pass\n")
# Gerçek repoda olduğu gibi: test_coverage_report.py kendisi keşfedilen
# bir test dosyasıdır (manifest girişli) — HOOK bloğu + test gövdesi.
COV_FILE = "test_coverage_report.py"
BASE = ["test_a.py", "test_b.py", COV_FILE]


class TestExcludeCiBindingGate(unittest.TestCase):
    """EXCLUDE ↔ CI-job/hook BAĞLAMA kapısı (sync --check'in üçüncü hedefi).

    Ölçülen boşluk (2026-09-30): EXCLUDE'lanan test pre-commit manifest'inde
    koşmaz; "CI'da X job'ında koşar" iddiası YALNIZCA yorumlarda yaşıyordu.
    Doğrulanan işaretler:
      * `ci_full_discover_drift_guard.py` (tam discover emniyet ağı) repo'da
        HİÇBİR yere bağlı değil (workflow/pre-commit/manifest: 0 eşleşme)
        → "CI her şeyi koşar" sözleşmesinin makinesel garantisi yok.
      * CI'da `verify` job'ı full discover koşuyor
        (`unittest discover -p "test_*.py"`) — yani var olan koşma yolu bu.
    Yani EXCLUDE'a yeni bir test ekleyen kişi onun HİÇBİR YERDE koşmadığını
    fark edemiyor. Bu kapı: (1) her EXCLUDE girdisi bir hedefe bağlı olmalı,
    (2) bildirilen hedef GERÇEKTEN var olmalı, (3) ters/stale bağ olmamalı,
    (4) full-discover sözleşmesi ölçülebilir kalmalı. Hepsi fail-closed.
    """

    WORKFLOW = (
        "name: t\non: [push]\njobs:\n"
        "  alpha:\n    name: Alpha job\n    steps:\n"
        "      - name: Run tests\n        run: |\n"
        '          python3 -m unittest discover -s _calisma/CIKTI -p "test_*.py"\n'
    )
    CONFIG = "repos:\n  - hooks:\n      - id: gate-x\n        name: x\n"

    def _surfaces(self, workflow=WORKFLOW, config=CONFIG):
        td = tempfile.mkdtemp()
        wf = os.path.join(td, "workflows")
        os.makedirs(wf)
        with open(os.path.join(wf, "verify.yml"), "w") as fh:
            fh.write(workflow)
        cfg = os.path.join(td, ".pre-commit-config.yaml")
        with open(cfg, "w") as fh:
            fh.write(config)
        return td, wf, cfg

    def _gate(self, wf, cfg, **kw):
        return s.run_check_exclude_binding(workflows_dir=wf, config_path=cfg, **kw)

    def test_gate_passes_when_every_exclude_has_existing_home(self):
        td, wf, cfg = self._surfaces()
        try:
            rc = self._gate(wf, cfg, exclude={"test_a.py"},
                            ci_jobs={"test_a.py": "alpha"}, hooks={})
            self.assertEqual(rc, 0, "tam bağlı küme bloklanmamalı")
        finally:
            shutil.rmtree(td)

    def test_gate_blocks_exclude_without_any_home(self):
        # Kapının özü: manifest'te koşmayan testin bir koşma YERİ olmalı.
        td, wf, cfg = self._surfaces()
        try:
            rc = self._gate(wf, cfg, exclude={"test_a.py"}, ci_jobs={}, hooks={})
            self.assertEqual(rc, 1, "bağsız EXCLUDE girdisi bloklanmalı")
        finally:
            shutil.rmtree(td)

    def test_gate_blocks_dangling_ci_job(self):
        # Job yeniden adlandırıldı/silindi → bağ boşlukta kalmasın.
        td, wf, cfg = self._surfaces()
        try:
            rc = self._gate(wf, cfg, exclude={"test_a.py"},
                            ci_jobs={"test_a.py": "ghost-job"}, hooks={})
            self.assertEqual(rc, 1, "var olmayan job id'si bloklanmalı")
        finally:
            shutil.rmtree(td)

    def test_gate_blocks_dangling_hook(self):
        td, wf, cfg = self._surfaces()
        try:
            rc = self._gate(wf, cfg, exclude={"test_b.py"}, ci_jobs={},
                            hooks={"test_b.py": "gate-yok"})
            self.assertEqual(rc, 1, "var olmayan hook id'si bloklanmalı")
        finally:
            shutil.rmtree(td)

    def test_gate_blocks_stale_binding_for_non_excluded_test(self):
        # Ters yön: EXCLUDE'da olmayan teste bağlama bildirilemez.
        td, wf, cfg = self._surfaces()
        try:
            rc = self._gate(wf, cfg, exclude=set(),
                            ci_jobs={"test_ghost.py": "alpha"}, hooks={})
            self.assertEqual(rc, 1, "EXCLUDE dışı stale bağ bloklanmalı")
        finally:
            shutil.rmtree(td)

    def test_gate_blocks_double_binding(self):
        td, wf, cfg = self._surfaces()
        try:
            rc = self._gate(wf, cfg, exclude={"test_a.py"},
                            ci_jobs={"test_a.py": "alpha"},
                            hooks={"test_a.py": "gate-x"})
            self.assertEqual(rc, 1, "çift bağlama (belirsizlik) bloklanmalı")
        finally:
            shutil.rmtree(td)

    def test_gate_is_fail_closed_when_workflow_surface_missing(self):
        # KÖR KAPI: yüzey okunamıyorsa "bağlar sağlam" sayılamaz.
        td, _wf, cfg = self._surfaces()
        try:
            rc = self._gate(os.path.join(td, "yok"), cfg,
                            exclude={"test_a.py"},
                            ci_jobs={"test_a.py": "alpha"}, hooks={})
            self.assertEqual(rc, 1, "okunamayan yüzeyde kapı kör geçmemeli")
        finally:
            shutil.rmtree(td)

    def test_gate_blocks_when_full_discover_sentinel_disappears(self):
        # "CI her şeyi koşar" vaadi ölçülebilir olmalı: full discover satırı
        # workflow'larda yoksa EXCLUDE'lu testlerin koşma yeri kalmamıştır.
        td, wf, cfg = self._surfaces(
            workflow=("name: t\non: [push]\njobs:\n  alpha:\n"
                      "    steps:\n      - name: x\n        run: true\n"))
        try:
            rc = self._gate(wf, cfg, exclude={"test_a.py"},
                            ci_jobs={"test_a.py": "alpha"}, hooks={})
            self.assertEqual(rc, 1, "full-discover sentinel yoksa bloklanmalı")
        finally:
            shutil.rmtree(td)

    def test_gate_is_skipped_in_fully_isolated_run(self):
        # Tam izole koşum (check_unit_tests_hook.sh'nin sandbox kopyası):
        # repo yüzeyi YOK → kapı "kapsam dışı" der, bloklamaz. Doğrulanacak
        # yüzey bulunmadığında kör FAIL de üretmek yanlış olur (sandbox
        # sözleşmesi: izole koşumda hook yeşil kalmalı).
        td = tempfile.mkdtemp()
        try:
            rc = self._gate(os.path.join(td, "yok"), os.path.join(td, "yok.yaml"),
                            exclude={"test_a.py"},
                            ci_jobs={"test_a.py": "alpha"}, hooks={})
            self.assertEqual(rc, 0, "tam izole koşumda kapı kapsam dışı olmalı")
        finally:
            shutil.rmtree(td)

    def test_gate_blocks_partial_surface(self):
        # Kısmi yüzey (config var, workflow yok) → ölçülemeyen bağlama
        # "temiz" sayılamaz: fail-closed.
        td = tempfile.mkdtemp()
        cfg = os.path.join(td, "cfg.yaml")
        with open(cfg, "w") as fh:
            fh.write(self.CONFIG)
        try:
            rc = self._gate(os.path.join(td, "yok-wf"), cfg,
                            exclude={"test_a.py"},
                            ci_jobs={"test_a.py": "alpha"}, hooks={})
            self.assertEqual(rc, 1, "kısmi yüzeyde kör PASS üretilmemeli")
        finally:
            shutil.rmtree(td)

    def test_real_repo_every_exclude_entry_declares_a_home(self):
        # Regresyon kapısı: yeni EXCLUDE girdisi bağlama bildirmeden eklenemez.
        rc = s.run_check_exclude_binding()
        self.assertEqual(rc, 0, "gerçek repo EXCLUDE↔hedef bağları temiz olmalı")

    def test_real_repo_declared_targets_exist(self):
        missing_jobs = sorted({j for j in s.EXCLUDE_CI_JOBS.values()
                               if j not in s.workflow_ci_tokens()})
        missing_hooks = sorted({h for h in s.EXCLUDE_HOOKS.values()
                                if h not in s.precommit_hook_ids()})
        self.assertEqual(missing_jobs, [], f"EXCLUDE, var olmayan CI job'a bağlı: {missing_jobs}")
        self.assertEqual(missing_hooks, [], f"EXCLUDE, var olmayan hook'a bağlı: {missing_hooks}")

    def test_real_repo_ci_runs_full_discover(self):
        # EXCLUDE sözleşmesinin makinesel kanıtı: full discover hâlâ koşuyor.
        blobs = s.read_workflows_text()
        self.assertTrue(any(s.FULL_DISCOVER_SENTINEL in b for b in blobs),
                        "CI full discover satırı kayboldu — EXCLUDE vaadi ölçülemez")

    def test_run_check_wires_binding_gate_and_skips_it_when_isolated(self):
        # (a) bağlama: --check yolunda kapı gerçekten çağrılıyor
        orig = s.run_check_exclude_binding
        s.run_check_exclude_binding = lambda **kw: 1
        try:
            rc = s.run_check()
        finally:
            s.run_check_exclude_binding = orig
        self.assertEqual(rc, 1, "binding gate run_check'e bağlı değil (sessiz kör kapı)")

        # (b) izolasyon: --dir ile geçici dizin koşumunda repo-geneli kapı çalışmaz
        calls = []

        def _spy(**kw):
            calls.append(kw)
            return 0

        with tempfile.TemporaryDirectory() as td:
            s.run_check_exclude_binding = _spy
            try:
                s.run_check(directory=td, manifest=os.path.join(td, "m.list"))
            finally:
                s.run_check_exclude_binding = orig
        self.assertEqual(calls, [], "izole koşumda repo-geneli kapı çalışmamalı")


class TestDriftGuardParsing(unittest.TestCase):
    """ci_full_discover_drift_guard saf (pure) çözümleme sözleşmesi.

    Ölçülen boşluk: gate `python -m unittest <modul>` komutuyla 161 dosyayı
    ayrı ayrı koşuyordu; bu komut repo kökünden ÇALIŞMIYOR (`_calisma/CIKTI`
    paket değil → `__init__.py` yok, sys.path'te değil), dolayısıyla her dosya
    rc=1 döndürüyor, `registered_battery_green` daima False ve
    `drift_detected` HİÇBİR ZAMAN True olamıyordu — yani gate fail-closed
    değildi (ölçüldü: files_passed 0/161, verdict PASS, 5m20s). Yeni çözümleme
    yalnız kayıtsız (kayıtlı olmayan) kırmızı dosyaları arar; kayıtlı batarya
    CI'da zaten sert kapı olarak koştuğu için YENİDEN koşulmaz.
    """

    FAIL_LINE = "FAIL: test_x (test_alpha_gate.AlphaTest.test_x)\n"
    ERROR_LINE = "ERROR: test_y (test_beta_gate.BetaTest.test_y)\n"
    NOISE = "FAIL: README skills index drift\nFAIL: skills index ölçülemedi\n"

    def _g(self):
        import ci_full_discover_drift_guard as g
        return g

    def test_extracts_failing_modules_from_fail_lines(self):
        g = self._g()
        self.assertEqual(g._failing_modules(self.FAIL_LINE), {"test_alpha_gate"})

    def test_extracts_failing_modules_from_error_lines(self):
        g = self._g()
        self.assertEqual(g._failing_modules(self.ERROR_LINE), {"test_beta_gate"})

    def test_ignores_output_lines_without_a_module(self):
        g = self._g()
        # alt-test basliklari parantez icermez; gercek FAIL/ERROR degildir
        self.assertEqual(g._failing_modules(self.NOISE), set())

    def test_registered_failing_file_is_not_drift(self):
        g = self._g()
        self.assertEqual(g._drift_modules(self.FAIL_LINE, {"test_alpha_gate"}, set()), set())

    def test_unregistered_failing_file_is_drift(self):
        g = self._g()
        self.assertEqual(g._drift_modules(self.FAIL_LINE, set(), set()),
                         {"test_alpha_gate"})

    def test_exempt_failing_file_is_not_drift(self):
        g = self._g()
        # EXEMPT_FROM_DIFF_GUARD gerçekten muafiyet uygular (ci'da koşmayan
        # smoke testleri full discover'da kırmızı olabilir ve bu DRIFT değildir)
        line = "FAIL: t (test_dashboard_playwright_smoke.SmokeTest.t)\n"
        self.assertEqual(
            g._drift_modules(line, set(), g.EXEMPT_FROM_DIFF_GUARD), set())

    def test_noise_never_produces_drift(self):
        g = self._g()
        self.assertEqual(g._drift_modules(self.NOISE, set(), set()), set())

if __name__ == "__main__":
    unittest.main()
