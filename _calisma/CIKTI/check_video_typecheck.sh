#!/usr/bin/env bash
# check_video_typecheck.sh — _calisma/video (LeibnizChain/Remotion) icin
# tsc --noEmit kapisi.
#
# check_dashboard_typecheck.sh ile Ayni sozlesme (setup-pre-commit
# "commit-ani typecheck" hedefinin zincir-uyarlamasi, Husky yerine mevcut
# pre-commit zinciri):
#   - node_modules/tsconfig yoksa SKIP (exit 0) — ortam-bagimli kapi ortam
#     yoksa blokelemez (zincirin SKIP-kulturu).
#   - node_modules + tsconfig VARSA fail-closed: herhangi bir tip-hatasi
#     commit'i blokeler (READ-ONLY: yalnizca --noEmit).
#   - uretilen veri dosyasi (public/data/leibniz.json) kaynak degildir; tip
#     kapisi ona dokunmaz, veri uretimi make_data.py'nin isi.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
VIDEO="$REPO/_calisma/video"

if [ ! -x "$VIDEO/node_modules/.bin/tsc" ] || [ ! -f "$VIDEO/tsconfig.json" ]; then
  echo "check-video-typecheck: tsc/tsconfig yok — SKIP"
  exit 0
fi

cd "$VIDEO"
node_modules/.bin/tsc --noEmit
echo "check-video-typecheck: OK"
