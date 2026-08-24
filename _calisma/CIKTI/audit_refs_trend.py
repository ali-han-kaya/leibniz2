#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_refs_trend.py — refs-trend denetimi: trend satırları ↔ kaynak artifact.

refs_trend.py'nin ürettiği `refs-trend.json` (ve .md) satırlarını, o trendi
besleyen KAYNAK `refs-online` artifact'larındaki `references_online.json` ile
karşılaştırır. Amaç: "trend satırı üretildikten sonra kaynak değişti" veya
"trend satırı kaynakla uyumsuz (elle eklenmiş / bayat / yanlış parse)" drift'ini
tekrar edilebilir biçimde yakala — manuel `gh run download` + göz kararı yerine.

Karşılaştırılan eksenler (her trend satırı için):
  1) KAYNAK VARLIĞI — trend satırının run_id'si için kaynak artifact'ı var mı?
     (yoksa: sahte/elle eklenmiş satır → FAIL)
  2) SAYI EŞLEŞMESİ — total_online / verified / unverified / mismatch, kaynak
     `references_online.json` ile birebir aynı mı? (değilse: bayat/yanlış → FAIL)
  3) KAYNAK DAĞILIMI — by_source sözlüğü kaynakla birebir aynı mı?
  4) KAPSAM — trend kaç run içeriyorsa, kaynak artifact'ların o pencere içindeki
     run'larının hepsi trendde var mı? (eksikse: trend bayat / artifact düşmüş)

Fail-closed: herhangi bir uyumsuzluk → exit 1 (JSON'da verdict: FAIL).
Çalışma hatası (trend json yok, API çekilemedi) → exit 2.
0 — trend kaynakla birebir tutarlı.

Not: refs_trend.py'nin fetch/parse fonksiyonları YENİDEN kullanılır (kod
çoğaltmaz) — trend üretimi ile denetim aynı tek kaynaktan beslenir, böylece
"üretici ve denetçi farklı şeyler okuyor" drift'i de kapanır.

Kullanım:
  python3 _calisma/CIKTI/audit_refs_trend.py --repo owner/name \\
      --trend-json refs-trend/refs-trend.json [--max-artifacts 100]
  python3 _calisma/CIKTI/audit_refs_trend.py --repo owner/name \\
      --trend-json refs-trend/refs-trend.json --json
"""
import argparse
import json
import os
import pathlib
import sys

# refs_trend.py'nin fetch/parse fonksiyonlarını tek kaynak olarak kullan.
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import refs_trend as rt  # noqa: E402


def load_trend(trend_path):
    """refs-trend.json'u okur. Döndürür: {rows: [...], generated, ...}.

    Dosya yoksa / bozuksa RuntimeError (çağıran exit 2).
    """
    p = pathlib.Path(trend_path)
    if not p.is_file():
        raise RuntimeError(f"trend json bulunamadı ({p})")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"trend json okunamadı ({p}): {e}")


def _row_key(row):
    """Trend satırının karşılaştırma anahtarı (run_id varsa onu, yoksa date)."""
    rid = row.get("run_id")
    if rid is not None:
        return ("run_id", str(rid))
    return ("date", str(row.get("date", "")))


def _norm_by_source(bs):
    """by_source sözlüğünü karşılaştırılabilir biçime getirir (None → {})."""
    return dict(bs or {})


def compare_row(row, source_report):
    """Tek trend satırını kaynak references_online.json ile karşılaştırır.

    Döndürür: [finding dict] — boşsa satır kaynakla birebir uyumlu.
    """
    findings = []
    fields = ["total_online", "verified", "unverified", "mismatch"]
    for f in fields:
        exp = row.get(f)
        got = source_report.get(f)
        if exp != got:
            findings.append({
                "kind": "count",
                "field": f,
                "trend": exp,
                "source": got,
                "detail": (f"{f} uyuşmuyor: trend={exp} kaynak={got}"),
            })
    exp_src = _norm_by_source(row.get("by_source"))
    got_src = _norm_by_source(source_report.get("by_source"))
    if exp_src != got_src:
        findings.append({
            "kind": "by_source",
            "field": "by_source",
            "trend": exp_src,
            "source": got_src,
            "detail": "by_source uyuşmuyor",
        })
    return findings


def audit(trend, source_reports):
    """Trend'i kaynak raporlarla karşılaştırır.

    source_reports: {run_key: references_online.json} — run_key str.
    Döndürür: {verdict, ok, rows_checked, findings, missing_sources,
               extra_sources, coverage}
    """
    findings = []
    rows_checked = 0
    covered_keys = set()

    for row in trend.get("rows", []):
        key = _row_key(row)
        rows_checked += 1
        src = source_reports.get(key[1])
        if src is None:
            findings.append({
                "kind": "missing_source",
                "row_key": key[1],
                "detail": (f"trend satırının kaynak artifact'ı yok "
                           f"({key[0]}={key[1]}) — sahte/bayat satır"),
            })
            continue
        covered_keys.add(key[1])
        findings += compare_row(row, src)# by_source dağılım denetimi: hathitrust/archive/perseus her run'da var mı?
    # Bu kaynaklar V5s/V5q/V5w sonrası sabit olmalı; eksiklik bayat
    # artifact veya kaynak drift'i anlamına gelir.
    EXPECTED_SOURCES = {"hathitrust", "archive", "perseus"}
    for row in trend.get("rows", []):
        bs = _norm_by_source(row.get("by_source"))
        missing_src = EXPECTED_SOURCES - set(bs.keys())
        if missing_src:
            findings.append({
                "kind": "by_source_missing",
                "row_key": _row_key(row)[1],
                "missing": sorted(missing_src),
                "by_source": bs,
                "detail": (f"by_source'ta beklenen kaynak(lar) yok: "
                           f"{', '.join(sorted(missing_src))} "
                           f"(run_key={_row_key(row)[1]})"),
            })

    # Kapsam: kaynak artifact'ların run_id'leri trendde var mı? (yoksa trend
    # bayat — o run'ın satırı üretilmemiş). run_id'siz kaynak atlanır.
    trend_keys = {_row_key(r)[1] for r in trend.get("rows", [])}
    extra_sources = sorted(
        k for k in source_reports if k not in trend_keys
    )
    coverage = {
        "trend_rows": rows_checked,
        "source_reports": len(source_reports),
        "matched": len(covered_keys),
        "missing_in_trend": extra_sources,
    }

    ok = not findings and not extra_sources
    return {
        "verdict": "PASS" if ok else "FAIL",
        "ok": ok,
        "rows_checked": rows_checked,
        "findings": findings,
        "missing_sources": sorted({f["row_key"] for f in findings
                                   if f["kind"] == "missing_source"}),
        "extra_sources": extra_sources,
        "coverage": coverage,
    }


def check_changelog_order():
    """CHANGELOG listesinin tarih/sıra doğruluğunu denetler.

    Sıralama: en yeni üstte (reverse chron). Her satır bir (date, note)
    tuple'ıdır; date YYYY-MM-DD formatında olmalı, önceki satırla karşılaştırılarak
    geriye doğru sıralı olmalı. Eşit tarihli satırlar kabul edilir (aynı günde
    birden çok not). Bozuk sıralama → [CHLOG-ORDER] findings.
    """
    findings = []
    changelog = getattr(rt, "CHANGELOG", None)
    if not changelog:
        return findings  # changelog boş → kontrol yok

    prev_date = None
    for i, entry in enumerate(changelog):
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            findings.append({
                "kind": "changelog_format",
                "index": i,
                "detail": f"CHANGELOG[{i}]: tuple/list bekleniyor, {type(entry).__name__} alındı",
            })
            continue
        date_str, note = entry[0], entry[1]
        # Tarih formatı kontrolü: YYYY-MM-DD (10 karakter, - ile ayrışmış)
        if (not isinstance(date_str, str) or len(date_str) < 10
                or date_str[4] != "-" or date_str[7] != "-"):
            findings.append({
                "kind": "changelog_date",
                "index": i,
                "detail": f"CHANGELOG[{i}]: tarih geçersiz ({date_str!r})",
            })
            continue
        # Sıra kontrolü: onceki tarih >= mevcut tarih (reverse chron)
        if prev_date is not None and date_str > prev_date:
            findings.append({
                "kind": "changelog_order",
                "index": i,
                "trend": prev_date,
                "source": date_str,
                "detail": (f"CHANGELOG sırası bozuk: [{i-1}]={prev_date} > "
                           f"[{i}]={date_str} (yeni üstte olmalı)"),
            })
        prev_date = date_str
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--trend-json", required=True,
                    help="refs_trend.py çıktısı refs-trend.json yolu")
    ap.add_argument("--max-artifacts", type=int, default=100,
                    help="kaynak olarak işlenecek refs-online artifact sayısı "
                         "(trend üretimiyle aynı pencere; varsayılan 100)")
    ap.add_argument("--json", action="store_true", help="makine-okur JSON")
    args = ap.parse_args(argv)

    try:
        trend = load_trend(args.trend_json)
    except RuntimeError as e:
        print(f"HATA: {e}", file=sys.stderr)
        return 2

    token = os.environ.get("GITHUB_TOKEN", "")
    try:
        artifacts = rt.fetch_refs_online_artifacts(args.repo, token,
                                                   args.max_artifacts)
    except Exception as e:
        print(f"HATA: refs-online artifact listelenemedi — {e}", file=sys.stderr)
        return 2

    # Kaynak raporları topla: {run_id_str: references_online.json}.
    # Aynı run_id'den birden çok artifact varsa (nadir) sonuncusu kullanılır.
    source_reports = {}
    parse_errors = []
    for a in artifacts:
        aid = a["id"]
        rid = (a.get("workflow_run") or {}).get("id")
        if rid is None:
            continue  # run_id'siz kaynak karşılaştırılamaz — atlanır
        try:
            blob = rt.api_get(
                f"/repos/{args.repo}/actions/artifacts/{aid}/zip",
                token, binary=True)
            rep = rt.parse_report(blob)
        except Exception as e:
            parse_errors.append(f"artifact {aid}: {e}")
            continue
        source_reports[str(rid)] = rep

    if parse_errors:
        print(f"  (kaynak parse hataları: {'; '.join(parse_errors)})",
              file=sys.stderr)

    result = audit(trend, source_reports)

    # Changelog sıralama denetimi (kaynak API gerekmez; CHANGELOG sabitinden).
    chlog_findings = check_changelog_order()
    result["findings"] += chlog_findings
    if chlog_findings:
        result["ok"] = False
        result["verdict"] = "FAIL"

    if args.json:
        print(json.dumps({
            "verdict": result["verdict"],
            "repo": args.repo,
            "trend_json": args.trend_json,
            "rows_checked": result["rows_checked"],
            "coverage": result["coverage"],
            "findings": result["findings"],
            "missing_sources": result["missing_sources"],
            "extra_sources": result["extra_sources"],
        }, indent=2, ensure_ascii=False))
    else:
        print(f"refs-trend denetimi — {args.repo}")
        print(f"trend: {args.trend_json}")
        c = result["coverage"]
        print(f"\n── Kapsam ──")
        print(f"  trend satırı: {c['trend_rows']} | kaynak rapor: "
              f"{c['source_reports']} | eşleşen: {c['matched']}")
        if c["missing_in_trend"]:
            print(f"  [FAIL] kaynakta var, trendde YOK: "
                  f"{', '.join(c['missing_in_trend'])}")
        print(f"\n── Satır eşleşmesi ──")
        if not result["findings"]:
            print("  tüm trend satırları kaynakla birebir uyumlu")
        for f in result["findings"]:
            if f["kind"] == "missing_source":
                print(f"  [FAIL] kaynak artifact yok: {f['row_key']} "
                      f"({f['detail']})")
            elif f["kind"] == "count":
                print(f"  [FAIL] {f['detail']}")
            elif f["kind"] == "by_source":
                print(f"  [FAIL] {f['detail']} "
                      f"(trend={f['trend']}, kaynak={f['source']})")
            elif f["kind"] == "by_source_missing":
                print(f"  [FAIL] {f['detail']}")
            elif f["kind"] in ("changelog_order", "changelog_date", "changelog_format"):
                print(f"  [FAIL] {f['detail']}")
        print(f"\nSONUÇ: {result['verdict']} — "
              f"{'trend kaynakla birebir tutarlı' if result['ok'] else 'DRIFT: yukarıdaki [FAIL] satırları'}")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
