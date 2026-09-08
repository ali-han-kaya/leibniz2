#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ci_stats.py — son N CI run'ın success rate + average duration hesabı.

audit_live_ci_sync.py deseni: `gh` CLI üzerinden canlı GitHub Actions
verisine erişir (gh auth gerekli). Her run için job listesi çekilir,
duration = en erken job startedAt → en geç job completedAt aralığı
(parallel job'lar çakıştığı için toplam değil — wall-clock run süresi).

Hesaplanan ölçütler:
  - success rate : tamamlanan run'ların conclusion==success oranı
                   (in_progress hariç; --include-running ile dahil edilebilir)
  - average duration : son N tamamlanan run'ın ortalama süresi (dakika; sıfır
                       süreli run'lar hesaplamaya katılmaz — gh henüz job
                       zamanları doldurmamışsa '?' gösterilir)
  - run/job kırılımı : her run için job count + durum

Kullanım:
  python3 _calisma/CIKTI/ci_stats.py                # son 5 run, ana branch
  python3 _calisma/CIKTI/ci_stats.py --limit 10     # son 10 run
  python3 _calisma/CIKTI/ci_stats.py --branch test  # branch seç
  python3 _calisma/CIKTI/ci_stats.py --json         # makine-okur JSON

Çıkış kodları:
  0 — hesaplandı (run sayısı sınırın altında olsa bile)
  1 — gh hatası / run bulunamadı
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime

DEFAULT_LIMIT = 5
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

TABLE_HEADER = "| # | Run ID | Tarih (UTC) | Branch | Durum | Süre | Job | Özet |"
_TABLE_SEP = "|---|---|---|---|---|---|---|---|"
_MARK = {"success": "✅ success", "failure": "🔴 failure",
         "in_progress": "🔄 in_progress"}


def run_gh(args):
    """gh alt sürecini çalıştır; hata RuntimeError'a dönüşür."""
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout.strip()


def get_repo():
    return run_gh(["gh", "repo", "view", "--json", "nameWithOwner",
                   "-q", ".nameWithOwner"])


def list_runs(repo, branch, limit):
    out = run_gh(["gh", "run", "list", "--repo", repo,
                  "--branch", branch, "--limit", str(limit),
                  "--json", "databaseId,status,conclusion,createdAt"])
    return json.loads(out or "[]")


def run_duration(repo, run_id):
    """Job startedAt/completedAt'ten wall-clock duration (saniye); yoksa None."""
    out = run_gh(["gh", "run", "view", str(run_id), "--repo", repo,
                  "--json", "jobs", "-q", ".jobs"])
    jobs = json.loads(out or "[]")
    started, completed = [], []
    for j in jobs:
        if not j.get("startedAt"):
            continue
        try:
            s = datetime.strptime(j["startedAt"], _TS_FMT)
            c = datetime.strptime(j["completedAt"], _TS_FMT) \
                if j.get("completedAt") else None
        except ValueError:
            continue
        started.append(s)
        if c:
            completed.append(c)
    if not started or not completed:
        return None, len(jobs)
    return int((max(completed) - min(started)).total_seconds()), len(jobs)


def stats(runs, durations):
    """runs (her biri {status, conclusion}) + durations (run_id → (sec, jobs)) → özet."""
    total = len(runs)
    completed = [r for r in runs if r.get("status") == "completed"]
    success = [r for r in completed if r.get("conclusion") == "success"]
    # Sıfır süreli ve None süreli run'lar ortalamaya KATILMAZ (docstring):
    # gh henüz job zamanlarını doldurmamışsa ya da 0 sn'lik hızlı run varsa
    # ortalama bozulmaz. Başarı hesabı sıfır süreli run'ları yine sayar.
    secs = [d[0] for d in durations.values() if d and d[0] not in (None, 0)]
    avg_sec = sum(secs) / len(secs) if secs else None
    return {
        "runs_total": total,
        "runs_completed": len(completed),
        "runs_in_progress": total - len(completed),
        "runs_success": len(success),
        "success_rate": (len(success) / len(completed)) if completed else None,
        "avg_duration_s": avg_sec,
        "avg_duration_min": (avg_sec / 60) if avg_sec is not None else None,
    }


def markdown_rows(rows, repo):
    """§9 tablo satırları: [header, separator, row…]. Linkli Run ID, backtick
    branch, durum işaretleri, süre/job/title sütunları; title'daki `|` kaçar."""
    lines = [TABLE_HEADER, _TABLE_SEP]
    for i, r in enumerate(rows, 1):
        rid = r.get("id")
        date = (r.get("createdAt") or "")[:16].replace("T", " ")
        branch = r.get("branch") or ""
        status = r.get("status")
        concl = r.get("conclusion") or ""
        mark = _MARK.get(status, _MARK.get(concl, concl or status or "?"))
        title = (r.get("title") or "").replace("|", "\\|")
        lines.append(
            f"| {i} | [{rid}](https://github.com/{repo}/actions/runs/{rid}) | "
            f"{date} | `{branch}` | {mark} | {_fmt_dur(r.get('duration_s'))} | "
            f"{r.get('jobs')} | {title} |")
    return lines


def stats_line(s):
    """Success rate + avg duration tek satır özeti (§9 istatistik satırı)."""
    rate = s["success_rate"]
    if rate is None:
        rate_txt = "— (tamamlanan run yok)"
    else:
        rate_txt = (f"{rate*100:.0f}% ({s['runs_success']}/{s['runs_completed']} "
                    f"tamamlanan run)")
    if s["avg_duration_min"] is None:
        avg_txt = "— (yeterli tamamlanmış run yok)"
    else:
        avg_txt = (f"{s['avg_duration_min']:.1f} dk "
                   f"({s['avg_duration_s']:.0f} sn)")
    return (f"**İstatistik (ci_stats.py — otomatik):** {rate_txt} · {avg_txt}")


def update_doc_block(doc_path, table, stat):
    """docs/PRE_PUSH_DENETIM_RAPORU.md §9 bloğunu değiştir.

    Başlık (`## 9. …`) ve bitiş işareti (`**Kırılım analizi`, elle yazılır)
    arasındaki bölümü değiştirir; sonrası korunur. Fail-closed: başlık ya da
    bitiş işareti yoksa ValueError + dosya değişmeden kalır.
    """
    with open(doc_path, encoding="utf-8") as f:
        text = f.read()
    head_start = text.find("## 9.")
    if head_start == -1:
        raise ValueError("§9 başlığı yok")
    marker = "**Kırılım analizi"
    marker_start = text.find(marker, head_start)
    if marker_start == -1:
        raise ValueError("bitiş işareti yok (**Kırılım analizi)")
    block = text[head_start:marker_start]
    if TABLE_HEADER not in block:
        raise ValueError("§9 tablo başlığı yok")
    # Başlık + açıklama satırlarını koru; ESKİ tablo satırlarını at.
    intro_end = block.find("| # |")
    intro = block[:intro_end].rstrip()
    new_block = (intro + "\n\n" + table + "\n\n" + stat + "\n\n"
                 + text[marker_start:])
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(new_block)


def _fetch_stats(repo, branch, limit):
    """gh'dan run'ları + süreleri çeker; (runs, rows, durations, s) döner."""
    runs = list_runs(repo, branch, limit)
    durations = {}
    rows = []
    for r in runs:
        rid = r.get("databaseId")
        dur, jobs = run_duration(repo, rid)
        durations[rid] = (dur, jobs)
        rows.append({
            "id": rid,
            "branch": r.get("headBranch") or "",
            "createdAt": (r.get("createdAt") or "")[:16],
            "status": r.get("status"),
            "conclusion": r.get("conclusion") or ("" if r.get("status") == "in_progress" else "?"),
            "duration_s": dur,
            "jobs": jobs,
            "title": r.get("displayTitle") or "",
        })
    return rows, durations, stats(runs, durations)


def _print_markdown(rows, repo, s):
    print("\n".join(markdown_rows(rows, repo)))
    print("")
    print(stats_line(s))
    return 0


def _update_doc(doc, repo, branch, limit):
    """§9 bloğunu canlı veriyle değiştir; 0/1 döner (fail-closed)."""
    try:
        rows, _durations, s = _fetch_stats(repo, branch, limit)
        table = "\n".join(markdown_rows(rows, repo))
        update_doc_block(doc, table, stats_line(s))
        return 0
    except ValueError as e:
        print(f"HATA: §9 blok güncellenemedi ({e})", file=sys.stderr)
        return 1


def _fmt_dur(secs):
    if secs is None:
        return "—"
    m, s = divmod(int(secs), 60)
    return f"{m}m{s:02d}s"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help=f"run sayısı (varsayılan: {DEFAULT_LIMIT})")
    ap.add_argument("--branch", default=None,
                    help="branch (varsayılan: mevcut branch adı — gh run list --branch yoksa tümü)")
    ap.add_argument("--json", action="store_true", help="makine-okur JSON")
    ap.add_argument("--markdown", action="store_true",
                    help="§9 markdown tablosu + istatistik satırı bas (docs senkronu)")
    ap.add_argument("--update-doc", metavar="PATH",
                    help="docs/PRE_PUSH_DENETIM_RAPORU.md §9 bloğunu güncelle")
    args = ap.parse_args(argv)

    if args.limit < 1:
        print("HATA: --limit en az 1 olmalı", file=sys.stderr)
        return 2

    try:
        repo = get_repo()
        branch = args.branch or "main"
        limit = args.limit
        if args.update_doc and limit == DEFAULT_LIMIT:
            limit = 10  # §9 sözleşmesi: varsayılan son 10 run
        runs = list_runs(repo, branch, limit)
    except RuntimeError as e:
        print(f"HATA: canlı veri çekilemedi ({e})", file=sys.stderr)
        return 1

    if not runs:
        print(f"HATA: {repo} ({branch}) üzerinde run bulunamadı", file=sys.stderr)
        return 1

    rows, durations, s = _fetch_stats(repo, branch, limit)
    if args.markdown:
        return _print_markdown(rows, repo, s)
    if args.update_doc:
        return _update_doc(args.update_doc, repo, branch, limit)

    print(f"CI istatistik — {repo} ({branch}, son {len(rows)} run)")
    print("")
    print(f"{'#':<3} {'Run ID':<13} {'Tarih':<11} {'Durum':<12} {'Süre':<8} {'Job':<4} Özet")
    print("-" * 90)
    for i, r in enumerate(rows, 1):
        status = r["status"]
        concl = r["conclusion"]
        if status == "in_progress":
            mark = "in_progress"
        elif concl == "success":
            mark = "✅ success"
        elif concl == "failure":
            mark = "🔴 failure"
        else:
            mark = f"{concl or '?'}"
        print(f"{i:<3} {r['id']:<13} {r['createdAt']:<11} {mark:<12} "
              f"{_fmt_dur(r['duration_s']):<8} {r['jobs']:<4} {r['title'][:40]}")
    print("")

    rate = s["success_rate"]
    print(f"Success rate: {rate*100:.0f}% ({s['runs_success']}/{s['runs_completed']} "
          f"tamamlanan run) — {s['runs_in_progress']} in_progress hariç")
    if s["avg_duration_min"] is not None:
        print(f"Ortalama süre: {s['avg_duration_min']:.1f} dk "
              f"({s['avg_duration_s']:.0f} sn) — {len([d for d in durations.values() if d])} "
              f"run üzerinden")
    else:
        print("Ortalama süre: — (yeterli tamamlanmış run yok)")
    return 0


if __name__ == "__main__":
    sys.exit(main())