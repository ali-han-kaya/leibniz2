#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_protection_drift.py — haftalık branch-protection drift kapısı (P1).

NEDEN AYRI SCRIPT: `status_checks.py --gh` aynı karşılaştırmayı yapar ama
CI'da KOŞAMAZ — branch protection okumak admin izni ister ve `administration`
scope'u Actions `permissions:` bloğunda GEÇERSİZDİR (ölçüldü 2026-09-30,
actionlint v1.7.7: "unknown permission scope administration"). Eklenirse
workflow PARSE HATASIYLA 0 JOB üretir. Bu yüzden okuma yetkisi
`PROTECTION_PAT` secret'ından gelir; GITHUB_TOKEN ile denenmez.

SÖZLEŞME (üç dal, üçü AYRI raporlanır):
  * token yok            → SKIP, rc=0, bulgu YOK (gürültü yapmaz; bu kasıtlı).
  * token var, okunamadı → rc=2 "DOĞRULANAMADI". Süresi geçmiş bir PAT'in
    sonsuza dek sessiz SKIP'e düşmesi, kapının hiç var olmamasıyla aynıdır —
    o yüzden bu dal YEŞİL değil.
  * okundu, drift var    → P1 bulguları (verify_delivery sözlüğü), rc=1.
  * okundu, temiz        → rc=0.

SALT-OKUNUR: API'ye hiçbir şey YAZMAZ (yalnızca GET).

Kullanım:
  PROTECTION_PAT=<pat> python3 _calisma/CIKTI/check_protection_drift.py
  PROTECTION_PAT=<pat> python3 _calisma/CIKTI/check_protection_drift.py --json
  python3 _calisma/CIKTI/check_protection_drift.py            # → SKIP rc=0
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import status_checks as sc          # noqa: E402
import verify_delivery as vd        # noqa: E402

BRANCH = "main"
# Sırayla denenir. PROTECTION_PAT tercih edilir: fine-grained, yalnızca
# "Administration: read" yetkisi verilmiş bir token olmalıdır.
TOKEN_ENVS = ("PROTECTION_PAT", "GH_ADMIN_TOKEN")

# ── alert (sticky issue) ────────────────────────────────────────────────
# Drift KIRMIZI bir koşumla yetinmez: haftalık scheduled job'un kırmızısı
# kimseye ulaşmayabilir (bildirim ayarına bağlı). Bu yüzden drift ve
# "doğrulanamadı" durumlarında tek bir takip issue'su açılır/güncellenir,
# temiz koşumda kapatılır. Issue'ya yazmak KORUMAYI değiştirmez; kapı
# salt-okunur kalır (fetch_protection yalnız GET).
ALERT_TITLE = "[protection-drift] Branch protection drift (main)"
ALERT_MARKER = "<!-- protection-drift-alert -->"
ALERT_TOKEN_ENVS = ("ALERT_GH_TOKEN", "GITHUB_TOKEN")


def alert_token(env=None):
    """Issue yazma yetkisi olan token (GITHUB_TOKEN / ALERT_GH_TOKEN)."""
    env = os.environ if env is None else env
    for name in ALERT_TOKEN_ENVS:
        value = env.get(name)
        if value and value.strip():
            return value.strip()
    return None


def _gh_call(args, token):
    """`gh <args>` çağır; (stdout|None, hata|None) döndür (yükseltmez)."""
    try:
        r = subprocess.run(["gh"] + list(args), capture_output=True, text=True,
                           env={**os.environ, "GH_TOKEN": token})
    except OSError as exc:
        return None, "gh çalıştırılamadı: %s" % exc
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip()
    return r.stdout, None


def run_url(repo):
    """Bu koşumun URL'i (yerelde yoksa None)."""
    run_id = os.environ.get("GITHUB_RUN_ID")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    if run_id and repo:
        return "%s/%s/actions/runs/%s" % (server.rstrip("/"), repo, run_id)
    return None


def build_alert_body(report, url=None):
    """Issue gövdesi: durum + P1 bulguları + koşum bağlantısı."""
    status = report.get("status", "?")
    repo = report.get("repo", "?")
    branch = report.get("branch", BRANCH)
    lines = [ALERT_MARKER, "",
             "## Branch protection drift — `%s`" % branch, "",
             "**Durum:** `%s`  ·  **Repo:** `%s`" % (status, repo)]
    if report.get("detail"):
        lines.append("**Ayrıntı:** %s" % report["detail"])
    if report.get("message"):
        lines.append("**Not:** %s" % report["message"])
    if url:
        lines.append("**Koşum:** %s" % url)
    findings = report.get("p1") or []
    if findings:
        lines += ["", "### P1 bulguları", "",
                  "| id | check | sorun | kanıt |",
                  "|----|-------|-------|-------|"]
        for f in findings:
            lines.append("| `%s` | %s | %s | %s |" % (
                f.get("id", "?"),
                str(f.get("check", "")).replace("|", "\\|"),
                str(f.get("issue", "")).replace("|", "\\|"),
                str(f.get("evidence", "")).replace("|", "\\|")))
    lines += ["", "Beklenen ayarlar `status_checks.expected_checks()` + "
                  "`verify_delivery.check_protection_drift` sözleşmesidir; "
                  "düzeltme `_calisma/CIKTI/setup_branch_protection.py` ile "
                  "yapılır.", "",
              "_Bu issue otomatik yönetilir: drift temizlenince kapatılır._"]
    return "\n".join(lines) + "\n"


def send_alert(report, token=None, url=None):
    """Sticky drift issue'sunu aç/güncelle/kapat.

    Döner: "created" | "updated" | "closed" | "noop" | "error: ...".
    SKIP (token yok) alert ÜRETMEZ — sözleşme gereği gürültü yapmaz.
    """
    status = report.get("status")
    if status == "SKIP":
        return "noop"
    token = token or alert_token()
    if not token:
        return "error: alert token yok (%s)" % "/".join(ALERT_TOKEN_ENVS)

    out, err = _gh_call(["issue", "list", "--state", "open", "--limit", "50",
                         "--search", "protection-drift in:title",
                         "--json", "number,title"], token)
    if out is None:
        return "error: issue listesi okunamadı: %s" % err
    try:
        issues = json.loads(out) if out.strip() else []
    except ValueError as exc:
        return "error: issue listesi ayrıştırılamadı: %s" % exc
    existing = next((i for i in issues
                     if isinstance(i, dict) and i.get("title") == ALERT_TITLE),
                    None)

    if status == "PASS":
        if not existing:
            return "noop"
        _o, err = _gh_call(["issue", "close", str(existing["number"]),
                            "--comment",
                            "Branch protection drift giderildi — otomatik "
                            "kapatıldı.%s" % (" " + url if url else "")],
                           token)
        return "closed" if err is None else "error: issue kapatılamadı: %s" % err

    body = build_alert_body(report, url)
    if existing:
        _o, err = _gh_call(["issue", "edit", str(existing["number"]),
                            "--body", body], token)
        return "updated" if err is None else "error: issue güncellenemedi: %s" % err
    _o, err = _gh_call(["issue", "create", "--title", ALERT_TITLE,
                        "--body", body], token)
    return "created" if err is None else "error: issue açılamadı: %s" % err


def token_from_env(env=None):
    """Okuma yetkisi olan token'ı döndürür; yoksa None."""
    env = os.environ if env is None else env
    for name in TOKEN_ENVS:
        value = env.get(name)
        if value and value.strip():
            return value.strip()
    return None


def fetch_protection(repo, token, branch=BRANCH):
    """Koruma nesnesini okur. Döner: (protection|None, error|None).

    `gh` yoksa (OSError) veya çağrı başarısızsa hata DÖNER, yükseltmez:
    çağıran bunu "okunamadı" (rc=2) olarak raporlar. Yükseltseydi istisna
    traceback'i kapıyı rc=1 ile kırar ve "drift" ile "araç yok" ayırt
    edilemezdi.
    """
    try:
        r = subprocess.run(
            ["gh", "api", "repos/%s/branches/%s/protection" % (repo, branch)],
            capture_output=True, text=True,
            env={**os.environ, "GH_TOKEN": token})
    except OSError as exc:
        return None, "gh çalıştırılamadı: %s" % exc
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip()
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        return None, "gh api çıktısı ayrıştırılamadı: %s" % exc
    return (data if isinstance(data, dict) else {}), None


def repo_slug(explicit=None):
    """owner/name — verilmezse gh'den; olmazsa GITHUB_REPOSITORY."""
    if explicit:
        return explicit, None
    try:
        out = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner",
                              "-q", ".nameWithOwner"],
                             capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip(), None
    except OSError as exc:
        return None, str(exc)
    slug = os.environ.get("GITHUB_REPOSITORY")
    if slug:
        return slug, None
    return None, "repo belirlenemedi"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=None, help="owner/name")
    ap.add_argument("--json", action="store_true", help="makine-okur çıktı")
    ap.add_argument("--alert", action="store_true",
                    help="FAIL/DOĞRULANAMADI durumunda sticky issue aç/güncelle; "
                         "PASS'ta açık issue'yu kapat (CI scheduled job)")
    args = ap.parse_args(argv)

    def _alert(payload):
        """--alert verildiyse issue'yu yönet; hata koşumu YEŞİLE çevirmez."""
        if not args.alert:
            return
        result = send_alert(payload, url=run_url(payload.get("repo")))
        if result.startswith("error"):
            # Drift'te alert hatası kırmızı koşumun SEBEBİ değil, ek bilgidir;
            # temiz koşumda ise yalnızca kapanmayan issue'yu bildirir. Yeşil
            # koşuya `error` basmak annotation'ı değersizleştirirdi.
            level = "warning" if payload.get("status") == "PASS" else "error"
            print("::%s::protection-drift alert: %s" % (
                      level, result[6:].strip()), file=sys.stderr)
        else:
            print("[alert] %s" % result, file=sys.stderr)

    token = token_from_env()
    if not token:
        # KASITLI SKIP: secret kurulmadıysa denetim yapılamaz. Bulgu üretmek
        # her hafta yanlış-P1 gürültüsü olurdu; sessiz kalmak yerine neyin
        # eksik olduğunu AÇIKÇA söyleriz.
        msg = ("SKIP — %s secret'ı yok; branch protection okunamaz "
               "(admin scope'u Actions'ta tanımlanamıyor). Kurulum: "
               "fine-grained token ('Administration: read') → repo secret "
               "'%s'" % (TOKEN_ENVS[0], TOKEN_ENVS[0]))
        if args.json:
            print(json.dumps({"status": "SKIP", "reason": "no-token",
                              "p1": [], "message": msg},
                             indent=2, ensure_ascii=False))
        else:
            print(msg)
        # SKIP alert üretmez (sözleşme: her hafta yanlış-P1 gürültüsü yok).
        return 0

    repo, err = repo_slug(args.repo)
    if not repo:
        print("HATA: %s" % err, file=sys.stderr)
        return 2

    protection, err = fetch_protection(repo, token)
    if protection is None:
        # Token VAR ama okunamadı: süresi geçmiş olabilir. Sessiz SKIP
        # kapıyı ölü hâle getirirdi.
        msg = ("DOĞRULANAMADI — %s koruması okunamadı: %s "
               "(token geçersiz/süresi geçmiş ya da yetki yetersiz)"
               % (repo, err))
        payload = {"status": "UNVERIFIABLE", "repo": repo, "branch": BRANCH,
                   "p1": [], "message": msg}
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(msg, file=sys.stderr)
        # Ölü monitör sessiz kalmamalı: token süresi geçtiyse issue açılır.
        _alert(payload)
        return 2

    # `expected_checks()` — verify.yml kapıları + ikincil workflow kapıları
    # (docker-security). Yalnız `gate_jobs()` kullanmak, required set 18'e
    # çıktıktan sonra haftalık monitörü eski 16'lık kümeye sabitlerdi ve
    # gerçek required check'ler "fazla" görünürdü.
    expected = list(sc.expected_checks())
    findings = []
    ok, detail = vd.check_protection_drift(
        lambda pri, cid, check, issue, evidence="": findings.append(
            {"id": cid, "priority": pri, "check": check,
             "issue": issue, "evidence": evidence}),
        protection, expected)

    payload = {
        "status": "PASS" if ok else "FAIL",
        "repo": repo,
        "branch": BRANCH,
        "expected_checks": len(expected),
        "detail": detail,
        "p1": findings,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("── branch protection drift (%s@%s) ──" % (repo, BRANCH))
        print("  beklenen required check: %d" % len(expected))
        print("  sonuç: %s — %s" % ("PASS" if ok else "FAIL", detail))
        for f in findings:
            print("  [%s] %s: %s\n        %s"
                  % (f["priority"], f["check"], f["issue"], f["evidence"]))
    _alert(payload)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
