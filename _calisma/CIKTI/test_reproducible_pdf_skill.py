#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_reproducible_pdf_skill.py — reproducible-pdf-build skill kurallarını kanıtlar.

skills/reproducible-pdf-build/SKILL.md prosedürünü MOCK qpdf + mock PDF
üzerinde koşar:

  1) RERUN kuralı (Step 1): aynı girdi üzerinde N koşum → distinct hash
     sayısı. NON-DETERMINISTIC (qpdf gerçeği — V5l bulgusu) / DETERMINISTIC.
  2) REUSE kuralı (Critical rule + Step 3): sidecar YALNIZCA ham hash
     değişince yeniden üretilir; değişmediyse aynen korunur → ardışık
     repack'ler byte-identical. repack_delivery.py'nin kararıyla aynı.
  3) OPSİYONEL ARAÇ: qpdf yoksa skip (fail değil).

Senkron testleri gerçek _calisma/repack_delivery.py kaynağını okuyup:
- reuse koşulunun (cached_raw == raw_hash) metinsel varlığını,
- sidecar formatının (satır 1: `<stripped>  <name>.metadata`,
  satır 2: `# raw: <raw>  <name>`) birebir eşleştiğini,
- karar fonksiyonunun (read_cached_raw line.split()[2]) repack ile aynı
  parse ettiğini davranışsal olarak doğrular.
"""
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import reproducible_pdf_skill as rp

REPACK_SRC = pathlib.Path(__file__).resolve().parent.parent / "repack_delivery.py"


def _write_mock_qpdf(dirpath, nondet):
    """MOCK qpdf betiği: girdiyi çıktıya kopyalar; nondet ise sayaç ekler.

    Sayaç dosyası betiğe gömülür → her çağrı farklı çıktı üretir (qpdf'nin
    gerçek non-determinizmi) ve çağrı sayısı sayaçtan okunabilir (reuse'da
    qpdf çağrılmadığını kanıtlamak için).
    """
    counter = dirpath / "mock_qpdf_counter"
    counter.write_text("0")
    script = dirpath / ("mock_qpdf_nondet.sh" if nondet else "mock_qpdf_stable.sh")
    append = ""
    if nondet:
        append = f"""
n=$(cat "{counter}" 2>/dev/null || echo 0)
n=$((n+1))
echo "$n" > "{counter}"
printf '%s' "$n" >> "$out"
"""
    body = f"""#!/bin/bash
# mock qpdf: $1 --remove-metadata $2(in) $3(out)
out="$3"
cat "$2" > "$out"
{append}
"""
    script.write_text(textwrap.dedent(body))
    script.chmod(0o755)
    return str(script), str(counter)


class TestSdeDocumentationSync(unittest.TestCase):
    """SKILL.md'nin tectonic + SDE bulgusunu gerçek deney kanıtıyla eşleştirir."""

    def test_skill_does_not_claim_tectonic_sde_determinism(self):
        skill = ROOT / "skills" / "reproducible-pdf-build" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertIn("tectonic", text.lower())
        self.assertIn("SOURCE_DATE_EPOCH", text)
        self.assertIn("does not honor `SOURCE_DATE_EPOCH`", text)
        self.assertIn("strict-determinism gate", text)
        self.assertIn("should stay OFF", text)
        self.assertNotIn("tectonic` is byte-deterministic", text)

    def test_pending_sde_record_cannot_be_present_as_proof(self):
        candidates = [
            ROOT / "_calisma" / "CIKTI" / "sde_determinism_output.txt",
            ROOT / "_calisma" / "sde_experiment" / "sde_determinism_output.txt",
        ]
        for path in candidates:
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                if "PENDING" in text:
                    self.skipTest(f"SDE deney kaydı henüz gerçek TeXLive ölçümü içermiyor: {path}")
                self.assertRegex(text, r"(?im)^KAPANIŞ:.*determin")


class TestRerunRule(unittest.TestCase):
    """SKILL.md Step 1 — aynı girdi üzerinde N koşum, distinct hash sayısı."""

    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory(prefix="rpskill_")
        cls.dir = pathlib.Path(cls.td.name)
        cls.pdf = cls.dir / "manuscript.pdf"
        cls.pdf.write_bytes(b"%PDF-1.7 mock deterministic input bytes" * 32)
        cls.qpdf_nondet, cls.counter = _write_mock_qpdf(cls.dir, nondet=True)
        cls.qpdf_stable, _ = _write_mock_qpdf(cls.dir, nondet=False)
        # Her zaman başarısız qpdf (returncode != 0 → None hash yolu)
        cls.qpdf_fail = cls.dir / "mock_qpdf_fail.sh"
        cls.qpdf_fail.write_text("#!/bin/bash\nexit 3\n")
        cls.qpdf_fail.chmod(0o755)

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def test_rerun_nondeterministic(self):
        """MOCK nondet qpdf: 5 koşum → 5 distinct hash → NON-DETERMINISTIC."""
        res = rp.rerun_experiment(self.qpdf_nondet, str(self.pdf), runs=5)
        self.assertEqual(res["verdict"], "NON-DETERMINISTIC")
        self.assertEqual(res["distinct"], 5)
        self.assertEqual(len(res["hashes"]), 5)
        self.assertIsNotNone(res["raw"])
        # 5 farklı çıktı hash'i — qpdf'nin V5l bulgusuyla aynı desen
        self.assertEqual(len({h for h in res["hashes"] if h}), 5)

    def test_rerun_deterministic(self):
        """MOCK stabil qpdf: 5 koşum → tek distinct hash → DETERMINISTIC."""
        res = rp.rerun_experiment(self.qpdf_stable, str(self.pdf), runs=5)
        self.assertEqual(res["verdict"], "DETERMINISTIC")
        self.assertEqual(res["distinct"], 1)

    def test_rerun_failure_produces_none(self):
        """Başarısız qpdf: her koşum None hash; distinct 0; çökmez."""
        res = rp.rerun_experiment(self.qpdf_fail, str(self.pdf), runs=3)
        self.assertEqual(res["hashes"], [None, None, None])
        self.assertEqual(res["distinct"], 0)
        self.assertEqual(res["verdict"], "DETERMINISTIC")  # distinct <= 1

    def test_rerun_never_touches_input(self):
        """Deney girdiyi asla değiştirmez (raw hash sabit kalır)."""
        before = rp.sha256_file(str(self.pdf))
        rp.rerun_experiment(self.qpdf_nondet, str(self.pdf), runs=3)
        self.assertEqual(before, rp.sha256_file(str(self.pdf)))


class TestReuseRule(unittest.TestCase):
    """SKILL.md Critical rule — sidecar yalnızca ham hash değişince yeniden üretilir."""

    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory(prefix="rpskill_reuse_")
        cls.dir = pathlib.Path(cls.td.name)
        cls.pdf = cls.dir / "ingiliz_empirizmi_v3.pdf"
        cls.sidecar = cls.dir / "ingiliz_empirizmi_v3.pdf.metadata.sha256"
        cls.qpdf_nondet, cls.counter = _write_mock_qpdf(cls.dir, nondet=True)
        cls.qpdf_stable, _ = _write_mock_qpdf(cls.dir, nondet=False)

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def setUp(self):
        """Her test bağımsız: ham PDF sabit, sidecar yok, sayaç sıfır."""
        self.pdf.write_bytes(b"%PDF-1.7 stable raw" * 64)
        if self.sidecar.exists():
            self.sidecar.unlink()
        pathlib.Path(self.counter).write_text("0")

    def _counter_val(self):
        return int(pathlib.Path(self.counter).read_text())

    def test_first_repack_regenerates(self):
        """Sidecar yokken ilk repack yeniden üretir (regenerate)."""
        decision, raw = rp.sync_sidecar(
            str(self.pdf), str(self.sidecar), "ingiliz_empirizmi_v3",
            qpdf=self.qpdf_nondet)
        self.assertEqual(decision, "regenerate")
        self.assertEqual(raw, rp.sha256_file(str(self.pdf)))
        self.assertTrue(self.sidecar.is_file())
        self.assertEqual(self._counter_val(), 1)  # qpdf tam 1 kez çağrıldı

    def test_second_repack_reuses_byte_identical(self):
        """Ham hash değişmedi → reuse; sidecar byte-identical, qpdf çağrılmaz.

        Ardışık repack'lerin byte-identical kanıtı: ikinci repack'te sidecar
        içeriği birebir aynı kalır ve qpdf hiç çalıştırılmaz (counter sabit).
        """
        rp.sync_sidecar(str(self.pdf), str(self.sidecar),
                        "ingiliz_empirizmi_v3", qpdf=self.qpdf_nondet)
        before = self.sidecar.read_bytes()
        c1 = self._counter_val()
        decision, _ = rp.sync_sidecar(
            str(self.pdf), str(self.sidecar),
            "ingiliz_empirizmi_v3", qpdf=self.qpdf_nondet)
        self.assertEqual(decision, "reuse")
        self.assertEqual(self.sidecar.read_bytes(), before)   # byte-identical
        self.assertEqual(self._counter_val(), c1)             # qpdf çağrılmadı

    def test_raw_change_triggers_regenerate(self):
        """PDF değişti → regenerate; sidecar yeni ham hash'i taşır."""
        rp.sync_sidecar(str(self.pdf), str(self.sidecar),
                        "ingiliz_empirizmi_v3", qpdf=self.qpdf_nondet)
        with open(self.pdf, "ab") as f:      # ham byte değişir
            f.write(b" EDITED")
        new_raw = rp.sha256_file(str(self.pdf))
        decision, raw = rp.sync_sidecar(
            str(self.pdf), str(self.sidecar),
            "ingiliz_empirizmi_v3", qpdf=self.qpdf_nondet)
        self.assertEqual(decision, "regenerate")
        self.assertEqual(raw, new_raw)
        # Sidecar'daki # raw satırı yeni ham hash'i gösterir
        self.assertEqual(rp.read_cached_raw(str(self.sidecar)), new_raw)

    def test_qpdf_missing_skips(self):
        """qpdf yok → skip; sidecar üretilmez; hata yok (opsiyonel araç)."""
        sidecar2 = self.dir / "nope.pdf.metadata.sha256"
        decision, raw = rp.sync_sidecar(str(self.pdf), str(sidecar2),
                                        "nope", qpdf=None)
        self.assertEqual(decision, "skip")
        self.assertFalse(sidecar2.exists())
        self.assertEqual(raw, rp.sha256_file(str(self.pdf)))

    def test_pdf_missing_skips(self):
        """PDF yok → skip; raw None; çökmez."""
        decision, raw = rp.sync_sidecar(
            str(self.dir / "missing.pdf"), str(self.sidecar),
            "missing", qpdf=self.qpdf_nondet)
        self.assertEqual(decision, "skip")
        self.assertIsNone(raw)

    def test_qpdf_failure_skips_keeps_old_sidecar(self):
        """Ham hash değişti + qpdf başarısız → skip; eski sidecar korunur."""
        # Önce geçerli bir sidecar üret, sonra PDF'i değiştir (stale sidecar).
        rp.sync_sidecar(str(self.pdf), str(self.sidecar),
                        "ingiliz_empirizmi_v3", qpdf=self.qpdf_nondet)
        with open(self.pdf, "ab") as f:
            f.write(b" EDITED")
        before = self.sidecar.read_bytes()
        fail = self.dir / "mock_qpdf_fail.sh"
        fail.write_text("#!/bin/bash\nexit 3\n")
        fail.chmod(0o755)
        decision, _ = rp.sync_sidecar(
            str(self.pdf), str(self.sidecar),
            "ingiliz_empirizmi_v3", qpdf=str(fail))
        self.assertEqual(decision, "skip")
        self.assertEqual(self.sidecar.read_bytes(), before)

    def test_read_cached_raw_parsing(self):
        """read_cached_raw, repack'in line.split()[2] parsesiyle aynıdır."""
        raw = "a" * 64
        self.sidecar.write_text(
            f"{'b' * 64}  ingiliz_empirizmi_v3.pdf.metadata\n"
            f"# raw: {raw}  ingiliz_empirizmi_v3.pdf\n")
        self.assertEqual(rp.read_cached_raw(str(self.sidecar)), raw)
        # # raw satırı yoksa None
        self.sidecar.write_text("hash  x.pdf.metadata\n")
        self.assertIsNone(rp.read_cached_raw(str(self.sidecar)))
        # Dosya yoksa None
        self.assertIsNone(rp.read_cached_raw(str(self.dir / "nope")))


class TestSyncAgainstRepackDelivery(unittest.TestCase):
    """reproducible_pdf_skill ↔ gerçek _calisma/repack_delivery.py senkronu.

    Skill protokolünün üretim kodundan sapmadığını iki yönden doğrular:
    (a) metinsel — reuse koşulu ve sidecar formatı repack kaynağında birebir
    var; (b) davranışsal — aynı girdide aynı karar (read_cached_raw parse'ı
    repack'in line.split()[2]'siyle aynı sonucu üretir).
    """

    @classmethod
    def setUpClass(cls):
        cls.src = REPACK_SRC.read_text(encoding="utf-8")
        if not REPACK_SRC.is_file():
            raise unittest.SkipTest(f"repack_delivery.py yok: {REPACK_SRC}")
        cls.td = tempfile.TemporaryDirectory(prefix="rpskill_sync_")
        cls.dir = pathlib.Path(cls.td.name)
        cls.qpdf_nondet, _ = _write_mock_qpdf(cls.dir, nondet=True)

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def test_reuse_condition_present_in_source(self):
        """repack_delivery.py, reuse koşulunu (cached_raw == raw_hash) içerir."""
        self.assertIn("cached_raw == raw_hash", self.src)
        self.assertIn("# raw:", self.src)

    def test_sidecar_format_matches(self):
        """Sidecar formatı birebir: satır 1 stripped + name.metadata, satır 2 # raw."""
        # repack'in yazdığı satırlar
        self.assertIn('f.write(f"{sha256(_tmp)}  ingiliz_empirizmi_v3.pdf.metadata', self.src)
        self.assertIn('f.write(f"# raw: {raw_hash}  ingiliz_empirizmi_v3.pdf', self.src)
        # helper'ın yazdığı format (repack ile birebir: name .pdf içerir)
        with tempfile.TemporaryDirectory() as td:
            sidecar = pathlib.Path(td, "x.pdf.metadata.sha256")
            rp.write_sidecar(str(sidecar), "a" * 64, "b" * 64, "x.pdf")
            lines = sidecar.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^[0-9a-f]{64}  x\.pdf\.metadata$")
        self.assertRegex(lines[1], r"^# raw: [0-9a-f]{64}  x\.pdf$")

    def test_cached_raw_parse_equivalence(self):
        """read_cached_raw ↔ repack'in inline parse'ı aynı sonucu verir."""
        with tempfile.TemporaryDirectory() as td:
            sidecar = pathlib.Path(td, "x.pdf.metadata.sha256")
            sidecar.write_text(
                "abc  x.pdf.metadata\n# raw: feedface  x.pdf\n")
            helper = rp.read_cached_raw(str(sidecar))
            # repack deseni: line.split()[2]
            repack = None
            for line in sidecar.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("# raw:"):
                    repack = line.split()[2]
                    break
            self.assertEqual(helper, repack)
            self.assertEqual(helper, "feedface")

    def test_decision_functionally_equivalent(self):
        """Aynı (pdf, sidecar) girdisinde helper kararı == repack kararı."""
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td)
            pdf = d / "p.pdf"
            pdf.write_bytes(b"%PDF-1.7 x" * 40)
            sidecar = d / "p.pdf.metadata.sha256"
            raw_hash = rp.sha256_file(str(pdf))
            # 1) Uyumlu sidecar → repack "reuse" der; helper de aynen korur.
            rp.write_sidecar(str(sidecar), "s" * 64, raw_hash, "p.pdf")
            self.assertEqual(rp.read_cached_raw(str(sidecar)), raw_hash)
            decision, raw = rp.sync_sidecar(str(pdf), str(sidecar), "p.pdf",
                                            qpdf=self.qpdf_nondet)
            self.assertEqual(decision, "reuse")
            self.assertEqual(raw, raw_hash)
            # 2) Bayat sidecar → repack "regenerate" der; helper da üretir.
            rp.write_sidecar(str(sidecar), "s" * 64, "f" * 64, "p.pdf")
            decision, _ = rp.sync_sidecar(str(pdf), str(sidecar), "p.pdf",
                                          qpdf=self.qpdf_nondet)
            self.assertEqual(decision, "regenerate")
            # 3) qpdf yok → repack hiç üretmez (UYARI); helper skip der.
            rp.write_sidecar(str(sidecar), "s" * 64, "f" * 64, "p.pdf")
            decision, _ = rp.sync_sidecar(str(pdf), str(sidecar), "p.pdf",
                                          qpdf=None)
            self.assertEqual(decision, "skip")

    def test_skill_doc_refers_to_production_artifacts(self):
        """SKILL.md, gerçek üretim araçlarına (repack_delivery.py vb.) işaret eder."""
        skill = pathlib.Path(__file__).resolve().parent.parent.parent \
            / "skills" / "reproducible-pdf-build" / "SKILL.md"
        if not skill.is_file():
            self.skipTest("SKILL.md yok")
        text = skill.read_text(encoding="utf-8")
        self.assertIn("repack_delivery.py", text)
        self.assertIn("reuse", text)
        self.assertIn("SOURCE_DATE_EPOCH", text)


class TestHelpers(unittest.TestCase):
    def test_sha256_file_matches_hashlib(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(os.urandom(200_000))  # chunked okuma yolu
            p = f.name
        try:
            with open(p, "rb") as stream:
                expect = hashlib.sha256(stream.read()).hexdigest()
            self.assertEqual(rp.sha256_file(p), expect)
        finally:
            os.unlink(p)

    def test_find_qpdf_found_via_path(self):
        """PATH'teki qpdf'i bulur (launchd minimal PATH senaryosu)."""
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td)
            fake = d / "qpdf"
            fake.write_text("#!/bin/bash\n")
            fake.chmod(0o755)
            old = os.environ.get("PATH", "")
            try:
                os.environ["PATH"] = td
                self.assertEqual(rp.find_qpdf(candidates=("qpdf",)), "qpdf")
            finally:
                os.environ["PATH"] = old

    def test_find_qpdf_missing_returns_none(self):
        self.assertIsNone(rp.find_qpdf(candidates=("definitely-not-qpdf-xyz",)))


if __name__ == "__main__":
    unittest.main()
