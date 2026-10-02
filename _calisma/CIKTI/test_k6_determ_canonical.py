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
import json
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
HOOK = CIKTI / "verify_delivery_hook.py"
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"
REPACK = ROOT / "_calisma" / "repack_delivery.py"
SHIPPED_MANIFEST = (ROOT / "_calisma" / "V5_ICERIK"
                    / "TESLIM_V5_FINAL_2026-08-17" / "stoic_hume_package"
                    / "Stoic_Hume_Formal_Section_2026-08-17" / "MANIFEST.txt")
TREND = ROOT / "docs" / "determinism_trend" / "determinism_trend.jsonl"
PIPELINE = ROOT / "docs" / "TEX_RENDER_PIPELINE.md"
SLIDES = CIKTI / "render_z3_slides.py"

# §4 defterinin önceki satırları — “üzerine yazma” protokolünü ölçmek için
# (test_id_residual_acceptance_doc.py ile aynı değerler, tek kaynak değil:
# burada satır KAYBI'nı yakalamak için gerekiyor).
TECTONIC_SINGLE = ("ad8fca69d4e4a2e1d67e497c8a7449f22"
                   "c8564f5e9b3790d0b6f85d90d318e1b")
PDFTEX_SINGLE = ("a75c340911801273b38be6ffb51a3482"
                 "0764b8f812d528dd2705d64117f1aa00")
PDFTEX_3PASS = ("544516b0d9d2f4c12b05b512b79b31ad"
                "238e82d3ca3aff81166a6bac1914f597")
DELIVERY_CANONICAL = ("d4f67e39fd0ef77e8f294ca2195bb1fc"
                      "784716234d0675ab88a4fd8695263a6a")

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


class TestStrictDeterminismIsWired(unittest.TestCase):
    """F) Uygulanan çekirdek KAPILARA BAĞLANMIŞ olmalı.

    Ölçülen boşluk: `verify_delivery.py` K6-DETERM'i kanonik hash'e
    bağlamış ve strict'i varsayılan açmış (2026-10-01), ama BAĞLAYAN
    yüzeyler sözleşmeyi ilan etmiyordu:
      - pre-commit `verify_delivery_hook.py` kapıyı `--strict-determinism`
        OLMADAN koşuyordu ve fail-closed DEPS listesinde ne kanonik
        çekirdek (`pdf_id_canonical.py`) ne de kabul defteri vardı →
        hook, commit'lenenden farklı bir çekirdek/defter doğrulayabilirdi
        (DEPS'in var oluş nedeni tam olarak bu).
      - `.github/workflows/verify.yml` hiçbir yerde `--strict-determinism`
        demiyordu → sözleşme yalnız bir varsayılana dayanıyordu; bir
        varsayılan çevrildiğinde kapı sessizce kapanırdı.
    """

    def test_precommit_hook_runs_the_gate_with_strict_determinism(self):
        # Davranışsal: hook'un gerçekten ne koştuğunu ölç, kaynak
        # metnine bakma. subprocess.run geçici olarak yakalanır (kapı
        # koşulmaz), DEPS ön-kontrolü boşaltılır (ağaç durumundan bağımsız).
        from unittest import mock

        hook = load_module("verify_delivery_hook")
        seen = {}

        class _Done:
            returncode = 0

        def fake_run(argv, *a, **kw):
            seen["argv"] = list(argv)
            return _Done()

        with mock.patch.object(hook.subprocess, "run", fake_run), \
                mock.patch.object(hook, "unstaged_deps", lambda: {}):
            rc = hook.main([])

        self.assertEqual(rc, 0, "kapı çıkış kodu korunmali")
        argv = seen.get("argv") or []
        self.assertTrue(argv, "hook kapıyı hiç koşmadı")
        self.assertTrue(any(a.endswith("verify_delivery.py") for a in argv),
                        "argv'da verify_delivery.py yok: %s" % (argv,))
        self.assertIn("--strict-determinism", argv,
                      "pre-commit kapısı strict'i açıkça ilan etmeli; "
                      "varsayılana güvenmek, varsayılan çevrilirse "
                      "sessizce kapanır")

    def test_hook_deps_cover_canonical_core_and_ledger(self):
        hook = load_module("verify_delivery_hook")
        deps = hook.DEPS
        self.assertTrue(any(d.endswith("pdf_id_canonical.py") for d in deps),
                        "kanonik çekirdek DEPS'te olmalı: strict karşılaştırması "
                        "bu modülü kullanıyor")
        self.assertTrue(
            any(d.endswith("ID_RESIDUAL_ACCEPTANCE.md") for d in deps),
            "kabul defteri DEPS'te olmalı: referansı O dosya taşıyor")

    def test_hook_deps_ledger_is_the_file_the_gate_actually_reads(self):
        # Yalnız "defter DEPS'te" yetmez: kapının okuduĞU dosya ile
        # DEPS'in koruduğu dosya aynı olmalı. Ayrışırsa DEPS'te başka bir
        # yol durur, hook yanlış dosyanın temizliğini denetler ve gerçek
        # defterin stage'lenmemiş olması sessizce geçer.
        vd = load_module("verify_delivery")
        hook = load_module("verify_delivery_hook")
        reads = os.path.relpath(
            os.path.realpath(vd.PDF_CANONICAL_LEDGER), str(ROOT))
        self.assertIn(reads, hook.DEPS,
                      "kapının okuduğu defter DEPS listesinde aynı yolla "
                      "bulunmalı (ölçülen: %s)" % reads)

    def test_ci_declares_strict_determinism_on_the_full_gate(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        # `--full` geçen satırdan başlayıp backslash ile devam eden tüm
        # komut bloğunu birleştir: bayrak bir sonraki satıra da kayabilir.
        lines = text.splitlines()
        start = next((i for i, ln in enumerate(lines)
                      if "verify_delivery.py" in ln and "--full" in ln
                      and not ln.lstrip().startswith("#")), None)
        self.assertIsNotNone(start, "CI'da --full kapı adımı bulunamadı")
        block = [lines[start]]
        for ln in lines[start + 1:]:
            if not block[-1].rstrip().endswith("\\"):
                break
            block.append(ln)
        command = "\n".join(block)
        self.assertIn("--strict-determinism", command,
                      "CI --full adımı strict'i ilan etmeli")
        self.assertNotIn("--no-strict-determinism", text,
                         "CI kapatma bayrağını kullanmamalı (teşhis bayrağı)")

    def test_repack_generator_corrects_the_refuted_tectonic_claim(self):
        # Bayat yorumun KAYDI tarihsel kayıt olarak korunur (V5k metni
        # silinmez — teslim tarihçesi yeniden yazılmaz), ama ÜRETİCİ onu
        # çürüten yeni bir kayıt yayımlar ve bu kayıt DAHA SONRA gelir:
        # okuyucu en son satırı güncel sözleşme olarak görür.
        src = REPACK.read_text(encoding="utf-8")
        self.assertIn("must not be enabled", src,
                      "V5k tarihsel kaydı korunmalı")
        self.assertIn("# V5n", src,
                      "üretici ölçümle çürütülmüş gerekçeyi düzelten kaydı "
                      "yayımlamalı")
        self.assertGreater(src.index("# V5n"), src.index("must not be enabled"),
                           "düzeltme kaydı, çürüttüğü kayıttan SONRA "
                           "gelmeli (yoksa en son okunan yanlış olur)")

    def test_shipped_manifest_debt_cannot_stay_silent(self):
        # Gemideki MANIFEST.txt V5k metnini taşır ve taşımaya devam eder
        # (düzeltme bir sonraki repack'ta sevk edilir — teslim hash'i
        # bugün değişmez). Bu BİR BORÇTUR; defterde yazmıyorsa kimse
        # göremez, yani sessiz kalırsa kapı fail-closed ihlali olur.
        if not SHIPPED_MANIFEST.is_file():
            self.skipTest("gemideki MANIFEST yok — SKIP")
        shipped = SHIPPED_MANIFEST.read_text(encoding="utf-8")
        if "must not be enabled" not in shipped:
            self.skipTest("gemideki MANIFEST bayat metni taşımıyor — borç yok")
        text = LEDGER.read_text(encoding="utf-8")
        self.assertIn("MANIFEST.txt", text,
                      "gemideki MANIFEST'in bayat yorumu defterde kayıtlı "
                      "olmalı (sessiz borç olmasın)")
        self.assertIn("V5k", text,
                      "borç kaydı, çürütülen kaydı (V5k) adıyla belirtilmeli")


class TestCiLinuxLedgerRow(unittest.TestCase):
    """G) CI-linux bağlamı defterde kendi satırıyla durmalı (protokol).

    Rapurun kendi protokolü (§4): “Yeni bağlam (CI, font paketi) → **yeni
    satır**; eskisinin üzerine asla yazma.” CI-linux tam olarak yeni bir
    bağlam: aynı kaynak, aynı SDE, ama farklı TeXLive/font paketi → farklı
    kanonik hash. O yüzden satır 3'ün (darwin) üzerine yazılmaz, AYRI satır
    alır.

    Satırın değeri SABİT bir metin değil: `docs/determinism_trend/
    determinism_trend.jsonl` içindeki determinism-trend CI kayıtlarından
    gelir. Buradaki testler satırı o kayda bağlar — yani “defterde yazılı”
    ile “CI'da ölçülmüş” ayrışırsa kapı kırmızıya döner.
    """

    def _platform_canonicals(self, platform):
        out = []
        for line in TREND.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            h = rec.get("texlive_canonical_sha256")
            if rec.get("platform") == platform and h:
                out.append((rec, h))
        return out

    def _ledger_data_rows(self):
        """§4 defter tablosunun veri satırları (başlık + ayraç hariç).

        Bölüm hedeflenir: belgede §2'de de bir tablo var, ilk `|` satırını
        yakalamak yanlış tabloyu getirirdi.
        """
        lines = LEDGER.read_text(encoding="utf-8").splitlines()
        start = None
        for i, line in enumerate(lines):
            if line.startswith("## 4."):
                start = i + 1
                break
        self.assertIsNotNone(start, "§4 defter bölümü bulunamadı")
        rows, header = [], None
        for line in lines[start:]:
            s = line.strip()
            if not s.startswith("|"):
                if rows:
                    break
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells if c):
                continue
            if header is None:
                header = cells
                continue
            rows.append(cells)
        return header, rows

    def _canonical_column(self):
        header, _ = self._ledger_data_rows()
        self.assertIsNotNone(header, "§4 tablosu bulunamadı")
        idx = [i for i, c in enumerate(header) if "kanonik" in c.lower()]
        self.assertTrue(idx, "defterde 'Kanonik' sütunu yok")
        return idx[0]

    def test_ci_linux_hash_is_stable_across_independent_ci_runs(self):
        recs = self._platform_canonicals("linux")
        if not recs:
            self.skipTest("trend kaydında linux ölçümü yok — SKIP")
        distinct = {h for _, h in recs}
        self.assertEqual(len(distinct), 1,
                         "CI-linux kanonik hash koşumlar arasında DEĞİŞMEMELİ: "
                         "%s" % sorted(distinct))
        self.assertGreaterEqual(len(recs), 2,
                                "tek koşum determinizm kanıtı değildir")
        for rec, _h in recs:
            self.assertEqual(rec.get("gate"), "PASS",
                             "kaydedilen CI koşumu PASS olmalı")

    def test_ledger_row_equals_the_measured_ci_hash(self):
        recs = self._platform_canonicals("linux")
        if not recs:
            self.skipTest("trend kaydında linux ölçümü yok — SKIP")
        measured = sorted({h for _, h in recs})[0]
        col = self._canonical_column()
        found = [cells for cells in self._ledger_data_rows()[1]
                 if col < len(cells) and measured in cells[col]]
        self.assertTrue(found,
                        "CI-linux kanonik hash'i (%s…) defterde kendi "
                        "satırıyla olmalı" % measured[:12])

    def test_ci_linux_row_is_a_full_hash_accepted_by_the_parser(self):
        # Protokol: kısaltılmış önek kabul edilmez. Satır gerçekten
        # `ledger_canonical_hashes` tarafından okunabilmeli (yani “Kanonik”
        # sütununda TAM 64-hex olmalı) — aksi hâlde `make accept` bu
        # bağlamı hiçbir zaman kabul edemez.
        recs = self._platform_canonicals("linux")
        if not recs:
            self.skipTest("trend kaydında linux ölçümü yok — SKIP")
        measured = sorted({h for _, h in recs})[0]
        accepted = load_module("pdf_id_canonical").ledger_canonical_hashes(
            LEDGER.read_text(encoding="utf-8"))
        self.assertIn(measured, accepted,
                      "CI-linux hash'i tam 64-hex olarak kabul edilmeli")

    def test_ci_linux_row_is_appended_not_an_overwrite(self):
        # “Eskisinin üzerine asla yazma”: önceki satırların kanonik
        # hash'leri aynen durmalı, CI-linux ayrı bir satır olmalı.
        recs = self._platform_canonicals("linux")
        if not recs:
            self.skipTest("trend kaydında linux ölçümü yok — SKIP")
        measured = sorted({h for _, h in recs})[0]
        col = self._canonical_column()
        rows = self._ledger_data_rows()[1]
        hashes = []
        for cells in rows:
            if col < len(cells):
                hashes.extend(re.findall(r"\b[0-9a-f]{64}\b", cells[col]))
        for previous in (TECTONIC_SINGLE, PDFTEX_SINGLE, PDFTEX_3PASS,
                         DELIVERY_CANONICAL):
            self.assertIn(previous, hashes,
                          "önceki satır (%s…) silinmiş/üzerine yazılmış "
                          "olamaz — protokol yeni satır ister"
                          % previous[:12])
        self.assertEqual(hashes.count(measured), 1,
                         "CI-linux hash'i tam bir kez ve ayrı satırda "
                         "bulunmalı")

    def test_ci_linux_context_is_distinct_from_darwin(self):
        # Satır 3 (darwin/Homebrew) ile CI-linux (ubuntu-latest/apt) farklı
        # paket seti → pdfTeX kanonik hash'i farklı olmalı. Aynı olsaydı ya
        # ölçüm hatası ya da kopyala-yapıştır hatası olurdu; protokol de
        # çapraz-platform eşitliği beklemiyor (§3 kural 3).
        linux = self._platform_canonicals("linux")
        darwin = self._platform_canonicals("darwin")
        if not linux or not darwin:
            self.skipTest("iki platform da ölçülmemiş — SKIP")
        lh = sorted({h for _, h in linux})[0]
        dh = sorted({h for _, h in darwin})[0]
        self.assertNotEqual(lh, dh,
                            "CI-linux ve darwin pdfTeX kanonik hash'i farklı "
                            "olmalı (farklı font/TeXLive paketi)")

    def test_tectonic_canonical_is_platform_stable(self):
        # Ölçülen asimetri: ayrışan bacak pdfTeX'tir, tectonic değil —
        # tectonic 0.17.0 çıktısı platformdan bağımsız. Satır 1 zaten tek
        # bir tectonic satırı taşır; linux de aynı hash'i veriyorsa
        # platform başına ikinci tectonic satırı AÇILMAMALI (yeni bağlam
        # yok, ölçüm aynı).
        linux = self._platform_canonicals("linux")
        darwin = self._platform_canonicals("darwin")
        if not linux or not darwin:
            self.skipTest("iki platform da ölçülmemiş — SKIP")
        lt = {r.get("tectonic_canonical_sha256") for r, _h in linux}
        dt = {r.get("tectonic_canonical_sha256") for r, _h in darwin}
        self.assertEqual(lt, dt,
                         "tectonic kanonik hash'i platformlar arası "
                         "değişmemeli (ölçümde öyle)")
        self.assertEqual(lt, {TECTONIC_SINGLE},
                         "tectonic kanonik hash'i satır 1 ile aynı olmalı")

    def test_ci_linux_row_carries_platform_and_sde_context(self):
        # Protokol: “defter satırları SDE bağlamını taşır”. Satır
        # platformu ve SDE'yi açıkça belirtmeli — kanonik hash SDE'ye
        # bağlıdır, bağlam yazılmazsa satır ileride yanlış okunur.
        recs = self._platform_canonicals("linux")
        if not recs:
            self.skipTest("trend kaydında linux ölçümü yok — SKIP")
        measured = sorted({h for _, h in recs})[0]
        col = self._canonical_column()
        rows = [cells for cells in self._ledger_data_rows()[1]
                if col < len(cells) and measured in cells[col]]
        joined = " ".join(rows[0])
        self.assertRegex(joined, r"linux|ubuntu",
                         "satır platformu (linux/ubuntu) belirtmeli")
        self.assertTrue(any(ch.isdigit() for ch in joined),
                        "satır SDE/geçiş bağlamını bir sayıyla taşımalı")

    def test_ci_linux_row_has_a_rationale_in_the_report(self):
        # “Satır 5 neden ayrı?” geleneği: ayrı satırın gerekçesi yazılı
        # olmalı, yoksa protokol uygulanmış görünür ama anlaşılmaz.
        text = LEDGER.read_text(encoding="utf-8")
        recs = self._platform_canonicals("linux")
        if not recs:
            self.skipTest("trend kaydında linux ölçümü yok — SKIP")
        measured = sorted({h for _, h in recs})[0]
        self.assertIn(measured, text)
        self.assertRegex(text, r"(?i)CI[- ]linux",
                         "CI-linux bağlamı raporda adıyla anılmalı")
        self.assertIn("determinism-trend", text,
                      "satırın ölçüm kaynağı (determinism-trend CI) "
                      "adıyla yazılmalı")


class TestFaz5DocumentationTruth(unittest.TestCase):
    """H) Dokümantasyon ÖLÇÜLMÜŞ durumu anlatmalı (Faz 5 kapanışı).

    Ölçülen boşluk: `docs/TEX_RENDER_PIPELINE.md` ve
    `skills/reproducible-pdf-build/SKILL.md` TeXLive'nin **yok** olduğu bir
    çağın anlatısını taşıyordu. Oysa bugün (2026-10-02) ölçülen durum:
      - TeXLive kurulu (Homebrew TeX Live 2026) ve iki motor da ölçülmüş,
      - `render_z3_slides.py` motoru `pdflatex → latex → tectonic` sırasıyla
        seçiyor; bu makinede `find_tex_engine()` = **pdflatex** (tectonic
        değil), PNG yolu `convert` (pdftoppm değil),
      - tüm kanonik hash'ler kabul defterinde.
    Belge kodu ve ölçümü anlatmıyorsa okuyucu yanlış pipeline'ı kopyalar.
    """

    def test_pipeline_doc_carries_the_measured_canonical_hashes(self):
        text = PIPELINE.read_text(encoding="utf-8")
        for h, label in ((TECTONIC_SINGLE, "tectonic"),
                         (PDFTEX_SINGLE, "pdfTeX tek-geçiş (darwin)"),
                         (PDFTEX_3PASS, "pdfTeX 3-geçiş (darwin)")):
            self.assertIn(h, text,
                          "%s kanonik hash'i belgede olmalı (ölçülmüş veri)"
                          % label)
        recs = [json.loads(l) for l in TREND.read_text(
            encoding="utf-8").splitlines() if l.strip()]
        ci = {r.get("texlive_canonical_sha256") for r in recs
              if r.get("platform") == "linux"}
        for h in ci:
            self.assertIn(h, text,
                          "CI-linux kanonik hash'i de belgede olmalı")

    def test_pipeline_doc_does_not_claim_texlive_is_absent(self):
        text = PIPELINE.read_text(encoding="utf-8")
        for stale in ("TeXLive bağımlılığı olmayan", "TeXLive'siz, doğrulanmış"):
            self.assertNotIn(stale, text,
                             "açılış tezi artık doğru değil (TeXLive kurulu "
                             "ve ölçüldü): %r" % stale)

    def test_pipeline_doc_engine_order_matches_the_renderer(self):
        src = SLIDES.read_text(encoding="utf-8")
        m = re.search(r"def find_tex_engine\(\).*?for cand in \(([^)]*)\):",
                      src, re.S)
        self.assertIsNotNone(m, "find_tex_engine aday listesi bulunamadı")
        order = [c.strip().strip("\"'") for c in m.group(1).split(",")]
        self.assertEqual(order, ["pdflatex", "latex", "tectonic"],
                         "motor aday sırası değişti — belgeyi de güncelle")
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("`pdflatex` → `latex` → `tectonic`", text,
                      "belge motor çözümleme sırasını kodla aynı yazmalı")

    def test_pipeline_doc_names_the_resolved_engine_and_png_path(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?i)find_tex_engine\(\)",
                         "belge hangi motorun SEÇİLDİĞİNİ ölçümle yazmalı "
                         "(tahmin değil)")
        self.assertIn("pdflatex", text)

    def test_pipeline_doc_links_the_acceptance_ledger(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("ID_RESIDUAL_ACCEPTANCE", text,
                      "belge kanonik hash'lerin tek kaynağına bağlanmalı")

    def test_skill_marks_the_migration_completed_with_a_reference(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?i)migration[^\n]{0,40}completed"
                              r"|completed[^\n]{0,40}migration",
                         "SKILL.md göçü 'future' olarak değil tamamlanmış "
                         "olarak işaretlemeli")
        self.assertIn("ID_RESIDUAL_ACCEPTANCE", text,
                      "SKILL.md /ID kabul raporuna referans vermeli")

    def test_skill_no_longer_teaches_tectonic_as_nondeterministic(self):
        # Ölçümle çürütülen alan dersi: tectonic 0.17.0 bu ölçümde byte-KARARLI
        # (ham = kanonik, iki platformda aynı). Derleyici düzeyindeki
        # kararsızlık pdfTeX'in rastgele trailer /ID'idir. SKILL.md bunu
        # "ölçümle çürütüldü" diye işaretlemeli.
        text = SKILL.read_text(encoding="utf-8")
        self.assertNotIn("is NOT byte-deterministic: consecutive builds",
                         text,
                         "ölçümle çürütülmüş iddia olduğu gibi kalmamalı")
        self.assertIn("tectonic", text)
        self.assertRegex(text, r"(?i)(çürüt|superseded|ölçümle)",
                         "SKILL.md çürütmeyi açıkça işaretlemeli")


if __name__ == "__main__":
    unittest.main()
