#!/usr/bin/env bash
# =============================================================================
# fresh_clone_setup.sh — TCC-safe preview/verify ortamını fresh clone'dan TEK
# KOMUTTA kurar (idempotent, fail-closed).
#
# Neden: preview_server.py launchd GUI agent rotasında çalışırken repo dizinini
# TCC nedeniyle OKUYAMAZ; tüm runtime TCC-safe mirror'da (~/Library/Caches/
# com.freebuff/) tutulur. Bu script, ayrı ayrı elle yapılan beş işi tek komuta
# toplar (run.md "How to reproduce the artifacts" adımları 1-4 + plist):
#
#   1. Repo venv        _calisma/.venv_z3          (z3 + pre-commit + yaml + jsonschema)
#   2. Mirror venv      ~/Library/Caches/com.freebuff/venv_z3  (TCC-safe, aynı paketler)
#   3+4. Preview+verify mirror  sync_verify_mirror.sh — TEK KOMUT:
#        ~/Library/Caches/com.freebuff/preview/   (preview_server.py + _daemonize.py, adım 2)
#        ~/Library/Caches/com.freebuff/verify + lean_reduct (adım 4)
#   5. HTML + plist     update_preview.sh --bootstrap (HTML build + LaunchAgent plist'leri)
#
# Her adım fail-closed'dur: kaynak yok / venv kurulamaz / kopya başarısız →
# hata ile durur (exit ≠ 0). --check modu beş artefaktın da GÜNCEL olduğunu,
# daemon HTTP rotasının çalıştığını ve launchd agent'ın kullandığı mirror'ın
# --check ile aynı olduğunu denetler (plist'teki gerçek --preview-dir/--dir;
# daemon_http_test.py mirror kopyasıyla SSE/run-now dahil HTTP smoke;
# 0 hazır / 1 eksik-bayat-drift / 2 hata) — K17/K18/K12 kapılarının ön-koşulu.
#
# Kullanım:
#   fresh_clone_setup.sh             # beş artefaktı kur (yoksa) / senkron et (bayatsa)
#   fresh_clone_setup.sh --check     # hepsi hazır mı? (0 evet / 1 eksik / 2 hata)
#   fresh_clone_setup.sh --force-venv# venv'leri her zaman yeniden kur (pip install --upgrade)
#   fresh_clone_setup.sh --help
#
# Ortam değişkenleri (override):
#   ROOT            repo kökü (varsayılan: script'in ../../)
#   REPO_VENV       repo venv yolu (varsayılan: $ROOT/_calisma/.venv_z3)
#   MIRROR_VENV     TCC-safe venv mirror (varsayılan: $HOME/Library/Caches/com.freebuff/venv_z3)
#   PREVIEW_MIRROR  TCC-safe preview dizini (varsayılan: $HOME/Library/Caches/com.freebuff/preview)
#   MIRROR_DIR      verify mirror (sync_verify_mirror.sh'e geçer)
#   LEAN_MIRROR_DIR Lean mirror (sync_verify_mirror.sh'e geçer)
#   FC_TEST_FAKE_VENV=1  TEST-ONLY: venv import denetimini atlar (offline birim
#                       testleri; gerçek kurulumda KULLANMA)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
CIKTI="$ROOT/_calisma/CIKTI"

REPO_VENV="${REPO_VENV:-$ROOT/_calisma/.venv_z3}"
MIRROR_VENV="${MIRROR_VENV:-$HOME/Library/Caches/com.freebuff/venv_z3}"
PREVIEW_MIRROR="${PREVIEW_MIRROR:-$HOME/Library/Caches/com.freebuff/preview}"
# Verify mirror (sync_verify_mirror.sh ile aynı varsayılan — daemon rotası
# daemon_http_test.py'nin MIRROR kopyasıyla doğrulanır).
MIRROR_DIR="${MIRROR_DIR:-$HOME/Library/Caches/com.freebuff/verify}"

# Mirror venv'e kurulacak paketler (repo venv ile aynı çekirdek küme).
# pre-commit de hook'lar için mirror'da gereklidir (launchd GUI agent rotası).
VENV_PACKAGES="z3-solver pre-commit pyyaml jsonschema"

say() { printf '%s\n' "$*"; }
err() { printf 'HATA: %s\n' "$*" >&2; }

# Python 3 bul (python3 → /usr/bin/python3 fallback). Yalnızca venv KURARKEN.
find_python3() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif [ -x /usr/bin/python3 ]; then
    printf '%s' /usr/bin/python3
  else
    return 1
  fi
}

# Venv kurulu ve çekirdek paketler import edilebiliyor mu?
venv_ok() {
  local py="$1/bin/python3"
  [ -x "$py" ] || return 1
  if [ "${FC_TEST_FAKE_VENV:-0}" = "1" ]; then
    # TEST-ONLY: import denetimini atla (offline birim testleri için).
    return 0
  fi
  "$py" -c "import z3, yaml" >/dev/null 2>&1 || return 1
  # jsonschema isteğe bağlı: verify_delivery.py şema doğrulamasında stdlib
  # fallback kullanır; jsonschema yalnızca CI'da ayrıca kurulur. Var ise
  # bonus doğrulama, yoksa bozuk sayılmaz.
  return 0
}

# Venv kur (python3 -m venv + pip install). Fail-closed.
create_venv() {
  local dir="$1"
  local py3
  py3="$(find_python3)" || { err "python3 bulunamadı — venv kurulamaz"; return 1; }
  say "venv kuruluyor: $dir (python: $py3)"
  mkdir -p "$(dirname "$dir")"
  rm -rf "$dir"
  "$py3" -m venv "$dir" || { err "venv oluşturulamadı: $dir"; return 1; }
  "$dir/bin/python3" -m pip install --quiet --disable-pip-version-check \
      $VENV_PACKAGES || { err "pip install başarısız: $dir"; return 1; }
  say "venv hazır: $dir"
}

# --check: beş artefaktın tamamı hazır mı? (0 evet / 1 eksik / 2 hata)
check_all() {
  local rc=0 missing=0

  # 1. Repo venv
  if venv_ok "$REPO_VENV"; then
    say "OK: repo venv ($REPO_VENV)"
  else
    err "repo venv eksik/bozuk: $REPO_VENV (fresh_clone_setup.sh çalıştırın)"
    missing=1
  fi

  # 2. Mirror venv
  if venv_ok "$MIRROR_VENV"; then
    say "OK: mirror venv ($MIRROR_VENV)"
  else
    err "mirror venv eksik/bozuk: $MIRROR_VENV (fresh_clone_setup.sh çalıştırın)"
    missing=1
  fi

  # 3+4. Preview + verify mirror (sync_verify_mirror.sh --check — adım 2+4
  #      tek komutta: 0 güncel/1 bayat/2 hata; PREVIEW_MIRROR dahil).
  #      BAYAT/EKSİK dosya listesi kullanıcıya komut satırında raporlanır.
  if [ -x "$SCRIPT_DIR/sync_verify_mirror.sh" ]; then
    local sync_out sync_rc=0
    sync_out="$("$SCRIPT_DIR/sync_verify_mirror.sh" --check 2>&1)" || sync_rc=$?
    if [ "$sync_rc" -eq 0 ]; then
      say "OK: preview + verify mirror (repo ↔ mirror birebir)"
    else
      err "preview/verify mirror bayat/eksik — bayat dosyalar:"
      printf '%s\n' "$sync_out" \
        | grep -E 'BAYAT/EKSİK' \
        | while IFS= read -r b; do err "  $b"; done
      err "  (fresh_clone_setup.sh çalıştırın)"
      missing=1
    fi
  else
    err "sync_verify_mirror.sh yok — preview/verify mirror denetlenemedi"
    missing=1
  fi

  # 3b. launchd agent'ın kullandığı mirror ile karşılaştır: plist'in
  #      ProgramArguments'undaki ('--' sonrası sunucu komutu) gerçek
  #      --preview-dir/--dir yolları, --check'in denetlediği PREVIEW_MIRROR/
  #      MIRROR_DIR ile aynı mı? Fark varsa --check anlamsızlaşır → DRIFT
  #      (fail-closed). Agent kurulu değilse BİLGİ (eksik sayılmaz).
  local ag_plist="$HOME/Library/LaunchAgents/com.freebuff.preview-leibniz2.plist"
  if [ -f "$ag_plist" ] && command -v python3 >/dev/null 2>&1; then
    local ag_dirs ag_preview ag_verify
    ag_dirs="$(python3 - "$ag_plist" 2>/dev/null <<'PYEOF'
import plistlib, sys
with open(sys.argv[1], "rb") as f:
    d = plistlib.load(f)
args = d.get("ProgramArguments", []) or []
# Sunucu komutu '--' ayracı sonrası (prestart wrapper); yoksa tümünü tara.
try:
    idx = args.index("--")
    server = args[idx + 1:]
except ValueError:
    server = args
def val(flag):
    try:
        return server[server.index(flag) + 1]
    except (ValueError, IndexError):
        return ""
print("PREVIEW_DIR=%s" % val("--preview-dir"))
print("VERIFY_DIR=%s" % val("--dir"))
PYEOF
)"
    ag_preview="$(printf '%s\n' "$ag_dirs" | sed -n 's/^PREVIEW_DIR=//p')"
    ag_verify="$(printf '%s\n' "$ag_dirs" | sed -n 's/^VERIFY_DIR=//p')"
    if [ -z "$ag_preview" ] || [ -z "$ag_verify" ]; then
      err "agent plist'i okunamadı ($ag_plist) — mirror karşılaştırması yapılamadı"
      missing=1
    elif [ "$ag_preview" != "$PREVIEW_MIRROR" ] || [ "$ag_verify" != "$MIRROR_DIR" ]; then
      err "DRIFT: launchd agent --check'in denetlediğinden FARKLI mirror kullanıyor:"
      err "  agent:   preview=$ag_preview verify=$ag_verify"
      err "  --check: preview=$PREVIEW_MIRROR verify=$MIRROR_DIR"
      err "  (update_preview.sh --start / fresh_clone_setup.sh çalıştırın)"
      missing=1
    else
      say "OK: launchd agent mirror'ı --check ile aynı (preview+verify)"
    fi
  elif [ -f "$ag_plist" ]; then
    err "python3 yok — agent plist karşılaştırması yapılamadı"
    missing=1
  else
    say "BİLGİ: launchd agent kurulu değil (plist yok) — mirror karşılaştırması atlandı"
  fi    # 5. HTML + plist (update_preview.sh --check + --plist-check)
    if [ -x "$SCRIPT_DIR/update_preview.sh" ]; then
      if "$SCRIPT_DIR/update_preview.sh" --check >/dev/null 2>&1; then
        say "OK: HTML build (güncel)"
      else
        err "HTML build bayat/eksik (fresh_clone_setup.sh çalıştırın)"
        missing=1
      fi
      # --plist-check: 0 hepsi güncel / 1 bayat / 2 şablon yok
      local prc=0
      "$SCRIPT_DIR/update_preview.sh" --plist-check >/dev/null 2>&1 || prc=$?
      if [ "$prc" -eq 0 ]; then
        say "OK: LaunchAgent plist'leri (güncel)"
      elif [ "$prc" -eq 2 ]; then
        err "plist şablonu yok (fresh_clone_setup.sh --bootstrap çalıştırın)"
        missing=1
      else
        err "LaunchAgent plist'leri bayat (fresh_clone_setup.sh çalıştırın)"
        missing=1
      fi
    else
      err "update_preview.sh yok — HTML/plist denetlenemedi"
      missing=1
    fi

    # 6. Daemon HTTP rotası (daemon_http_test.py — MIRROR kopyasıyla koşulur:
    #    launchd GUI agent'ının TCC-safe runtime'ı birebir doğrulanır; repo
    #    kopyası değil, mirror kopyası. Boş portta geçici daemon kurulur ve
    #    SSE/run-now dahil HTTP smoke'u exit 0 vermeli.)
    if [ -f "$MIRROR_DIR/daemon_http_test.py" ]; then
      local dpy=""
      if [ -x "$REPO_VENV/bin/python3" ]; then
        dpy="$REPO_VENV/bin/python3"
      elif [ -x "$MIRROR_VENV/bin/python3" ]; then
        dpy="$MIRROR_VENV/bin/python3"
      elif command -v python3 >/dev/null 2>&1; then
        dpy="$(command -v python3)"
      fi
      local dreport
      dreport="$(mktemp)" || dreport="/tmp/fc_setup_daemon_report.json"
      if [ -n "$dpy" ] && (cd "$MIRROR_DIR" && \
          "$dpy" daemon_http_test.py --out "$dreport" \
            --start-timeout 30 >/dev/null 2>&1); then
        say "OK: daemon HTTP rotası (daemon_http_test.py — mirror kopyası)"
      else
        err "daemon HTTP rotası başarısız (mirror kopyası daemon_http_test.py)"
        missing=1
      fi
      rm -f "$dreport"
    else
      err "daemon_http_test.py mirror'da yok — daemon rotası denetlenemedi"
      missing=1
    fi

    if [ "$missing" -ne 0 ]; then
      say "SONUÇ: EKSİK — 5 artefakt + daemon rotası + agent mirror uyumu hazır değil (exit 1)"
      return 1
    fi
    say "SONUÇ: TAMAM — beş artefakt + daemon rotası + agent mirror uyumu hazır (exit 0)"
    return 0
}

# Tüm kurulum: 5 adım (fail-closed).
setup_all() {
  local force_venv="${1:-0}"

  say "=== 1/5: Repo venv ($REPO_VENV) ==="
  if venv_ok "$REPO_VENV" && [ "$force_venv" -eq 0 ]; then
    say "GÜNCEL: repo venv zaten hazır"
  else
    create_venv "$REPO_VENV" || return $?
  fi

  say "=== 2/5: Mirror venv ($MIRROR_VENV) ==="
  if venv_ok "$MIRROR_VENV" && [ "$force_venv" -eq 0 ]; then
    say "GÜNCEL: mirror venv zaten hazır"
  else
    create_venv "$MIRROR_VENV" || return $?
  fi

  say "=== 3+4/5: Preview + verify mirror (sync_verify_mirror.sh — adım 2+4) ==="
  "$SCRIPT_DIR/sync_verify_mirror.sh" || return $?

  say "=== 5/5: HTML build + LaunchAgent plist'leri (--bootstrap) ==="
  "$SCRIPT_DIR/update_preview.sh" --bootstrap || return $?

  say "FRESH-CLONE KURULUM: tamam — 5/5 artefakt hazır (adım 2+4 tek komutta)"
  say "           sonraki adım: update_preview.sh --start (launchctl bootstrap) " \
       "veya fresh_clone_setup.sh --check"
}

usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"
}

main() {
  local mode="${1:-setup}" force_venv=0
  case "$mode" in
    --help|-h)
      usage
      exit 0
      ;;
    --check)
      check_all
      ;;
    --force-venv)
      force_venv=1
      setup_all "$force_venv"
      ;;
    setup)
      setup_all "$force_venv"
      ;;
    *)
      err "bilinmeyen mod: $mode (--help)"
      exit 2
      ;;
  esac
}

main "$@"
