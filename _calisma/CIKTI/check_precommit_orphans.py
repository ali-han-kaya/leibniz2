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
  olabilir; cezalandırılmaz).
- Dizin boş/yok → exit 0.
"""
import hashlib
import os
import pathlib
import sys
import time

WINDOW_HOURS = 24
ARCHIVE = pathlib.Path(__file__).resolve().parent / "recovery_patches_20260918"


def cache_dir() -> pathlib.Path:
    home = os.environ.get("PRE_COMMIT_HOME")
    return pathlib.Path(home) if home else pathlib.Path.home() / ".cache" / "pre-commit"


def main() -> int:
    base = cache_dir()
    now = time.time()
    orphans = []
    if base.is_dir():
        for p in base.glob("patch*"):
            age_h = (now - p.stat().st_mtime) / 3600.0
            if age_h > WINDOW_HOURS:
                orphans.append((p, age_h))

    if not orphans:
        return 0

    # Bilinen-olay parmak-izleri: arşivdeki patch'lerin sha256'sı ile
    # karşılaştır; birebir eşleşme = 2026-09-18 revert-olayı içeriği.
    known = {}
    if ARCHIVE.is_dir():
        for a in ARCHIVE.glob("patch*"):
            known[hashlib.sha256(a.read_bytes()).hexdigest()] = a.name

    print("PRE-COMMIT PATCH ORPHANS (kurtarma-penceresi dışı kalıntı):")
    for p, age_h in sorted(orphans, key=lambda x: -x[1]):
        print(f"  {p.name}: {age_h:.1f}h eski")
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h in known:
            print(
                f"    KNOWN-INCIDENT: içerik {known[h]} ile birebir aynı "
                "(2026-09-18 revert olayı). Kurtarma: `git apply <patch>` "
                f"ile geri-uygula (arsiv: {ARCHIVE})."
            )
    print(
        "recovery: her patch, bir koşumun unstaged deltasidir (revert-olayi "
        "kanitidir, dis-aktor degil). Gerekmiyorsa sil; olay-arsivi icin "
        "_calisma/CIKTI/recovery_patches_20260918/ desenini izle."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
