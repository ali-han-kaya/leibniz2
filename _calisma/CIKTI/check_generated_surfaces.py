#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_generated_surfaces.py — "CI'da ÜRET ve TARA" kapısı (fail-closed).

Problem sınıfı: commit dışı (`.gitignore`'lu) üretilmiş yüzeyleri denetleyen
kapılar "dosya yoksa SKIP" derse, taze klonda ve CI'da kanıt SESSİZCE
kaybolur (`design_preview.html` tam buydu: statik tarama yalnız yerel kopyaya
bakıyordu). Bu kapı envanteri (`generated_surfaces.py`) tek kaynak alır:

  1. **BUILD yüzeyleri** her koşuda GERÇEKTEN üretilir (geçici hedef ya da
     beyan edilmiş çıktı yolu) ve tarayıcısı çalıştırılır. Üretim, çıktı ya
     da tarama başarısızsa kapı KIRMIZI — SKIP yok.
  2. **SINIFLANDIRILMIŞ yüzeyler** (CI adımı / canlı runtime / toolchain)
     için beyan edilen üretici ve tarayıcı metinlerinin gerçekten o
     dosyalarda bulunduğu doğrulanır: "kayıt var, yürütme yok" fail-open'u
     kapıda kırmızıdır.
  3. `--audit`: kapı/test kaynaklarındaki gitignore'lu yol literallerinin
     TAMAMI envanterde sınıflandırılmış olmalı; yeni bir üretilmiş yüzey
     envantere yazılmadan eklenirse burada kırmızıya düşer.

Kullanım:
  python3 _calisma/CIKTI/check_generated_surfaces.py            # hızlı set
  python3 _calisma/CIKTI/check_generated_surfaces.py --all      # + yavaş set
  python3 _calisma/CIKTI/check_generated_surfaces.py --strict   # CI: SKIP = FAIL
  python3 _calisma/CIKTI/check_generated_surfaces.py --audit    # kapsam
  python3 _calisma/CIKTI/check_generated_surfaces.py --list     # envanter
  python3 _calisma/CIKTI/check_generated_surfaces.py --json     # makine-okunur

Çıkış kodları: 0 = hepsi PASS (strict'te SKIP yok), 1 = FAIL/SKIP(strict)
/ sınıflandırılmamış yol, 2 = kullanım hatası.

Yalnız `generated_surfaces` envanterini ve beyan ettiği üreticileri koşar;
dış ağa çıkmaz. Tüm yazma hedefleri `.gitignore`'ludur (design_preview için
çağrı başına geçici dizin).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile
from typing import Dict, List

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import generated_surfaces as registry  # noqa: E402


def _fmt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return "%.1f MiB" % (n / (1024 * 1024))
    if n >= 1024:
        return "%.1f KiB" % (n / 1024)
    return "%d B" % n


def run_build(surface, strict: bool) -> dict:
    """Tek BUILD yüzeyi: üret → çıktıları doğrula → tara."""
    row = {"id": surface.id, "kind": "build", "status": "PASS",
           "note": surface.note, "outputs": {}, "problems": []}
    missing = registry.unmet_requirements(surface)
    if missing:
        row["status"] = "FAIL" if strict else "SKIP"
        row["problems"].append("araç eksik: %s" % ", ".join(missing))
        return row

    tmp = None
    out = None
    if any(spec == "{out}" for spec in surface.outputs):
        tmp = tempfile.TemporaryDirectory(prefix="gen-surface-%s-" % surface.id)
        out = pathlib.Path(tmp.name) / "design_preview.html"
    try:
        proc = registry.generate(surface, out=out)
        if proc.returncode != 0:
            row["status"] = "FAIL"
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
            row["problems"].append("üretici rc=%d: %s"
                                   % (proc.returncode, " | ".join(tail)))
            return row
        paths = registry.output_paths(surface, out)
        for name, path in paths.items():
            if not path.is_file():
                row["problems"].append("beyan edilen çıktı yok: %s" % name)
                continue
            row["outputs"][name] = path.stat().st_size
        row["problems"].extend(registry.scan(surface, paths))
    finally:
        if tmp is not None:
            tmp.cleanup()
    # Design preview taraması geçici dosya silindikten SONRA değil, içeride
    # yapılır; çıktı boyutları raporda kalır.
    if row["problems"]:
        row["status"] = "FAIL"
    return row


def run_classified(entry) -> dict:
    problems = registry.verify_classified(entry)
    return {"id": entry.id, "kind": entry.kind,
            "status": "FAIL" if problems else "PASS",
            "note": entry.note, "outputs": {}, "problems": problems}


def run_audit() -> List[dict]:
    rows = []
    for literal, source in registry.audit_unclassified():
        rows.append({"id": "audit", "kind": "coverage", "status": "FAIL",
                     "note": "sınıflandırılmamış gitignore'lu yol",
                     "problems": ["%s (kaynak: %s)" % (literal, source)]})
    return rows


def render(rows: List[dict], strict: bool) -> List[str]:
    lines = ["GENERATED SURFACES — commit dışı üretilmiş yüzeyler "
             "(üret + tara)"]
    for row in rows:
        mark = {"PASS": "✅", "SKIP": "⏭️ ", "FAIL": "❌"}[row["status"]]
        detail = ""
        if row.get("outputs"):
            detail = " [" + ", ".join("%s=%s" % (k, _fmt_size(v))
                                      for k, v in row["outputs"].items()) + "]"
        lines.append("%s %-26s %-9s %s%s"
                     % (mark, row["id"], row["kind"], row["status"], detail))
        for problem in row["problems"]:
            lines.append("     • %s" % problem)
    fails = [r for r in rows if r["status"] == "FAIL"]
    skips = [r for r in rows if r["status"] == "SKIP"]
    if fails:
        lines.append("SONUÇ: FAIL — %d yüzey (üret ya da tarama başarısız)"
                     % len(fails))
    elif skips:
        lines.append("SONUÇ: SKIP — %d yüzey araç yokluğundan üretilmedi: %s"
                     % (len(skips), ", ".join(r["id"] for r in skips)))
        if strict:
            lines.append("  --strict: SKIP kabul edilmez (CI ortamı tüm "
                         "araçları kurmalı)")
    else:
        lines.append("SONUÇ: PASS — tüm üretilmiş yüzeyler üretildi ve "
                     "tarandı")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true",
                    help="yavaş/yazma-üreten BUILD yüzeylerini de koş "
                         "(varsayılan: yalnız hızlı set)")
    ap.add_argument("--strict", action="store_true",
                    help="araç yokluğu SKIP değil FAIL (CI)")
    ap.add_argument("--audit", action="store_true",
                    help="yalnız kapsam denetimi: gitignore'lu yollar "
                         "sınıflandırılmış mı?")
    ap.add_argument("--with-audit", action="store_true",
                    help="üretim/tarama ile birlikte kapsam denetimini de koş")
    ap.add_argument("--list", action="store_true",
                    help="envanteri yazdır (üretim yapmaz)")
    ap.add_argument("--json", action="store_true",
                    help="makine-okunur çıktı (stdout tek JSON belgesi)")
    args = ap.parse_args(argv)

    if args.list:
        rows = []
        for surface in registry.BUILD:
            rows.append({"id": surface.id, "kind": "build",
                         "generator": list(surface.generator),
                         "outputs": list(surface.outputs),
                         "scan": surface.scan,
                         "requires": list(surface.requires),
                         "fast": surface.fast, "note": surface.note})
        for entry in registry.CLASSIFIED:
            rows.append({"id": entry.id, "kind": entry.kind,
                         "paths": list(entry.paths),
                         "owner": "%s ← %r" % (entry.owner_file,
                                               entry.owner_snippet),
                         "scan": "%s ← %r" % (entry.scan_file,
                                              entry.scan_snippet),
                         "note": entry.note})
        if args.json:
            json.dump({"surfaces": rows}, sys.stdout, ensure_ascii=False,
                      indent=2)
            sys.stdout.write("\n")
            return 0
        for row in rows:
            print("%-26s %-9s %s" % (row["id"], row["kind"],
                                     row.get("note", "")))
        return 0

    rows: List[dict] = []
    if args.audit:
        rows = run_audit()
        if not rows:
            rows = [{"id": "coverage_audit", "kind": "coverage",
                     "status": "PASS", "outputs": {}, "problems": [],
                     "note": "tüm gitignore'lu yollar sınıflandırılmış"}]
    else:
        for surface in registry.BUILD:
            if surface.fast or args.all:
                rows.append(run_build(surface, strict=args.strict))
        rows.extend(run_classified(entry)
                    for entry in registry.CLASSIFIED)
        if args.with_audit:
            unaudited = run_audit()
            rows.extend(unaudited)
            if not unaudited:
                rows.append({"id": "coverage_audit", "kind": "coverage",
                             "status": "PASS", "outputs": {},
                             "problems": [],
                             "note": "tüm gitignore'lu yollar "
                                     "sınıflandırılmış"})

    fails = [r for r in rows if r["status"] == "FAIL"]
    skips = [r for r in rows if r["status"] == "SKIP"]
    rc = 1 if fails or (args.strict and skips) else 0

    if args.json:
        json.dump({"surfaces": rows, "strict": args.strict, "ok": rc == 0},
                  sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        for line in render(rows, args.strict):
            print(line)
    return rc


if __name__ == "__main__":
    sys.exit(main())
