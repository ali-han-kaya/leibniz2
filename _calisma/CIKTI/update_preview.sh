#!/usr/bin/env bash
# =============================================================================
# update_preview.sh — canlı CI dashboard'ın TCC-safe kopyasını dinamik build eder
# ve LaunchAgent plist'ini şablondan per-profile üretir.
#
# BÖLÜM 1 — HTML dashboard
# Neden: preview_server.py (TCC-safe dizinden çalışır) preview.html'ı HER
# İSTEKTE ~/Library/Caches/com.freebuff/preview/preview.html'den okur.
# Kaynak dosya (.freebuff/preview.html) değiştiğinde bu script, içine build
# damgası (UTC zaman + kaynak SHA-256 + git short SHA) gömülü kopyayı
# TCC-safe dizine yazar; sunucu YENİDEN BAŞLATMADAN yeni içeriği servis eder
# (tarayıcıda yenilemek yeterlidir). Build damgası header'da görünür, böylece
# "preview gerçekten yenilendi mi" sorusu sayfada kanıtlanır.
#
# BÖLÜM 2 — LaunchAgent plist (Homebrew-style)
# Kurulu plist tam yolu KORUNUR: ~/Library/LaunchAgents/com.freebuff.preview-leibniz2.plist
# Ancak plist İÇERİĞİ şablon olarak TCC-safe dizinde tutulur:
#   ~/Library/Caches/com.freebuff/preview-template/com.freebuff.preview-leibniz2.plist.tmpl
# Şablonda {{HOME}} / {{PORT}} / {{INTERVAL}} placeholder'ları vardır; script
# bunları verilen profile göre render eder. Böylece aynı şablon her kullanıcı/
# makinede (farklı HOME) doğru mutlak yolları üretir. Şablon yoksa script
# yerleşik varsayılanı yazar (tek kaynak = script; Caches kopyası operasyonel).
#
# Kullanım:
#   update_preview.sh                      # HTML build (kaynak değişmediyse atla)
#   update_preview.sh --force              # HTML yeniden build
#   update_preview.sh --check              # HTML güncel mi? (0 güncel / 1 bayat / 2 hata)
#   update_preview.sh --watch [N]          # HTML izle; değişince build
#   update_preview.sh --plist [HOME]       # plist'i şablondan üret (vars. $HOME)
#   update_preview.sh --plist-force [HOME] # stamp tazelense bile yeniden üret
#   update_preview.sh --plist-check [HOME] # kurulu plist güncel mi? (0/1/2)
#   update_preview.sh --plist-watch [N]    # şablonu izle; değişince yeniden üret
#   update_preview.sh --plist-reset        # şablonu yerleşik varsayılandan geri yaz
#   update_preview.sh --help
#
# Ortam değişkenleri (override):
#   SRC         kaynak HTML   (varsayılan: <repo>/.freebuff/preview.html)
#   DST         TCC-safe kopya (varsayılan: ~/Library/Caches/com.freebuff/preview/preview.html)
#   INTERVAL    --watch bekleme süresi (varsayılan: 3)
#   PLIST_LABEL LaunchAgent etiketi (varsayılan: com.freebuff.preview-leibniz2)
#   PLIST_LOGNAME log dosya adı (varsayılan: preview-leibniz2)
#   PLIST_PORT  plist'teki port (varsayılan: 8000)
#   PLIST_INTERVAL plist'teki interval (varsayılan: 30)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC="${SRC:-$ROOT/.freebuff/preview.html}"
DST="${DST:-$HOME/Library/Caches/com.freebuff/preview/preview.html}"
INTERVAL="${INTERVAL:-3}"

PLIST_LABEL="${PLIST_LABEL:-com.freebuff.preview-leibniz2}"
PLIST_LOGNAME="${PLIST_LOGNAME:-preview-leibniz2}"
PLIST_TMPL_DIR="$HOME/Library/Caches/com.freebuff/preview-template"
PLIST_TMPL="$PLIST_TMPL_DIR/$PLIST_LABEL.plist.tmpl"
PLIST_PORT="${PLIST_PORT:-8000}"
PLIST_INTERVAL="${PLIST_INTERVAL:-30}"

say() { printf '%s\n' "$*"; }
err() { printf 'HATA: %s\n' "$*" >&2; }

src_short() {
  shasum -a 256 "$SRC" 2>/dev/null | awk '{print substr($1,1,12)}'
}

# DST içine gömülü "src <12 hex>" işareti (varsa)
dst_src_short() {
  if [ -f "$DST" ]; then
    grep -o -E 'src [0-9a-f]{12}' "$DST" 2>/dev/null | head -1 | awk '{print $2}'
  fi
  return 0
}

git_short() {
  git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || printf '%s' "-"
}

build() {
  local now stamp tmp src_s
  src_s="${SRC//\"/\\\"}"
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  stamp="<span class=\"ts\" id=\"build-stamp\" title=\"src: ${src_s}\">build ${now} · src $(src_short) · git $(git_short)</span>"
  mkdir -p "$(dirname "$DST")"
  tmp="$(mktemp "$DST.tmp.XXXXXX")" || { err "geçici dosya oluşturulamadı"; return 1; }
  if ! python3 - "$SRC" "$stamp" "$tmp" <<'PY'
import sys
src, stamp, out = sys.argv[1], sys.argv[2], sys.argv[3]
html = open(src, encoding="utf-8").read()
# <span id="live-status" ...>...</span>'dan sonra stamp ekle (header).
anchor = '<span id="live-status"'
i = html.find(anchor)
if i != -1:
    j = html.find("</span>", i)
    i = (j + len("</span>")) if j != -1 else (i + len(anchor))
else:
    # yedek: ilk </h1>'den sonra
    anchor = "</h1>"
    i = html.find(anchor)
    i = (i + len(anchor)) if i != -1 else len(html)
html = html[:i] + "\n  " + stamp + html[i:]
open(out, "w", encoding="utf-8").write(html)
PY
  then
    rm -f "$tmp"
    err "build başarısız (python3 gerekli)"
    return 1
  fi
  mv "$tmp" "$DST"
  say "OK: $DST"
  say "    build ${now} · src $(src_short) · git $(git_short)"
}

# ============================================================================
# BÖLÜM 2 — plist şablonu
# ============================================================================

# Yerleşik varsayılan şablon (tek kaynak). {{HOME}}/{{PORT}}/{{INTERVAL}}
# placeholder'ları per-profile render edilir.
plist_default_template() {
  cat <<'TPL'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{{LABEL}}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>{{HOME}}/Library/Caches/com.freebuff/preview/preview_server.py</string>
    <string>--dir</string>
    <string>{{HOME}}/Library/Caches/com.freebuff/verify</string>
    <string>--preview-dir</string>
    <string>{{HOME}}/Library/Caches/com.freebuff/preview</string>
    <string>--port</string>
    <string>{{PORT}}</string>
    <string>--interval</string>
    <string>{{INTERVAL}}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key>
  <string>{{HOME}}/Library/Logs/com.freebuff/{{LOGNAME}}.log</string>
  <key>StandardErrorPath</key>
  <string>{{HOME}}/Library/Logs/com.freebuff/{{LOGNAME}}.log</string>
</dict>
</plist>
TPL
}

# Şablon dizinini hazırla; şablon yoksa yerleşik varsayılanı yaz.
plist_ensure_template() {
  mkdir -p "$PLIST_TMPL_DIR"
  if [ ! -f "$PLIST_TMPL" ]; then
    plist_default_template > "$PLIST_TMPL"
    say "Şablon yazıldı: $PLIST_TMPL"
  fi
}

# {{HOME}} gibi placeholder'ları verilen profile göre doldur; stdout'a basar.
plist_render() {
  local home="$1"
  sed -e "s|{{HOME}}|${home}|g" \
      -e "s|{{LABEL}}|${PLIST_LABEL}|g" \
      -e "s|{{LOGNAME}}|${PLIST_LOGNAME}|g" \
      -e "s|{{PORT}}|${PLIST_PORT}|g" \
      -e "s|{{INTERVAL}}|${PLIST_INTERVAL}|g" \
      "$PLIST_TMPL"
}

# Kurulu plist'in tam yolu (Homebrew-style, per-profile).
plist_dst_for() {
  printf '%s/Library/LaunchAgents/%s.plist' "$1" "$PLIST_LABEL"
}

# HOME argümanını normalleştir (varsayılan $HOME, ~ ile başlıyorsa genişlet).
plist_home() {
  local h="${1:-$HOME}"
  case "$h" in
    \~*) h="${HOME}${h#\~}" ;;
  esac
  printf '%s' "$h"
}

plist_validate() {
  if command -v plutil >/dev/null 2>&1; then
    plutil -lint "$1" >/dev/null 2>&1
  else
    # plutil yoksa XML iyi-biçimliliğini python ile kontrol et
    python3 -c 'import plistlib,sys; plistlib.load(open(sys.argv[1],"rb"))' "$1" >/dev/null 2>&1
  fi
}

# Bir HOME için: kurulu plist, şablondan üretilecek içerikle aynı mı?
plist_up_to_date() {
  local home="$1" dst rendered
  dst="$(plist_dst_for "$home")"
  [ -f "$dst" ] || return 1
  rendered="$(plist_render "$home")" || return 2
  [ "$(cat "$dst")" = "$rendered" ] || return 1
  plist_validate "$dst" || return 1
  return 0
}

plist_install() {
  local home="$1" dst tmp
  dst="$(plist_dst_for "$home")"
  mkdir -p "$(dirname "$dst")"
  tmp="$(mktemp "$dst.tmp.XXXXXX")" || { err "geçici dosya oluşturulamadı"; return 1; }
  plist_render "$home" > "$tmp" || { rm -f "$tmp"; return 1; }
  if ! plist_validate "$tmp"; then
    rm -f "$tmp"
    err "üretilen plist geçersiz (plutil/python doğrulaması başarısız) — yazılmadı"
    return 1
  fi
  mv "$tmp" "$dst"
  say "OK: $dst"
  say "    plist şablondan üretildi (port $PLIST_PORT, interval ${PLIST_INTERVAL}s)"
}

plist_do() {
  local home
  home="$(plist_home "${1:-}")"
  plist_ensure_template
  if plist_up_to_date "$home"; then
    say "GÜNCEL: $(plist_dst_for "$home") zaten şablondan üretilmiş (--plist-force ile zorla)."
  else
    plist_install "$home"
  fi
}

plist_force() {
  local home
  home="$(plist_home "${1:-}")"
  plist_ensure_template
  plist_install "$home"
}

plist_check() {
  local home
  home="$(plist_home "${1:-}")"
  if [ ! -f "$PLIST_TMPL" ]; then
    err "şablon yok: $PLIST_TMPL (önce --plist çalıştır)"
    exit 2
  fi
  if plist_up_to_date "$home"; then
    say "GÜNCEL: $(plist_dst_for "$home")  (şablonla aynı, plutil geçerli)"
    exit 0
  else
    say "BAYAT/GEÇERSİZ: $(plist_dst_for "$home") şablondan farklı"
    exit 1
  fi
}

plist_watch() {
  local interval last_h last_t
  interval="${1:-$INTERVAL}"
  plist_ensure_template
  last_h=""
  last_t=""
  say "İzleniyor: $PLIST_TMPL (her ${interval}s) — Ctrl+C ile durdur"
  trap 'say "durduruldu."; exit 0' INT TERM
  while true; do
    local h t
    h="$(shasum -a 256 "$PLIST_TMPL" 2>/dev/null | awk '{print $1}')"
    t="$(date +%s)"
    if [ "$h" != "$last_h" ]; then
      if [ -n "$last_t" ]; then
        # ilk turda değilse ve şablon değiştiyse yeniden üret
        if ! plist_up_to_date "$HOME"; then
          plist_install "$HOME"
        else
          say "şablon değişti ama kurulu plist zaten güncel"
        fi
      fi
      last_h="$h"
    fi
    last_t="$t"
    sleep "$interval"
  done
}

usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"
}

case "${1:-build}" in
  --help|-h)
    usage
    ;;
  --check)
    [ -f "$SRC" ] || { err "kaynak yok: $SRC"; exit 2; }
    s="$(src_short)"
    d="$(dst_src_short)"
    if [ -z "$d" ]; then
      say "DST'de build damgası yok (henüz build edilmemiş): $DST"
      exit 1
    elif [ "$s" = "$d" ]; then
      say "GÜNCEL: $DST  (src $s)"
      exit 0
    else
      say "BAYAT: DST src=$d, SRC src=$s"
      exit 1
    fi
    ;;
  --force)
    [ -f "$SRC" ] || { err "kaynak yok: $SRC"; exit 2; }
    build
    ;;
  --watch)
    [ -f "$SRC" ] || { err "kaynak yok: $SRC"; exit 2; }
    interval="${2:-$INTERVAL}"
    last=""
    say "İzleniyor: $SRC (her ${interval}s) — Ctrl+C ile durdur"
    trap 'say "durduruldu."; exit 0' INT TERM
    while true; do
      s="$(src_short)"
      if [ "$s" != "$last" ] && [ "$s" != "$(dst_src_short)" ]; then
        build
      fi
      last="$s"
      sleep "$interval"
    done
    ;;
  --plist)
    plist_do "${2:-}"
    ;;
  --plist-force)
    plist_force "${2:-}"
    ;;
  --plist-check)
    plist_check "${2:-}"
    ;;
  --plist-watch)
    plist_watch "${2:-}"
    ;;
  --plist-reset)
    mkdir -p "$PLIST_TMPL_DIR"
    plist_default_template > "$PLIST_TMPL"
    say "Şablon yerleşik varsayılandan geri yazıldı: $PLIST_TMPL"
    ;;
  build)
    [ -f "$SRC" ] || { err "kaynak yok: $SRC"; exit 2; }
    if [ "$(src_short)" = "$(dst_src_short)" ]; then
      say "GÜNCEL: $DST zaten aynı kaynaktan build edilmiş (--force ile zorla)."
    else
      build
    fi
    ;;
  *)
    err "bilinmeyen mod: $1 (--help)"
    exit 2
    ;;
esac
