#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Son 10 workflow run'ında required check başarı oranlarını hesaplar."""
import argparse
import json
import subprocess
import sys

DEFAULT_LIMIT = 10


def run_gh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout.strip()


def list_runs(repo, branch, limit):
    out = run_gh(["gh", "run", "list", "--repo", repo, "--branch", branch,
                  "--limit", str(limit), "--json", "databaseId,status,conclusion"])
    return json.loads(out or "[]")


def view_jobs(repo, run_id):
    out = run_gh(["gh", "run", "view", str(run_id), "--repo", repo,
                  "--json", "jobs", "-q", ".jobs"])
    return json.loads(out or "[]")


def calculate(check_names, run_jobs):
    """Her check için completed/success/failed/rate özeti üretir."""
    result = {}
    for name in check_names:
        observed = [j for jobs in run_jobs for j in jobs if j.get("name") == name]
        completed = [j for j in observed if j.get("status") == "completed"]
        success = [j for j in completed if j.get("conclusion") == "success"]
        result[name] = {
            "observed": len(observed),
            "completed": len(completed),
            "success": len(success),
            "failed": sum(1 for j in completed if j.get("conclusion") != "success"),
            "success_rate": len(success) / len(completed) if completed else None,
        }
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--branch", default="main")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        repo = args.repo or run_gh(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
        sys.path.insert(0, __import__("os").path.dirname(__file__))
        import status_checks
        checks = list(status_checks.gate_jobs().values())
        runs = list_runs(repo, args.branch, args.limit)
        jobs = [view_jobs(repo, r["databaseId"]) for r in runs]
        rates = calculate(checks, jobs)
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"HATA: CI check verisi alınamadı: {exc}", file=sys.stderr)
        return 1
    payload = {"repo": repo, "branch": args.branch, "runs": len(runs),
               "limit": args.limit, "checks": rates}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"CI required check başarı oranları — son {len(runs)} run")
        for name, row in rates.items():
            rate = "—" if row["success_rate"] is None else f"{row['success_rate'] * 100:.0f}%"
            print(f"{rate:>4} ({row['success']}/{row['completed']})  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
