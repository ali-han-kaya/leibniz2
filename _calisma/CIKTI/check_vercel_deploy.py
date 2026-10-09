#!/usr/bin/env python3
"""check_vercel_deploy.py — canli Vercel deploy /api dogrulamasi (fail-closed).

Aylik cron (vercel-deploy-check.yml) CI'da bu scripti; `--base-url` lokalde
AYNI kodu kosturur (test_gated_schedules K1/K2 parity — akis YAML'da yeniden
yazilmaz):

  1) /api/health → birebir "ok" (bosluk-temizlikli; yerel serve_health
     duz-metin sozlesmesi),
  2) /api/run-history → JSON dizi + {ts, verdict} sema + verdict kumesi
     {PASS, FAIL, ?} — "200 + parse" yetmez, sema-parite de sinanir.
  3) /slides_z3/P1-a.png → 200 + PNG magic (statik-upload kaniti;
     .vercelignore dir-prune hatasi API'leri bozmadan yalnizca statik
     agaci kesebilir — 2026-10-09: /slides_z3/* TÜM deploy'larda 404).

Fail-closed: herhangi bir uc FAIL → exit 1 (sessiz PASS yok). Satir-raporu
stdout'a; GITHUB_STEP_SUMMARY tanimliysa markdown ozet oraya da eklenir.
stdlib-only; ag-dis test edilebilir (test_check_vercel_deploy.py).

Kullanim:
    python3 check_vercel_deploy.py                       # canli alias
    python3 check_vercel_deploy.py --base-url http://127.0.0.1:8000
    python3 check_vercel_deploy.py --json
"""
import argparse
import datetime
import json
import os
import sys
import urllib.request

DEFAULT_BASE = "https://leibniz2.vercel.app"
TIMEOUT_HEALTH = 20
TIMEOUT_HISTORY = 30
TIMEOUT_SLIDE = 30
VERDICTS = {"PASS", "FAIL", "?"}


def _get(url, timeout):
    req = urllib.request.Request(url, headers={"Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def _get_bytes(url, timeout):
    req = urllib.request.Request(url, headers={"Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def check_health(base):
    """/api/health → (ok, mesaj)."""
    try:
        status, body = _get(base + "/api/health", TIMEOUT_HEALTH)
    except Exception as e:  # ag/HTTP/DNS — hepsi FAIL
        return False, "ag/HTTP hatasi: %s" % e
    if status != 200:
        return False, "HTTP %s" % status
    if "".join(body.split()) != "ok":
        return False, "ok beklenen, gelen: %r" % body[:200]
    return True, "ok"


def check_run_history(base):
    """/api/run-history → (ok, mesaj); sema-parite dahil."""
    try:
        status, body = _get(base + "/api/run-history", TIMEOUT_HISTORY)
    except Exception as e:
        return False, "ag/HTTP hatasi: %s" % e
    if status != 200:
        return False, "HTTP %s" % status
    try:
        rows = json.loads(body)
    except ValueError as e:
        return False, "JSON degil: %s" % e
    if not isinstance(rows, list) or not rows:
        return False, "bos liste veya liste degil"
    first = rows[0]
    missing = {"ts", "verdict"} - set(first)
    if missing:
        return False, "sema eksik: %r" % sorted(missing)
    if first["verdict"] not in VERDICTS:
        return False, "verdict gecersiz: %r" % (first["verdict"],)
    return True, "%d satir, ilk=%s %s" % (
        len(rows), first.get("ts"), first["verdict"])


def check_slide(base):
    """/slides_z3/P1-a.png → (ok, mesaj); PNG magic ile statik-upload kaniti."""
    try:
        status, body = _get_bytes(base + "/slides_z3/P1-a.png", TIMEOUT_SLIDE)
    except Exception as e:
        return False, "ag/HTTP hatasi: %s" % e
    if status != 200:
        return False, "HTTP %s" % status
    if not body.startswith(b"\x89PNG\r\n\x1a\n"):
        return False, "PNG magic yok: %r" % body[:16]
    return True, "PNG %d bayt" % len(body)


def run(base):
    """Tum uc → (fail, satirlar)."""
    checks = (("api/health", check_health),
              ("api/run-history", check_run_history),
              ("slides_z3/P1-a.png", check_slide))
    lines = []
    fail = 0
    for name, fn in checks:
        ok, msg = fn(base)
        if ok:
            lines.append("- /%s: **PASS** (%s)" % (name, msg))
        else:
            fail = 1
            lines.append("- /%s: **FAIL** — %s" % (name, msg))
    return fail, lines


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _write_summary(base, verdict, lines):
    """GITHUB_STEP_SUMMARY tanimliysa markdown ozeti ekle (her kosumda)."""
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    with open(summary, "a", encoding="utf-8") as fh:
        fh.write("## Vercel deploy dogrulama (aylik)\n\n")
        fh.write("- Base: %s\n" % base)
        fh.write("- UTC: %s\n\n" % _utc_now())
        for ln in lines:
            fh.write(ln + "\n")
        fh.write("\n**VERDICT: %s** — %s\n" % (
            verdict, "tum uc canli." if verdict == "PASS"
            else "en az bir uc dogrulanamadi."))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Vercel deploy /api dogrulama (fail-closed)")
    ap.add_argument("--base-url",
                    default=os.environ.get("VERCEL_BASE_URL", DEFAULT_BASE),
                    help="deployment koku (default: $VERCEL_BASE_URL veya "
                         "canli alias)")
    ap.add_argument("--json", action="store_true",
                    help="sonucu JSON olarak bas")
    args = ap.parse_args(argv)
    base = args.base_url.rstrip("/")
    if not base.startswith(("http://", "https://")):
        print("GECERSIZ base-url: %r (http(s):// ile baslamali)" % base,
              file=sys.stderr)
        # "Her kosumda ozet" sozlesmesi gecersiz sema icin de gecerli:
        # dispatch girdisi kirilabilir; ozetsiz kirmizi sessiz kayiptir.
        _write_summary(base, "FAIL", ["- gecersiz base-url: %r" % base])
        return 1
    fail, lines = run(base)
    verdict = "FAIL" if fail else "PASS"
    if args.json:
        print(json.dumps({"base": base, "verdict": verdict,
                          "lines": lines}, ensure_ascii=False))
    else:
        for ln in lines:
            print(ln)
        print("VERDICT: %s — %s" % (verdict, base))
    _write_summary(base, verdict, lines)
    return fail


if __name__ == "__main__":
    sys.exit(main())
