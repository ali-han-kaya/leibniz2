#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refs_trend.py — `refs-online` artifact'larını run'lar arası toplar ve
"online verification trend" tablosu üretir (CrossRef/SEP/OpenLibrary ve
diğer kaynaklardan çevrimiçi doğrulanan referans sayısının zaman serisi).

Kaynak: GitHub Actions API — `repos/{owner}/{repo}/actions/artifacts?name=
refs-online` → her artifact'ın zip'inden `references_online.json` çıkarılır
(verify_delivery.py --refs-out'un ürettiği VERSION JSON).

Kimlik:
  - CI: GITHUB_TOKEN env (workflow'da `actions: read` gerekir).
  - Yerel: token yoksa `gh api` (kullanıcı auth'u) kullanılır.

Çıktı (--out-dir):
  - refs-trend.md  — insan-okur trend tablosu + özet
  - refs-trend.json — makine-okur {generated, repo, rows[], summary}

Kullanım:
  GITHUB_TOKEN=... python3 _calisma/CIKTI/refs_trend.py --repo owner/name \\
      --out-dir refs-trend [--max-artifacts 100]

Çıkış kodları: 0 her zaman (veri yoksa boş tablo + not; API hatası → 1,
advisory job continue-on-error ile tolere eder).
"""
import argparse
import datetime
import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile

API = "https://api.github.com"


def api_get(path, token, binary=False):
    """GitHub API GET. Token varsa urllib, yoksa `gh api` (yerel auth)."""
    if token:
        req = urllib.request.Request(f"{API}{path}")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("User-Agent", "refs-trend")
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        return data if binary else json.loads(data.decode("utf-8"))
    cmd = ["gh", "api", path]
    r = subprocess.run(cmd, capture_output=True, text=not binary)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "gh api hatası").strip())
    out = r.stdout
    if binary:
        # text=False iken bytes, text=True iken str gelebilir.
        return out if isinstance(out, bytes) else out.encode()
    return json.loads(out.decode("utf-8") if isinstance(out, bytes) else out)


def fetch_refs_online_artifacts(repo, token, max_artifacts):
    """Son max_artifacts adet `refs-online` artifact'ını toplar -> [dict]."""
    rows = []
    page = 1
    while len(rows) < max_artifacts:
        path = (f"/repos/{repo}/actions/artifacts?name=refs-online"
                f"&per_page=100&page={page}")
        data = api_get(path, token)
        artifacts = data.get("artifacts", [])
        for a in artifacts:
            if a.get("name") == "refs-online":
                rows.append(a)
        if len(artifacts) < 100 or len(rows) >= max_artifacts:
            break
        page += 1
        if page > 10:  # güvenlik: en fazla 1000 artifact
            break
    rows.sort(key=lambda a: a.get("created_at", ""))
    return rows[-max_artifacts:]


def parse_report(blob):
    """Artifact zip'inden references_online.json'u ayrıştırır."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist()
                 if n.endswith("references_online.json")]
        if not names:
            raise ValueError("zip içinde references_online.json yok")
        return json.loads(z.read(names[0]).decode("utf-8"))


def short_date(iso):
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return (iso or "")[:16]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--out-dir", default="refs-trend")
    ap.add_argument("--max-artifacts", type=int, default=100,
                    help="işlenecek en fazla artifact (varsayılan 100)")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    os.makedirs(args.out_dir, exist_ok=True)
    generated = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        artifacts = fetch_refs_online_artifacts(args.repo, token,
                                                args.max_artifacts)
    except Exception as e:
        print(f"HATA: refs-online artifact listelenemedi — {e}", file=sys.stderr)
        sys.exit(1)

    rows = []
    for a in artifacts:
        aid = a["id"]
        try:
            blob = api_get(f"/repos/{args.repo}/actions/artifacts/{aid}/zip",
                           token, binary=True)
            rep = parse_report(blob)
        except Exception as e:
            print(f"  (atlandı: artifact {aid} ({a.get('created_at')}) — {e})",
                  file=sys.stderr)
            continue
        by_source = rep.get("by_source", {})
        rows.append({
            "date": rep.get("date", a.get("created_at", "")),
            "run_id": (a.get("workflow_run") or {}).get("id"),
            "total_online": rep.get("total_online", 0),
            "verified": rep.get("verified", 0),
            "unverified": rep.get("unverified", 0),
            "mismatch": rep.get("mismatch", 0),
            "by_source": by_source,
        })

    rows.sort(key=lambda r: r["date"])

    # ── Markdown tablo ───────────────────────────────────────────────────
    lines = [
        "# Çevrimiçi Referans Doğrulama Trendi (refs-online)",
        "",
        f"- **Kaynak:** `refs-online` artifact'ları (GitHub API, son "
        f"{len(rows)} run)",
        f"- **Üretim:** refs_trend.py — {generated}",
        f"- **Repo:** {args.repo}",
        "",
    ]
    if not rows:
        lines += [
            "## Veri yok",
            "",
            "Henüz `refs-online` artifact'ı bulunamadı. İlk `verify` run'ları",
            "bu tabloyu doldurmaya başlar (her run bir satır).",
            "",
        ]
    else:
        lines += [
            "| # | Tarih (UTC) | Run ID | Toplam | Doğrulanan | "
            "Doğrulanamayan | Uyumsuz | Kaynak dağılımı |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for i, r in enumerate(rows, 1):
            src = ", ".join(f"{k}={v}" for k, v in
                            sorted(r["by_source"].items()))
            lines.append(
                f"| {i} | {short_date(r['date'])} | {r['run_id'] or '-'} | "
                f"{r['total_online']} | {r['verified']} | {r['unverified']} | "
                f"{r['mismatch']} | {src} |"
            )
        lines += [""]

        # Özet
        verified_all = sum(r["verified"] for r in rows)
        latest = rows[-1]
        lines += [
            "## Özet",
            "",
            f"- **Run sayısı:** {len(rows)}",
            f"- **En güncel run:** {short_date(latest['date'])} "
            f"(run {latest['run_id']}) — {latest['verified']}/{latest['total_online']} "
            "doğrulanan",
            f"- **Tüm run'lar toplam doğrulanan:** {verified_all}",
            f"- **Ortalama doğrulanan/run:** "
            f"{verified_all / len(rows):.1f}",
            f"- **İlk run:** {short_date(rows[0]['date'])} — "
            f"{rows[0]['verified']}/{rows[0]['total_online']} doğrulanan",
            "",
        ]

    md_path = os.path.join(args.out_dir, "refs-trend.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))

    summary = {
        "generated": generated,
        "repo": args.repo,
        "run_count": len(rows),
        "rows": rows,
        "totals": {
            "verified": sum(r["verified"] for r in rows),
            "total_online": sum(r["total_online"] for r in rows),
        },
    } if rows else {
        "generated": generated,
        "repo": args.repo,
        "run_count": 0,
        "rows": [],
        "totals": {"verified": 0, "total_online": 0},
    }
    with open(os.path.join(args.out_dir, "refs-trend.json"), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[refs-trend] yazıldı: {md_path} ({len(rows)} run)")


if __name__ == "__main__":
    main()
