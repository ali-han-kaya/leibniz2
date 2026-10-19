#!/usr/bin/env bash
# =============================================================================
# start_preview.sh — Live CI Dashboard için launchd start + readiness
#
# Kurulum zincirini tek yerde toplar:
#   1. update_preview.sh --bootstrap (mirror + HTML + plist; varsayılan)
#   2. update_preview.sh --start     (yalnız launchctl bootstrap/kickstart)
#   3. /api/health + /preview.html   (iki endpoint 200 olmadan başarı sayılmaz)
#
# Güvenlik: port 8000'i dinleyen süreci sahiplenmez; rastgele port eşleme
# PID'lerini öldürmez. Mevcut LaunchAgent yalnızca update_preview.sh --start tarafından
# bootout/bootstrap edilir. Başka bir servis portu kullanıyorsa timeout ile
# fail-closed durulur ve o servis zorla sonlandırılmaz.
#
# Kullanım:
#   bash _calisma/CIKTI/start_preview.sh
#   bash _calisma/CIKTI/start_preview.sh --no-rebuild
#   PREVIEW_HEALTH_TIMEOUT=60 bash _calisma/CIKTI/start_preview.sh --no-rebuild
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="${PREVIEW_LABEL:-com.freebuff.preview-leibniz2}"
PORT=8000
MAX_WAIT="${PREVIEW_HEALTH_TIMEOUT:-30}"
REBUILD=true
HEALTH_URL="http://127.0.0.1:${PORT}/api/health"
PREVIEW_URL="http://127.0.0.1:${PORT}/preview.html"
LOG_BASENAME="${LABEL#com.freebuff.}"
LOG_PATH="${HOME}/Library/Logs/com.freebuff/${LOG_BASENAME}.log"

say() { printf '[start_preview] %s\n' "$*"; }
err() { printf '[start_preview] HATA: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Kullanım: start_preview.sh [--no-rebuild]

  --no-rebuild  Yalnız launchd start + HTTP readiness; mirror/HTML/plist
                hazırlanmış varsayılır.
  --help       Bu yardım metnini gösterir.

Ortam:
  PREVIEW_HEALTH_TIMEOUT  Hazır olma bekleme süresi (varsayılan: 30 saniye)
  PREVIEW_LABEL           LaunchAgent label (varsayılan: com.freebuff.preview-leibniz2)
EOF
}

for arg in "$@"; do
  case "$arg" in
    --no-rebuild) REBUILD=false ;;
    --help|-h) usage; exit 0 ;;
    *) err "bilinmeyen argüman: $arg (--help)" ;;
  esac
done

case "$MAX_WAIT" in
  ''|*[!0-9]*) err "PREVIEW_HEALTH_TIMEOUT pozitif tam sayı olmalı: $MAX_WAIT" ;;
esac
[ "$MAX_WAIT" -gt 0 ] || err "PREVIEW_HEALTH_TIMEOUT 0'dan büyük olmalı"

command -v curl >/dev/null 2>&1 || err "curl bulunamadı — readiness doğrulanamıyor"
[ -f "$SCRIPT_DIR/update_preview.sh" ] || err "update_preview.sh yok: $SCRIPT_DIR/update_preview.sh"

# 1) İsteğe bağlı hazırlık: mirror + build + plist. Bu adım launchd'ye
# yüklemez; --start aşağıdaki ikinci adımda yapılır.
if $REBUILD; then
  say "hazırlık: mirror + HTML + LaunchAgent plist zinciri"
  bash "$SCRIPT_DIR/update_preview.sh" --bootstrap
fi

# 2) launchd yaşam döngüsü. update_preview.sh yalnızca kendi label'ının
# plist'ini bootout/bootstrap eder; port sahibini tahmin edip öldürmez.
say "launchd: $LABEL etiketi bootstrap ediliyor"
bash "$SCRIPT_DIR/update_preview.sh" --start "$LABEL"

# 3) Readiness: health tek başına yeterli değildir; dashboard yüzeyi de
# gerçekten servis edilebilmeli. HTTP durum kodu 200 yeterli kabul edilir.
say "readiness: $HEALTH_URL + $PREVIEW_URL (max ${MAX_WAIT}s)"
deadline=$(( $(date +%s) + MAX_WAIT ))
ready=false
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -fsS --max-time 2 -o /dev/null "$HEALTH_URL" \
     && curl -fsS --max-time 2 -o /dev/null "$PREVIEW_URL"; then
    ready=true
    break
  fi
  sleep 1
done

if ! $ready; then
  say "readiness başarısız; launchd durumu:"
  bash "$SCRIPT_DIR/update_preview.sh" --status || true
  err "dashboard ${MAX_WAIT}s içinde hazır olmadı; log: $LOG_PATH"
fi

pid="$({ launchctl list 2>/dev/null || true; } \
  | awk -v label="$LABEL" '$3 == label { print $1; exit }')"
[ -n "$pid" ] || pid="-"

say "READY: Live CI Dashboard"
printf 'DASHBOARD_URL: %s\n' "$PREVIEW_URL"
printf 'PID: %s\n' "$pid"
printf '# register_preview: url=%s pid=%s\n' "$PREVIEW_URL" "$pid"
