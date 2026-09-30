#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_id_residual_acceptance.py — Faz 3 kabul raporunun GERÇEK ÜRETİCİSİ.

Kaynak kanıt: `texlive_determinism_test.sh` raporu (varsayılan
`.build/texlive/determinism_report.txt`) — yani iki BAĞIMSIZ 3-geçiş koşumunun
ölçtüğü ham/kanonik hash'ler, `/ID` kalıntısı ve verdict. Bu script o kanıtı
`docs/ID_RESIDUAL_ACCEPTANCE.md` §4 hash geçiş defterine bağlar; defter satırı
elle yazılmaz, ölçülen alanlardan ÜRETİLİR.

  --check (varsayılan): kanıt tutarlı mı (verdict=PASS, run1=run2, rerun=0) ve
      kanonik hash defterde mi — değilse fail-closed (exit 1). Sahte kabul
      üretilmez; `make -f docs/Makefile.texlive accept` bunu çağırır.
  --update: kanıt TUTARLI ama defterde satır yoksa, ölçülen alanlardan yeni
      defter satırı üretip §4 tablosuna ekler (Faz 6 bilinçli çıkış yolu:
      yeni bağlam = yeni motor/font paketi/SDE) ve yeniden doğrular.

Kanonik tanımı (rapor sözleşmesi — fallback ZORUNLU):
  residual=/ID   → texlive_canonical_run{1,2}_sha256 (/ID nötrlenmiş hash)
  residual=none  → ham hash'ler zaten eşit: kanonik = texlive_run1_sha256
                   (o durumda rapor kanonik satırı YAZMAZ; fallback olmadan
                   deterministik bir motorda accept haksız yere fail-closed
                   olurdu)

Exit kodları:
  0 = KABUL — kanıt tutarlı + kanonik hash defterde
  1 = fail-closed — kanıt tutarsız (verdict≠PASS / run1≠run2 / rerun kaldı)
      veya kanonik hash defterde yok (--update edilmedi)
  2 = hata — rapor/defter yok ya da ayrıştırılamadı

stdlib-only, OFFLINE.
"""
from __future__ import annotations

import argparse
import os
import sys

DEFAULT_REPORT = ".build/texlive/determinism_report.txt"
DEFAULT_DOC = "docs/ID_RESIDUAL_ACCEPTANCE.md"

CANON1 = "texlive_canonical_run1_sha256"
CANON2 = "texlive_canonical_run2_sha256"
RAW1 = "texlive_run1_sha256"
RAW2 = "texlive_run2_sha256"
LEDGER_HEADING = "## 4."
DEFAULT_NOTE = "gen_id_residual_acceptance.py --update (2× bağımsız koşum)"


def parse_report(text):
    """`key=value` satırlarını sözlüğe çevir (ilk görülen kazanır).

    Başlık/boşluk/değeri boşluk içeren anahtar satırları atlanır; değerler
    boşluk içerebilir (`residual=/ID (pdfTeX …)`).
    """
    out = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "=" not in line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and " " not in key and key not in out:
            out[key] = value.strip()
    return out


def canonical_of(report):
    """(hash, mod) → mod: 'id-canonical' | 'raw-equal' | None (kanıt yok).

    Ayrıca (c1 != c2) tutarsızlığı 'mismatch' olarak bildirilir:
    dönen değer (canon, mod, problems).
    """
    c1, c2 = report.get(CANON1), report.get(CANON2)
    if c1 and c2:
        problems = [] if c1 == c2 else [
            "kanonik hash'ler farklı (run1≠run2) — içerik determinizmi YOK"]
        return c1, "id-canonical", problems
    r1, r2 = report.get(RAW1), report.get(RAW2)
    if r1 and r2:
        if r1 != r2:
            return None, None, [
                "ham hash'ler farklı ama kanonik satırlar raporda yok "
                "(rapor eksik/kirli) — kanonik karşılaştırma yapılamadı"]
        return r1, "raw-equal", []
    return None, None, ["raporda hash satırı yok (texlive_run{1,2}_sha256)"]


def evidence_problems(report):
    """Kanıt-tutarlılık hataları (verdict + rerun + kanonik eşitlik)."""
    problems = []
    verdict = report.get("verdict")
    if verdict != "PASS":
        problems.append(
            f"verdict=PASS değil (verdict={verdict or 'yok'} "
            f"residual={report.get('residual', 'yok')})")
    try:
        passes = int(report.get("passes", "1"))
    except ValueError:
        passes = 1
        problems.append(f"passes sayı değil: {report.get('passes')!r}")
    if passes > 1:
        for i in (1, 2):
            k = f"texlive_run{i}_rerun_left"
            v = report.get(k)
            if v != "0":
                problems.append(f"{k}={v or 'yok'} (son geçiş logunda "
                                "'Rerun to get' kalmış olabilir — hizalama "
                                "kanıtlanamadı)")
    return problems


def ledger_area(text):
    """§4 tablosunun (başlangıç, bitiş) satır indeksleri; yoksa None."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(LEDGER_HEADING):
            start = i
            break
    if start is None:
        return None
    first = last = None
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("|"):
            if first is None:
                first = i
            last = i
        elif first is not None:
            break
    if first is None:
        return None
    return first, last


def ledger_row_numbers(text):
    """§4 tablosundaki veri satırı numaraları (| 1 | …, | 2 | …)."""
    area = ledger_area(text)
    if not area:
        return []
    first, last = area
    nums = []
    for line in text.splitlines()[first:last + 1]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0].isdigit():
            nums.append(int(cells[0]))
    return nums


def build_row(report, canon, engine_label, note, row_no):
    """Ölçülen kanıttan §4 defter satırı üret (elle yazılmaz)."""
    residual = report.get("residual", "")
    raw1 = report.get(RAW1, "—")
    if "none" in residual:
        raw_cell = f"`{raw1}` (residual=none — ham = kanonik)"
    else:
        raw_cell = "koşum-başına değişken (`/ID`)"
    label = engine_label or (
        f"{os.path.basename(report.get('pdflatex', 'pdflatex'))} "
        "(sürüm etiketi verilmedi)")
    return ("| %d | %s | %s | %s | %s | `%s` | %s |"
            % (row_no, label, report.get("passes", "1"),
               report.get("source_date_epoch", "0"), raw_cell, canon, note))


def insert_row(text, row):
    """§4 tablosunun son veri satırından sonra yeni satırı ekle."""
    area = ledger_area(text)
    if not area:
        raise ValueError("§4 (hash geçiş defteri) tablosu bulunamadı")
    first, last = area
    lines = text.splitlines()
    lines.insert(last + 1, row)
    out = "\n".join(lines)
    if text.endswith("\n"):
        out += "\n"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Faz 3 /ID kabul kanıtını oku, defteri doğrula/üret")
    ap.add_argument("--report", default=DEFAULT_REPORT,
                    help="texlive_determinism_test.sh raporu (gerçek üretici çıktısı)")
    ap.add_argument("--doc", default=DEFAULT_DOC,
                    help="kabul raporu (hash geçiş defteri)")
    ap.add_argument("--update", action="store_true",
                    help="kanıt tutarlı ama defterde satır yoksa üretip ekle (bilinçli)")
    ap.add_argument("--engine-label", default=os.environ.get(
                        "PDFLATEX_VERSION", ""),
                    help="defter satırındaki 'Motor / sürüm' hücresi "
                         "(varsayılan: PDFLATEX_VERSION ortam değişkeni)")
    ap.add_argument("--note", default=DEFAULT_NOTE,
                    help="defter satırındaki 'Ölçüm' hücresi")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.report):
        print(f"HATA: determinism raporu yok: {args.report}", file=sys.stderr)
        print("      Önce gerçek üreticiyi koştur: "
              "make -f docs/Makefile.texlive check", file=sys.stderr)
        return 2
    if not os.path.isfile(args.doc):
        print(f"HATA: kabul raporu yok: {args.doc}", file=sys.stderr)
        return 2

    with open(args.report, encoding="utf-8") as f:
        report = parse_report(f.read())
    with open(args.doc, encoding="utf-8") as f:
        doc = f.read()

    canon, mode, problems = canonical_of(report)
    ev = evidence_problems(report)
    if problems or ev:
        print("ERROR: kabul KANITI TUTARSIZ — defter doğrulanamaz", file=sys.stderr)
        for p in problems + ev:
            print(f"       - {p}", file=sys.stderr)
        print(f"       Kanıt: {args.report}", file=sys.stderr)
        return 1
    if not canon:
        print("ERROR: kanonik hash hesaplanamadı (rapor eksik)", file=sys.stderr)
        return 1

    if canon in doc:
        print("── Faz 3 kabul ──")
        print("KABUL: kanonik hash kabul raporunun hash geçiş defterinde")
        print(f"canon={canon}")
        print(f"mod={mode}")
        return 0

    if args.update:
        num = max(ledger_row_numbers(doc) or [0]) + 1
        row = build_row(report, canon, args.engine_label, args.note, num)
        try:
            new_doc = insert_row(doc, row)
        except ValueError as exc:
            print(f"ERROR: {exc}: {args.doc}", file=sys.stderr)
            return 2
        with open(args.doc, "w", encoding="utf-8") as f:
            f.write(new_doc)
        print(f"DEFTER GÜNCELLENDİ: {args.doc}")
        print(row)
        print("── Faz 3 kabul ──")
        print("KABUL: kanonik hash kabul raporunun hash geçiş defterinde (yeni satır)")
        print(f"canon={canon}")
        print(f"mod={mode}")
        return 0

    print(f"ERROR: kanonik hash kabul raporunun hash geçiş defterinde yok: {canon}",
          file=sys.stderr)
    print(f"       Defter: {args.doc} §4 (hash geçiş defteri)", file=sys.stderr)
    print("       Yeni bağlam (CI, font paketi, motor sürümü) ise deftere",
          file=sys.stderr)
    print("       BİLİNÇLİ satır ekle (Faz 6 çıkış yolu) ve tekrar koş:", file=sys.stderr)
    print(f"         python3 {os.path.relpath(os.path.abspath(__file__))} "
          f"--update --report {args.report} --doc {args.doc} "
          f"--engine-label \"<motor sürümü>\"", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
