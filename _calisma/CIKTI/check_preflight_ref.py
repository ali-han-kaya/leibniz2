#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_preflight_ref.py — Preflight: missing source ref branch resolver.

Ne kanıtlar
----------
Bir merge/karşılaştırma isteğinde kaynak (source) ref belirtilmemiş/bulunamazsa,
bu araç tüm neighborhood dalları tarar ve her birinin target'a göre nasıl
"dışarıda" (not-reachable) olduğu raporlar. Kullanıcıya "doğru dallı"yı
açıkça göstermek için.

Kullanım:
    python3 _calisma/CIKTI/check_preflight_ref.py TARGET_BRANCH [--source SOURCE_REF]
    python3 _calisma/CIKTI/check_preflight_ref.py TARGET_BRANCH --source feature/xyz
    python3 _calisma/CIKTI/check_preflight_ref.py main --source working

Exit codes:
    0 = OK (source ref bulundu veya dallar listelendi)
    1 = HATA (kullanım hatası)
    2 = Çözülemeyen ref (hedef de çözülemez)
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


class GitError(RuntimeError):
    """git komutu başarısız oldu / ref çözülemedi."""


def git(args, cwd=ROOT):
    """git çalıştırır. (stdout) döner; hata hâlinde GitError yükselir."""
    proc = subprocess.run(
        ["git"] + list(args), cwd=cwd, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise GitError(
            "git %s → rc=%d %s" % (" ".join(args), proc.returncode, proc.stderr.strip())
        )
    return proc.stdout.strip()


def try_git(args, cwd=ROOT):
    """git çalıştırır, hata hâlinde None (sessiz ölçüm yutması)."""
    try:
        return git(args, cwd)
    except GitError:
        return None


def _int(text):
    """'12\n' → 12; ölçülemezse None."""
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def resolve_ref(ref, cwd=ROOT):
    """Verilen ref'i çözümle; eksikse GitError fırlat."""
    return try_git(["rev-parse", "--verify", ref], cwd)


def branch_commits_outside_target(branch, target, cwd=ROOT):
    """Belirtilen branch'te target'a ulaşamayan (not-reachable) commit sayısını hesaplar."""
    # rev-list --count branch..target: target'ta olan, branch'de olmayanlar
    # rev-list --count target..branch: branch'ta target'te olmayanlar (yeni eklemeler)
    # Kullanıcı "target'a ulaşamayan commit" istiyor yani branch..target dışındakiları
    count = _int(try_git(["rev-list", "--count", "%s..%s" % (branch, target)], cwd))
    return count


def list_branches_outside_target(target, cwd=ROOT):
    """Tüm local dalları tara ve her birinin target'a göre dışarıdaki commit sayısını hesapla."""
    branches = []

    # Tüm local branch'leri getir
    text = try_git(["for-each-ref", "--format=%(refname:short)", "refs/heads/"], cwd)
    if text is None:
        return branches

    for branch in text.splitlines():
        if not branch.strip():
            continue
        branch = branch.strip()
        outside = branch_commits_outside_target(branch, target, cwd)
        branches.append({
            "branch": branch,
            "outside_count": outside if outside is not None else -1,
        })

    # Sırala: dışarıdaki commit sayısı azlıdan çokluğa
    branches.sort(key=lambda b: (b["outside_count"] if b["outside_count"] >= 0 else 999, b["branch"]))
    return branches


def main():
    ap = argparse.ArgumentParser(
        description="Preflight: missing source ref branch resolver.\n"
                    "Eğer source ref belirtilmemişse, tüm dalları tarayarak hangi dallın "
                    "target'a göre en fazla/yok commit olduğunu gösterir.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("target", help="Hedef dal (ör. main, reword-working)")
    ap.add_argument(
        "--source", default=None,
        help="Kaynak ref (ör. feature/xyz, working). Belirtilmediğinde preflight "
             "tüm dalları listeler.",
    )
    ap.add_argument(
        "--root", default=ROOT, help="Git deposu kökü (varsayılan: repo kökü)",
    )
    args = ap.parse_args()

    cwd = os.path.abspath(args.root)

    # Çalışma dizini bir git repo mu?
    try:
        git(["rev-parse", "--show-toplevel"], cwd)
    except GitError:
        print("HATA: --root bir git deposu değil: %s" % cwd, file=sys.stderr)
        return 1

    target = args.target.strip()
    source = (args.source or "").strip() if args.source else ""

    # 1) Source ref verilmişse doğrulama yap
    if source:
        try:
            resolved = resolve_ref(source, cwd)
            if resolved:
                print("OK: Kaynak ref çözüldü: %s → %s" % (source, resolved))
                return 0
            else:
                print("HATA: Kaynak ref çözülemedi: %s" % source, file=sys.stderr)
                return 2
        except GitError:
            pass  # Düşüş → source verilmiş ama çözülemedi → preflight tetikle

    # 2) Source verilmemiş veya çözülemedi → preflight: tüm dalları listle
    print("PREFLIGHT: Kaynak ref eksik/çözülemiyor — tüm dallar taranıyor...")
    print("Hedef: %s" % target)
    print()

    branches = list_branches_outside_target(target, cwd)

    if not branches:
        print("UYARI: Hedef '%s' altında hiç dallan bulunamadı." % target, file=sys.stderr)
        return 2

    print("Her dallın hedef'e göre 'dışarıdaki' (not-reachable) commit sayısı:")
    print("-" * 70)
    for b in branches:
        name = b["branch"]
        cnt = b["outside_count"]
        if cnt >= 0:
            status = "%d commit" % cnt if cnt != 1 else "1 commit"
            if cnt == 0:
                status = "0 commit (hedefin içinde)"
            print("  %s: %s" % (name, status))
        else:
            print("  %s: ölçülemedi" % name)

    # "En uygun" dalı belirle: en az dışarıdaki commit sayısı olan
    best = branches[0]
    print()
    print("ÖNERİ: Hedefin '%s' ile en çok uyumlu dal: %s" % (target, best["branch"]))
    if best["outside_count"] == 0:
        print("  → Bu dal hedefin tamamen içinde; merge NO-OP olacaktır.")
    elif best["outside_count"] == 1:
        print("  → Bu dala 1 yeni commit eklenmiş; fast-forward mümkün.")
    else:
        print("  → Bu dala %d yeni commit eklenmiş; merge gerekli." % best["outside_count"])

    print()
    print("NOT: 'dışarıdaki' = hedef dalına ulaşılamayan commit sayısı.")
    print("      Count 0 → dal hedefin içinde (zaten güncel).")
    print("      Count > 0 → dal hedefin önünde/güncel değil.")

    return 0


if __name__ == "__main__":
    sys.exit(main())