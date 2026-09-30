#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_bootstrap_toolchain.py — araç-kümesi kapısının sözleşme testleri.

Seam = kapı CLI'si (`check_bootstrap_toolchain.main`) + `LEIBNIZ2_BOOTSTRAP`
dikişi. Davranış testleri HERMETİK: sahte bootstrap betiği geçici dizinde
yazılır, gerçek araç-kümesine (venv, node_modules, chromium) hiç dokunulmaz —
batarya bu testi kendi ortamında koşur, `dev_bootstrap.sh`'a bağımlı olmaz.

Kapsanan sözleşmeler:
  - rc=0 → PASS ("CHECK OK")
  - rc=1 → BLOKE + ilk eksik unit adı + kopyala-yapıştır kurtarma komutu
  - rc=1 ama `CHECK FAIL:` satırı yoksa → unit UYDURMAZ (None kalır)
  - beklenmeyen rc (2/127/…) → kör kapı rc=2, "eksik" DENMEZ
  - bootstrap betiği yok → kör kapı rc=2 (sessiz PASS yasak)
  - timeout → kör kapı rc=2
  - --json makine-okunur ve rc ile gövde tutarlı
  - GERÇEK AĞAÇ değişmezleri: hook wiring, yalnız-`--check` çağrısı
    (özyineleme kilidi), envanter/manifest/HOOK_COVERAGE kayıtları ve
    kurtarma komutunun bootstrap'ın kendi komutuyla aynı olması.
"""

import ast
import contextlib
import io
import json
import os
import pathlib
import re
import stat
import sys
import tempfile
import textwrap
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
ROOT = CIKTI.parent.parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import check_bootstrap_toolchain as gate  # noqa: E402

REAL_CONFIG = ROOT / ".pre-commit-config.yaml"
REAL_SKILL = ROOT / "skills" / "verify-chain" / "SKILL.md"
REAL_BOOTSTRAP = ROOT / "_calisma" / "dev_bootstrap.sh"
REAL_MANIFEST = CIKTI / "check_unit_tests.list"
HOOK_ID = "check-bootstrap-toolchain"
TEST_FILE = "test_check_bootstrap_toolchain.py"


def write_fake_bootstrap(body: str) -> pathlib.Path:
    """Geçici bir bootstrap betiği yaz ve yolunu döndür."""
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="bootstrap-gate-"))
    script = tmpdir / "dev_bootstrap.sh"
    script.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def run_gate(argv=None, script=None):
    """Kapıyı `LEIBNIZ2_BOOTSTRAP` dikişiyle koştur → (rc, stdout+stderr)."""
    env_backup = os.environ.get("LEIBNIZ2_BOOTSTRAP")
    if script is not None:
        os.environ["LEIBNIZ2_BOOTSTRAP"] = str(script)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = gate.main(argv or [])
    finally:
        if env_backup is None:
            os.environ.pop("LEIBNIZ2_BOOTSTRAP", None)
        else:
            os.environ["LEIBNIZ2_BOOTSTRAP"] = env_backup
    return rc, buf.getvalue()


def branch(script: str, label: str) -> str:
    """`case` dalının GÖVDESİ: `label)` ile kendi `;;` terminatörü arası.

    Neden: önceki ölçüm `end = text.index("--full)", start)` ile
    sınırlıydı, yani dalın sonunu değil İSİMDE geçen bir sonraki bayrağı
    arıyordu. `--verify` eklendiğinde `--check)` ile `--full)` arasına
    girdi ve `run_battery` aralığa düştü — test kendi kurgusundan
    kırmızıya döndü (ölçüldü: "'run_battery' unexpectedly found").

    `;;` terminatörü dalın GERÇEK sonudur, dolayısıyla bu hem daha dar
    hem daha doğru bir sınırdır: invariant artık "bu dalın içinde"
    der, "bu daldan sonraki her şeyde" değil.
    """
    start = script.index(label)
    end = script.index(";;", start)
    return script[start:end]


def code_only(path: pathlib.Path) -> str:
    """Yalnız ÇALIŞTIRILABILIR kod — docstring ve yorumlar düşer.

    Neden: bu modülün docstring'i tam olarak yaptığı şeyi SAYIYLA anlatıyor
    ("kapı kurmaz: `npm ci` + `prisma generate` …"). Ham metin taraması bu
    açıklamayı ihlal sanır ve test, tanımı kendi varlığıyla çürütür. Bu
    yüzden yasaklar koda uygulanır, söze değil.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    holders = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders) or not node.body:
            continue
        first = node.body[0]
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def entry_line(block: str) -> str:
    """Hook bloğundaki `entry:` satırı (argümanlar burada yaşar)."""
    line = next(l for l in block.splitlines() if l.strip().startswith("entry:"))
    return line.strip()


def hook_block(text: str, hook_id: str) -> str:
    """`.pre-commit-config.yaml` içinden bir hook'un bloğunu metin olarak kes.

    YAML bağımlılığı istemiyoruz (batarya venv python'ında pyyaml var ama
    bu test stdlib-only kalmalı); blok sınırları kanonik: `- id: <hook_id>`
    satırından sonraki `- id:` satırına kadar.
    """
    start = text.find(f"- id: {hook_id}\n")
    if start == -1:
        raise AssertionError(f"hook bulunamadı: {hook_id}")
    nxt = text.find("\n      - id:", start + 1)
    return text[start:] if nxt == -1 else text[start:nxt]


class TestPassPath(unittest.TestCase):
    def test_rc_zero_passes(self):
        script = write_fake_bootstrap('echo "CHECK OK"\nexit 0\n')
        rc, out = run_gate(script=script)
        self.assertEqual(rc, 0)
        self.assertIn("CHECK OK", out)

    def test_json_ok(self):
        script = write_fake_bootstrap('echo "CHECK OK"\nexit 0\n')
        rc, out = run_gate(["--json"], script=script)
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["missing_unit"])


class TestBlockPath(unittest.TestCase):
    """Eksik araç-kümesi → commit BLOKE + kurtarma komutu."""

    def _missing(self, unit="dashboard_next_build"):
        return write_fake_bootstrap(
            f'printf "CHECK FAIL: {unit} eksik veya paritesiz '
            "(kurulum: bash '/x/_calisma/dev_bootstrap.sh')\\n\"\nexit 1\n"
        )

    def test_rc_one_blocks_with_recovery(self):
        rc, out = run_gate(script=self._missing())
        self.assertEqual(rc, gate.BLOCK)
        self.assertIn("BLOKE", out)
        # Kullanıcının araştırmaya devam etmemesi için komut KOPYALANIR.
        self.assertIn(gate.RECOVERY, out)

    def test_first_missing_unit_is_named(self):
        rc, out = run_gate(script=self._missing("venv_z3"))
        self.assertEqual(rc, gate.BLOCK)
        self.assertIn("venv_z3", out)

    def test_json_block(self):
        rc, out = run_gate(["--json"], script=self._missing("pptx"))
        self.assertEqual(rc, gate.BLOCK)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "missing")
        self.assertEqual(payload["missing_unit"], "pptx")
        self.assertEqual(payload["recovery"], gate.RECOVERY)

    def test_no_fail_line_means_no_invented_unit(self):
        """`CHECK FAIL:` yoksa kapı hangi unit'in eksik olduğunu BİLMEZ.

        Uydurma bir unit adı yazmak, kullanıcıyı yanlış yere yönlendirir
        (en kötü hata: eksik olan başka bir şeyken "şunu kur" demek).
        """
        script = write_fake_bootstrap('echo "boş bir hata"\nexit 1\n')
        rc, out = run_gate(["--json"], script=script)
        self.assertEqual(rc, gate.BLOCK)
        self.assertIsNone(json.loads(out)["missing_unit"])

    def test_still_blocks_even_without_unit_name(self):
        rc, out = run_gate(script=write_fake_bootstrap("exit 1\n"))
        self.assertEqual(rc, gate.BLOCK)
        self.assertIn(gate.RECOVERY, out)


class TestBlindGate(unittest.TestCase):
    """Ölçülemeyen = yeşil değil. Kör kapı rc=2, commit YİNE bloklanır."""

    def test_missing_script_is_blind_not_pass(self):
        rc, out = run_gate(["--json"], script="/nonexistent/dev_bootstrap.sh")
        self.assertEqual(rc, gate.BLIND)
        self.assertEqual(json.loads(out)["status"], "blind")

    def test_unexpected_rc_is_blind(self):
        rc, out = run_gate(["--json"], script=write_fake_bootstrap("exit 127\n"))
        self.assertEqual(rc, gate.BLIND)
        self.assertEqual(json.loads(out)["rc"], 127)

    def test_rc_two_is_blind(self):
        rc, out = run_gate(["--json"], script=write_fake_bootstrap("exit 2\n"))
        self.assertEqual(rc, gate.BLIND)

    def test_blind_message_does_not_claim_missing_toolset(self):
        """`--check` kendi argüman hatasında rc=2 verir; bu 'eksik
        araç-kümesi' değildir ve öyle sunulmamalıdır."""
        rc, out = run_gate(script=write_fake_bootstrap("exit 2\n"))
        self.assertEqual(rc, gate.BLIND)
        self.assertIn("KÖR KAPI", out)
        self.assertNotIn(gate.RECOVERY, out)

    def test_timeout_is_blind(self):
        script = write_fake_bootstrap("sleep 5\nexit 0\n")
        rc, out = run_gate(["--json", "--timeout", "1"], script=script)
        self.assertEqual(rc, gate.BLIND)
        self.assertEqual(json.loads(out)["status"], "blind")


class TestWiringInvariants(unittest.TestCase):
    """Gerçek ağaç değişmezleri — kablolama bozulursa kapı sessizce
    çalışmaz (bir hook config'e hiç yazılmamışsa test kırılmalı)."""

    @classmethod
    def setUpClass(cls):
        cls.config = REAL_CONFIG.read_text(encoding="utf-8")
        cls.block = hook_block(cls.config, HOOK_ID)

    def test_hook_is_registered(self):
        self.assertIn(f"- id: {HOOK_ID}", self.config)

    def test_entry_points_at_the_gate_script(self):
        self.assertIn("entry: python3 _calisma/CIKTI/check_bootstrap_toolchain.py",
                      self.block)

    def test_hook_always_runs(self):
        """`files:` dar tetikleme olsaydı, araç-kümesi bozukken yalnız
        dokunulmayan bir dosyaya yapılan commit kapıyı atlatırdı —
        tam olarak bu kapının var olma sebebi olan boşluk."""
        self.assertIn("always_run: true", self.block)

    def test_hook_does_not_take_filenames(self):
        self.assertIn("pass_filenames: false", self.block)

    def test_hook_runs_on_pre_commit_stage(self):
        self.assertIn("stages: [pre-commit]", self.block)

    def test_entry_line_carries_no_bootstrap_arguments(self):
        """`entry:` satırı bayraksız olmalı — `--check`'i KAPININ kendisi
        ekler. Config'de bayrak görünürse iki yerden yönlendirilmiş olur
        ve biri unutulduğunda kapı sessizce farklı bir şey ölçer."""
        line = entry_line(self.block)
        self.assertNotIn("--check", line)
        self.assertNotIn("--full", line)
        self.assertNotIn("dev_bootstrap.sh", line)

    def test_gate_invokes_check_only(self):
        """Özyineleme kilidi: bu kapı `dev_bootstrap.sh`'ı çağırır, o da
        `--full` ile bataryayı koşabilir. Çağrı YALNIZ `--check` olmalı."""
        code = code_only(CIKTI / "check_bootstrap_toolchain.py")
        # Tırnak stiline takılmasın diye ham bayrak aranır: `ast.unparse`
        # tek tırnağa normalize eder, ama bayrağın kendisi değişmez.
        self.assertIn("--check", code)
        self.assertNotIn("--full", code)
        self.assertNotIn("run_battery", code)

    def test_bootstrap_check_branch_never_runs_the_battery(self):
        """`--check` bataryayı çalıştırmaz — bu, yukarıdaki kilidin ikinci
        yarısıdır. Metinsel invariant: `--check)` case bloğu içinde
        run_battery geçmemeli."""
        text = REAL_BOOTSTRAP.read_text(encoding="utf-8")
        self.assertNotIn("run_battery", branch(text, "--check)"))

    def test_bootstrap_verify_branch_runs_the_battery(self):
        """`--verify` bataryayı KOŞAR — `--full` ile aynı uçtan uca yol."""
        text = REAL_BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn("run_battery", branch(text, "--verify)"))

    def test_bootstrap_verify_branch_never_provisions(self):
        """`--verify` ÖLÇER, KURMAZ — `--full`'in ayırt edici farkı.

        Kapı (`check_bootstrap_toolchain.py`) kurulum yapmaz; `--verify`
        de kurmamalı, yoksa "ölçtüğünü sandığın ağacı değiştirmiş olursun"
        ve fail-closed ölçümü sessizce kendi koşulunu bozar.
        """
        text = REAL_BOOTSTRAP.read_text(encoding="utf-8")
        self.assertNotIn("provision_unit", branch(text, "--verify)"))

    def test_gate_never_auto_installs(self):
        """Kapı ölçer, KURMAZ. Kurulum commit'e gömülemez (ağ + dakikalar)."""
        source = code_only(CIKTI / "check_bootstrap_toolchain.py")
        for forbidden in ("pip install", "npm ci", "npm install",
                          "prisma generate", "next build", "playwright install"):
            self.assertNotIn(forbidden, source)

    def test_hook_is_documented_in_the_inventory_block(self):
        self.assertIn(HOOK_ID, REAL_SKILL.read_text(encoding="utf-8"))

    def test_test_file_is_in_the_battery_manifest(self):
        self.assertIn(TEST_FILE, REAL_MANIFEST.read_text(encoding="utf-8"))

    def test_hook_coverage_maps_hook_to_test(self):
        import test_coverage_report as coverage
        self.assertEqual(coverage.HOOK_COVERAGE.get(HOOK_ID), [TEST_FILE])

    def test_recovery_command_matches_bootstrap_own_advice(self):
        """İki yer kurtarma komutunu yazıyor (bootstrap'ın kendi `CHECK FAIL`
        satırı ve kapının RECOVERY). Ayrışırsa kullanıcı blokta başka bir
        komuta yönelir — bu yüzden sapma ölçülür.

        SATIR SEÇİMİ: `next(... if "CHECK FAIL:" in l)` ilk eşleşmeyi alır;
        etiket yolu eklenince `unit_path` açıklamasında da bu metin geçtiği
        için seçim bir YORUM satırına kayabiliyordu (ölçüldü: "not found in
        '# `^CHECK FAIL:...` ile İLK token...'"). Kurtarma komutunu yazan
        satır, `say` çağrısı olan gerçek `CHECK FAIL:` üretimidir.

        BİÇİM AYRIMI: bootstrap'ın kendi öğütü artık GÖRELI değil
        mutlak yol basıyor (`bash '$SELF'`). Sebep: göreli komut
        başka bir dizinden çalıştırıldığında kırılıyordu (2026-09-29
        düzeltmesi) — yani eski literal, aynı betiğe daha kötü bir
        referanstı. Bu yüzden invariant LITERAL'I değil "aynı betiğe
        işaret eder" gerçeğini ölçer: `$SELF` tanımı göreli yoldan
        türetilmiş olmalı, kapının `RECOVERY`'si ise değişmemiş kalmalı.
        """
        text = REAL_BOOTSTRAP.read_text(encoding="utf-8")
        lines = [l for l in text.splitlines()
                 if "CHECK FAIL:" in l and not l.lstrip().startswith("#")]
        self.assertTrue(lines, "bootstrap'ta CHECK FAIL uretimi bulunamadi")
        line = next(l for l in lines if "SELF" in l or "dev_bootstrap.sh" in l)
        self.assertIn("bash '$SELF'", line)
        # $SELF, göreli yoldan türetilir → kök dizinden de geçerli kalır.
        self.assertIn('_calisma/dev_bootstrap.sh"',
                      next(l for l in text.splitlines() if l.startswith("SELF=")))
        self.assertEqual(gate.RECOVERY, "bash _calisma/dev_bootstrap.sh")

    def test_unit_name_stays_the_first_token(self):
        """Kapı `UNIT_RE = ^CHECK FAIL:\\s*(\\S+)` ile İLK token'ı, yani unit
        adını, okur. Etiket gerçek yolu da basmaya başladı (2026-09-29);
        yol İKİNCİ konuma (parantez içi) kaydırıldı, çünkü birinci olsaydı
        kapı `pptx (_calisma/pptx)` diye okur ve kullanıcıya olmayan bir
        unit adı raporlardı."""
        self.assertEqual(gate.UNIT_RE.pattern, r"^CHECK FAIL:\s*(\S+)")
        sample = "CHECK FAIL: pptx (_calisma/pptx) eksik veya paritesiz"
        m = gate.UNIT_RE.search(sample)
        self.assertIsNotNone(m, "imza artik CHECK FAIL satirini okumuyor")
        self.assertEqual(m.group(1), "pptx")

    def test_units_are_not_duplicated_in_the_gate(self):
        """Unit listesi TEK kaynakta (bootstrap). Kapıda bir unit adı
        geçerse iki doğruluk kaynağı doğar ve sapma sessiz kalır.

        Adlar elle yazılmaz — `_calisma/bootstrap_units.conf`'tan okunur.
        Elle yazılan bir liste, envanterden bir ad silindiğinde kapının o
        adı artık denetlememesi anlamına gelirdi: kapı sessizce daha az
        denetlerdi."""
        source = code_only(CIKTI / "check_bootstrap_toolchain.py")
        conf = ROOT / "_calisma" / "bootstrap_units.conf"
        self.assertTrue(conf.is_file(), f"envanter yok: {conf}")
        units = [ln.split()[0] for ln in conf.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
        self.assertTrue(units, "envanter boş")
        for unit in units:
            self.assertIsNone(
                re.search(rf"CHECK FAIL:\s*{re.escape(unit)}\b", source),
                f"kapı unit listesini kopyalamış: {unit}",
            )


if __name__ == "__main__":
    unittest.main()
