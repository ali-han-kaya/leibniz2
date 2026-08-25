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


def check_changelog_rendered():
    """CHANGELOG'daki her satırın changelog_lines() çıktısında görünüp
    görünmediğini doğrular.

    Her CHANGELOG girdisi bir (date, note) tuple'ıdır; not içindeki ilk
    anahtar kelime (örn. 'V5o', 'V5w', 'Kapsam') rendered_satırlarda
    aranır. Bulunamazsa → [CHLOG-RENDERED] finding.
    """
    findings = []
    changelog = getattr(rt, "CHANGELOG", None)
    if not changelog:
        return findings
    rendered = "\n".join(rt.changelog_lines())
    if not rendered:
        findings.append({
            "kind": "changelog_rendered",
            "detail": "changelog_lines() boş çıktı üretti",
        })
        return findings
    # Her CHANGELOG notundaki anahtar kelimeyi rendered'da ara.
    # İlk kelime (tarih değil) genellikle versiyon/kapsam etiketidir.
    _SKIP_PREFIXES = ("2026-", "2025-", "Kapsam:")
    for i, entry in enumerate(changelog):
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        note = entry[1]
        if not isinstance(note, str) or not note.strip():
            continue
        # Notun ilk anlamlı kelimesini bul (tarih/boşluk/çift nokta hariç).
        words = note.split()
        keyword = None
        for w in words:
            if len(w) < 3 or w.startswith(_SKIP_PREFIXES):
                continue
            # Noktalama temizle
            for _p in ('"', "'", ',', ';', ':', '.', '(', ')'):
                w = w.strip(_p)
            keyword = w
            if keyword and len(keyword) >= 3:
                break
        if not keyword:
            continue
        if keyword not in rendered:
            findings.append({
                "kind": "changelog_rendered",
                "index": i,
                "keyword": keyword,
                "note": note[:80],
                "detail": (f"CHANGELOG[{i}] '{keyword}' rendered çıktıda "
                           f"bulunamadı ({note[:50]}...)"),
            })
    return findings


def check_refs_trend_summary(trend_json_path):
    """refs-trend.md özet bölümünü denetler.

    Kontroller:
      1) 'Kapsam geçiş dipnotu' başlığı mevcut mu?
      2) Dipnotta V5n→V5q/V5t/V5w geçiş zinciri referansları var mı?
      3) '56/56' ve 'yerel doğrulama' ifadesi var mı?
      4) Dipnot, Özet bölümünden sonra mı geliyor (sıra)?
      5) toplam_satir degisimi (first→last row total_online) dipnotla eslesiyor mu?
    """
    findings = []
    # .md dosyasını bul: trend_json_path refs-trend/refs-trend.json ise
    # refs-trend/refs-trend.md kardeşidir.
    p = pathlib.Path(trend_json_path)
    md_path = p.parent / "refs-trend.md"
    if not md_path.is_file():
        findings.append({
            "kind": "summary_md_missing",
            "detail": f"refs-trend.md bulunamadı ({md_path})",
        })
        return findings

    md_text = md_path.read_text(encoding="utf-8")
    md_lines = md_text.splitlines()

    # 1) 'Kapsam geçiş dipnotu' başlığı var mı?
    dipnot_idx = None
    for i, line in enumerate(md_lines):
        if "Kapsam geçiş dipnotu" in line:
            dipnot_idx = i
            break
    if dipnot_idx is None:
        findings.append({
            "kind": "summary_footnote_missing",
            "detail": "refs-trend.md'de 'Kapsam geçiş dipnotu' bulunamadı",
        })
        return findings  # diğer kontroller dipnota bağlı

    # Dipnot bloğu: dipnot_idx'den itibaren boş satıra kadar
    footnote_block = []
    for line in md_lines[dipnot_idx:dipnot_idx + 15]:
        footnote_block.append(line)
        if line.strip() == "" and len(footnote_block) > 1:
            break
    footnote_text = " ".join(footnote_block)

    # 2) V5 geçiş referansları
    expected_versions = ["V5n", "V5q", "V5t", "V5w"]
    for v in expected_versions:
        if v not in footnote_text:
            findings.append({
                "kind": "summary_footnote_version",
                "version": v,
                "detail": f"Dipnotta {v} referansı eksik",
            })

    # 3) '56/56' ve 'yerel doğrulama'
    if "56/56" not in footnote_text:
        findings.append({
            "kind": "summary_footnote_56",
            "detail": "Dipnotta '56/56' ifadesi eksik",
        })
    if "yerel doğrulama" not in footnote_text and "yerel dogrulama" not in footnote_text:
        findings.append({
            "kind": "summary_footnote_local",
            "detail": "Dipnotta 'yerel doğrulama' ifadesi eksik",
        })

    # 4) Dipnot Özet bölümünden sonra mı? (Özet üstte, dipnot altta olmalı)
    ozet_idx = None
    for i, line in enumerate(md_lines):
        if line.strip() == "## Özet":
            ozet_idx = i
            break
    if ozet_idx is not None and dipnot_idx < ozet_idx:
        findings.append({
            "kind": "summary_footnote_order",
            "detail": (f"Dipnot (satır {dipnot_idx+1}) Özet bölümünden "
                       f"önce geliyor ({ozet_idx+1}) — dipnot Özet之后 olmalı"),
        })

    # 5) Toplam satır degisimi dipnotla eslesiyor mu?
    #    trend.json'dan ilk/son row'un total_online'ini oku.
    try:
        with open(p, encoding="utf-8") as f:
            trend_data = json.load(f)
        rows = trend_data.get("rows", [])
        if len(rows) >= 2:
            first_t = rows[0].get("total_online", 0)
            last_t = rows[-1].get("total_online", 0)
            # Dipnotta "54/49 → 56/26 → 61/61" formatında geçiş olmalı
            # İlk ve son değer dipnotla eşleşmeli
            if first_t == last_t and "→" in footnote_text:
                findings.append({
                    "kind": "summary_footnote_stale",
                    "detail": (f"Dipnotta geçiş var ama trend'de ilk/son "
                               f"total_online aynı ({first_t}) — dipnot bayat"),
                })
    except Exception:
        pass  # trend json okunamazsa atla (zaten audit() kontrol eder)

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
    ap.add_argument("--offline", action="store_true",
                    help="Kaynak artifact'ları GitHub API'den değil, "
                         "--artifacts-dir altından oku (çevrimdışı tekrarlanabilir)")
    ap.add_argument("--artifacts-dir", default=None,
                    help="--offline modunda kaynak dizin (alt dizinlerinde "
                         "refs-online/ klasörü beklenir; varsayılan: trend-json "
                         "yanındaki all_artifacts)")
    ap.add_argument("--json", action="store_true", help="makine-okur JSON")
    args = ap.parse_args(argv)

    try:
        trend = load_trend(args.trend_json)
    except RuntimeError as e:
        print(f"HATA: {e}", file=sys.stderr)
        return 2

    # Kaynak raporları topla: {run_id_str: references_online.json}.
    source_reports = {}
    parse_errors = []

    if args.offline:
        # ── OFFLINE mod: yerel dizinden refs-online zip'lerini oku ────────
        # Beklenen yapı: artifacts_dir/refs-online/refs-online-{id}.zip
        # veya artifacts_dir/altında tek-level zip dosyaları.
        art_dir = pathlib.Path(args.artifacts_dir)
        if not art_dir.is_dir():
            # varsayılan: trend-json'un iki üstündeki all_artifacts/
            art_dir = (pathlib.Path(args.trend_json).resolve().parent
                       .parent.parent / "all_artifacts")
        if not art_dir.is_dir():
            print(f"HATA: --offline artifacts dizini bulunamadı ({art_dir})",
                  file=sys.stderr)
            return 2

        # refs-online dizinini veya zip dosyalarını ara
        ref_dirs = [art_dir / "refs-online"]
        if not ref_dirs[0].is_dir():
            ref_dirs = []
            # root level zip'leri de dene
            for zf in art_dir.rglob("*.zip"):
                ref_dirs.append(zf)

        import re as _re
        def _extract_run_id(zf):
            """Zip dosya adından run_id çıkar (refs-online-{id}.zip)."""
            m = _re.search(r"(\d+)\.zip$", zf.name)
            return m.group(1) if m else None

        def _load_zip(zf):
            """Zip'ten report + run_id döndür."""
            blob = zf.read_bytes()
            rep = rt.parse_report(blob)
            rid = _extract_run_id(zf)
            if rid is not None:
                return rid, rep
            return None, rep

        if ref_dirs and ref_dirs[0].is_dir():
            # refs-online/ altındaki zip dosyaları
            for zf in sorted(ref_dirs[0].glob("*.zip")):
                try:
                    rid, rep = _load_zip(zf)
                    if rid is not None:
                        source_reports[rid] = rep
                except Exception as e:
                    parse_errors.append(f"{zf.name}: {e}")
        else:
            # Root-level zip'leri dene
            for zf in sorted(art_dir.glob("*.zip")):
                try:
                    rid, rep = _load_zip(zf)
                    if rid is not None:
                        source_reports[rid] = rep
                except Exception as e:
                    parse_errors.append(f"{zf.name}: {e}")

        print(f"  [offline] {len(source_reports)} kaynak rapor yüklendi "
              f"({art_dir})", file=sys.stderr)
    else:
        # ── ONLINE mod: GitHub API'den indir ─────────────────────────────
        try:
            artifacts = rt.fetch_refs_online_artifacts(args.repo, os.environ.get("GITHUB_TOKEN", ""),
                                                       args.max_artifacts)
        except Exception as e:
            print(f"HATA: refs-online artifact listelenemedi — {e}", file=sys.stderr)
            return 2

        for a in artifacts:
            aid = a["id"]
            rid = (a.get("workflow_run") or {}).get("id")
            if rid is None:
                continue
            try:
                blob = rt.api_get(
                    f"/repos/{args.repo}/actions/artifacts/{aid}/zip",
                    os.environ.get("GITHUB_TOKEN", ""), binary=True)
                rep = rt.parse_report(blob)
            except Exception as e:
                parse_errors.append(f"artifact {aid}: {e}")
                continue
            source_reports[str(rid)] = rep

    if parse_errors:
        print(f"  (kaynak parse hataları: {'; '.join(parse_errors)})",
              file=sys.stderr)

    result = audit(trend, source_reports)

    # Changelog sıralama + render denetimi (kaynak API gerekmez).
    chlog_findings = check_changelog_order()
    chlog_rendered = check_changelog_rendered()
    all_chlog = chlog_findings + chlog_rendered
    result["findings"] += all_chlog
    if all_chlog:
        result["ok"] = False
        result["verdict"] = "FAIL"

    # refs-trend.md özet dipnot denetimi (56/56 yerel doğrulama notu).
    summary_findings = check_refs_trend_summary(args.trend_json)
    result["findings"] += summary_findings
    if summary_findings:
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
            elif f["kind"] in ("changelog_order", "changelog_date",
                               "changelog_format", "changelog_rendered"):
                print(f"  [FAIL] {f['detail']}")
            elif f["kind"].startswith("summary_"):
                print(f"  [FAIL] {f['detail']}")
        print(f"\nSONUÇ: {result['verdict']} — "
              f"{'trend kaynakla birebir tutarlı' if result['ok'] else 'DRIFT: yukarıdaki [FAIL] satırları'}")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
