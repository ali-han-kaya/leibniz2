#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
override_trend.py — `budget` artifact'larını run'lar arası toplar ve
"CLI override trend" tablosu üretir (warning=true run'larının zaman serisi).

Kaynak: GitHub Actions API — `budget` artifact'larındaki
cli_overrides_version.json (check_cli_overrides.py --version-out çıktısı).

Kimlik:
  - CI: GITHUB_TOKEN env (workflow'da `actions: read` gerekir).
  - Yerel: token yoksa `gh api` (kullanıcı auth'u) kullanılır.

Çıktı (--out-dir):
  - override-trend.md  — insan-okur tablo: CLI override zaman serisi
  - override-trend.json — makine-okur {generated, repo, rows[]}

Kullanım:
  GITHUB_TOKEN=... python3 _calisma/CIKTI/override_trend.py --repo owner/name \\
      --out-dir override-trend [--max-artifacts 50]

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


class _NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    """Redirect'te Authorization başlığını düşürür.

    GitHub `/zip` endpoint'i imzalı Azure blob URL'ine 302 yönlendirir.
    urllib varsayılan olarak Authorization'ı redirect'e taşır; blob depolama
    geçersiz Bearer token'ı 401 ile reddeder.
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
        req.add_header("User-Agent", "override-trend")
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
        if page > 10:
            break
    rows.sort(key=lambda a: a.get("created_at", ""))
    return rows[-max_artifacts:]


def parse_override_data(blob):
    """Artifact zip'inden cli_overrides_version.json'u ayrıştırır.

    Dosya budget/ alt dizininde veya kökte olabilir (upload-artifact yapısına
    bağlı olarak). İlk bulunan okunur.
    """
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            if name.endswith("cli_overrides_version.json"):
                return json.loads(z.read(name).decode("utf-8"))
    raise ValueError("zip içinde cli_overrides_version.json yok")


def short_date(iso):
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return (iso or "")[:16]


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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--out-dir", default="override-trend")
    ap.add_argument("--max-artifacts", type=int, default=50,
                    help="işlenecek en fazla artifact (varsayılan 50)")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    os.makedirs(args.out_dir, exist_ok=True)
    generated = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Fetch budget artifacts
    try:
        artifacts = fetch_artifacts_by_name(args.repo, token,
                                            "budget", args.max_artifacts)
    except Exception as e:
        print(f"HATA: budget artifact listelenemedi — {e}", file=sys.stderr)
        sys.exit(1)

    rows = []
    for a in artifacts:
        aid = a["id"]
        try:
            blob = api_get(f"/repos/{args.repo}/actions/artifacts/{aid}/zip",
                           token, binary=True)
            data = parse_override_data(blob)
        except Exception as e:
            # cli_overrides_version.json her budget artifact'ında olmayabilir
            # (eski run'lar veya check_cli_overrides koşmadıysa)
            print(f"  (atlandı: artifact {aid} ({a.get('created_at')}) — {e})",
                  file=sys.stderr)
            continue

        warning = data.get("warning", False)
        override_count = data.get("override_count", 0)
        overrides = data.get("overrides", [])

        # Her override için özet: key → file_value → effective
        override_keys = [o.get("key", "?") for o in overrides]
        override_detail = ", ".join(
            f"{o.get('key','?')}: {o.get('file_value')} → {o.get('effective')}"
            for o in overrides
        ) if overrides else ""

        rows.append({
            "date": data.get("generated_at",
                             a.get("created_at", "")),
            "run_id": (a.get("workflow_run") or {}).get("id"),
            "artifact_id": aid,
            "warning": warning,
            "override_count": override_count,
            "override_keys": override_keys,
            "override_detail": override_detail,
        })

    rows.sort(key=lambda r: r["date"])

    # ── Markdown tablo ───────────────────────────────────────────────────
    lines = [
        "# CLI Override Trendi (cli_overrides_version.json)",
        "",
        f"- **Kaynak:** `budget` artifact'larındaki `cli_overrides_version.json`"
        f" (son {len(rows)} run)",
        f"- **Üretim:** override_trend.py — {generated}",
        f"- **Repo:** {args.repo}",
        "",
    ]
    if not rows:
        lines += [
            "## Veri yok",
            "",
            "Henüz `budget` artifact'ından `cli_overrides_version.json` "
            "bulunamadı. İlk `budget` run'ları bu tabloyu doldurmaya başlar.",
            "",
        ]
    else:
        lines += [
            "| # | Tarih (UTC) | Run ID | Warning | Count | Override detayı |",
            "|---|---|---|---|---|---|",
        ]
        for i, r in enumerate(rows, 1):
            warn_icon = "⚠️" if r["warning"] else "—"
            lines.append(
                f"| {i} | {short_date(r['date'])} | {r['run_id'] or '-'} | "
                f"{warn_icon} | {r['override_count']} | "
                f"{r['override_detail'] or '—'} |"
            )
        lines += [""]

        # Özet
        warning_runs = [r for r in rows if r["warning"]]
        latest = rows[-1]
        lines += [
            "## Özet",
            "",
            f"- **Run sayısı:** {len(rows)}",
            f"- **Warning=true run sayısı:** {len(warning_runs)}",
            f"- **Warning oranı:** "
            f"{len(warning_runs) / len(rows) * 100:.1f}%",
            f"- **En güncel run:** {short_date(latest['date'])} "
            f"(run {latest['run_id']}) — "
            f"{'⚠️ override VAR' if latest['warning'] else 'override YOK'}",
            f"- **İlk run:** {short_date(rows[0]['date'])} — "
            f"warning={'TRUE' if rows[0]['warning'] else 'FALSE'}",
            "",
        ]

        # Warning dağılımı
        if warning_runs:
            # Hangi override_key'lerden kaçar kere görüldü
            key_counts = {}
            for r in warning_runs:
                for k in r["override_keys"]:
                    key_counts[k] = key_counts.get(k, 0) + 1
            lines += [
                "### Override anahtarı dağılımı",
                "",
                "| Anahtar | Görülme sayısı |",
                "|---|---|",
            ]
            for k in sorted(key_counts):
                lines.append(f"| `{k}` | {key_counts[k]} |")
            lines += [""]

        # En son override'lar
        if warning_runs:
            last_warn = warning_runs[-1]
            lines += [
                "### En son override kaydı",
                "",
                f"- **Tarih:** {short_date(last_warn['date'])}",
                f"- **Run ID:** {last_warn['run_id'] or '-'}",
                f"- **Override sayısı:** {last_warn['override_count']}",
                f"- **Detay:** {last_warn['override_detail'] or '—'}",
                "",
            ]

    md_path = os.path.join(args.out_dir, "override-trend.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))

    summary = {
        "generated": generated,
        "repo": args.repo,
        "run_count": len(rows),
        "warning_run_count": len([r for r in rows if r["warning"]]),
        "rows": rows,
        "override_counts": stats([r["override_count"] for r in rows]),
    }
    with open(os.path.join(args.out_dir, "override-trend.json"), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[override-trend] yazıldı: {md_path} "
          f"({len(rows)} run, {summary['warning_run_count']} warning)")


if __name__ == "__main__":
    main()