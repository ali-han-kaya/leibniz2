#!/usr/bin/env bash
# =============================================================================
# dashboard_devices_smoke.sh — dashboard CIHAZ-paritesi smoke'unun TEK giriş
# noktası (Chromium/CDP + WebKit/Safari katmanları).
#
# Neden var: iki cihaz katmanı bugüne kadar YALNIZ PR/push koşumunda
# (verify.yml `dashboard-smoke` + `webkit-smoke`) kanıt üretiyordu. Panelin
# cihaz yüzeyindeki drift — statik varlık 404'ü, CSP/MIME değişimi, seçici
# kayması, SSE kopması — bu yüzden ancak BİR SONRAKİ PR'da kırmızıya
# dönüyordu; yani drift, kendisi PR'ı bloke ettikten sonra öğreniliyordu.
# `dashboard-devices-drift.yml` bu script'i haftalık cron'da çağırır; akış
# YAML'da yeniden yazılmaz (test_gated_schedules K1 parite kuralı).
#
# Katmanlar:
#   chromium — test_preview_interaction_cdp.py   (hover/filtre/lightbox)
#              test_dashboard_playwright_smoke.py (SSE + CSP render)
#              test_dashboard_keyboard_nav.py     (klavye kapsamı)
#   webkit   — test_dashboard_webkit_smoke.py    (Safari paritesi, safedriver)
#
# SKIP semantiği (docker_security_smoke.sh ile aynı sözleşme):
#   Tarayıcı/sürücü bu ortamda YOKSA katman SKIP döner (exit 0) — yerel
#   makinede doğru davranış. CI'da SKIP kanıt DEĞİLDİR: workflow'un assert
#   adımı `verdict=PASS` arar, aksi halde job KIRMIZI olur. Aksi halde
#   eksik kurulumlu bir runner haftalık "yeşil ama kanıtsız" koşum üretir ve
#   cron'un tek amacı (erken görünürlük) sessizce boşalır.
#
# Kullanım:
#   bash _calisma/CIKTI/dashboard_devices_smoke.sh                  # all
#   bash _calisma/CIKTI/dashboard_devices_smoke.sh --layer chromium
#   bash _calisma/CIKTI/dashboard_devices_smoke.sh --layer webkit
#   bash _calisma/CIKTI/dashboard_devices_smoke.sh --report-dir /tmp/dd
#
# Ortam değişkenleri:
#   ROOT         repo kökü (varsayılan: script'in ../../)
#   PY           koşumu yapacak python (varsayılan: repo venv → python3)
#   REPORT_DIR   rapor dizini (varsayılan: $ROOT/.freebuff/sim/dashboard_devices)
#
# Çıktı sözleşmesi (workflow grep ile doğrular):
#   layer=chromium verdict=PASS|FAIL|SKIP
#   layer=webkit   verdict=PASS|FAIL|SKIP
#   verdict=PASS|FAIL|SKIP
# Exit: 0 = PASS ya da tüm katmanlar SKIP; 1 = herhangi bir katman FAIL;
#       2 = kullanım/ortam hatası.
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
CIKTI="$ROOT/_calisma/CIKTI"
REPORT_DIR="${REPORT_DIR:-$ROOT/.freebuff/sim/dashboard_devices}"
REPORT_FILE=""

say() {
  printf '%s\n' "$*"
  printf '%s\n' "$*" >> "$REPORT_FILE"
}
err() { printf 'HATA: %s\n' "$*" >&2; }

# Python çözümü — dashboard_smoke.sh ile aynı öncelik: açık PY, repo venv'leri,
# sonra sistem python3 (CI runner'ında playwright pip ile kurulu olan budur).
resolve_python() {
  if [ -n "${PY:-}" ]; then printf '%s' "$PY"; return 0; fi
  if [ -x "$ROOT/_calisma/.venv_z3/bin/python3" ]; then
    printf '%s' "$ROOT/_calisma/.venv_z3/bin/python3"; return 0
  fi
  if [ -x "$ROOT/_calisma/.venv/bin/python3" ]; then
    printf '%s' "$ROOT/_calisma/.venv/bin/python3"; return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3; return 0
  fi
  return 1
}

# Chromium yoklaması: playwright paketi + indirilmiş chromium ikilisi. Test
# dosyalarının kendi skip ölçütüyle aynı (var olmayan ikilide test SKIP eder;
# burada SKIP'i ÖNCEDEN ve adıyla söylüyoruz ki CI'da kırmızıya çevrilebilsin).
chromium_probe() {
  "$PY" - >/dev/null 2>&1 <<'PROBE'
import os
import sys
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    exe = p.chromium.executable_path
sys.exit(0 if os.path.isfile(exe) else 1)
PROBE
}

# WebKit yoklaması: testin KENDİ arayıcısı (safedriver aday listesi tek
# kaynakta kalsın — burada ikinci bir liste kopyalanmaz).
webkit_probe() {
  PYTHONPATH="$CIKTI${PYTHONPATH:+:$PYTHONPATH}" "$PY" - >/dev/null 2>&1 <<'PROBE'
import sys
import test_dashboard_webkit_smoke as m

sys.exit(0 if m.find_safedriver() else 1)
PROBE
}

LAYER_VERDICT=""

# run_layer <ad> <probe-fn> <modül...>
run_layer() {
  local layer="$1" probe="$2"
  shift 2
  local report="$REPORT_DIR/$layer.log"

  if ! "$probe"; then
    say "SKIP: $layer katmanı bu ortamda koşulamaz (tarayıcı/sürücü yok) — kanıt üretilmedi"
    say "layer=$layer verdict=SKIP"
    LAYER_VERDICT=SKIP
    return 0
  fi

  say "── $layer katmanı: $*"
  ( cd "$ROOT" && "$PY" -m unittest -v "$@" ) > "$report" 2>&1
  local rc=$?
  cat "$report"
  cat "$report" >> "$REPORT_FILE"
  if [ "$rc" -ne 0 ]; then
    say "layer=$layer verdict=FAIL (rc=$rc, rapor: $report)"
    LAYER_VERDICT=FAIL
    return 1
  fi
  say "layer=$layer verdict=PASS"
  LAYER_VERDICT=PASS
  return 0
}

usage() {
  printf 'kullanım: %s [--layer chromium|webkit|all] [--report-dir DIR]\n' \
    "$(basename "$0")"
}

main() {
  local layer="all"
  while [ $# -gt 0 ]; do
    case "$1" in
      --layer)      layer="${2:-}"; shift 2 || { usage; return 2; } ;;
      --report-dir) REPORT_DIR="${2:-}"; shift 2 || { usage; return 2; } ;;
      -h|--help)    usage; return 0 ;;
      *)            err "bilinmeyen argüman: $1"; usage; return 2 ;;
    esac
  done
  case "$layer" in
    chromium|webkit|all) ;;
    *) err "geçersiz --layer: ${layer:-<boş>} (chromium|webkit|all)"; return 2 ;;
  esac

  # --report-dir sonrası: rapor dosyası dizinden TÜRETİLİR (üstteki sabit
  # hesap argümanı görmüyordu; yanlış dizine yazıp sessizce kaybolurdu).
  REPORT_FILE="$REPORT_DIR/dashboard_devices_report.txt"
  mkdir -p "$REPORT_DIR" || { err "rapor dizini açılamadı: $REPORT_DIR"; return 2; }
  : > "$REPORT_FILE"
  PY="$(resolve_python)" || { err "python3 bulunamadı"; return 2; }

  say "--- dashboard_devices_smoke — $(date -u +%Y-%m-%dT%H:%M:%SZ) ---"
  say "python: $PY"
  say "root:   $ROOT"
  say "layer:  $layer"
  say ""

  # FAIL tek katmanda da hüküm verir; kalan katman yine koşar ki tek koşumda
  # iki kanıt birden toplansın (biri diğerini maskelemesin).
  local failed=0 ran=0 skipped=0
  if [ "$layer" = "all" ] || [ "$layer" = "chromium" ]; then
    ran=$((ran + 1))
    run_layer chromium chromium_probe \
      _calisma.CIKTI.test_preview_interaction_cdp \
      _calisma.CIKTI.test_dashboard_playwright_smoke \
      _calisma.CIKTI.test_dashboard_keyboard_nav || failed=1
    [ "$LAYER_VERDICT" = "SKIP" ] && skipped=$((skipped + 1))
  fi
  if [ "$layer" = "all" ] || [ "$layer" = "webkit" ]; then
    ran=$((ran + 1))
    run_layer webkit webkit_probe \
      _calisma.CIKTI.test_dashboard_webkit_smoke || failed=1
    [ "$LAYER_VERDICT" = "SKIP" ] && skipped=$((skipped + 1))
  fi

  say ""
  if [ "$failed" -ne 0 ]; then
    say "verdict=FAIL"
    err "en az bir cihaz katmanı kırmızı (rapor: $REPORT_FILE)"
    return 1
  fi
  if [ "$skipped" -eq "$ran" ]; then
    say "verdict=SKIP"
    err "hiçbir katman koşulamadı (SKIP kanıt değildir) — rapor: $REPORT_FILE"
    return 0
  fi
  say "verdict=PASS"
  return 0
}

main "$@"
