#!/usr/bin/env python3
"""check_precommit_orphans.py — pre-commit patch-kalıntısı kapısı (fail-closed).

Kök-neden (systematic-debugging turu, 2026-09-19): pre-commit unstaged
deltayı ~/.cache/pre-commit/patch<epoch>-<pid> dosyasına stash'leyip
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
"""
import hashlib
import os
import pathlib
import sys
import time

WINDOW_HOURS = 24
HERE = pathlib.Path(__file__).resolve().parent
# Arşiv dizinleri tarih damgalıdır (recovery_patches_20260918, …_20260920,
# …_20260926): desen GLOB'dur, tek dizin sabitlenmez — yeni arşiv eklendiğinde
# parmak-izi kaynağı kendiliğinden genişler.
ARCHIVE_GLOB = "recovery_patches_*"


def cache_dir() -> pathlib.Path:
    home = os.environ.get("PRE_COMMIT_HOME")
    return pathlib.Path(home) if home else pathlib.Path.home() / ".cache" / "pre-commit"


def archive_fingerprints():
    """sha256 → ["<arşiv-dizini>/<patch-adı>", …] (tüm arşiv dizinlerinden).

    Aynı içerik birden çok arşivde olabilir (tekrar eden olay): hepsi
    listelenir, böylece kurtarma yolu tek bir dizine bağlı kalmaz.
    """
    known = {}
    for directory in sorted(HERE.glob(ARCHIVE_GLOB)):
        if not directory.is_dir():
            continue
        for patch in sorted(directory.glob("patch*")):
            try:
                digest = hashlib.sha256(patch.read_bytes()).hexdigest()
            except OSError as exc:  # arşiv okunamazsa etiketleme eksilir → görünür olsun
                print(f"UYARI: arşiv patch'i okunamadı: {patch} ({exc})")
                continue
            known.setdefault(digest, []).append(f"{directory.name}/{patch.name}")
    return known


def main() -> int:
    base = cache_dir()
    now = time.time()
    known = archive_fingerprints()
    orphans = []
    fresh_known = []

    if base.is_dir():
        for patch in sorted(base.glob("patch*")):
            if not patch.is_file():
                continue
            try:
                age_h = (now - patch.stat().st_mtime) / 3600.0
                digest = hashlib.sha256(patch.read_bytes()).hexdigest()
            except OSError as exc:
                print(f"UYARI: cache patch'i okunamadı: {patch} ({exc})")
                continue
            matches = known.get(digest, [])
            if age_h > WINDOW_HOURS:
                orphans.append((patch, age_h, matches))
            elif matches:
                fresh_known.append((patch, age_h, matches))

    if fresh_known:
        # Taze patch kurtarma-penceresi içindedir → BLOKLAMAZ; ama içeriği
        # arşivdeki bir olayla birebir aynıysa aynı delta daha önce de yetim
        # kalmıştır: bu bir tekrar sinyalidir, sessiz geçmemeli.
        print("PRE-COMMIT PATCH RECURRENCE (kurtarma-penceresi içinde — bloklamaz):")
        for patch, age_h, matches in fresh_known:
            print(f"  {patch.name}: {age_h:.1f}h eski — içerik arşivle BİREBİR aynı")
            print(f"    KNOWN-INCIDENT: {', '.join(matches)}")

    if not orphans:
        return 0

    print("PRE-COMMIT PATCH ORPHANS (kurtarma-penceresi dışı kalıntı):")
    for patch, age_h, matches in sorted(orphans, key=lambda x: -x[1]):
        print(f"  {patch.name}: {age_h:.1f}h eski")
        if matches:
            print("    KNOWN-INCIDENT: içerik arşivle birebir aynı "
                  f"({', '.join(matches)}). Kurtarma: `git apply <patch>` ile "
                  "geri-uygula.")
    archives = [d for d in sorted(HERE.glob(ARCHIVE_GLOB)) if d.is_dir()]
    print(f"arşiv parmak-izleri: {len(archives)} dizin / "
          f"{sum(len(v) for v in known.values())} patch"
          + ("" if known else " — UYARI: arşiv yok/boş, KNOWN-INCIDENT "
                              "etiketi üretilemedi (kontrol körleşti)"))
    print(
        "recovery: her patch, bir koşumun unstaged deltasidir (revert-olayi "
        "kanitidir, dis-aktor degil). Gerekmiyorsa sil; olay-arsivi icin "
        "_calisma/CIKTI/recovery_patches_<tarih>/ desenini izle."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
