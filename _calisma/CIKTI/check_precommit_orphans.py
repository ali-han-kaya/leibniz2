#!/usr/bin/env python3
"""check_precommit_orphans.py — pre-commit patch-kalıntısı kapısı (fail-closed).

Kök-neden (systematic-debugging turu, 2026-09-19): pre-commit unstaged
deltayı ~/.cache/pre-commit/patch<epoch>-<pid> dosyasına stash'leyup
`git checkout -- .` ile siler; geri-uygulama yalnız finally-bloğunda
yapılır. Pencere-içi süreç-ölümü → ağaç sessizce revert olur ve delta
yalnız patch-dosyasında kalır. pre-commit patch dosyalarını ASLA silmez
(kaynakta unlink yok) → yetimler birikir (~170 bulundu).

Sözleşme (tdd turu, seam = kapı CLI'si):
- PRE_COMMIT_HOME env'i varsa o dizin (pre-commit'in kendi override'ı),
  yoksa ~/.cache/pre-commit denetlenir.
- 24s+ yaşlı patch → exit 1; çıktı dosyayı adlar ve kurtarma-protokolünü
  söyler (patch = kurtarma-artefaktı: arşivle veya sil, dış-aktör-değil).
- Taze patch (<24s) → exit 0 (az-önce ölen koşumun tek kurtarma-aracı
  olabilir; cezalandırılmaz) — ama içeriği arşivle birebir eşleşiyorsa
  tekrar-olay uyarısı basılır ve yine exit 0 kalır.
- Arşiv parmak-izleri `recovery_patches_*` dizinlerinin TAMAMINDAN gelir
  (2026-09-27 düzeltmesi: eskiden tek dizin sabitti — 09-18 arşivi görünür,
  09-20 ve 09-26 arşivleri görünmezdi; aynı delta'nın sonraki kopyaları
  KNOWN-INCIDENT etiketi almıyordu). Arşivsizlik tek başına blok değildir,
  ama çıktı "parmak-izi yok" diyerek etiketsizliği görünür kılar.
- Dizin boş/yok → exit 0.
Exit: 0 = kurtarma-penceresi temiz, 1 = yetim var (fail-closed),
2 = kullanım hatası.

Çift parmak-izi + özel uyarı bloğu (2026-09-27, 2. tur): yetim patch'in
içeriği arşivle karşılaştırılırken İKİ özet alınır. sha256 birebir
eşleşme = bilinen olay (KNOWN-INCIDENT) ve bunun için çıktının EN ÜSTÜNDE
kendi uyarı bloğu basılır — yetim listesinin içine gömülü satır, scroll'lanıp
geçilebilir; ayrı blok geçilemez. md5 ikinci sinyaldir: kısa (32 hex) ve
olay notlarına yapıştırılabilir, ama TEK BAŞINA etiket üretmez (bilinen
çakışma yüzeyi var) — yalnız sha256 düştüğünde "zayıf-parmak-izi
çakışması" tanısına iner ve içeriğin FARKLI olduğunu söyler. Böylece ikinci
özet hiçbir zaman sha256'yı zayıflatmaz, yalnız onun göremediği durumu
(çakışma / yakın kopya) görünür kılar.
"""
import hashlib
import os
import pathlib
import sys
import time
from typing import NamedTuple

WINDOW_HOURS = 24
HERE = pathlib.Path(__file__).resolve().parent
# Arşiv dizinleri tarih damgalıdır (recovery_patches_20260918, …_20260920,
# …_20260926, …_20260927): desen GLOB'dur, tek dizin sabitlenmez — yeni arşiv
# eklendiğinde parmak-izi kaynağı kendiliğinden genişler.
ARCHIVE_GLOB = "recovery_patches_*"

# Tanı etiketleri. Sıra sözleşmedir: KNOWN yalnız sha256 birebir eşleşmesi
# üretir; WEAK yalnız md5 eşleşip sha256 düştüğünde (etiket DEĞİLDİR).
KNOWN = "known-incident"
WEAK = "weak-md5-only"
NONE = None


class Fingerprints(NamedTuple):
    """Olay-arşivinin çift parmak-izi haritası (TEK okuma, iki hesap).

    İki ayrı okuma yapılsa dosya arada değişirse haritalar birbirini
    tutmazdı — "birebir aynı" yargısı sessizce yanlışlaşırdı.
    """

    sha256: dict
    md5: dict
    archives: list
    patch_count: int


def cache_dir() -> pathlib.Path:
    home = os.environ.get("PRE_COMMIT_HOME")
    return pathlib.Path(home) if home else pathlib.Path.home() / ".cache" / "pre-commit"


def digests(data: bytes) -> tuple:
    """(sha256, md5) — ikisi de aynı baytlardan.

    md5 kasıtlı olarak güvenlik-dışı işaretlenir (FIPS çekirdeklerde
    `hashlib.md5()` reddedilebilir): burada kimlik etiketi üretir,
    bütünlük güvencesi sağlamaz — o rol sha256'nindir.
    """
    return (
        hashlib.sha256(data).hexdigest(),
        hashlib.md5(data, usedforsecurity=False).hexdigest(),
    )


def archive_fingerprints() -> Fingerprints:
    """Tüm arşiv dizinlerinden çift parmak-izi.

    Aynı içerik birden çok arşivde olabilir (tekrar eden olay): hepsi
    listelenir, böylece kurtarma yolu tek bir dizine bağlı kalmaz.
    """
    by_sha: dict = {}
    by_md5: dict = {}
    archives = []
    count = 0
    for directory in sorted(HERE.glob(ARCHIVE_GLOB)):
        if not directory.is_dir():
            continue
        archives.append(directory.name)
        for patch in sorted(directory.glob("patch*")):
            if not patch.is_file():
                continue
            try:
                sha, md5 = digests(patch.read_bytes())
            except OSError as exc:  # arşiv okunamazsa etiketleme eksilir → görünür olsun
                print(f"UYARI: arşiv patch'i okunamadı: {patch} ({exc})")
                continue
            loc = f"{directory.name}/{patch.name}"
            by_sha.setdefault(sha, []).append(loc)
            by_md5.setdefault(md5, []).append(loc)
            count += 1
    return Fingerprints(sha256=by_sha, md5=by_md5, archives=archives,
                        patch_count=count)


def classify(prints: Fingerprints, sha: str, md5: str):
    """(sha256, md5) → (etiket, arşiv konumları).

    Sıra sözleşmedir. sha256 birebir eşleşmesi tek otoritedir: aynı
    içerik demektir, "bilinen olay" etiketi doğar. sha256 düştüyse md5'e
    bakılır, ama o eşleşme WEAK'tır — md5 çakışabildiği için etiket
    üretmez, yalnız "içerik farklı ama özet aynı" ayrımını görünür kılar.
    """
    exact = prints.sha256.get(sha)
    if exact:
        return KNOWN, exact
    weak = prints.md5.get(md5)
    if weak:
        return WEAK, weak
    return NONE, []


def main() -> int:
    base = cache_dir()
    now = time.time()
    prints = archive_fingerprints()
    orphans = []
    incidents = []
    weak = []

    if base.is_dir():
        for patch in sorted(base.glob("patch*")):
            if not patch.is_file():
                continue
            try:
                age_h = (now - patch.stat().st_mtime) / 3600.0
                sha, md5 = digests(patch.read_bytes())
            except OSError as exc:
                print(f"UYARI: cache patch'i okunamadı: {patch} ({exc})")
                continue
            label, locs = classify(prints, sha, md5)
            is_orphan = age_h > WINDOW_HOURS
            if is_orphan:
                orphans.append((patch, age_h))
            if label == KNOWN:
                incidents.append((patch, age_h, sha, md5, locs, is_orphan))
            elif label == WEAK:
                weak.append((patch, age_h, md5, locs))

    # --- özel uyarı blokları: çıktının EN ÜSTÜNDE, yetim listesinden ÖNCE ---
    if incidents:
        print(f"⚠️  BİLİNEN OLAY PARMAK-İZİ (KNOWN-INCIDENT) — {len(incidents)} "
              "patch, içerik olay-arşiviyle BİREBİR aynı")
        for patch, age_h, sha, md5, locs, is_orphan in sorted(
                incidents, key=lambda x: -x[1]):
            durum = "yetim, kurtarma-penceresi dışı" if is_orphan else "taze"
            print(f"   {patch.name}: {age_h:.1f}h eski ({durum})")
            print(f"     arşiv: {', '.join(locs)}")
            print(f"     sha256: {sha}")
            print(f"     md5:    {md5}")
        fresh_n = sum(1 for x in incidents if not x[5])
        if fresh_n:
            # Taze eşleşme BLOKLANMAZ: az önce ölen koşumun tek kurtarma
            # aracı olabilir. Ama aynı delta daha önce de yetim kalmıştır →
            # sessiz geçmemeli.
            print(f"   ↳ {fresh_n} tanesi kurtarma-penceresi içinde "
                  "(<24h) — bloklamaz, tekrar sinyali")
        print("   ↳ aynı içerik arşivde duruyor: yeni veri kaybı değil; "
              "kaynağı doğrulamak için `git apply` ile denetle")

    if weak:
        print(f"⚠️  ZAYIF-PARMAK-İZİ ÇAKIŞMASI (md5 eşleşti, sha256 eşleşmedi) "
              f"— {len(weak)} patch")
        for patch, age_h, md5, locs in sorted(weak, key=lambda x: -x[1]):
            print(f"   {patch.name}: {age_h:.1f}h eski")
            print(f"     arşiv: {', '.join(locs)} (içerik FARKLI)")
            print(f"     md5:    {md5}")
        print("   ↳ md5 çakışabildiği için bu eşleşme bilinen-olay etiketi "
              "DEĞİLDİR ve tek başına kanıt sayılmaz; yalnız göz atmaya değer")

    if not orphans:
        return 0

    print("PRE-COMMIT PATCH ORPHANS (kurtarma-penceresi dışı kalıntı):")
    for patch, age_h in sorted(orphans, key=lambda x: -x[1]):
        print(f"  {patch.name}: {age_h:.1f}h eski")
    print(f"arşiv parmak-izleri: {len(prints.archives)} dizin / "
          f"{prints.patch_count} patch (sha256 + md5)"
          + ("" if prints.patch_count else
             " — UYARI: arşiv yok/boş, parmak-izi üretilemedi (kontrol körleşti)"))
    print(
        "recovery: her patch, bir koşumun unstaged deltasidir (revert-olayi "
        "kanitidir, dis-aktor degil). Gerekmiyorsa sil; olay-arsivi icin "
        "_calisma/CIKTI/recovery_patches_<tarih>/ desenini izle."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
