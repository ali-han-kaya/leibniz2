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

stdlib only, OFFLINE — geçici dizinlerle izole çalışır.
"""

import os
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