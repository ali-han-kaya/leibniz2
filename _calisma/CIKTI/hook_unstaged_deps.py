#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hook_unstaged_deps.py — pre-commit hook'ları için ortak unstaged-deps ön-kontrolü.

`language: system`, `pass_filenames: false` hook'ları ÇALIŞMA AĞACINI test
eder; `git commit` ise STAGE'LENEN içeriği alır. Bağımlılık dosyalarının
stage edilmemiş/untracked değişiklikleri varsa hook, commit edilecek
sürümden FARKLI bir sürümü test edebilir. Bu modül o durumu NET bir uyarıyla
görünür yapar (advisory — testler yine de koşar, exit kodu test sonucunu
yansıtır).

Kullanan hook'lar:
  - check_repro_manifest_hook.py        (check-repro-manifest)
  - check_pattern_consistency_hook.py   (check-pattern-consistency)
  - verify_delivery_hook.py             (verify-delivery)
"""
import subprocess
import sys


def unstaged_deps(deps):
    """Bağımlılık dosyalarının stage durumunu döndürür: {rel: durum}.

    git status --porcelain çıktısındaki XY kodundan:
      - '??'            → untracked (hiç stage edilmemiş — commit'e girmez)
      - Y sütununda 'M' → iş ağacında değişiklik (unstaged veya MM)
      - yalnızca 'M '   → SADECE stage edilmiş → temiz (uyarı yok)
    """
    r = subprocess.run(
        ["git", "status", "--porcelain", "--", *deps],
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


def print_warning(hook_name, dirty):
    """Hook adı + kirli bağımlılık listesiyle NET uyarı bloğu basar (advisory)."""
    print(f"⚠️  {hook_name} ÖN-KONTROL: bağımlılık dosyası "
          "STAGE EDİLMEMİŞ", file=sys.stderr)
    for rel, st in sorted(dirty.items()):
        print(f"    • {rel}  ({st})", file=sys.stderr)
    print("  Hook testleri ÇALIŞMA AĞACINI koşar; `git commit` "
          "stage'lenen içeriği alır.", file=sys.stderr)
    print("  Bu dosyalarda farklı sürüm test edilip farklı sürüm "
          "commit edilebilir.", file=sys.stderr)
    print("  Stage'lemek için: git add <dosya> "
          "(uyarı advisory — testler yine de koşar)", file=sys.stderr)


def block_strict(hook_name, dirty):
    """Strict mod: kirli bağımlılık varsa hook'u BLOKE eder (fail-closed).

    Uyarı bloğunu basar ve exit 2 döndürür — çağıran hook, asıl kapıyı
    KOŞMADAN bu kodu döndürmelidir (commit bloke).
    """
    print(f"⛔  {hook_name} ÖN-KONTROL (--strict): bağımlılık dosyası "
          "STAGE EDİLMEMİŞ — HOOK BLOKE", file=sys.stderr)
    for rel, st in sorted(dirty.items()):
        print(f"    • {rel}  ({st})", file=sys.stderr)
    print("  Strict modda unstaged/untracked bağımlılık commit'i bloke eder:",
          file=sys.stderr)
    print("  hook, stage edilen sürümle aynı içeriği test edemez.",
          file=sys.stderr)
    print("  Stage'lemek için: git add <dosya>  (sonra commit'i tekrarla)",
          file=sys.stderr)
    return 2
