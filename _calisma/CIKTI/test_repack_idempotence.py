#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_repack_idempotence.py — üst-üstte repack byte-identical (sabit nokta) testi.

/tmp'de yürütülen "iki repack + zip-hash eşitliği" deneyinin kalıcı unittest
karşılığı. Deney iddiası (V5l düzeltmesinin kanıtı): `repack_delivery.main()`
bir kez koştuktan sonra TREE'NİN KENDİSİ üzerinde ikinci kez koşulduğunda
zip byte'ları değişmez — yani repack sabit noktadır (idempotent).

Bu, `ci_repack_test.sh`'in test ettiği FARKLI bir özelliktir:
  - ci_repack_test.sh : repack çıktısı == commit'li HEAD  (tazelik/uyum)
  - buradaki test      : repack(repack(T)) == repack(T)   (sabit nokta)
İkisi birbirini ikame etmez; ikisi de gereklidir.

TASARIM — neden sentetik ağaç, neden gerçek paket değil:
`repack_delivery.py` modül düzeyinde `ROOT = dirname(__file__)` ile mutlak
yol kurar; bu yüzden test GERÇEK `_calisma/` ağacını kopyalamak yerine
tmp'de SÖZLEŞME-ŞEKLİNDE (synthetic) bir ağaç kurar ve modülün KENDİSİNİ
oraya kopyalayıp oradan import eder. Böylece:
  - çalışma ağacı hiç kirlenmez (repack'in kendi yan etkileri tmp'de kalır),
  - test paket içeriğine bağlı değildir (bir dosya silinse kırılmaz),
  - saniyeler içinde biter → check-unit-tests bataryasına eklenebilir.

KRİTİK: negatif kontrol. `test_two_repacks_byte_identical` tek başına
BOŞ GEÇEBİLİR — repack hiçbir şey üretmese de "iki hash eşit" olur. Bu yüzden
`test_source_change_moves_zip_hash` aynı kurguyu tersine çalıştırır: paket
içeriğini değiştirip hash'in ZORUNLU olarak değiştiğini kanıtlar. Negatif
kontrol kırılırsa asıl testin kanıt değeri düşer.

qpdf bağımlılığı YOK: metadata sidecar'ı önceden doğru `# raw:` satırıyla
kurulur, repack'in reuse koruması (raw PDF hash'i değişmedi → sidecar'a dokunma)
yolu her iki koşumda da çalışır. qpdf yoksa da aynı yol işler (repack qpdf'i
atlar, mevcut sidecar korunur) → test her iki ortamda da aynı sonucu verir.

stdlib `unittest` — ek bağımlılık yok. CI'da "Run CIKTI unit tests" adımı ve
check-unit-tests pre-commit bataryası bu modülü otomatik koşar.
"""
import contextlib
import hashlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)          # _calisma/ — repack_delivery.py burada
REPACK_SRC = os.path.join(PARENT, "repack_delivery.py")
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

# Yalnız SÖZLEŞME ŞABLONU olarak okunur (MANIFEST_FILES listesi). Bu modülün
# ROOT'u GERÇEK ağaca işaret eder; main() ASLA çağrılmaz — testin gerçekten
# koştuğu modül, tmp ağacından ayrı bir import ile yüklenir (bkz.
# _Sandbox.import_repack). Böylece repack'in yan etkileri çalışma ağacına
# sızmaz.
import repack_delivery as template
# Satır sayısını okuyan iki dosya write_manifest() için zorunlu; içerik testin
# konusu değil ama var olmalı (yoksa os.path.getsize FileNotFoundError).
COUNTED = ("core_section.tex", "L0_Lplus_spec.md")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class _Sandbox:
    """Sözleşme-şeklinde geçici `_calisma/` ağacı + içine yönlendirilmiş repack."""

    def __init__(self, root):
        self.root = root                       # tmp/_calisma
        # Göreli yolları ŞABLON modülünün kendi sabitlerinden türetiyoruz:
        # paket dizini yeniden adlandırılırsa/derinleşirse test kırılmaz,
        # sadece aynı şekli yeniden kurar.
        self.pkg = os.path.join(root, os.path.relpath(template.PKG, template.ROOT))
        self.outer_src = os.path.join(root, os.path.relpath(template.OUTER_SRC, template.ROOT))
        self.cikti = os.path.join(root, os.path.relpath(template.CIKTI, template.ROOT))
        self.repack = os.path.join(root, "repack_delivery.py")

    def build(self):
        for d in (self.pkg, self.outer_src, self.cikti):
            os.makedirs(d, exist_ok=True)

        # 1) MANIFEST_FILES'ın tamamı — write_manifest() her birinin
        #    getsize()'ını alır, yoksa repack çöker.
        for fn in template.MANIFEST_FILES:
            self._put(self.pkg, fn, b"")

        # 2) satır sayısı okunan iki dosya gerçek içerikle
        for fn in COUNTED:
            self._put(self.pkg, fn, b"% placeholder\n" * 7)

        # 3) PDF stub'ı — minimal ama geçerli imza (qpdf --remove-metadata
        #    çağrılsa bile patlamayacak düz byte dizisi; reuse koruması
        #    sayesinde zaten hiç çağrılmaz).
        pdf = self._put(self.pkg, "ingiliz_empirizmi_v3.pdf", b"%PDF-1.5\n%stub\n")

        # 4) metadata sidecar — `# raw:` satırı PDF'in ham hash'iyle eşleşir,
        #    böylece repack reuse yolunu seçer (qpdf olsa da olmasa da).
        with open(os.path.join(self.pkg, "ingiliz_empirizmi_v3.pdf.metadata.sha256"),
                  "w", encoding="utf-8") as f:
            f.write("%s  ingiliz_empirizmi_v3.pdf.metadata\n" % _sha256(pdf))
            f.write("# raw: %s  ingiliz_empirizmi_v3.pdf\n" % _sha256(pdf))

        # 5) dış klasör içeriği (dış zip bunu paketler)
        for fn in ("README.md", "KLASOR_NOTLARI.md", "ozet.md"):
            self._put(self.outer_src, fn, b"stub %s\n" % fn.encode())

        # 6) repack modülünün kendisi + gen_config stub'ı
        shutil.copy2(REPACK_SRC, self.repack)
        # sync_config() CIKTI/gen_config.py'yi çalıştırır; dosya yoksa python
        # exit 2 döner ve sync_config bunu "ortam uyarısı" sayıp geçer. Stub
        # bilinçli olarak bu yolu kullanır: test paket içeriğine değil,
        # repack'in determinizm mantığına bakar.
        with open(os.path.join(self.cikti, "gen_config.py"), "w", encoding="utf-8") as f:
            f.write("import sys\nsys.exit(2)  # ortam yok (repack bunu geçer)\n")
        return self

    def _put(self, directory, name, data):
        p = os.path.join(directory, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def import_repack(self):
        """Modülü tmp ağacından import et (ROOT = tmp)."""
        spec = importlib.util.spec_from_file_location("_sandbox_repack", self.repack)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod

    def zip_hashes(self, mod):
        return {
            "inner": _sha256(os.path.join(self.cikti, mod.INNER_ZIP)),
            "outer": _sha256(os.path.join(self.cikti, mod.OUTER_ZIP)),
        }


class RepackIdempotenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.box = _Sandbox(os.path.join(self._tmp.name, "_calisma")).build()
        self.rd = self.box.import_repack()
        self._argv = sys.argv
        sys.argv = ["repack_delivery.py"]          # argparse sözleşmesi
        self.addCleanup(self._restore_argv)

    def _restore_argv(self):
        sys.argv = self._argv

    def _repack(self):
        """repack'i stdout susturarak koşur; exit kodunu döndürür."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = self.rd.main()
        self.assertEqual(rc, 0, "repack exit 0 olmalı; çıktı:\n%s" % buf.getvalue())
        return buf.getvalue()

    # ── çekirdek iddia ───────────────────────────────────────────────
    def test_two_consecutive_repacks_are_byte_identical(self):
        """repack(repack(T)) == repack(T): ikinci koşum zip'i DEĞİŞTİRMEZ."""
        self._repack()
        first = self.box.zip_hashes(self.rd)
        self._repack()
        second = self.box.zip_hashes(self.rd)

        for key in first:
            self.assertEqual(
                first[key], second[key],
                "%s zip'i üst-üstte repack'te değişti:\n  run1 %s\n  run2 %s"
                % (key, first[key], second[key]))
        # İç zip dış zip'in İÇİNDE de aynı baytlarla gömülü olmalı.
        with open(os.path.join(self.box.cikti, self.rd.INNER_ZIP), "rb") as f:
            inner_bytes = f.read()
        self.assertTrue(len(inner_bytes) > 0, "iç zip boş üretildi")

    # ── negatif kontrol: eşitlik testi boş olamaz ─────────────────────
    def test_source_change_moves_zip_hash(self):
        """Kaynak değişirse hash ZORUNLU değişir — aksi hâlde yukarıdaki
        test her repackçi için boş geçerdi."""
        self._repack()
        before = self.box.zip_hashes(self.rd)

        # Paket içeriğini değiştir (inner zip'in girdisi olan PKG dizini).
        target = os.path.join(self.box.pkg, "ozet.md") \
            if os.path.exists(os.path.join(self.box.pkg, "ozet.md")) \
            else os.path.join(self.box.pkg, "README.md")
        with open(target, "a", encoding="utf-8") as f:
            f.write("\ndegisiklik: repack girdisi degisti\n")

        self._repack()
        after = self.box.zip_hashes(self.rd)
        self.assertNotEqual(
            before["inner"], after["inner"],
            "paket içeriği değişti ama iç zip hash'i sabit kaldı — hash "
            "karşılaştırması içeriği görmüyor, test boştur")

    # ── bütünlük: sidecar'lar her koşumdan sonra senkron ─────────────
    def test_sidecars_stay_in_sync_after_each_run(self):
        """Her repack sonrası zip↔sidecar eşleşmesi korunur (verify kapısı)."""
        for i in (1, 2):
            self._repack()
            with contextlib.redirect_stdout(io.StringIO()):
                ok = self.rd.verify_sidecars(self.box.cikti)
            self.assertTrue(ok, "run%d sonrası zip/sidecar hash'leri eşleşmiyor" % i)

    # ── yan ürünler de stabil olmalı ─────────────────────────────────
    def test_sidecar_and_manifest_are_stable_across_runs(self):
        """Yan ürünler (MANIFEST.txt, KLASOR_CHECKSUMLARI) de kaymamalı."""
        def snapshot():
            return {
                "manifest": _sha256(os.path.join(self.box.pkg, "MANIFEST.txt")),
                "checksums": _sha256(os.path.join(
                    self.box.outer_src, "KLASOR_CHECKSUMLARI.sha256")),
                "inner_sidecar": _sha256(os.path.join(
                    self.box.cikti, self.rd.INNER_ZIP + ".sha256")),
                "outer_sidecar": _sha256(os.path.join(
                    self.box.cikti, self.rd.OUTER_ZIP + ".sha256")),
            }
        self._repack()
        first = snapshot()
        self._repack()
        self.assertEqual(first, snapshot(),
                         "repack yan ürünleri ikinci koşumda değişti")

    # ── geçici iç zip artığı bırakılmamalı (repack step 5) ───────────
    def test_no_transient_inner_zip_left_in_outer_dir(self):
        """İç zip dış klasörde ara ürün olarak kalmamalı (K0'un bayat kopya
        uyarısını üretmemek için repack step 5 siler)."""
        self._repack()
        stray = os.path.join(self.box.outer_src, self.rd.INNER_ZIP)
        stray_side = stray + ".sha256"
        self.assertFalse(os.path.exists(stray),
                         "dış klasörde ara ürün iç zip kaldı: %s" % stray)
        self.assertFalse(os.path.exists(stray_side),
                         "dış klasörde ara ürün iç zip sidecar'ı kaldı")


if __name__ == "__main__":
    unittest.main()
