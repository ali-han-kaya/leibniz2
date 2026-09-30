#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_data.py — LeibnizChain kompozisyonunun veri dosyasini uretir.

Kompozisyon kendi sayilarini GÖMMEZ: `public/data/leibniz.json` dosyasini
`delayRender` + `staticFile` ile okur (src/useLeibnizData.ts). Bu script o
dosyayi repodaki gercek kaynaklardan deterministik olarak uretir:

  - _calisma/CIKTI/history.jsonl            → zaman cizelgesi + verdict
                                                 dagilimi + kapi kirilmasi
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
import signal
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

# history.jsonl'deki kapı telemetri sütunları. Hepsi null ise kapı hiç
# sonuç üretmeden koşu kesildi demektir — sahne "RAPOR YOK" der, ✅ uydurmaz.
GATE_TELEMETRY = [
    "refs_verified",
    "refs_total",
    "refs_mismatch",
    "z3_passed",
    "z3_failed",
    "z3_total",
    "lean_ok",
    "lineage_ok",
    "lineage_count",
    "flaky_count",
    "deterministic_count",
    "precommit_hooks",
]

# status_board işaretleri. Tanınmayan işaret UYDURULMAZ: "UNKNOWN" olur ve
# sahne soluk çizer (sessizce PASS saymak, uydurma sayı üretmektir).
BOARD_MARKS = {
    "✅": "PASS",  # U+2705
    "✔": "PASS",
    "⚠": "WARN",  # U+26A0 (+ varyasyon seçici U+FE0F)
    "❌": "FAIL",  # U+274C
    "⛔": "FAIL",
}

RECONSTRUCTION = (
    "yeniden inşa: kaynak proje /tmp temizliginde kayboldu; spesifikasyon "
    "findings.md:70-75 ve recovery_patches_20260918/patch1789754982-84993:540-549"
)


def fail(msg):
    print("make_data: FAIL — %s" % msg, file=sys.stderr)
    raise SystemExit(1)


def read_history(allow_missing=False):
    """history.jsonl -> (kosu satirlari, kapı telemetri doluluk sayaci).

    Telemetri sayaci GATE_TELEMETRY sutun basina "bu kosuda dolu olan kac
    sutun" sayar. 0 olan sutun "hicbir kosuda raporlanmadi" demektir.
    """
    if not os.path.isfile(HISTORY):
        if not allow_missing:
            fail("girdi yok: %s (preview_server calismasi gerekli)" % HISTORY)
        return [], {c: 0 for c in GATE_TELEMETRY}
    runs = []
    telemetry = {c: 0 for c in GATE_TELEMETRY}
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
            for col in GATE_TELEMETRY:
                if row.get(col) is not None:
                    telemetry[col] += 1
            runs.append(
                {
                    "n": len(runs) + 1,
                    "ts": row["ts"][:19].replace("T", " "),
                    "day": row["ts"][:10],
                    "verdict": row.get("verdict") or "?",
                    "duration_s": row.get("duration_s"),
                    "findings": len(row.get("findings") or []),
                    "exit_code": row.get("exit_code"),
                    "p0": row.get("p0"),
                    "p1": row.get("p1"),
                    "drift": row.get("pattern_drift") or "?",
                    "z3_passed": row.get("z3_passed") or 0,
                    "z3_total": row.get("z3_total") or 0,
                    "overrides": row.get("cli_override_count") or 0,
                    "board": row.get("status_board") or "",
                    "telemetry_reported": sum(
                        1 for c in GATE_TELEMETRY if row.get(c) is not None
                    ),
                }
            )
    if not runs and not allow_missing:
        fail("history.jsonl bos — zaman cizelgesi sahnesi veri alamaz")
    return runs, telemetry


def parse_status_board(text):
    """"Pre-commit ⚠️ · K0 ✅ · …" -> [{label, state}].

    ayirici "·" (U+00B7); isaretler "⚠️" gibi varyasyon seçici (U+FE0F)
    taşıyabildiği için önce onu temizlenir, sonra işaret bulunur — böylece
    "K0✅" (boşluksuz) ve "K0 ✅" aynı ayrışır.
    """
    out = []
    for chunk in (text or "").split("·"):
        chunk = chunk.replace("\ufe0f", "").strip()
        if not chunk:
            continue
        mark, label = "", chunk
        for glyph, state in BOARD_MARKS.items():
            if glyph in chunk:
                mark, label = glyph, chunk.replace(glyph, "").strip()
                break
        if not label:
            label = chunk
        out.append(
            {"label": label, "state": BOARD_MARKS.get(mark, "UNKNOWN"), "mark": mark}
        )
    return out


def signal_name(exit_code):
    """exit_code=-15 -> "SIGTERM". Pozitif/None kod sinyali degildir."""
    if exit_code is None or exit_code >= 0:
        return None
    try:
        return signal.Signals(-exit_code).name
    except ValueError:
        return None


def read_frozen_constants():
    """test_id_residual_acceptance_doc.py icindeki SHA-256 sabitlerini okur.

    AST yerine metin taramasi: dosya zaten tek parca string literaller
    birlestirme deseni kullaniyor, ve bu yontem modul icerigi degistirse bile
    (yeni sabit, farkli sira) calisir.
    """
    if not os.path.isfile(FROZEN):
        fail("girdi yok: %s" % FROZEN)
    with open(FROZEN, encoding="utf-8") as fh:
        src = fh.read()
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
    runs, telemetry = read_history(allow_missing=allow_missing)
    frozen = read_frozen_constants()
    total = len(runs)

    verdicts = collections.Counter(r["verdict"] for r in runs)
    exit_codes = collections.Counter(r["exit_code"] for r in runs)
    drift = collections.Counter(r["drift"] for r in runs)
    span = {
        "count": total,
        "verdicts": dict(sorted(verdicts.items())),
        # Sıralı liste (sinyal adıyla): grafik segmentleri için sayı-dizesi
        # anahtar yerine gerçek kod + ad.
        "exits": [
            {
                "code": code,
                "count": n,
                "signal": signal_name(code),
            }
            for code, n in sorted(
                exit_codes.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)
            )
        ],
        "drift": dict(sorted(drift.items())),
        "data_missing": not runs,
    }
    span["first"] = runs[0]["day"] if runs else None
    span["last"] = runs[-1]["day"] if runs else None
    span["severity"] = {
        "p0": sum(r["p0"] or 0 for r in runs),
        "p1": sum(r["p1"] or 0 for r in runs),
        "findings": sum(r["findings"] for r in runs),
        "z3_passed": sum(r["z3_passed"] for r in runs),
        "z3_total": sum(r["z3_total"] for r in runs),
        "overrides": sum(r["overrides"] for r in runs),
    }
    span["max_duration_s"] = (
        max((r["duration_s"] or 0) for r in runs) if runs else None
    )
    span["telemetry"] = {
        "columns": len(GATE_TELEMETRY),
        # "dolu" = hicbir kosuda null olmayan sutun. z3 ailesi 0/0 degerlidir
        # (sutun dolu, kanit yukumlulugu yok) — bu yuzden "raporlandi" ile
        # "basarili" birbirine karistirilmaz.
        "reported": sorted(c for c, n in telemetry.items() if n > 0),
        "unreported": sorted(c for c, n in telemetry.items() if n == 0),
        "min_per_run": min((r["telemetry_reported"] for r in runs), default=0),
        "max_per_run": max((r["telemetry_reported"] for r in runs), default=0),
    }
    boards = [r["board"] for r in runs if r["board"]]
    span["board"] = parse_status_board(boards[-1] if boards else "")
    span["board_raw"] = boards[-1] if boards else ""
    span["board_agreement"] = {"distinct": len(set(boards)), "of_runs": total}

    states = collections.Counter(b["state"] for b in span["board"])
    broken = [r for r in runs if r["exit_code"] is not None and r["exit_code"] < 0]
    top = collections.Counter(r["exit_code"] for r in broken).most_common(1)
    break_exit = top[0][0] if top else None
    gates = {
        "range": "K0 – K15",
        "core": GATES_CORE,
        "all": GATES_ALL,
        "names": GATE_NAMES,
        "verdict": {
            "ok": states.get("PASS", 0),
            "warn": states.get("WARN", 0),
            "other": states.get("UNKNOWN", 0) + states.get("FAIL", 0),
        },
        "board": span["board"],
        "board_raw": span["board_raw"],
        # Tahta adı doğrudan kapı numarası olan kayıtlar: K0 ✅ -> K0 yeşil.
        "ok_ids": [
            b["label"] for b in span["board"] if b["state"] == "PASS" and b["label"] in GATE_NAMES
        ],
        # K0 dışında kalan tahta adları grup sinyali (kapı numarası değil):
        # "K katmanları ⚠️" -> 16 kutunun tamamı için grup uyarısı.
        "group_warn": [
            b["label"] for b in span["board"] if b["label"] not in GATE_NAMES
        ],
        "break": {
            "kind": "signal" if broken else ("none" if runs else "no_data"),
            "exit_code": break_exit,
            "signal": signal_name(break_exit),
            "runs": len(broken),
            "of_runs": total,
            "share_pct": round(100.0 * len(broken) / total, 1) if total else 0.0,
            "telemetry_reported": len(span["telemetry"]["reported"]),
            "telemetry_columns": span["telemetry"]["columns"],
            "p0": span["severity"]["p0"],
            "p1": span["severity"]["p1"],
            "max_duration_s": span["max_duration_s"],
        },
    }
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
        "gates": gates,
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
