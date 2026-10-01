#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_k6_determ_canonical.py — Faz 4 sözleşmesi (K6-DETERM ↔ kabul defteri).

Ölçülen gerçekler (2026-10-01), bu testlerin neden var olduğu:
  1) `qpdf --remove-metadata` TEK girdide 3 koşumda 3 farklı hash üretti
     (2042ba8b…/7f9125d0…/c9b9890d…) → strict karşılaştırma stripped'a
     bağlanırsa kapı HER koşumda yanlış pozitif üretir.
  2) pdfTeX `SOURCE_DATE_EPOCH` ile /ID'yi sabitlemez; kalıntı trailer
     /ID çiftidir → kanonik görünüm (`/ID` nötrlü) kararlı hash verir.
  3) Teslim artefaktının kanonik hash'i `d4f67e39…`; defterdeki 4 ölçümün
     hiçbiriyle aynı değil → defter protokolü gereği YENİ satır (satır 5).

Sözleşmenin beş bacağı:
  A. Kanonik uygulama tek yerde (shell betiği de aynı modülü okur).
  B. K6-DETERM strict'i kanonik hash'e uygular, stripped'a UYGULAMAZ.
  C. Referans sabit değil: kabul defterinin "Kanonik" sütunundan okunur;
     kısaltılmış önek kabul edilmez.
  D. Strict varsayılan açık; kapatma bayrağı adı sabit.
  E. Defterdeki teslim satırı, depodaki gerçek PDF'in kanonik hash'idir
     (canlı ölçüm — sabit bir metin değil).

stdlib-only, OFFLINE. Python 3.9 uyumlu.
"""
import ast
import hashlib
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CIKTI = ROOT / "_calisma" / "CIKTI"
LEDGER = ROOT / "docs" / "ID_RESIDUAL_ACCEPTANCE.md"
SKILL = ROOT / "skills" / "reproducible-pdf-build" / "SKILL.md"
SHELL_SCRIPT = CIKTI / "texlive_determinism_test.sh"
VERIFY = CIKTI / "verify_delivery.py"
MODULE = CIKTI / "pdf_id_canonical.py"

PDF = (ROOT / "_calisma" / "V5_ICERIK" / "TESLIM_V5_FINAL_2026-08-17"
       / "stoic_hume_package" / "Stoic_Hume_Formal_Section_2026-08-17"
       / "ingiliz_empirizmi_v3.pdf")


def load_module(name):
    """CIKTI'yi sys.path'e ekleyip modülü içe aktarır (yan etkisiz)."""
    if str(CIKTI) not in sys.path:
        sys.path.insert(0, str(CIKTI))
    __import__(name)
    return sys.modules[name]


class TestCanonicalSingleImplementation(unittest.TestCase):
    """A) Kanonik hash'in tek uygulaması var."""

    def setUp(self):
        self.mod = load_module("pdf_id_canonical")

    def test_module_normalizes_id_pair(self):
        data = b"%PDF-1.7\n/ID [<aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa>"
        data += b"<bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb>] trailer\n"
        digest, found = self.mod.canonical_sha256_bytes(data)
        neutral = self.mod.ID_NEUTRAL
        self.assertTrue(found)
        self.assertEqual(digest, hashlib.sha256(
            b"%PDF-1.7\n" + neutral + b" trailer\n").hexdigest())

    def test_different_ids_collapse_to_same_canonical_hash(self):
        # /ID dışında bayt birebir aynı iki dosya → kanonik eşit.
        a = b"body\x00/ID [<" + b"1" * 32 + b"><" + b"2" * 32 + b">]"
        b = b"body\x00/ID [<" + b"3" * 32 + b"><" + b"4" * 32 + b">]"
        self.assertNotEqual(hashlib.sha256(a).hexdigest(),
                            hashlib.sha256(b).hexdigest())
        self.assertEqual(self.mod.canonical_sha256_bytes(a)[0],
                         self.mod.canonical_sha256_bytes(b)[0])

    def test_content_difference_is_never_hidden(self):
        # Fail-safe: /ID dışındaki fark kanonikte görünür kalır.
        a = b"page-one/ID [<" + b"1" * 32 + b"><" + b"1" * 32 + b">]"
        b = b"page-two/ID [<" + b"2" * 32 + b"><" + b"2" * 32 + b">]"
        self.assertNotEqual(self.mod.canonical_sha256_bytes(a)[0],
                            self.mod.canonical_sha256_bytes(b)[0])

    def test_missing_id_is_reported_not_silently_canonical(self):
        data = b"%PDF-1.7\nno trailer id here\n"
        digest, found = self.mod.canonical_sha256_bytes(data)
        self.assertFalse(found)
        # Desen tutmazsa kanonik = ham (hiçbir fark gizlenmez).
        self.assertEqual(digest, hashlib.sha256(data).hexdigest())

    def test_shell_script_delegates_to_the_module(self):
        text = SHELL_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("import pdf_id_canonical as c", text,
                      "shell betiği kanonik hash'i modülden okumalı")
        # Regex'in ikinci kopyası iki gerçeklik yaratır.
        body = text.split("canonical_sha() {", 1)[1].split("}", 1)[0]
        self.assertNotIn("re.compile", body,
                         "canonical_sha() içinde regex kopyası olmamalı")

    def test_shell_and_python_agree_on_the_shipped_pdf(self):
        if not PDF.is_file():
            self.skipTest("teslim PDF'i yok")
        py = load_module("pdf_id_canonical").canonical_sha256_path(str(PDF))[0]
        proc = subprocess.run(
            ["bash", "-c",
             "ROOT=%s; source /dev/stdin <<'EOS'\n" % ROOT +
             "canonical_sha() {\n"
             "  python3 - \"$1\" \"$ROOT/_calisma/CIKTI\" <<'PY'\n"
             "import sys\n"
             "sys.path.insert(0, sys.argv[2])\n"
             "import pdf_id_canonical as c\n"
             "print(c.canonical_sha256_path(sys.argv[1])[0])\n"
             "PY\n"
             "}\n"
             "EOS\n"
             "canonical_sha %s\n" % PDF],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), py,
                         "shell kanonik_sha ile modül aynı hash'i vermeli")


class TestStrictGateBindsToLedger(unittest.TestCase):
    """B/C/D) K6-DETERM'in strict yüzeyi ve referansı."""

    def setUp(self):
        self.mod = load_module("pdf_id_canonical")
        self.text = VERIFY.read_text(encoding="utf-8")

    def test_strict_applies_to_canonical_hash(self):
        self.assertIn("def k6_canonical_finding(", self.text)
        self.assertIn("canonical_h not in ledger", self.text,
                      "kanonik hash defterde yoksa P1 üretilmeli")
        self.assertIn('add("P1", "K6-DETERM"', self.text)

    def test_strict_is_never_applied_to_the_qpdf_stripped_hash(self):
        # Yanlış pozitif üreticinin strict'e girmesi en sessiz hatadır:
        # kapı her koşumda kırmızıya döner, insanlar da bayrağı kapatır.
        # Metin aramak kırılgan (drift hem atama hem koşulda geçer), bu
        # yüzden AST: stripped/drift dalının İÇİNDE K6-DETERM P1 add()
        # çağrısı olmamalı.
        src = VERIFY.read_text(encoding="utf-8")
        lines = src.splitlines()
        offenders = []
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.If) or not node.body:
                continue
            test_src = "\n".join(
                lines[node.lineno - 1:node.body[0].lineno - 1])
            if not re.search(r"drift|stripped", test_src):
                continue
            body_src = "\n".join(
                lines[node.body[0].lineno - 1:node.end_lineno])
            if '"K6-DETERM"' in body_src and 'add("P1"' in body_src:
                offenders.append(node.lineno)
        self.assertEqual(offenders, [],
                         "strict kararı stripped/drift dalına girmiş: %s"
                         % offenders)

    def test_ledger_column_is_the_only_accepted_source(self):
        text = LEDGER.read_text(encoding="utf-8")
        raw = load_module("pdf_id_canonical")
        everything = raw.ledger_hashes(text)
        canonical = raw.ledger_canonical_hashes(text)
        self.assertTrue(canonical)
        self.assertTrue(canonical.issubset(everything))
        # Ham (bilgi) sütunundaki teslim hash'i kabul kümesinde OLMAMALI.
        delivery_raw = "74b2cdbdb18fafbf5b3c87570c92f150" \
            "0e7580469bcf4295b09734116df0779f"
        self.assertIn(delivery_raw, everything)
        self.assertNotIn(delivery_raw, canonical,
                         "ham hash kabul referansı olamaz")

    def test_truncated_prefix_is_not_accepted(self):
        text = LEDGER.read_text(encoding="utf-8")
        canonical = load_module("pdf_id_canonical").ledger_canonical_hashes(text)
        self.assertIn("47681218", text, "defter donmuş öneki taşıyor")
        self.assertFalse(any(h.startswith("47681218") for h in canonical),
                         "kısaltılmış önek kabul edilmemeli")

    def test_strict_defaults_on_with_a_named_opt_out(self):
        self.assertIn('ap.add_argument("--no-strict-determinism"', self.text)
        self.assertIn('"--strict-determinism", dest="strict_determinism"',
                      self.text)
        self.assertIn("action=\"store_true\", default=True", self.text)

    def test_ledger_absence_is_fail_closed(self):
        self.assertIn("if not ledger:", self.text,
                      "defter boşsa strict P1 vermeli (sessiz yeşil olmaz)")

    # ---- DAVRANIŞ: metin aramak yerine kararı çalıştır --------------
    # İlk yazımda iki mutasyon testleri kaçırdı (M1: karşılaştırma
    # `if False:` yapılsa; M2: hash koda sabitlenip defter hiç
    # okunmasa). Metin grep'i ikisini de kaçırır — bu yüzden karar saf
    # bir fonksiyona çıkarıldı ve burada ÇALIŞTIRILIR.

    def _pdf(self):
        if not PDF.is_file():
            self.skipTest("teslim PDF'i yok")
        return str(PDF)

    def test_gate_fails_when_hash_is_absent_from_ledger(self):
        vd = load_module("verify_delivery")
        finding, evidence = vd.k6_canonical_finding(
            self._pdf(), ledger={"0" * 64})
        self.assertIsNotNone(finding, "defterde olmayan hash P1 vermeli")
        self.assertIn("defterinde yok", finding)
        self.assertIn("make -f docs/Makefile.texlive accept", finding,
                      "çıkış yolu (bilinçli satır) kullanıcıya gösterilmeli")
        self.assertFalse(evidence["canonical_accepted"])

    def test_gate_passes_when_hash_is_in_ledger(self):
        vd = load_module("verify_delivery")
        digest, _ = vd.canonical_pdf_hashes(self._pdf())
        finding, evidence = vd.k6_canonical_finding(
            self._pdf(), ledger={digest})
        self.assertIsNone(finding)
        self.assertTrue(evidence["canonical_accepted"])
        self.assertEqual(evidence["canonical_ledger_size"], 1)

    def test_gate_is_silent_only_when_strict_is_explicitly_off(self):
        vd = load_module("verify_delivery")
        finding, evidence = vd.k6_canonical_finding(
            self._pdf(), ledger={"0" * 64}, strict=False)
        self.assertIsNone(finding)
        self.assertFalse(evidence["canonical_accepted"],
                         "strict kapalıyken de kabul edilmiş sayılmamalı")

    def test_missing_ledger_file_is_fail_closed_not_silent(self):
        vd = load_module("verify_delivery")
        finding, _ = vd.k6_canonical_finding(
            self._pdf(), ledger_path=str(ROOT / "docs" / "yok-boyle-bir.md"))
        self.assertIsNotNone(finding, "defter dosyası yoksa kapı P1 vermeli")
        self.assertIn("okunamadı", finding)

    def test_ledger_is_read_from_the_given_path(self):
        # Hash koda sabitlenirse (M2) bu test kırılır: geçici defterin
        # içeriği kümeye yansımak zorunda.
        vd = load_module("verify_delivery")
        import tempfile

        marker = "a1b2c3d4" + "0" * 56
        doc = ("| Motor | Kanonik (referans) |\n|---|---|\n"
               "| test | `%s` |\n" % marker)
        with tempfile.NamedTemporaryFile("w", suffix=".md",
                                         delete=False, encoding="utf-8") as fh:
            fh.write(doc)
            tmp = fh.name
        try:
            self.assertEqual(vd.ledger_canonical_hashes(tmp), {marker})
        finally:
            os.unlink(tmp)


class TestDeliveryRowIsMeasuredNotTyped(unittest.TestCase):
    """E) Defter satırı = depodaki gerçek PDF'in kanonik hash'i."""

    def test_ledger_pins_the_shipped_pdf_canonical_hash(self):
        if not PDF.is_file():
            self.skipTest("teslim PDF'i yok")
        digest, found = load_module(
            "pdf_id_canonical").canonical_sha256_path(str(PDF))
        self.assertTrue(found, "teslim PDF'inde /ID bulunamadı")
        text = LEDGER.read_text(encoding="utf-8")
        self.assertIn(digest, text,
                      "defter teslim PDF'inin kanonik hash'ini pinlemeli")

    def test_gate_would_accept_the_shipped_pdf(self):
        if not PDF.is_file():
            self.skipTest("teslim PDF'i yok")
        vd = load_module("verify_delivery")
        digest, _ = vd.canonical_pdf_hashes(str(PDF))
        self.assertIn(digest, vd.ledger_canonical_hashes(),
                      "kapı teslim PDF'ini KABUL etmeli (strict yeşil)")

    def test_pdf_inside_the_delivery_zip_has_the_same_canonical_hash(self):
        # CI'da kapı ZIP'ten çıkarılan paketi okur, çalışma ağacındaki
        # kopyayı değil. İkisi bugün bayt birebir aynı; kanonik eşitlik
        # ise /ID kalıntısı yüzünden ayrışabilecek tek yüzey.
        import zipfile

        zp = CIKTI / "TESLIM_V5_FINAL_2026-08-17.zip"
        if not zp.is_file() or not PDF.is_file():
            self.skipTest("teslim zip'i veya PDF'i yok")
        mod = load_module("pdf_id_canonical")
        with zipfile.ZipFile(str(zp)) as zf:
            member = next((n for n in zf.namelist()
                           if n.endswith("ingiliz_empirizmi_v3.pdf")), None)
            self.assertIsNotNone(member, "zip içinde PDF yok")
            data = zf.read(member)
        zip_digest, zip_found = mod.canonical_sha256_bytes(data)
        tree_digest, _ = mod.canonical_sha256_path(str(PDF))
        self.assertTrue(zip_found)
        self.assertEqual(zip_digest, tree_digest,
                         "zip içi ve ağaç içi kanonik hash ayrışmamalı")


class TestPhase4DocumentationTruth(unittest.TestCase):
    """Dokümanlar ölçümle çelişmemeli."""

    def test_ledger_documents_the_qpdf_false_positive_measurement(self):
        text = LEDGER.read_text(encoding="utf-8")
        for token in ("2042ba8b", "7f9125d0", "c9b9890d"):
            self.assertIn(token, text,
                          "qpdf 3-koşum ölçümü defterde kayıtlı olmalı")

    def test_skill_no_longer_tells_operators_to_keep_strict_off(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertNotIn("should stay OFF", text)
        self.assertIn("--no-strict-determinism", text)

    def test_verify_source_has_no_stale_tectonic_nondeterminism_claim(self):
        text = VERIFY.read_text(encoding="utf-8")
        self.assertNotIn("tectonic non-deterministic olduğundan", text,
                         "ölçümle çürütülmüş gerekçe kodda kalmamalı")


if __name__ == "__main__":
    unittest.main()
