#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shuffle_tests.py — test izolasyonu denetimi (shuffle-audit) KALICI ARACI.

Ne kanıtlar
-----------
`check_unit_tests_hook.sh` her test dosyasını AYRI yorumlayıcıda, alfabetik
sırayla koşar. Bu, iki tür sızıntıyı yapısal olarak görünmez kılar:
çapraz-dosya sızıntısı (süreç sınırı var) ve sıra bağımlılığı (sıra sabit).
Gerçekte 2026-09-18 turunda (python-testing-patterns) seed=42 ile METOT
sırası karıştırıldığında yeşil süitenin hiç göstermediği 3 sızıntı ailesi
ortaya çıktı:

  1) `LATEST['layers']` — yedek/restore yapılmayan modül-global mutasyon
  2) `GATES` — `_patch_commands` sözlüğünün yerinde (in-place) bozulması
  3) `SSE_CLIENTS` / `STREAM_CLIENTS` — join(timeout) edilmemiş thread'in
     sızdırdığı canlı istemci

Bu aracın işi o turu TEKRARLANABİLİR kılmak: aynı seed → aynı sıra → aynı
bulgu seti. Bulgu iki kanaldan gelir:
  * ORDER-DEPENDENCE: test yalnız karıştırılmış sırada kırılıyorsa
    (alfabetik taban koşumunda geçiyor, karıştırılmışta değil). Sırada
    kendisinden ÖNCE koşan test 'şüpheli' olarak adlandırılır.
  * LEAK: `--watch mod:attr` ile izlenen modül-globalinin test sonrası
    değişmesi (değiştiren test = şüpheli, isim doğrudan çıkar).

Kapsam sınırı (dürüstlük kuralı)
--------------------------------
Kapsam BİR DOSYA İÇİDİR: her dosya kendi alt sürecinde koşar — bu, kapının
mevcut süreç-başına-dosya sözleşmesini korur (kilitlenen port/LaunchAgent/
ağ yüzeyi yeni risk almaz) ve asıl sızıntı yüzeyini (dosya içi sıra)
ölçer. Çapraz-dosya sızıntı bu kapsamda YAPISAL OLARAK GÖRÜNMEZ.

`--scope flat` bunu kapatır: kapsamdaki TÜM dosyalar TEK alt süreçte, tek
global sırada koşar; `--watch` hedefi dosya sınırını aşan sızıntıyı da
adlandırır (kirleten testin dosyası + sırada sonra koşan kurban). Bedeli
açıkça ödenir: tek süreç = yavaşlama ve çapraz-test gürültüsü (bir testin
bıraktığı thread/port diğerini etkileyebilir), bu yüzden bu mod varsayılan
DEĞİLDİR ve raporda UYARI satırı taşır. Sızıntı bulgusu `file` alanında
kirleten testin (kurbanın değil) dosyasını gösterir.

Ortam-bağımlı testler (launchctl/daemon/canlı sunucu/ağ) kapsam DIŞIDIR:
EXCLUDE listesi TEK KAYNAK'tır (sync_check_unit_tests.EXCLUDE — check-unit-tests
kapısıyla aynı küme; kopya sezgi yok).

Kullanım
--------
    python3 shuffle_tests.py                       # kapsam=manifest, seed=42
    python3 shuffle_tests.py --seed 7 --seed 13    # çoklu tohum (geçmiş sözleşme)
    python3 shuffle_tests.py --tests test_a.py test_b.py
    python3 shuffle_tests.py --scope cikti         # manifest yerine disk keşfi
    python3 shuffle_tests.py --scope flat --watch preview_server:LATEST
                                                    # TÜM CIKTI tek süreçte:
                                                    # çapraz-dosya sızıntı da görünür
    python3 shuffle_tests.py --group-by-class      # sınıf blokları sabit, metotlar karışık
    python3 shuffle_tests.py --watch coordinator_loop:LATEST \
                             --watch preview_server:SSE_CLIENTS
    python3 shuffle_tests.py --dry-run             # sıra planı + order_sha256, koşum yok
    python3 shuffle_tests.py --list                # kapsam dosyalarını yaz
    python3 shuffle_tests.py --json audit.json     # makine-okur sidecar (atomik)

Kapı bağlaması (pre-commit + CI):
    python3 shuffle_tests.py --scope manifest \
        --exclude-from shuffle_audit.exclude --seed 42 --seed 7 --seed 13 \
        --budget 900 --json logs/shuffle_audit.json

`--exclude-from` ad bazlı bir dışlama listesi okur (yorumlu); kapsamda
olmayan girdi exit 2'dir (yeniden adlandırılan test sessizce dışlanmış
sayılmaz). `--budget` duvar-saati tavanıdır: dolduğunda kalan koşumlar
yapılmaz ve `kind="budget"` bulgusu üretilir — kırpılmış denetim temiz
sayılmaz.

Exit kodu: 0 = temiz (bulgu yok), 1 = bulgu (fail-closed: sıra bağımlılığı /
sızıntı / alt süreç hatası / zaman aşımı / tükenen bütçe), 2 = kullanım/ortam
hatası.

Yalnızca Python 3 standart kütüphanesi (unittest, random, subprocess). Ağ yok,
yazma yok (yalnız --json sidecar'ı yazılır), stdlib-only ve OFFLINE.

Determinizm sözleşmesi
----------------------
`--seed` verilmezse 42. Aynı seed + aynı kapsam → aynı sıra → aynı
`order_sha256` (raporda yazılır): bir bulguyu "şu seed ile tekrar ettim"
diye başka birine devretmek mümkündür. `PYTHONDONTWRITEBYTECODE=1` alt
sürece geçirilir (CIKTI ağacında __pycache__ bırakılmaz).

Meta kayıt sözleşmesi (bu dosya nasıl "repodadır")
--------------------------------------------------
Bu aracın testi `test_shuffle_tests.py` check-unit-tests kapsamındadır;
`check_unit_tests.list` + `test_coverage_report.HOOK_COVERAGE` kayıtları
`sync_check_unit_tests.py --update` ile TEK KAYNAK üretiminden gelir (elle
liste bakımı yok). Aracın kendisi koşu anında manifest'i okur — kopya yok.
"""
import argparse
import hashlib
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# TEK KAYNAK: ortam-bağımlı test kümesi + manifest okuma/keşif aynı modülden
# gelir (check-unit-tests kapısıyla birebir aynı sözleşme).
import sync_check_unit_tests as _sync  # noqa: E402

MANIFEST = _sync.MANIFEST
# Tarihsel tohum kümesi (2026-09-18 turu: 42/7/13 yeşildi). Varsayılan tek
# tohum — çoklu tohum yalnız şüpheli doğrulaması içindir.
DEFAULT_SEED = 42
DEFAULT_TIMEOUT_S = 300
# Bütçe tavanında son bir dosyaya 1 s'lik dilim vermek onu yapay olarak
# düşürür (sahte timeout/"sonuç okunamadı" bulgusu). Bu eşiğin altında
# kalındıysa koşum BAŞLATILMAZ: durum dürüstçe "bütçe tükendi" olur.
BUDGET_MIN_SLOT_S = 5.0


class BudgetExhausted(Exception):
    """Duvar-saati bütçesi tükendi — sessiz kırpma değil, BULGU."""


def read_exclude_file(path):
    """Dışlama listesini okur (# yorum + boş satır atlanır; ad bazlı).

    Girdiler dosya ADI olarak karşılaştırılır (manifest girdileri gibi) —
    mutlak yol yazmak taşınabilirliği bozardı. Okunamayan dosya fail-closed:
    dışlama sessizce boşalmış gibi davranmak kapsamı genişletip çıktıyı
    yanlış kırmızıya boyardı.
    """
    names = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if line:
                    names.append(os.path.basename(line))
    except OSError as exc:
        raise SystemExit(_usage(f"--exclude-from okunamadı: {path} ({exc})"))
    return names


def apply_exclusions(files, exclude_path):
    """Kapsamdan ad bazlı dışlar → (kalan dosyalar, dışlanan adlar).

    Fazlalık (kapsamda olmayan girdi) fail-closed: yeniden adlandırılmış ya
    da düzeltilmiş bir test sessizce dışlanmış sayılmaz — liste bakımı
    zorunlu kalır. `--tests` verildiğinde çağrılmaz: açık hedef kazanır.
    """
    names = read_exclude_file(exclude_path)
    have = {os.path.basename(f): f for f in files}
    unknown = sorted(set(names) - set(have))
    if unknown:
        raise SystemExit(_usage(
            "--exclude-from: kapsamda olmayan girdi(ler): " + ", ".join(unknown)))
    drop = set(names)
    kept = [f for f in files if os.path.basename(f) not in drop]
    return kept, sorted(drop)


# ---------------------------------------------------------------- yardımcılar
def test_id(t):
    """unittest TestCase → 'modüle.Class.method' kimliği (deterministik)."""
    return t.id()


def flatten(suite):
    """TestSuite ağacını TestCase listesine düzleştirir (sıra korunur)."""
    out = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            out.extend(flatten(item))
        else:
            out.append(item)
    return out


def load_module_tests(path):
    """Tek test dosyasını yükler → TestCase listesi (içe aktarım dahil).

    Dosyanın kendi dizini sys.path'e eklenir; böylece geçici dizindeki
    fixture modülleri de (test izolasyonu) gerçek modül gibi koşar.
    """
    d = os.path.dirname(os.path.abspath(path))
    if d not in sys.path:
        sys.path.insert(0, d)
    name = os.path.basename(path)
    if name.endswith(".py"):
        name = name[:-3]
    suite = unittest.TestLoader().loadTestsFromName(name)
    return flatten(suite)


def load_tests_for(paths, flat=False):
    """Dosya listesini yükler → (testler, id→dosya haritası, yükleme hataları).

    flat=True: tüm dosyalar AYNI yorumlayıcıda yüklenir (tek süreç, global
    sıra) — çapraz-dosya sızıntısını görünür kılan yol. Harita bulguyu
    kirleten testin DOSYASINA bağlar; tek süreçte `file` alanı tek başına
    kapsam etiketidir, kimin kimi kirlettiğini söylemez.
    """
    tests, sources, errors = [], {}, []
    for path in paths:
        name = os.path.basename(os.path.abspath(path))
        try:
            group = load_module_tests(path)
        except Exception as exc:  # noqa: BLE001 — içe aktarım hatası BULGUDUR
            # Tek bozuk dosya kapsamı KİLİTLEMEMELİ: hata kaydedilir, diğer
            # dosyalar yüklenir (flat modda aksi halde tüm denetim ölür ve
            # bozuk dosya sessizce kapsam dışı kalırdı).
            errors.append({"file": name,
                           "detail": f"{type(exc).__name__}: {exc}"})
            continue
        for t in group:
            tests.append(t)
            sources[test_id(t)] = name
    return tests, sources, errors


def plan_order(tests, seed, group_by_class=False):
    """Test listesini seed'e göre karıştırır (tek kaynak: plan üretimi).

    group_by_class=True: sınıf blokları alfabetik sabit kalır, metotlar
    karışır — sınıf-kapsamlı state (setUpClass) olan yüzeylerde kullanılır.
    group_by_class=False (varsayılan): sınıflar da metotlar da serbest —
    2026-09-18'de sınıflar ARASI sızıntıyı bulan mod budur.
    """
    items = list(tests)
    if not group_by_class:
        random.Random(seed).shuffle(items)
        return items
    buckets = {}
    for t in items:
        key = test_id(t).rsplit(".", 1)[0]
        buckets.setdefault(key, []).append(t)
    rng = random.Random(seed)
    ordered = []
    for key in sorted(buckets):
        group = buckets[key]
        rng.shuffle(group)
        ordered.extend(group)
    return ordered


def order_digest(ids):
    """Sıranın kanıt parmak izi: aynı seed → aynı digest (reproducibility)."""
    h = hashlib.sha256()
    for i in ids:
        h.update(i.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def snapshot_targets(specs):
    """--watch 'mod:attr' girdilerini çözümler → [(spec, modül, attr)].

    Çözümlenemeyen hedef fail-closed: kullanım hatası (exit 2), sessizce
    yok sayım yok — aksi halde 'izleme açıktı' yanılgısı doğar.

    NESNE değil (modül, attr) saklanır: teardown'lar globali yerinde
    bozmak yerine YENİDEN BAĞLAYARAK geri yükleyebilir
    (`ps.LATEST = self._old_latest`). Örneklenen anlık bağlama bakılmazsa
    gerçekten temiz bir geri yükleme yanlışlıkla 'sızıntı' sayılırdı
    (ölçülen false positive — bu yüzden bağlama örnekleme anında çözülür).
    """
    out = []
    for spec in specs:
        if ":" not in spec:
            raise ValueError(f"--watch hedefi 'modul:attr' biçiminde olmalı: {spec}")
        mod_name, attr = spec.split(":", 1)
        mod = sys.modules.get(mod_name)
        if mod is None:
            try:
                __import__(mod_name)
            except ImportError as exc:
                raise ValueError(f"--watch modülü içe aktarılamadı: {mod_name} ({exc})")
            mod = sys.modules[mod_name]
        if not hasattr(mod, attr):
            raise ValueError(f"--watch hedefi yok: {mod_name}.{attr}")
        out.append((spec, mod, attr))
    return out


def _fingerprint(value):
    """Kıyaslanabilir, derin kopyası güvenli parmak izi (containers)."""
    if isinstance(value, dict):
        return ("dict", len(value), repr(sorted((repr(k), repr(v)) for k, v in value.items())))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, len(value), repr([repr(x) for x in value]))
    if isinstance(value, (set, frozenset)):
        return (type(value).__name__, len(value), repr(sorted(repr(x) for x in value)))
    if isinstance(value, bytearray):
        return ("bytearray", bytes(value))
    return ("scalar", repr(value))


def take_snapshot(targets):
    """İzlenen hedeflerin parmak izini alır → {spec: fingerprint}.

    Bağlama ÖRNEKLEME ANINDA çözülür (snapshot_targets'in gerekçesi):
    geri yükleme 'yerinde' ise parmak izi değişir, 'yeniden bağlama' ile
    ise temiz görünür.
    """
    return {spec: _fingerprint(getattr(mod, attr)) for spec, mod, attr in targets}


def diff_snapshots(before, after):
    """İki snapshot arasında DEĞİŞEN hedefleri döner (sızıntı adayları)."""
    return [spec for spec, value in after.items() if before.get(spec) != value]


# ------------------------------------------------------------- alt süreç
class _OrderedResult(unittest.TextTestResult):
    """Test sonuçlarını KOŞULDUĞU SIRAYLA toplar (sıra bağımlılığı kanıtı)."""

    def __init__(self, stream, watch_specs=None):
        super().__init__(stream, False, 0)
        self.ran = []
        self.failures_ = []
        self.errors_ = []
        self.skipped_ = []
        # Sızıntı örneklemesi: unittest doCleanups()'ı stopTest'TEN ÖNCE
        # çalıştırır; örnekleme burada yapılır, böylece "restore eden" test
        # yanlışlıkla suçlanmaz. Sızıntı tanımı = test bittikten SONRA hâlâ
        # bozulmuş global (bir sonraki teste sızar).
        self.watch = list(watch_specs or [])
        self.base = take_snapshot(self.watch) if self.watch else {}
        self.leaks = []

    def startTest(self, test):
        self.ran.append(test_id(test))
        super().startTest(test)

    def addFailure(self, test, err):
        self.failures_.append({"id": test_id(test),
                               "detail": self._exc_info_to_string(err, test)})
        super().addFailure(test, err)

    def addError(self, test, err):
        self.errors_.append({"id": test_id(test),
                              "detail": self._exc_info_to_string(err, test)})
        super().addError(test, err)

    def addSkip(self, test, reason):
        self.skipped_.append({"id": test_id(test), "reason": reason})
        super().addSkip(test, reason)

    def stopTest(self, test):
        if not self.watch:
            return super().stopTest(test)
        now = take_snapshot(self.watch)
        for spec in diff_snapshots(self.base, now):
            self.leaks.append({"target": spec, "after": test_id(test),
                               "previous": self.ran[-2] if len(self.ran) > 1 else None})
        self.base = now
        super().stopTest(test)


def child_main(argv):
    """Verilen testleri (tek dosya ya da --_run-flat ile tüm kapsam) koşup
    JSON sonucu yazar (iç mod).

    Çıktı KANALA değil dosyaya gider: unittest'in kendi stderr/stdout
    gürültüsü sonucu bozamaz.
    """
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--_run", default=None)
    ap.add_argument("--_run-flat", dest="_run_flat", action="store_true")
    ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--order", default="shuffled", choices=["shuffled", "alphabetical"])
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--result-out", required=True)
    ap.add_argument("--group-by-class", action="store_true")
    ap.add_argument("--watch", action="append", default=[])
    args = ap.parse_args(argv)

    flat = bool(args._run_flat)
    if flat and not args.path:
        print("HATA: --_run-flat en az bir --path ister", file=sys.stderr)
        return 2
    if not flat and not args._run:
        print("HATA: --_run ya da --_run-flat gerekli", file=sys.stderr)
        return 2
    paths = ([os.path.abspath(p) for p in args.path] if flat
             else [args._run])
    label = f"flat:{len(paths)} dosya" if flat else args._run
    out = {"file": label, "flat": flat, "order": args.order, "seed": args.seed,
           "tests": 0, "ran": [], "failures": [], "errors": [],
           "skipped": [], "leaks": [], "sources": {}, "import_error": None}
    try:
        tests, sources, load_errors = load_tests_for(paths, flat=flat)
    except Exception as exc:  # noqa: BLE001 — içe aktarım hatası bulgudur
        out["import_error"] = f"{type(exc).__name__}: {exc}"
        _write_json(args.result_out, out)
        return 1
    out["sources"] = sources
    out["import_errors"] = load_errors

    if args.order == "alphabetical":
        ordered = sorted(tests, key=test_id)
    else:
        ordered = plan_order(tests, args.seed, group_by_class=args.group_by_class)
    out["tests"] = len(ordered)
    out["order_sha256"] = order_digest([test_id(t) for t in ordered])

    try:
        specs = snapshot_targets(args.watch)
    except ValueError as exc:
        out["import_error"] = str(exc)
        _write_json(args.result_out, out)
        return 2

    stream = io.StringIO()
    suite = unittest.TestSuite(ordered)
    result = _OrderedResult(stream, specs)
    result.startTestRun()
    suite.run(result)
    result.stopTestRun()
    out["ran"] = result.ran
    out["failures"] = result.failures_
    out["errors"] = result.errors_
    out["skipped"] = result.skipped_
    out["leaks"] = result.leaks
    _write_json(args.result_out, out)
    return 0


# ----------------------------------------------------------------- ebeveyn
def _write_json(path, data):
    """Atomik JSON yazım (tmp + replace) — yarım sidecar bırakmaz."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=os.path.basename(path) + ".tmp.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def child_env():
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # CIKTI ağacında __pycache__ bırakma
    return env


def _child_cmd(order, seed, group_by_class, watch):
    """Geri kalanı eklenmemiş alt süreç komutu (tek yer: --order/--seed/--watch)."""
    cmd = [sys.executable, os.path.abspath(__file__),
           "--order", order, "--seed", str(seed)]
    if group_by_class:
        cmd.append("--group-by-class")
    for spec in watch or []:
        cmd += ["--watch", spec]
    return cmd


def _run_child(cmd, timeout, label):
    """Alt süreci koşur, JSON sonucunu okur. Zaman aşımı = bulgu (fail-closed)."""
    fd, res_path = tempfile.mkstemp(prefix="shuffle_audit_", suffix=".json")
    os.close(fd)
    cmd = cmd + ["--result-out", res_path]
    started = time.time()
    status = {"timed_out": False, "rc": None}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, env=child_env())
        status["rc"] = proc.returncode
        stderr = proc.stderr
    except subprocess.TimeoutExpired:
        status["timed_out"] = True
        stderr = ""
    try:
        with open(res_path, encoding="utf-8") as fh:
            result = json.load(fh)
    except (OSError, ValueError) as exc:
        result = {"file": label, "order": "?", "seed": 0, "tests": 0,
                  "ran": [], "failures": [], "errors": [], "skipped": [],
                  "leaks": [], "sources": {},
                  "import_error": f"sonuç okunamadı: {exc}"}
    finally:
        try:
            os.unlink(res_path)
        except OSError:
            pass
    result["timed_out"] = status["timed_out"]
    result["rc"] = status["rc"]
    result["duration_s"] = round(time.time() - started, 3)
    if stderr.strip():
        result["stderr_tail"] = stderr.strip()[-600:]
    return result


def run_file(path, order, seed, timeout, group_by_class, watch):
    """Tek dosyayı kendi alt sürecinde koşur (varsayılan kapsam)."""
    cmd = _child_cmd(order, seed, group_by_class, watch) + [
        "--_run", os.path.abspath(path)]
    return _run_child(cmd, timeout, os.path.abspath(path))


def run_flat(files, order, seed, timeout, group_by_class, watch):
    """TÜM dosyaları TEK alt süreçte, tek global sırada koşur (--scope flat)."""
    cmd = _child_cmd(order, seed, group_by_class, watch) + ["--_run-flat"]
    for path in files:
        cmd += ["--path", os.path.abspath(path)]
    return _run_child(cmd, timeout, "flat:%d dosya" % len(files))


def audit(files, seeds, timeout, group_by_class, watch, baseline=True, flat=False,
          budget=None):
    """Denetimi koşar: bulgu listesi + özet döner (saf, yan etkisiz).

    baseline: alfabetik sıradaki koşum. Yalnız karıştırılmış sırada kırılan
    testler "order-dependence" sayılır — sıra bağımlılığının tanımı budur
    (yeşil taban + kırık karışık sıra).

    flat=True: kapsamdaki tüm dosyalar TEK alt süreçte, tek global sırada
    koşar; bulgular kirleten testin dosyasına bağlanır (sources haritası).

    budget: duvar-saati tavanı (s). Dolduğunda kalan koşumlar YAPILMAZ ve
    `kind="budget"` bulgusu üretilir — kırpılmış denetim "temiz" SAYILMAZ
    (fail-closed). Alt süreç zaman aşımı da kalan bütçeyle sınırlanır ki tek
    bir yavaş dosya tavanı aşamasın.
    """
    findings = []
    per_run = []
    base_ok = set()  # (dosya, test_id) — alfabetik tabanda da kırılanlar
    t0 = time.time()
    deadline = (t0 + float(budget)) if budget is not None else None
    budget_hit = None  # (denetlenmeyen dosya sayısı, ilk dosya adı)

    def remaining():
        return None if deadline is None else deadline - time.time()

    def file_of(result, tid):
        """Test id → dosya adı; flat koşumda sources, tek dosyada kapsam."""
        return (result.get("sources") or {}).get(tid) or result["file"]

    def collect(result, order_label, seed):
        broke = {f["id"] for f in result["failures"]} | {e["id"] for e in result["errors"]}
        prev = {}
        for idx, tid in enumerate(result["ran"]):
            if tid in broke:
                prev[tid] = result["ran"][idx - 1] if idx else None
        per_run.append({
            "file": os.path.basename(result["file"]), "order": order_label,
            "seed": seed, "tests": result.get("tests", 0),
            "skipped": len(result.get("skipped", [])),
            "duration_s": result.get("duration_s"),
            "order_sha256": result.get("order_sha256"),
            "broken": sorted(broke), "suspect": prev,
        })
        if result.get("timed_out"):
            findings.append({"kind": "timeout", "file": result["file"],
                             "detail": f"{timeout}s içinde bitmedi (order={order_label}, seed={seed})"})
        if result.get("import_error"):
            findings.append({"kind": "error", "file": result["file"],
                             "detail": result["import_error"]})
        for err in result.get("import_errors") or []:
            findings.append({"kind": "error", "file": err["file"],
                             "detail": err["detail"]})
        for leak in result.get("leaks", []):
            # Kurban = kirleten testten hemen sonra koşan test. Yoksa sızıntı
            # run sonunda kalmıştır: yine bulgudur (restore edilmemiş), ama
            # bu koşumda kimseyi bozmadı — metin ayrımı dürüstlük için.
            order = result.get("ran") or []
            culprit = leak["after"]
            idx = order.index(culprit) if culprit in order else -1
            victim = order[idx + 1] if 0 <= idx < len(order) - 1 else None
            findings.append({"kind": "leak", "file": file_of(result, culprit),
                             "target": leak["target"], "after": culprit,
                             "suspect": leak["previous"], "victim": victim,
                             "order": order_label, "seed": seed,
                             "detail": f"{leak['target']} {culprit} tarafından bozuldu"
                                       + (f" → sonraki test {victim} kirli durumla koştu"
                                          if victim else
                                          " (run sonunda kaldı, kurban yok)")})
        return broke, prev

    # flat: tek süreç → dosya döngüsü tek koşuma çöker (path=None).
    for index, path in enumerate(files if not flat else [None]):
        def _run(order, seed):
            left = remaining()
            if left is not None and left < BUDGET_MIN_SLOT_S:
                raise BudgetExhausted
            # Tek alt süreç tavanı kalan bütçeyi AŞAMAZ.
            limit = timeout if left is None else max(BUDGET_MIN_SLOT_S,
                                                     min(timeout, left))
            if flat:
                return run_flat(files, order, seed, limit, group_by_class,
                                watch)
            return run_file(path, order, seed, limit, group_by_class, watch)

        try:
            if baseline:
                # Taban: alfabetik sıra. Burada da kırılan test sıra-bağımlı
                # DEĞİLDİR (koşum ortamına bağlıdır) — kanıta girmesin.
                base = _run("alphabetical", DEFAULT_SEED)
                base_broke, _ = collect(base, "alphabetical", DEFAULT_SEED)
                base_ok |= {(file_of(base, t), t) for t in base_broke}
            for seed in seeds:
                res = _run("shuffled", seed)
                broke, prev = collect(res, "shuffled", seed)
                for tid in sorted(broke):
                    if baseline and (file_of(res, tid), tid) in base_ok:
                        continue  # tabanda da kırık → sıra bağımlılığı değil
                    findings.append({
                        "kind": "order-dependence", "file": file_of(res, tid),
                        "test": tid, "suspect": prev.get(tid),
                        "detail": "yalnız karıştırılmış sırada kırıldı",
                    })
        except BudgetExhausted:
            unrun = len(files) - index
            budget_hit = (unrun, os.path.basename(path) if path else "flat")
            break

    if budget_hit is not None:
        unrun, first = budget_hit
        findings.append({
            "kind": "budget", "file": first,
            "detail": (f"{budget:g}s bütçe tükendi — {unrun} dosya denetlenmedi "
                       f"(ilk: {first}); kırpılmış denetim TEMİZ SAYILMAZ"),
        })

    totals = {
        "files": len(files), "seeds": list(seeds), "flat": flat,
        "tests": sum(r["tests"] for r in per_run),
        "skipped": sum(r["skipped"] for r in per_run),
        "duration_s": round(time.time() - t0, 2),
        "runs": per_run, "budget_s": budget,
        "budget_exhausted": budget_hit is not None,
    }
    return aggregate(findings), totals


def aggregate(findings):
    """Aynı SUÇLU+hedef sızıntılarını tek satırda toplar.

    Bir polluter her koşumda (ve her tohumda) birden fazla olay üretebilir
    (globali kademeli olarak kirletir). 48 ham kaydı okunabilir 5 satıra
    indirmeden rapor, eylem listesi hâline gelmez.
    """
    out, leaks = [], {}
    for f in findings:
        if f["kind"] != "leak":
            out.append(f)
            continue
        key = (f["file"], f["target"], f["after"])
        g = leaks.setdefault(key, {
            "kind": "leak", "file": f["file"], "target": f["target"],
            "after": f["after"], "suspect": f.get("suspect"),
            "victim": f.get("victim"), "victims": set(), "orders": set(),
            "occurrences": 0})
        g["occurrences"] += 1
        g["orders"].add(str(f.get("order", "?")))
        if f.get("victim"):
            g["victims"].add(f["victim"])
            g["victim"] = f["victim"]
    for g in leaks.values():
        g["victims"] = sorted(g["victims"])
        g["orders"] = sorted(g["orders"])
        g["detail"] = (
            f"{g['target']} {g['after']} tarafından bozuldu — {g['occurrences']} kez"
            f" ({', '.join(g['orders'])} sırasında) · kirli koşan sonraki test: "
            + (", ".join(g["victims"]) if g["victims"]
               else "yok (run sonunda kaldı)"))
        out.append(g)
    out.sort(key=lambda f: (f["kind"] != "order-dependence",
                            -f.get("occurrences", 0)))
    return out


def render_text(findings, totals, scope_label, group_by_class, flat=False,
                excluded=None):
    lines = ["=== shuffle-audit (shuffle_tests.py) ==="]
    scope = f"Kapsam: {scope_label} ({totals['files']} dosya"
    if excluded:
        scope += f", {len(excluded)} dışlanan"
    scope += ")"
    lines.append(f"{scope} · tohum: "
                 f"{', '.join(str(s) for s in totals['seeds'])} · "
                 f"sıra: {'sınıf bloklu' if group_by_class else 'tam karışık'}")
    if totals.get("budget_s") is not None:
        state = "TÜKENDİ" if totals.get("budget_exhausted") else "aşılmadı"
        lines.append(f"Bütçe: {totals['budget_s']:g}s ({state})")
    if flat:
        lines.append("UYARI: tek süreç (--scope flat) — çapraz-dosya sızıntı "
                     "görünür, ama çapraz-test gürültüsü ve yavaşlama bedeli "
                     "bu moda aittir.")
    lines.append(f"Koşum: {len(totals['runs'])} alt koşum · {totals['tests']} test · "
                 f"SKIP {totals['skipped']} · {totals['duration_s']}s")
    if not findings:
        lines.append("Bulgu yok — karıştırılmış sıra tabanla aynı davranışı koruyor.")
        lines.append("SONUÇ: PASS")
        return "\n".join(lines)
    for f in findings:
        head = f"[{f['kind']}] {os.path.basename(f.get('file', ''))}"
        if f.get("test"):
            head += f" :: {f['test']}"
        lines.append(head)
        if f["kind"] == "leak":
            lines.append(f"    hedef: {f.get('target')} · değiştiren test: {f.get('after')}")
        elif f.get("suspect"):
            lines.append(f"    şüpheli (sırada hemen önce koşan test): {f['suspect']}")
        lines.append(f"    {f.get('detail', '')}")
    lines.append(f"SONUÇ: FAIL ({len(findings)} bulgu)")
    return "\n".join(lines)


# ------------------------------------------------------------------- main
def scope_manifest(directory=None):
    """check-unit-tests koşu listesi (kapının gerçekten koştuğu küme)."""
    manifest = os.path.join(directory or HERE, "check_unit_tests.list")
    return _sync.read_manifest(manifest)


def scope_cikti(directory=None):
    """Disk keşfi: CIKTI'daki test_*.py (EXCLUDE düşülmüş)."""
    return _sync.discover(directory or HERE)


def resolve_scope(args):
    if args.tests:
        missing = [t for t in args.tests if not os.path.isfile(t)]
        if missing:
            raise SystemExit(_usage(f"--tests hedefi yok: {', '.join(missing)}"))
        return list(args.tests), "tests"
    if args.scope == "flat":
        # TÜM CIKTI testleri (disk keşfi, EXCLUDE uygulanmış) tek süreçte.
        files = scope_cikti(args.dir)
        return [os.path.join(args.dir or HERE, f) for f in files], \
            "flat(tek süreç, keşif)"
    if args.scope == "cikti":
        files = scope_cikti(args.dir)
        return [os.path.join(args.dir or HERE, f) for f in files], "cikti(keşif)"
    return [os.path.join(args.dir or HERE, f) for f in scope_manifest(args.dir)], \
        "manifest(check_unit_tests.list)"


def _usage(msg):
    print(f"HATA: {msg}", file=sys.stderr)
    print("Yardım: python3 shuffle_tests.py --help", file=sys.stderr)
    return 2


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--_run" in argv or "--_run-flat" in argv:
        return child_main(argv)

    ap = argparse.ArgumentParser(
        description="shuffle-audit: test sırası bağımlılığı/sızıntı denetimi")
    ap.add_argument("--seed", type=int, action="append",
                    help=f"tohum (varsayılan {DEFAULT_SEED}; birden çok kez "
                         "verilebilir)")
    ap.add_argument("--scope", choices=["manifest", "cikti", "flat"],
                    default="manifest",
                    help="kapsam: manifest (kapı listesi) | cikti (disk keşfi) | "
                         "flat (TÜM CIKTI tek süreçte: çapraz-dosya sızıntı "
                         "görünür; yavaş + gürültülü)")
    ap.add_argument("--tests", nargs="+", metavar="F",
                    help="yalnız bu dosyaları denetle (kapsam bayrağını ve "
                         "dışlama listesini ezer: açık hedef kazanır)")
    ap.add_argument("--exclude-from", dest="exclude_from", default=None,
                    metavar="PATH",
                    help="kapsamdan dışlanacak dosya adları (# yorumlu liste); "
                         "kapsamda olmayan girdi fail-closed (exit 2)")
    ap.add_argument("--budget", type=float, default=None, metavar="S",
                    help="duvar-saati bütçesi (s); dolduğunda kalan koşumlar "
                         "yapılmaz ve fail-closed 'budget' bulgusu üretilir")
    ap.add_argument("--dir", default=None, help="test dizini (izole koşum)")
    ap.add_argument("--group-by-class", action="store_true",
                    help="sınıf bloklarını sabit tut, metotları karıştır")
    ap.add_argument("--watch", action="append", default=[], metavar="MOD:ATTR",
                    help="izlenen modül-globali (sızıntı tespiti)")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S,
                    help=f"alt süreç tavanı (s, varsayılan {DEFAULT_TIMEOUT_S}); "
                         "--scope flat'te TÜM kapsam tek süreç olduğu için bu "
                         "tavan bütün koşuma uygulanır")
    ap.add_argument("--no-baseline", dest="baseline", action="store_false",
                    help="alfabetik taban koşumunu atla (daha hızlı, "
                         "sıra bağımlılığı iddiası zayıflar)")
    ap.add_argument("--list", action="store_true", help="kapsamı yaz ve çık")
    ap.add_argument("--dry-run", action="store_true",
                    help="yalnız sıra planını + order_sha256 yaz, koşum yapma")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="makine-okur rapor (atomik sidecar)")
    args = ap.parse_args(argv)

    seeds = args.seed if args.seed else [DEFAULT_SEED]
    if args.budget is not None and args.budget < 0:
        return _usage("--budget negatif olamaz")
    try:
        files, scope_label = resolve_scope(args)
        excluded = []
        # Açık --tests hedefi kazanır; dışlama yalnız toplu kapsamda uygulanır.
        if args.exclude_from and not args.tests:
            files, excluded = apply_exclusions(files, args.exclude_from)
    except SystemExit as e:
        return e.code
    if not files:
        return _usage("kapsam boş — test dosyası bulunamadı")

    if args.list:
        for f in files:
            print(f)
        if excluded:
            print(f"[shuffle-audit] dışlanan: {len(excluded)}", file=sys.stderr)
        return 0

    flat = args.scope == "flat"
    if flat and scope_label == "tests":
        scope_label = "tests(flat, tek süreç)"

    if args.dry_run:
        if flat:
            # Tek süreç: TÜM testler tek global sırada (dosya başına ayrı
            # plan birleştirilmez — birleştirme sırası flat koşumla aynı olmaz).
            tests, _sources, load_errors = load_tests_for(files, flat=True)
            if load_errors:
                # Sessiz kapsam daralması YASAK: yüklenemeyen dosya adıyla
                # raporlanır ve exit 1 (plan eksikse "temiz" demek yanlış).
                for err in load_errors:
                    print(f"HATA: {err['file']} yüklenemedi: {err['detail']}",
                          file=sys.stderr)
                return 1
            ids = [test_id(t) for t in
                   plan_order(tests, seeds[0], group_by_class=args.group_by_class)]
        else:
            plan = []
            for path in files:
                tests = load_module_tests(path)
                plan.append((path, plan_order(tests, seeds[0],
                                              group_by_class=args.group_by_class)))
            ids = [test_id(t) for _, group in plan for t in group]
        print(f"kapsam={scope_label} dosya={len(files)} test={len(ids)} "
              f"seed={seeds[0]} order_sha256={order_digest(ids)}")
        return 0

    findings, totals = audit(files, seeds, args.timeout, args.group_by_class,
                             args.watch, baseline=args.baseline, flat=flat,
                             budget=args.budget)
    report = {"tool": "shuffle_tests.py", "scope": scope_label,
              "flat": flat, "seeds": seeds,
              "group_by_class": args.group_by_class,
              "watch": args.watch, "baseline": args.baseline,
              "excluded": excluded,
              "totals": totals, "findings": findings}
    if args.json_out:
        _write_json(args.json_out, report)
        print(f"[shuffle-audit] JSON: {args.json_out}", file=sys.stderr)
    print(render_text(findings, totals, scope_label, args.group_by_class,
                      flat=flat, excluded=excluded))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
