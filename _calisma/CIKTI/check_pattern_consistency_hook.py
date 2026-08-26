#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_pattern_consistency_hook.py — check-pattern-consistency hook'unun ön-kontrolü.

check-pattern-consistency hook'u (`language: system`, `pass_filenames: false`)
ÇALIŞMA AĞACINI test eder; `git commit` ise STAGE'LENEN içeriği alır.
Bağımlılık dosyalarının (verify.yml — merge pattern kaynağı,
check_pattern_consistency.py — test edilen denetçi, gen_repro_manifest.py —
ARTIFACT_JOBS kaynağı) stage edilmemiş değişiklikleri varsa hook, commit
edilecek sürümden FARKLI bir sürümü test edebilir. Bu ön-kontrol o durumu NET
bir uyarıyla görünür yapar (advisory — denetim yine de koşar, exit kodu
denetim sonucunu yansıtır).

Kullanım (pre-commit entry):
    python3 _calisma/CIKTI/check_pattern_consistency_hook.py

Davranış:
  1. Bağımlılık dosyaları için `git status --porcelain` ile stage durumu
     denetlenir: '??' (untracked) veya iş-ağacı sütununda 'M' (unstaged /
     staged+unstaged) → uyarı listesine girer; yalnızca staged ('M ') temizdir.
  2. Uyarı varsa net bir blok basılır (advisory).
  3. Asıl kapı koşulur: check_pattern_consistency.py (önceki hook entry'siyle
     birebir aynı komut). Exit kodu korunur.
"""
import pathlib
import subprocess
import sys

CIKTI = pathlib.Path(__file__).resolve().parent

sys.path.insert(0, str(CIKTI))
import hook_unstaged_deps as hud  # noqa: E402

# Hook'un test ettiği ve commit'in içeriğini belirleyen bağımlılıklar.
DEPS = [
    ".github/workflows/verify.yml",                 # merge pattern kaynağı
    "_calisma/CIKTI/check_pattern_consistency.py",  # test edilen denetçi
    "_calisma/CIKTI/gen_repro_manifest.py",         # ARTIFACT_JOBS kaynağı
]


def unstaged_deps():
    """Bağımlılık dosyalarının stage durumu ({rel: durum})."""
    return hud.unstaged_deps(DEPS)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    strict = "--strict" in argv
    dirty = unstaged_deps()
    if dirty:
        if strict:
            # Fail-closed: stage edilen sürümle aynı içerik test edilemez.
            return hud.block_strict("check-pattern-consistency", dirty)
        hud.print_warning("check-pattern-consistency", dirty)
    # Asıl kapı: önceki hook entry'siyle birebir aynı komut.
    r = subprocess.run(
        [sys.executable, str(CIKTI / "check_pattern_consistency.py")])
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
