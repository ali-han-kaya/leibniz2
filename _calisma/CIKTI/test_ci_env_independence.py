#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI-ortamı BAĞIMSIZLIĞI: testler geliştirici makinesini ölçmemeli.

ÖLÇÜLEN OLAY — PR #54 (`land/migration-gates-2026-09-30`) `Run CIKTI unit
tests` adımı 11 failure + 53 error ile düştü. Hepsi aynı kök nedendi: testler
"bu unit KURULU OLMALI" diye varsayıyordu. GitHub runner'da `_calisma/.venv_z3`,
`*/node_modules`, `apps/dashboard-next/.next/BUILD_ID` ve `history.jsonl`
(hattâ gitignored) YOKTUR — bunlar başka job'larda üretilir. Yani testler
kendi kapılarını değil, geliştirici iş istasyonunun kurulumunu ölçüyordu.

Dört düzeltmenin her biri kendi kuralını burada sabitler:

  1. `test_dev_bootstrap` gerçek-ağaç değişmezliği SNAPSHOT'a göre ölçer
     ("var/yok" değil, "DÜZENİ DEĞİŞMEDİ") → kurulu olmayan unit CI'da da geçer.
  2. `_read_report(path=None)` default'ı IMPORT anında değil ÇAĞRI anında
     `REPORT`'a bakar → testin `rdt.REPORT` yönlendirmesi sessizce yutulmaz.
  3. `next start` gerektiren canlı katmanlar, derleme yoksa SKIP (ERROR değil).
  4. `history.jsonl` (gitignored) yoksa staging ölçümü SKIP.

Kural: "eksik ön koşul" SKIP'tir, hata değil. Bir gate'in kırmızısı
"ortam eksik" ile "kapı kırık" ayrımını kaybederse fail-closed sessizleşir.
"""

import importlib
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import record_determinism_trend as rdt  # noqa: E402
import test_dashboard_next_live_stream as nls  # noqa: E402
import test_dashboard_next_request_dedup as nrd  # noqa: E402
import test_dev_bootstrap as tdb  # noqa: E402

# CI runner'da hiçbir bootstrap unit'i kurulu değil.
CI_UNPROVISIONED = (
    "_calisma/.venv_z3",
    "_calisma/pptx",
    "_calisma/docx",
    "_calisma/video",
    "apps/dashboard-next",
    "apps/trend-db",
)


def _is_ci_unprovisioned(path):
    p = str(path).replace(os.sep, "/")
    return any(u in p for u in CI_UNPROVISIONED)


class _HideUnits:
    """Bağlam yöneticisi: `os.path.exists`/`isfile`'ı CI görünümüne bağlar."""

    def __init__(self, attr="os.path.exists", extra=()):
        self._attr = attr
        self._extra = tuple(extra)
        self._real = None

    def __enter__(self):
        self._real = getattr(os.path, self._attr)

        def fake(p):
            p = str(p).replace(os.sep, "/")
            if any(e in p for e in self._extra):
                return False
            return self._real(p) and not _is_ci_unprovisioned(p)

        setattr(os.path, self._attr, fake)
        return self

    def __exit__(self, *exc):
        setattr(os.path, self._attr, self._real)
        return False


class TestReadReportDefaultBinding(unittest.TestCase):
    """Kural 2 — default arg bağlanmamalı."""

    def test_read_report_follows_module_global_at_call_time(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fake_report = os.path.join(td, "report.txt")
            with open(fake_report, "w", encoding="utf-8") as f:
                f.write("source=/x/y.tex\nverdict=PASS\n")
            orig = rdt.REPORT
            rdt.REPORT = fake_report
            try:
                # `def f(path=REPORT)` olsaydı bu None dönerdi: default
                # import anında bağlanır, testin yönlendirmesini yutar.
                self.assertIsNotNone(rdt._read_report())
                self.assertEqual(rdt._read_report()["verdict"], "PASS")
                self.assertEqual(rdt._read_report(rdt.REPORT),
                                 rdt._read_report())
            finally:
                rdt.REPORT = orig

    def test_read_report_still_returns_none_for_absent_path(self):
        self.assertIsNone(rdt._read_report("/yok/olmayan/report.txt"))


class TestRealTreeInvarianceIsSnapshotBased(unittest.TestCase):
    """Kural 1 — "kurulu mu" değil, "değişti mi" ölçülmeli."""

    def _run_invariant(self):
        suite = unittest.TestLoader().loadTestsFromName(
            "TestBrokenUnitFailsCheckClosedHermetic"
            ".test_real_tree_is_never_mutated", tdb)
        with open(os.devnull, "w") as devnull:
            return unittest.TextTestRunner(stream=devnull, verbosity=0).run(
                suite)

    def test_invariant_holds_when_no_unit_is_provisioned(self):
        """CI koşulu: hiçbir unit kurulu değil → yeşil kalmalı.

        Ölçülen: düzeltme öncesi bu koşul 9 failure üretiyordu.
        """
        with _HideUnits("exists"):
            res = self._run_invariant()
        self.assertTrue(
            res.wasSuccessful(),
            "unit kurulu değilken gerçek-ağaç değişmezliği kırıldı: %s"
            % [str(f[0]) for f in res.failures])

    def test_invariant_is_not_vacuous_on_this_machine(self):
        """Guard'ın kendisi ölçülebilir olmalı: burada unit'ler KURULU.

        Aksi halde yukarıdaki test hiçbir şey ölçmeden yeşil kalırdı —
        fail-closed'un kendisi gibi: ölçülemeyen yeşil sayılmaz.

        ÖNEMLİ: bu kontrol KURULU ORTAMI da varsayıyor. CI'da hiçbir unit
        kurulu olmadığı için "ölçülemez" durum SKIP'tir — FAIL değil. Aksi
        halde bu dosya, düzeltmeye çalıştığı hatanın ta kendisini (ortamı
        ölçmek) üretirdi: ilk CI koşusunda tam olarak bu yüzden 2 test
        düştü. Kural aynı: eksik ön koşul SKIP.
        """
        provisioned = [rel for _l, rel in tdb.SENTINELS
                       if os.path.exists(os.path.join(ROOT, rel))]
        if not provisioned:
            self.skipTest("hiçbir bootstrap unit'i kurulu değil — bu "
                          "ortamda guard'ın geçerliliği ölçülemiyor "
                          "(temiz klon / CI runner)")
        self.assertTrue(self._run_invariant().wasSuccessful())

    def test_snapshot_is_captured_in_setup(self):
        """Değişmez "var/yok" DEĞİL "değişmedi" — snapshot setUp'ta alınır."""
        import inspect
        cls = tdb.TestBrokenUnitFailsCheckClosedHermetic
        self.assertIn("_real_before",
                      inspect.getsource(cls.setUp))
        inv = inspect.getsource(cls.test_real_tree_is_never_mutated)
        self.assertNotIn("self.assertTrue(os.path.exists(abs_rel))", inv)
        self.assertIn("self.assertEqual(os.path.exists(abs_rel)", inv)


class TestLiveNextLayersSkipWithoutBuild(unittest.TestCase):
    """Kural 3 — derleme yoksa canlı katman SKIP, ERROR değil."""

    def test_both_suites_share_the_precondition_contract(self):
        self.assertEqual(nls._next_missing(), nrd._next_missing(),
                         "iki suite aynı ön koşul sözleşmesini paylaşmalı")

    def test_next_missing_reports_build_absence(self):
        with _HideUnits("isfile"):
            for mod in (nls, nrd):
                with self.subTest(mod=mod.__name__):
                    self.assertTrue(
                        mod._next_missing(),
                        "derleme yokken _next_missing() boş dönmemeli")

    def test_live_suites_skip_when_build_is_absent(self):
        """BUILD_ID + next binary yokken setUpClass SKIP'e düşmeli.

        Ölçülen: düzeltme öncesi üç sınıf da `RuntimeError` ile ERROR
        oluyordu (yani eksik ortam, kapı kusuru gibi raporlanıyordu).
        """
        with _HideUnits("isfile"):
            for mod, cls_name in ((nls, "LiveStreamTest"),
                                  (nls, "TrendWindowTest"),
                                  (nrd, "RequestDedupTest")):
                with self.subTest(suite=cls_name):
                    with self.assertRaises(unittest.SkipTest):
                        getattr(mod, cls_name).setUpClass()


class TestStagingSkipsWithoutLiveHistory(unittest.TestCase):
    """Kural 4 — gitignored `history.jsonl` yoksa staging ölçümü SKIP."""

    def _scwv(self):
        return importlib.import_module("test_surface_cwv_report")

    def test_history_constant_points_at_ignored_runtime_file(self):
        scwv = self._scwv()
        self.assertTrue(scwv.HISTORY_JSONL.endswith("history.jsonl"))
        with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
            self.assertIn("_calisma/CIKTI/history.jsonl", f.read(),
                          "history.jsonl gitignored olmaktan çıktıysa bu "
                          "SKIP gereksizleşir")

    def test_staging_test_skips_when_history_absent(self):
        scwv = self._scwv()
        method = scwv.SurfaceCwvReportContractTest(
            "test_staging_produces_preview_server_layout")
        # Sadece `history.jsonl` gizlenir: `landing.html` KURULU kalmalı, yoksa
        # test daha önceki guard'dan (üretim yapılmamış) skip olarak geçer ve
        # bizim ölçtüğümüz dal hiç çalışmaz — yani skip'in YANLIŞ sebebiyle
        # geçmiş, doğru sebeple geçmeyen bir test olurdu.
        with _HideUnits("isfile", extra=("history.jsonl",)):
            with self.assertRaises(unittest.SkipTest):
                method.test_staging_produces_preview_server_layout()

    def test_staging_test_is_not_vacuous_when_history_present(self):
        """Skip'in kendisi ölçülebilir olmalı: kurulu ortamda history VAR.

        `test_video_data_contract.py` ile aynı gerekçe — skip koşulu her
        koşuda tutulursa test hiç ölçmez ve sessizce ölür. `history.jsonl`
        gitignored olduğu için temiz klonda (ve CI'da) ölçülemez: SKIP.
        """
        scwv = self._scwv()
        if not os.path.isfile(scwv.HISTORY_JSONL):
            self.skipTest("canlı history.jsonl yok — staging guard'ının "
                          "geçerliliği bu ortamda ölçülemiyor "
                          "(temiz klon / CI runner)")
        method = scwv.SurfaceCwvReportContractTest(
            "test_staging_produces_preview_server_layout")
        method.test_staging_produces_preview_server_layout()


class TestKeyboardNavSeedsItsOwnDashboardData(unittest.TestCase):
    """Kural 5 — klavye suite'i canlı `history.jsonl` ÖLÇMEZ, kendi verisini tohumlar.

    `.rh-row` ve `#trend rect[data-tip]` yalnız `/api/run-history` ve
    `/api/trend` yanıtından doğar; bu uçlar `history.jsonl`'i okur ve o dosya
    gitignored olduğu için temiz klonda (ve CI'da) YOKTUR. Tohumlama
    yapılmazsa suite sessizce "0 satır" ölçerdi: `wait_for(attached)` zaman
    aşımı → hata, filtre testi `0 <= 0` ile boşuna geçerdi.

    Playwright'yi burada koşturmak ~90 s sürerdi; kural kaynaktan okunur
    (AST) — canlı kanıt `test_dashboard_keyboard_nav.py`'nın kendi koşusudur.
    """

    ROW_DEPENDENT = ("_first_row", "_hover_center")

    def _module(self):
        return importlib.import_module("test_dashboard_keyboard_nav")

    def test_both_seeder_helpers_exist(self):
        mod = self._module()
        for name in ("_seed_run_history", "_seed_trend"):
            self.assertTrue(callable(getattr(mod.KeyboardNavTestBase, name,
                                             None)),
                            "tohumlayıcı kayboldu: %s" % name)

    def test_seeded_tests_are_never_left_data_dependent(self):
        """Satır/grafik bekleyen her test önce tohumlamALI.

        Tohumlama çağrısı düşerse: temiz klonda hata, dolu klonda sessiz
        yeşil — yani kural yalnız `ast` ile korunabilir.
        """
        import ast
        path = os.path.join(HERE, "test_dashboard_keyboard_nav.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for fn in node.body:
                if not isinstance(fn, ast.FunctionDef) or not \
                        fn.name.startswith("test_"):
                    continue
                called = {c.func.attr for c in ast.walk(fn)
                          if isinstance(c, ast.Call)
                          and isinstance(c.func, ast.Attribute)}
                if called & set(self.ROW_DEPENDENT) and not \
                        any(c.startswith("_seed_") for c in called):
                    offenders.append("%s.%s" % (node.name, fn.name))
        self.assertEqual(offenders, [],
                         "canlı veriye bağımlı kalan testler: %s" % offenders)


if __name__ == "__main__":
    unittest.main(verbosity=2)
