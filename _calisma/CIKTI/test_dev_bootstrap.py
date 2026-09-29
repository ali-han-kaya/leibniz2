"""test_dev_bootstrap.py — dev_bootstrap.sh sözleşme-testleri (stdlib-only).

Kapsam: --check exit-kontratı (fail-closed), --help rc=0, arg-kontratı
(rc=2), idempotence, pin-paritesi, --full batarya-kablolaması.
Çalıştırma: venv_z3 python ile (battery listesine girer).

--full testleri SAHTE batarya enjekte eder (LEIBNIZ2_BOOTSTRAP_BATTERY):
bu test dosyası zaten bataryanın İÇİNDEdir, gerçek bataryayı koşmak
özyineleme olurdu. Sözleşme bataryanın kendisi değil, çağrı-kablolamasıdır
(yeşil → BOOTSTRAP OK, kırmızı → fail-closed, batarya-içi → red).

Ortam-guard: venv/node_modules yoksa ortama-bağlı testler SKIP eder —
CI'nın venv'siz `unittest discover` koşumunda süit kırmızıya düşmez
(2026-09-19 adversarial-tur düzeltmesi).

Not: fail-closed testi gerçek .venv_z3'ü geçici-adla gizler; finally bloğu
her durumda geri koyar. Test venv'in kendi yorumlayıcısı altında koştuğu
için rename çalışan süreci bozmaz (açık dosya-tutamaçları inode-bağlıdır).
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir, os.pardir))
SCRIPT = os.path.join(ROOT, "_calisma", "dev_bootstrap.sh")
VENV = os.path.join(ROOT, "_calisma", ".venv_z3")
VENV_PY = os.path.join(VENV, "bin", "python")

PPTX_LIB = os.path.join(ROOT, "_calisma", "pptx", "node_modules", "pptxgenjs")
DASH_TSC = os.path.join(ROOT, "apps", "dashboard-next", "node_modules", ".bin", "tsc")
# Batarya manifestindeki testlerin istediği ortam-sentinelleri: biri eksikse
# ilgili test SKIP eder, yani taze checkout'ta yeşil batarya sessizce kapsam
# kaybeder. Bu yüzden her biri bir unit'e bağlı ve --check fail-closed.
TREND_DB_TSX = os.path.join(ROOT, "apps", "trend-db", "node_modules", ".bin", "tsx")
VIDEO_TSC = os.path.join(ROOT, "_calisma", "video", "node_modules", ".bin", "tsc")
VERIFY_YML = os.path.join(ROOT, ".github", "workflows", "verify.yml")
REQ_FILE = os.path.join(ROOT, "_calisma", "requirements-z3.txt")
UNITS_CONF = os.path.join(ROOT, "_calisma", "bootstrap_units.conf")


def _run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _legacy_browser_override():
    """Python 3.9 test fixture override'ını requirements dosyasından oku."""
    matches = []
    for raw in _read(REQ_FILE).splitlines():
        line = raw.strip()
        if not line.startswith("#"):
            continue
        line = line[1:].strip()
        if (line.startswith("LEIBNIZ2_BROWSER_PIN=") and
                line.endswith(" bash _calisma/dev_bootstrap.sh")):
            matches.append(line.split("=", 1)[1].split(None, 1)[0])
    if len(matches) != 1:
        raise AssertionError("requirements-z3.txt tek eski-Python override örneği taşımalı")
    return matches[0]


def _requirements_sections():
    """Tek kaynağın iki bölümü: ([venv] satırları, [browser] pini).

    Sürümler BURADA yaşar. Bu modül de dahil hiçbir yerde `paket==sürüm`
    sabiti tutulmaz; `TestSinglePinSource` bunu kırmızıya düşürür. Sürüm
    bump'ı = requirements dosyasında tek satır, testte de dokunulmaz.
    """
    venv, browser, in_browser = [], "", False
    for raw in _read(REQ_FILE).splitlines():
        line = raw.strip()
        if line.startswith("# [browser]"):
            if in_browser:
                raise ValueError("[browser] bölümü birden fazla tanımlanmış")
            in_browser = True
            continue
        if not line or line.startswith("#"):
            continue
        if in_browser:
            if browser:
                raise ValueError("[browser] bölümünde birden fazla pin var")
            browser = line
        else:
            venv.append(line)
    return venv, browser


PINS, BROWSER_PIN = _requirements_sections()
# Tek istisna: bu değer bir test FİXTÜRÜ (3.9 için geçersiz kılma yolu),
# repo'nun kullandığı sürüm değil. İzin listesi açıkça yazılı ki "neden
# burada?" sorusu yanıtsız kalmasın.
LEGACY_BROWSER_PIN = _legacy_browser_override()
ALLOWED_TEST_FIXTURES = {
    LEGACY_BROWSER_PIN: "3.9 override yolunun sınanması için sentetik değer",
}
# Fixture değeri de requirements-z3.txt içindeki açık uyumluluk örneğinden gelir.
OLD_PY_PIN = LEGACY_BROWSER_PIN
PIN_LITERAL = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*==[0-9][0-9A-Za-z.]*")


# ── Unit envanteri: TEK KAYNAK ──────────────────────────────────────────────
# Liste, sıra ve görünen yollar `dev_bootstrap.sh`'in okuduğu AYNI dosyada
# yaşar. Bu modülde hiçbir unit ADI sabit yazılmaz. Ölçülen sebep: liste
# `UNITS=(...)` dizisi, `unit_path()` case tablosu ve ÜÇ test sınıfında elle
# yazılmıştı; yeni bir unit eklemek dört yerden birini unutmak demekti ve
# unutulan yer sessizce kapsam kaybediyordu (o unit `--check`'te hiç ölçülmüyor,
# testleri yeşil görünüyordu).
def _unit_rows():
    """Envanteri satır satır oku: [(ad, görünen-yol, check-türü, prov-türü)].

    `dev_bootstrap.sh` ile AYNI ayrıştırma kuralı (boşlukla ayrılmış alanlar,
    `#` ile başlayan satırlar yorum) — iki taraf ayrışırsa sessiz sapma olur,
    bu yüzden burada da fail-closed: alan sayısı ne eksik ne fazla kabul edilir.

    Alan sayısı denetimi daha önce ölçülen bir tuzağı kapatır: alanlardan
    birinde boşluk ("venv_z3 + chromium") satırı sessizce bozuyordu.
    """
    rows = []
    for lineno, raw in enumerate(_read(UNITS_CONF).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 4:
            raise AssertionError(
                "bootstrap_units.conf:%d dört alan bekleniyordu, %d bulundu: %r"
                % (lineno, len(fields), raw))
        rows.append(tuple(fields))
    if not rows:
        raise AssertionError("bootstrap_units.conf boş — envanter kayboldu")
    names = [r[0] for r in rows]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise AssertionError("bootstrap_units.conf'te yinelenen unit: %s" % dupes)
    return rows


UNIT_ROWS = _unit_rows()                  # sıra = bağımlılık sırası = envanter sırası
UNIT_NAMES = [r[0] for r in UNIT_ROWS]
UNIT_LABELS = {r[0]: r[1] for r in UNIT_ROWS}
# Yapı denetimi: `check_unit`/`provision_unit` yalnız bu türleri bilir ve
# başka her şeyi `die` ile reddeder. Bilinmeyen bir tür sızarsa — yeni unit
# ekleyen kişi envanteri günceller, script'i güncellemezse — kapı fail-closed
# ölmeli, yoksa o unit sessizce hiç ölçülmezdi.
KNOWN_CHECK_KINDS = {"venv", "browser", "resolve", "exec", "artifact"}
KNOWN_PROV_KINDS = {"venv", "npm", "browser", "prisma", "nextbuild"}


def _check_kind(check):
    return check.split(":", 1)[0]


def _prov_kind(prov):
    return prov.split(":", 1)[0]


# Etiket iki çeşit: yol (`/` içerir — `ls` ile bakılacak yer) veya tariftir
# (`browsers` → `venv_z3+chromium`; yol değil, iki bileşeni anlatıyor).
# Ayırıcı: `/`. Tarifi olan tek unit `browser` türündedir; bu, alanların
# boşlukla ayrıldığı bir dosyada "venv_z3 + chromium" yazmanın sessizce
# alan sayısını bozduğu ölçülen tuzağın canlı karşılığıdır.
PATH_UNITS = [r for r in UNIT_ROWS if "/" in r[1]]
DESCRIPTIVE_UNITS = [r for r in UNIT_ROWS if "/" not in r[1]]


def _sentinels(row):
    """(ad, check-türü) → gizlenince o unit'i kıran sentinel dosya yolları.

    Kırık-unit sözleşmesi envanterden TÜRETİLİR: yeni bir `exec:` ya da
    `artifact:` unit'i eklenince fail-closed ölçümü kendiliğinden gelir —
    elle tutulan bir sentinel tablosu olsaydı yeni unit ölçümsüz kalırdı.

    Biçim ÖNEMLİ: `resolve:` paket DİZİNİ çözer, `exec:`/`artifact:` dosya
    YOLU arar. Dosyayı gizlemek paket dizini durduğu için ölçüm yapmaz
    (ölçüldü: "CHECK OK", rc=0).
    """
    name, label, check, _prov = row
    if check == "venv":
        return [(name, "%s/bin/python" % label)]
    if check.startswith("resolve:"):
        return [(name, "%s/node_modules/%s" % (label, check.split(":", 1)[1]))]
    if check.startswith("exec:"):
        return [(name, p) for p in check.split(":", 1)[1].split(",") if p]
    if check.startswith("artifact:"):
        return [(name, check.split(":", 1)[1])]
    return []            # `browser` dosya değil süreç probelidir (ayrı ölçülür)


SENTINELS = [s for row in UNIT_ROWS for s in _sentinels(row)]


@unittest.skipUnless(os.path.isfile(VENV_PY),
                     "yerel araç-kümesi (venv_z3) kurulu değil")
class TestCheckContract(unittest.TestCase):
    """Gerçek host araç-kümesini prob'lar; CI verify job'ında venv yoktur.

    Bu guard yalın CI keşfinde yalnız bu host-bağımlı sınıfı atlar. Sahte kök
    kullanan sözleşme testleri (aşağıdaki sınıflar) her ortamda çalışmaya devam
    eder; guard tüm modüle uygulanmaz.
    """
    def test_check_passes_on_provisioned_checkout(self):
        if not os.path.isdir(VENV):
            self.skipTest("araç-kümesi eksik — provisioned-ortam testi tam-kurulumda koşar")
        r = _run(["bash", SCRIPT, "--check"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # Kırık-unit sözleşmesi artık MUTASYONSUZ: `TestBrokenUnitFailsCheckClosed
    # Hermetic` (aşağıda) aynı beş sentinel'i sahte kökte gizleyip ölçüyor.
    # Buradaki eski sürüm GERÇEK `.venv_z3`/`pptxgenjs`/`tsc`/`tsx`
    # dosyalarını `os.rename` ile ağaçtan çıkarıyordu; o pencere boyunca aynı
    # checkout'taki BAŞKA bir `--check` çağrısı kırmızı görüyordu (ölçüldü:
    # "CHECK FAIL: venv_z3 eksik veya paritesiz rc=1"). Zincirde
    # `check-unit-tests` ile `check-bootstrap-toolchain` aynı commit'te
    # `--check` çağırdığı için batarya 10/10 tek başına yeşilken pre-commit
    # altında aralıklı kırmızıydı ve hook test çıktısını attığı için sebep
    # görünmüyordu. Ağaç artık ölçüm aracı DEĞİLDİR.

    def test_check_fail_closed_without_browser_layer(self):
        """Tarayıcı katmanı ÖLÇÜMÜ işlevsel: boş `PLAYWRIGHT_BROWSERS_PATH`
        chromium'u bulunamaz kılar → rc=1. Ölçüm gerçek venv'e dokunmaz
        (paketi gizlemek yerine arama yolunu değiştirir), bu yüzden koşum
        sırasında paralel bir tarayıcı testini bozmaz."""
        if _run(["bash", SCRIPT, "--check"]).returncode != 0:
            self.skipTest("araç-kümesi eksik — tam-kurulumda koşar")
        empty = tempfile.mkdtemp(prefix="no-browsers-")
        self.addCleanup(shutil.rmtree, empty, True)
        env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=empty)
        r = _run(["bash", SCRIPT, "--check"], env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CHECK FAIL: browsers", r.stdout)


class TestArgContract(unittest.TestCase):
    """Arg-kontratı: bilinmeyen/ekstra bayrak rc=2; "" no-args'la-özdeş."""

    def test_bad_usage_exits_two(self):
        for argv in (["--version"], ["--check", "extra"]):
            r = _run(["bash", SCRIPT, *argv])
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("--check", r.stderr)

    def test_help_rejects_extra_arg(self):
        """REGRESYON (2026-09-29): `--help extra` rc=0 dönüyordu.

        `--check extra` ve `--full extra` rc=2 veriyor, `--help extra` ise
        `--help`'ı basıp çıkıyordu. Üçü de tek bayrak bekleyen aynı komut;
        sessizce yutulan fazladan argüman, kullanıcının yazım hatasını
        "komut çalıştı" sanmasına yol açar. Kural: `--help` de dahil
        TÜM bayraklar tek argümanla sınırlı, fazlası rc=2.
        """
        r = _run(["bash", SCRIPT, "--help", "extra"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        # Kullanım stdout'a DEĞIL stderr'e basılır (rc=2 yolu) — kullanıcı
        # yardım metnini görür, yanlış bayrağın sessizce yutulmadığını bilir.
        self.assertIn("--check", r.stderr)

    def test_help_exits_zero_when_alone(self):
        """Dengesi: `--help` TEK başına yardım basıp rc=0 vermeye devam eder."""
        r = _run(["bash", SCRIPT, "--help"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for flag in ("--full", "--check", "--help"):
            self.assertIn(flag, r.stdout)

    def test_empty_string_arg_is_install_not_error(self):
        """${1:-} sözleşmesi: "" bayrağısız-koşumla-özdeş (kurulum-yolu)."""
        check = _run(["bash", SCRIPT, "--check"])
        if check.returncode != 0:
            self.skipTest("araç-kümesi eksik")
        r = _run(["bash", SCRIPT, ""])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("BOOTSTRAP OK", r.stdout)


class TestHelpAndIdempotence(unittest.TestCase):
    def test_help_exits_zero(self):
        r = _run(["bash", SCRIPT, "--help"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("--check", r.stdout)

    def test_bootstrap_twice_is_noop_second_run(self):
        check = _run(["bash", SCRIPT, "--check"])
        if check.returncode != 0:
            self.skipTest("araç-kümesi eksik — idempotence tam-kurulumda koşar")
        r = _run(["bash", SCRIPT])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("up to date", r.stdout)
        self.assertTrue(r.stdout.rstrip().endswith("BOOTSTRAP OK"))


def _provisioned_or_skip(testcase):
    """--full kurulum döngüsü KOŞAR: tam-kurulum yoksa npm/venv indirmeye
    kalkışırdı (ağ + dakikalar). Mevcut sözleşmeyle aynı kapı: --check rc!=0
    → SKIP (CI'nın çıplak unittest discover'ı kırmızıya düşmesin)."""
    if _run(["bash", SCRIPT, "--check"]).returncode != 0:
        testcase.skipTest("araç-kümesi eksik — --full kablolaması tam-kurulumda koşar")


@unittest.skipUnless(os.path.isfile(VENV_PY),
                     "yerel araç-kümesi (venv_z3) kurulu değil")
class TestFullFlag(unittest.TestCase):
    """`--full` = kurulum + temel batarya (uçtan uca yeşil koşum)."""

    def setUp(self):
        _provisioned_or_skip(self)

    def _battery(self, body):
        """Sahte batarya betiği (gerçeği dakikalar sürer ve bu testi içerir)."""
        d = tempfile.mkdtemp(prefix="boot-battery-")
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "fake_battery.sh")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/bash\n" + body + "\n")
        return p

    def _run_full(self, battery, in_battery=None):
        env = dict(os.environ)
        env["LEIBNIZ2_BOOTSTRAP_BATTERY"] = battery
        env.pop("LEIBNIZ2_IN_BATTERY", None)  # dış ortam sızmasın
        if in_battery is not None:
            env["LEIBNIZ2_IN_BATTERY"] = in_battery
        return _run(["bash", SCRIPT, "--full"], env=env)

    def test_green_battery_reports_ok_last(self):
        r = self._run_full(self._battery('echo "sahte batarya: 180 dosya PASS."'))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("temel batarya:", r.stdout)
        self.assertIn("sahte batarya", r.stdout, "batarya çıktısı akışa karışmalı")
        self.assertTrue(r.stdout.rstrip().endswith("BOOTSTRAP OK"), r.stdout)

    def test_red_battery_blocks_bootstrap_ok(self):
        r = self._run_full(self._battery('echo "FAILED: test_x" >&2; exit 7'))
        self.assertNotEqual(r.returncode, 0, "kırmızı batarya rc=0 dönemez")
        self.assertIn("BOOTSTRAP FAIL", r.stderr)
        self.assertIn("FAILED: test_x", r.stderr, "bataryanın kendi hatası görünmeli")
        self.assertNotIn("BOOTSTRAP OK", r.stdout, "kırmızı bataryada OK basılmamalı")

    def test_recursion_is_refused_inside_battery(self):
        """Batarya içinden --full: özyineleme, hiç başlamadan reddedilir."""
        r = self._run_full(self._battery("exit 0"), in_battery="1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("özyineleme", r.stderr)
        self.assertNotIn("temel batarya:", r.stdout, "batarya hiç başlamamalı")


class TestFullArgContract(unittest.TestCase):
    """Arg-kontratı: fazladan argüman kuruluma girmeden rc=2."""

    def test_full_rejects_extra_arg(self):
        r = _run(["bash", SCRIPT, "--full", "extra"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--check", r.stderr)

    def test_help_lists_full(self):
        r = _run(["bash", SCRIPT, "--help"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("--full", r.stdout)


class TestVerifyFlag(unittest.TestCase):
    """`--verify` = araç-kümesi ölçümü, SONRA batarya — kurulum YAPMAZ.

    `--full` ile farkı sözleşmenin KENDİSİ: `--full` eksik bulduğu birimi
    kurar, yani "bu ağaç hazır mı" sorusunu kurulum yaparak değiştirip
    yanıtlar. `--verify` fail-closed ölür — ölçtüğü ağaca dokunmaz.

    Ölçüm SAHTE KÖKTE: gerçek ağaç değiştirilmeden hem yeşil hem kırık dal
    ölçülebilir, dolayısıyla zincir yarışı imkânsız olur (bkz.
    `TestBrokenUnitFailsCheckClosedHermetic`).
    """

    def setUp(self):
        self.root = _fake_bootstrap_root()
        self.addCleanup(shutil.rmtree, str(self.root), True)
        self.env = _fake_env(self.root)
        self.battery = str(self.root / "fake_battery.sh")
        self.env["LEIBNIZ2_BOOTSTRAP_BATTERY"] = self.battery

    def _battery(self, body):
        """Sahte batarya betiği — gerçeği dakikalar sürer ve BU testi içerir."""
        with open(self.battery, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/bash\n" + body + "\n")

    def _run_boot(self, *argv):
        script = str(self.root / "_calisma" / "dev_bootstrap.sh")
        return _run(["bash", script, *argv], env=self.env)

    def _hide_first_npm_sentinel(self):
        """Envanterden TÜRETİLMİŞ bir `resolve:` sentinel'ini gizle.

        Birim ADINA bağlanmaz: elle seçilmiş bir birim, envanter değişince
        ölçüm sessizce yanlış hedefe kayabilirdi.
        """
        name, rel = next(s for s in SENTINELS if "/node_modules/" in s[1])
        p = self.root / rel
        hidden = p.with_name(p.name + ".hidden_by_test")
        os.rename(p, hidden)
        self.addCleanup(os.rename, str(hidden), str(p))
        return name

    def test_green_tree_runs_battery_after_the_toolchain_check(self):
        """SIRA sözleşmesi: batarya, araç-kümesi ölçülmeden başlamaz."""
        self._battery('echo "sahte batarya: 191 dosya PASS."')
        r = self._run_boot("--verify")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("CHECK OK", r.stdout)
        self.assertIn("temel batarya:", r.stdout)
        self.assertIn("sahte batarya", r.stdout, "batarya çıktısı akışa karışmalı")
        self.assertLess(r.stdout.index("CHECK OK"), r.stdout.index("temel batarya:"),
                        "batarya araç-kümesi ölçülmeden başladı")
        self.assertTrue(r.stdout.rstrip().endswith("BOOTSTRAP OK"), r.stdout)

    def test_broken_unit_dies_before_the_battery(self):
        name = self._hide_first_npm_sentinel()
        self._battery('echo "SAHTE BATARYA CAAGRILDI"')
        r = self._run_boot("--verify")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CHECK FAIL: %s (" % name, r.stdout)
        self.assertNotIn("temel batarya:", r.stdout,
                         "kırık araç-kümesinde batarya KOŞMAMALI")
        self.assertEqual(_read(self.env["FAKE_LOG"]), "",
                         "--verify kurulum YAPMAMALI: sahte npm/pip çağrısı görüldü")

    def test_the_same_broken_tree_would_be_provisioned_by_full(self):
        """Yukarıdaki 'kurulum yok' iddiasının BOŞ OLMAYAN kanıtı.

        Aynı kırık ağaçta `--full` sahte npm'yi GERÇEKTEN çağırıyor. Yani
        log'un boş kalması ölçüm hatası değil, `--verify`'nin kurmama
        kararı — bu eşleşme olmadan `test_broken_unit...` kendi kurgusu
        yüzünden yeşil kalabilirdi.
        """
        self._hide_first_npm_sentinel()
        self._battery('echo "sahte batarya: 191 dosya PASS."')
        r = self._run_boot("--full")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("npm", _read(self.env["FAKE_LOG"]))

    def test_verify_rejects_extra_arg(self):
        r = self._run_boot("--verify", "extra")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--verify", r.stderr)

    def test_recursion_is_refused_inside_battery(self):
        """Batarya içinden `--verify`: özyineleme, hiç başlamadan reddedilir."""
        self._battery("exit 0")
        self.env["LEIBNIZ2_IN_BATTERY"] = "1"
        r = self._run_boot("--verify")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("özyineleme", r.stderr)
        self.assertNotIn("temel batarya:", r.stdout, "batarya hiç başlamamalı")

    def test_help_lists_verify_next_to_full(self):
        r = _run(["bash", SCRIPT, "--help"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("--verify", r.stdout)
        self.assertIn("[--full|--verify|--check|--help]", r.stdout)


class TestPinParity(unittest.TestCase):
    @unittest.skipUnless(os.path.isfile(VENV_PY), "venv_z3 kurulu değil")
    def test_venv_pins_match_matrix(self):
        r = _run([VENV_PY, "-m", "pip", "freeze"])
        frozen = set(r.stdout.splitlines())
        for pin in PINS:
            self.assertIn(pin, frozen, "pin eksik: " + pin)

    def test_pins_cover_the_battery_imports(self):
        """Pin listesi bataryanın GERÇEKTEN istediği paketleri kapsamalı:
        manifestte jsonschema/PIL isteyen testler var; pin eksikse taze
        checkout'ta o testler SKIP eder (sessiz kapsam kaybı).

        Eşleme pakET ADIYLA kurulur, sürümle değil: aksi halde sürüm bump'ı
        (tek dosyalık olması gereken işlem) testi de kırar."""
        battery = os.path.join(ROOT, "_calisma", "CIKTI", "check_unit_tests.list")
        listed = set(_read(battery).split())
        names = {p.split("==")[0].lower().replace("_", "-") for p in PINS}
        consumers = {
            "jsonschema": "test_validate_config_schema.py",
            "pillow": "test_verification_chain_deck.py",
        }
        required = {"z3-solver", "pyyaml", "pre-commit", "jsonschema", "pillow"}
        self.assertTrue(required <= names,
                        "requirements'ta bataryanın temel pin'leri eksik: %s"
                        % sorted(required - names))
        for pkg, test in consumers.items():
            self.assertIn(test, listed,
                          "%s bataryada değil — pin gerekçesi boşa düşmüş" % test)
            self.assertIn(pkg, names, "requirements'ta %s pini yok" % pkg)

    def test_requirements_file_is_the_only_pin_source(self):
        """Sürüm sabiti bu dosyada yaşar; script onu okur, kendi listesi yok."""
        script = _read(SCRIPT)
        self.assertIn("requirements-z3.txt", script)
        self.assertIn("_load_pins", script)
        self.assertNotRegex(script, r"BROWSER_PIN=\"[^\"]+==",
                            "BROWSER_PIN sabitlenmiş, dosyadan okunmalı")


# ── tarayıcı katmanı: sahte kök ile hermetik kurulum testi ───────────────

def _script_pins():
    """Sahte venv'in `pip freeze` çıktısı = tek kaynağın [venv] bölümü."""
    return _requirements_sections()[0]


FAKE_VENV_PY = '''#!/usr/bin/env python3
"""Sahte venv python'u — scriptin çağırdığı dört yolu taklit eder."""
import os, sys
log = os.environ.get("FAKE_LOG")
args = sys.argv[1:]
if args[:2] == ["-m", "pip"] and args[2:3] == ["freeze"]:
    print(os.environ.get("FAKE_FREEZE", ""))
    sys.exit(0)
if args[:2] == ["-m", "pip"] and args[2:3] == ["install"]:
    open(log, "a").write("pip " + " ".join(args) + "\\n")
    sys.exit(0)
if args[:2] == ["-m", "playwright"]:
    open(log, "a").write("playwright " + " ".join(args) + "\\n")
    sys.exit(0)
if args[:1] == ["-"]:                     # stdin programı: check_browsers
    sys.stdin.read()
    sys.exit(0 if os.environ.get("FAKE_BROWSER_OK") == "1" else 1)
if args[:1] == ["-c"] and "version_info" in args[1]:
    # python_floor_ok sürüm probunu `-c` ile sorar; sahte yorumlayıcı
    # ölçülemez dönerse script fail-closed olarak ÖLÜMÜ seçer.
    print(os.environ.get("FAKE_PY_VERSION", "3.11.0"))
    sys.exit(0)
if args[:1] == ["-c"]:
    floor, have = args[2], args[3]        # taban karşılaştırması
    f = tuple(int(x) for x in floor.split("."))
    h = tuple(int(x) for x in have.split("."))
    sys.exit(0 if h >= f else 1)
if args[:1] == ["--version"]:
    print("Python %s" % os.environ.get("FAKE_PY_VERSION", "3.11.0"))
    sys.exit(0)
sys.exit(1)                              # beklenmeyen çağrı = gürültülü fail
'''

# Sahte node: `check_pptx`/`check_docx` unit'leri `node -e
# "require.resolve('<pkg>')"` çağırır. Ölçülen boşluk (2026-09-29): shim
# koşulsuz `exit 0` idi, dolayısıyla `check_pptx` SAHTE KÖKTE HİÇBİR ZAMAN
# kırmızı olamıyordu — paket dizini gizlendiğinde bile "CHECK OK" dönüyordu
# (rc=0). Yani kırık-unit sözleşmesi bu iki unit'i hiç ölçemiyordu.
# Shim artık GERÇEKTEN çözümler: paket dizini yoksa exit 1 (node'un
# `require.resolve` hata kodu), varsa exit 0.
FAKE_NODE = '''#!/bin/bash
if [ "$1" = "-e" ] && [ "$2" = "require.resolve('pptxgenjs')" ]; then
  [ -d "$PWD/node_modules/pptxgenjs" ] && exit 0
  echo "Cannot find module 'pptxgenjs'" >&2
  exit 1
fi
if [ "$1" = "-e" ] && [ "$2" = "require.resolve('docx')" ]; then
  [ -d "$PWD/node_modules/docx" ] && exit 0
  echo "Cannot find module 'docx'" >&2
  exit 1
fi
exit 0
'''
FAKE_NPM = '''#!/bin/bash
printf "npm %s\\n" "$*" >> "$FAKE_LOG"
# Güvenlik: sahte npm YALNIZ kendi sahte köküne yazabilir. Test koşumları
# yanlışlıkla gerçek ağaca artefakt bırakmamalı (ölçüldü: bir mutasyon
# koşusu `_calisma/CIKTI/apps/dashboard-next/.next/BUILD_ID` bırakmıştı —
# izlenmeyen, gitignore'lu olmayan çöp).
[ -n "$FAKE_ROOT" ] || { echo "FAKE_ROOT yok — yazma reddedildi" >&2; exit 9; }
# `npm run build --prefix apps/dashboard-next` → BUILD_ID üret (yoksa ikinci
# koşuda dashboard_next_build hâlâ "eksik" görünür ve idempotence ölçülemez).
if [ "$1" = "run" ] && [ "$2" = "build" ]; then
  # `npm run build --prefix apps/dashboard-next` → BUILD_ID prefix'in altına.
  # --prefix CWD'den bağımsız olduğu için argümandan okunur.
  shift 2
  prefix=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --prefix) prefix="$2"; shift 2 ;;
      *) shift ;;
    esac
  done
  [ -n "$prefix" ] || prefix="."
  case "$prefix" in
    "$FAKE_ROOT"/*) ;;
    *) echo "build gerçek ağacın dışına çıktı: $prefix" >&2; exit 9 ;;
  esac
  mkdir -p "$prefix/.next"
  printf 'fakebuildid00000000000000\\n' > "$prefix/.next/BUILD_ID"
fi
exit 0
'''
# npx prisma generate → sahte artefaktı yazar; npm run build → BUILD_ID yazar.
# Böylece ikinci koşuda unit'ler "up to date" der (idempotence gerçekten ölçülür).
FAKE_NPX = '''#!/bin/bash
printf "npx %s\\n" "$*" >> "$FAKE_LOG"
if [ "$1" = "prisma" ] && [ "$2" = "generate" ]; then
  # provision, CI'ın komutu gibi `cd apps/trend-db` YAPILARAK çağırır →
  # çıktı schema'nın `output = "../generated"` hedefidir, yani CWD'ye göre.
  case "$PWD" in
    "$FAKE_ROOT"/*) ;;
    *) echo "prisma generate gerçek ağacın dışına çıktı: $PWD" >&2; exit 9 ;;
  esac
  mkdir -p generated
  printf '// fake prisma client\\nexport class PrismaClient {}\\n' > generated/client.ts
fi
exit 0
'''


def _fake_bootstrap_root():
    """Script'i sahte bir köke kopyalar; her unit'in sentineli hazır.

    Gerçek ağaçtaki kurulum yolunu (pip/playwright install) AĞA ÇIKMADAN ve
    gerçek venv'e dokunmadan sınamanın tek yolu: ROOT scriptin kendi
    konumundan türetilir, dolayısıyla kopya kendi kökünü kurar.
    """
    td = tempfile.mkdtemp(prefix="boot-fakeroot-")
    root = pathlib.Path(td)
    (root / "_calisma").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "_calisma" / "dev_bootstrap.sh")
    # Pinlerin TEK KAYNAK dosyası da kopyalanır: sahte kök kendi kökünden
    # okuyor (ROOT scriptin konumundan türetilir), yoksa script "requirements
    # dosyası yok" deyip ölür ve sözleşme ölçülmez.
    shutil.copy(REQ_FILE, root / "_calisma" / "requirements-z3.txt")
    # Envanter de kopyalanır: script kendi kökünden okuyor. Eksik kalsaydı
    # "unit envanteri yok" diye ölürdü — sözleşme ölçülmeden bütün sahte
    # kök testleri kırmızı olurdu. (Bu ikinci kez unutuluyordu: refs eklendi
    # ama sahte kök yalnız SCRIPT + REQ_FILE kopyalıyordu.)
    shutil.copy(UNITS_CONF, root / "_calisma" / "bootstrap_units.conf")
    # node/npm sahte PATH'ten gelir: ortamda node olmasa da test koşar.
    bindir = root / "bin"
    bindir.mkdir()
    for name, body in (("node", FAKE_NODE), ("npm", FAKE_NPM)):
        p = bindir / name
        p.write_text(body, encoding="utf-8")
        p.chmod(0o755)
    vbin = root / "_calisma" / ".venv_z3" / "bin"
    vbin.mkdir(parents=True)
    vpy = vbin / "python"
    vpy.write_text(FAKE_VENV_PY, encoding="utf-8")
    vpy.chmod(0o755)
    for rel in ("_calisma/pptx/node_modules/pptxgenjs/package.json",
                "_calisma/docx/node_modules/docx/package.json"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"name":"fake"}\n', encoding="utf-8")
    for rel in ("apps/dashboard-next/node_modules/.bin/tsc",
                "apps/dashboard-next/node_modules/.bin/next",
                "apps/trend-db/node_modules/.bin/tsx",
                "_calisma/video/node_modules/.bin/tsc"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        p.chmod(0o755)
    # `npx` sahte: prisma generate + npm run build ağa/kuruluma çıkmadan
    # ölçülsün, üretilen artefaktlar da sahte kökte DOĞSUN (yoksa ikinci
    # koşu "up to date" der ve test hiçbir şey ölçmezdi).
    npx = root / "bin" / "npx"
    npx.write_text(FAKE_NPX, encoding="utf-8")
    npx.chmod(0o755)
    _write_generated_artifacts(root)
    return root


def _fake_env(root, **extra):
    """Sahte kökün ortamı: sahte PATH/log + gerçek pinler.

    `browser` probu `FAKE_BROWSER_OK`'a bakar, `venv` probu `pip freeze`
    çıktısını PINS ile karşılaştırır; ikisi de sahte kökte ÖLÇÜLEBİLİR
    kalmalı yoksa kırık-unit sözleşmesi ölçülemez yeşil olur.
    """
    env = dict(os.environ)
    env["FAKE_LOG"] = str(root / "calls.log")
    env["FAKE_FREEZE"] = "\n".join(_script_pins())
    env["FAKE_BROWSER_OK"] = "1"
    env["FAKE_ROOT"] = str(root)          # sahte npm/npx sınırı
    env["PATH"] = str(root / "bin") + os.pathsep + env["PATH"]
    env.pop("LEIBNIZ2_IN_BATTERY", None)
    pathlib.Path(env["FAKE_LOG"]).write_text("", encoding="utf-8")
    env.update(extra)
    return env


def _row_fields(text, name):
    """Envanter metninden `name` satırının alanlarını döndürür."""
    for raw in text.splitlines():
        s = raw.strip()
        if s and not s.startswith("#") and s.split()[0] == name:
            return s.split()
    raise AssertionError("envanterde satır yok: " + name)


def _set_row(text, name, fields):
    """`name` satırını verilen alanlarla değiştirir; sıra KORUNUR.

    Alan BİÇİMİ elle yazılmaz — envanterden okunur, yalnız değiştirilecek
    alan elle verilir. Yoksa test kendi kopyasını koruyor ve envanterden
    saparsa test yanlış yere yeşil kalır.
    """
    out, hit = [], False
    for raw in text.splitlines():
        s = raw.strip()
        if s and not s.startswith("#") and s.split()[0] == name:
            out.append(" ".join(fields))
            hit = True
        else:
            out.append(raw)
    if not hit:
        raise AssertionError("envanterde satır yok: " + name)
    return "\n".join(out) + "\n"


def _drop_row(text, name):
    """`name` satırını siler; yorumlar ve diğer satırlar yerinde kalır."""
    out, hit = [], False
    for raw in text.splitlines():
        s = raw.strip()
        if s and not s.startswith("#") and s.split()[0] == name:
            hit = True
            continue
        out.append(raw)
    if not hit:
        raise AssertionError("envanterde satır yok: " + name)
    return "\n".join(out) + "\n"


def _rewrite_conf(root, transform):
    """Sahte kökteki envanteri dönüştürür; GERÇEK dosyaya dokunmaz.

    Envanter de test edilen bileşenlerden biri: satır eklemek, sıra
    değiştirmek, türü bozmak script'i değiştirmeden davranışı değiştirmeli.
    """
    p = pathlib.Path(root) / "_calisma" / "bootstrap_units.conf"
    p.write_text(transform(p.read_text(encoding="utf-8")), encoding="utf-8")
    return p


def _write_generated_artifacts(root):
    """Sahte prisma istemcisi + BUILD_ID (bootstrap'un ürettiği artefaktlar)."""
    client = root / "apps/trend-db/generated/client.ts"
    client.parent.mkdir(parents=True, exist_ok=True)
    client.write_text("// fake prisma client\nexport class PrismaClient {}\n",
                      encoding="utf-8")
    build_id = root / "apps/dashboard-next/.next/BUILD_ID"
    build_id.parent.mkdir(parents=True, exist_ok=True)
    build_id.write_text("fakebuildid00000000000000\n", encoding="utf-8")


class TestBrowserLayerProvisioning(unittest.TestCase):
    """`browsers` unit'i iki adımlı (pip pin + chromium indirme) ve ağa
    çıkar; bu yüzden ölçümü sahte kökte yapılır."""

    def setUp(self):
        self.root = _fake_bootstrap_root()
        self.addCleanup(shutil.rmtree, str(self.root), True)
        self.log = str(self.root / "calls.log")
        self.env = dict(os.environ)
        self.env["FAKE_LOG"] = self.log
        self.env["FAKE_FREEZE"] = "\n".join(_script_pins())
        self.env["PATH"] = str(self.root / "bin") + os.pathsep + self.env["PATH"]
        self.env.pop("LEIBNIZ2_IN_BATTERY", None)
        battery = self.root / "fake_battery.sh"
        battery.write_text('#!/bin/bash\necho "sahte batarya: 3 dosya PASS."\n',
                           encoding="utf-8")
        self.env["LEIBNIZ2_BOOTSTRAP_BATTERY"] = str(battery)
        pathlib.Path(self.log).write_text("", encoding="utf-8")

    def _run_boot(self, *argv):
        script = str(self.root / "_calisma" / "dev_bootstrap.sh")
        return _run(["bash", script, *argv], env=self.env)

    def test_full_provisions_pin_and_chromium(self):
        self.env["FAKE_BROWSER_OK"] = "0"
        r = self._run_boot("--full")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = _read(self.log)
        self.assertIn("pip install --quiet " + BROWSER_PIN, calls)
        self.assertIn("playwright install chromium", calls)
        self.assertIn("browsers (venv_z3+chromium):", r.stdout)
        self.assertTrue(r.stdout.rstrip().endswith("BOOTSTRAP OK"), r.stdout)

    def test_working_browser_is_not_reinstalled(self):
        """Çalışan chromium varsa indirme TETİKLENMEZ (idempotence)."""
        self.env["FAKE_BROWSER_OK"] = "1"
        r = self._run_boot()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("browsers (%s): up to date" % UNIT_LABELS["browsers"],
                      r.stdout)
        self.assertEqual(_read(self.log), "")

    def test_missing_browser_layer_fails_check_closed(self):
        self.env["FAKE_BROWSER_OK"] = "0"
        r = self._run_boot("--check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CHECK FAIL: browsers", r.stdout)

    def test_browser_pin_matches_ci(self):
        """İkinci kaynak YOK: CI `-r` ile aynı pin dosyasından kuruyor."""
        yml = _read(VERIFY_YML)
        self.assertNotRegex(yml, r"playwright==[0-9]",
                            "verify.yml'de sabitlenmiş tarayıcı sürümü kaldı")
        self.assertIn("pip install -r _calisma/requirements-z3.txt", yml)
        self.assertTrue(BROWSER_PIN.startswith("playwright=="), BROWSER_PIN)


class TestBrokenUnitFailsCheckClosedHermetic(unittest.TestCase):
    """`--check` birim kırıkken fail-closed — SAHTE KÖKTE, ağaca dokunmadan.

    Ölçülen yarış (2026-09-29): `TestCheckContract.test_check_fail_closed_on_
    broken_unit` aynı sözleşmeyi GERÇEK ağacı mutilate ederek ölçüyordu —
    `os.rename(VENV, VENV + ".hidden_by_test")` ile repo'nun kurulu
    `.venv_z3`'ünü (ve `pptxgenjs`, dashboard `tsc`, trend-db `tsx`, video
    `tsc` sentinel'lerini) ağaçtan çıkarıyor, `--check` kırmızıyı ölçüyor,
    geri koyuyordu. O pencere boyunca aynı checkout'ta çalışan BAŞKA bir
    `--check` kırmızı görüyor:

        CHECK FAIL: venv_z3 eksik veya paritesiz   rc=1     (gizliyken)
        CHECK OK                                     rc=0     (geri konunca)

    Zincir bunu kaçınılmaz kılıyor: `check-unit-tests` (config:1045) ve
    `check-bootstrap-toolchain` (config:1087) AYNI commit'te `--check`
    çağırıyor; ölçüldü — batarya `test_dev_bootstrap`'ı 10/10 tek başına
    geçiyor, pre-commit altında aralıklı KIRMIZI. Hook ayrıca test
    çıktısını `>/dev/null 2>&1` ile attığı için kırmızı sebepsiz görünüyor.

    Sözleşme SAĞLAMDIR, sadece ölçüm yeri değişti: sentinel'ler sahte kökte
    kurulur, orada gizlenir, orada geri konur. Gerçek ağaç hiç değişmez →
    yarış imkânsız.
    """

    # Sentinel tablosu ENVANTERDEN türetilir (`_sentinels`), elle yazılmaz:
    # (unit adı, fake kök içindeki göreli sentinel yolu). Kapsam ölçüldü —
    # elle tablo dokuz birimin beşini kapsıyordu, `docx` ve iki üretim
    # biriminin kırık-unit ölçümü YOKTU; yani eklenen birim sessizce
    # ölçümsüz kalıyordu.
    UNITS = SENTINELS

    def setUp(self):
        self.root = _fake_bootstrap_root()
        self.addCleanup(shutil.rmtree, str(self.root), True)
        self.env = _fake_env(self.root)

    def _run_boot(self, *argv):
        script = str(self.root / "_calisma" / "dev_bootstrap.sh")
        return _run(["bash", script, *argv], env=self.env)

    def test_every_unit_is_present_in_the_fake_root(self):
        """Sözleşmenin ölçülebilir olması için: her sentinel GERÇEKTEN var.
        Yoksa `test_..._fails_check_closed` 'gizledim' sandığı için yeşil
        kalır ve hiçbir şey ölçmez (fail-closed'un kendisi gibi: ölçülemeyen
        yeşil sayılmaz)."""
        for label, rel in self.UNITS:
            with self.subTest(unit=label):
                self.assertTrue((self.root / rel).exists(),
                                "sahte kökte sentinel yok: " + rel)

    def test_each_broken_unit_fails_check_closed(self):
        for label, rel in self.UNITS:
            with self.subTest(unit=label):
                target = self.root / rel
                hidden = self.root / (rel + ".hidden_by_test")
                target.rename(hidden)
                try:
                    r = self._run_boot("--check")
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertIn("CHECK FAIL", r.stdout)
                finally:
                    if hidden.exists():
                        hidden.rename(target)
                r2 = self._run_boot("--check")
                self.assertEqual(r2.returncode, 0,
                                 "geri-koyma sonrası --check yeşil olmalı: "
                                 + r2.stdout + r2.stderr)

    def test_hidden_unit_is_provisionable_again(self):
        """Gizlenen unit `provision_` ile geri gelir: `die` değil, kurulum.

        Bu, `check_`→`provision_` hattının fail-CLOSED ama kendini onarıcı
        olduğunu ölçer; `npm ci` sahte PATH'ten geldiği için ağa çıkmaz."""
        target = self.root / "_calisma/video/node_modules/.bin/tsc"
        hidden = self.root / "_calisma/video/node_modules/.bin/tsc.hidden"
        target.rename(hidden)
        try:
            r = self._run_boot()
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("video (_calisma/video): npm ci", r.stdout)
            self.assertTrue(r.stdout.rstrip().endswith("BOOTSTRAP OK"), r.stdout)
        finally:
            if hidden.exists():
                hidden.rename(target)

    def test_real_tree_is_never_mutated(self):
        """REGRESYON: bu sınıf gerçek ağaca hiç dokunmaz.

        Kırmızıyı üretmek için ağaçta `*.hidden_by_test` izi bırakmak, testi
        çalıştıranın değil başkasının `--check`'ini bozuyordu. Tüm yeniden
        adlandırmalar `self.root` (tempdir) altında olduğu için burada ölçülür.
        """
        for label, rel in self.UNITS:
            with self.subTest(unit=label):
                self.assertFalse((self.root / (rel + ".hidden_by_test")).exists())
        # Gerçek kökte hiçbir gizli sentinel olmamalı. Yol listesi de elle
        # değil, envanterin göreli sentinel'lerinden türetilir.
        for label, rel in self.UNITS:
            abs_rel = os.path.join(ROOT, rel)
            with self.subTest(real=label):
                self.assertFalse(os.path.exists(abs_rel + ".hidden_by_test"),
                                 "gerçek ağaçta gizli sentinel kalmış: " + abs_rel)
                self.assertTrue(os.path.exists(abs_rel),
                                "gerçek ağaç bozuldu: " + abs_rel)

    # Birim etiketi artık gerçek yolu da yazıyor. Raporun üç tüketicisi var
    # ve hepsi korunmalı: (1) `check_bootstrap_toolchain.py` UNIT_RE'si
    # `^CHECK FAIL:\s*(\S+)` ile İLK token'ı, yani unit ADINI, yakalar —
    # yol parantez içinde geldiği için imza bozulmaz; (2) aynı dosyanın
    # "unit listesini kapıda kopyalama" testi `CHECK FAIL:\s*<unit>\b`
    # arar; (3) `test_recovery_command_matches_bootstrap_own_advice` blok
    # satırının kendi komutunu taşıdığını okur.
    # Beklenen yollar da ENVANTERDEN gelir: elle yazılmış bir sözlük, yeni
    # unit eklenince sessizce eksik kalırdı (dokuz birimin sekizini kapsıyor,
    # `browsers` dışarıda bırakılmıştı).
    EXPECTED_PATHS = {name: label for name, label, _c, _p in PATH_UNITS}

    def test_check_fail_line_keeps_unit_name_first(self):
        """Tuketicinin ayakta kalması: İLK token hâlâ unit adı olmalı.

        `UNIT_RE = ^CHECK FAIL:\\s*(\\S+)` kapının hangi unit'i okuduğunu
        belirler. Etiket yolu öne aldıysa kapı `pptx (_calisma/pptx)` diye
        okur ve kullanıcıya yanlış isim raporlar.
        """
        # `--check` fail-fast: ilk bozuk unit'te durur. `tsx` sentinel'i
        # `trend_db` unit'inin parçası olduğu için KIRMIZI unit trend_db'dir
        # (tsx adı bir alt-sentinel, ayrı unit değil).
        target = self.root / "apps/trend-db/node_modules/.bin/tsx"
        target.rename(self.root / "apps/trend-db/node_modules/.bin/tsx.h")
        try:
            r = self._run_boot("--check")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            line = next(l for l in r.stdout.splitlines() if l.startswith("CHECK FAIL:"))
            first_token = line.split(":", 1)[1].split()[0]
            self.assertEqual(first_token, "trend_db",
                             "ilk token unit adi olmaliydi: " + line)
            self.assertRegex(line, r"^CHECK FAIL:\s*trend_db\s+\(apps/trend-db\)")
        finally:
            hidden = self.root / "apps/trend-db/node_modules/.bin/tsx.h"
            if hidden.exists():
                hidden.rename(target)

    def test_check_fail_line_prints_real_path(self):
        """Etiket artık `ls` ile bakılacak yeri söylüyor."""
        target = self.root / "_calisma/pptx/node_modules/pptxgenjs"
        hidden = self.root / "_calisma/pptx/node_modules/pptxgenjs.h"
        target.rename(hidden)
        try:
            r = self._run_boot("--check")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("CHECK FAIL: pptx (_calisma/pptx)", r.stdout)
        finally:
            if hidden.exists():
                hidden.rename(target)

    def test_every_unit_path_is_reachable_in_the_fake_root(self):
        """Etiket yolları sahte kökte de GERÇEK yol olmalı.

        `unit_path` `$ROOT/` önekini soyuyor; sahte kökte göreli yol
        (`_calisma/pptx`) aynen görünmeli. Etiket kökten bağımsız bir
        sabite yaslanırsa bu test kırılır.
        """
        for unit, rel in self.EXPECTED_PATHS.items():
            with self.subTest(unit=unit):
                self.assertTrue((self.root / rel).exists(),
                                "etiket yolu sahte kökte yok: " + rel)

    def test_up_to_date_lines_print_real_paths(self):
        """Kurulum yolunun etiketi de yol yazıyor (tutarlılık)."""
        r = self._run_boot()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for unit, rel in self.EXPECTED_PATHS.items():
            with self.subTest(unit=unit):
                self.assertIn(f"{unit} ({rel}): up to date", r.stdout)

    def test_up_to_date_lines_follow_the_inventory_order(self):
        """Sıra da envanterden gelir — `trend_db_codegen` `trend_db`'den
        SONRA kurulmalı (node_modules'ına ihtiyaç duyar). Sıranın kayması
        `npm ci`'ın başarısız olmasıyla değil, TÜM unit'lerin ölçülmez
        hale gelmesiyle ölçülür, o yüzden burada sabit bir dizi değil
        envanterin kendi sırası referans alınır."""
        r = self._run_boot()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        positions = [r.stdout.index("%s (%s): up to date" % (n, l))
                     for n, l, _c, _p in UNIT_ROWS]
        self.assertEqual(positions, sorted(positions),
                         "kurulum sırası envanterdeki sırayla aynı değil")


class TestUnitInventoryIsSingleSource(unittest.TestCase):
    """Envanter TEK kaynakta: `bootstrap_units.conf` → script + testler.

    Ölçülen sebep: liste `dev_bootstrap.sh` içindeki `UNITS=(...)` dizisinde,
    `unit_path()` case tablosunda ve ÜÇ test sınıfında ayrı ayrı yazılıydı.
    Yeni bir unit eklemek dört yerden birini unutmak demekti; unutulan yer
    SESSİZCE kapsam kaybediyordu — script o unit'i hiç kontrol etmiyor,
    testler onu hiç ölçmüyor, yeşil batarya eksik kapsamı saklıyordu.

    Buradaki testler iki işi birden yapar: (1) STRÜKTÜREL — envanter ve
    script arasında kalan kopya yok; (2) DAVRANIŞSAL — envanteri bozunca
    script, script'i değiştirmeden, doğru şekilde ölür. İkinci tür asıl
    güvence: "yeni unit ekle" adımının gerçekten tek dosyalık olduğunu
    ölçer.
    """

    def setUp(self):
        self.root = _fake_bootstrap_root()
        self.addCleanup(shutil.rmtree, str(self.root), True)
        self.env = _fake_env(self.root)

    def _run_boot(self, *argv):
        script = str(self.root / "_calisma" / "dev_bootstrap.sh")
        return _run(["bash", script, *argv], env=self.env)

    # ── envanterin kendisi ──────────────────────────────────────────────────

    def test_every_row_declares_a_known_check_and_provision_kind(self):
        """Script yalnız beş provision türü ve dört check türü biliyor.

        Envanter bunlardan birine uymayan bir satır taşırsa script'in o
        satırı `die` ile reddetmesi beklenir (aşağıda ölçülüyor). Bu test
        yalnız hatırlatır: neden var olduğu buradadır.
        """
        for name, _label, check, prov in UNIT_ROWS:
            with self.subTest(unit=name):
                self.assertIn(_check_kind(check), KNOWN_CHECK_KINDS)
                self.assertIn(_prov_kind(prov), KNOWN_PROV_KINDS)

    def test_browsers_is_the_only_descriptive_label(self):
        """Alanlar BOŞLUKLA ayrılır, bu yüzden hiçbir alanda boşluk olmaz.

        Ölçülen tuzak: `browsers`'ın etiketi bir zamanlar `venv_z3 + chromium`
        idi. Beşinci alan (`_rest`) boş kaldığı için eksik-alan denetimi
        yakalamadı, satır sessizce `check`=venv_z3 `provision`=+ olarak
        ayrıştı ve script "bilinmeyen check türü (+)" ile öldü. Yapı denetimi
        bunu ikinci kez yakalıyor: yol olmayan tek etiket `browsers` ve türü
        `browser`.
        """
        self.assertEqual([n for n, _l, c, _p in DESCRIPTIVE_UNITS], ["browsers"])
        checks = {n: c for n, _l, c, _p in UNIT_ROWS}
        self.assertEqual(_check_kind(checks["browsers"]), "browser")

    def test_inventory_drives_both_the_script_and_the_tests(self):
        """`test_check_bootstrap_toolchain.py` de AYNI dosyayı okur.

        Kapıdaki "unit listesini kopyalama" testi elle dokuz ad yazıyordu;
        envanterden bir ad silinirse kapı sessizce bir ad daha az denetlerdi.
        """
        other = _read(os.path.join(HERE, "test_check_bootstrap_toolchain.py"))
        self.assertIn("bootstrap_units.conf", other,
                      "kapı testi envanteri okumuyor — kopya riski")

    # ── script envanteri okuyor, kopyalamıyor ───────────────────────────────

    def test_script_holds_no_inventory_copy(self):
        """Script'te unit listesi YOK: envanteri okur, kendi listesi yok.

        `UNITS=()` boş bir dizi olarak açılıp envanterle doldurulmalı; literal
        bir liste ya da `unit_path()` case tablosu kalmamalı.
        """
        script = _read(SCRIPT)
        self.assertIn("bootstrap_units.conf", script)
        # Kod satırları (yorumlar hariç): envanter dışında liste kurulmaz.
        code = "\n".join(l for l in script.splitlines()
                         if not l.lstrip().startswith("#"))
        self.assertNotRegex(code, r"UNITS=\([^)]",
                            "script unit listesini gömüyor, envanteri okumalı")
        for name in UNIT_NAMES:
            with self.subTest(unit=name):
                self.assertNotRegex(code, rf"check_{name}\b|provision_{name}\b",
                                    f"birim başına fonksiyon kalmış: {name}")

    def test_a_new_unit_needs_no_script_change(self):
        """TEK DOSYALIK EKLEME — asıl güvence.

        Envantere yeni bir satır eklemek script'i değiştirmeden onu
        ölçülebilir kılar: `--check` yeni birimi kendi adıyla, kendi
        görünen yoluyla fail-closed olarak raporlar. Elle tutulan bir
        `UNITS=(...)` dizisi olsaydı bu test kırmızı olurdu.
        """
        _rewrite_conf(self.root, lambda t: t + "\n# yeni satır\n"
                      "yeni_birim _calisma/yeni artifact:_calisma/yeni/u.txt venv\n")
        r = self._run_boot("--check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CHECK FAIL: yeni_birim (_calisma/yeni)", r.stdout)

    def test_inventory_order_is_the_check_order(self):
        """Sıra envanterin sırasıdır: satırı taşı, ölçülen sıra da taşınır.

        İLK satır sona taşınır (son satırı taşımak bir işe yaramaz — zaten
        sondadır). Ölçüm: ilk "up to date" satırı değişen birim olmalı, yani
        script'in gezdiği sırayı `dev_bootstrap.sh` içinde sabitleyen bir
        liste olmadığı kanıtlanır.
        """
        first_row = UNIT_ROWS[0]
        second = UNIT_ROWS[1]
        _rewrite_conf(self.root,
                      lambda t: _drop_row(t, first_row[0]) + " ".join(first_row) + "\n")
        r = self._run_boot()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        seen = [l for l in r.stdout.splitlines() if "up to date" in l]
        self.assertTrue(seen[0].startswith("%s (" % second[0]),
                        "ilk kurulan birim değişmedi: " + seen[0])
        self.assertEqual(seen[-1], "%s (%s): up to date" % (first_row[0], first_row[1]))

    # ── bozuk envanter fail-closed ──────────────────────────────────────────

    def test_label_with_a_space_is_rejected(self):
        """REGRESYON: boşluklu etiket ölçülen şekilde öldürür.

        Ölçüldü (2026-09-29): "venv_z3 + chromium" beşinci alanı doldurduğu
        için eksik-alan denetimi sessizce geçti ve script daha geç, yanlış
        bir sebeple ("bilinmeyen check türü (+)") öldü. Artık beşinci alanın
        boş olması zorunlu — ve bu satır o tuzağın canlı karşılığıdır.
        """
        _rewrite_conf(self.root, lambda t: _set_row(
            t, "browsers", ["browsers", "venv_z3 + chromium", "browser", "browser"]))
        r = self._run_boot("--check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("fazladan alan var", r.stderr)

    def test_missing_field_is_rejected(self):
        _rewrite_conf(self.root, lambda t: _set_row(
            t, "browsers", _row_fields(t, "browsers")[:3]))
        r = self._run_boot("--check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("eksik satır", r.stderr)

    def test_unknown_check_kind_fails_closed(self):
        _rewrite_conf(self.root, lambda t: _set_row(
            t, "venv_z3", ["venv_z3", UNIT_LABELS["venv_z3"], "bilinmeyen", "venv"]))
        r = self._run_boot("--check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("bilinmeyen check türü", r.stderr)

    def test_unknown_provision_kind_fails_closed(self):
        # Provision yalnız check BAŞARISIZKEN çağrılır; bu yüzden ilk satır
        # hem kırık check'e hem de bilinmeyen türe çevrilir.
        _rewrite_conf(self.root, lambda t: _set_row(
            t, "venv_z3",
            ["venv_z3", UNIT_LABELS["venv_z3"], "artifact:eksik/yok", "bilinmeyen"]))
        r = self._run_boot()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("bilinmeyen provision türü", r.stderr)

    def test_empty_inventory_is_rejected(self):
        _rewrite_conf(self.root, lambda t: "# hepsi yorum oldu\n")
        r = self._run_boot("--check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("unit envanteri boş", r.stderr)


class TestGeneratedArtifactUnits(unittest.TestCase):
    """`trend_db_codegen` + `dashboard_next_build` unit'leri.

    Ölçülen boşluk (2026-09-28): ikisi de CI'da VAR, scriptte YOKTU. Taze
    worktree'de bootstrap + --check yeşilken batarya 5/188 kırmızıydı:
    `prisma generate` 3 testi, `next build` kalan 2'yi düzeltiyor (ölçüldü).
    Buradaki sözleşme: ikisi de unit, yani --check onları da fail-closed
    ölçer — "yeşil CHECK OK" artık üretim yapılmamış ağacı sessizce kabul etmez.
    """

    def setUp(self):
        self.root = _fake_bootstrap_root()
        self.addCleanup(shutil.rmtree, str(self.root), True)
        self.log = str(self.root / "calls.log")
        self.env = dict(os.environ)
        self.env["FAKE_LOG"] = self.log
        self.env["FAKE_FREEZE"] = "\n".join(_script_pins())
        self.env["PATH"] = str(self.root / "bin") + os.pathsep + self.env["PATH"]
        self.env.pop("LEIBNIZ2_IN_BATTERY", None)
        self.env["FAKE_BROWSER_OK"] = "1"      # tarayıcı katmanı yeşil
        self.env["FAKE_ROOT"] = str(self.root)  # sahte npm/npx sınırı
        pathlib.Path(self.log).write_text("", encoding="utf-8")

    def _run_boot(self, *argv):
        script = str(self.root / "_calisma" / "dev_bootstrap.sh")
        return _run(["bash", script, *argv], env=self.env)

    def _drop_artifact(self, rel):
        p = self.root / rel
        if p.is_dir():
            shutil.rmtree(str(p))
        elif p.exists():
            p.unlink()

    def test_check_fails_closed_without_generated_client(self):
        self._drop_artifact("apps/trend-db/generated")
        r = self._run_boot("--check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CHECK FAIL: trend_db_codegen", r.stdout)

    def test_check_fails_closed_without_next_build(self):
        self._drop_artifact("apps/dashboard-next/.next")
        r = self._run_boot("--check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CHECK FAIL: dashboard_next_build", r.stdout)

    def test_bootstrap_produces_client_and_build_id(self):
        self._drop_artifact("apps/trend-db/generated")
        self._drop_artifact("apps/dashboard-next/.next")
        r = self._run_boot()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.rstrip().endswith("BOOTSTRAP OK"), r.stdout)
        calls = _read(self.log)
        self.assertIn("npx prisma generate", calls)
        self.assertIn("npm run build", calls)
        self.assertTrue((self.root / "apps/trend-db/generated/client.ts").is_file())
        self.assertTrue((self.root / "apps/dashboard-next/.next/BUILD_ID").is_file())

    def test_provisioning_is_idempotent(self):
        r = self._run_boot()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pathlib.Path(self.log).write_text("", encoding="utf-8")
        r2 = self._run_boot()
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIn("trend_db_codegen (apps/trend-db/generated): up to date",
                      r2.stdout)
        self.assertIn("dashboard_next_build (apps/dashboard-next/.next): up to date",
                      r2.stdout)
        self.assertEqual(_read(self.log), "", "ikinci koşu hiçbir şey kurmamalı")

    def test_prisma_generate_gets_placeholder_url(self):
        """`prisma.config.ts` DATABASE_URL'siz generate'ı reddeder; CI'ın
        kullandığı yer tutucu DSN verilmeli (gerçek kimlik bilgisi değil)."""
        self._drop_artifact("apps/trend-db/generated")
        r = self._run_boot()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("trend_db_codegen (apps/trend-db/generated): "
                      "prisma generate (kod üretimi", r.stdout)


class TestBrowserPinPythonFloor(unittest.TestCase):
    """BROWSER_PIN'in taşıyıcı yorumlayıcı tabanı (ölçülen ölüm).

    playwright 1.61+ `requires_python >=3.10` istiyor; 3.9'da pip "No matching
    distribution" der — beş npm kurulumundan SONRA ve sebebi yanlış göstererek.
    Script bu yüzden tabanı ÖNCEDEN ölçüyor ve reçete veriyor.
    """

    def setUp(self):
        self.root = _fake_bootstrap_root()
        self.addCleanup(shutil.rmtree, str(self.root), True)
        self.log = str(self.root / "calls.log")
        self.env = dict(os.environ)
        self.env["FAKE_LOG"] = self.log
        self.env["FAKE_FREEZE"] = "\n".join(_script_pins())
        self.env["PATH"] = str(self.root / "bin") + os.pathsep + self.env["PATH"]
        self.env.pop("LEIBNIZ2_IN_BATTERY", None)
        self.env["FAKE_BROWSER_OK"] = "0"      # tarayıcı katmanı eksik → provision
        self.env["FAKE_ROOT"] = str(self.root)  # sahte npm/npx sınırı
        pathlib.Path(self.log).write_text("", encoding="utf-8")

    def _run_boot(self, *argv):
        script = str(self.root / "_calisma" / "dev_bootstrap.sh")
        return _run(["bash", script, *argv], env=self.env)

    def test_old_interpreter_fails_with_recipe_not_pip_noise(self):
        self.env["FAKE_PY_VERSION"] = "3.9.6"
        r = self._run_boot()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("Python >=3.10", r.stdout + r.stderr)
        self.assertIn("3.9.6", r.stdout + r.stderr)
        self.assertIn("LEIBNIZ2_BROWSER_PIN", r.stdout + r.stderr)
        self.assertNotIn("No matching distribution", r.stdout + r.stderr)

    def test_explicit_pin_override_is_honored_and_loud(self):
        self.env["FAKE_PY_VERSION"] = "3.9.6"
        self.env["LEIBNIZ2_BROWSER_PIN"] = OLD_PY_PIN
        r = self._run_boot()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("UYARI", r.stdout)
        self.assertIn("pip install --quiet " + OLD_PY_PIN, _read(self.log))

    def test_supported_interpreter_uses_the_pinned_version(self):
        self.env["FAKE_PY_VERSION"] = "3.11.15"
        r = self._run_boot()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("UYARI", r.stdout)
        self.assertIn("pip install --quiet " + BROWSER_PIN, _read(self.log))

    def test_recipe_does_not_blame_path_alone(self):
        """REGRESYON (2026-09-29 taze-worktree kanıtı): mesaj "Çözüm: PATH'te
        >=3.10 bir python3 kullan" diyordu, ama taban denetimi VENV'in
        yorumlayıcısına bakıyor ve `venv_z3` aynı çağrıda ÖNCE çalıştığı
        için hata anında venv çoktan 3.9 ile yaratılmış oluyor. Yani
        önerilen kurtarma taze makinede ÇALIŞMIYORDU — ölçüldü: aynı hata
        0 s'de yeniden döndü. Reçete artık (a) ölçümün hangi yorumlayıcıya
        baktığını, (b) PATH'in tek başına yetmediğini, (c) kopyala-yapıştır
        kurtarma komutunu taşımalı."""
        self.env["FAKE_PY_VERSION"] = "3.9.6"
        r = self._run_boot()
        out = r.stdout + r.stderr
        self.assertIn("VENV", out,
                      "hangi yorumlayıcıya bakıldığı belirtilmeli")
        self.assertIn("YETMEZ", out,
                      "PATH'i değiştirmenin tek başına yetmediği söylenmeli")
        self.assertIn("rm -rf", out,
                      "kopyala-yapıştır kurtarma komutu taşımalı")
        self.assertIn("LEIBNIZ2_BROWSER_PIN", out, "3.9 kaçışı korunmalı")

    def test_floor_is_measured_on_the_venv_interpreter(self):
        """Reçetenin gerekçesi yapısal: taban denetimi `$VENV_PY`'ye bakar.
        Bu bir gün PATH python3'üne çevrilirse (doğru bir iyileştirme olurdu)
        mesajın uyarısı yanlışlaşır — ikisi birlikte değişmelidir."""
        text = _read(SCRIPT)
        self.assertIn('interp="$VENV_PY"', text,
                      "taban denetimi venv yorumlayıcısına bakmalı")

    def test_pin_floor_is_declared_next_to_the_pin(self):
        """Taban sabiti script'te durmalı ve gerekçesi yazılı olmalı: sürüm
        yükseltilip taban unutulursa (ör. 1.63 → 1.70) aynı sınıf ölüm
        sessizce geri gelir. Taban bir SÜRÜM değil, taşıyıcı şart olduğu için
        requirements dosyasında değil burada yaşar."""
        text = _read(SCRIPT)
        floor = re.search(r'BROWSER_PIN_MIN_PY="([0-9.]+)"', text)
        self.assertIsNotNone(floor, "BROWSER_PIN_MIN_PY bulunamadı")
        self.assertIn("python_floor_ok", text)
        self.assertIn("requires_python", text, "taban gerekçesi yazılı olmalı")


# Sahte yorumlayıcı: `_satisfying_interpreter` aday taramasını ÖLÇER.
#
# İki biçim, ikisi de /bin/sh: shebang `env python3` olsaydı sahte dizin
# kendi `python3`'ünü çağırır ve sonsuz özyinelemeye düşerdi.
#
#   SAF      — yalnız sürüm probuna cevap verir. Sürüm DENETLENMEZ,
#              ortam değişkeninden okunur; karşılaştırma gerçekten
#              yapılır, yani adayın tabanı geçip geçmediği ölçülür.
#   DELEGATE — sürüm probunu sahte yanıtlar, diğer her şeyi GERÇEK bir
#              Python'a devreder. `python3`/`python` için şart: sahte venv
#              yorumlayıcısının shebang'i `#!/usr/bin/env python3` ve o
#              sahte `python3` PATH'te birinci sırada; saf biçim
#              konulursa FAKE_VENV_PY hiç çalışmaz ve test ölçtüğünü
#              sandığı şeyi değil "venv olusturma" hatasını ölçer
#              (böyle bir kırılma yaşandı).
FAKE_INTERP_PURE = '''#!/bin/sh
ver="${%s:-3.9.6}"
case "$1" in
  --version) echo "Python $ver"; exit 0 ;;
  -c)
    case "$2" in
      *'version_info[:3]'*) echo "$ver"; exit 0 ;;
      *'version_info[:2]'*) echo "$ver" | cut -d. -f1,2; exit 0 ;;
      *)
        awk -v f="$3" -v h="$4" 'BEGIN{
          split(f,F,"."); split(h,H,".");
          for(i=1;i<=3;i++){ if((H[i]+0)>(F[i]+0)) exit 0; if((H[i]+0)<(F[i]+0)) exit 1 }
          exit 0 }'
        exit $?          # awk'in rc'si DIŞARI AKTARILMAZSA dal düşer ve
      ;;                # satır sonundaki `exit 1` çalışır — hep "başarısız".
    esac
    ;;
  -m)
    # Venv'i kuran yorumlayıcı HANGİ adaysa o olabilir; hepsinde bu kol
    # olmalı, yoksa seçilen aday `exit 1` ile kurulumu öldürür.
    if [ "$2" = "venv" ]; then
      mkdir -p "$3/bin" && cp "__FAKE_VENV_PY__" "$3/bin/python" \
        && chmod 755 "$3/bin/python"
      exit $?
    fi
    ;;
esac
exit 1
'''

FAKE_INTERP_DELEGATE = '''#!/bin/sh
ver="${%s:-3.9.6}"
case "$1" in
  --version) echo "Python $ver"; exit 0 ;;
  -c)
    case "$2" in
      *'version_info[:3]'*) echo "$ver"; exit 0 ;;
      *'version_info[:2]'*) echo "$ver" | cut -d. -f1,2; exit 0 ;;
    esac
    ;;
  -m)
    # `python3 -m venv <dir>` — gerçek venv KURMAZ (ağ + saniyeler), onun
    # yerine sahte venv python'u yazar. Scriptin bundan sonraki adımları
    # (`$VENV_PY -m pip install`, `pip freeze`) normalde işler.
    if [ "$2" = "venv" ]; then
      mkdir -p "$3/bin" && cp "__FAKE_VENV_PY__" "$3/bin/python" \
        && chmod 755 "$3/bin/python"
      exit $?
    fi
    ;;
esac
exec "__REAL_PYTHON__" "$@"
'''

# `_satisfying_interpreter` bu adayları sırayla arar ve İLK GEÇENDE
# durur. Test her adaya ne döneceğini bildirmek ZORUNDA: listede boşluk
# bırakılırsa sıradaki GERÇEK yorumlayıcı (PATH'te `~/.local/bin` gibi
# bir dizin) devreye girer ve test ölçtüğünü sandığı şeyi ölçmez —
# yani test makineden makineye değişir.
INTERP_CANDIDATES = ("python3.13", "python3.12", "python3.11", "python3.10",
                     "python3", "python")
INTERP_DELEGATING = ("python3", "python")


def _interp_env_key(name):
    """Sahte yorumlayıcının sürüm değişkeni — kabukta GENİŞLETİLEBİLİR olmalı.

    Ölçülen kırılma: `python3.11` için `FAKE_INTERP_VERSION_python3.11`
    yazıldığında kabuk genişletmesi NOKTADA durur (`${A_python3}` + `.11`),
    değişken okunmaz ve her aday sessizce 3.9.6 bildirir. Bu yüzden
    test, "geçen yorumlayıcı bulundu" dalını hiç göremiyordu ve not-found
    dalı yeşildi. Nokta → alt çizgi.
    """
    return "FAKE_INTERP_VERSION_" + name.replace(".", "_")


def _write_fake_interpreters(bindir):
    """Sahte yorumlayıcı dizini yazar; sürüm adaya gömülü gelir.

    Sürüm `FAKE_INTERP_VERSION_<ad>` ortam değişkeninden okunur — tek bir
    değişken tüm adaylara aynı sürümü bildirirdi.
    """
    bindir = pathlib.Path(bindir)
    bindir.mkdir(parents=True, exist_ok=True)
    (bindir / "fake_venv_py").write_text(FAKE_VENV_PY, encoding="utf-8")
    for name in INTERP_CANDIDATES:
        tpl = (FAKE_INTERP_DELEGATE if name in INTERP_DELEGATING
               else FAKE_INTERP_PURE)
        body = (tpl % _interp_env_key(name)) \
            .replace("__REAL_PYTHON__", sys.executable) \
            .replace("__FAKE_VENV_PY__", str(bindir / "fake_venv_py"))
        p = bindir / name
        p.write_text(body, encoding="utf-8")
        p.chmod(0o755)
    return bindir


class TestProvisionLinesPrintRealPaths(unittest.TestCase):
    """Kurulum çıktısı da `ad (gerçek yol)` biçimini kullanır.

    Ölçülen tutarsızlık (2026-09-29): `unit_path` yalnız `--check` ve
    "up to date" satırlarında kullanılıyordu. Beş provision türünün
    çıktısı birbirinden FARKLI ve üçü hataydı:

        venv_z3: kuruluyor            → yol YOK
        _calisma/pptx: npm ci         → ad YOK
        browsers: playwright==…        → yol YOK
        apps/trend-db: prisma …       → `sed` ile üst dizine budanmış
        apps/dashboard-next: next …   → `sed` ile üst dizine budanmış

    Yani "hangi dizini açmam lazım" sorusunun cevabı kurulum sırasında
    kayboluyordu. İki `sed` de gereksizdi: etiket envanterde olduğuna
    göre `unit_path` zaten doğru yolu veriyor.
    """

    def setUp(self):
        self.root = _fake_bootstrap_root()
        self.addCleanup(shutil.rmtree, str(self.root), True)
        self.env = _fake_env(self.root)

    def _run_boot(self, *argv):
        return _run(["bash", str(self.root / "_calisma" / "dev_bootstrap.sh"),
                     *argv], env=self.env)

    def _hide(self, *rel_paths):
        for rel in rel_paths:
            p = self.root / rel
            self.assertTrue(p.exists(), "sentinel yok: " + rel)
            p.rename(self.root / (rel + ".h"))

    def _unhide(self, *rel_paths):
        for rel in rel_paths:
            h = self.root / (rel + ".h")
            if h.exists():
                h.rename(self.root / rel)

    def _lines(self, out):
        return [l for l in out.splitlines() if ": " in l]

    def test_venv_provision_prints_its_real_path(self):
        self._hide("_calisma/.venv_z3/bin/python")
        try:
            r = self._run_boot()
            self.assertTrue(
                any(l.startswith("venv_z3 (_calisma/.venv_z3): kuruluyor")
                    for l in self._lines(r.stdout)),
                r.stdout)
        finally:
            self._unhide("_calisma/.venv_z3/bin/python")

    def test_npm_provision_prints_name_and_path(self):
        self._hide("_calisma/pptx/node_modules/pptxgenjs")
        try:
            r = self._run_boot()
            self.assertTrue(
                any(l.startswith("pptx (_calisma/pptx): npm ci")
                    for l in self._lines(r.stdout)),
                r.stdout)
        finally:
            self._unhide("_calisma/pptx/node_modules/pptxgenjs")

    def test_browser_provision_prints_its_label(self):
        self.env["FAKE_BROWSER_OK"] = "0"      # tarayıcı katmanı eksik
        r = self._run_boot()
        self.assertTrue(
            any(l.startswith("browsers (%s):" % UNIT_LABELS["browsers"])
                for l in self._lines(r.stdout)),
            r.stdout)

    def test_generated_provisions_print_name_and_path(self):
        for unit, rel in (("trend_db_codegen",
                           "apps/trend-db/generated/client.ts"),
                          ("dashboard_next_build",
                           "apps/dashboard-next/.next/BUILD_ID")):
            with self.subTest(unit=unit):
                self._hide(rel)
                try:
                    r = self._run_boot()
                    label = UNIT_LABELS[unit]
                    self.assertTrue(
                        any(l.startswith("%s (%s):" % (unit, label))
                            for l in self._lines(r.stdout)),
                        "%s satırı gerçek yolu taşımadı:\n%s" % (unit, r.stdout))
                finally:
                    self._unhide(rel)

    def test_no_provision_line_prints_a_bare_unit_name(self):
        """Hiçbir provision satırı `ad: ...` biçiminde KALMAMALI.

        Yapısal denetim: `say "$1: ..."` ya da elle budanmış yol kalırsa
        tutarsızlık sessizce geri gelir ve yukarıdaki testlerden biri
        kırılana kadar fark edilmez.
        """
        code = "\n".join(l for l in _read(SCRIPT).splitlines()
                         if not l.lstrip().startswith("#"))
        self.assertNotRegex(code, r'say "\$1:',
                            "provision çıktısı çıplak unit adı basıyor")
        self.assertNotIn("sed 's#/generated##'", code,
                         "budanmış yol etiketi yerine kullanılıyor")


class TestBrowserRemedyHint(unittest.TestCase):
    """Ölüm mesajı KURTARMA YOLU da verir, ve o yol ölçülmüştür.

    Ölçülen boşluk (2026-09-29, taze-worktree kanıtı): eski mesaj
    `PATH=<python3'ün bulunduğu dizin>` diyordu — yer tutucu, ve bu makede
    ÇALIŞMIYORDU: PATH'te `python3.11` vardı ama `python3` yoktu, `python3`
    3.9.6'ydı. Yani reçete tam olarak ölümü doğuran koşulu yeniden
    öneriyordu. Şimdi script tabanı geçen yorumlayıcıyı sistemde arıyor ve
    TAM yolunu yazıyor; bulunamazsa bunu açıkça söylüyor (uydurma komut
    basmıyor — "ölçülemeyen yeşil sayılmaz").
    """

    def setUp(self):
        self.root = _fake_bootstrap_root()
        self.addCleanup(shutil.rmtree, str(self.root), True)
        self.env = _fake_env(self.root)
        self.env["FAKE_PY_VERSION"] = "3.9.6"     # venv yorumlayıcısı eski
        # Tarayıcı katmanı EKSİK olmalı: ipucu `browsers` PROVISION
        # yolunda basılır, check yeşilken o yol hiç çalışmaz.
        self.env["FAKE_BROWSER_OK"] = "0"

    def _hint_output(self, version_by_name):
        """Belirtilen yorumlayıcı haritasıyla çözüm ipucu çıktısını verir."""
        bindir = _write_fake_interpreters(self.root / "fakebin")
        self.env["PATH"] = str(bindir) + os.pathsep + self.env["PATH"]
        for name, ver in version_by_name.items():
            self.env[_interp_env_key(name)] = ver
        r = _run(["bash", str(self.root / "_calisma" / "dev_bootstrap.sh")],
                 env=self.env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        return r.stdout + r.stderr

    def _only(self, passing):
        """Verilen aday dışında hepsi tabanı GEÇEMEYEN harita."""
        return {n: ("3.12.1" if n == passing else "3.9.6")
                for n in INTERP_CANDIDATES}

    def test_hint_names_a_real_interpreter_not_a_placeholder(self):
        """Bulunan yorumlayıcının TAM YOLU ve çalıştırılabilir komut yazılır."""
        out = self._hint_output(self._only("python3.11"))
        bindir = str(self.root / "fakebin")
        self.assertIn(bindir, out, "bulunan yorumlayıcının dizini yazılmadı")
        self.assertIn("rm -rf", out, "kurtarma komutu yok")
        self.assertIn("_calisma/.venv_z3", out, "silinecek venv yolu yok")
        self.assertIn("dev_bootstrap.sh", out, "yeniden koşulacak betik yok")
        # Yer tutucu KALMAMALI: ölçülen boşluğun kendisiydi.
        self.assertNotIn("<python3", out,
                         "hâlâ yer tutucu basıyor — reçete çalıştırılamaz")

    def test_hint_is_fail_closed_when_nothing_satisfies_the_floor(self):
        """Hiçbir aday geçmiyorsa mesaj bunu SÖYLER, komut UYDURMAZ."""
        out = self._hint_output({n: "3.9.6" for n in INTERP_CANDIDATES})
        self.assertIn("YÖK", out, "yetersiz durum açıkça söylenmeli")
        self.assertNotIn("bulundu:", out, "olmayan yorumlayıcı varsayıldı")
        # Uydurma kurtarma komutu basılmamalı: `rm -rf ... PATH=` satırı
        # yalnız GERÇEKTEN bulunan bir dizin varsa basılır.
        self.assertNotRegex(out, r"rm -rf '[^']*' && PATH=",
                            "bulunmayan yorumlayıcı için komut basıldı")

    def test_hint_always_offers_the_39_escape_hatch(self):
        """Geçici geçersiz kılma HER iki dalda da sunulur.

        Yorumlayıcı bulunmuş olsa bile bu seçenek geçerlidir; yalnız
        bulunamadığı dalda yazılırsa mesaj, eskisinden daha eksik olurdu.
        """
        for passing in (None, "python3.11"):
            with self.subTest(bulunan=passing):
                out = self._hint_output(
                    self._only("python3.11") if passing else
                    {n: "3.9.6" for n in INTERP_CANDIDATES})
                self.assertIn("LEIBNIZ2_BROWSER_PIN", out)

    def test_hint_tells_you_to_delete_the_venv_first(self):
        """Venv silinmeden önerilen komut ÇALIŞMAZ (ölçüldü: 0 s'de geri döner)."""
        out = self._hint_output(self._only("python3.11"))
        self.assertIn("SİL", out, "venv'in silinmesi söylenmiyor")
        self.assertIn("YETMEZ", out,
                      "PATH'in tek başına yetmediği uyarısı korunmalı")

    # ── venv'i kuran yorumlayıcı ────────────────────────────────────────────
    def _provision_venv(self, version_by_name):
        """Venv'i YOK edip kurulumu koşturur; venv satırının logunu verir.

        Venv check'inin kırık olması gerekir, yoksa provision hiç çağrılmaz
        ve hangi yorumlayıcının seçildiği ölçülemez.
        """
        bindir = _write_fake_interpreters(self.root / "fakebin")
        self.env["PATH"] = str(bindir) + os.pathsep + self.env["PATH"]
        for name, ver in version_by_name.items():
            self.env[_interp_env_key(name)] = ver
        import shutil as _sh
        _sh.rmtree(str(self.root / "_calisma" / ".venv_z3"))
        r = _run(["bash", str(self.root / "_calisma" / "dev_bootstrap.sh")],
                 env=self.env)
        return r

    def test_venv_is_built_with_an_interpreter_that_satisfies_the_pin(self):
        """Venv, tarayıcı pinini taşıyabilen bir yorumlayıcıyla kurulur.

        Ölçülen kırılma (2026-09-29): venv daima PATH'teki `python3` ile
        kuruluyordu. Bu makinede `python3` 3.9.6, ama `python3.11` PATH'te
        VARDI; yine de venv 3.9 ile kurulup `browsers` adımında ölüyor ve
        kullanıcı kurtarma turuna giriyordu. Dahası: ipucunun önerdiği
        komut da çalışmıyordu — `python3.11` dizinini PATH'e eklemek
        `python3`'ü değiştirmiyor. Yani ölüm, reçeteden de geliyordu.
        """
        r = self._provision_venv(self._only("python3.12"))
        self.assertIn("venv_z3 (_calisma/.venv_z3): kuruluyor (python3=python3.12",
                      r.stdout,
                      "venv tabanı geçen yorumlayıcıyla kurulmadı")
        self.assertTrue((self.root / "_calisma" / ".venv_z3" / "bin" / "python")
                        .exists(), "sahte venv oluşmadı")

    def test_venv_falls_back_to_python3_when_nothing_satisfies(self):
        """Tabanı geçen yorumlayıcı YOKSA davranış DEĞİŞMEZ: `python3`.

        Yeni seçim, uygun yorumlayıcı bulunmayan makineleri etkilememeli —
        yoksa "iyileştirme" dar bir makine kümesini kırardı.
        """
        r = self._provision_venv({n: "3.9.6" for n in INTERP_CANDIDATES})
        self.assertIn("venv_z3 (_calisma/.venv_z3): kuruluyor (python3=python3,",
                      r.stdout,
                      "yedek davranış bozuldu: sadece python3 kullanılmalı")


class TestSinglePinSource(unittest.TestCase):
    """Sürüm sabiti TEK dosyada yaşar: `_calisma/requirements-z3.txt`.

    Ölçülen gerekçe (2026-09-28): sürümler kopyalanmıştı — scriptin PINS
    dizisi, testin PINS aynası, doğrudan workflow kurulumları ve cache key'leri.
    Daha kötüsü `verify.yml`'in bir job'ı pre-commit/pyyaml/jsonschema'yı
    **PİNSİZ** kuruyordu: iki sürüm hattı sessizce birlikte yaşıyordu ve
    "iki kaynak eşit mi" testi onu görmüyordu. Bu kapı aynı sınıf sızıntının
    geri dönmesini fail-closed engeller: sürüm bump'ı tek satır olmalı.
    """

    # `docs/HOOK_ENV_MATRIX.md` de TÜKETİCİDİR: z3 satırı "`z3-solver`
    # pip pin'i" diyor. Üç öteki doc'ta bu bağ zorunluydu
    # (`test_user_docs_reference_pin_source...`), bu doc listede OLMADIĞI
    # için boşlukta kaldı — yani sürüm matrisinin okuru, o pini nereden
    # alacağını öğrenemiyordu. Ölçüldü: doc'ta `requirements-z3.txt` YOK.
    MATRIX_DOC = "docs/HOOK_ENV_MATRIX.md"

    CONSUMERS = ("_calisma/dev_bootstrap.sh",
                 ".github/workflows/verify.yml",
                 "_calisma/CIKTI/test_dev_bootstrap.py",
                 "README.md",
                 "docs/FIRST_RUN_TUTORIAL.md",
                 "docs/READER_TEST_PROTOCOL.md",
                 MATRIX_DOC)

    def test_no_version_literal_outside_the_requirements_file(self):
        leaks = []
        for rel in self.CONSUMERS:
            is_test = rel.endswith("test_dev_bootstrap.py")
            for m in PIN_LITERAL.finditer(_read(os.path.join(ROOT, rel))):
                if is_test and m.group(0) in ALLOWED_TEST_FIXTURES:
                    continue
                leaks.append("%s → %s" % (rel, m.group(0)))
        self.assertEqual(leaks, [],
                         "sürüm tek kaynaktan sabitlenmeli: " + "; ".join(leaks))

    def test_requirements_file_is_complete_and_fully_pinned(self):
        venv, browser = _requirements_sections()
        self.assertTrue(venv, "[venv] bölümü boş")
        normalize = lambda pin: re.sub(r"[-_.]+", "-", pin.split("==", 1)[0].lower())
        self.assertEqual(len(venv), len(set(normalize(pin) for pin in venv)),
                         "[venv] paketleri yinelenmemeli")
        for pin in venv:
            self.assertRegex(pin, r"^[A-Za-z_][A-Za-z0-9_.-]*==[0-9][0-9A-Za-z.]*$",
                             "pinsiZ satır (sürüm hattı açılır): %r" % pin)
        self.assertRegex(browser, r"^playwright==[0-9][0-9A-Za-z.]*$", browser)

    def test_ci_installs_and_caches_from_the_requirements_file(self):
        yml = _read(VERIFY_YML)
        self.assertNotRegex(yml, r"pip install \S+==",
                            "CI'da sabitlenmiş kurulum kaldı")
        self.assertEqual(yml.count("pip install -r _calisma/requirements-z3.txt"), 8,
                         "tüm kök-ortam CI kurulumları tek kaynaktan olmalı")
        self.assertEqual(yml.count("hashFiles('_calisma/requirements-z3.txt')"), 2,
                         "iki cache anahtarı da kaynaktan türemeli")

        lines = yml.splitlines()
        direct_installs = []
        managed = {"z3-solver", "pyyaml", "pre-commit", "jsonschema",
                   "pillow", "playwright"}
        index = 0
        while index < len(lines):
            line = lines[index]
            index += 1
            if line.lstrip().startswith("#") or "pip install" not in line:
                continue
            command = line.split("pip install", 1)[1].strip()
            while command.endswith("\\") and index < len(lines):
                command = command[:-1] + " " + lines[index].strip()
                index += 1
            if "-r _calisma/requirements-z3.txt" in command:
                continue
            packages = {
                token.strip("\\\"'").split("==", 1)[0].lower().replace("_", "-")
                for token in command.split()
            }
            if packages & managed:
                direct_installs.append(line.strip())
        self.assertEqual(
            direct_installs, [],
            "gereksinim dosyasındaki paketler başka bir pip komutunda kuruluyor: %s"
            % direct_installs)

    def test_every_fixture_exception_is_documented(self):
        """İzin listesi boş doldurulmasın: her istisna bir gerekçe taşır ve
        o gerekçe gerçekten dosyada yazılıdır."""
        text = _read(os.path.join(ROOT, "_calisma", "CIKTI", "test_dev_bootstrap.py"))
        for pin, why in ALLOWED_TEST_FIXTURES.items():
            self.assertIn(why, text, "fixture gerekçesi kodda yazılı değil")

    def test_user_docs_reference_pin_source_instead_of_versions(self):
        for rel in ("README.md", "docs/FIRST_RUN_TUTORIAL.md",
                    "docs/READER_TEST_PROTOCOL.md", self.MATRIX_DOC):
            with self.subTest(file=rel):
                text = _read(os.path.join(ROOT, rel))
                self.assertIn("requirements-z3.txt", text,
                              "%s pin kaynağını göstermeli" % rel)

    def _matrix_rows(self):
        """HOOK_ENV_MATRIX tablosunu AYNI ayrıştırıcıyla okur.

        İkinci bir ayrıştırıcı YAZILMAZ: doc'un sahibi zaten
        `check_hook_env_matrix.parse_table`. İki ayrı ayrıştırıcı, tablonun
        iki farklı yorumunu (ve aralarında sessiz bir kaymayı) üretirdi —
        doc'un yapısal denetimini burada yeniden yorumlama riski.
        """
        import check_hook_env_matrix as chem
        return chem.parse_table(_read(os.path.join(ROOT, self.MATRIX_DOC)))

    def test_env_matrix_doc_delegates_pip_pins_to_the_single_source(self):
        """Sürüm matrisi pip pini VAAT EDER ama sürüm YAZMAZ.

        Matrisin işi gözlenen sürümleri göstermektir (`z3` prob'u
        `5.1.0` döner, pip pini ise dört haneli `5.1.0.0` der — gözlem ile pin
        AYNI ŞEY DEĞİLDİR ve karıştırılmamalıdır). Pin hücresinin dediği
        dağıtımın gerçekten kaynakta kurulu olduğunu ölçüyoruz: doc,
        script'in hiç kurmadığı bir şeyi vaat edemez.
        """
        rows = self._matrix_rows()
        self.assertTrue(rows, "HOOK_ENV_MATRIX.md tablosu okunamadı")

        pinned = {re.sub(r"[-_.]+", "-", p.split("==", 1)[0].lower())
                  for p in PINS}
        pip_cells = {k: c[3] for k, c in rows.items() if "pip pin" in c[3]}
        self.assertTrue(pip_cells,
                        "matriste 'pip pin' diyen satır yok — ölçüm yüzeyi kayboldu")
        for key, cell in sorted(pip_cells.items()):
            named = {re.sub(r"[-_.]+", "-", t.lower())
                     for t in re.findall(r"`([^`]+)`", cell) if "/" not in t}
            self.assertTrue(named, "%s: 'pip pin' diyor ama paket adlamıyor" % key)
            unknown = named - pinned
            self.assertEqual(unknown, set(),
                             "%s: doc pip pin'i diyor ama kaynakta yok: %s"
                             % (key, sorted(unknown)))

    def test_env_matrix_observed_column_is_not_mistaken_for_a_pin(self):
        """Gözlem sütunu ile pip pini AYRIŞMALI.

        z3 prob'u `5.1.0` dondurur, pip pini ise dört haneli `5.1.0.0`
        der — yani gözlem ile pin aynı metin DEĞİLDİR. Karıştırılırsa
        matris, kaynağa dokunmadan "pini güncelledin" izlenimi verir.
        Beklenen: doc'ta `paket==sürüm` biçimli LİTERAL yok. (Bu satırın
        kendisi de tarama altında: literal yazmak, taradığı kuralı ihlal
        eder — ölçüldü, ilk yazımda bu test kendi kaynağını yakaladı.)
        """
        text = _read(os.path.join(ROOT, self.MATRIX_DOC))
        self.assertEqual(PIN_LITERAL.findall(text), [],
                         "matris sürümü YAZMAMALI, kaynağı göstermeli")


if __name__ == "__main__":
    unittest.main()
