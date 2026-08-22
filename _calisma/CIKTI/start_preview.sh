#!/usr/bin/env bash
# =============================================================================
# start_preview.sh — HTML rebuild + launchd start + health check tek komutta
#
# update_preview.sh --force + --start'i birleştirir, sunucu hazır olana kadar
# bekler ve URL/PID'i.stdout'a yazar (register_preview için).
#
# Kullanım:
#   bash _calisma/CIKTI/start_preview.sh          # rebuild + start + register bilgisi
#   bash _calisma/CIKTI/start_preview.sh --no-rebuild  # sadece start + health
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CALISMA="$(dirname "$SCRIPT_DIR")"
ROOT="$(dirname "$CALISMA")"
PORT=8000
LABEL="com.freebuff.preview-leibniz2"
MAX_WAIT=30

say()  { printf "\033[36m[start_preview]\033[0m %s\n" "$*"; }
err()  { printf "\033[31m[start_preview]\033[0m %s\n" "$*" >&2; exit 1; }

# --- Argümanlar ---
REBUILD=true
for arg in "$@"; do
    case "$arg" in
        --no-rebuild) REBUILD=false ;;
        --help|-h)
            echo "Kullanım: $0 [--no-rebuild]"
            echo "  --no-rebuild  HTML rebuild yapmadan start + health check"
            exit 0 ;;
        *) err "bilinmeyen argüman: $arg" ;;
    esac
done

# --- 1) HTML rebuild ---
if $REBUILD; then
    say "HTML rebuild ediliyor..."
    bash "$SCRIPT_DIR/update_preview.sh" --force
fi

# --- 2) Mevcut sunucuyu durdur (varsa) ---
# launchctl bootout ile temiz durdur: KeepAlive SuccessfulExit=false
# olduğu için temiz çıkışta launchd yeniden başlatmaz.
OLD_PID=$(lsof -i :"$PORT" -t 2>/dev/null | head -1 || true)
if [ -n "$OLD_PID" ]; then
    say "Mevcut sunucu durduruluyor (pid $OLD_PID)..."
    launchctl bootout gui/$(id -u) "/Users/$USER/Library/LaunchAgents/$LABEL.plist" 2>/dev/null || true
    sleep 1
    # Eğer hâlâ ayakta ise zorla öldür
    if kill -0 "$OLD_PID" 2>/dev/null; then
        say "PID hâlâ ayakta, zorla öldürülüyor..."
        kill -9 "$OLD_PID" 2>/dev/null || true
        sleep 1
    fi
fi

# --- 3) launchd ile başlat ---
say "launchd ile başlatılıyor ($LABEL)..."
bash "$SCRIPT_DIR/update_preview.sh" --start "$LABEL"

# --- 4) Sağlık kontrolü ---
say "Sunucu hazır olana kadar bekleniyor (max ${MAX_WAIT}s)..."
READY=false
for i in $(seq 1 "$MAX_WAIT"); do
    if curl -sf "http://127.0.0.1:$PORT/api/latest" >/dev/null 2>&1; then
        READY=true
        break
    fi
    sleep 1
done

if ! $READY; then
    err "sunucu ${MAX_WAIT}s içinde hazır olmadı (port $PORT)"
fi

# --- 5) PID ve URL ---
PID=$(lsof -i :"$PORT" -t 2>/dev/null | head -1)
URL="http://127.0.0.1:${PORT}/preview.html"

say "✅ Sunucu hazır"
say "   URL:  $URL"
say "   PID:  $PID"
say "   Port: $PORT"

# --- 6) Health snapshot ---
LATEST=$(curl -sf "http://127.0.0.1:$PORT/api/latest" 2>/dev/null || echo "{}")
VERDICT=$(echo "$LATEST" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('verdict','?'))" 2>/dev/null || echo "?")
REFS=$(echo "$LATEST" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"{d.get('refs_verified','?')}/{d.get('regs_total','?')}\")" 2>/dev/null || echo "?")

say "   Durum: verdict=$VERDICT refs=$REFS"

# --- 7) register_preview için çıktı ---
echo ""
echo "# register_preview komutu:"
echo "#   url: $URL"
echo "#   pid: $PID"
