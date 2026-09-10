#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""classify_lean_error.py — K9 hata sınıflandırıcısı.

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
    4         proof_gap    Coq: `Admitted` ispat boşluğu bırakır (proof gap)
    5         axiom        Coq: top-level `Axiom` bildirimi (varsayım ekler)
    6         linter       --wfail uyarıları (unused variable, deprecated,
                           declaration uses 'sorry') — derlenir ama kapı fail

Saf fonksiyonlar: `classify_lean_error(text)` → (priority, cls) veya (None, None);
`classify_coq_error(text)` aynı sözleşmeyle Coq sinyallerini kullanır (syntax/
type ortak sınıflandırıcıya düşer). Dış bağımlılık yok; verify_delivery'nin
run_lean_proof / run_lake_build FAIL detail'lerine `[sınıf]` etiketi ekler
(K9 hata ayıklayıcısı).
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
        r"term has type",
    ]),
    # 3 — unsolved: ispat tamamlanmamış (hedef açık).
    ("unsolved", 3, [
        r"unsolved goals",
        r"tactic .*failed",
        r"no goals to be solved",
        r"failed to prove",
        r"unsolved",
    ]),
    # 4 — proof_gap: Coq `Admitted` ispat boşluğu.
    ("proof_gap", 4, [
        r"\bAdmitted\b",
        r"proof contains",
        r"proof is incomplete",
    ]),
    # 5 — axiom: Coq top-level `Axiom` bildirimi.
    ("axiom", 5, [
        r"^\s*Axiom\b",
        r"\bAxiom\b\s+[A-Za-z_]",
    ]),
    # 6 — linter: --wfail uyarıları (derlenir ama kapı fail).
    ("linter", 6, [
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


def _classify(text):
    """Ortak sınıflandırıcı: en yüksek öncelikli (en küçük numaralı) sınıf."""
    if not text:
        return None, None
    for cls, pri, rx in _PATTERNS:
        if rx.search(text):
            # ERROR_CLASSES sırası zaten öncelik sırasıdır — ilk eşleşen
            # en köklü hata; daha düşük priority'li sınıflara bakma.
            return pri, cls
    return None, None


def classify_lean_error(text):
    """Lean derleme çıktısını hata sınıfına göre sınıflandırır.

    Döndürür: (priority, cls) — en yüksek öncelikli (en küçük numaralı) sınıf;
    eşleşme yoksa (None, None). Çıktı birden çok sınıf içeriyorsa daha köklü
    hata kazanır (skill error-priority: syntax > type > unsolved > linter).
    """
    return _classify(text)


def classify_coq_error(text):
    """Coq derleme çıktısını sınıflandırır (proof_gap/axiom + ortak dilim).

    `Admitted` → (4, "proof_gap"); top-level `Axiom` → (5, "axiom") —
    syntax/type/unsolved/linter ortak sınıflandırıcıdan düşer.
    """
    return _classify(text)


def tag_error_detail(detail, lang="lean"):
    """FAIL detail'ine `[sınıf]` ön eki ekler; sınıf yoksa olduğu gibi döner.

    lang="coq" ise classify_coq_error kullanılır (proof_gap/axiom etiketleri).
    Örn: "lake build hatası: unsolved goals" → "[unsolved] lake build hatası: …"
    """
    classifier = classify_coq_error if lang == "coq" else classify_lean_error
    _pri, cls = classifier(detail)
    if cls is None:
        return detail
    return f"[{cls}] {detail}"


def tag_lean_detail(detail):
    """K9 Lean FAIL detail'ine `[sınıf]` ön eki ekler; sınıf yoksa aynı kalır."""
    return tag_error_detail(detail, "lean")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        pri, cls = classify_lean_error(sys.argv[1])
        print(f"priority={pri} class={cls}")
    else:
        print("kullanım: python3 classify_lean_error.py '<lean çıktısı>'")
        sys.exit(2)