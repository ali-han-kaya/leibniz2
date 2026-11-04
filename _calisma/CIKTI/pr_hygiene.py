#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pr_hygiene.py — PR board hijyeni: birikim ölçümü + BEHIND dalların güncellenmesi.

17 açık PR'ın aynı anda birikmesi (2026-11-04) tek tek çakışma çözümüyle
temizlendi; kök neden otomasyonun yokluğuydu: main ilerledikçe hiçbir aktör
açık PR'ları güncellemiyor, board sessizce BEHIND/DIRTY'ye düşüyordu.

Bu araç her main push'unda (ve elle) board'u ölçer:
  * açık / BEHIND / DIRTY / BLOCKED / taslak / bayat (> STALE_DAYS) sayıları,
  * `--apply` ile: yalnız BEHIND + taslak-değil + `hold` etiketsiz PR'lar
    `gh pr update-branch --rebase` ile güncellenir (en fazla --max-updates),
  * `--issue` ile: tek bir izleme issue'su açılır/güncellenir; board temizse
    issue kapatılır (idempotent, başlık işaretçisiyle aranır).

Fail-closed hüküm (sessiz yeşil yok):
  rc 0 = ölçüm tamam, birikim eşiğin altında
  rc 1 = uygulama sırasında güncelleme hatası (PR bazında raporlanır)
  rc 2 = ÖLÇÜM İMKÂNSIZ (gh yok / API hatası) — iş KIRMIZI biter
  rc 3 = BİRİKİM EŞİĞİ AŞILDI (open > --threshold) — iş KIRMIZI biter

Oflayn doğrulama: `--from-json PATH` ile `gh pr list --json` çıktısı
dosyadan okunur; ağa çıkılmaz (test_pr_hygiene.py bunu kullanır).

stdlib-only; gh CLI dış bağımlılığıdır (runner'da hazır).
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

FIELDS = ("number,title,headRefName,mergeable,mergeStateStatus,isDraft,"
          "updatedAt,labels,author")
STALE_DAYS = 7
DEFAULT_THRESHOLD = 8
DEFAULT_MAX_UPDATES = 5
HOLD_LABEL = "hold"
ISSUE_MARKER = "PR board hygiene"


class GhError(Exception):
    """gh çağrısı başarısız — ölçüm/uygulama imkânsız (fail-closed)."""


def normalize(payload):
    """`gh pr list --json` çıktısını kararlı bir iç modele çevirir."""
    out = []
    for pr in payload:
        labels = {lbl.get("name") if isinstance(lbl, dict) else lbl
                  for lbl in (pr.get("labels") or [])}
        labels.discard(None)
        out.append({
            "number": int(pr["number"]),
            "title": pr.get("title") or "",
            "branch": pr.get("headRefName") or "",
            "mergeable": (pr.get("mergeable") or "UNKNOWN").upper(),
            "state": (pr.get("mergeStateStatus") or "UNKNOWN").upper(),
            "draft": bool(pr.get("isDraft")),
            "updated_at": pr.get("updatedAt") or "",
            "labels": labels,
        })
    return sorted(out, key=lambda p: p["number"])


def _age_days(updated_at, now):
    if not updated_at:
        return None
    try:
        ts = datetime.datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return max(0, (now - ts.replace(tzinfo=datetime.timezone.utc)).days)


def classify(prs, now=None, stale_days=STALE_DAYS):
    """Board'u sınıflandırır: sayımlar + isim listeleri (saf fonksiyon)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    report = {
        "open": len(prs),
        "behind": [], "dirty": [], "blocked": [], "draft": [], "stale": [],
        "mergeable": [],
    }
    for pr in prs:
        n = pr["number"]
        if pr["draft"]:
            report["draft"].append(n)
        if pr["state"] == "BEHIND":
            report["behind"].append(n)
        elif pr["state"] == "DIRTY" or pr["mergeable"] == "CONFLICTING":
            report["dirty"].append(n)
        elif pr["state"] == "BLOCKED":
            report["blocked"].append(n)
        elif pr["mergeable"] == "MERGEABLE":
            report["mergeable"].append(n)
        age = _age_days(pr["updated_at"], now)
        if age is not None and age > stale_days:
            report["stale"].append(n)
    report["stale_days"] = stale_days
    return report


def eligible_for_update(prs, max_updates=DEFAULT_MAX_UPDATES):
    """Yalnız BEHIND + taslak-değil + `hold` etiketsiz PR'lar; sınırlı sayıda.

    DIRTY (gerçek çakışma) otomatik güncellenmez: rebase çakışmayı çözmez,
    yalnız insan kararı gerektirir. Taslak/hold PR'larına dokunulmaz.
    """
    picked = []
    for pr in prs:
        if pr["state"] != "BEHIND":
            continue
        if pr["draft"] or HOLD_LABEL in pr["labels"]:
            continue
        picked.append(pr["number"])
        if len(picked) >= max_updates:
            break
    return picked


def verdict(report, threshold=DEFAULT_THRESHOLD):
    """(rc, başlık) — eşik aşımı KIRMIZI sinyaldir, sessiz geçmez."""
    if report["open"] > threshold:
        return 3, ("PILEUP: %d açık PR > eşik %d"
                   % (report["open"], threshold))
    return 0, "OK: %d açık PR (eşik %d)" % (report["open"], threshold)


def render(report, threshold=DEFAULT_THRESHOLD):
    """İnsan-okunur markdown rapor (issue gövdesi + adım özeti)."""
    rc, head = verdict(report, threshold)

    def ids(key):
        return ", ".join("#%d" % n for n in report[key]) or "—"

    lines = [
        "**%s**" % head,
        "",
        "| Ölçüm | Sayı | PR'lar |",
        "|---|---|---|",
        "| Açık | %d | — |" % report["open"],
        "| BEHIND (güncellenebilir) | %d | %s |"
        % (len(report["behind"]), ids("behind")),
        "| DIRTY (çakışma — insan) | %d | %s |"
        % (len(report["dirty"]), ids("dirty")),
        "| BLOCKED | %d | %s |" % (len(report["blocked"]), ids("blocked")),
        "| Taslak | %d | %s |" % (len(report["draft"]), ids("draft")),
        "| Bayat (> %d gün) | %d | %s |"
        % (report["stale_days"], len(report["stale"]), ids("stale")),
        "",
        "Otomatik kural: yalnız BEHIND + taslak-değil + `hold` etiketsiz "
        "PR'lar rebase edilir; DIRTY PR'lar insan çözümü bekler.",
    ]
    return rc, "\n".join(lines)


def run_gh(args, runner=None):
    """gh çağrısı; hata `GhError` (rc 2 — ölçüm imkânsız)."""
    runner = runner or subprocess.run
    try:
        proc = runner(["gh"] + list(args), capture_output=True, text=True,
                      timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise GhError("gh çalıştırılamadı: %s" % exc)
    if proc.returncode != 0:
        raise GhError("gh %s → rc %d: %s"
                      % (" ".join(args[:2]), proc.returncode,
                         (proc.stderr or proc.stdout).strip()[:500]))
    return proc.stdout


def fetch_prs(repo=None, runner=None):
    args = ["pr", "list", "--state", "open", "--limit", "100",
            "--json", FIELDS]
    if repo:
        args += ["--repo", repo]
    return normalize(json.loads(run_gh(args, runner)))


def update_branch(number, repo=None, runner=None):
    args = ["pr", "update-branch", str(number), "--rebase"]
    if repo:
        args += ["--repo", repo]
    run_gh(args, runner)


def sync_issue(report_text, pileup, repo=None, runner=None):
    """Tek izleme issue'su: PILEUP'ta aç/güncelle, temizde kapat (idempotent)."""
    args = ["issue", "list", "--state", "open", "--search",
            '"%s" in:title' % ISSUE_MARKER, "--json", "number,title",
            "--limit", "10"]
    if repo:
        args += ["--repo", repo]
    found = json.loads(run_gh(args, runner))
    mine = [i for i in found if i.get("title", "").startswith(ISSUE_MARKER)]
    if pileup:
        if mine:
            n = mine[0]["number"]
            run_gh(["issue", "comment", str(n), "--body", report_text], runner)
            return "updated #%d" % n
        create = ["issue", "create", "--title",
                  "%s: birikim eşiği aşıldı" % ISSUE_MARKER,
                  "--body", report_text]
        if repo:
            create += ["--repo", repo]
        url = run_gh(create, runner).strip()
        return "created %s" % url
    for issue in mine:
        close = ["issue", "close", str(issue["number"]), "--reason",
                 "completed"]
        if repo:
            close += ["--repo", repo]
        run_gh(close, runner)
    return "closed %d" % len(mine) if mine else "no-op"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="yalnız ölç (varsayılan)")
    ap.add_argument("--apply", action="store_true",
                    help="BEHIND PR'ları rebase et")
    ap.add_argument("--issue", action="store_true",
                    help="izleme issue'sunu senkronla")
    ap.add_argument("--repo", default=os.environ.get("REPO") or None)
    ap.add_argument("--threshold", type=int,
                    default=int(os.environ.get("PR_HYGIENE_THRESHOLD",
                                               DEFAULT_THRESHOLD)))
    ap.add_argument("--max-updates", type=int, default=DEFAULT_MAX_UPDATES)
    ap.add_argument("--stale-days", type=int, default=STALE_DAYS)
    ap.add_argument("--from-json", default=None,
                    help="ağa çıkmadan `gh pr list --json` çıktısını oku")
    ap.add_argument("--json-out", default=None,
                    help="raporu JSON olarak da yaz (tek belge)")
    args = ap.parse_args(argv)

    try:
        if args.from_json:
            with open(args.from_json, encoding="utf-8") as fh:
                prs = normalize(json.load(fh))
        else:
            prs = fetch_prs(args.repo)
    except (GhError, OSError, ValueError) as exc:
        print("FAIL: PR board ölçülemedi: %s" % exc, file=sys.stderr)
        return 2

    report = classify(prs, stale_days=args.stale_days)
    rc, body = render(report, args.threshold)
    print(body)

    updates = []
    if args.apply and not args.from_json:
        for n in eligible_for_update(prs, args.max_updates):
            try:
                update_branch(n, args.repo)
                updates.append({"pr": n, "status": "updated"})
            except GhError as exc:
                updates.append({"pr": n, "status": "error", "error": str(exc)})
        for u in updates:
            print("update #%d: %s" % (u["pr"], u["status"]))
        if any(u["status"] == "error" for u in updates):
            rc = 1

    issue_state = None
    if args.issue and not args.from_json:
        try:
            issue_state = sync_issue(body, rc != 0, args.repo)
            print("issue:", issue_state)
        except GhError as exc:
            print("FAIL: issue senkronu: %s" % exc, file=sys.stderr)
            return 2

    if args.json_out:
        doc = {"threshold": args.threshold, "report": report,
               "verdict_rc": rc, "updates": updates,
               "issue": issue_state}
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")

    print("SONUÇ: %s" % ("OK" if rc == 0 else "FAIL (rc=%d)" % rc),
          file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
