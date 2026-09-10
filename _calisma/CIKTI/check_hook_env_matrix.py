#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_hook_env_matrix.py — docs/HOOK_ENV_MATRIX.md ↔ probe_tool_versions() denetimi.

Hook env sürüm tablosunun kodla senkronunu fail-closed doğrular:

  1. ARAÇ KÜMESİ (iki yönlü): doc tablosundaki `Anahtar` sütunu ==
     verify_delivery.probe_tool_versions() anahtar kümesi. Kodda yeni bir
     araç prob edilirse doc'a satır eklenmeli; doc'ta kodda olmayan satır
     (bayat) varsa kaldırılmalı.
  2. PIN'LER: `lean` satırının "Beklenen pin" hücresi LEAN_TOOLCHAIN
     sabitini (leanprover/lean4:v4.14.0) içermeli — K9-LAKE toolchain'i tek
     kaynaktır.
  3. ALGILAMA KOMUTLARI: her satırın "Algılama komutu" hücresi dolu olmalı
     (probe'un nasıl çalıştığı belgelenmeden geçilmez).

Ek olarak canlı prob'u çalıştırıp gözlenen sürümleri makine-okunur yazar
(advisory — sürüm değerleri bloke etmez, yapısal drift eder).

Exit: 0 = uyumlu, 1 = drift (fail-closed), 2 = kullanım/ortam hatası.
--json: {ok, findings[], observed{}} makine-okunur.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.normpath(os.path.join(HERE, "..", "..", "docs",
                                    "HOOK_ENV_MATRIX.md"))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import verify_delivery as vd  # noqa: E402

# Tablo satırı: | `python` | Python | tümü | pin | 3.9.6 | 3.12 | komut |
# Anahtar karakter sınıfı RAKAM içerir (z3 gibi araç anahtarları)!
_ROW_RE = re.compile(r"^\|\s*`([a-z0-9_]+)`\s*\|(.+?)\|\s*$")
# 7 hücreli satır (Anahtar + Araç + K katmanı + pin + yerel + CI + komut).
_CELLS = 7


def parse_table(text):
    """HOOK_ENV_MATRIX.md'deki sürüm tablosunu {anahtar: hücreler} olarak ayrıştır."""
    rows = {}
    in_table = False
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            m = _ROW_RE.match(line)
            if m and len(cells) == _CELLS:
                rows[m.group(1)] = cells
        elif line.strip() and not line.startswith("#"):
            in_table = False
    return rows


def check_doc(text, probe_keys):
    """doc ↔ kod yapısal denetimi. Döner (ok, findings[])."""
    findings = []
    rows = parse_table(text)
    doc_keys = set(rows)
    code_keys = set(probe_keys)

    for k in sorted(code_keys - doc_keys):
        findings.append(f"KOD'DA VAR, DOC'TA YOK: '{k}' — "
                        f"HOOK_ENV_MATRIX.md'ye satır ekle (probe_tool_versions "
                        f"artık '{k}' prob ediyor)")
    for k in sorted(doc_keys - code_keys):
        findings.append(f"DOC'TA VAR, KOD'DA YOK: '{k}' — "
                        f"bayat satır, kaldır (probe_tool_versions '{k}' "
                        f"prob etmiyor)")

    # lean pin'i → LEAN_TOOLCHAIN sabitiyle birebir (tek kaynak).
    if "lean" in rows:
        pin_cell = rows["lean"][3]
        if vd.LEAN_TOOLCHAIN not in pin_cell:
            findings.append(
                f"LEAN PIN DRIFT: 'lean' Beklenen pin hücresi '{pin_cell}' "
                f"LEAN_TOOLCHAIN '{vd.LEAN_TOOLCHAIN}' içermiyor")

    # Her satırın algılama komutu hücresi dolu olmalı (hücre 6).
    for k, cells in sorted(rows.items()):
        if not cells[6]:
            findings.append(f"ALGILAMA KOMUTU YOK: '{k}' — "
                            f"'Algılama komutu' hücresi boş")
    return (len(findings) == 0, findings)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", default=DOC, help="matrix doc yolu")
    ap.add_argument("--json", action="store_true", help="makine-okunur JSON")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.doc):
        print(f"HATA: {args.doc} bulunamadı", file=sys.stderr)
        return 2
    with open(args.doc, encoding="utf-8") as f:
        text = f.read()

    try:
        observed = vd.probe_tool_versions()
    except Exception as e:  # noqa: BLE001
        print(f"HATA: probe_tool_versions koşulamadı: {e}", file=sys.stderr)
        return 2

    ok, findings = check_doc(text, list(observed))
    if args.json:
        print(json.dumps({
            "tool": "check_hook_env_matrix.py",
            "doc": args.doc,
            "ok": ok,
            "verdict": "PASS" if ok else "FAIL",
            "findings": findings,
            "observed": observed,
        }, indent=2, ensure_ascii=False))
        return 0 if ok else 1

    print("=== Hook env sürüm matrisi denetimi ===")
    for k, v in sorted(observed.items()):
        print(f"  {k:<11} {v or 'yok (None — advisory)'}")
    print(f"  doc: {args.doc} ({len(parse_table(text))} satır)")
    if findings:
        for f in findings:
            print(f"  [DRIFT] {f}")
    print(f"SONUÇ: {'PASS' if ok else 'FAIL'} "
          f"({len(findings)} bulgu, {'fail-closed' if findings else 'uyumlu'})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
