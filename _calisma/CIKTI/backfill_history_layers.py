#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_history_layers.py — arşiv satırlarına koşunun GERÇEK kapı dökümünü
geri doldur (satırın KENDİ run kaydındaki verify raporundan).

Neden: `layers` (K0-K21) history.jsonl sözleşmesine 2026-10-17'de girdi; ondan
önce yazılan satırlar yalnız `status_board` özetini ("K0 🔴 · K katmanları 🔴")
taşıyor. Durum panosunun ARKASINDAKİ kapı sonuçları kaybolmadı: her koşunun
`runs/run-<ts>.json` kaydı, verify'ın `--json` çıktısını (`stdout`) ve dolayısıyla
`layers` haritasını saklıyor. Video'nun kırılma animasyonu kapı başına GERÇEK
veri gösterebilsin diye bu satırlar aynı koşunun kendi raporundan tamamlanır.

Fail-closed kurallar (hiçbiri uydurma üretmez):

  - Yalnız AYNI `ts` değerini taşıyan run kaydı eşleşir. Başka koşunun
    kapıları bu satıra yazılmaz.
  - Durumlar `preview_server._normalize_layers` ile doğrulanır (tek kaynak);
    tanınmayan anahtar/durum DÜŞER. Normalize sonucu boşsa satır dokunulmaz.
  - Satırda zaten `layers` varsa DOKUNULMAZ; run kaydı farklı bir harita
    taşıyorsa bu bir `conflict` olarak raporlanır (sunucunun yazdığı veri
    arşivin otoritesidir).
  - Kayıt yok / raporda `layers` yok → satır olduğu gibi kalır (`missing_*`).
  - Yazım atomiktir (mkstemp + replace) ve `history.jsonl.sha256` sidecar'ı
    yeniden üretilir — K15 bu sidecar'ı fail-closed doğrular. Değişmeyen
    satırların BAYTLARI korunur (yalnız tamamlanan satır yeniden serileşir).
  - Yazımdan sonra sidecar digest'i dosyadan yeniden ölçülür; tutmazsa exit 1.

Bu araç ÇEVRİMDIŞI bir onarım yoludur: `preview_server.persist_history`
çalışırken tek yazıcıdır (test_history_single_writer bu tekilliği pinler).
Bu yüzden yazım, planın okuduğu arşivin digest'ine bağldır: arada sunucu bir
satır eklerse (mtime/boyut/digest değişir) `apply` yazMAZ ve exit 1 verir —
son koşu sessizce ezilmez.

Kullanım:

  python3 backfill_history_layers.py               # plan (dry-run), insan özeti
  python3 backfill_history_layers.py --json        # plan, TEK JSON dokümanı
  python3 backfill_history_layers.py --apply       # arşivi yaz
  python3 backfill_history_layers.py --apply --json

Yollar __file__'ten türer (sabit gömülü yol yok); `--history` / `--runs-dir`
ile değiştirilebilir (testler bunu kullanır).
"""

import argparse
import glob
import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_HISTORY = os.path.join(REPO, "_calisma", "CIKTI", "history.jsonl")
DEFAULT_RUNS_DIR = os.path.join(REPO, "_calisma", "CIKTI", "runs")


def _normalize(raw):
    """`layers` haritasını preview_server'ın kuralıyla doğrula (tek kaynak)."""
    import preview_server as ps
    return ps._normalize_layers(raw)


def _layers_from_json_blob(text):
    """stdout'un tamamı ya da son `{...}` bloğu → `layers` (yoksa None)."""
    if not text or not text.strip():
        return None
    try:
        blob = json.loads(text)
    except ValueError:
        start, end = text.rfind("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            blob = json.loads(text[start:end + 1])
        except ValueError:
            return None
    if not isinstance(blob, dict):
        return None
    return blob.get("layers")


def layers_of_record(record):
    """Run kaydı → normalize edilmiş GERÇEK kapı haritası (yoksa {}).

    Önce kaydın kendi `layers` alanı, sonra `stdout` içindeki verify JSON'ı.
    Tek bir kaynak: aynı koşunun raporu; başka koşudan veri karışmaz.
    """
    if not isinstance(record, dict):
        return {}
    raw = record.get("layers")
    normalized = _normalize(raw) if isinstance(raw, dict) else {}
    if normalized:
        return normalized
    return _normalize(_layers_from_json_blob(record.get("stdout") or ""))


def load_run_records(runs_dir):
    """`runs/run-*.json` → {ts: kayıt}. Aynı ts iki kez görülürse sonuncusu
    kazanır ve çağıran taraf `duplicates` ile uyarılır."""
    records = {}
    duplicates = []
    for path in sorted(glob.glob(os.path.join(runs_dir, "run-*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                record = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        ts = record.get("ts")
        if not isinstance(ts, str) or not ts:
            continue
        if ts in records:
            duplicates.append(ts)
        records[ts] = record
    return records, duplicates


def plan(history_path, runs_dir):
    """Arşiv + run kayıtları → (satırlar, ham satırlar, rapor).

    Saf okuma: hiçbir dosya yazılmaz. `rows[i]["raw"]` değişmeyen satırların
    baytlarını korumak için tutulur.
    """
    records, duplicates = load_run_records(runs_dir)
    rows = []
    report = {
        "history": history_path,
        "runs_dir": runs_dir,
        "records": len(records),
        "duplicate_ts": duplicates,
        "rows": 0,
        "already": 0,
        "filled": 0,
        "missing_record": 0,
        "missing_report": 0,
        "conflict": 0,
        "invalid_json": 0,
        "filled_rows": [],
        "conflicts": [],
    }
    if not os.path.isfile(history_path):
        report["error"] = "arşiv yok: %s" % history_path
        return rows, report

    with open(history_path, "rb") as fh:
        baseline = fh.read()
    report["baseline_sha256"] = hashlib.sha256(baseline).hexdigest()

    with open(history_path, encoding="utf-8") as fh:
        raw_lines = [ln.rstrip("\n") for ln in fh if ln.strip()]

    for idx, raw in enumerate(raw_lines, 1):
        report["rows"] += 1
        try:
            row = json.loads(raw)
        except ValueError:
            report["invalid_json"] += 1
            rows.append({"n": idx, "raw": raw, "row": None, "action": "invalid"})
            continue
        if not isinstance(row, dict):
            report["invalid_json"] += 1
            rows.append({"n": idx, "raw": raw, "row": None, "action": "invalid"})
            continue

        existing = _normalize(row.get("layers")) if isinstance(
            row.get("layers"), dict) else {}
        ts = row.get("ts")
        record = records.get(ts) if isinstance(ts, str) else None
        found = layers_of_record(record) if record is not None else {}

        action = "already" if existing else (
            "missing_record" if record is None else
            "missing_report" if not found else "fill")

        if existing and found and existing != found:
            action = "conflict"
            report["conflict"] += 1
            report["conflicts"].append({"n": idx, "ts": ts,
                                        "keys": sorted(set(existing) | set(found))})
        elif action == "already":
            report["already"] += 1
        elif action == "missing_record":
            report["missing_record"] += 1
        elif action == "missing_report":
            report["missing_report"] += 1

        if action == "fill":
            row = dict(row)
            row["layers"] = found
            report["filled"] += 1
            failed = sorted(gid for gid, entry in found.items()
                            if entry.get("status") == "FAIL")
            report["filled_rows"].append({
                "n": idx,
                "ts": ts,
                "gates": len(found),
                "failed": failed,
                "exit_code": row.get("exit_code"),
            })
        rows.append({"n": idx, "raw": raw, "row": row, "action": action})

    return rows, report


def _write_atomic(path, data):
    """tmp (aynı dizin, benzersiz ad) + rename — yarım dosya okunmaz."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=os.path.basename(path) + ".tmp.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def render(rows):
    """Değişen satırları yeniden serileştir; diğerlerinin baytları korunur."""
    out = []
    for item in rows:
        if item["action"] == "fill":
            out.append(json.dumps(item["row"], ensure_ascii=False))
        else:
            out.append(item["raw"])
    return "\n".join(out) + "\n"


def apply(history_path, rows, report):
    """Arşivi atomik yaz + sidecar'ı yeniden üret; digest'i yeniden ölçer.

    Fail-closed eşzamanlılık: planın okuduğu arşiv yazımdan önce değişirse
    (sunucu yeni satır yazdı) `apply` DURUR — aksi hâlde okunan anlık görüntü,
    yeni satırı sessizce silen bir "lost update" olurdu.
    """
    content = render(rows)
    before = None
    if os.path.isfile(history_path):
        with open(history_path, "rb") as fh:
            current = fh.read()
        before = hashlib.sha256(current).hexdigest()
        expected = report.get("baseline_sha256")
        if expected and before != expected:
            raise SystemExit(
                "backfill: FAIL — arşiv plan sırasında değişti "
                "(beklenen %s…, bulunan %s…); yazılmadı"
                % (expected[:12], before[:12]))
    _write_atomic(history_path, content)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    sidecar = history_path + ".sha256"
    _write_atomic(sidecar, "%s  %s\n" % (digest, os.path.basename(history_path)))

    with open(history_path, "rb") as fh:
        measured = hashlib.sha256(fh.read()).hexdigest()
    with open(sidecar, encoding="utf-8") as fh:
        recorded = (fh.read().split() or [""])[0]
    if measured != digest or recorded != digest:
        raise SystemExit("backfill: FAIL — sidecar doğrulanamadı (dosya=%s sidecar=%s)"
                         % (measured, recorded))
    report["applied"] = True
    report["sha256_before"] = before
    report["sha256_after"] = digest
    report["sidecar"] = os.path.basename(sidecar)
    return report


def summarize(report, stream):
    print("backfill_history_layers: %d satır · %d dolduruldu · %d zaten dolu · "
          "%d kayıt yok · %d rapor yok · %d çakışma"
          % (report["rows"], report["filled"], report["already"],
             report["missing_record"], report["missing_report"],
             report["conflict"]), file=stream)
    if report.get("filled_rows"):
        for item in report["filled_rows"]:
            print("  + #%d %s exit=%s kapı=%d FAIL=%s"
                  % (item["n"], item["ts"], item["exit_code"], item["gates"],
                     ",".join(item["failed"]) or "-"), file=stream)
    if report.get("applied"):
        print("  yazıldı · sha256 %s" % report["sha256_after"][:16], file=stream)
    else:
        print("  kuru koşum (yazmak için --apply)", file=stream)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history", default=DEFAULT_HISTORY)
    ap.add_argument("--runs-dir", default=DEFAULT_RUNS_DIR)
    ap.add_argument("--apply", action="store_true",
                    help="arşivi yaz (varsayılan: yalnız plan)")
    ap.add_argument("--json", action="store_true",
                    help="stdout'a TEK JSON dokümanı bas (tanı stderr'de)")
    args = ap.parse_args(argv)

    rows, report = plan(args.history, args.runs_dir)
    if report.get("error") and not report["rows"]:
        summarize(report, sys.stderr)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    if args.apply and report["filled"]:
        apply(args.history, rows, report)
    elif args.apply:
        report["applied"] = False

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        summarize(report, sys.stderr)
    else:
        summarize(report, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
