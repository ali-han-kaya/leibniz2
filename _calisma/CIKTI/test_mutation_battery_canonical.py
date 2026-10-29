#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_mutation_battery_canonical.py — `id_canonical` çekirdeği + strict wiring
için KALICI mutasyon bataryası.

Neden
-----
`/ID`-kanonik determinizm zincirinin dört yüzeyi var:

  1. **Defter bağı** — K6-DETERM yalnız kabul defterinin "Kanonik (referans)"
     sütununu referans alır (`pdf_id_canonical.ledger_canonical_hashes`), hash
     defterde yoksa P1 (fail-closed).
  2. **Sidecar eşliği** — donmuş kaydın `# canonical:` satırı ile defter
     satırı aynı hash'i söylemek zorunda (`id_canonical.sidecar_canonical` +
     `check_id_residual_doc_sync.check`).
  3. **Fail-closed yollar** — defter yok/boş/okunamaz ya da hüküm kapalıysa
     kapı yeşile dönmez; belirsizlik raporlanır.
  4. **Hook bayrağı** — strict VARSAYILAN AÇIK; tek çıkış `--no-strict-determinism`
     ve hiçbir hook/CI adımı onu geçmemeli.

Bu yüzeylerin her biri normalde yeşil koşar; asıl soru, bekçi zayıflatılırsa
süitin hâlâ kırmızı düşüp düşmediği. Bu dosya her yüzeyin keeper'ını
(`*_violations`) saf fonksiyon olarak tutar ve GERÇEK dosyanın geçici
kopyasına `mutation_guard.apply_mutations` ile bilinçli zayıflatma uygular:
mutasyon KAÇARSA test kırmızı olur. Mutasyon metni kaynaktan kayarsa
`MutationNotApplicable` (bayat kanıt) yükselir — sessiz no-op yok
(docs/adr/NEGATIVE_TEST_CONTRACTS.md §5 kural 3, test_fail_closed_gates.py
deseniyle aynı).

Mutasyon → yakalayan keeper eşlemesi:
  * defter sütunu "Ham"a kaydırıldı        → canonical_ledger_violations
  * 64-hex kuralı {8,64}'e gevşetildi      → canonical_ledger_violations
  * /ID nötrlemesi söküldü                 → canonical_hash_violations
  * `# canonical:` yerine `# raw:` okundu  → sidecar_parity_violations
  * env defter önceliği silindi            → ledger_resolution_violations
  * okuma hatası "başarı" sayıldı          → ledger_error_reporting_violations
  * K6 karşılaştırması `if False`          → gate_violations
  * boş-defter dalı söküldü                → gate_violations
  * hüküm `if True` (hep sessiz)           → gate_violations
  * strict varsayılanı False'a çevrildi    → determinism_wiring_violations
  * hook'a `--no-strict-determinism` eklendi→ determinism_wiring_violations
  * defter↔kayıt kanonik karşılaştırması    → doc_sync_violations
  * "kayıtta var, defterde yok" dalı silindi→ doc_sync_violations
  * ham hash karşılaştırması söküldü        → doc_sync_violations

stdlib-only, OFFLINE. Gerçek repo dosyalarına yazmaz (yalnız temp kopya).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import mutation_guard as mg  # noqa: E402  (HERE sys.path'e eklendikten sonra)
import check_id_residual_doc_sync as docsync  # noqa: E402
import id_canonical  # noqa: E402
import pdf_id_canonical  # noqa: E402
import verify_delivery  # noqa: E402

VERIFY = HERE / "verify_delivery.py"
ID_CANON = HERE / "id_canonical.py"
PDF_CANON = HERE / "pdf_id_canonical.py"
DOC_SYNC = HERE / "check_id_residual_doc_sync.py"
PRECOMMIT = ROOT / ".pre-commit-config.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"
REAL_LEDGER = ROOT / "docs" / "ID_RESIDUAL_ACCEPTANCE.md"
PDF_NAME = "ingiliz_empirizmi_v3.pdf"

RAW = "f" * 64
OTHER = "0" * 64


# ---------------------------------------------------------------------------
# Fixtures — sentetik PDF / defter / sidecar (repo dosyalarına dokunmaz)
# ---------------------------------------------------------------------------
def pdf_bytes(id_a=b"1" * 32, id_b=b"2" * 32):
    """Minimal PDF: yalnız trailer `/ID` çifti kanonik yüzeyi taşır."""
    return (b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
            b"trailer\n<< /Size 2 /ID [<" + id_a + b"><" + id_b + b">] >>\n"
            b"%%EOF\n")


def ledger_doc(canonical, raw=RAW):
    """`pdf_id_canonical` defter ayrıştırıcısının beklediği tablo."""
    return ("| Motor | Ham (bilgi) | Kanonik (referans) |\n"
            "|---|---|---|\n"
            "| test | `%s` | `%s` |\n" % (raw, canonical))


DOC_ROW = ("| Dönem | Ham PDF (bilgi) | Metadata-stripped | Kanonik (referans) |\n"
           "|---|---|---|---|\n"
           "| tectonic-era teslim (V5l; mevcut) | `%s` | `%s` | %s |\n")


def sidecar_text(canonical=None, raw=RAW, stripped=OTHER):
    text = ("%s  %s.metadata\n# raw: %s  %s\n"
            % (stripped, PDF_NAME, raw, PDF_NAME))
    if canonical:
        text += "# canonical: %s  %s\n" % (canonical, PDF_NAME)
    return text


class Fixtures:
    """Temp dizinde PDF + defter kopyaları; kanonik hash ölçülerek üretilir."""

    def __init__(self, tmpdir):
        self.dir = Path(tmpdir)
        self.pdf = self.dir / PDF_NAME
        self.pdf.write_bytes(pdf_bytes())
        self.canonical, found = pdf_id_canonical.canonical_sha256_bytes(
            self.pdf.read_bytes())
        assert found, "sentetik PDF /ID taşımalı"
        self.pdf_other_id = self.dir / "other-id.pdf"
        self.pdf_other_id.write_bytes(pdf_bytes(b"3" * 32, b"4" * 32))

        self.ledger_ok = self._write("ledger-ok.md", ledger_doc(self.canonical))
        self.ledger_absent = self._write("ledger-absent.md", ledger_doc(OTHER))
        self.ledger_empty = self._write(
            "ledger-empty.md", "| Motor | Kanonik (referans) |\n|---|---|\n")
        self.ledger_missing = self.dir / "ledger-yok.md"
        self.env_ledger = self._write("ledger-env.md", ledger_doc(OTHER))

        # check_id_residual_doc_sync fixtures (defter satırı ↔ donmuş kayıt).
        self.doc_ok = self._write(
            "doc-ok.md", DOC_ROW % (RAW, OTHER, "`%s`" % self.canonical))
        self.doc_bad_raw = self._write(
            "doc-bad-raw.md", DOC_ROW % ("a" * 64, OTHER,
                                         "`%s`" % self.canonical))
        self.doc_no_canon = self._write(
            "doc-no-canon.md", DOC_ROW % (RAW, OTHER, "—"))
        self.sidecar_ok = self._write(
            "sidecar-ok.sha256", sidecar_text(self.canonical))
        self.sidecar_bad_canon = self._write(
            "sidecar-bad.sha256", sidecar_text("b" * 64))
        self.sidecar_plain = self._write(
            "sidecar-plain.sha256", sidecar_text(None))
        self.sidecar_no_canon = self.dir / "sidecar-yok.sha256"

    def _write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# Keeper'lar: metin/modül → ihlal listesi ([] = bekçi yerinde)
# ---------------------------------------------------------------------------
def canonical_ledger_violations(mod, real_ledger_text):
    """Defter bağı: yalnız Kanonik sütunu, yalnız tam 64-hex kabul edilir."""
    out = []
    got = mod.ledger_canonical_hashes(ledger_doc("a" * 64))
    if got != {"a" * 64}:
        out.append("Kanonik sütunu yerine başka sütun okundu: %r" % sorted(got))
    real = mod.ledger_canonical_hashes(real_ledger_text)
    if not real:
        out.append("gerçek defterden kanonik hash okunamadı")
    if any(h.startswith("47681218") for h in real):
        out.append("kısaltılmış önek kabul edildi (yalnız tam 64-hex)")
    return out


def canonical_hash_violations(mod, fx):
    """Çekirdek normalizasyon: /ID dışında fark yoksa hash eşit olmalı."""
    out = []
    a = mod.canonical_pdf_sha256(str(fx.pdf))
    b = mod.canonical_pdf_sha256(str(fx.pdf_other_id))
    if not a or not b:
        out.append("kanonik hash okunamadı — yüzey ölçülemez")
    elif a != b:
        out.append("/ID nötrlenmiyor: aynı içerik farklı kanonik hash verdi")
    return out


def sidecar_parity_violations(mod, fx):
    """Sidecar eşliği: `# canonical:` satırı ham satırla karışmamalı."""
    out = []
    got = mod.sidecar_canonical(str(fx.sidecar_ok))
    if got != fx.canonical:
        out.append("sidecar canonical satırı yanlış okundu: %r" % got)
    if mod.sidecar_canonical(str(fx.sidecar_plain)) is not None:
        out.append("canonical satırı yokken değer uyduruldu")
    return out


def ledger_resolution_violations(mod, fx):
    """Defter çözümleme sırası: açık env yolu ilk kazanır."""
    out = []
    old = os.environ.get("ID_RESIDUAL_LEDGER")
    os.environ["ID_RESIDUAL_LEDGER"] = str(fx.env_ledger)
    try:
        tokens, err, src = mod.ledger_tokens()
    finally:
        if old is None:
            os.environ.pop("ID_RESIDUAL_LEDGER", None)
        else:
            os.environ["ID_RESIDUAL_LEDGER"] = old
    if str(src) != str(fx.env_ledger):
        out.append("ID_RESIDUAL_LEDGER yolu yok sayıldı (kaynak: %r)" % src)
    if err:
        out.append("defter okuma hatası: %s" % err)
    if not tokens:
        out.append("env defterinden hash okunamadı")
    return out


def ledger_error_reporting_violations(mod, fx):
    """Fail-closed: hiçbir aday okunamazsa hata metni döner, sessiz boş yok."""
    out = []
    tokens, err, src = mod.ledger_tokens(str(fx.dir / "yok-boyle-bir.md"))
    if tokens:
        out.append("okunamayan defterden hash uyduruldu")
    if src is not None:
        out.append("okunamayan defter kaynak olarak bildirildi")
    if not err:
        out.append("okuma hatası raporlanmadı (sessiz boş küme)")
    return out


def gate_violations(mod, fx):
    """K6-DETERM hükmü: kabul, ret ve fail-closed dalları."""
    out = []

    finding, ev = mod.k6_canonical_finding(
        str(fx.pdf), ledger_path=str(fx.ledger_ok))
    if finding is not None:
        out.append("defterde kayıtlı hash reddedildi: %s" % finding)
    if ev.get("canonical_accepted") is not True:
        out.append("kabul kanıtı işaretlenmedi")
    if ev.get("canonical_ledger_size") != 1:
        out.append("defter boyutu yanlış: %r" % ev.get("canonical_ledger_size"))

    finding, ev = mod.k6_canonical_finding(
        str(fx.pdf), ledger_path=str(fx.ledger_absent))
    if finding is None:
        out.append("defterde OLMAYAN hash kabul edildi (fail-open)")
    elif "defterinde yok" not in finding:
        out.append("ret mesajı çıkış yolunu göstermiyor: %s" % finding)
    if ev.get("canonical_accepted") is not False:
        out.append("ret kanıtı 'kabul' işaretlendi")

    finding, _ev = mod.k6_canonical_finding(
        str(fx.pdf), ledger_path=str(fx.ledger_empty))
    if finding is None:
        out.append("boş defter sessiz yeşil sayıldı")
    elif "okunamadı/boş" not in finding:
        out.append("boş defter 'kayıtsız hash' gibi raporlandı: %s" % finding)

    finding, _ev = mod.k6_canonical_finding(
        str(fx.pdf), ledger_path=str(fx.ledger_missing))
    if finding is None:
        out.append("defter dosyası yokken kapı yeşil")
    elif "okunamadı" not in finding:
        out.append("eksik defter raporlanmadı: %s" % finding)

    finding, ev = mod.k6_canonical_finding(
        str(fx.pdf), ledger_path=str(fx.ledger_absent), strict=False)
    if finding is not None:
        out.append("tanı modu (strict=False) hüküm üretti")
    if ev.get("canonical_accepted") is not False:
        out.append("tanı modunda 'kabul' işaretlendi")
    return out


def doc_sync_violations(mod, fx):
    """Defter satırı ↔ donmuş kayıt eşliği (ham + kanonik)."""
    out = []

    findings, notes, _ = mod.check(fx.doc_ok, fx.sidecar_ok, PDF_NAME)
    if findings:
        out.append("uyumlu defter+kayıt bulgu üretti: %r" % findings)
    if notes:
        out.append("uyumlu kayıtta NOT üretildi: %r" % notes)

    findings, _n, _ = mod.check(fx.doc_ok, fx.sidecar_bad_canon, PDF_NAME)
    if not any(f.get("kind") == "doc_value_mismatch"
               and f.get("column") == "canonical" for f in findings):
        out.append("kanonik hash uyuşmazlığı yakalanmadı")

    findings, _n, _ = mod.check(fx.doc_bad_raw, fx.sidecar_ok, PDF_NAME)
    if not any(f.get("kind") == "doc_value_mismatch"
               and f.get("column") == "raw" for f in findings):
        out.append("ham hash uyuşmazlığı yakalanmadı")

    findings, _n, _ = mod.check(fx.doc_no_canon, fx.sidecar_ok, PDF_NAME)
    if not any(f.get("kind") == "doc_hash_missing"
               and f.get("column") == "canonical" for f in findings):
        out.append("kayıtta kanonik var, defterde yok → bulgu yok")

    findings, _n, _ = mod.check(fx.doc_ok, fx.sidecar_no_canon, PDF_NAME)
    if not any(f.get("kind") in {"frozen_record_missing",
                                 "stripped_missing"} for f in findings):
        out.append("kayıt yokken fail-closed bulgu üretilmedi")
    return out


STRICT_ARG = ('    ap.add_argument("--strict-determinism", dest="strict_determinism",\n'
              '                    action="store_true", default=True,\n')
OPT_OUT_ARG = ('    ap.add_argument("--no-strict-determinism", '
               'dest="strict_determinism",\n')


def determinism_wiring_violations(vd_text, precommit_text, workflow_text):
    """Strict VARSAYILAN AÇIK olmalı; hook/CI opt-out bayrağını geçmemeli."""
    out = []
    if STRICT_ARG not in vd_text:
        out.append("--strict-determinism varsayılanı açık değil "
                   "(default=True bloğu bulunamadı)")
    if OPT_OUT_ARG not in vd_text:
        out.append("--no-strict-determinism adlı çıkış yolu yok")
    if "verify_delivery_hook.py --strict" not in precommit_text:
        out.append("verify-delivery hook'u verify_delivery_hook'a bağlı değil")
    for label, text in (("pre-commit", precommit_text),
                        ("verify.yml", workflow_text)):
        if "--no-strict-determinism" in text:
            out.append("%s strict hükmünü kapatıyor (--no-strict-determinism)"
                       % label)
    return out


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
class MutationBatteryBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="mut-canon-")
        cls.fx = Fixtures(cls._tmp.name)
        cls.real_ledger_text = REAL_LEDGER.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self._names = []

    def tearDown(self):
        for name in self._names:
            mg.unload(name)

    def _load(self, src, mutations):
        path = mg.mutated_copy(src, self.fx.dir, mutations)
        name = "mut_%s_%d" % (Path(src).stem, len(self._names))
        module = mg.load_copy(path, name)
        self._names.append(name)
        return module

    def assertCaught(self, keeper, *args):
        """Mutantta keeper KIRMIZI olmalı; yeşil kalırsa mutasyon kaçmıştır."""
        violations = keeper(*args)
        self.assertNotEqual(
            violations, [],
            "mutasyon kaçtı — keeper yeşil kaldı (kanıt değersiz)")


# ---------------------------------------------------------------------------
# 0) Kanıt boş değil: gerçek modüller keeper'ları geçer
# ---------------------------------------------------------------------------
class TestKeepersGreenOnRealSources(MutationBatteryBase):
    def test_coverage_keepers_are_not_vacuous(self):
        checks = {
            "canonical_ledger": canonical_ledger_violations(
                pdf_id_canonical, self.real_ledger_text),
            "canonical_hash": canonical_hash_violations(id_canonical, self.fx),
            "sidecar_parity": sidecar_parity_violations(
                id_canonical, self.fx),
            "ledger_resolution": ledger_resolution_violations(
                id_canonical, self.fx),
            "ledger_error": ledger_error_reporting_violations(
                id_canonical, self.fx),
            "gate": gate_violations(verify_delivery, self.fx),
            "doc_sync": doc_sync_violations(docsync, self.fx),
            "wiring": determinism_wiring_violations(
                VERIFY.read_text(encoding="utf-8"),
                PRECOMMIT.read_text(encoding="utf-8"),
                WORKFLOW.read_text(encoding="utf-8")),
        }
        for label, violations in checks.items():
            self.assertEqual(violations, [], "%s bekçisi yeşil değil" % label)


# ---------------------------------------------------------------------------
# 1) Defter bağı (pdf_id_canonical)
# ---------------------------------------------------------------------------
class TestLedgerBindingMutations(MutationBatteryBase):
    def test_column_slide_to_raw_is_caught(self):
        mod = self._load(PDF_CANON, [
            ('            if "kanonik" in cell.lower():\n',
             '            if "ham" in cell.lower():\n'),
        ])
        self.assertCaught(canonical_ledger_violations, mod,
                          self.real_ledger_text)

    def test_hash_width_loosened_is_caught(self):
        mod = self._load(PDF_CANON, [
            ('FULL_HASH_RE = re.compile(r"\\b[0-9a-f]{64}\\b")\n',
             'FULL_HASH_RE = re.compile(r"\\b[0-9a-f]{8,64}\\b")\n'),
        ])
        self.assertCaught(canonical_ledger_violations, mod,
                          self.real_ledger_text)

    def test_id_neutralisation_removed_is_caught(self):
        mod = self._load(ID_CANON, [
            ("        data = _ID_TRAILER_PATTERN.sub(_ID_TRAILER_NEUTRAL, data)\n",
             "        data = data  # MUTASYON: /ID nötrlenmiyor\n"),
        ])
        self.assertCaught(canonical_hash_violations, mod, self.fx)


# ---------------------------------------------------------------------------
# 2) Sidecar eşliği (id_canonical + doc sync)
# ---------------------------------------------------------------------------
class TestSidecarParityMutations(MutationBatteryBase):
    def test_sidecar_reader_returns_raw_is_caught(self):
        mod = self._load(ID_CANON, [
            ('                if line.startswith("# canonical:"):\n',
             '                if line.startswith("# raw:"):\n'),
        ])
        self.assertCaught(sidecar_parity_violations, mod, self.fx)

    def test_doc_sync_canonical_comparison_removed_is_caught(self):
        mod = self._load(DOC_SYNC, [
            ("            and doc_canonical != rec_canonical:\n",
             "            and False:  # MUTASYON\n"),
        ])
        self.assertCaught(doc_sync_violations, mod, self.fx)

    def test_doc_sync_missing_canonical_branch_removed_is_caught(self):
        mod = self._load(DOC_SYNC, [
            ("    elif rec_canonical is not None and doc_canonical is None:\n",
             "    elif False:  # MUTASYON\n"),
        ])
        self.assertCaught(doc_sync_violations, mod, self.fx)

    def test_doc_sync_raw_comparison_removed_is_caught(self):
        mod = self._load(DOC_SYNC, [
            ("and doc_value != rec_value:",
             "and False:  # MUTASYON"),
        ])
        self.assertCaught(doc_sync_violations, mod, self.fx)


# ---------------------------------------------------------------------------
# 3) Fail-closed yollar (defter çözümleme + K6 hükmü)
# ---------------------------------------------------------------------------
class TestFailClosedMutations(MutationBatteryBase):
    def test_env_ledger_precedence_removed_is_caught(self):
        mod = self._load(ID_CANON, [
            ("    env = os.environ.get(LEDGER_ENV)\n    if env:\n"
             "        out.append(env)\n",
             "    env = os.environ.get(LEDGER_ENV)  # MUTASYON\n"),
        ])
        self.assertCaught(ledger_resolution_violations, mod, self.fx)

    def test_read_error_reported_as_success_is_caught(self):
        mod = self._load(ID_CANON, [
            ("        except OSError:\n            continue\n",
             '        except OSError:\n            return set(), "", cand\n'),
        ])
        self.assertCaught(ledger_error_reporting_violations, mod, self.fx)

    def test_gate_comparison_disabled_is_caught(self):
        mod = self._load(VERIFY, [
            ("    if canonical_h not in ledger:\n",
             "    if False:  # MUTASYON\n"),
        ])
        self.assertCaught(gate_violations, mod, self.fx)

    def test_empty_ledger_branch_removed_is_caught(self):
        mod = self._load(VERIFY, [
            ("    if not ledger:\n", "    if False:  # MUTASYON\n"),
        ])
        self.assertCaught(gate_violations, mod, self.fx)

    def test_gate_forced_silent_is_caught(self):
        mod = self._load(VERIFY, [
            ("    if not canonical_h or not strict:\n", "    if True:\n"),
        ])
        self.assertCaught(gate_violations, mod, self.fx)


# ---------------------------------------------------------------------------
# 4) Hook bayrağı (varsayılan + opt-out kablolaması)
# ---------------------------------------------------------------------------
class TestHookFlagMutations(MutationBatteryBase):
    def test_strict_default_flipped_is_caught(self):
        mod = self._load(VERIFY, [
            (STRICT_ARG,
             STRICT_ARG.replace("default=True", "default=False")),
        ])
        self.assertCaught(determinism_wiring_violations,
                          Path(mod.__file__).read_text(encoding="utf-8"),
                          PRECOMMIT.read_text(encoding="utf-8"),
                          WORKFLOW.read_text(encoding="utf-8"))

    def test_opt_out_flag_in_hook_is_caught(self):
        pre = PRECOMMIT.read_text(encoding="utf-8")
        entry = ("        entry: python3 _calisma/CIKTI/"
                 "verify_delivery_hook.py --strict\n")
        next_hook = "      - id: check-action-pins\n"
        start = pre.index(entry)
        end = pre.index(next_hook, start)
        old = pre[start:end]
        new = old.replace(entry, entry.rstrip("\n")
                          + " --no-strict-determinism\n")
        mutated = mg.apply_mutations(pre, [(old, new)])
        self.assertCaught(determinism_wiring_violations,
                          VERIFY.read_text(encoding="utf-8"),
                          mutated,
                          WORKFLOW.read_text(encoding="utf-8"))

    def test_opt_out_flag_in_ci_is_caught(self):
        wf = WORKFLOW.read_text(encoding="utf-8")
        old = ("python3 _calisma/CIKTI/verify_delivery.py "
               "--dir _calisma/CIKTI --full")
        mutated = mg.apply_mutations(
            wf, [(old, old + " --no-strict-determinism")])
        self.assertCaught(determinism_wiring_violations,
                          VERIFY.read_text(encoding="utf-8"),
                          PRECOMMIT.read_text(encoding="utf-8"),
                          mutated)


# ---------------------------------------------------------------------------
# 5) Kanıt tazeliği: kaynaktan kaymış mutasyon sessiz no-op olamaz
# ---------------------------------------------------------------------------
class TestMutationFreshness(unittest.TestCase):
    def test_stale_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="mut-stale-") as tmp:
            with self.assertRaises(mg.MutationNotApplicable):
                mg.mutated_copy(
                    PDF_CANON, tmp,
                    [("bu metin kaynakta yok", "yeni")])

    def test_ambiguous_mutation_is_rejected(self):
        # Aynı metin iki kez geçiyorsa hangi çağrının zayıflatıldığı belirsiz.
        with tempfile.TemporaryDirectory(prefix="mut-amb-") as tmp:
            with self.assertRaises(mg.MutationNotApplicable):
                mg.mutated_copy(
                    PDF_CANON, tmp,
                    [("import ", "import  ")])


if __name__ == "__main__":
    unittest.main()
