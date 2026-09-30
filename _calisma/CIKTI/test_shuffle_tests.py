#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_shuffle_tests.py — shuffle_tests.py (shuffle-audit) birim testleri.

Kontratlar (biri kırılırsa aracın kanıt değeri düşer):
  1) DETERMİNİZM — aynı seed → aynı sıra + aynı order_sha256; farklı seed →
     farklı sıra. "Şu seed ile tekrar ettim" devri bu satıra dayanır.
  2) KAPSAM — audit'in koştuğu küme check-unit-tests ile AYNI olmalı
     (sync_check_unit_tests: manifest/discover tek kaynak); ortam-bağımlı
     testler (EXCLUDE) kapsama giremez.
  3) SIRA BAĞIMLILIĞI — yeşil taban (alfabetik) + kırık karışık sıra
     = tek bulgu; bulgu şüpheli'yi (sırada hemen önce koşan testi) ADLANDIRIR.
  4) SIZINTI (polluter) — --watch mod:attr hedefi test sonrası değişirse
     değiştiren test doğrudan adlandırılır.
  5) EXIT KODLARI — 0 temiz / 1 bulgu (fail-closed) / 2 kullanım hatası.
  6) META KAYIT — aracın kendi testi manifest + HOOK_COVERAGE içinde
     (regresyon kapısı: kayıt elle bozulursa burada yakalanır).

Tüm denetimler geçici dizinlerde kurulan küçük fixture modülleriyle koşar:
OFFLINE, stdlib-only, ağ yok, gerçek repo testleri TEK TEK çalıştırılmaz.
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shuffle_tests as st  # noqa: E402
import sync_check_unit_tests as s  # noqa: E402

CLI = os.path.join(HERE, "shuffle_tests.py")


# ------------------------------------------------------------------ fixture
# İki sınıf: TestAVictim alfabetikte ÖNCE koşar (taban yeşil), TestZPolluter
# modül-global'ını kirletir. Karışık sırada polluter önce gelirse victim
# kırılır → sıra bağımlılığı KANITI. 2026-09-18 sızıntı deseninin minimali.
FIXTURE_LEAK = '''
import unittest

import leak_state


class TestAVictim(unittest.TestCase):
    def test_state_is_clean(self):
        self.assertEqual(leak_state.STATE, [],
                         "önceki test modül-global'ını geri yüklememiş")


class TestZPolluter(unittest.TestCase):
    def test_pollutes_global(self):
        leak_state.STATE.append("sızıntı")
'''

FIXTURE_GREEN = '''
import unittest


class TestAlpha(unittest.TestCase):
    def test_one(self):
        self.assertEqual(1, 1)

    def test_two(self):
        self.assertEqual("a", "a")
'''

STATE_MOD = '''
STATE = []
'''

REBIND_STATE_MOD = '''
STATE = {}
'''

# Geri yükleme YERİNDE değil, yeniden bağlama ile yapılır — repoda
# StatusBoardTests/SnapshotFileTests'in kullandığı desen. Örnekleyici anlık
# nesne referansını tutarsa burada yanlışlıkla 'sızıntı' der (false positive).
FIXTURE_REBIND = '''
import unittest

import reb_state


class TestARebindingRestore(unittest.TestCase):
    def setUp(self):
        self._old = dict(reb_state.STATE)

    def tearDown(self):
        reb_state.STATE = self._old

    def test_writes_into_global(self):
        reb_state.STATE["k"] = 1
        self.assertEqual(reb_state.STATE["k"], 1)
'''


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def run_cli(*args, **kwargs):
    """shuffle_tests.py CLI'sını alt süreçte koşur → (rc, stdout, stderr)."""
    proc = subprocess.run([sys.executable, CLI, *args], capture_output=True,
                          text=True, timeout=kwargs.get("timeout", 120),
                          env=st.child_env())
    return proc.returncode, proc.stdout, proc.stderr


def make_fixture_dir(td, leak=True):
    """Geçici test dizini kurar → (test dosyası yolu, leak_state yolu)."""
    state = _write(os.path.join(td, "leak_state.py"), STATE_MOD)
    if leak:
        target = _write(os.path.join(td, "test_leak.py"), FIXTURE_LEAK)
    else:
        target = _write(os.path.join(td, "test_green.py"), FIXTURE_GREEN)
    _write(os.path.join(td, "check_unit_tests.list"),
           "# test\n" + os.path.basename(target) + "\n")
    return target, state


# ------------------------------------------------------------------ sıra
class _Stub:
    """plan_order'ın ihtiyaç duyduğu tek şey id() — gerçek TestCase değil."""

    def __init__(self, name):
        self._name = name

    def id(self):
        return "test_mod." + self._name


class TestOrdering(unittest.TestCase):
    def _tests(self, count=6):
        return [_Stub(f"t{i}") for i in range(count)]

    def test_same_seed_same_order_and_digest(self):
        """DETERMİNİZM: aynı seed → birebir aynı sıra ve digest."""
        a = st.plan_order(self._tests(), 42)
        b = st.plan_order(self._tests(), 42)
        self.assertEqual([st.test_id(t) for t in a], [st.test_id(t) for t in b])
        self.assertEqual(st.order_digest([st.test_id(t) for t in a]),
                         st.order_digest([st.test_id(t) for t in b]))

    def test_different_seed_changes_order(self):
        """Farklı tohum → farklı sıra (yoksa audit tek tohumla kilitlenir)."""
        a = st.order_digest([st.test_id(t) for t in st.plan_order(self._tests(), 42)])
        b = st.order_digest([st.test_id(t) for t in st.plan_order(self._tests(), 7)])
        self.assertNotEqual(a, b)

    def test_group_by_class_keeps_class_blocks(self):
        """--group-by-class: sınıf blokları sabit, metotlar karışık."""
        tests = [_Stub("A.t1"), _Stub("A.t2"), _Stub("B.t1"), _Stub("B.t2")]
        got = [st.test_id(t) for t in
               st.plan_order(tests, 42, group_by_class=True)]
        classes = [i.split(".")[-2] for i in got]
        self.assertEqual(classes, sorted(classes),
                         "sınıf blokları alfabetik kalmalı")
        self.assertEqual(len(got), len(tests))

    def test_order_digest_is_position_sensitive(self):
        """Digest sırayı duyarlı: aynı küme, farklı sıra → farklı iz."""
        ids = ["m.A.t1", "m.A.t2", "m.A.t3"]
        self.assertNotEqual(st.order_digest(ids),
                            st.order_digest(["m.A.t2", "m.A.t1", "m.A.t3"]))
        self.assertEqual(st.order_digest(ids), st.order_digest(list(ids)))


# ----------------------------------------------------------------- kapsam
class TestScope(unittest.TestCase):
    def test_manifest_scope_matches_gate_manifest(self):
        """Kapsam manifest'ten okunur (kapının koştuğu küme = TEK KAYNAK)."""
        with tempfile.TemporaryDirectory() as td:
            target, _ = make_fixture_dir(td, leak=False)
            files, label = st.resolve_scope(
                type("A", (), {"tests": None, "scope": "manifest", "dir": td})())
            self.assertEqual(files, [os.path.join(td, "test_green.py")])
            self.assertIn("manifest", label)
            self.assertTrue(os.path.isfile(target))

    def test_cikti_scope_respects_exclude(self):
        """--scope cikti: keşif, EXCLUDE kümesini uygular (kopya sezgi yok)."""
        with tempfile.TemporaryDirectory() as td:
            make_fixture_dir(td, leak=False)
            _write(os.path.join(td, "test_verify_refs.py"), "pass = 1\n")
            _write(os.path.join(td, "not_a_test.py"), "pass = 1\n")
            found = st.scope_cikti(td)
            self.assertIn("test_green.py", found)
            self.assertNotIn("test_verify_refs.py", found)  # EXCLUDE
            self.assertNotIn("not_a_test.py", found)

    def test_missing_test_target_is_usage_error(self):
        """Var olmayan --tests hedefi exit 2 (sessiz boş kapsam YASAK)."""
        rc, _out, err = run_cli("--tests", "/nonexistent/test_nope.py")
        self.assertEqual(rc, 2)
        self.assertIn("HATA", err)

    def test_empty_scope_is_usage_error(self):
        with tempfile.TemporaryDirectory() as td:
            rc, _out, err = run_cli("--scope", "cikti", "--dir", td)
            self.assertEqual(rc, 2)
            self.assertIn("kapsam boş", err)


# -------------------------------------------------------------- sızıntı
class TestLeakDetection(unittest.TestCase):
    def _seeds_that_expose(self, target, state, seeds, extra=()):
        """Verilen tohumlardan ilk bulguyu üreteni döner (yoksa None)."""
        for seed in seeds:
            findings, _totals = st.audit(
                [target], [seed], 60, False, [f"leak_state:STATE"] + list(extra),
                baseline=True)
            if any(f["kind"] in ("order-dependence", "leak") for f in findings):
                return seed, findings
        return None, []

    def test_order_dependence_named_with_suspect(self):
        """Yeşil taban + kırık karışık sıra → bulgu + SUÇLU ADI."""
        with tempfile.TemporaryDirectory() as td:
            target, _state = make_fixture_dir(td, leak=True)
            seed, findings = self._seeds_that_expose(target, _state, range(1, 12))
            self.assertIsNotNone(seed, "hiçbir tohum sızıntıyı yakalamadı")
            kinds = {f["kind"] for f in findings}
            self.assertIn("order-dependence", kinds)
            od = next(f for f in findings if f["kind"] == "order-dependence")
            self.assertIn("TestAVictim", od["test"])
            # Şüpheli = sırada kırılan testten hemen önce koşan test: kirleten
            # sınıf (2026-09-18'deki LATEST/GATES sızıntılarının bulunduğu yer).
            self.assertTrue(od["suspect"], "şüpheli adlandırılmalı")
            self.assertIn("Polluter", od["suspect"])

    def test_watch_reports_direct_polluter(self):
        """--watch: KİRLETEN test doğrudan adlandırılır (polluter-finder).

        'after' = değişikliği yaratan test (suçlu), 'victim' = sırada ondan
        sonra koşan test (kurban). İkisi de raporda görünür olmalı — sadece
        kırılan testi görmek 'polluter'ı bulmaya yetmez."""
        with tempfile.TemporaryDirectory() as td:
            target, _state = make_fixture_dir(td, leak=True)
            _seed, findings = self._seeds_that_expose(target, _state, range(1, 12))
            leaks = [f for f in findings if f["kind"] == "leak"]
            self.assertTrue(leaks, "watch hedefi sızıntıyı bildirmeli")
            self.assertTrue(any("Polluter" in (f.get("after") or "") for f in leaks),
                            "sızıntıyı yaratan test adlandırılmalı")
            self.assertTrue(any("Victim" in (f.get("victim") or "") for f in leaks),
                            "kurban (sırada sonraki test) adlandırılmalı")

    def test_baseline_green_run_reports_nothing(self):
        """Temiz fixture: hiçbir bulgu yok (araç gürültü üretmemeli)."""
        with tempfile.TemporaryDirectory() as td:
            target, _state = make_fixture_dir(td, leak=False)
            findings, totals = st.audit([target], [42], 60, False, [],
                                        baseline=True)
            self.assertEqual(findings, [])
            self.assertGreater(totals["tests"], 0)

    def test_rebinding_restore_is_not_a_leak(self):
        """FALSE-POSITIVE KALKANI: yeniden bağlamayla geri yükleyen test temizdir.

        Repodaki desen (ps.LATEST = self._old_latest) örnekleyici nesne
        referansını tutarsa 'sızıntı' sanılır; hedef bağlama örnekleme
        anında çözülür, geri yükleme görünür olur."""
        with tempfile.TemporaryDirectory() as td:
            _write(os.path.join(td, "reb_state.py"), REBIND_STATE_MOD)
            target = _write(os.path.join(td, "test_rebind.py"), FIXTURE_REBIND)
            findings, _totals = st.audit([target], [42], 60, False,
                                         ["reb_state:STATE"], baseline=True)
            self.assertEqual([f for f in findings if f["kind"] == "leak"], [])

    def test_green_fixture_cli_exit_zero_and_json(self):
        """Yeşil koşum rc=0 + JSON sidecar şeması dolu (atomik yazım)."""
        with tempfile.TemporaryDirectory() as td:
            target, _state = make_fixture_dir(td, leak=False)
            out = os.path.join(td, "audit.json")
            rc, stdout, _err = run_cli("--tests", target, "--seed", "42",
                                       "--json", out)
            self.assertEqual(rc, 0, stdout)
            self.assertIn("SONUÇ: PASS", stdout)
            import json
            with open(out, encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(report["tool"], "shuffle_tests.py")
            self.assertEqual(report["seeds"], [42])
            self.assertEqual(report["findings"], [])
            self.assertIn("runs", report["totals"])

    def test_dry_run_prints_digest_without_running(self):
        """--dry-run: sıra + order_sha256 yazılır, hiçbir test koşmaz."""
        with tempfile.TemporaryDirectory() as td:
            target, _state = make_fixture_dir(td, leak=False)
            rc, stdout, _err = run_cli("--tests", target, "--dry-run")
            self.assertEqual(rc, 0)
            self.assertIn("order_sha256=", stdout)
            self.assertIn("seed=42", stdout)

    def test_child_result_json_schema(self):
        """Alt koşum sözleşmesi: ran/skip sayaçları dolu, sıra korunur."""
        with tempfile.TemporaryDirectory() as td:
            target, _state = make_fixture_dir(td, leak=False)
            out = os.path.join(td, "child.json")
            rc = st.child_main(["--_run", target, "--order", "shuffled",
                                "--seed", "42", "--result-out", out])
            self.assertEqual(rc, 0)
            import json
            with open(out, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["tests"], 2)
            self.assertEqual(len(data["ran"]), 2)
            self.assertEqual(data["failures"], [])
            self.assertEqual(data["leaks"], [])
            self.assertEqual(data["seed"], 42)

    def test_watch_target_typo_is_finding_not_silent(self):
        """--watch hedefi yoksa SESSİZ GEÇMEZ: bulgu olarak raporlanır (exit 1).

        Aksi halde 'izleme açıktı' sanılır ve sızıntı denetimi kanıtsız
        çalışıyormuş gibi görünür (fail-closed)."""
        with tempfile.TemporaryDirectory() as td:
            target, _state = make_fixture_dir(td, leak=False)
            rc, out, _err = run_cli("--tests", target, "--watch", "yok.py:NO")
            self.assertEqual(rc, 1)
            self.assertIn("SONUÇ: FAIL", out)
            rc2, out2, _e = run_cli("--tests", target, "--watch", "bicimsiz")
            self.assertEqual(rc2, 1)
            self.assertIn("SONUÇ: FAIL", out2)


# ------------------------------------------------------------ meta kayıt
class TestMetaRegistration(unittest.TestCase):
    def test_test_file_in_manifest_and_hook_coverage(self):
        """Bu testin kendisi kapı kapsamında olmalı (regresyon kapısı)."""
        self.assertIn("test_shuffle_tests.py", s.read_manifest())
        entries = s.read_hook_coverage()
        self.assertIn("test_shuffle_tests.py", entries,
                      "HOOK_COVERAGE kaydı eksik: "
                      "`python3 sync_check_unit_tests.py --update`")

    def test_exclude_shared_with_gate(self):
        """EXCLUDE tek kaynak: audit kapıyla aynı ortam-bağımlı küreyi eler."""
        self.assertIs(st._sync.EXCLUDE, s.EXCLUDE)


if __name__ == "__main__":
    unittest.main()
