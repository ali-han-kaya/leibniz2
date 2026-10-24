#!/usr/bin/env bash
# fetch_live_data.sh — videoyu GERÇEK repo/CI verisiyle besler.
#
# İki girdi indirir (ikisi de best-effort, biri diğerini bloke etmez):
#   _calisma/CIKTI/history.jsonl       ← son başarılı verify run-history
#   _calisma/CIKTI/klayers.runs.json   ← son N başarılı verify `klayers`
#
# `klayers.runs.json` yoksa make_data.py --allow-missing-data boş kapı
# zinciri üretir; sahne "K katman raporu yok" der, PASS uydurmaz.
#
# Kullanım:
#   bash _calisma/video/scripts/fetch_live_data.sh
#   LEIBNIZ_GATE_RUNS=5 bash _calisma/video/scripts/fetch_live_data.sh
set -euo pipefail

VIDEO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$VIDEO_DIR/../.." && pwd)"
CIKTI="$REPO_ROOT/_calisma/CIKTI"
OUT_RUNS="$CIKTI/klayers.runs.json"
HISTORY="$CIKTI/history.jsonl"
RUN_COUNT="${LEIBNIZ_GATE_RUNS:-3}"

if ! command -v gh >/dev/null 2>&1; then
  echo "fetch_live_data: gh yok — veri indirilemedi" >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "fetch_live_data: gh oturumu yok — 'gh auth login' gerekli" >&2
  exit 1
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/leibniz-video-live.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

ok=0

# 1) Zaman çizelgesi + kırılma + durum tahtası: en yeni başarılı koşu.
latest_id="$(gh run list --workflow verify.yml --status success --limit 1 \
  --json databaseId --jq '.[0].databaseId')"
if [ -n "$latest_id" ] && [ "$latest_id" != "null" ]; then
  if gh run download "$latest_id" --name run-history --dir "$TMP/run-history"; then
    if [ -s "$TMP/run-history/history.jsonl" ]; then
      artifact_rows=$(wc -l < "$TMP/run-history/history.jsonl" | tr -d ' ')
      local_rows=0
      if [ -s "$HISTORY" ]; then
        local_rows=$(wc -l < "$HISTORY" | tr -d ' ')
      fi
      # CI artifact'ı tek koşu taşıyabilir; yereldeki 100 koşuluk geçmişi
      # daha küçük bir dosyayla EZME. Daha zengin kayıt korunur.
      if [ "$artifact_rows" -ge "$local_rows" ]; then
        cp "$TMP/run-history/history.jsonl" "$HISTORY"
        if [ -s "$TMP/run-history/history.jsonl.sha256" ]; then
          cp "$TMP/run-history/history.jsonl.sha256" "$HISTORY.sha256"
        elif command -v sha256sum >/dev/null 2>&1; then
          sha256sum "$HISTORY" > "$HISTORY.sha256"
        else
          shasum -a 256 "$HISTORY" > "$HISTORY.sha256"
        fi
        echo "fetch_live_data: history ← verify #$latest_id ($artifact_rows koşu)"
      else
        echo "fetch_live_data: yerel history ($local_rows koşu) korundu" >&2
      fi
      ok=1
    fi
  fi
fi

# 2) K0-K15 gerçek durumları: son N başarılı koşunun klayers artifact'ı.
gh run list --workflow verify.yml --status success --limit "$RUN_COUNT" \
  --json databaseId,createdAt \
  --jq '.[] | [.databaseId, .createdAt] | @tsv' > "$TMP/runs.tsv"

# gh en yeniyi önce döndürür; sahnede kronolojik sıra istiyoruz.
sort -k2 "$TMP/runs.tsv" -o "$TMP/runs.tsv"

while IFS=$'\t' read -r run_id _; do
  [ -n "$run_id" ] || continue
  if gh run download "$run_id" --name klayers --dir "$TMP/klayers-$run_id"; then
    if [ -s "$TMP/klayers-$run_id/klayers.json" ]; then
      echo "fetch_live_data: klayers ← verify #$run_id"
    fi
  else
    echo "fetch_live_data: klayers #$run_id indirilemedi (atlandı)" >&2
  fi
done < "$TMP/runs.tsv"

python3 - "$TMP" "$OUT_RUNS" <<'PY'
import json
import os
import pathlib
import sys

tmp = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])
runs = []
tsv = tmp / "runs.tsv"
for line in tsv.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    run_id, created_at = line.split("\t", 1)
    path = tmp / ("klayers-" + run_id) / "klayers.json"
    if not path.is_file():
        continue
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        continue
    if not isinstance(data.get("layers"), dict) or not data["layers"]:
        continue
    runs.append(
        {"run_id": run_id, "created_at": created_at, "klayers": data}
    )

if not runs:
    print("fetch_live_data: hiçbir klayers artifact'ı okunamadı", file=sys.stderr)
    raise SystemExit(1)
out.write_text(
    json.dumps({"runs": runs}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print("fetch_live_data: klayers.runs.json ← %d koşu (%s)"
      % (len(runs), ", ".join(r["run_id"] for r in runs)))
PY

ok=1

if [ "$ok" -ne 1 ]; then
  echo "fetch_live_data: hiçbir girdi indirilemedi" >&2
  exit 1
fi
