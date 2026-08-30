#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""classify_lean_error.py — K9 FAIL detail'ini hata sınıfına göre sınıflandırır.

Skill'deki (skills/verify-chain/SKILL.md) error-priority kuralı K9'a özgü
hata sınıfı sırasıyla uygulanır. Lean 4 derleme çıktısındaki hatalar kökten
yüzeyselliğe doğru sınıflandırılır — en yüksek öncelikli sınıf raporlanır
(birden çok sınıf içeren çıktıda daha köklü hata önce teşhis edilir):

    priority  sınıf        anlam
    ────────  ───────────  ──────────────────────────────────────────────
    1         syntax       dosya ayrıştırılamıyor (parser hatası) — en köklü;
                           syntax bozuksa diğer hatalar gürültüdür
    2         type         tip hatası (type mismatch, unknown identifier,
                           failed to synthesize) — kanıt gövdesi tip-çözümlemede
    3         unsolved     ispat tamamlanmamış (unsolved goals, tactic failed,
                           sorry kalıntısı) — hedef açık kalmış
    4         linter       --wfail uyarıları (unused variable, deprecated,
                           declaration uses 'sorry') — derlenir ama kapı fail

Saf fonksiyon: `classify_lean_error(text)` → (priority, cls) veya (None, None).
Dış bağımlılık yok; verify_delivery.run_lean_proof / run_lake_build FAIL
detail'lerine `[sınıf]` etiketi ekler (K9 hata ayıklayıcısı).
"""
import re

# Sınıf → (öncelik, eşleşme desenleri). SIRA ÖNEMLİ: syntax en köklü, linter
# en yüzeysel. Skill tablosuyla tek kaynak (SKILL.md §K9 error priority).
ERROR_CLASSES = [
    # 1 — syntax: parser/ayrıştırma hatası (en köklü).
    ("syntax", 1, [
        r"syntax error",
        r"unexpected token",
        r"unexpected end of input",
        r"expected .* but got",
        r"parse error",
        r"unknown parser",
        r"invalid .* syntax",
    ]),
    # 2 — type: tip çözümleme hatası (kanıt gövdesi tiplenemiyor).
    ("type", 2, [
        r"type mismatch",
        r"application type mismatch",
        r"unknown identifier",
        r"failed to synthesize",
        r"don't know how to synthesize",
        r"typeclass instance",
        r"expected type",
        r"has type",
    ]),
    # 3 — unsolved: ispat tamamlanmamış (hedef açık).
    ("unsolved", 3, [
        r"unsolved goals",
        r"tactic .*failed",
        r"no goals to be solved",
        r"failed to prove",
        r"unsolved",
    ]),
    # 4 — linter: --wfail uyarıları (derlenir ama kapı fail).
    ("linter", 4, [
        r"declaration uses 'sorry'",
        r"unused variable",
        r"deprecated",
        r"warning:",
        r"linter",
    ]),
]

# Derlenmiş regex'ler — her çağrıda derlemeyi önle.
_PATTERNS = [(cls, pri, re.compile(p, re.IGNORECASE))
             for cls, pri, pats in ERROR_CLASSES
             for p in pats]


def classify_lean_error(text):
    """Lean derleme çıktısını hata sınıfına göre sınıflandırır.

    Döndürür: (priority, cls) — en yüksek öncelikli (en küçük numaralı) sınıf;
    eşleşme yoksa (None, None). Çıktı birden çok sınıf içeriyorsa daha köklü
    hata kazanır (skill error-priority: syntax > type > unsolved > linter).
    """
    if not text:
        return None, None
    best = None
    for cls, pri, rx in _PATTERNS:
        if rx.search(text):
            # ERROR_CLASSES sırası zaten öncelik sırasıdır — ilk eşleşen
            # en köklü hata; daha düşük priority'li sınıflara bakma.
            return pri, cls
    return None, None


def tag_lean_detail(detail):
    """K9 FAIL detail'ine `[sınıf]` ön eki ekler; sınıf yoksa olduğu gibi döner.

    Örn: "lake build hatası: unsolved goals" → "[unsolved] lake build hatası: …"
    """
    pri, cls = classify_lean_error(detail)
    if cls is None:
        return detail
    return f"[{cls}] {detail}"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        pri, cls = classify_lean_error(sys.argv[1])
        print(f"priority={pri} class={cls}")
    else:
        print("kullanım: python3 classify_lean_error.py '<lean çıktısı>'")
        sys.exit(2)
