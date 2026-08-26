#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_repro_manifest_hook.py — check-repro-manifest hook'unun ön-kontrolü.

check-repro-manifest hook'u (`language: system`, `pass_filenames: false`)
ÇALIŞMA AĞACINI test eder; `git commit` ise STAGE'LENEN içeriği alır.
Bağımlılık dosyalarının (verify.yml — merge pattern/ARTIFACT_JOBS kaynağı,
gen_repro_manifest.py — test edilen üretici, test_gen_repro_manifest.py —
testin kendisi) stage edilmemiş değişiklikleri varsa hook, commit edilecek
sürümden FARKLI bir sürümü test edebilir. Bu ön-kontrol o durumu NET bir
uyarıyla görünür yapar (advisory — testler yine de koşar, exit kodu test
sonucunu yansıtır).

Kullanım (pre-commit entry):
    python3 _calisma/CIKTI/check_repro_manifest_hook.py

Davranış:
  1. Bağımlılık dosyaları için `git status --porcelain` ile stage durumu
     denetlenir: '??' (untracked) veya iş-ağacı sütununda 'M' (unstaged /
     staged+unstaged) → uyarı listesine girer; yalnızca staged ('M ') temizdir.
  2. Uyarı varsa net bir blok basılır (advisory).
  3. Asıl kapı koşulur: test_gen_repro_manifest.py unittest discovery'si
     (önceki hook entry'siyle birebir aynı komut). Exit kodu korunur.
"""
import pathlib
import subprocess
import sys

CIKTI = pathlib.Path(__file__).resolve().parent

sys.path.insert(0, str(CIKTI))
import hook_unstaged_deps as hud  # noqa: E402

# Hook'un test ettiği ve commit'in içeriğini belirleyen bağımlılıklar.
DEPS = [
    ".github/workflows/verify.yml",               # merge pattern / ARTIFACT_JOBS
    "_calisma/CIKTI/gen_repro_manifest.py",        # test edilen üretici
    "_calisma/CIKTI/test_gen_repro_manifest.py",   # testin kendisi
]


# Geriye dönük uyumluluk: testler hook.unstaged_deps() çağırır.
unstaged_deps = lambda: hud.unstaged_deps(DEPS)  # noqa: E731


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    strict = "--strict" in argv
    dirty = unstaged_deps()
    if dirty:
        if strict:
            # Fail-closed: stage edilen sürümle aynı içerik test edilemez.
            return hud.block_strict("check-repro-manifest", dirty)
        hud.print_warning("check-repro-manifest", dirty)
    # Asıl kapı: önceki hook entry'siyle birebir aynı komut.
    r = subprocess.run(
        [sys.executable, "-m", "unittest", "discover",
         "-s", str(CIKTI), "-p", "test_gen_repro_manifest.py"])
    # Test başarısızsasatır numarası dahil detaylı çıktı üret
    if r.returncode != 0:
        print("\n─── check-repro-manifest HATA DETAYI ───", file=sys.stderr)
        # pattern一致性 test'inden satır numarası al
        try:
            import check_pattern_consistency as cpc
            errors = cpc.check()
            if errors:
                for e in errors:
                    print(f"  ✗ {e}", file=sys.stderr)
        except Exception:
            pass
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
