#!/usr/bin/env bash
# =============================================================================
# update_preview.sh — canlı CI dashboard'ın TCC-safe kopyasını dinamik build eder.
#
# Neden: preview_server.py (TCC-safe dizinden çalışır) preview.html'ı HER
# İSTEKTE ~/Library/Caches/com.freebuff/preview/preview.html'den okur.
# Kaynak dosya (.freebuff/preview.html) değiştiğinde bu script, içine build
# damgası (UTC zaman + kaynak SHA-256 + git short SHA) gömülü kopyayı
# TCC-safe dizine yazar; sunucu YENİDEN BAŞLATMADAN yeni içeriği servis eder
# (tarayıcıda yenilemek yeterlidir). Build damgası header'da görünür, böylece
# "preview gerçekten yenilendi mi" sorusu sayfada kanıtlanır.
#
# Kullanım:
#   update_preview.sh                # tek seferlik build (kaynak değişmediyse atla)
#   update_preview.sh --force        # stamp tazelense bile yeniden build et
#   update_preview.sh --check        # DST güncel mi? (exit 0 güncel / 1 bayat / 2 hata)
#   update_preview.sh --watch [N]    # N sn'de bir (vars. 3) kaynağı izle; değişince build
#   update_preview.sh --help
#
# Ortam değişkenleri (override):
#   SRC         kaynak HTML   (varsayılan: <repo>/.freebuff/preview.html)
#   DST         TCC-safe kopya (varsayılan: ~/Library/Caches/com.freebuff/preview/preview.html)
#   INTERVAL    --watch bekleme süresi (varsayılan: 3)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC="${SRC:-$ROOT/.freebuff/preview.html}"
DST="${DST:-$HOME/Library/Caches/com.freebuff/preview/preview.html}"
INTERVAL="${INTERVAL:-3}"

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

usage() {
  sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
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
