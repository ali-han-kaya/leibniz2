#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sync_check_unit_tests.py — sync_check_unit_tests.py kapısının birim testleri.

Özellikle kural testi: _calisma/CIKTI'ya YENİ bir test_*.py dosyası
eklendiğinde check-unit-tests manifest'inin otomatik senkron davranışı:
  - discover() yeni dosyayı bulur (EXCLUDE hariç)
  - run_check() manifest güncel değilse exit 1 (fail-closed)
  - run_update() manifest'i günceller (yeni ekler, silineni çıkarır)
  - EXCLUDE setindekiler asla listeye girmez
  - gerçek repo manifest'i diskteki gerçek setle uyumlu (uyumsuzsa bu test FAIL)
    — yani gelecekte biri manifest'i bozarsa bu test yakalar (regresyon kapısı)

İKİNCİ HEDEF (2026-09-17 boşluğu): test_coverage_report.py'deki
HOOK_COVERAGE["check-unit-tests"] listesi de senkronlanır. Ölçülen kök
neden: sync_check_unit_tests.py yalnız manifest'i güncelleyip HOOK_COVERAGE'ı
unutunca check-coverage-report kapısı "uncovered" FAIL üretti
(test_texlive_determinism_id_residual.py tam bu boşluktan düştü).

stdlib only, OFFLINE — geçici dizinlerle izole çalışır.
"""

import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_check_unit_tests as s  # noqa: E402


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

    def test_drift_guard_can_still_parse_regenerated_block(self):
        """Yeniden yazılan blok, ci_full_discover_drift_guard'ın statik parse'
       ıyla okunabilir olmalı (format kontratı)."""
        entries = ["test_a.py", "test_b.py"]
        td, cov = self._env(entries, ("test_new.py",))
        try:
            s.run_update(stage=False, directory=td.name,
                         manifest=os.path.join(td.name, "mf.list"), coverage=cov)
            src = open(cov, encoding="utf-8").read()
            i = src.find('"check-unit-tests":')
            j = src.find("],", i)
            self.assertGreater(i, 0)
            self.assertGreater(j, i)
            import re as _re
            found = _re.findall(r'"([^"]+\.py)"', src[i:j + 1])
            self.assertIn("test_new.py", found)
            self.assertIn("test_a.py", found)
        finally:
            td.cleanup()

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


if __name__ == "__main__":
    unittest.main()