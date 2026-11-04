#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""branch_cleanup_advisor.py — dal silme önerisi, KAPSAM KANITIYLA (salt-okunur).

Squash/rebase merge'ler dal commit'lerini ana hatta bırakmaz: `git branch
--merged` boş döner, PR "MERGED" görünür ama dal ucu main'in atası değildir.
Bu yüzden "silebilir miyim?" sorusu commit soyundan değil **içerikten** yanıtlanır.
Her dal için kanıt üretilir:

  ANCESTOR  — dal ucu base'in atası (fast-forward merge); silmek kayıpsız.
  EMPTY     — dal base ile aynı uçta; taşıdığı commit yok.
  SAME_TREE — ağaç base ile birebir aynı (commit'ler farklı, içerik aynı).
  CONTENT   — dalın DEĞİŞTİRDİĞİ her dosyanın blob'u base'de birebir aynı
              (squash/rebase sonrası içerik yerleşmiş); dosya sayısı raporlanır.
  PATCH_ID  — `git cherry` base'de eşleşmeyen commit bırakmıyor (yama düzeyinde
              kapsanmış); upstream/toplam commit sayısı raporlanır.
  MERGE     — içerik tam eşleşmiyor ama dalda merge commit'i var; `git cherry`
              merge'leri listelemediği için yama eşleşmesi kanıt sayılmaz →
              REVIEW.
  PARTIAL   — dosyaların bir kısmı base'de aynı, kalanı farklı → REVIEW.
  UNIQUE    — base'de karşılığı olmayan içerik/commit var → KEEP.

Kararlar: ANCESTOR/EMPTY/SAME_TREE/CONTENT/PATCH_ID → DELETE,
MERGE/PARTIAL → REVIEW, UNIQUE → KEEP. Araç HİÇBİR ŞEY SİLMEZ; yalnız `git push <remote> --delete <dal>`
komutunu yazdırır (--commands).

Kullanım:
  python3 _calisma/CIKTI/branch_cleanup_advisor.py                  # tablo
  python3 _calisma/CIKTI/branch_cleanup_advisor.py --json            # tek JSON doküman
  python3 _calisma/CIKTI/branch_cleanup_advisor.py --commands        # silme komutları
  python3 _calisma/CIKTI/branch_cleanup_advisor.py --base origin/main --remote origin

Çıkış kodları: 0 ölçüm tamam (öneriler advisory) · 2 ortam/ölçüm hatası
(git yok, repo değil, base çözülemiyor) — sessiz "silebilirsin" yok.
"""
import argparse
import json
import re
import subprocess
import sys

DELETE_EVIDENCE = ("ANCESTOR", "EMPTY", "SAME_TREE", "CONTENT", "PATCH_ID")


class GitError(RuntimeError):
    pass


def git(*args, cwd=None, allow_fail=False):
    """git komutunu koşturur; döner: (rc, stdout, stderr)."""
    try:
        proc = subprocess.run(["git"] + list(args), cwd=cwd,
                              capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise GitError(f"git bulunamadı: {exc}") from exc
    if proc.returncode != 0 and not allow_fail:
        first = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise GitError(f"git {' '.join(args)} rc={proc.returncode}: "
                       f"{first[0] if first else '(çıktı yok)'}")
    return proc.returncode, proc.stdout, proc.stderr


def resolve_base(repo, base):
    rc, out, _ = git("rev-parse", "--verify", f"{base}^{{commit}}",
                     cwd=repo, allow_fail=True)
    if rc != 0:
        raise GitError(f"base çözülemiyor: {base!r} (git fetch --prune çalıştırın)")
    return out.strip()


def list_branches(repo, remote, base):
    """Uzak dallar (base ve <remote>/HEAD hariç) — uç sha + tarih ile."""
    rc, out, _ = git("for-each-ref",
                     "--format=%(refname:short)|%(objectname)|%(committerdate:iso-strict)",
                     f"refs/remotes/{remote}", cwd=repo)
    rows = []
    prefix = f"{remote}/"
    base_short = base[len(prefix):] if base.startswith(prefix) else base
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) != 3:
            continue
        ref, sha, date = parts
        if not ref.startswith(prefix):
            continue
        name = ref[len(prefix):]
        if not name or name == "HEAD" or name == base_short:
            continue
        rows.append({"branch": name, "sha": sha, "date": date})
    return sorted(rows, key=lambda r: r["branch"])


def _blob(repo, rev, path):
    rc, out, _ = git("rev-parse", "--verify", f"{rev}:{path}", cwd=repo,
                     allow_fail=True)
    return out.strip() if rc == 0 else None


def content_evidence(repo, base_sha, merge_base, branch_sha):
    """Dalın değiştirdiği dosyaların base'deki blob'larıyla karşılaştırması.

    Dosya kümesi **merge-base'e göre** çıkarılır (dalın NE getirdiği); base ile
    doğrudan diff alınırsa içeriği zaten base'de olan dosyalar hiç görünmez ve
    squash-merge kanıtı kaybolur. Karşılaştırma yönü: dal blob'u ↔ base blob'u.

    Döner: (aynı, farklı, base'de yok, toplam, örnek_dosyalar).
    """
    _, out, _ = git("diff", "--name-only", merge_base, branch_sha, cwd=repo)
    paths = [p for p in out.splitlines() if p]
    if not paths:
        return 0, 0, 0, 0, []
    same = changed = missing = 0
    differing = []
    for path in paths:
        b_blob = _blob(repo, branch_sha, path)
        base_blob = _blob(repo, base_sha, path)
        if base_blob is None:
            missing += 1
            differing.append(path)
        elif b_blob == base_blob:
            same += 1
        else:
            changed += 1
            differing.append(path)
    return same, changed, missing, len(paths), sorted(differing)[:5]


def analyze_branch(repo, row, base_sha):
    """Tek dal için kanıt + öneri."""
    info = {
        "branch": row["branch"],
        "tip": row["sha"][:8],
        "date": row["date"],
        "ahead": 0,
        "behind": 0,
        "files_total": 0,
        "files_identical": 0,
        "files_changed": 0,
        "files_missing_in_base": 0,
        "unique_commits": 0,
        "upstream_commits": 0,
        "evidence": None,
        "recommend": None,
        "reason": None,
        "sample_paths": [],
    }

    rc, out, _ = git("rev-list", "--count", f"{base_sha}..{row['sha']}",
                     cwd=repo, allow_fail=True)
    info["ahead"] = int(out.strip() or 0) if rc == 0 else 0
    rc, out, _ = git("rev-list", "--count", f"{row['sha']}..{base_sha}",
                     cwd=repo, allow_fail=True)
    info["behind"] = int(out.strip() or 0) if rc == 0 else 0

    ancestor = git("merge-base", "--is-ancestor", row["sha"], base_sha,
                   cwd=repo, allow_fail=True)[0] == 0
    if row["sha"] == base_sha:
        # Uç birebir base: taşınan commit yok (ANCESTOR'dan daha kesin kanıt).
        info["evidence"] = "EMPTY"
        info["reason"] = "dal ucu base ile aynı commit; taşıdığı commit yok"
    elif ancestor:
        info["evidence"] = "ANCESTOR"
        info["reason"] = "dal ucu base'in atası (fast-forward merge)"
    elif info["ahead"] == 0:
        # Base'in gerisinde: yeni commit yok, ağaç aynıysa kayıpsız.
        rc_tree = git("diff", "--quiet", base_sha, row["sha"], "--",
                      cwd=repo, allow_fail=True)[0]
        if rc_tree == 0:
            info["evidence"] = "SAME_TREE"
            info["reason"] = "dal ucu base ile aynı ağaçta; yeni commit yok"
        else:
            info["evidence"] = "KEEP"
            info["reason"] = ("base'in gerisinde ve ağacı farklı — önce "
                              "fetch/inceleme gerekir")
    else:
        rc_mb, mb, _ = git("merge-base", base_sha, row["sha"], cwd=repo,
                           allow_fail=True)
        merge_base = mb.strip() if rc_mb == 0 else ""
        if not merge_base:
            info["evidence"] = "UNRELATED"
            info["reason"] = "base ile ortak ata yok — içerik karşılaştırılamaz"
            info["recommend"] = "KEEP"
            return info
        same, changed, missing, total, sample = content_evidence(
            repo, base_sha, merge_base, row["sha"])
        info.update({"files_total": total, "files_identical": same,
                     "files_changed": changed, "files_missing_in_base": missing,
                     "sample_paths": sample})

        _, cherry, _ = git("cherry", base_sha, row["sha"], cwd=repo,
                           allow_fail=True)
        lines = [c for c in cherry.splitlines() if c.strip()]
        info["unique_commits"] = sum(1 for c in lines if c.startswith("+"))
        info["upstream_commits"] = sum(1 for c in lines if c.startswith("-"))
        # `git cherry` MERGE commit'lerini listelemez: birleştirme sırasında
        # çözülen içerik yalnız merge commit'inde yaşar. Bu yüzden yama eşleşmesi
        # tek başına kapsam kanıtı DEĞİL — içerik tam eşleşmiyorsa REVIEW.
        rc_m, merges, _ = git("rev-list", "--merges", "--count",
                              f"{base_sha}..{row['sha']}", cwd=repo,
                              allow_fail=True)
        merge_ahead = int(merges.strip() or 0) if rc_m == 0 else 0

        if total == 0:
            info["evidence"] = "PATCH_ID"
            info["reason"] = ("dal dosya değiştirmiyor (yalnız merge/boş "
                              "commit) — içerik kapsanmış")
        elif same == total:
            info["evidence"] = "CONTENT"
            info["reason"] = (f"{same}/{total} dosya base'de birebir aynı "
                              "(squash/rebase sonrası içerik yerleşmiş)")
        elif merge_ahead > 0:
            info["evidence"] = "MERGE"
            info["reason"] = (f"dalda {merge_ahead} merge commit var; içerik "
                              f"tam eşleşmiyor ({same}/{total}) — yama "
                              "eşleşmesi tek başına kanıt değil")
        elif info["unique_commits"] == 0 and info["upstream_commits"] > 0:
            info["evidence"] = "PATCH_ID"
            info["reason"] = (f"{info['upstream_commits']} yama base'de "
                              "eşleşiyor; benzersiz commit yok")
        elif same > 0:
            info["evidence"] = "PARTIAL"
            info["reason"] = (f"{same}/{total} dosya aynı, {changed} farklı, "
                              f"{missing} base'de yok")
        else:
            info["evidence"] = "UNIQUE"
            info["reason"] = (f"{total} dosya base'de karşılıksız, "
                              f"{info['unique_commits']} benzersiz commit")

    if info["evidence"] == "UNRELATED":
        info["recommend"] = "KEEP"
    elif info["evidence"] in DELETE_EVIDENCE:
        info["recommend"] = "DELETE"
    elif info["evidence"] in ("PARTIAL", "MERGE"):
        info["recommend"] = "REVIEW"
    else:
        info["recommend"] = "KEEP"
    return info


def analyze(repo, base, remote):
    base_sha = resolve_base(repo, base)
    rows = [analyze_branch(repo, row, base_sha)
            for row in list_branches(repo, remote, base)]
    return base_sha, rows


def build_payload(repo, base, remote, base_sha, rows, with_commands):
    summary = {"delete": 0, "review": 0, "keep": 0}
    for row in rows:
        key = row["recommend"].lower()
        summary[key] = summary.get(key, 0) + 1
    commands = [f"git push {remote} --delete {row['branch']}"
                for row in rows if row["recommend"] == "DELETE"]
    return {
        "verdict": "ACTION" if summary["delete"] else "OK",
        "repo": repo,
        "base": base,
        "base_sha": base_sha,
        "remote": remote,
        "total_branches": len(rows),
        "summary": summary,
        "branches": rows,
        "delete_commands": commands if with_commands else [],
    }


def _pad(text, width):
    text = "" if text is None else str(text)
    return text + " " * max(0, width - len(text))


def format_report(payload):
    lines = [f"dal temizlik önerisi — {payload['repo']}",
             f"  base: {payload['base']} ({payload['base_sha'][:12]}) · "
             f"uzak: {payload['remote']} · {payload['total_branches']} dal"]
    lines.append("")
    order = {"DELETE": 0, "REVIEW": 1, "KEEP": 2}
    rows = sorted(payload["branches"],
                  key=lambda r: (order.get(r["recommend"], 9), r["branch"]))
    bw = max([len(r["branch"]) for r in rows] + [6])
    for row in rows:
        evidence = row["evidence"] or "-"
        files = (f"{row['files_identical']}/{row['files_total']}"
                 if row["files_total"] else "-")
        lines.append(
            f"  {_pad(row['recommend'], 6)}  {_pad(evidence, 9)}  "
            f"ahead={str(row['ahead']):>3} behind={str(row['behind']):>4}  "
            f"dosya={files:>7}  {_pad(row['branch'], bw)}  "
            f"{row['date'][:10]}")
        lines.append(f"          ↳ {row['reason']}")
        if row["sample_paths"] and row["recommend"] != "DELETE":
            lines.append(f"          örnek yollar: {', '.join(row['sample_paths'])}")

    s = payload["summary"]
    lines.append("")
    lines.append(f"Özet: {s['delete']} DELETE · {s['review']} REVIEW · "
                 f"{s['keep']} KEEP")
    if payload["delete_commands"]:
        lines.append("")
        lines.append("Silme komutları (araç SİLMEZ; elle onaylayın):")
        lines.extend(f"  {cmd}" for cmd in payload["delete_commands"])
    else:
        lines.append("Silme komutları için: --commands")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="git çalışma ağacı (varsayılan: .)")
    ap.add_argument("--base", default="origin/main",
                    help="referans dal (varsayılan: origin/main)")
    ap.add_argument("--remote", default="origin", help="uzak adı (varsayılan: origin)")
    ap.add_argument("--json", action="store_true", help="tek JSON doküman bas")
    ap.add_argument("--commands", action="store_true",
                    help="DELETE dalar için `git push --delete` komutlarını yazdır")
    args = ap.parse_args(argv)

    try:
        if not re.match(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$", args.base):
            raise GitError(f"base biçimi geçersiz: {args.base!r}")
        base_sha, rows = analyze(args.repo, args.base, args.remote)
    except GitError as exc:
        if args.json:
            print(json.dumps({"verdict": "ERROR", "error": str(exc)},
                             indent=2, ensure_ascii=False))
        print(f"HATA: {exc}", file=sys.stderr)
        sys.exit(2)

    payload = build_payload(args.repo, args.base, args.remote, base_sha, rows,
                            args.commands)
    # Özet/verdict teşhis satırı stderr'de: --json stdout'u tek doküman kalır.
    s = payload["summary"]
    print(f"dal temizlik: {s['delete']} DELETE · {s['review']} REVIEW · "
          f"{s['keep']} KEEP — {payload['verdict']}", file=sys.stderr)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(format_report(payload))
    sys.exit(0)


if __name__ == "__main__":
    main()
