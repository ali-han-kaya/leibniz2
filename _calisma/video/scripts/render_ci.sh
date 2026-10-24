#!/usr/bin/env bash
# render_ci.sh — LeibnizChain mp4'sini CI'da (ve yerelde) uçtan uca üretir.
#
# Neden ayrı sürücü: temiz klonda `_calisma/CIKTI/history.jsonl` YOKTUR
# (gitignored çalışma-zamanı verisi). `npm run render` bu durumda fail-closed
# durur; CI'da render'ın amacı boru hattını kanıtlamaktır, sahte veri üretmek
# değil. `make_data.py --allow-missing-data` yoksa açıkça sentinel üretir ve
# bu dosya (render_mode.txt) hangi modun kullanıldığını artefakta taşır.
#
# Çıktılar:
#   out/leibniz-chain.mp4  — LeibnizChain render'ı (repoda tutulmaz)
#   out/render_report.json — check_render.py --json (kare/süre/bayt/sha256)
#   out/render_check.txt   — insan-okur PASS/FAIL satırları
#   out/render_mode.txt    — history | sentinel
#   out/gate-chain.mp4     — GateChainRuns render'ı (ikinci kompozisyon)
#   out/gate_render_report.json / gate_render_check.txt — onun sözleşme ölçümü
#
# İki kompozisyon da HER koşuda render edilir: ölçülmeyen kompozisyon
# sessizce çürür (kare bütçesi kayar, tip hatası render'da gizlenir).
set -euo pipefail

VIDEO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$VIDEO_DIR/../.." && pwd)"
cd "$VIDEO_DIR"

mkdir -p out

HISTORY="$REPO_ROOT/_calisma/CIKTI/history.jsonl"
if [ -s "$HISTORY" ]; then
  DATA_MODE="history"
else
  DATA_MODE="sentinel"
fi
printf '%s\n' "$DATA_MODE" > out/render_mode.txt
echo "render_ci: data_mode=$DATA_MODE"

# Tarayıcıyı render'dan ÖNCE indir: indirme arızası render hatası gibi
# görünmesin (Remotion gerekirse kendisi de indirir).
npx --no-install remotion browser ensure

# data:ci = make_data.py --allow-missing-data; history varsa yine gerçek veri.
npm run render:ci

python3 check_render.py out/leibniz-chain.mp4 --json > out/render_report.json \
  2> out/render_check.txt
cat out/render_check.txt

# İkinci kompozisyon: history.jsonl → koşu-başına 16 kapı (K0–K15).
# Kare bütçesi 630; check_render bunu make_data.FRAMES_BY_COMPOSITION'dan okur.
npm run render:ci:gates

python3 check_render.py out/gate-chain.mp4 --composition GateChainRuns \
  --json > out/gate_render_report.json 2> out/gate_render_check.txt
cat out/gate_render_check.txt
