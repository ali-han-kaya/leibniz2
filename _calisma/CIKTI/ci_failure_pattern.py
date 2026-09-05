#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ci_failure_pattern.py — son N CI run'ın failure'larını sınıflandırır.

audit_live_ci_sync.py / ci_stats.py deseni: `gh` CLI üzerinden canlı GitHub
Actions verisine erişir (gh auth gerekli). Son N run'ın (varsayılan 10) her
job conclusion'ını toplar ve HER DÜŞEN JOB'U üç desenden birine ayırır:

  - flaky         : job pencerede bazı run'larda PASS, bazılarında FAIL —
                    aralıklı (F_J ≤ W_J/2). Geçici ağ zaman aşımı, taşınmış
                    port, cache yarışı gibi nedenlerle beklenir.
  - deterministik : job pencerede tutarlı FAIL (F_J > W_J/2) — aynı job
                    sürekli kırmızı; kod/ortam hatası sinyali, yok sayılmaz.
  - config-drift  : job adı config/drift-senkron anahtarları taşıyor
                    ("config", "basenames", "hook-env") VE pencerede FAIL —
                    config ↔ kod/doc drift'i sinyali (K10/K11/K13 deseni).
  - pass          : pencerede hiç FAIL yok.

Sınıflandırma KURALI (fail-closed değil — advisory rapor): F_J > W_J/2 →
deterministik; 0 < F_J ≤ W_J/2 → flaky; config anahtarlı + F_J > 0 →
config-drift. Skipped (PR-only job'ların push'ta atlanması) pencereye
KATILMAZ (ne PASS ne FAIL sayılır) — yanlış flaky üretmez.

Çıkış kodları:
  0 — rapor üretildi (bulgular olsa bile — advisory)
  1 — gh hatası / run bulunamadı / veri yok
"""
import argparse
import json
import subprocess
import sys

DEFAULT_LIMIT = 10
# Config/drift-senkron job'larının ad anahtarları (küçük harfe çevrilmiş
# adla eşleşir): "config drift check", "CONFIG_BASENAMES sync check",
# "hook env matrix check" (job adlarında tire değil BOŞLUK kullanılır).
CONFIG_KEYWORDS = ("config", "basenames", "hook env")


def run_gh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout.strip()


def get_repo():
    return run_gh(["gh", "repo", "view", "--json", "nameWithOwner",
                   "-q", ".nameWithOwner"])


def list_runs(repo, branch, limit):
    cmd = ["gh", "run", "list", "--repo", repo, "--limit", str(limit),
           "--json", "databaseId,status,conclusion,createdAt"]
    if branch:
        cmd += ["--branch", branch]
    out = run_gh(cmd)
    return json.loads(out or "[]")


def list_jobs(repo, run_id):
    out = run_gh(["gh", "run", "view", str(run_id), "--repo", repo,
                  "--json", "jobs", "-q", ".jobs"])
    return json.loads(out or "[]")


def classify_job(job_name, failures, window):
    """Sınıflandırma KURALI: (kategori, detay). window = job'ın pencereye
    KATILDIĞI run sayısı (success+failure; skipped hariç)."""
    if failures == 0:
        return "pass", "pencerede FAIL yok"
    if any(k in job_name.lower() for k in CONFIG_KEYWORDS):
        return "config-drift", (f"{failures}/{window} FAIL — config/kod drift'i "
                                f"sinyali")
    if failures > window / 2:
        return "deterministic", f"{failures}/{window} FAIL — tutarlı kırmızı"
    return "flaky", f"{failures}/{window} FAIL — aralıklı (PASS de var)"


def analyze(runs):
    """runs (her biri {databaseId, conclusion}) → (run_timeline, jobs)."""
    timeline = []
    jobs = {}  # job_name → {"failures": int, "window": int}
    for r in runs:
        rid = r.get("databaseId")
        concl = r.get("conclusion") or ("in_progress"
                                        if r.get("status") == "in_progress"
                                        else "?")
        try:
            jlist = list_jobs(get_repo(), rid) if rid else []
        except RuntimeError:
            jlist = []
        run_fail = [j["name"] for j in jlist
                    if j.get("conclusion") == "failure"]
        timeline.append({"run_id": rid, "conclusion": concl,
                         "failed_jobs": run_fail})
        for j in jlist:
            c = j.get("conclusion")
            if c not in ("success", "failure"):
                continue  # skipped/neutral pencereye katılmaz
            rec = jobs.setdefault(j["name"], {"failures": 0, "window": 0})
            rec["window"] += 1
            if c == "failure":
                rec["failures"] += 1
    return timeline, jobs


def summarize(timeline, jobs):
    n = len(timeline)
    fails = [t for t in timeline if t["conclusion"] == "failure"]
    by_job = []
    for name, rec in sorted(jobs.items(), key=lambda kv: -kv[1]["failures"]):
        if rec["failures"] == 0:
            continue
        cat, det = classify_job(name, rec["failures"], rec["window"])
        by_job.append({"job": name, **rec, "category": cat, "detail": det})
    return {
        "runs_total": n,
        "runs_failure": len(fails),
        "success_rate": ((n - len(fails)) / n) if n else None,
        "jobs": by_job,
        "categories": {
            "deterministic": [b["job"] for b in by_job
                              if b["category"] == "deterministic"],
            "flaky": [b["job"] for b in by_job if b["category"] == "flaky"],
            "config_drift": [b["job"] for b in by_job
                             if b["category"] == "config-drift"],
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help=f"son N run (varsayılan {DEFAULT_LIMIT})")
    ap.add_argument("--branch", default=None,
                    help="branch (varsayılan: gh run list --branch yoksa tümü)")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--json", action="store_true", help="makine-okur JSON")
    args = ap.parse_args(argv)

    repo = args.repo or get_repo()
    try:
        runs = list_runs(repo, args.branch, args.limit)
        timeline, jobs = analyze(runs)
    except RuntimeError as e:
        print(f"HATA: gh erişilemedi: {e}", file=sys.stderr)
        return 1

    if not timeline:
        print("HATA: run bulunamadı", file=sys.stderr)
        return 1

    s = summarize(timeline, jobs)
    if args.json:
        print(json.dumps(s, indent=2, ensure_ascii=False))
        return 0

    print(f"=== CI failure pattern (son {s['runs_total']} run) ===")
    for t in timeline:
        mark = "✅" if t["conclusion"] == "success" else "❌"
        jobs_s = (", ".join(t["failed_jobs"]) if t["failed_jobs"] else "-")
        print(f"  {mark} run {t['run_id']}: {t['conclusion']} "
              f"(düşen: {jobs_s})")
    print(f"  success rate: {s['success_rate']:.0%} "
          f"({s['runs_total'] - s['runs_failure']}/{s['runs_total']})")
    if not s["jobs"]:
        print("  düşen job yok — pencere temiz")
    for b in s["jobs"]:
        tag = {"deterministic": "🔴", "flaky": "🟡",
               "config-drift": "🟠"}[b["category"]]
        print(f"  {tag} {b['category']:<13} {b['job']} "
              f"({b['detail']})")
    print(f"SONUÇ: rapor üretildi (advisory)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
