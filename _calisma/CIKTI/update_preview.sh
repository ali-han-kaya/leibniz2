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
# BÖLÜM 2 — LaunchAgent plist'leri (Homebrew-style, tek komut)
# İKİ plist yönetilir (tek --plist komutuyla): com.freebuff.preview-leibniz2
# (birincil; KeepAlive=true, interval 30) ve com.freebuff.preview-server
# (legacy; interval 60). Kurulu tam yollar korunur:
#   ~/Library/LaunchAgents/<label>.plist
# İçerikleri şablon olarak TCC-safe dizinde tutulur:
#   ~/Library/Caches/com.freebuff/preview-template/<label>.plist.tmpl
# Şablonda {{HOME}} / {{LABEL}} / {{LOGNAME}} / {{PORT}} / {{INTERVAL}} /
# {{KEEPALIVE}} placeholder'ları vardır; script bunları her profile göre
# render eder. İkisi de aynı TCC-safe mirror --dir'ini kullanır (launchd GUI
# agent'ı repo dizinini TCC nedeniyle okuyamaz). Şablon yoksa script yerleşik
# varsayılanı yazar (tek kaynak = script; Caches kopyası operasyonel).
#
# BÖLÜM 3 — verify mirror senkronu (sync_verify_mirror.sh'e delege eder)
# verify_delivery.py --full koşusu launchd GUI agent rotasında repo yerine
# TCC-safe mirror'dan (--dir) çalışır; mirror, CIKTI runtime dosyalarının ve
# Lean ispatının kopyasıdır. --mirror bunu TEK KOMUTLA senkron eder (run.md
# adım 4'ün yerine geçer); --mirror-check bayatlığı denetler (fail-closed:
# 0 güncel / 1 bayat / 2 hata).
#
# Kullanım:
#   update_preview.sh                      # HTML build (kaynak değişmediyse atla)
#   update_preview.sh --force              # HTML yeniden build
#   update_preview.sh --check              # HTML güncel mi? (0 güncel / 1 bayat / 2 hata)
#   update_preview.sh --watch [N]          # HTML izle; değişince build
#   update_preview.sh --plist [HOME]       # her iki plist'i şablonlardan üret (vars. $HOME)
#   update_preview.sh --plist-force [HOME] # her iki plist'i her zaman yeniden üret
#   update_preview.sh --plist-check [HOME] # kurulu plist'ler güncel mi? (0 hepsi/1 bayat/2 şablon yok)
#   update_preview.sh --plist-watch [N]    # şablonları izle; değişince yeniden üret
#   update_preview.sh --plist-reset        # şablonları yerleşik varsayılandan geri yaz
#   update_preview.sh --start [LABEL]       # plist'i üret + launchctl bootstrap (vars. birincil)
#   update_preview.sh --stop [LABEL|all]    # launchctl bootout (all = her iki agent)
#   update_preview.sh --mirror             # verify mirror'ı senkron et (sync_verify_mirror.sh)
#   update_preview.sh --mirror-check       # mirror güncel mi? (0 güncel/1 bayat/2 hata)
#   update_preview.sh --mirror-force       # mirror'ı koşulsuz yeniden kopyala
#   update_preview.sh --help
#
# Ortam değişkenleri (override):
#   SRC         kaynak HTML   (varsayılan: <repo>/.freebuff/preview.html)
#   DST         TCC-safe kopya (varsayılan: ~/Library/Caches/com.freebuff/preview/preview.html)
#   INTERVAL    --watch bekleme süresi (varsayılan: 3)
#   (plist profilleri script içindeki PLIST_PROFILES dizisindedir:
#    label|logname|port|interval|keepalive — env ile override edilmez)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC="${SRC:-$ROOT/.freebuff/preview.html}"
DST="${DST:-$HOME/Library/Caches/com.freebuff/preview/preview.html}"
INTERVAL="${INTERVAL:-3}"

PLIST_TMPL_DIR="$HOME/Library/Caches/com.freebuff/preview-template"
# Her profil: "label|logname|port|interval|keepalive". İkisi de aynı
# preview_server.py'yi aynı TCC-safe mirror --dir'iyle başlatır (launchd GUI
# agent'ı repo dizinini TCC nedeniyle okuyamaz); şablonda {{HOME}}/.../verify
# sabittir. Farklar yalnızca label/logname/interval/keepalive'dir.
PLIST_PROFILES=(
  "com.freebuff.preview-leibniz2|preview-leibniz2|8000|30|true"
  "com.freebuff.preview-server|preview-server|8000|60|false"
)

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

# Yerleşik varsayılan şablon (tek kaynak). {{HOME}}/{{LABEL}}/{{LOGNAME}}/
# {{PORT}}/{{INTERVAL}}/{{KEEPALIVE}} placeholder'ları per-profile render edilir.
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
  <key>KeepAlive</key>{{KEEPALIVE}}
  <key>StandardOutPath</key>
  <string>{{HOME}}/Library/Logs/com.freebuff/{{LOGNAME}}.log</string>
  <key>StandardErrorPath</key>
  <string>{{HOME}}/Library/Logs/com.freebuff/{{LOGNAME}}.log</string>
</dict>
</plist>
TPL
}

# Profil listesini yayınla (her satır "label|logname|port|interval|keepalive").
plist_profiles() {
  printf '%s\n' "${PLIST_PROFILES[@]}"
}

# Bir profilin şablon dosyası yolu.
plist_tmpl_for() {
  printf '%s/%s.plist.tmpl' "$PLIST_TMPL_DIR" "$1"
}

# Şablon dizinini hazırla; eksik her profil şablonunu yerleşik varsayılandan yaz.
plist_ensure_templates() {
  mkdir -p "$PLIST_TMPL_DIR"
  while IFS='|' read -r label _; do
    local tmpl
    tmpl="$(plist_tmpl_for "$label")"
    if [ ! -f "$tmpl" ]; then
      plist_default_template > "$tmpl"
      say "Şablon yazıldı: $tmpl"
    fi
  done < <(plist_profiles)
}

# {{HOME}} gibi placeholder'ları bir profile göre doldur; stdout'a basar.
# $1=home $2=label $3=logname $4=port $5=interval $6=keepalive(true|false)
plist_render() {
  local home="$1" label="$2" logname="$3" port="$4" interval="$5" keepalive="$6"
  sed -e "s|{{HOME}}|${home}|g" \
      -e "s|{{LABEL}}|${label}|g" \
      -e "s|{{LOGNAME}}|${logname}|g" \
      -e "s|{{PORT}}|${port}|g" \
      -e "s|{{INTERVAL}}|${interval}|g" \
      -e "s|{{KEEPALIVE}}|<${keepalive}/>|g" \
      "$(plist_tmpl_for "$label")"
}

# Kurulu plist'in tam yolu (Homebrew-style, per-profile).
plist_dst_for() {
  printf '%s/Library/LaunchAgents/%s.plist' "$1" "$2"
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

# Bir profile göre: kurulu plist, şablondan üretilecek içerikle aynı mı?
plist_up_to_date() {
  local home="$1" label="$2" dst rendered
  dst="$(plist_dst_for "$home" "$label")"
  [ -f "$dst" ] || return 1
  rendered="$(plist_render "$@")" || return 2
  [ "$(cat "$dst")" = "$rendered" ] || return 1
  plist_validate "$dst" || return 1
  return 0
}

plist_install() {
  local home="$1" label="$2" port="$4" interval="$5" dst tmp
  dst="$(plist_dst_for "$home" "$label")"
  mkdir -p "$(dirname "$dst")"
  tmp="$(mktemp "$dst.tmp.XXXXXX")" || { err "geçici dosya oluşturulamadı"; return 1; }
  plist_render "$@" > "$tmp" || { rm -f "$tmp"; return 1; }
  if ! plist_validate "$tmp"; then
    rm -f "$tmp"
    err "üretilen plist geçersiz (plutil/python doğrulaması başarısız) — yazılmadı"
    return 1
  fi
  mv "$tmp" "$dst"
  say "OK: $dst"
  say "    plist şablondan üretildi (port $port, interval ${interval}s)"
}

plist_do() {
  local home
  home="$(plist_home "${1:-}")"
  plist_ensure_templates
  local rc=0
  while IFS='|' read -r label logname port interval keepalive; do
    if plist_up_to_date "$home" "$label" "$logname" "$port" "$interval" "$keepalive"; then
      say "GÜNCEL: $(plist_dst_for "$home" "$label") zaten şablondan üretilmiş (--plist-force ile zorla)."
    else
      plist_install "$home" "$label" "$logname" "$port" "$interval" "$keepalive" || rc=1
    fi
  done < <(plist_profiles)
  return $rc
}

plist_force() {
  local home
  home="$(plist_home "${1:-}")"
  plist_ensure_templates
  local rc=0
  while IFS='|' read -r label logname port interval keepalive; do
    plist_install "$home" "$label" "$logname" "$port" "$interval" "$keepalive" || rc=1
  done < <(plist_profiles)
  return $rc
}

plist_check() {
  local home
  home="$(plist_home "${1:-}")"
  local rc=0 missing=0
  while IFS='|' read -r label logname port interval keepalive; do
    local tmpl
    tmpl="$(plist_tmpl_for "$label")"
    if [ ! -f "$tmpl" ]; then
      err "şablon yok: $tmpl (önce --plist çalıştır)"
      missing=1
      continue
    fi
    if plist_up_to_date "$home" "$label" "$logname" "$port" "$interval" "$keepalive"; then
      say "GÜNCEL: $(plist_dst_for "$home" "$label")  (şablonla aynı, plutil geçerli)"
    else
      say "BAYAT/GEÇERSİZ: $(plist_dst_for "$home" "$label") şablondan farklı"
      rc=1
    fi
  done < <(plist_profiles)
  if [ "$missing" -ne 0 ]; then exit 2; fi
  if [ "$rc" -ne 0 ]; then exit 1; fi
  exit 0
}

plist_reset() {
  mkdir -p "$PLIST_TMPL_DIR"
  while IFS='|' read -r label _; do
    plist_default_template > "$(plist_tmpl_for "$label")"
    say "Şablon yerleşik varsayılandan geri yazıldı: $(plist_tmpl_for "$label")"
  done < <(plist_profiles)
}

# ============================================================================
# BÖLÜM 2b — launchctl bootstrap/bootout (--start / --stop)
# ============================================================================

# Birincil label (KeepAlive, otomatik yeniden başlatma) — --start varsayılanı.
plist_primary_label() {
  plist_profiles | head -1 | awk -F'|' '{print $1}'
}

# launchd hedef domain'i (kullanıcı GUI agent'ı).
launchctl_domain() { printf 'gui/%s' "$(id -u)"; }

# Profil satırını label'a göre bul (label|logname|port|interval|keepalive).
plist_profile_for() {
  local want="$1"
  while IFS='|' read -r label logname port interval keepalive; do
    [ "$label" = "$want" ] || continue
    printf '%s|%s|%s|%s|%s\n' "$label" "$logname" "$port" "$interval" "$keepalive"
    return 0
  done < <(plist_profiles)
  return 1
}

# label launchd'ye yüklü mü? (launchctl list 3. sütun = label)
plist_is_loaded() {
  launchctl list 2>/dev/null | awk -v l="$1" '$3 == l {found=1} END {exit found ? 0 : 1}'
}

# Tek label'ı bootstrap et (idempotent: varsa sök → yükle → enable).
plist_start_one() {
  local label="$1" profile dst logname port interval keepalive
  profile="$(plist_profile_for "$label")" || {
    err "bilinmeyen label: $label"
    say "  profiller:"
    while IFS='|' read -r l _; do say "    $l"; done < <(plist_profiles)
    return 1
  }
  IFS='|' read -r label logname port interval keepalive <<< "$profile"
  dst="$(plist_dst_for "$HOME" "$label")"

  # Kurulu plist yok/başka ise önce üret (generate + validate) — tek komut.
  if ! plist_up_to_date "$HOME" "$label" "$logname" "$port" "$interval" "$keepalive"; then
    plist_install "$HOME" "$label" "$logname" "$port" "$interval" "$keepalive" || return 1
  fi

  # İdem-potent: önce varsa sök, sonra yükle, sonra enable.
  launchctl bootout "$(launchctl_domain)" "$dst" 2>/dev/null || true
  launchctl bootstrap "$(launchctl_domain)" "$dst" || { err "bootstrap başarısız: $dst"; return 1; }
  launchctl enable "$(launchctl_domain)/$label" 2>/dev/null || true
  say "START: $label → bootstrap edildi ($dst)"
  say "       yüklü: $(plist_is_loaded "$label" && echo evet || echo hayır)"
}

# Tek label'ı bootout et.
plist_stop_one() {
  local label="$1" dst
  dst="$(plist_dst_for "$HOME" "$label")"
  if plist_is_loaded "$label"; then
    launchctl bootout "$(launchctl_domain)" "$dst" 2>/dev/null \
      && say "STOP: $label → bootout edildi" \
      || { err "bootout başarısız: $label ($dst)"; return 1; }
  else
    say "STOP: $label zaten yüklü değil"
  fi
}

plist_start() {
  local label="${1:-$(plist_primary_label)}"
  if [ "$label" = "all" ]; then
    err "--start all desteklenmez (iki agent aynı 8000 portunu paylaşır); birincil label'ı kullanın"
    return 1
  fi
  plist_start_one "$label"
}

plist_stop() {
  local label="${1:-$(plist_primary_label)}"
  if [ "$label" = "all" ]; then
    local rc=0
    while IFS='|' read -r l _; do
      plist_stop_one "$l" || rc=1
    done < <(plist_profiles)
    return $rc
  fi
  plist_stop_one "$label"
}

# Tüm şablonların birleşik SHA-256'sı (--plist-watch değişim algısı için).
plist_templates_hash() {
  { while IFS='|' read -r label _; do
      cat "$(plist_tmpl_for "$label")" 2>/dev/null || true
    done < <(plist_profiles); } | shasum -a 256 | awk '{print $1}'
}

plist_watch() {
  local interval last_h last_t
  interval="${1:-$INTERVAL}"
  plist_ensure_templates
  last_h=""
  last_t=""
  say "İzleniyor: $PLIST_TMPL_DIR (her ${interval}s) — Ctrl+C ile durdur"
  trap 'say "durduruldu."; exit 0' INT TERM
  while true; do
    local h t
    h="$(plist_templates_hash)"
    t="$(date +%s)"
    if [ "$h" != "$last_h" ]; then
      if [ -n "$last_t" ]; then
        # ilk turda değilse ve şablon değiştiyse yeniden üret
        plist_do "$HOME" || say "plist yeniden üretilirken sorun oluştu"
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
    plist_reset
    ;;
  --start)
    plist_start "${2:-}"
    ;;
  --stop)
    plist_stop "${2:-}"
    ;;
  --mirror)
    "$SCRIPT_DIR/sync_verify_mirror.sh"
    ;;
  --mirror-force)
    "$SCRIPT_DIR/sync_verify_mirror.sh" --force
    ;;
  --mirror-check)
    "$SCRIPT_DIR/sync_verify_mirror.sh" --check
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
