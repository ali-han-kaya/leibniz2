#!/usr/bin/env python3
"""seed_a11y_history.py — a11y kapisi icin deterministik run gecmisi tohumla.

NEDEN (olcum 2026-10-03, yerel Chromium + gercek preview_server):
  a11y-gate job'i temiz clone'da `history.jsonl` YOKKEN basliyor; pano
  trend yuzeyi hic cizilmiyor. Kapinin taradigi anda:
      #trend <text> node = 0, #trend-count = "" (bos),
      axe color-contrast = 36 node, trend'e ait node = 0
  fetch'ler cozulduktan sonra:
      #trend <text> node = 14, #trend-count = "(4 run)",
      axe color-contrast = 43 node, trend'e ait node = 6
  Yani 6 gercek node kapidan gorusuydu.

NEDEN TOHUMLAMA TEK BASINA YETMEZ:
  Veri diskte olsa bile kapı `wait_until="load"` sonrasi HEMEN axe.run()
  cagirir; fetch'ler cozulmedigi icin ayni bosluk korunurdu. Iki kosul
  birlikte duzeltilir: hazir isareti (preview.js scanPending*) + kapida
  fail-closed bekci (a11y_gate `settle`). Bu dosya yalnizca tohumlama
  yarisi; `--rows` >= 2 zorunlu (tek nokta cizgi degil).

BU BIR SAHTE VERI URETICISIDIR, OLCUM DEGILDIR: amaci kapinin dolu
yuzeyi taradigini kanitlamak. Gercek kosumun gecmisi (run-history
artifact'i) BILEREK KULLANILMAZ: capraz-job artifact bagimliligi kapiyi
kirilgan yapar ve tohumlama adiminin sirasi belirsizlestirir.

DETERMINIZM: saat, tarih ve rastgelelik YOK. Ayni `--rows` -> ayni bayt
(test_a11y_settle_contract.py::test_two_runs_are_byte_identical), yani
kumeler arasinda a11y girdisi oynamaz.
"""

import argparse
import datetime
import json
import os
import sys

BASE_TS = datetime.datetime(2026, 1, 5, 3, 17, tzinfo=datetime.timezone.utc)
STEP = datetime.timedelta(days=7)
MIN_ROWS = 2
DEFAULT_ROWS = 8

# Sabit desenler: indeks -> deger. Amac gercekci bir trend sekli, degil
# deterministik olmak. p0 hicbir satirda yok (kapinin konusu P0/P1 trendi).
P1_PATTERN = (0, 0, 1, 0, 0, 2, 0, 1)
DURATION_PATTERN = (41.2, 44.8, 39.6, 45.4, 42.1, 43.7, 40.9, 46.2)
BUDGET_PATTERN = (1.02, 1.09, 1.04, 1.11, 1.07, 1.15, 1.03, 1.08)


def row(index):
    """index -> tek history satiri (dashboard alanlari dolu)."""
    ts = (BASE_TS + STEP * index).isoformat()
    return {
        "ts": ts,
        "verdict": "PASS",
        "p0": 0,
        "p1": P1_PATTERN[index % len(P1_PATTERN)],
        "duration_s": DURATION_PATTERN[index % len(DURATION_PATTERN)],
        "duration_pct_warn": False,
        "budget_usd": BUDGET_PATTERN[index % len(BUDGET_PATTERN)],
        "budget_limit": 30.0,
        "budget_method": "both",
        "pdf_pages": 33,
        "ref_count": 64,
        "refs_verified": 64,
        "refs_total": 64,
        "refs_mismatch": 0,
        "z3_passed": 12,
        "z3_failed": 0,
        "z3_total": 12,
        "lean_ok": True,
        "lean_detail": "",
        "cli_override_count": 0,
        "exit_code": 0,
    }


def write_history(path, rows=DEFAULT_ROWS):
    """`rows` satirlik deterministik gecmisi `path`'e yaz; satir sayisini dondur.

    rows < MIN_ROWS: SystemExit (fail-closed) — tek satirlik 'trend' cizgi
    degildir ve kapinin yuzey dogrulugu testi degil, yanlis assurance verir.
    """
    if rows < MIN_ROWS:
        print("HATA: --rows >= %d olmali (tek nokta trend cizmez)" % MIN_ROWS,
              file=sys.stderr)
        raise SystemExit(2)
    lines = [json.dumps(row(i), ensure_ascii=False, sort_keys=True)
             for i in range(rows)]
    payload = "\n".join(lines) + "\n"
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w", encoding="utf-8") as f:
        f.write(payload)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="history.jsonl hedef yolu")
    ap.add_argument("--rows", type=int, default=DEFAULT_ROWS,
                    help="tohumlanacak satir sayisi (>= %d)" % MIN_ROWS)
    args = ap.parse_args(argv)
    written = write_history(args.out, args.rows)
    print("seeded %d rows -> %s" % (written, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
