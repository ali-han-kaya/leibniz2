#!/usr/bin/env python3
"""Badge endpoint checker — README'deki badge URL'lerinin HTTP 200 döndüğünü doğrula.

CI'da advisory bir adım olarak koşulur: badge kırıksa run summary'ye uyarı
düşer ama job fail etmez (badge URL'i değişirse güncellenmeli).

Kullanım:
    python3 check_badge_endpoints.py              # README'den badge'leri oku
    python3 check_badge_endpoints.py --json        # JSON çıktı
    python3 check_badge_endpoints.py --strict      # Badge kırıksa exit 1
    python3 check_badge_endpoints.py --timeout 15  # Timeout (saniye)
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
import ssl


# README.md yolu (bu script'ten bir üst dizin)
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_README = os.path.join(_REPO_ROOT, "README.md")

# Badge URL regex: ![alt](url) veya [![alt](url)](link)
_BADGE_RE = re.compile(r"!\[([^\]]*)\]\((https?://[^)]+)\)")

# Known badge URL patterns (README'den çıkarılır, fallback olarak da kullanılır)
_FALLBACK_BADGES = [
    {
        "label": "CI status",
        "url": "https://github.com/ali-han-kaya/leibniz2/actions/workflows/verify.yml/badge.svg",
        "source": "github-actions",
    },
    {
        "label": "pre-commit",
        "url": "https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white",
        "source": "shields.io",
    },
    {
        "label": "License: MIT + CC-BY-4.0",
        "url": "https://img.shields.io/badge/License-MIT%20%2B%20CC--BY--4.0-blue.svg",
        "source": "shields.io",
    },
]


def extract_badges_from_readme(readme_path=None):
    """README.md'den badge URL'lerini çıkarır.

    Returns: [{label, url, source}]
    """
    path = readme_path or _README
    if not os.path.isfile(path):
        return list(_FALLBACK_BADGES)

    with open(path, encoding="utf-8") as f:
        content = f.read()

    badges = []
    for m in _BADGE_RE.finditer(content):
        label = m.group(1)
        url = m.group(2)
        # Kaynağı belirle
        if "shields.io" in url or "img.shields.io" in url:
            source = "shields.io"
        elif "github.com" in url:
            source = "github-actions"
        else:
            source = "other"
        badges.append({"label": label, "url": url, "source": source})

    return badges if badges else list(_FALLBACK_BADGES)


def check_badge(url, timeout=10):
    """Tek bir badge URL'ini HTTP HEAD/GET ile kontrol eder.

    Returns: {url, status, ok, error}
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # shields.io sertifika sorunları için

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "leibniz2-badge-checker/1.0")
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            status = resp.getcode()
            return {"url": url, "status": status, "ok": 200 <= status < 400,
                    "error": None}
    except urllib.error.HTTPError as e:
        return {"url": url, "status": e.code, "ok": False,
                "error": str(e)}
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return {"url": url, "status": 0, "ok": False, "error": str(e)}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Badge endpoint checker")
    ap.add_argument("--json", action="store_true", help="JSON çıktı")
    ap.add_argument("--strict", action="store_true",
                    help="Badge kırıksa exit 1")
    ap.add_argument("--timeout", type=int, default=10,
                    help="HTTP timeout (saniye)")
    ap.add_argument("--readme", default=None,
                    help="README.md yolu (varsayılan: repo root)")
    args = ap.parse_args()

    badges = extract_badges_from_readme(args.readme)
    results = []

    for badge in badges:
        r = check_badge(badge["url"], timeout=args.timeout)
        r["label"] = badge["label"]
        r["source"] = badge["source"]
        results.append(r)

    ok_count = sum(1 for r in results if r["ok"])
    fail_count = len(results) - ok_count

    if args.json:
        print(json.dumps({
            "badges": results,
            "ok_count": ok_count,
            "fail_count": fail_count,
            "total": len(results),
        }, indent=2))
    else:
        for r in results:
            icon = "✅" if r["ok"] else "❌"
            status_str = str(r["status"]) if r["status"] else "ERR"
            err = f" ({r['error']})" if r["error"] else ""
            print(f"  {icon} [{r['source']:>15}] {r['label']:<20} "
                  f"HTTP {status_str}{err}")
        print()
        print(f"  Toplam: {len(results)} badge · "
              f"✅ {ok_count} · ❌ {fail_count}")

    if fail_count > 0:
        print(f"\n⚠️  {fail_count} badge kırık/mevcut değil!", file=sys.stderr)
        if args.strict:
            sys.exit(1)
    else:
        print("\n✅ Tüm badge'ler canlı (HTTP 200).")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
