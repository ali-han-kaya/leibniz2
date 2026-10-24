#!/usr/bin/env python3
"""vercel_latest_preview.py — en guncel READY preview URL'ini cozer (fail-closed).

Neden: aylik `vercel-deploy-check` isi uretim alias'ini degil, **en guncel
preview**'i denetler. git-connect engeli (Login Connection 400) yuzunden sabit
bir preview alias'i yok (docs/VERCEL_DEPLOYMENT.md §5); bu yuzden URL her
kosumda Vercel API'sinden cozulur:

    GET https://api.vercel.com/v6/deployments?projectId=<id>&limit=<N>

Secim kurali: liste yeniden-eskiye gelir; `readyState == "READY"` ve
`target != "production"` olan **ilk** kayit en guncel preview'dir. BUILDING /
ERROR / QUEUED deployment'lar atlanir — yayinda olmayan bir URL'i "en guncel"
diye dondurmek sessiz-PASS uretirdi.

Cikis kodlari (fail-closed; hicbir durumda URL uydurulmaz):
    0 → URL bulundu (stdout'a tek satir)
    1 → READY preview yok
    2 → girdi eksik (token veya project id)
    3 → API/HTTP hatasi

`--json` makine-okur cikti verir: {"url", "target", "readyState",
"createdAt", "project_id"}.

Token **asla** stdout/stderr'e yazilmaz; hata mesajlari yalniz HTTP
durumunu/API mesajini tasir.

Kullanim:
    VERCEL_TOKEN=... python3 vercel_latest_preview.py --project-id prj_...
    python3 vercel_latest_preview.py --project-id prj_... --json
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.vercel.com/v6/deployments"
DEFAULT_LIMIT = 20
TIMEOUT_S = 20


def _api_url(project_id, limit):
    qs = urllib.parse.urlencode({"projectId": project_id, "limit": str(limit)})
    return "%s?%s" % (API_BASE, qs)


def fetch_deployments(project_id, token, limit=DEFAULT_LIMIT, timeout=TIMEOUT_S):
    """API'den deployment listesini ceker (stdlib urllib)."""
    req = urllib.request.Request(
        _api_url(project_id, limit),
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def pick_latest_preview(deployments):
    """READY + production-disi ilk deployment'i dondurur (yoksa None)."""
    for dep in deployments or []:
        if not isinstance(dep, dict):
            continue
        if dep.get("readyState") != "READY":
            continue
        if dep.get("target") == "production":
            continue
        url = (dep.get("url") or "").strip()
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        out = dict(dep)
        out["url"] = url
        return out
    return None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description="En guncel READY Vercel preview URL'i")
    ap.add_argument("--project-id", default=os.environ.get("VERCEL_PROJECT_ID", ""),
                    help="Vercel proje id (varsayilan: $VERCEL_PROJECT_ID)")
    ap.add_argument("--token", default=os.environ.get("VERCEL_TOKEN", ""),
                    help="Vercel token (varsayilan: $VERCEL_TOKEN; stdout'a yazilmaz)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help="API sayfa boyu (varsayilan %d)" % DEFAULT_LIMIT)
    ap.add_argument("--json", action="store_true", help="JSON cikti")
    args = ap.parse_args(argv)

    if not args.token:
        print("HATA: VERCEL_TOKEN tanimli degil (--token veya ortam degiskeni)",
              file=sys.stderr)
        return 2
    if not args.project_id:
        print("HATA: project id tanimli degil (--project-id veya $VERCEL_PROJECT_ID)",
              file=sys.stderr)
        return 2
    if args.limit <= 0:
        print("HATA: --limit pozitif olmali", file=sys.stderr)
        return 2

    try:
        payload = fetch_deployments(args.project_id, args.token, args.limit)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        print(("HATA: Vercel API HTTP %s %s" % (e.code, detail)).rstrip(),
              file=sys.stderr)
        return 3
    except Exception as e:  # ag/DNS/timeout/JSON — hepsi FAIL
        print("HATA: Vercel API cagrisi basarisiz: %s" % e, file=sys.stderr)
        return 3

    dep = pick_latest_preview(payload.get("deployments"))
    if dep is None:
        print("HATA: READY preview deployment bulunamadi (limit=%d)" % args.limit,
              file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({
            "url": dep["url"],
            "target": dep.get("target"),
            "readyState": dep.get("readyState"),
            "createdAt": dep.get("createdAt"),
            "project_id": args.project_id,
        }, ensure_ascii=False))
    else:
        print(dep["url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
