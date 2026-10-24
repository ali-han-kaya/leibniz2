#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cls_trend.py — `cls-budget` artifact'larını run'lar arası toplar.

İKİ İDDİA birlikte denetlenir:

  1. **Bütçe** (mutlak): her run'da tema başına CLS < 0.1. Bütçe aşımı zaten
     `a11y-gate` içindeki CLS kapısında BLOKE eder; trend bunu tarihsel
     olarak görünür kılar (`budget_breaches`).
  2. **Bütçe-ALTI regresyon** (göreli): CLS bütçenin altında kalsa bile
     önceki run'lara göre sıçrıyorsa yakalanır. 0.09 < 0.1 olduğu için
     bütçe kapısından geçen ama 0.0001'den 0.09'a çıkan bir sayfa
     "yeşil" görünürdü; bu modül o boşluğu kapatır.

Kaynak: GitHub Actions API — son N `cls-budget` artifact'ındaki
`cls_budget.json` (test_dashboard_cls_budget.py CLS_REPORT_PATH çıktısı).

Kimlik: CI'da `GITHUB_TOKEN` + `actions: read`; token yoksa `gh api`
(kullanıcı auth'u). API/ayrıştırma erişimi `refs_trend.py`'den gelir
(tek kaynak — üçüncü bir kopya yok).

Regresyon kuralı (deterministik, iki eşik BİRLİKTE):
  - taban = önceki `--window` run'ın tema başına CLS **medyanı** (son run
    hariç; medyan tek bir aykırı run'a duyarlı değil),
  - göreli eşik: `current > baseline * (1 + --tolerance)` (vars. %20),
  - mutlak taban: `current - baseline >= --min-delta` (vars. 0.005 ≈
    bütçenin %5'i) — mikro gürültüyü regresyon saymamak için.
  İkisi de sağlanırsa o tema REGRESYON'dur.

Kararlar (fail-closed, sessiz PASS yok):
  - PASS        → geçmiş var, regresyon yok (exit 0)
  - REGRESSION  → en az bir tema regresyonda (exit 1)
  - SKIP        → geçmiş yetersiz (< --min-history run) — PASS DEĞİL;
                  tablo "baseline yok" der, exit 0 (ilk run'lar bloke olmaz)
  - ERROR       → en güncel rapor okunamadı/şeması boş → doğrulanamaz (exit 1)
  - API/zip hatası → hiçbir artifact yazılmaz, exit 1 (fail-closed)

Çıktı (--out-dir):
  - cls-trend.json   — makine-okur {verdict, baseline, themes[], regressions,
                        budget_breaches, rows[]}
  - cls-trend.jsonl  — KOŞUM GEÇMİŞİ: satır başına bir run (deterministik,
                        tarih sıralı; `sort_keys` ile byte-kararlı)
  - cls-trend.md     — insan-okur tablo (run summary'ye de eklenir)

Kullanım:
  GITHUB_TOKEN=... python3 _calisma/CIKTI/cls_trend.py --repo owner/name \\
      --out-dir cls-trend [--max-artifacts 50] [--summary]

Ortam override'ları: CLS_TREND_TOLERANCE, CLS_TREND_MIN_DELTA,
CLS_TREND_WINDOW, CLS_TREND_MIN_HISTORY.
"""
import argparse
import json
import math
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# API/token/zip yardımcıları TEK KAYNAK: refs_trend.py (aynı kullanıcı
# auth fallback'i, aynı redirect-token düşürme davranışı).
import refs_trend as rt  # noqa: E402

ARTIFACT_NAME = "cls-budget"
DEFAULT_TOLERANCE = 0.20
DEFAULT_MIN_DELTA = 0.005
DEFAULT_WINDOW = 10
DEFAULT_MIN_HISTORY = 2


# ─────────────────────────────────────────────────────────────── ayrıştırma
def _as_value(v):
    """CLS değerini güvenli float'a çevir; geçersiz → None (fail-closed).

    bool KABUL EDİLMEZ (Python'da bool int'tir; `True` bir ölçüm değildir),
    NaN/inf/negatif değerler de ölçüm sayılmaz.
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    if math.isnan(f) or math.isinf(f) or f < 0:
        return None
    return f


def parse_cls_report(blob):
    """Artifact zip'inden `cls_budget.json`'u ayrıştırır (ilk eşleşme)."""
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            if name.endswith("cls_budget.json"):
                return json.loads(z.read(name).decode("utf-8"))
    raise ValueError("zip içinde cls_budget.json yok")


def record_row(artifact, report):
    """Bir artifact + rapor → tarihsel kayıt satırı (artifact metadata'sıyla).

    `run_id`/`date` artifact API kaydından gelir: raporun kendisi run kimliği
    taşımaz (test modülü CI ortamını bilmek zorunda kalmasın).
    """
    themes = {}
    for name, data in sorted((report.get("themes") or {}).items()):
        data = data or {}
        themes[name] = {
            "cls": _as_value(data.get("cls")),
            "verdict": data.get("verdict"),
        }
    return {
        "date": artifact.get("created_at") or "",
        "run_id": (artifact.get("workflow_run") or {}).get("id"),
        "artifact_id": artifact.get("id"),
        "budget": _as_value(report.get("budget")),
        "verdict": report.get("verdict"),
        "themes": themes,
    }


def _fetch_records(repo, token, max_artifacts):
    """Son N `cls-budget` artifact'ını indirip kayıt satırlarına çevirir.

    Okunamayan tek artifact tüm trendi düşürmez (eski/bozuk run atlanır ve
    stderr'e yazılır); hiç kayıt yoksa çağıran ERROR verir.
    """
    artifacts = rt.fetch_artifacts_by_name(repo, token, ARTIFACT_NAME,
                                           max_artifacts)
    rows = []
    for a in artifacts:
        aid = a.get("id")
        try:
            blob = rt.api_get(f"/repos/{repo}/actions/artifacts/{aid}/zip",
                              token, binary=True)
            rows.append(record_row(a, parse_cls_report(blob)))
        except Exception as e:  # noqa: BLE001 — atlanan artifact rapordan düşmez
            print(f"  (atlandı: artifact {aid} ({a.get('created_at')}) — {e})",
                  file=sys.stderr)
    rows.sort(key=lambda r: (r["date"], r["run_id"] or 0))
    return rows


# ─────────────────────────────────────────────────────────────── matematik
def median(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def detect_regressions(rows, tolerance=DEFAULT_TOLERANCE,
                       min_delta=DEFAULT_MIN_DELTA, window=DEFAULT_WINDOW,
                       min_history=DEFAULT_MIN_HISTORY):
    """Bütçe-altı regresyonları bulur (saf fonksiyon — IO yok).

    Döndürür:
      {"verdict": PASS|REGRESSION|SKIP|ERROR, "reason": str|None,
       "baseline_runs": int,
       "themes": [{theme, current, baseline, delta, ratio, threshold,
                   regressed: bool}],
       "regressions": [theme...],
       "budget_breaches": [{date, run_id, theme, cls, budget}]}
    """
    out = {"verdict": "SKIP", "reason": None, "baseline_runs": 0,
           "themes": [], "regressions": [], "budget_breaches": []}

    if not rows:
        out["reason"] = "hiç cls-budget artifact'ı yok"
        return out

    current = rows[-1]
    previous = rows[:-1][-window:] if window > 0 else []
    out["baseline_runs"] = len(previous)

    # Bütçe ihlalleri: pencere + güncel run boyunca ölçülen her değer için.
    for r in previous + [current]:
        budget = r.get("budget")
        if budget is None:
            continue
        for theme, data in sorted((r.get("themes") or {}).items()):
            cls = data.get("cls")
            if cls is not None and cls >= budget:
                out["budget_breaches"].append({
                    "date": r.get("date"), "run_id": r.get("run_id"),
                    "theme": theme, "cls": cls, "budget": budget,
                })

    current_themes = {t: d.get("cls") for t, d in
                      (current.get("themes") or {}).items()
                      if d.get("cls") is not None}
    if not current_themes:
        # En güncel rapor doğrulanamıyorsa "PASS" demek sessiz yeşil olurdu.
        out["verdict"] = "ERROR"
        out["reason"] = ("en güncel cls-budget raporunda ölçülmüş tema yok "
                         "(şema bozuk ya da ölçüm yapılmamış)")
        return out

    if len(previous) < max(1, min_history):
        out["reason"] = (f"karşılaştırma için yeterli geçmiş yok "
                         f"({len(previous)} < {min_history} run)")
        return out

    for theme in sorted(current_themes):
        cur = current_themes[theme]
        baseline = median([
            ((r.get("themes") or {}).get(theme) or {}).get("cls")
            for r in previous
        ])
        if baseline is None:
            out["themes"].append({
                "theme": theme, "current": cur, "baseline": None,
                "delta": None, "ratio": None, "threshold": None,
                "regressed": False,
            })
            continue
        delta = cur - baseline
        threshold = baseline * (1.0 + tolerance)
        # İki eşik BİRLİKTE: göreli sıçrama VE anlamlı mutlak artış.
        regressed = cur > threshold and delta >= min_delta
        ratio = (cur / baseline) if baseline > 0 else None
        out["themes"].append({
            "theme": theme,
            "current": cur,
            "baseline": baseline,
            "delta": delta,
            "ratio": ratio,
            "threshold": threshold,
            "regressed": bool(regressed),
        })
        if regressed:
            out["regressions"].append(theme)

    out["verdict"] = "REGRESSION" if out["regressions"] else "PASS"
    return out


# ─────────────────────────────────────────────────────────────── çıktılar
def build_trend(rows, tolerance=DEFAULT_TOLERANCE, min_delta=DEFAULT_MIN_DELTA,
                window=DEFAULT_WINDOW, min_history=DEFAULT_MIN_HISTORY):
    """CLI/JSON payload'ı — `generated` YOK (deterministik artifacts)."""
    decision = detect_regressions(rows, tolerance, min_delta, window,
                                  min_history)
    return {
        "artifact": ARTIFACT_NAME,
        "verdict": decision["verdict"],
        "reason": decision["reason"],
        "policy": {"tolerance": tolerance, "min_delta": min_delta,
                   "window": window, "min_history": min_history},
        "run_count": len(rows),
        "baseline_runs": decision["baseline_runs"],
        "themes": decision["themes"],
        "regressions": decision["regressions"],
        "budget_breaches": decision["budget_breaches"],
        "rows": rows,
    }


def history_jsonl(rows):
    """Koşum geçmişi: satır başına bir run, byte-kararlı (sort_keys)."""
    lines = [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows]
    return "\n".join(lines) + ("\n" if lines else "")


def render_markdown(trend):
    icon = {"PASS": "✅", "REGRESSION": "🔴", "SKIP": "⏭️",
            "ERROR": "🔴"}.get(trend["verdict"], "❔")
    lines = [
        f"### {icon} CLS bütçe trendi — {trend['verdict']}",
        "",
        f"- **Kaynak:** `{ARTIFACT_NAME}` artifact'larındaki `cls_budget.json`"
        f" (son {trend['run_count']} run)",
        f"- **Politika:** taban = önceki {trend['baseline_runs']} run'ın "
        f"medyanı · göreli eşik +%{trend['policy']['tolerance'] * 100:.0f} · "
        f"mutlak taban {trend['policy']['min_delta']}",
    ]
    if trend["reason"]:
        lines.append(f"- **Not:** {trend['reason']}")
    lines += ["", "| Tema | Güncel CLS | Taban (medyan) | Δ | Eşik | Karar |",
              "|---|---|---|---|---|---|"]
    for t in trend["themes"]:
        if t["baseline"] is None:
            lines.append(f"| `{t['theme']}` | {t['current']:.6f} | — | — | — "
                         f"| taban yok |")
            continue
        verdict = "🔴 REGRESYON" if t["regressed"] else "✅"
        lines.append(
            f"| `{t['theme']}` | {t['current']:.6f} | {t['baseline']:.6f} "
            f"| {t['delta']:+.6f} | {t['threshold']:.6f} | {verdict} |")
    lines.append("")

    if trend["budget_breaches"]:
        lines += ["**Bütçe ihlalleri (pencere içinde):**", ""]
        for b in trend["budget_breaches"]:
            lines.append(f"- `{b['date']}` run {b['run_id']} · "
                         f"`{b['theme']}` CLS={b['cls']:.6f} ≥ "
                         f"{b['budget']:.6f}")
        lines.append("")
    else:
        lines += ["Bütçe ihlali yok (pencere içinde).", ""]

    if trend["regressions"]:
        lines += ["**Regresyonlu temalar:** "
                  + ", ".join(f"`{t}`" for t in trend["regressions"]), ""]
    return "\n".join(lines)


def main(argv=None, fetch=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--out-dir", default="cls-trend")
    ap.add_argument("--max-artifacts", type=int, default=50)
    ap.add_argument("--window", type=int,
                    default=int(os.environ.get("CLS_TREND_WINDOW",
                                               DEFAULT_WINDOW)))
    ap.add_argument("--min-history", type=int,
                    default=int(os.environ.get("CLS_TREND_MIN_HISTORY",
                                               DEFAULT_MIN_HISTORY)))
    ap.add_argument("--tolerance", type=float,
                    default=float(os.environ.get("CLS_TREND_TOLERANCE",
                                                 DEFAULT_TOLERANCE)))
    ap.add_argument("--min-delta", type=float,
                    default=float(os.environ.get("CLS_TREND_MIN_DELTA",
                                                 DEFAULT_MIN_DELTA)))
    ap.add_argument("--summary", action="store_true",
                    help="markdown'ı GITHUB_STEP_SUMMARY'ye de ekle")
    ap.add_argument("--fetch-retries", type=int, default=4,
                    help="bu run'ın artifact'ı görünene kadar yeniden dene")
    ap.add_argument("--retry-delay", type=float, default=5.0,
                    help="denemeler arası bekleme (saniye)")
    args = ap.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN", "")
    fetch = fetch or _fetch_records
    expected_run = (os.environ.get("GITHUB_RUN_ID") or "").strip()

    def _fetch_once():
        return fetch(args.repo, token, args.max_artifacts)

    try:
        rows = _fetch_once()
        # Artifact görünürlüğü gecikebilir (upload → API listesi). Bu run'ın
        # artifact'ı henüz listede yoksa kısa bir backoff'la yeniden dene;
        # yine yoksa ERROR (bayat PASS yok).
        attempt = 0
        while (expected_run and attempt < args.fetch_retries
               and (not rows or str(rows[-1].get("run_id")) != expected_run)):
            attempt += 1
            print(f"  (bu run'ın cls-budget artifact'ı henüz görünmüyor — "
                  f"deneme {attempt}/{args.fetch_retries})", file=sys.stderr)
            time.sleep(args.retry_delay)
            rows = _fetch_once()
    except Exception as e:  # noqa: BLE001 — API hatası fail-closed
        print(f"HATA: cls-budget artifact'ları alınamadı — {e}",
              file=sys.stderr)
        return 1

    trend = build_trend(rows, tolerance=args.tolerance,
                        min_delta=args.min_delta, window=args.window,
                        min_history=args.min_history)

    # Fail-closed: CI'da "güncel" satır bu run'ın kendi artifact'ı olmalı.
    # a11y-gate ölçümden önce düştüyse en yeni artifact ESKİ bir run'dır;
    # onu güncel saymak bayat bir PASS üretirdi (trend kapısı kendi run'ını
    # doğrulamadan yeşil veremez).
    newest = str(rows[-1].get("run_id")) if rows else "-"
    if expected_run and newest != expected_run:
        trend["verdict"] = "ERROR"
        trend["reason"] = ("bu run'ın cls-budget artifact'ı yok "
                           f"(beklenen run {expected_run}, en güncel {newest})")

    md = render_markdown(trend)

    os.makedirs(args.out_dir, exist_ok=True)
    rt._write_atomic(os.path.join(args.out_dir, "cls-trend.json"),
                     json.dumps(trend, indent=2, ensure_ascii=False,
                                sort_keys=True))
    rt._write_atomic(os.path.join(args.out_dir, "cls-trend.jsonl"),
                     history_jsonl(rows))
    rt._write_atomic(os.path.join(args.out_dir, "cls-trend.md"), md + "\n")
    print(md)

    if args.summary:
        dest = os.environ.get("GITHUB_STEP_SUMMARY")
        if dest:
            with open(dest, "a", encoding="utf-8") as f:
                f.write("\n" + md + "\n")

    print(f"[cls-trend] {trend['verdict']} — {trend['run_count']} run, "
          f"{len(trend['regressions'])} regresyon, "
          f"{len(trend['budget_breaches'])} bütçe ihlali", file=sys.stderr)
    return 0 if trend["verdict"] in ("PASS", "SKIP") else 1


if __name__ == "__main__":
    raise SystemExit(main())
