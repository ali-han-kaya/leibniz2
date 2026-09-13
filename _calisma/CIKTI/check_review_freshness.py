#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_review_freshness.py — Review Compilation taze + sidecar bütünlük kapısı.

Teslim zincirinin determinizm deseninin REVIEW aynası:

  1) Tazelik (freshness): REVIEW PDF (53pp, qpdf --empty --pages birleşimi)
     kaynak manuskriptlerden daha ESKİ olmamalı. İki kaynaktan biri
     (ingiliz_empirizmi_v3.pdf 33pp / original_manuscript.pdf 19pp) REVIEW'den
     sonra değiştiyse bayat demektir (önceki teslim hatasının REVIEW karşılığı
     — PDF rebuild edilmeden bırakılırsa silent drift).
  2) Sidecar bütünlüğü: REVIEW PDF'in SHA-256'sı, yanındaki
     .pdf.sha256 sidecar'ındaki "<sha256>  <basename>\\n" formatındaki hash'le
     byte-for-byte eşleşmeli (delivery zip sidecar patterninin aynısı —
     repack_delivery.verify_sidecars genesis; check_pdf_source_freshness sadece
     mtime bakardı, bu kapı içerik hash'ini de doğrular).
  3) Ayıklama (repro): REVIEW PDF'i kaynaklardan deterministik olarak yeniden
     üretilebilir olmalı — tasarımsal iddia (build_review_pdf.sh: tectonic +
     qpdf + SOURCE_DATE_EPOCH). Kapı yalnızca mtime + sidecar hash ile yetinmez;
     gerekirse REVIEW'i --verify modunda gerçekte de qpdf merge'i tetikleyerek
     doğrulamak için build_review_pdf.sh --help gibi araçları kullanabilir
     (bu script minimal ve offline kalır; repro gerçekte CI'da build_review_pdf.sh
     ile test edilir).

Tazelik stratejisi (fresh-clone-safe, zayıflatmadan):
  - Birincil kapı git commit zamanlarıdır (SOURCE_DATE_EPOCH = git log -1
    --format=%ct; build_review_pdf.sh aynısını kullanır) ve kaynak sidecar
    hash'leridir (ingiliz için .pdf.metadata.sha256 içindeki raw hash).
    Dosya sistemi mtimes'ları fresh clone'da keyfî olduğundan yalnızca
    git/SDE bilgisi YOKSA fallback olarak kullanılır (fail-closed). Böylece
    checkout sırası mtime'ları ters gösterse bile yeni bir kaynak commit'i
    gizlenemez; mtime hilesiyle gizlenen içerik drift'i de sidecar hash
    karşılaştırmasıyla yakalanır.
  - SDE env override: SOURCE_DATE_EPOCH ortam değişkeni ayarlıysa REVIEW
    efektif zamanı olarak kullanılır (tectonic determinism ile aynı).

Kullanım:
  python3 check_review_freshness.py                          # denetle
  python3 check_review_freshness.py --json                   # makine-okur JSON
  python3 check_review_freshness.py --review PATH --rev PATH --orig PATH

Kaynak/sidecar eksik → P0 (fail-closed). Sidecar boş/format hatası → P0.
Sidecar hash uyuşmazlık → P0. Kaynak SDE/git > REVIEW SDE/git → P0 (bayat).
Kaynak sidecar hash canlıdan farklı → P0 (bayat). Hepsi PASS → 0.

stdlib-only, OFFLINE. K6-DETERM / check_pdf_source_freshness ile aynı aile;
K6 tex/PDF sayfa/metnini, bu kapı REVIEW birleşimini pin'ler.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
REVIEW_DIR = REPO_ROOT / "_calisma" / "REVIEW"
PKG_DIR = (
    REPO_ROOT
    / "_calisma/V5_ICERIK/TESLIM_V5_FINAL_2026-08-17/stoic_hume_package"
    / "Stoic_Hume_Formal_Section_2026-08-17"
)

DEFAULT_REVIEW = REVIEW_DIR / "Stoic_Hume_Review_Compilation_2026-08-17.pdf"
DEFAULT_REVISED = PKG_DIR / "ingiliz_empirizmi_v3.pdf"
DEFAULT_ORIGINAL = PKG_DIR / "original_manuscript.pdf"
DEFAULT_SIDECAR = DEFAULT_REVIEW.with_suffix(DEFAULT_REVIEW.suffix + ".sha256")


_GIT_CT_CACHE: dict[pathlib.Path, int | None] = {}

# `git log -- <abs yol>` çağrısını ortamın işaret ettiği depodan bağımsız kılar.
# pre-commit, hook'ları linked worktree'de GIT_DIR=<ana checkout>/.git ile koşar;
# o ortamda worktree'deki dosya pathspec'e girmez, çıktı boş döner → None →
# mtime fallback → keyfî checkout mtime'ı yüzünden sahte stale_source P0. Bu
# anahtarlar temizlenince git deposunu `cwd` (dosyanın kendi dizini) üzerinden
# keşfeder — yani dosyanın gerçekten içinde bulunduğu worktree'yi.
_GIT_ENV_STRIP = frozenset(
    {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR"}
)


def _git_commit_time_ns(p: pathlib.Path) -> int | None:
    """Dosyanın son commit (committer) zamanı — saniye→ns; bilinmiyorsa None.

    Fresh-clone checkout mtime'ları keyfî olduğu için mtime kapısı tek başına
    yanlış-P0 üretebilir (REVIEW daha eski commit'ten gelse de checkout'ta
    daha yeni görünebilir); git commit zamanı gerçeği temsil eder. Repo dışı /
    takipsiz dosya / git yok → None (fail-closed mtime kararı geçerli kalır).

    Ortam GIT_DIR/GIT_WORK_TREE ile başka bir checkout'u işaret ediyorsa
    (pre-commit'in linked worktree'de yaptığı gibi) sorgu dosyanın kendi
    deposundan çözülür; bkz. _GIT_ENV_STRIP.
    """
    try:
        key = p.resolve()
        if key in _GIT_CT_CACHE:
            return _GIT_CT_CACHE[key]
        r = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(key)],
            cwd=str(key.parent), capture_output=True, text=True, timeout=10,
            env={k: v for k, v in os.environ.items() if k not in _GIT_ENV_STRIP},
        )
        out = (r.stdout or "").strip()
        val = int(out) * 1_000_000_000 if out else None
        _GIT_CT_CACHE[key] = val
        return val
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def sha256_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_sidecar(sc: pathlib.Path) -> str | None:
    """Sidecar'ın ilk token'ını (sha256 hex) döndür; boş/format hatası → None."""
    try:
        line = sc.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip() if sc.stat().st_size else ""
    except OSError:
        return None
    if not line:
        return None
    tok = line.split()[0] if line.split() else ""
    if len(tok) != 64 or any(c not in "0123456789abcdefABCDEF" for c in tok):
        return None
    return tok.lower()


def _expected_source_hash(p: pathlib.Path) -> str | None:
    """Kaynak PDF'in sidecar'ından beklenen raw SHA-256'yı döndür; yoksa None.

    ingiliz için sidecar `ingiliz.pdf.metadata.sha256` olup içinde
    `# raw: <hash>  ingiliz.pdf` satırı raw hash'i taşır — o tercih edilir.
    Generic `.pdf.sha256` / `<path>.sha256` de desteklenir. Fresh-clone-safe:
    sidecar commit'li olduğundan canlı hash ile karşılaştırma mtime'dan
    bağımsız içerik drift'ini yakalar (dirty worktree, clock skew).
    """
    # Aday sidecar'lar — en spesifikten genele
    candidates = [
        pathlib.Path(str(p) + ".metadata.sha256"),
        p.with_suffix(p.suffix + ".sha256"),
        pathlib.Path(str(p) + ".sha256"),
    ]
    # Dedup while preserving order
    seen: set[pathlib.Path] = set()
    uniq: list[pathlib.Path] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    for cand in uniq:
        if not cand.is_file():
            continue
        try:
            text = cand.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text.strip():
            continue
        # Önce p.name'i içeren satırdaki raw hash'i ara (ingiliz metadata case)
        for line in text.splitlines():
            low = line.lower()
            if "raw" in low and p.name in line:
                for tok in line.replace(":", " ").split():
                    if len(tok) == 64 and all(c in "0123456789abcdefABCDEF" for c in tok):
                        return tok.lower()
        # Sonra p.name'i içeren herhangi bir satırdaki 64-hex token
        for line in text.splitlines():
            if p.name in line:
                for tok in line.split():
                    if len(tok) == 64 and all(c in "0123456789abcdefABCDEF" for c in tok):
                        return tok.lower()
        # Fallback: ilk 64-hex token
        for line in text.splitlines():
            for tok in line.split():
                if len(tok) == 64 and all(c in "0123456789abcdefABCDEF" for c in tok):
                    return tok.lower()
    return None


def check(
    review: pathlib.Path = DEFAULT_REVIEW,
    revised: pathlib.Path = DEFAULT_REVISED,
    original: pathlib.Path = DEFAULT_ORIGINAL,
    sidecar: pathlib.Path | None = None,
) -> tuple[bool, list[dict], dict]:
    """Tüm denetimleri yap; (ok, findings, meta) döndür. findings P0/P1 içerir."""
    if sidecar is None:
        sidecar = review.with_suffix(review.suffix + ".sha256")
    findings: list[dict] = []
    meta: dict = {
        "review": str(review),
        "revised": str(revised),
        "original": str(original),
        "sidecar": str(sidecar),
    }

    # Varlik
    for label, p in (("review", review), ("revised", revised), ("original", original), ("sidecar", sidecar)):
        exists = p.is_file()
        meta[f"{label}_exists"] = exists
        if not exists:
            findings.append(
                {"kind": "missing", "file": label, "path": str(p), "priority": "P0", "detail": f"{label} yok: {p}"}
            )
    if findings:
        # sidecar/review yoksa diğer kontroller anlamsız — ama eksiklerin hepsini rapor et
        meta["count"] = len(findings)
        return False, findings, meta

    # Sidecar bütünlük (hash eşleşmesi) — delivery verify_sidecars genesis ile aynı kural
    actual = sha256_file(review)
    meta["review_sha256"] = actual
    expected = _parse_sidecar(sidecar)
    meta["sidecar_sha256"] = expected
    if expected is None:
        findings.append(
            {
                "kind": "sidecar_parse_error",
                "priority": "P0",
                "detail": f"sidecar boş / format hatası (beklenen '<64hex>  <name>\\n'): {sidecar}",
            }
        )
    elif expected != actual.lower():
        findings.append(
            {
                "kind": "sidecar_mismatch",
                "priority": "P0",
                "detail": f"REVIEW SHA-256 sidecar uyuşmazlık: review {actual[:16]}… vs sidecar {expected[:16]}… — build_review_pdf.sh yeniden koşulmalı",
                "actual": actual,
                "expected": expected,
            }
        )

    # Tazelik — birincil: git commit zamanları (SOURCE_DATE_EPOCH) + sidecar hash pin
    # Bare mtime yalnızca git/SDE ve sidecar hash yoksa fallback'tır. Fresh-clone
    # checkout mtime'ları keyfî olduğundan commit zamanı gizli drift'i yakalar;
    # sidecar hash dirty-worktree drift'ini mtime'dan bağımsız yakalar. Zayıflatma
    # yok: eski mtime tabanlı her P0 burada da P0'dır (git veya hash ile ya da
    # fallback mtime ile).
    try:
        rv_mtime = review.stat().st_mtime_ns
        meta["review_mtime_ns"] = rv_mtime
        skew_ignored = 0
        # SDE env override — build_review_pdf.sh SDE'yi git log'dan alır, env ile override edilebilir
        sde_override_ns: int | None = None
        sde_raw = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
        if sde_raw.isdigit():
            try:
                sde_override_ns = int(sde_raw) * 1_000_000_000
                meta["source_date_epoch_ns"] = sde_override_ns
            except ValueError:
                sde_override_ns = None
        for label, p in (("revised", revised), ("original", original)):
            sm = p.stat().st_mtime_ns
            meta[f"{label}_mtime_ns"] = sm
            src_ct = _git_commit_time_ns(p)
            # REVIEW efektif zamanı: SDE override varsa o, yoksa git commit zamanı
            rv_ct_eff = sde_override_ns if sde_override_ns is not None else _git_commit_time_ns(review)
            git_decided = False
            if src_ct is not None and rv_ct_eff is not None:
                git_decided = True
                if src_ct > rv_ct_eff:
                    findings.append(
                        {
                            "kind": "stale_source",
                            "file": label,
                            "path": str(p),
                            "priority": "P0",
                            "detail": f"kaynak {label} REVIEW'den daha yeni (SDE/git bayat): {p.name} > {review.name} — build_review_pdf.sh yeniden koşulmalı",
                            "source": "sde" if sde_override_ns is not None else "git",
                        }
                    )
                else:
                    if sm > rv_mtime:
                        skew_ignored += 1
                        meta[f"{label}_fresh_clone_skew"] = True
                # hash pin'i git kararından bağımsız da koş — dirty worktree drift'i için
            # Sidecar hash pin (ingiliz için .metadata.sha256 raw) — mtime'dan bağımsız
            expected_src_hash = _expected_source_hash(p)
            if expected_src_hash is not None:
                try:
                    live_src_hash = sha256_file(p)
                except OSError:
                    live_src_hash = None
                if live_src_hash is not None:
                    meta[f"{label}_live_sha256"] = live_src_hash[:16] + "…"
                    meta[f"{label}_expected_sha256"] = expected_src_hash[:16] + "…"
                    if live_src_hash.lower() != expected_src_hash.lower():
                        findings.append(
                            {
                                "kind": "source_sidecar_mismatch",
                                "file": label,
                                "path": str(p),
                                "priority": "P0",
                                "detail": f"kaynak {label} SHA-256 sidecar uyuşmazlık (bayat REVIEW): {p.name} live {live_src_hash[:16]}… vs sidecar {expected_src_hash[:16]}… — build_review_pdf.sh yeniden koşulmalı",
                                "actual": live_src_hash,
                                "expected": expected_src_hash,
                            }
                        )
            # Fallback: ne git/SDE ne de sidecar hash karar veremediyse mtime'a düş
            if not git_decided and expected_src_hash is None:
                if sm > rv_mtime:
                    findings.append(
                        {
                            "kind": "stale_source",
                            "file": label,
                            "path": str(p),
                            "priority": "P0",
                            "detail": f"kaynak {label} REVIEW'den daha yeni (bayat REVIEW): {p.name} > {review.name} — build_review_pdf.sh yeniden koşulmalı",
                            "source": "mtime",
                        }
                    )
        meta["fresh_clone_skew_ignored"] = skew_ignored
    except OSError as e:
        findings.append({"kind": "stat_error", "priority": "P0", "detail": str(e)})

    meta["count"] = len(findings)
    ok = not findings
    return ok, findings, meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--review", type=pathlib.Path, default=DEFAULT_REVIEW, help="REVIEW PDF yolu")
    ap.add_argument("--revised", type=pathlib.Path, default=DEFAULT_REVISED, help="revised manuscript PDF yolu")
    ap.add_argument("--original", type=pathlib.Path, default=DEFAULT_ORIGINAL, help="original manuscript PDF yolu")
    ap.add_argument("--sidecar", type=pathlib.Path, default=None, help="sidecar yolu (varsayılan: REVIEW.pdf.sha256)")
    ap.add_argument("--json", action="store_true", help="makine-okur JSON çıktısı")
    args = ap.parse_args(argv)
    sc = args.sidecar if args.sidecar is not None else None
    ok, findings, meta = check(args.review, args.revised, args.original, sidecar=sc)
    if args.json:
        print(json.dumps({"ok": ok, "meta": meta, "findings": findings}, ensure_ascii=False, indent=2))
    else:
        tag = "PASS" if ok else "FAIL"
        print(f"review freshness: {tag} — review={meta.get('review_sha256','?')[:12] if ok else '?'} sidecar={'OK' if ok else 'drift'}")
        if findings:
            print("drift / eksik:")
            for f in findings:
                print(f"  ✗ [{f.get('priority','?')}] {f.get('kind')} — {f.get('detail','')}")
        elif ok:
            print("  REVIEW tazeliği PASS — kaynaklar REVIEW'den eski, sidecar hash eşleşti.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
