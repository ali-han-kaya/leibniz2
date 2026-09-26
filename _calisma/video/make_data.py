#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_data.py — LeibnizChain kompozisyonunun veri dosyasini uretir.

Kompozisyon kendi sayilarini GÖMMEZ: `public/data/leibniz.json` dosyasini
`delayRender` + `staticFile` ile okur (src/useLeibnizData.ts). Bu script o
dosyayi repodaki gercek kaynaklardan deterministik olarak uretir:

  - _calisma/CIKTI/history.jsonl            → zaman cizelgesi sahnesi
  - test_id_residual_acceptance_doc.py      → SHA-256 mühür sabitleri

Girdi dosyalarindan biri yoksa fail-closed: sessizce bozuk veriyle sahne
üretmek, uydurma sayı göstermekten kötüdür.

  python3 make_data.py            → public/data/leibniz.json yazar
  python3 make_data.py --stdout   → JSON'u stdout'a basar (testler icin)
  python3 make_data.py --check    → uretilemiyorsa exit 1 (taniklik kapisi)
  python3 make_data.py --allow-missing-data
                                   → history.jsonl yoksa SENTINEL veri uretir
                                     (bos kosu listesi + data_missing işareti).
                                     YALNIZ temiz klon/CI'da kullanilir: tip
                                     ve render boru hattini ölçmek için veri
                                     olmadan da kompozisyon kurulabilmelidir.
                                     Yerelde varsayılan fail-closed kalır —
                                     ekranın boş kalması sessizce "veri
                                     yok" demekten iyidir.

stdlib-only, cevrimdisi. Yollar __file__'ten turetilir (sabit gomulu yol yok).
"""

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HISTORY = os.path.join(REPO, "_calisma", "CIKTI", "history.jsonl")
FROZEN = os.path.join(REPO, "_calisma", "CIKTI", "test_id_residual_acceptance_doc.py")
OUT = os.path.join(HERE, "public", "data", "leibniz.json")

# Kompozisyonun kare bütcesi — src/Root.tsx durationInFrames ile ayni olmak
# ZORUNDA (test_video_data_contract.py bunu dogrular).
FRAMES = 760
FPS = 30
WIDTH = 1280
HEIGHT = 720

# Donmus kanit kartlari. Bunlar 2026-09-18 Remotion turunun kayit degerleridir
# (findings.md:102, progress.md:6, recovery_patches_20260918 yamasinda
# patch1789754982-84993:543). Burada SABIT liste tutulur: calisma aninda
# README/progress dosyalarindan okunsa, her gun degisen bir sayi kare
# bütcesini kaydirirdi.
EVIDENCE = [
    {"label": "Test suite", "value": "2323 OK", "sub": "skipped=12", "ok": True},
    {"label": "a11y gate", "value": "PASS", "sub": "axe + 28 kural", "ok": True},
    {"label": "Seal hash", "value": "74b2cdbd…", "sub": "delivery raw sha256", "ok": True},
    {"label": "RC probe", "value": "9/9", "sub": "release candidate", "ok": True},
]

GATES_CORE = ["K0", "K1", "K2", "K3", "K4", "K5", "K6", "K7"]
GATES_ALL = GATES_CORE + [
    "K8",
    "K9",
    "K10",
    "K11",
    "K12",
    "K13",
    "K14",
    "K15",
]
GATE_NAMES = {
    "K0": "Bayat zip taraması",
    "K1": "Yapı",
    "K2": "Manifest",
    "K3": "Checksum",
    "K4": "Lineage",
    "K5": "Frozen record",
    "K6": "Kaynak",
    "K7": "PDF",
    "K8": "Refs",
    "K9": "Z3",
    "K10": "Lean",
    "K11": "Hook",
    "K12": "Pre-commit",
    "K13": "Sidecar",
    "K14": "Lineage drift",
    "K15": "History sidecar",
}

RECONSTRUCTION = (
    "yeniden inşa: kaynak proje /tmp temizliginde kayboldu; spesifikasyon "
    "findings.md:70-75 ve recovery_patches_20260918/patch1789754982-84993:540-549"
)


def fail(msg):
    print("make_data: FAIL — %s" % msg, file=sys.stderr)
    raise SystemExit(1)


def read_history(allow_missing=False):
    """history.jsonl -> kosu satirlari."""
    if not os.path.isfile(HISTORY):
        if not allow_missing:
            fail("girdi yok: %s (preview_server calismasi gerekli)" % HISTORY)
        return []
    runs = []
    with open(HISTORY, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                fail("history.jsonl:%d ayristirilamadi: %s" % (lineno, exc))
            if "ts" not in row:
                fail("history.jsonl:%d 'ts' alani yok" % lineno)
            runs.append(
                {
                    "n": len(runs) + 1,
                    "ts": row["ts"][:19].replace("T", " "),
                    "day": row["ts"][:10],
                    "verdict": row.get("verdict") or "?",
                    "duration_s": row.get("duration_s"),
                    "findings": len(row.get("findings") or []),
                }
            )
    if not runs and not allow_missing:
        fail("history.jsonl bos — zaman cizelgesi sahnesi veri alamaz")
    return runs


def read_frozen_constants():
    """test_id_residual_acceptance_doc.py icindeki SHA-256 sabitlerini okur.

    AST yerine metin taramasi: dosya zaten tek parca string literaller
    birlestirme deseni kullaniyor, ve bu yontem modul icerigi degistirse bile
    (yeni sabit, farkli sira) calisir.
    """
    if not os.path.isfile(FROZEN):
        fail("girdi yok: %s" % FROZEN)
    src = open(FROZEN, encoding="utf-8").read()
    out = {}
    for name in ("DELIVERY_RAW", "DELIVERY_STRIPPED", "PDFTEX_3PASS"):
        marker = name + " = ("
        idx = src.find(marker)
        if idx < 0:
            fail("sabit bulunamadi: %s" % name)
        chunk = src[idx + len(marker) : src.find(")", idx)]
        value = "".join(chunk.split('"')[1::2])
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            fail("%s 64 haneli hex degil: %r" % (name, value))
        out[name] = value
    return out


def build(allow_missing=False):
    runs = read_history(allow_missing=allow_missing)
    frozen = read_frozen_constants()
    verdicts = collections.Counter(r["verdict"] for r in runs)
    span = {
        "count": len(runs),
        "verdicts": dict(sorted(verdicts.items())),
        "data_missing": not runs,
    }
    span["first"] = runs[0]["day"] if runs else None
    span["last"] = runs[-1]["day"] if runs else None
    return {
        "meta": {
            "repo": "leibniz2",
            "composition": "LeibnizChain",
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "frames": FRAMES,
            "duration_s": round(FRAMES / FPS, 2),
            "reconstruction": RECONSTRUCTION,
        },
        "runs": runs,
        "run_span": span,
        "evidence": EVIDENCE,
        "gates": {
            "range": "K0 – K15",
            "core": GATES_CORE,
            "all": GATES_ALL,
            "names": GATE_NAMES,
            "verdict": "PASS",
        },
        "seal": {
            "delivery_raw": frozen["DELIVERY_RAW"],
            "delivery_stripped": frozen["DELIVERY_STRIPPED"],
            "pdftex_3pass": frozen["PDFTEX_3PASS"],
        },
    }


def dumps(payload):
    """Tek yazim bicimi: indent=2, ensure_ascii=False, son satirda satir sonu.

    prettier bu bicimi degistirmedigi icin uretilen dosya bicim kapisindan
    gecer (satiri dizilere sigmiyorsa prettier de ayni sekilde acar).
    """
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stdout", action="store_true", help="JSON'u yazmak yerine bas")
    ap.add_argument("--check", action="store_true", help="uretim kapisi: hata halinde exit 1")
    ap.add_argument(
        "--allow-missing-data",
        action="store_true",
        help="history.jsonl yoksa sentinel uret (yalniz temiz klon/CI)",
    )
    args = ap.parse_args(argv)

    text = dumps(build(allow_missing=args.allow_missing_data))

    if args.check:
        print("make_data --check: OK (%d bayt uretilebilir)" % len(text.encode("utf-8")))
        return 0
    if args.stdout:
        sys.stdout.write(text)
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("make_data: %s (%d bayt)" % (os.path.relpath(OUT, REPO), len(text.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
