#!/usr/bin/env python3
"""record_determinism_trend.py — TeX motor determinizmi trend kaydı.

texlive_determinism_test.sh deneyinin kanıt raporunu okur, ölçümü doğrular
ve determinism_trend.jsonl'a tek satır ekler. Amaç: tectonic ve TeXLive
kanonik hash'lerinin **oturumlar arası** kararlılığını haftalık CI + yerel
koşumlarla izlemek; sapma ilk haftada görünür.

Veri sözleşmesi (jsonl — satır başına ölçüm; yalnız eklenir, asla yeniden
yazılmaz; güncellik `source_mtime` + `source_sha256` ile izlenir):
  {"date": "YYYY-MM-DD", "source_mtime": <int>, "tectonic_bin": "...",
   "texlive_bin": "...", "tectonic_canonical_sha256": "<64 hex>",
   "texlive_canonical_sha256": "<64 hex>", "source_sha256": "<64 hex>",
   "sde": <int>, "platform": "darwin|linux", "gate": "PASS"}

--check değişmezi (fail-closed trend kapısı; pre-commit/CI):
  1. GENÇLİK — son kayıt 7 günden eskiyse FAIL (haftalık cron + push
     tetiklemesi koşum frekansını taşır; koşum yoksa kanıt bayatlar).
  2. UZLAŞMA — son kayıttan bu yana kaynak .tex değişmediyse (aynı
     source_sha256) kanonik hash'ler DEĞİŞMEMELİ. Kaynak değiştiyse hash
     serbest (yeni bazeline ait). İhlal = motor/determinizm sapması.
  3. PLATFORM KAPSAMI — cutoff sonrası en az bir darwin + bir linux kaydı:
     aynı kaynak + motor sürümü + SDE ile iki platformun kanonik hash'i
     birebir eşit olmalı; eşitsizlik ya CI/lokal motor sürüm sapmasıdır ya
     da determinizm kırığıdır — ikisi de fail-closed inceleme ister.
"""
import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CIKTI = os.path.join(ROOT, "_calisma", "CIKTI")
REPORT = os.path.join(ROOT, "docs", "ci_simulate", "texlive_determinism",
                      "texlive_determinism_report.txt")
TREND = os.path.join(ROOT, "docs", "determinism_trend",
                     "determinism_trend.jsonl")  # versiyonlu (ci_simulate ignore'da)

# Platform-kapsam değişmezi bu tarihten başlar (deneyin ilk canlı ölçümü).
PLATFORM_SCOPE_CUTOFF = "2026-09-17"

# Uzlaşma penceresi: son N kayıttaki aynı-kaynak-hash eşleşmeleri denetlenir.
CONCORDANCE_WINDOW = 5


def _read_report(path=REPORT):
    """Deney raporunu `key=value` satırlarından okur; dosya yoksa None."""
    if not os.path.exists(path):
        return None
    fields = {}
    for raw in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"^([a-z_0-9]+)=(.*)$", raw.rstrip("\n"))
        if m:
            fields[m.group(1)] = m.group(2)
    return fields


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_from_report(report):
    """Raporun `source=` değerini repo-kök mutlak yoluna normalize eder."""
    src = report.get("source", "")
    if os.path.isabs(src) and os.path.exists(src):
        return src
    candidate = os.path.join(ROOT, src)
    return candidate if os.path.exists(candidate) else (src or candidate)


def _extract_report_data(report):
    """Rapor alanlarından ölçüm değerlerini çıkarır; bozuk raporda ValueError."""
    required = ("tectonic_sha256", "texlive_canonical_run1_sha256",
                "texlive_canonical_run2_sha256", "verdict")
    for key in required:
        if key not in report:
            raise ValueError(f"rapor alanı eksik: {key}")
    if report["verdict"] != "PASS":
        raise ValueError(f"deney verdict PASS değil: {report.get('verdict')!r}")
    c1 = report["texlive_canonical_run1_sha256"]
    c2 = report["texlive_canonical_run2_sha256"]
    if c1 != c2:
        raise ValueError(f"rapor içi kanonik koşumlar zıt: {c1} != {c2}")
    for val in (report["tectonic_sha256"], c1):
        if not re.fullmatch(r"[0-9a-f]{64}", val):
            raise ValueError(f"hash 64 hex değil: {val!r}")
    return {
        "tectonic_canonical_sha256": report["tectonic_sha256"],
        "texlive_canonical_sha256": c1,
        "tectonic_bin": report.get("tectonic", "unknown"),
        "texlive_bin": report.get("pdflatex", "unknown"),
    }


def _append(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def _records(path=TREND):
    if not os.path.exists(path):
        return []
    out = []
    for i, raw in enumerate(open(path, encoding="utf-8"), 1):
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError as e:
            raise ValueError(f"satır {i}: bozuk JSONL: {e}") from e
    return out


def _is_current_week(date_str, now=None):
    d = datetime.date.fromisoformat(date_str)
    ref = now or datetime.date.today()
    return (ref - d).days < 7


def trend_invariant(records, now=None):
    """Trend değişmezi: gençlik + kaynak-uzlaşma + platform kapsamı.

    Döndürür: "OK" ya da noktalı virgülle birleşik ihlal açıklamaları.
    """
    if not records:
        return "trend boş — ilk ölçüm gerekli (--update ile deney koşumu sonrası)"
    latest = records[-1]
    problems = []

    # 1) Gençlik: haftalık koşum frekansı.
    if not _is_current_week(latest["date"], now):
        problems.append(
            f"son ölçüm bayat ({latest['date']}) — haftalık koşum atlanmış")

    # 2) Kaynak-uzlaşma: aynı source_sha256 + AYNI PLATFORM → aynı kanonik
    #    hash'ler (platform-scoped: CI Debian TeXLive hash'i ile lokal
    #    Homebrew hash'i eşit mi — ölçmeden varsayılmaz; çapraz eşitlik
    #    aşağıda yalnız KARŞILAŞTIRILIR, ihlal varsayılmaz).
    for prev in records[-(CONCORDANCE_WINDOW + 1):-1]:
        if (prev.get("source_sha256") == latest.get("source_sha256")
                and prev.get("platform") == latest.get("platform")):
            for key in ("tectonic_canonical_sha256",
                        "texlive_canonical_sha256"):
                if prev.get(key) != latest.get(key):
                    problems.append(
                        f"{key} aynı kaynakta değişti: "
                        f"{prev.get('date')} {str(prev.get(key))[:12]}… → "
                        f"{latest.get('date')} {str(latest.get(key))[:12]}…")

    # 3) Platform kapsamı: cutoff sonrası her iki platformdan kayıt.
    post = [r for r in records
            if str(r.get("date", "")) >= PLATFORM_SCOPE_CUTOFF]
    plats = {r.get("platform") for r in post}
    missing = {"darwin", "linux"} - plats
    if missing:
        problems.append(
            f"platform kapsamı eksik (cutoff {PLATFORM_SCOPE_CUTOFF} "
            f"sonrası): {'/'.join(sorted(missing))} kaydı yok")

    # 4) Çapraz-platform karşılaştırma BURADA DEĞİL — ihlal sayılmaz
    #    (farklı paket setleri farklı hash üretebilir; R3: ölçmeden
    #    varsayma). Bilgilendirici not _cross_platform_note ile ayrı yazılır.

    return "; ".join(problems) if problems else "OK"


def _cross_platform_note(records):
    """Bilgilendirici çapraz-platform gözlemi (fail DEĞİL); None veya metin."""
    post = [r for r in records
            if str(r.get("date", "")) >= PLATFORM_SCOPE_CUTOFF]
    latest_by_platform = {}
    for r in post:
        latest_by_platform[r.get("platform")] = r
    if not {"darwin", "linux"} <= set(latest_by_platform):
        return None
    d = latest_by_platform["darwin"]
    l = latest_by_platform["linux"]
    same_src = d.get("source_sha256") == l.get("source_sha256")
    same_sha = (d.get("tectonic_canonical_sha256")
                == l.get("tectonic_canonical_sha256"))
    if same_src and same_sha:
        return ("not: darwin/linux tectonic kanonik hash'leri birebir eşit "
                "(aynı kaynak) — çapraz-platform determinizm güçlü kanıt")
    if same_src:
        return ("not: darwin/linux tectonic hash'leri farklı (aynı kaynak) — "
                "beklenen: motor/paket-seti farkı; trendde izlenir")
    return None


def _build_record(report, source):
    data = _extract_report_data(report)
    return {
        "date": datetime.date.today().isoformat(),
        "source_mtime": int(os.stat(source).st_mtime),
        "source_sha256": _sha256_of(source),
        "sde": int(report.get("source_date_epoch", "0") or 0),
        "platform": platform.system().lower(),
        "gate": report["verdict"],
        **data,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Determinizm trend kaydı: --update ölçüm ekler, "
                    "--check trend değişmezlerini doğrular")
    parser.add_argument("--update", action="store_true",
                        help="deney raporundan ölçüm oku ve jsonl'a ekle")
    parser.add_argument("--check", action="store_true",
                        help="trend değişmezlerini doğrula (fail-closed)")
    args = parser.parse_args(argv)
    if not (args.update or args.check):
        parser.error("bir mod gerekli: --update veya --check")

    if args.update:
        report = _read_report()
        if report is None:
            print(f"FAIL: deney raporu yok: {REPORT} — önce deneyi koş "
                  f"(texlive_determinism_hook.sh)", file=sys.stderr)
            return 1
        # Bayat-kanıt koruması: eski rapor bugünün tarihiyle kaydedilirse
        # trendin tazelik iddiası kendini bozar; ölçüm yalnız taze deneyden.
        age_hours = (time.time() - os.stat(REPORT).st_mtime) / 3600.0
        if age_hours > 48.0:
            print(f"FAIL: deney raporu bayat ({age_hours:.0f} saat) — "
                  "ölçüm kaydedilemez; önce deneyi koş", file=sys.stderr)
            return 1
        try:
            source = _source_from_report(report)
            if not os.path.exists(source):
                print(f"FAIL: kaynak .tex bulunamadı: {source}",
                      file=sys.stderr)
                return 1
            record = _build_record(report, source)
        except ValueError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1
        _append(TREND, record)
        print(f"OK: ölçüm eklendi: {TREND}")
        print(f"  date={record['date']} platform={record['platform']} "
              f"tectonic={record['tectonic_canonical_sha256'][:12]}… "
              f"texlive={record['texlive_canonical_sha256'][:12]}…")
        return 0

    # --check modu (fail-closed trend kapısı)
    try:
        records = _records()
        verdict = trend_invariant(records)
    except ValueError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    if verdict == "OK":
        note = _cross_platform_note(records)
        print(f"determinism-trend: OK ({len(records)} ölçüm, "
              f"son {records[-1]['date']}, "
              f"platform={records[-1].get('platform')})")
        if note:
            print(note)
        return 0
    print(f"FAIL: trend değişmezi ihlali: {verdict}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
