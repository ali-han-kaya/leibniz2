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

AİLELER (2026-10-08): iki bağımsız kanonik-hash serisi aynı dosyada yaşar:
  * manuscript (varsayılan; `family` alanı yoksa bu) — el yazması:
    tectonic + TeXLive çifti (texlive_determinism_test.sh raporu).
  * canvas — Incidental Proof levha kitabı: tectonic tek bacağı
    (canvas_determinism_test.sh raporu). Satır şekli aynıdır + "family":
    "canvas"; kanonik hash `tectonic_canonical_sha256` alanındadır ve
    KİTAP (apex) kanonik hash'idir (levhaları gömer → aileyi kapsar).
  `family` alanı `date`'ten SONRA gelir (anahtar sıralı yazım + sözlüksel
  birleştirme sırası = kronolojik; trend_record_merge.py buna dayanır).

--check değişmezi (fail-closed trend kapısı; CI + testler) — AİLE BAŞINA:
  1. GENÇLİK — ailenin son kaydı 7 günden eskiyse FAIL (haftalık cron + push
     tetiklemesi koşum frekansını taşır; koşum yoksa kanıt bayatlar).
     Aile kapsamı ŞARTTIR: taze bir canvas kaydı, bayat manuscript serisini
     yeşile boyayamaz (fail-open regresyon testi bekçidir).
  2. UZLAŞMA — aynı platformda son kayıttan bu yana kaynak .tex değişmediyse
     (aynı source_sha256) o ailenin kanonik hash'leri DEĞİŞMEMELİ. Kaynak
     değiştiyse hash serbest (yeni bazeline ait). İhlal = motor/determinizm
     sapması. Denetlenen alanlar satırdaki `*_canonical_sha256` alanlarıdır
     (yeni bir alan eklendiğinde değişmez onu OTOMATİK kapsar).
  3. PLATFORM KAPSAMI — aile başına, cutoff sonrası en az bir darwin + bir
     linux kaydı: aynı kaynak + motor sürümü + SDE ile iki platformun kanonik
     hash'i birebir eşit olmalı; eşitsizlik ya CI/lokal motor sürüm sapmasıdır
     ya da determinizm kırığıdır — ikisi de fail-closed inceleme ister.
  4. VARLIK — FAMILIES'teki HER ailenin trendde en az bir kaydı olmalı:
     canvas satırı hiç yazılmamışsa yeşil manuscript tek başına yeter sayılmaz
     (sessiz aile kaybı = fail-closed kırmızı).
  5. ŞEMA — dosyadaki `family` değerleri FAMILIES içinde olmalı; yazım hatası
     hiç denetlenmeyen bir seri yaratır → kırmızı.

İhlaller `[aile] ` önekiyle raporlanır: iki seri tek jsonl'da yaşadığı için
taze bir canvas kaydı BAYAT manuscript serisini yeşile boyayamaz (ve tersi).
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

# Aileler: aynı jsonl, iki bağımsız seri. `family` alanı bulunmayan
# kayıtlar manuscript'tır (2026-10-08 öncesi kayıtlar alanı taşımaz —
# şema genişlemesi geriye dönük okunur).
FAMILY_MANUSCRIPT = "manuscript"
FAMILY_CANVAS = "canvas"
FAMILIES = (FAMILY_MANUSCRIPT, FAMILY_CANVAS)

# Canvas (Incidental Proof) kanıt raporu — üretici:
# _calisma/CIKTI/canvas_determinism_test.sh (docs/Makefile.texlive
# `plate-book-check` her kaynak için çağırır). Trende giren satır KİTAP
# (apex) raporundan gelir: kitap beş levhayı gömer, yani kanonik hash'i
# aileyi transitif kapsar.
CANVAS_APEX_STEM = "incidental_proof_book"
CANVAS_REPORT = os.path.join(ROOT, "docs", "ci_simulate", "canvas_determinism",
                             CANVAS_APEX_STEM + ".determinism.txt")
CANVAS_APEX_TEX = os.path.join(CIKTI, "canvas", CANVAS_APEX_STEM + ".tex")

# Canvas SDE sabiti — docs/Makefile.texlive `PLATE_BOOK_EPOCH` ile
# canvas_determinism_test.sh varsayımı AYNI değer; test bunu üç dosyayı okuyup
# karşılaştırarak kilitler (tek gerçeklik diller arası türülemez). Neden sabit:
# kaynaklar gömülü /CreationDate taşır; epoch el yazmasınınkine (1786924800)
# kayarsa levha PDF'leri sessizce yeniden damgalanır ve commit'li baytlar
# bir daha üretilemez — Makefile'ın adlandırdığı risk, kayıt anında kapatılır.
CANVAS_SDE = 1700000000

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


def _extract_canvas_data(report):
    """Canvas raporundan ölçüm değerlerini çıkarır; bozuk raporda ValueError.

    Fail-closed denetimler: verdict PASS, iki bağımsız koşumun KANONİK hash'i
    eşit, hash'ler 64-hex, `hash_form` kanonik (/ID nötr) ve `id_form` bunun
    gerçekten uygulandığını gösterir. Böylece ham bir hash "kanonik" diye
    trende giremez.
    """
    required = ("tectonic_run1_sha256", "tectonic_run2_sha256", "verdict",
                "hash_form", "id_form")
    for key in required:
        if key not in report:
            raise ValueError(f"canvas raporu alanı eksik: {key}")
    if report["verdict"] != "PASS":
        raise ValueError(f"canvas deney verdict PASS değil: {report.get('verdict')!r}")
    if not report["hash_form"].startswith("canonical"):
        raise ValueError(f"canvas raporu kanonik hash taşımıyor: "
                         f"hash_form={report['hash_form']!r}")
    if report["id_form"] != "id_found":
        raise ValueError(f"canvas raporunda /ID nötrlenmemiş "
                         f"(id_form={report['id_form']!r}) — kanonik iddia kanıtsız")
    if "source_date_epoch" not in report:
        raise ValueError("canvas raporu alanı eksik: source_date_epoch")
    try:
        sde = int(str(report["source_date_epoch"]).strip() or "0")
    except ValueError as e:
        raise ValueError("canvas raporu source_date_epoch sayı değil: %r"
                         % report["source_date_epoch"]) from e
    if sde != CANVAS_SDE:
        raise ValueError(f"canvas SDE sabiti ihlali: {sde} != {CANVAS_SDE} — "
                         f"yanlış SOURCE_DATE_EPOCH ile üretilen hash trende girmez")
    c1 = report["tectonic_run1_sha256"]
    c2 = report["tectonic_run2_sha256"]
    if c1 != c2:
        raise ValueError(f"canvas raporu içi kanonik koşumlar zıt: {c1} != {c2}")
    for val in (c1,):
        if not re.fullmatch(r"[0-9a-f]{64}", val):
            raise ValueError(f"hash 64 hex değil: {val!r}")
    return {
        "tectonic_canonical_sha256": c1,
        "tectonic_bin": report.get("tectonic", "unknown"),
    }


def family_of(record):
    """Kaydın ailesi; alan yoksa manuscript (geriye dönük okuma)."""
    fam = record.get("family")
    return fam if isinstance(fam, str) and fam else FAMILY_MANUSCRIPT


def hash_keys(record):
    """Kayıttaki kanonik-hash alanları (dinamik: yeni alan otomatik kapsanır)."""
    return tuple(sorted(k for k in record if k.endswith("_canonical_sha256")))


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
    """Trend değişmezi: AİLE BAŞINA (manuscript ve canvas bağımsız seriler).

    Döndürür: "OK" ya da noktalı virgülle birleşik ihlal açıklamaları; her
    ihlal `[aile] ` öneki taşır. Aile ayrımı ŞARTTIR: taze bir canvas kaydı,
    bayat manuscript serisini yeşile boyayamaz (ve tersi) — fail-open
    regresyonu test_record_determinism_trend.py bekçidir.

    4. VARLIK + 5. ŞEMA da burada: FAMILIES'te tanımlı olmayan bir aile
    serisi denetimsiz kalır, tanımlı bir ailense hiç kayıt taşıyamaz —
    ikisi de fail-closed kırmızıdır.
    """
    if not records:
        return "trend boş — ilk ölçüm gerekli (--update ile deney koşumu sonrası)"
    problems = []
    for unknown in sorted({family_of(r) for r in records} - set(FAMILIES)):
        problems.append(
            f"[{unknown}] şema-dışı aile — FAMILIES eşlemesi bu değeri "
            f"içermiyor (seri denetlenmiyor)")
    for family in FAMILIES:
        fam = [r for r in records if family_of(r) == family]
        if not fam:
            problems.append(
                f"[{family}] kayıt yok — seri hiç başlamamış "
                f"(--update --family {family})")
            continue
        problems.extend(f"[{family}] {p}"
                        for p in _family_invariant(fam, now))
    return "; ".join(problems) if problems else "OK"


def _family_invariant(fam, now=None):
    """Tek ailenin üç değişmezi: gençlik + kaynak-uzlaşma + platform kapsamı.

    `fam` trend dosyasındaki sıra korunmuş tek ailenin kayıtlarıdır (son eleman
    ailenin son ölçümüdür).
    """
    problems = []
    latest = fam[-1]

    # 1) Gençlik: haftalık koşum frekansı.
    if not _is_current_week(latest["date"], now):
        problems.append(
            f"son ölçüm bayat ({latest['date']}) — haftalık koşum atlanmış")

    # 2) Kaynak-uzlaşma: aynı source_sha256 + AYNI PLATFORM → aynı kanonik
    #    hash'ler (platform-scoped: CI Debian TeXLive hash'i ile lokal
    #    Homebrew hash'i eşit mi — ölçmeden varsayılmaz; çapraz eşitlik
    #    yalnız not edilir, ihlal sayılmaz). Denetlenen alanlar iki kaydın
    #    ORTAK `*_canonical_sha256` alanlarıdır: yeni bir alan eklendiğinde
    #    değişmez onu otomatik kapsar, ailenin taşımadığı alanı (canvas'ta
    #    texlive bacağı yok) kırmızıya çevirmez.
    for prev in fam[-(CONCORDANCE_WINDOW + 1):-1]:
        if (prev.get("source_sha256") == latest.get("source_sha256")
                and prev.get("platform") == latest.get("platform")):
            for key in sorted(set(hash_keys(prev)) & set(hash_keys(latest))):
                if prev.get(key) != latest.get(key):
                    problems.append(
                        f"{key} aynı kaynakta değişti: "
                        f"{prev.get('date')} {str(prev.get(key))[:12]}… → "
                        f"{latest.get('date')} {str(latest.get(key))[:12]}…")

    # 3) Platform kapsamı: cutoff sonrası her iki platformdan kayıt (aynı
    #    kaynak + motor sürümü + SDE ile iki platformun kanonik hash'i
    #    birebir eşit olmalı — çapraz eşitleme bilgi notudur, ihlal değil).
    post = [r for r in fam
            if str(r.get("date", "")) >= PLATFORM_SCOPE_CUTOFF]
    plats = {r.get("platform") for r in post}
    missing = {"darwin", "linux"} - plats
    if missing:
        problems.append(
            f"platform kapsamı eksik (cutoff {PLATFORM_SCOPE_CUTOFF} "
            f"sonrası): {'/'.join(sorted(missing))} kaydı yok")
    return problems


def _cross_platform_note(records, family=FAMILY_MANUSCRIPT):
    """Bilgilendirici çapraz-platform gözlemi (fail DEĞİL); None veya metin.

    Aile bazlı: iki seri tek jsonl'da yaşadığı için darwin/linux kıyası yalnız
    AYNI ailenin satırları arasında yapılır — karışık seri kıyası (ör. canvas
    darwin vs manuscript linux) anlamsızdı ve yanıltıcı bir "eşitlik" kanıtı
    üretebilirdi.
    """
    fam = [r for r in records if family_of(r) == family]
    post = [r for r in fam
            if str(r.get("date", "")) >= PLATFORM_SCOPE_CUTOFF]
    latest_by_platform = {}
    for r in post:
        latest_by_platform[r.get("platform")] = r
    if not {"darwin", "linux"} <= set(latest_by_platform):
        return None
    d = latest_by_platform["darwin"]
    l = latest_by_platform["linux"]
    same_src = d.get("source_sha256") == l.get("source_sha256")
    keys = sorted(set(hash_keys(d)) & set(hash_keys(l)))
    same_sha = bool(keys) and all(d.get(k) == l.get(k) for k in keys)
    if same_src and same_sha:
        return ("not: [%s] darwin/linux kanonik hash'leri birebir eşit "
                "(aynı kaynak) — çapraz-platform determinizm güçlü kanıt"
                % family)
    if same_src:
        return ("not: [%s] darwin/linux kanonik hash'leri farklı (aynı kaynak) "
                "— beklenen: motor/paket-seti farkı; trendde izlenir" % family)
    return None


def _build_record(report, source):
    data = _extract_report_data(report)
    return {
        "date": datetime.date.today().isoformat(),
        "family": FAMILY_MANUSCRIPT,
        "source_mtime": int(os.stat(source).st_mtime),
        "source_sha256": _sha256_of(source),
        "sde": int(report.get("source_date_epoch", "0") or 0),
        "platform": platform.system().lower(),
        "gate": report["verdict"],
        **data,
    }


def _build_canvas_record(report, source):
    """Canvas ailesi kaydı: apex (kitap) kanonik hash'i + kaynak .tex parmak izi."""
    data = _extract_canvas_data(report)
    return {
        "date": datetime.date.today().isoformat(),
        "family": FAMILY_CANVAS,
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
                    "--check trend değişmezlerini doğrular (aile başına)")
    parser.add_argument("--update", action="store_true",
                        help="deney raporundan ölçüm oku ve jsonl'a ekle")
    parser.add_argument("--check", action="store_true",
                        help="trend değişmezlerini doğrula (fail-closed)")
    parser.add_argument("--family", choices=sorted(FAMILIES),
                        default=FAMILY_MANUSCRIPT,
                        help="hangi ailenin ölçümü kaydedilecek "
                             "(yalnız --update; varsayılan manuscript)")
    args = parser.parse_args(argv)
    if not (args.update or args.check):
        parser.error("bir mod gerekli: --update veya --check")

    if args.update:
        canvas = args.family == FAMILY_CANVAS
        report_path = CANVAS_REPORT if canvas else REPORT
        report = _read_report(report_path)
        if report is None:
            hint = ("make -f docs/Makefile.texlive plate-book-check"
                    if canvas else "texlive_determinism_hook.sh")
            print(f"FAIL: deney raporu yok: {report_path} — önce deneyi koş "
                  f"({hint})", file=sys.stderr)
            return 1
        try:
            source = _source_from_report(report)
            if not os.path.exists(source):
                print(f"FAIL: kaynak .tex bulunamadı: {source}",
                      file=sys.stderr)
                return 1
            if canvas:
                # Kayıt KİTAP (apex) satırı: rapor başka bir kaynağı
                # (levha, el yazması) gösteriyorsa o ölçüm aileyi temsil
                # etmez → fail-closed.
                if os.path.realpath(source) != os.path.realpath(CANVAS_APEX_TEX):
                    raise ValueError(
                        f"canvas raporu apex (kitap) kaynağını göstermiyor: "
                        f"{source} (beklenen {CANVAS_APEX_TEX}) — kitap hash'i "
                        f"olmayan ölçüm trende girmez")
                record = _build_canvas_record(report, source)
            else:
                record = _build_record(report, source)
        except ValueError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1
        _append(TREND, record)
        hashes = " ".join(
            "%s=%s…" % (k[:-len("_canonical_sha256")], str(record[k])[:12])
            for k in hash_keys(record))
        print(f"OK: {args.family} ölçümü eklendi: {TREND}")
        print(f"  date={record['date']} platform={record['platform']} "
              f"family={record['family']} {hashes}")
        return 0

    # --check modu (fail-closed trend kapısı; aile başına)
    try:
        records = _records()
        verdict = trend_invariant(records)
    except ValueError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    if verdict == "OK":
        parts = []
        for family in FAMILIES:
            fam = [r for r in records if family_of(r) == family]
            parts.append(f"{family} son {fam[-1]['date']} "
                         f"({fam[-1].get('platform')})")
        print(f"determinism-trend: OK ({len(records)} ölçüm, "
              + " · ".join(parts) + ")")
        for note in (_cross_platform_note(records, family)
                     for family in FAMILIES):
            if note:
                print(note)
        return 0
    print("FAIL: trend değişmezi ihlali:", file=sys.stderr)
    for problem in verdict.split("; "):
        print(f"  {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
