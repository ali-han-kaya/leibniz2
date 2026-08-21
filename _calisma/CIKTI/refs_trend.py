#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refs_trend.py — `refs-online` artifact'larını run'lar arası toplar ve
"online verification trend" tablosu üretir (CrossRef/SEP/OpenLibrary ve
diğer kaynaklardan çevrimiçi doğrulanan referans sayısının zaman serisi).

Kaynak: GitHub Actions API — iki artifact türü run'lar arası toplanır:
  - `refs-online` → her zip'ten `references_online.json` (verify_delivery.py
    --refs-out'un ürettiği VERSION JSON) → çevrimiçi doğrulama zaman serisi.
  - `run-history` → her zip'ten `history.jsonl` (verify_delivery.py
    --history-out'un tek JSONL kaydı; ts/duration_s/budget_usd/verdict) →
    duration + budget trendi.

Kimlik:
  - CI: GITHUB_TOKEN env (workflow'da `actions: read` gerekir).
  - Yerel: token yoksa `gh api` (kullanıcı auth'u) kullanılır.

Çıktı (--out-dir):
  - refs-trend.md  — insan-okur tablo: refs trendi + duration/budget trendi
  - refs-trend.json — makine-okur {generated, repo, rows[], totals,
                     duration_budget{rows[], summary}}

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

# refs-trend raporu changelog'u (kısa kayıt; en yeni üstte).
# Kaynak: verify_delivery.py K6 denetimindeki düzeltmeler. Yeni bir denetim
# düzeltmesi yapıldığında buraya tek satır eklenir (denetlenebilir geçmiş).
CHANGELOG = [
    ("2026-08-21",
     "V5t: Della Rocca 2010 'PSR' artık CrossRef DIŞI Handle System API'den "
     "doğrulanır — makalenin kendi DC.identifier'ı bir Handle'dır "
     "(hdl.handle.net/2027/spo.3521354.0010.007), DOI yok; kaynak sayısı "
     "değişmedi (61/61 PASS)."),
    ("2026-08-19",
     "V5n: Norton 1981 ve Popkin 1951 DOI'leri CrossRef'e eklendi — kapsam-dışı "
     "kalan son 2 dergi makalesi artık çevrimiçi doğrulanır "
     "(canlı kapsam 54→56; 4fe2ccc)."),
    ("2026-08-18",
     "Hicks 1925 ve Hume 1975 OpenLibrary sorguları güçlendirildi "
     "(29/31 → 31/31 çevrimiçi doğrulama; ce5523b)."),
]


class _NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    """Redirect'te Authorization başlığını düşürür.

    GitHub `/zip` endpoint'i imzalı Azure blob URL'ine 302 yönlendirir.
    urllib varsayılan olarak Authorization'ı redirect'e taşır; blob depolama
    geçersiz Bearer token'ı 401 (InvalidAuthenticationInfo) ile reddeder.
    İmza URL'in kendisindedir — redirect'te auth başlığı gerekmez.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.remove_header("Authorization")
        return new


def api_get(path, token, binary=False):
    """GitHub API GET. Token varsa urllib, yoksa `gh api` (yerel auth)."""
    if token:
        req = urllib.request.Request(f"{API}{path}")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("User-Agent", "refs-trend")
        # Redirect'te Authorization'ı düşür (Azure blob 401'inin kökü).
        opener = urllib.request.build_opener(_NoAuthRedirect)
        with opener.open(req, timeout=60) as r:
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


def fetch_artifacts_by_name(repo, token, name, max_artifacts):
    """Son max_artifacts adet `name` artifact'ını toplar -> [dict] (tarih sıralı)."""
    rows = []
    page = 1
    while len(rows) < max_artifacts:
        path = (f"/repos/{repo}/actions/artifacts?name={name}"
                f"&per_page=100&page={page}")
        data = api_get(path, token)
        artifacts = data.get("artifacts", [])
        for a in artifacts:
            if a.get("name") == name:
                rows.append(a)
        if len(artifacts) < 100 or len(rows) >= max_artifacts:
            break
        page += 1
        if page > 10:  # güvenlik: en fazla 1000 artifact
            break
    rows.sort(key=lambda a: a.get("created_at", ""))
    return rows[-max_artifacts:]


def fetch_refs_online_artifacts(repo, token, max_artifacts):
    """Son max_artifacts adet `refs-online` artifact'ını toplar -> [dict]."""
    return fetch_artifacts_by_name(repo, token, "refs-online", max_artifacts)


def parse_report(blob):
    """Artifact zip'inden references_online.json'u ayrıştırır."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist()
                 if n.endswith("references_online.json")]
        if not names:
            raise ValueError("zip içinde references_online.json yok")
        return json.loads(z.read(names[0]).decode("utf-8"))


def parse_history_record(blob):
    """Artifact zip'inden history.jsonl'in son (en güncel) kaydını döndürür."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist() if n.endswith("history.jsonl")]
        if not names:
            raise ValueError("zip içinde history.jsonl yok")
        text = z.read(names[0]).decode("utf-8")
    last = None
    for line in text.splitlines():
        line = line.strip()
        if line:
            last = json.loads(line)
    if last is None:
        raise ValueError("history.jsonl boş")
    return last


def stats(vals):
    """Sayı listesi için {count,min,max,avg} özeti; boşsa {count:0,...}."""
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return {"count": 0, "min": None, "max": None, "avg": None}
    return {
        "count": len(vals),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
        "avg": round(sum(vals) / len(vals), 2),
    }


def short_date(iso):
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return (iso or "")[:16]


def changelog_lines():
    """CHANGELOG kaydını markdown satırlarına çevirir (boş liste = changelog yok).

    Tek kaynak: CHANGELOG sabiti. Denetim düzeltmelerinin kısa, denetlenebilir
    geçmişini refs-trend.md'nin altına ekler (en yeni üstte).
    """
    if not CHANGELOG:
        return []
    out = ["## Changelog", ""]
    for date, note in CHANGELOG:
        out.append(f"- **{date}:** {note}")
    out.append("")
    return out


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

    try:
        hist_artifacts = fetch_artifacts_by_name(args.repo, token,
                                                 "run-history",
                                                 args.max_artifacts)
    except Exception as e:
        print(f"  (run-history listelenemedi — {e}; duration/budget trendi boş)",
              file=sys.stderr)
        hist_artifacts = []

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

    history_rows = []
    for a in hist_artifacts:
        aid = a["id"]
        try:
            blob = api_get(f"/repos/{args.repo}/actions/artifacts/{aid}/zip",
                           token, binary=True)
            rec = parse_history_record(blob)
        except Exception as e:
            print(f"  (atlandı: run-history artifact {aid} "
                  f"({a.get('created_at')}) — {e})", file=sys.stderr)
            continue
        history_rows.append({
            "date": rec.get("ts", a.get("created_at", "")),
            "run_id": (a.get("workflow_run") or {}).get("id"),
            "duration_s": rec.get("duration_s"),
            "budget_usd": rec.get("budget_usd"),
            "verdict": rec.get("verdict"),
            "p0": rec.get("p0"),
            "p1": rec.get("p1"),
        })
    history_rows.sort(key=lambda r: r["date"])

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

    # ── Duration / Budget trendi (run-history) ───────────────────────────
    if history_rows:
        lines += [
            "## Duration / Budget trendi (run-history)",
            "",
            f"- **Kaynak:** `run-history` artifact'ları (son {len(history_rows)} run)",
            "",
            "| # | Tarih (UTC) | Run ID | Duration (s) | Budget (USD) | Verdict |",
            "|---|---|---|---|---|---|",
        ]
        for i, r in enumerate(history_rows, 1):
            dur = (f"{r['duration_s']:.1f}"
                   if isinstance(r["duration_s"], (int, float))
                   else (r["duration_s"]
                         if r["duration_s"] is not None else "—"))
            bud = (f"${r['budget_usd']:.2f}"
                   if isinstance(r["budget_usd"], (int, float))
                   else (r["budget_usd"]
                         if r["budget_usd"] is not None else "—"))
            lines.append(
                f"| {i} | {short_date(r['date'])} | {r['run_id'] or '-'} | "
                f"{dur} | {bud} | {r['verdict'] or '-'} |"
            )
        lines += [""]

        ds = stats([r["duration_s"] for r in history_rows])
        bs = stats([r["budget_usd"] for r in history_rows])

        def num(v, nd=1):
            return f"{v:.{nd}f}" if v is not None else "—"

        lines += [
            "**Duration özeti:** "
            f"min {num(ds['min'])} s · max {num(ds['max'])} s · "
            f"avg {num(ds['avg'])} s",
            "",
            "**Budget özeti:** "
            f"min ${num(bs['min'], 2)} · max ${num(bs['max'], 2)} · "
            f"avg ${num(bs['avg'], 2)}",
            "",
        ]

    # Changelog: denetim düzeltmelerinin kısa kaydı (kaynak: CHANGELOG).
    lines += changelog_lines()

    md_path = os.path.join(args.out_dir, "refs-trend.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))

    duration_budget = {
        "run_count": len(history_rows),
        "rows": history_rows,
        "summary": {
            "duration_s": stats([r["duration_s"] for r in history_rows]),
            "budget_usd": stats([r["budget_usd"] for r in history_rows]),
        },
    }
    summary = {
        "generated": generated,
        "repo": args.repo,
        "run_count": len(rows),
        "rows": rows,
        "totals": {
            "verified": sum(r["verified"] for r in rows),
            "total_online": sum(r["total_online"] for r in rows),
        } if rows else {"verified": 0, "total_online": 0},
        "duration_budget": duration_budget,
    }
    with open(os.path.join(args.out_dir, "refs-trend.json"), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[refs-trend] yazıldı: {md_path} "
          f"({len(rows)} refs + {len(history_rows)} history run)")


if __name__ == "__main__":
    main()
