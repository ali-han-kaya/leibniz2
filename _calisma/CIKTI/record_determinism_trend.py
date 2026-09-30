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
   "sde": <int>, "platform": "darwin|linux", "gate": "PASS",
   "passes": <int>}

`passes` alanı (Faz 4 re-baseline'ı, 2026-09-30): o ölçümün kaç pdflatex
geçişiyle alındığıdır. Deney default'u artık 3'tür (tek geçişte çapraz
referans/bibliyografya çözülmez; hizalama iddiası kurulamaz). `passes`
alanı olmayan eski satırlar 1 kabul edilir (o dönemin default'u). Farklı
geçiş modları **karşılaştırılamaz**: 1-geçiş ve 3-geçiş kanonik hash'leri
tanım gereği farklıdır (aynı kaynakta ölçülmüş olsa bile).

--check değişmezi (fail-closed trend kapısı; pre-commit/CI):
  1. GENÇLİK — son kayıt 7 günden eskiyse FAIL (haftalık cron + push
     tetiklemesi koşum frekansını taşır; koşum yoksa kanıt bayatlar).
  2. UZLAŞMA (platform- VE mod-kapsamlı) — son kayıttan bu yana kaynak .tex
     değişmediyse (aynı source_sha256), platform VE `passes` aynıysa kanonik
     hash'ler DEĞİŞMEMELİ. Kaynak, platform ya da geçiş modu değiştiyse hash
     serbest (yeni bazeline ait; mod değişimi bilinçli re-baseline'dır ve
     nota yazılır). İhlal = motor/determinizm sapması.
  3. PLATFORM KAPSAMI — cutoff sonrası en az bir darwin + bir linux kaydı
     bulunmalı (karşılaştırılabilir bağlam garantisi). Çapraz-platform
     eşitliği İHLAL SAYILMAZ: farklı paket setleri (Homebrew TeX Live ↔
     Debian texlive+cm-super) farklı kanonik hash üretebilir; yalnız
     `_cross_platform_note` ile bilgilendirici olarak raporlanır.
     Gerekçe ve ölçüm: docs/PDF_DETERMINISM_EXPLAINED.md §6.
"""
import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import sys

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


def _read_report(path=None):
    """Deney raporunu `key=value` satırlarından okur; dosya yoksa None.

    Varsayılan `REPORT`'u IMPORT anında bağlamak yanlıştı: `main()` ve testler
    `rdt.REPORT`'u geçici bir dosyaya yönlendirir, ama `def f(path=REPORT)`
    o anki bağı yakalar — yönlendirme sessizce yok sayılır ve `--update` var
    olmayan GERÇEK rapora düşüp rc=1 verir (yerelde rapor mevcut olduğu için
    yeşil, CI'da rapor yok olduğu için kırmızı). Default None → çağrı anında
    modül seviyesine bakılır.
    """
    if path is None:
        path = REPORT  # noqa
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


def _report_canonical(report):
    """Raporun TeXLive kanonik koşum çiftini döndürür (fail-closed).

    Hızlı yol (`residual=none`: iki koşumun ham PDF'i baştan birebir aynı)
    kanonik alanları YAZMAZ — betik eşitlikte erken çıkar. O durumda ham
    hash kanonik hash'in kendisidir; fallback yalnız bu kanıtla yapılır
    (`gen_id_residual_acceptance.py` ile AYNI kural; ham ≠ kanonik olan bir
    hiçbir durum sessizce kabul edilmez).
    """
    c1 = report.get("texlive_canonical_run1_sha256")
    c2 = report.get("texlive_canonical_run2_sha256")
    if c1 is None and c2 is None:
        r1 = report.get("texlive_run1_sha256")
        r2 = report.get("texlive_run2_sha256")
        residual = str(report.get("residual", ""))
        if r1 and r1 == r2 and residual.startswith("none"):
            return r1, r1
        raise ValueError(
            "kanonik alanlar yok ve residual=none değil "
            f"(residual={residual!r}) — ölçüm kanıtlanamadı")
    if c1 is None or c2 is None:
        raise ValueError("kanonik alanların yalnız biri var — rapor tutarsız")
    return c1, c2


def _report_passes(report):
    """Raporun geçiş modunu döndürür; çok-geçişte hizalama kanıtı şart."""
    raw = report.get("passes", "1")
    try:
        passes = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"passes sayı değil: {raw!r}") from None
    if passes < 1:
        raise ValueError(f"passes pozitif olmalı: {passes}")
    if passes > 1:
        for key in ("texlive_run1_rerun_left", "texlive_run2_rerun_left"):
            val = report.get(key)
            if val is None:
                raise ValueError(f"çok-geçiş raporu {key} taşımalı")
            if str(val) != "0":
                raise ValueError(
                    f"çok-geçişte {key}={val!r} — K6 hizalama iddiası "
                    f"üretilemez, ölçüm kaydedilmez")
    return passes


def _extract_report_data(report):
    """Rapor alanlarından ölçüm değerlerini çıkarır; bozuk raporda ValueError."""
    for key in ("tectonic_sha256", "verdict"):
        if key not in report:
            raise ValueError(f"rapor alanı eksik: {key}")
    if report["verdict"] != "PASS":
        raise ValueError(f"deney verdict PASS değil: {report.get('verdict')!r}")
    c1, c2 = _report_canonical(report)
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
        "passes": _report_passes(report),
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


def _passes(record):
    """Kaydın geçiş modu; `passes` alanı olmayan eski satırlar 1'dir."""
    try:
        return int(record.get("passes") or 1)
    except (TypeError, ValueError):
        return 1


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

    # 2) Kaynak-uzlaşma: aynı source_sha256 + AYNI PLATFORM + AYNI GEÇİŞ MODU
    #    → aynı kanonik hash'ler (platform-scoped: CI Debian TeXLive hash'i ile
    #    lokal Homebrew hash'i eşit mi — ölçmeden varsayılmaz; çapraz eşitlik
    #    aşağıda yalnız KARŞILAŞTIRILIR, ihlal varsayılmaz). Mod-kapsamlı:
    #    1-geçiş ve 3-geçiş kanonikleri tanım gereği farklıdır (çapraz
    #    referans/bibliyografya çözümü) — Faz 4 re-baseline'ı sahte ihlal
    #    üretmez, ama aynı mod içindeki sapma yine yakalanır.
    for prev in records[-(CONCORDANCE_WINDOW + 1):-1]:
        if (prev.get("source_sha256") == latest.get("source_sha256")
                and prev.get("platform") == latest.get("platform")
                and _passes(prev) == _passes(latest)):
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


def _mode_note(records):
    """Bilgilendirici geçiş-modu gözlemi (fail DEĞİL); None veya metin.

    Son kaydın `passes` değeri kendisinden önceki kayıttan farklıysa bu
    bilinçli bir re-baseline'dır: aynı-mod karşılaştırması bu satırdan
    başlar (eski satırlarla kıyaslanmaz).
    """
    if len(records) < 2:
        return None
    prev, latest = records[-2], records[-1]
    if _passes(prev) == _passes(latest):
        return None
    return (f"not: geçiş modu değişti {_passes(prev)} → {_passes(latest)} "
            f"({latest.get('date')}) — bilinçli re-baseline; uzlaşma "
            f"karşılaştırması aynı mod içinde yapılır")


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
        report = _read_report(REPORT)
        if report is None:
            print(f"FAIL: deney raporu yok: {REPORT} — önce deneyi koş "
                  f"(texlive_determinism_hook.sh)", file=sys.stderr)
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
              f"passes={record.get('passes', 1)} "
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
              f"platform={records[-1].get('platform')}, "
              f"passes={_passes(records[-1])})")
        if note:
            print(note)
        mode_note = _mode_note(records)
        if mode_note:
            print(mode_note)
        return 0
    print(f"FAIL: trend değişmezi ihlali: {verdict}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
