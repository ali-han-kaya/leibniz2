#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_data.py — LeibnizChain kompozisyonunun veri dosyasini uretir.

Kompozisyon kendi sayilarini GÖMMEZ: `public/data/leibniz.json` dosyasini
`delayRender` + `staticFile` ile okur (src/useLeibnizData.ts). Bu script o
dosyayi repodaki gercek kaynaklardan deterministik olarak uretir:

  - _calisma/CIKTI/history.jsonl            → zaman cizelgesi + verdict
                                                 dagilimi + kapi kirilmasi
                                                 + GateChainRuns kompozisyonunun
                                                 koşu-başına 16 kapı durumu
  - _calisma/CIKTI/klayers.runs.json        → LeibnizChain'in K0-K15 gerçek
                                                 PASS/FAIL/SKIP anlık görüntüsü
                                                 (son N verify koşumu)
  - test_id_residual_acceptance_doc.py      → SHA-256 mühür sabitleri

Girdi dosyalarindan biri yoksa fail-closed: sessizce bozuk veriyle sahne
üretmek, uydurma sayı göstermekten kötüdür.

  python3 make_data.py            → public/data/leibniz.json yazar
  python3 make_data.py --stdout   → JSON'u stdout'a basar (testler icin)
  python3 make_data.py --check    → uretilemiyorsa exit 1 (taniklik kapisi)
  python3 make_data.py --allow-missing-data
                                   → history/klayers yoksa SENTINEL veri uretir
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
# verify_delivery.py --klayers-out çıktısı. Workflow son 3 başarılı verify
# koşumunun `klayers` artifact'ını tek dosyada birleştirir; tek dosya da
# (eski yerel indirme) kabul edilir.
KLayers_RUNS = os.path.join(REPO, "_calisma", "CIKTI", "klayers.runs.json")
KLayers = os.path.join(REPO, "_calisma", "CIKTI", "klayers.json")
FROZEN = os.path.join(REPO, "_calisma", "CIKTI", "test_id_residual_acceptance_doc.py")
OUT = os.path.join(HERE, "public", "data", "leibniz.json")

# Kompozisyonun kare bütcesi — src/Root.tsx durationInFrames ile ayni olmak
# ZORUNDA (test_video_data_contract.py bunu dogrular).
FRAMES = 760
FPS = 30
WIDTH = 1280
HEIGHT = 720

# ── İkinci kompozisyon: GateChainRuns (history.jsonl → 16 kapı, koşu koşu) ──
# Kare bütcesi: INTRO + RUNS × PER_RUN + OUTRO. Her koşu 90 karede 16 kapıyı
# soldan sağa yakar (16 × 4 = 64 kare reveal + 26 kare hold).
GATE_HISTORY_RUNS = 6
GATE_HISTORY_INTRO = 45
GATE_HISTORY_PER_RUN = 90
GATE_HISTORY_OUTRO = 45
GATE_HISTORY_FRAMES = (
    GATE_HISTORY_INTRO + GATE_HISTORY_RUNS * GATE_HISTORY_PER_RUN + GATE_HISTORY_OUTRO
)  # 630 = 21.00 sn @ 30 fps

# check_render.py bu tablodan okur — kompozisyon başına kare sayısı TEK kaynaktan.
FRAMES_BY_COMPOSITION = {
    "LeibnizChain": FRAMES,
    "GateChainRuns": GATE_HISTORY_FRAMES,
}

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
# verify_delivery.py LABELS ile aynı (klayers.json yoksa yalnız yedek).
GATE_NAMES = {
    "K0": "Bayat zip taraması",
    "K1": "Dış zip sidecar",
    "K2": "Klasör checksum",
    "K3": "İç zip sidecar",
    "K4": "Manifest",
    "K5": "Script byte-for-byte",
    "K6": "İçerik",
    "K7": "Hijyen",
    "K8": "Z3 sembolik ispat",
    "K9": "Lean reduct-invariance",
    "K10": "Manifest digest",
    "K11": "Config drift",
    "K12": "Plist şablon",
    "K13": "Repro self-test",
    "K14": "Cleanup kaydı",
    "K15": "History sidecar",
}
GATE_STATUSES = {"PASS", "FAIL", "SKIP"}
# GateChainRuns ek olarak WARN taşır (status_board'un ⚠️ işareti gerçek bir
# durumdur) ve kaydı olmayan kapı MISSING kalır — PASS'a yükseltilmez.
GATE_HISTORY_STATUSES = {"PASS", "FAIL", "SKIP", "WARN", "MISSING"}

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
    "🔴": "FAIL",  # U+1F534 — preview_server._STATUS_ICONS'ın GERÇEK fail işareti
    "❌": "FAIL",  # U+274C
    "⛔": "FAIL",
}

# Durum panosundaki GRUP sinyali (“K katmanları …”) — kapı kimliği değildir.
# Pre-commit/Bütçe/Soy hattı kalemleri de kapı değildir ama 16 kutuyu temsil
# etmezler; bu yüzden grup sinyali yalnız katman kaleminden okunur.
GROUP_BOARD_HINT = "katman"

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
                    # Koşunun KENDİ kapı dökümü (varsa). gate_states_for_run
                    # bunu tahtadan önce kullanır; taşımazsak per-gate kanıt
                    # elde olsa bile sahne "KAYIT YOK" çizerdi.
                    "layers": _history_layers(row),
                    "telemetry_reported": sum(
                        1 for c in GATE_TELEMETRY if row.get(c) is not None
                    ),
                }
            )
    if not runs and not allow_missing:
        fail("history.jsonl bos — zaman cizelgesi sahnesi veri alamaz")
    return runs, telemetry


def _read_gate_runs(allow_missing=False):
    """klayers.runs.json (son N koşu) veya tek klayers.json -> koşu listesi.

    Her koşu 16 kapının GERÇEK durumunu taşır. Eksik katman uydurulmaz:
    `MISSING` olarak kalır ve sahnede "KAYIT YOK" çizilir. Dosya hiç yoksa
    --allow-missing-data ile boş liste döner (temiz klon/CI); aksi halde
    fail-closed — video gerçek kapı raporu olmadan çekilmez.
    """
    if os.path.isfile(KLayers_RUNS):
        try:
            with open(KLayers_RUNS, encoding="utf-8") as fh:
                bundle = json.load(fh)
        except (OSError, ValueError) as exc:
            fail("klayers.runs.json okunamadı: %s" % exc)
        raw_runs = bundle.get("runs") if isinstance(bundle, dict) else None
        if not isinstance(raw_runs, list):
            fail("klayers.runs.json 'runs' listesi taşımıyor")
        source = os.path.relpath(KLayers_RUNS, REPO)
    elif os.path.isfile(KLayers):
        try:
            with open(KLayers, encoding="utf-8") as fh:
                single = json.load(fh)
        except (OSError, ValueError) as exc:
            fail("klayers.json okunamadı: %s" % exc)
        raw_runs = [
            {
                "run_id": os.environ.get("LEIBNIZ_GATE_RUN_ID") or None,
                "created_at": os.environ.get("LEIBNIZ_GATE_RUN_AT") or None,
                "klayers": single,
            }
        ]
        source = os.path.relpath(KLayers, REPO)
    else:
        if allow_missing:
            return [], "yok"
        fail(
            "girdi yok: %s (video-render klayers artifact'ını indirir; "
            "yerelde 'scripts/fetch_live_data.sh' çalıştırın)" % KLayers_RUNS
        )

    runs = []
    for raw in raw_runs:
        if not isinstance(raw, dict):
            fail("klayers run kaydı obje değil: %r" % (raw,))
        data = raw.get("klayers")
        if not isinstance(data, dict):
            fail("klayers run 'klayers' objesi taşımıyor")
        layers_obj = data.get("layers")
        if not isinstance(layers_obj, dict) or not layers_obj:
            # anti-cascade placeholder: {ok:false, placeholder:true}
            continue
        layers = []
        for gid in GATES_ALL:
            lyr = layers_obj.get(gid)
            if not isinstance(lyr, dict):
                layers.append(
                    {
                        "id": gid,
                        "label": GATE_NAMES[gid],
                        "status": "MISSING",
                        "ran": False,
                        "findings": 0,
                    }
                )
                continue
            status = str(lyr.get("status") or "").upper()
            if status not in GATE_STATUSES:
                # `ran:false` + status yok = koşmadı; bilinmeyen durum PASS olmaz.
                status = "SKIP" if lyr.get("ran") is False else "MISSING"
            findings = lyr.get("findings") or []
            layers.append(
                {
                    "id": gid,
                    "label": str(lyr.get("label") or GATE_NAMES[gid]).strip(),
                    "status": status,
                    "ran": lyr.get("ran") is not False and status != "MISSING",
                    "findings": len(findings) if isinstance(findings, list) else 0,
                }
            )
        counts = collections.Counter(layer["status"] for layer in layers)
        runs.append(
            {
                "run_id": str(raw.get("run_id") or "") or None,
                "created_at": str(raw.get("created_at") or "") or None,
                "verdict": str(data.get("verdict") or "").upper() or None,
                "layers": layers,
                "counts": {
                    "pass": counts.get("PASS", 0),
                    "fail": counts.get("FAIL", 0),
                    "skip": counts.get("SKIP", 0),
                    "missing": counts.get("MISSING", 0),
                },
            }
        )
    # ISO-8601 created_at kronolojik sıralar; zaman yoksa giriş sırası korunur.
    if any(run["created_at"] for run in runs):
        runs.sort(key=lambda run: (run["created_at"] or "", run["run_id"] or ""))
    return runs, source


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


def _is_gate_id(gid):
    """`K<sayı>` biçimli GERÇEK katman kimliği mi (K0, K16, K21 …)?

    Sahnenin çizdiği zincir K0-K15'tir; arşiv ise K16-K21'i de taşır. Kapsam
    dışı kapılar silinmez: kırılma bloğu gerçek FAIL'leri (ör. K16/K17)
    "kapsam dışı" olarak adlandırabilsin diye korunurlar.
    """
    if not isinstance(gid, str) or len(gid) < 2 or not gid.startswith("K"):
        return False
    return gid[1:].isdigit()


def _history_layers(row):
    """history satırındaki `layers` haritasını {kapı: DURUM} olarak doğrula.

    preview_server her koşunun kapı dökümünü yazar (`layers`); status_board
    bu haritanın özetidir. Tanınmayan durum DÜŞER — uydurma PASS üretilmez.
    `K<sayı>` kimlikleri (K0-K21) korunur; K0-K15 zincirde çizilir, kalanı
    `outside` olarak raporlanır. Harita yoksa `{}` döner ve koşu tahta/grup
    sinyaliyle çizilir (sahne kaynağı `from` alanında gösterir).
    """
    raw = row.get("layers")
    if not isinstance(raw, dict):
        return {}
    out = {}
    for gid, value in raw.items():
        if not _is_gate_id(gid):
            continue
        status = _layer_status(value)
        if status:
            out[gid] = status
    return out


def _layer_status(value):
    """history satırındaki `layers[gate]` değerini kapı durumuna çevirir.

    preview_server `layers` alanını verify JSON'ından olduğu gibi yazar;
    desteklenen biçimler: {"status": "PASS", …} (klayers kaydı) ve düz
    "PASS" dizesi. Tanınmayan değer None döner — uydurma durum üretilmez.
    """
    if isinstance(value, dict):
        status = str(value.get("status") or "").upper()
    elif isinstance(value, str):
        status = value.upper()
    else:
        return None
    return status if status in GATE_STATUSES else None


def _board_gate_states(board):
    """status_board kalemlerinden YALNIZ adı geçen kapıların durumunu çıkarır.

    Tahtada “K katmanları ⚠️” gibi grup sinyali kapı numarası değildir:
    tek bir kapıya dağıtılmaz (uydurma PASS/FAIL olurdu). Yalnız etiketi
    doğrudan kapı kimliği olan kalemler eşlenir; tanınmayan işaret UNKNOWN
    kalır ve kapı durumuna yükseltilmez.
    """
    states = {}
    for item in parse_status_board(board):
        if item["label"] not in GATE_NAMES:
            continue
        if item["state"] in ("PASS", "FAIL", "WARN"):
            states[item["label"]] = item["state"]
    return states


def _board_group_state(board):
    """Tahtadaki KATMAN grup sinyali — tek değer.

    “K katmanları ⚠️” → "WARN". Pre-commit/Bütçe/Soy hattı kalemleri de kapı
    değildir ama 16 kutuyu temsil etmezler; grup sinyali yalnız katman
    kaleminden okunur. Kalem yoksa None: sahne “grup sinyali yok” yazar,
    yeşil varsaymaz.
    """
    for item in parse_status_board(board):
        if item["label"] in GATE_NAMES:
            continue
        if GROUP_BOARD_HINT in item["label"].lower():
            return item["state"]
    return None


def gate_states_for_run(run):
    """Tek history koşusu → 16 kapının GERÇEK durumu.

    Çözümleme sırası (ilk bulunan kazanır):
      1. `run["layers"]` — verify'ın koşu-başına katman haritası (tam kanıt);
      2. `status_board` — YALNIZ tahtada adı geçen kapı (örn. “K0 🔴”);
      3. `MISSING` — kayıt yok. PASS'a yükseltilmez, sahne “KAYIT YOK” çizer.

    `from` alanı kanıtın kaynağını taşır ("layers" | "board" | None) — böylece
    sahnede ve testte “bu yeşil nereden geldi?” sorusu cevaplanabilir.
    """
    layers = run.get("layers")
    layers = layers if isinstance(layers, dict) else {}
    board_states = _board_gate_states(run.get("board"))
    gates = []
    for gid in GATES_ALL:
        status = _layer_status(layers.get(gid))
        source = "layers" if status else None
        if status is None and gid in board_states:
            status, source = board_states[gid], "board"
        gates.append(
            {
                "id": gid,
                "label": GATE_NAMES[gid],
                "status": status or "MISSING",
                "from": source,
            }
        )
    reported = sum(1 for gate in gates if gate["status"] != "MISSING")
    # Kapsam dışı (K16+) gerçek kayıtlar: zincir 16 kutu çizer ama bir koşu
    # K16/K17'de kalabilir. Bunlar silinirse FAIL veren koşu "16/16 raporlu,
    # FAIL yok" görünürdü — veri değil, kapsam hatası olurdu.
    outside = []
    for gid, value in layers.items():
        if gid in GATES_ALL or not _is_gate_id(gid):
            continue
        status = _layer_status(value)
        if status:
            outside.append({"id": gid, "status": status})
    outside.sort(key=lambda item: int(item["id"][1:]))
    return {
        "n": run["n"],
        "ts": run["ts"],
        "day": run["day"],
        "verdict": run["verdict"],
        "exit_code": run["exit_code"],
        "duration_s": run["duration_s"],
        "gates": gates,
        "reported": reported,
        "missing": len(gates) - reported,
        "outside": outside,
        # Kaynak ayrımı: `layers` VAR MI (koşu-başına tam harita) — sahne
        # “tam kayıt” ile “yalnız tahta sinyali”ni ayırt edebilsin.
        "layers_reported": bool(layers),
        "board_raw": run.get("board") or "",
        "board_group_state": _board_group_state(run.get("board")),
    }


def select_break_latest(candidates, states_by_n):
    """Kırılan koşular → (çizilecek kayıt, en yeni kayıt).

    `candidates`: sıfır olmayan çıkışlı koşular (kronolojik). Sinyalle kesilen
    bir koşunun kapı raporu yoktur; animasyon bu yüzden KANITI OLAN en yeni
    kırılmayı çizer. Hiçbir adayda kanıt yoksa en yeni kayıt döner (0/16 —
    uydurma yok). `newest` her zaman gerçekten en yeni kırılmadır.
    """
    newest = states_by_n[candidates[-1]["n"]] if candidates else None
    with_evidence = [states_by_n[run["n"]] for run in candidates
                     if states_by_n[run["n"]]["reported"] > 0]
    latest = with_evidence[-1] if with_evidence else newest
    return latest, newest


def build_gate_history(runs):
    """history koşularının son N'i → GateChainRuns kompozisyonunun verisi.

    Kaynak YALNIZ history.jsonl: her koşu kendi satırındaki kayıtla çizilir;
    başka bir koşunun (ör. klayers.runs.json) durumu buraya karıştırılmaz.
    """
    shown = runs[-GATE_HISTORY_RUNS:]
    records = [gate_states_for_run(run) for run in shown]
    reported = sum(record["reported"] for record in records)
    return {
        "source": os.path.relpath(HISTORY, REPO),
        "composition": "GateChainRuns",
        "frames": GATE_HISTORY_FRAMES,
        "fps": FPS,
        "width": WIDTH,
        "height": HEIGHT,
        "intro_frames": GATE_HISTORY_INTRO,
        "per_run_frames": GATE_HISTORY_PER_RUN,
        "outro_frames": GATE_HISTORY_OUTRO,
        "run_capacity": GATE_HISTORY_RUNS,
        "gate_count": len(GATES_ALL),
        "runs": records,
        "run_count": len(records),
        "data_missing": not records,
        "totals": {
            "reported": reported,
            "missing": len(records) * len(GATES_ALL) - reported,
            "cells": len(records) * len(GATES_ALL),
        },
    }


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
    gate_runs, gate_source = _read_gate_runs(allow_missing=allow_missing)
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
    latest_gate_labels = {}
    if gate_runs:
        latest_gate_labels = {
            layer["id"]: layer["label"]
            for layer in gate_runs[-1]["layers"]
            if layer["status"] != "MISSING"
        }
    gate_names = dict(GATE_NAMES)
    gate_names.update(latest_gate_labels)

    gate_chain = {
        "source": gate_source,
        "runs": gate_runs,
        "run_count": len(gate_runs),
        "data_missing": not gate_runs,
        "complete": bool(gate_runs)
        and all(
            all(layer["status"] != "MISSING" for layer in run["layers"])
            for run in gate_runs
        ),
    }

    # Koşu-başına kapı durumları TEK kez çözülür: by_gate dağılımı, son
    # koşunun `statuses` dökümü ve kırılma bloğu aynı kaynaktan okur (üç ayrı
    # çözümleme aynı satır için farklı sonuç veremez).
    states_by_n = {run["n"]: gate_states_for_run(run) for run in runs}
    # Kırılma animasyonunun kapı-başına kanıtı: kırılan koşuların KENDİ kapı
    # dökümü (varsa `layers`, yoksa tahtada adı geçen kapı, yoksa MISSING).
    # Uydurma yok: kayıt olmayan kapı "missing" sayılır.
    broken_runs = [r for r in runs
                   if r["exit_code"] is not None and r["exit_code"] < 0]
    by_gate = {}
    for run in runs:
        for gate in states_by_n[run["n"]]["gates"]:
            slot = by_gate.setdefault(
                gate["id"], {"pass": 0, "fail": 0, "skip": 0,
                             "warn": 0, "missing": 0})
            slot[gate["status"].lower()] = slot.get(
                gate["status"].lower(), 0) + 1

    # Kırılma = sıfır olmayan çıkış. Sinyalle kesilen koşu raporunu
    # ÜRETEMEZ (süreç kapıları yazmadan öldü) — animasyon bu yüzden kapı
    # kanıtı OLAN en yeni kırılmayı çizer, en yeni kırılmayı da ayrıca ve
    # dürüstçe adlandırır (`newest`). Kayıt yoksa PASS/FAIL uydurulmaz.
    break_candidates = [r for r in runs
                        if r["exit_code"] is not None and r["exit_code"] != 0]

    def _break_record(record):
        return {
            "n": record["n"],
            "ts": record["ts"],
            "exit_code": record["exit_code"],
            "signal": signal_name(record["exit_code"]),
            "gates": record["gates"],
            "failed": [g["id"] for g in record["gates"]
                       if g["status"] == "FAIL"],
            # K0-K15 dışında kalan gerçek kapı kayıtları (K16+) — kırılma
            # gerçekten oradaysa animasyon bunu söyler, gizlemez.
            "outside": record.get("outside") or [],
            "outside_failed": [g["id"] for g in (record.get("outside") or [])
                               if g["status"] == "FAIL"],
            "reported": record["reported"],
            "layers_reported": record["layers_reported"],
        }

    latest_state, newest_break = select_break_latest(break_candidates, states_by_n)
    latest_break = _break_record(latest_state) if latest_state else None

    gates = {
        "range": "K0 – K15",
        "core": GATES_CORE,
        "all": GATES_ALL,
        "names": gate_names,
        "verdict": {
            "ok": states.get("PASS", 0),
            "warn": states.get("WARN", 0),
            "other": states.get("UNKNOWN", 0) + states.get("FAIL", 0),
        },
        "board": span["board"],
        "board_raw": span["board_raw"],
        # Son koşunun GERÇEK kapı dökümü (16 kapı) + kanıt kaynağı.
        "statuses": states_by_n[runs[-1]["n"]]["gates"] if runs else [],
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
            # Kapı-başına kırılma dökümü (koşu sayıları) + kapı kanıtı olan
            # en yeni kırılmanın kendi durumları. İkisi de history
            # satırlarından türer; `newest` en yeni kırılmayı (kanıtı
            # olmasa da) adlandırır — animasyon ikisini ayrı gösterir.
            "by_gate": by_gate,
            "latest": latest_break,
            "newest": (
                {
                    "n": newest_break["n"],
                    "ts": newest_break["ts"],
                    "exit_code": newest_break["exit_code"],
                    "signal": signal_name(newest_break["exit_code"]),
                    "reported": newest_break["reported"],
                }
                if newest_break is not None else None
            ),
            "latest_is_newest": (
                latest_break is None
                or (newest_break is not None
                    and latest_break["n"] == newest_break["n"])
            ),
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
        "gate_chain": gate_chain,
        # İkinci kompozisyon (GateChainRuns): koşu-başına 16 kapı, yalnız
        # history.jsonl satırlarından — klayers anlık görüntüsü karışmaz.
        "gate_history": build_gate_history(runs),
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
