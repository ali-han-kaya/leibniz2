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

# ÇAPRAZ-DOSYA fixture'ı: kirleten A dosyasında, kurban B dosyasında. Dosya
# başı kapsamda ikisi ayrı süreçte koşar (sızıntı süreç sınırını aşamaz);
# --scope flat tek süreçte koşunca kurban kirli durumla koşar.
FLAT_STATE_MOD = '''
STATE = []
'''

FLAT_POLLUTER = '''
import unittest

import flat_state


class TestPolluter(unittest.TestCase):
    def test_pollutes_global(self):
        flat_state.STATE.append("sızıntı")
'''

FLAT_VICTIM = '''
import unittest

import flat_state


class TestVictim(unittest.TestCase):
    def test_state_is_clean(self):
        self.assertEqual(flat_state.STATE, [],
                         "başka dosyadaki test modül-global'ını kirletmiş")
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


HOOK = os.path.join(HERE, "shuffle_audit_hook.sh")


def run_hook(*args, **kwargs):
    """shuffle_audit_hook.sh sarmalayıcısını (pre-commit/CI girişi) koşur.

    Gerçek ortamdan İZOLE: SHUFFLE_AUDIT_* değişkenleri testin verdiğiyle
    sabitlenir, aksi halde geliştiricinin kabuğundaki bir değişken testin
    ölçtüğü davranışı değiştirirdi.
    """
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("SHUFFLE_AUDIT_")}
    env.pop("PYTHONPATH", None)
    env.update(kwargs.get("env") or {})
    proc = subprocess.run(["bash", HOOK, *args], capture_output=True,
                          text=True, timeout=kwargs.get("timeout", 120),
                          env=env)
    return proc.returncode, proc.stdout, proc.stderr


def make_flat_dir(td):
    """İki dosyalı çapraz-dosya fixture'ı → [polluter, victim] (alfabetik)."""
    _write(os.path.join(td, "flat_state.py"), FLAT_STATE_MOD)
    polluter = _write(os.path.join(td, "test_aaa_polluter.py"), FLAT_POLLUTER)
    victim = _write(os.path.join(td, "test_zzz_victim.py"), FLAT_VICTIM)
    _write(os.path.join(td, "check_unit_tests.list"),
           "# test\ntest_aaa_polluter.py\ntest_zzz_victim.py\n")
    return [polluter, victim]


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


# ----------------------------------------------------------- flat kapsam
class TestFlatScope(unittest.TestCase):
    """--scope flat: TÜM dosyalar tek süreçte, tek global sırada.

    Varsayılan kapsamın yapısal körü: dosya başına alt süreç → çapraz-dosya
    sızıntı görünmez. Flat modu bunu kapatır; bedelli (yavaş/gürültülü)
    olduğu için varsayılan değildir ve raporda UYARI taşır.
    """

    def test_flat_scope_resolves_all_discovered_files(self):
        """--scope flat: keşif kümesi (EXCLUDE uygulanmış) tümü, flat etiketi."""
        with tempfile.TemporaryDirectory() as td:
            make_fixture_dir(td, leak=False)
            files, label = st.resolve_scope(
                type("A", (), {"tests": None, "scope": "flat", "dir": td})())
            self.assertIn(os.path.join(td, "test_green.py"), files)
            self.assertIn("flat", label)

    def test_flat_child_runs_all_files_in_one_process(self):
        """Tek alt süreç: iki dosyanın testleri de aynı koşumda + sources haritası."""
        with tempfile.TemporaryDirectory() as td:
            files = make_flat_dir(td)
            res = st.run_flat(files, "shuffled", 42, 120, False, [])
            self.assertTrue(res.get("flat"))
            self.assertEqual(res["file"], "flat:2 dosya")
            self.assertEqual(len(res["ran"]), 2)
            self.assertEqual(set(res["sources"].values()),
                             {"test_aaa_polluter.py", "test_zzz_victim.py"})

    def test_cross_file_leak_names_polluter_file_and_victim(self):
        """Flat modda çapraz-dosya sızıntı: kirletenin DOSYASI + kurban adı."""
        with tempfile.TemporaryDirectory() as td:
            files = make_flat_dir(td)
            hit = None
            for seed in range(1, 12):
                findings, _totals = st.audit(
                    files, [seed], 60, False, ["flat_state:STATE"],
                    baseline=False, flat=True)
                leaks = [f for f in findings if f["kind"] == "leak"
                         and f.get("victim") and "Victim" in f["victim"]]
                if leaks:
                    hit = (seed, leaks[0])
                    break
            self.assertIsNotNone(
                hit, "flat modda çapraz-dosya kurban adlandırılmadı")
            seed, leak = hit
            self.assertTrue(leak["file"].endswith("test_aaa_polluter.py"),
                            "bulgu kirleten testin dosyasını göstermeli")
            self.assertIn("Polluter", leak["after"])
            # Aynı tohumda dosya-başı kapsam kurbanı göremez: ayrı süreçler.
            per_file, _t = st.audit(files, [seed], 60, False,
                                    ["flat_state:STATE"], baseline=False)
            self.assertFalse([f for f in per_file
                              if f["kind"] == "order-dependence"])

    def test_flat_cli_warns_and_fails_on_cross_file_leak(self):
        """CLI: UYARI satırı + sızıntı bulgusu → exit 1 (fail-closed)."""
        with tempfile.TemporaryDirectory() as td:
            make_flat_dir(td)
            rc, out, _err = run_cli("--scope", "flat", "--dir", td,
                                    "--seed", "42",
                                    "--watch", "flat_state:STATE")
            self.assertEqual(rc, 1, out)
            self.assertIn("UYARI: tek süreç", out)
            self.assertIn("SONUÇ: FAIL", out)


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

    def test_no_baseline_flag_is_honored(self):
        """--no-baseline GERÇEKTEN tabanı atlar (sessiz no-op = sahte hız).

        Bayrak eskiden parse edilip `args.baseline = True` ile eziliyordu:
        kullanıcı tabanı kapattığını sanırken iki kat subprocess koşuyordu.
        """
        with tempfile.TemporaryDirectory() as td:
            target, _state = make_fixture_dir(td, leak=False)
            out = os.path.join(td, "audit.json")
            rc, stdout, _err = run_cli("--tests", target, "--seed", "42",
                                       "--no-baseline", "--json", out)
            self.assertEqual(rc, 0, stdout)
            import json
            with open(out, encoding="utf-8") as f:
                report = json.load(f)
            self.assertFalse(report["baseline"])
            self.assertEqual(len(report["totals"]["runs"]), 1,
                             "taban kapalıyken tek (karışık) koşum olmalı")

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


# --------------------------------------------------------- dışlama listesi
class TestExclusions(unittest.TestCase):
    """--exclude-from: ad bazlı, fail-closed, açık --tests tarafından ezilir.

    Kapı bağlaması bu bayrağa dayanır: kalıcı kırmızı (ortam/oynak) dosyalar
    kapsam dışında tutulurken YENİ dosyalar otomatik kapsamda kalmalı. Bu
    yüzden dışlama bir "izleyici listesi"dir, tersi (allowlist) değil.
    """

    def test_exclusion_shrinks_manifest_scope_and_keeps_others(self):
        """Manifest kapsamından yalnız adı geçen dosya düşer."""
        with tempfile.TemporaryDirectory() as td:
            _write(os.path.join(td, "test_keep.py"), FIXTURE_GREEN)
            _write(os.path.join(td, "test_drop.py"), FIXTURE_GREEN)
            _write(os.path.join(td, "check_unit_tests.list"),
                   "# test\ntest_keep.py\ntest_drop.py\n")
            excl = _write(os.path.join(td, "exclude.list"),
                          "# gerekçe: kalıcı kırmızı\ntest_drop.py\n")
            rc, out, err = run_cli("--scope", "manifest", "--dir", td,
                                   "--exclude-from", excl, "--list")
            self.assertEqual(rc, 0, err)
            self.assertIn("test_keep.py", out)
            self.assertNotIn("test_drop.py", out)
            self.assertIn("dışlanan: 1", err)

    def test_exclusion_is_reported_in_json(self):
        """Rapor dışlananları taşır — kapsam daralması sessiz kalmaz."""
        with tempfile.TemporaryDirectory() as td:
            _write(os.path.join(td, "test_keep.py"), FIXTURE_GREEN)
            _write(os.path.join(td, "test_drop.py"), FIXTURE_GREEN)
            _write(os.path.join(td, "check_unit_tests.list"),
                   "# test\ntest_keep.py\ntest_drop.py\n")
            excl = _write(os.path.join(td, "exclude.list"), "test_drop.py\n")
            out_json = os.path.join(td, "audit.json")
            rc, out, _err = run_cli("--scope", "manifest", "--dir", td,
                                    "--exclude-from", excl,
                                    "--json", out_json)
            self.assertEqual(rc, 0, out)
            import json
            with open(out_json, encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(report["excluded"], ["test_drop.py"])
            self.assertIn("1 dışlanan", out)

    def test_phantom_exclusion_is_usage_error(self):
        """Kapsamda olmayan girdi exit 2 (yeniden adlandırılan test sessiz
        dışlanmış sayılmaz; liste bakımı zorunlu)."""
        with tempfile.TemporaryDirectory() as td:
            make_fixture_dir(td, leak=False)
            excl = _write(os.path.join(td, "exclude.list"), "test_renamed.py\n")
            rc, _out, err = run_cli("--scope", "manifest", "--dir", td,
                                    "--exclude-from", excl)
            self.assertEqual(rc, 2)
            self.assertIn("test_renamed.py", err)

    def test_missing_exclusion_file_is_usage_error(self):
        with tempfile.TemporaryDirectory() as td:
            make_fixture_dir(td, leak=False)
            rc, _out, err = run_cli("--scope", "manifest", "--dir", td,
                                    "--exclude-from", os.path.join(td, "yok.list"))
            self.assertEqual(rc, 2)
            self.assertIn("okunamadı", err)

    def test_explicit_tests_override_exclusion(self):
        """--tests açık hedeftir: dışlama listesi onu elemez."""
        with tempfile.TemporaryDirectory() as td:
            target, _state = make_fixture_dir(td, leak=False)
            excl = _write(os.path.join(td, "exclude.list"),
                          os.path.basename(target) + "\n")
            rc, out, _err = run_cli("--tests", target,
                                    "--exclude-from", excl)
            self.assertEqual(rc, 0, out)
            self.assertIn("SONUÇ: PASS", out)


# ---------------------------------------------------------------- bütçe
class TestBudget(unittest.TestCase):
    """--budget: duvar-saati tavanı; tükenme BULGUDUR (sessiz kırpma yok)."""

    def test_zero_budget_is_finding_not_pass(self):
        """Bütçe 0 → hiç koşum yok ama exit 0 DEĞİL, adlı bulgu."""
        with tempfile.TemporaryDirectory() as td:
            make_fixture_dir(td, leak=False)
            out_json = os.path.join(td, "audit.json")
            rc, out, _err = run_cli("--scope", "manifest", "--dir", td,
                                    "--budget", "0", "--json", out_json)
            self.assertEqual(rc, 1, out)
            self.assertIn("[budget]", out)
            self.assertIn("TEMİZ SAYILMAZ", out)
            import json
            with open(out_json, encoding="utf-8") as f:
                report = json.load(f)
            self.assertTrue(report["totals"]["budget_exhausted"])
            self.assertEqual(report["totals"]["runs"], [])
            self.assertEqual([f["kind"] for f in report["findings"]], ["budget"])

    def test_generous_budget_is_not_reported(self):
        """Bütçe aşılmazsa bulgu üretilmez (gürültü yok) ve JSON'da iz kalır."""
        with tempfile.TemporaryDirectory() as td:
            target, _state = make_fixture_dir(td, leak=False)
            out_json = os.path.join(td, "audit.json")
            rc, out, _err = run_cli("--tests", target, "--budget", "120",
                                    "--json", out_json)
            self.assertEqual(rc, 0, out)
            self.assertIn("Bütçe: 120s (aşılmadı)", out)
            import json
            with open(out_json, encoding="utf-8") as f:
                report = json.load(f)
            self.assertFalse(report["totals"]["budget_exhausted"])
            self.assertEqual(report["findings"], [])


# ------------------------------------------------------- sarmalayıcı (kapı)
class TestHookWrapper(unittest.TestCase):
    """shuffle_audit_hook.sh: pre-commit + CI'ın GERÇEK giriş noktası.

    Bu sınıf kapının "kırmızıya dönebilme" sözleşmesini pinler: atlama
    satırları PASS gibi okunamaz, kırpılmış liste temiz sayılmaz, kullanım
    hatası exit 2 kalır.
    """

    def test_changed_mode_without_test_files_is_loud_skip(self):
        """Değişen test dosyası yoksa sessiz geçiş yok: PASS olmadığı yazılır."""
        with tempfile.TemporaryDirectory() as td:
            out_json = os.path.join(td, "audit.json")
            rc, out, _err = run_hook(env={"SHUFFLE_AUDIT_OUT": out_json})
            self.assertEqual(rc, 0, out)
            self.assertIn("atlandı", out)
            self.assertIn("PASS değil", out)
            self.assertIn("shuffle-audit", out)
            self.assertFalse(os.path.exists(out_json),
                             "denetim koşmadan JSON üretilmemeli")

    def test_non_test_files_are_announced_not_silently_dropped(self):
        """Ayıklanan her ad YAZILIR (sessiz kapsam kaybı yok)."""
        with tempfile.TemporaryDirectory() as td:
            out_json = os.path.join(td, "audit.json")
            rc, out, _err = run_hook("README.md", "docs/notes.md",
                                     env={"SHUFFLE_AUDIT_OUT": out_json})
            self.assertEqual(rc, 0, out)
            self.assertIn("atlandı (test dosyası değil): README.md", out)
            self.assertIn("atlandı (test dosyası değil): docs/notes.md", out)

    def test_file_cap_skips_instead_of_truncating(self):
        """Tavan aşılırsa kırpılmış liste koşulmaz; yüksek sesle ATLANDI."""
        with tempfile.TemporaryDirectory() as td:
            out_json = os.path.join(td, "audit.json")
            rc, out, _err = run_hook("a/test_one.py", "a/test_two.py",
                                     env={"SHUFFLE_AUDIT_MAX_FILES": "1",
                                          "SHUFFLE_AUDIT_OUT": out_json})
            self.assertEqual(rc, 0, out)
            self.assertIn("ATLANDI", out)
            self.assertIn("PASS değildir", out)
            self.assertFalse(os.path.exists(out_json))

    def test_default_seeds_and_budget_per_mode(self):
        """Mod başına varsayılanlar: changed=42/180 s, full=42,7,13/2400 s.

        Varsayılanlar aracın CLI'sına GERÇEKTEN ulaşmalı (env yoksa) ve
        SHUFFLE_AUDIT_SEEDS virgül/boşluk ayrımıyla çoklu tohuma açılmalı.
        """
        import json
        with tempfile.TemporaryDirectory() as td:
            target, _state = make_fixture_dir(td, leak=False)
            out_json = os.path.join(td, "audit.json")
            rc, out, _err = run_hook(target,
                                     env={"SHUFFLE_AUDIT_OUT": out_json})
            self.assertEqual(rc, 0, out)
            with open(out_json, encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(report["seeds"], [42])
            self.assertEqual(report["totals"]["budget_s"], 180)

            rc, out, _err = run_hook(target,
                                     env={"SHUFFLE_AUDIT_OUT": out_json,
                                          "SHUFFLE_AUDIT_SEEDS": "7, 13",
                                          "SHUFFLE_AUDIT_BUDGET": "90"})
            self.assertEqual(rc, 0, out)
            with open(out_json, encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(report["seeds"], [7, 13])
            self.assertEqual(report["totals"]["budget_s"], 90)
            self.assertIn("tohum: 7, 13", out)

    def test_zero_tests_is_fail_closed(self):
        """0 test = kayıt hatası: exit 0 (sahte PASS) YASAK."""
        import json
        with tempfile.TemporaryDirectory() as td:
            target, _state = make_fixture_dir(td, leak=False)
            out_json = os.path.join(td, "audit.json")
            rc, out, err = run_hook(target,
                                    env={"SHUFFLE_AUDIT_OUT": out_json,
                                         "SHUFFLE_AUDIT_BUDGET": "0"})
            self.assertEqual(rc, 1, out + err)
            self.assertIn("0 test denetlendi", err)
            with open(out_json, encoding="utf-8") as f:
                self.assertTrue(json.load(f)["totals"]["budget_exhausted"])

    def test_usage_error_keeps_exit_two(self):
        """Kullanım hatası (olmayan hedef) bulguya (1) çökertilmemeli."""
        with tempfile.TemporaryDirectory() as td:
            out_json = os.path.join(td, "audit.json")
            rc, _out, err = run_hook("test_boyle_bir_dosya_yok.py",
                                     env={"SHUFFLE_AUDIT_OUT": out_json})
            self.assertEqual(rc, 2, err)
            self.assertIn("hedefi yok", err)


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

    def test_repo_exclusion_list_is_consistent_and_non_empty(self):
        """Kapının dışlama listesi manifest'le tutarlı olmalı (fail-closed).

        Her girdi manifest'te VAR olmalı (yeniden adlandırma listeyi sessizce
        boşaltmasın) ve kalan kapsam boş OLMAMALI (boş kapsam = sahte PASS).
        Liste yalnız kalıcı kırmızı/ortam dosyalarını dışlar; yeni bir test
        dosyası otomatik olarak kapsamda kalır.
        """
        manifest = s.read_manifest()
        exclude_path = os.path.join(HERE, "shuffle_audit.exclude")
        self.assertTrue(os.path.isfile(exclude_path),
                        "shuffle_audit.exclude yok — kapı kapsamı belirsiz")
        names = st.read_exclude_file(exclude_path)
        self.assertTrue(names, "dışlama listesi boş olamaz")
        unknown = sorted(set(names) - set(manifest))
        self.assertEqual(unknown, [],
                         "manifest'te olmayan dışlama girdisi: %s" % unknown)
        kept = [t for t in manifest if t not in set(names)]
        self.assertTrue(kept, "dışlama tüm kapsamı boşalttı")


if __name__ == "__main__":
    unittest.main()
