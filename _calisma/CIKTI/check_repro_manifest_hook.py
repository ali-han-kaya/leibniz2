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

# Hook'un test ettiği ve commit'in içeriğini belirleyen bağımlılıklar.
DEPS = [
    ".github/workflows/verify.yml",               # merge pattern / ARTIFACT_JOBS
    "_calisma/CIKTI/gen_repro_manifest.py",        # test edilen üretici
    "_calisma/CIKTI/test_gen_repro_manifest.py",   # testin kendisi
]


def unstaged_deps():
    """Bağımlılık dosyalarının stage durumunu döndürür: {rel: durum}.

    git status --porcelain çıktısındaki XY kodundan:
      - '??'            → untracked (hiç stage edilmemiş — commit'e girmez)
      - Y sütununda 'M' → iş ağacında değişiklik (unstaged veya MM)
      - yalnızca 'M '   → SADECE stage edilmiş → temiz (uyarı yok)
    """
    r = subprocess.run(
        ["git", "status", "--porcelain", "--", *DEPS],
        capture_output=True, text=True)
    dirty = {}
    for line in r.stdout.splitlines():
        line = line.rstrip("\n")
        if len(line) < 2:
            continue
        code, rel = line[:2], line[3:].strip()
        if code.startswith("??"):
            dirty[rel] = "untracked (stage edilmemiş — commit'e girmez)"
        elif len(code) == 2 and code[1] == "M":
            dirty[rel] = ("unstaged değişiklik" if code[0] == " "
                          else "staged + unstaged (çift durum)")
    return dirty


def main():
    dirty = unstaged_deps()
    if dirty:
        print("⚠️  check-repro-manifest ÖN-KONTROL: bağımlılık dosyası "
              "STAGE EDİLMEMİŞ", file=sys.stderr)
        for rel, st in sorted(dirty.items()):
            print(f"    • {rel}  ({st})", file=sys.stderr)
        print("  Hook testleri ÇALIŞMA AĞACINI koşar; `git commit` "
              "stage'lenen içeriği alır.", file=sys.stderr)
        print("  Bu dosyalarda farklı sürüm test edilip farklı sürüm "
              "commit edilebilir.", file=sys.stderr)
        print("  Stage'lemek için: git add <dosya> "
              "(uyarı advisory — testler yine de koşar)",
              file=sys.stderr)
    # Asıl kapı: önceki hook entry'siyle birebir aynı komut.
    r = subprocess.run(
        [sys.executable, "-m", "unittest", "discover",
         "-s", str(CIKTI), "-p", "test_gen_repro_manifest.py"])
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
