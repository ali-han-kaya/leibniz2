#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""select_affected_tests.py — commit'te DOKUNULAN testleri seçer.

check-unit-tests her commit'te 190 test dosyasının tamamını koşuyordu
(ölçüldü ~345-370 s). Bu araç, değişen dosya listesinden koşulması gereken
testleri seçer; `check_unit_tests_hook.sh` yalnız onları koşar.

Çıktı: seçilen test dosya adları, her satıra bir tane (stdout). Tanılar
stderr'e gider — kabuk yalnız isimleri okur.

KÖR KAPI (rc=2): manifest ya da kapsam eşlemesi okunamazsa seçim ÜRETİLMEZ.
Sessizce "0 test" demek, commit'i hiçbir şey koşmadan geçirmek olurdu;
bunun yerine çağıran taraf TAM BATARYA'ya düşer. Ölçülemeyen = yeşil değil.

Seçim kuralı `test_coverage_report.affected_tests`'tedir (tek kaynak):
  - ALWAYS_RUN testleri her commit'te koşar (makine + ölçülemeyen bağımlılık)
  - kalanlar için eşleme = TÜRETİLEN (testin import'ları) ∪ BİLANEN glob'lar
  - test dosyasının kendisi değiştiyse o test koşar

`--all-files` (yani CI) girdiğinde seçim TAM BATARYAYA eşittir: manifest'teki
her test dosyası değişen listededir. Bu, "full batarya CI'da kalır"
sözleşmesinin mekanik garantisidir ve testle sabitlenmiştir.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

CIKTI = pathlib.Path(__file__).resolve().parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import test_coverage_report as coverage  # noqa: E402

BLIND = 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Değişen dosyalardan etkilenen testleri seçer.")
    parser.add_argument("paths", nargs="*",
                        help="depo göreli değişen dosya yolları")
    parser.add_argument("--full", action="store_true",
                        help="seçim yapma: manifest'in tamamını bas")
    parser.add_argument("--json", action="store_true",
                        help="makine-okunur rapor (stdout)")
    args = parser.parse_args(argv)

    try:
        manifest = coverage.read_manifest()
    except OSError as exc:
        print(f"select_affected_tests: KÖR KAPI — manifest okunamadı: {exc}",
              file=sys.stderr)
        return BLIND
    if not manifest:
        print("select_affected_tests: KÖR KAPI — manifest BOŞ; seçim "
              "üretilemez (çağıran tam bataryaya düşmeli).", file=sys.stderr)
        return BLIND

    if args.full:
        selected = list(manifest)
        report = {"selected": selected, "total": len(manifest), "mode": "full"}
    else:
        result = coverage.affected_tests(args.paths, manifest=manifest)
        selected = result["selected"]
        report = {"selected": selected, "total": result["total"],
                  "mode": "incremental", "changed": len(result["changed"])}

    # Asla boş olamaz: ALWAYS_RUN kümesi her commit'te devreye girer. Boş
    # çıkması bir kural ihlalidir, sessiz geçilmez.
    if not selected:
        print("select_affected_tests: KÖR KAPI — seçim BOŞ döndü; "
              "ALWAYS_RUN kuralı ihlal edilmiş.", file=sys.stderr)
        return BLIND

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        for t in selected:
            print(t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
