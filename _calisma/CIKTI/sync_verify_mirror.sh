#!/usr/bin/env bash
# =============================================================================
# sync_verify_mirror.sh — repo → TCC-safe mirror TEK KOMUT senkronu.
#
# Neden: preview_server.py launchd GUI agent rotasında çalışırken repo
# dizinini TCC nedeniyle okuyamaz; tüm runtime TCC-safe mirror'da tutulur.
# Bu script, fresh_clone_setup.sh'in 3+4. adımını yerine getirir
# (preview mirror: preview_server.py + _daemonize.py ve verify mirror:
# CIKTI runtime dosyaları + Lean ispatı — tek komutta):
#   ~/Library/Caches/com.freebuff/preview      (adım 2 — sunucu çalıştırıcı)
#   ~/Library/Caches/com.freebuff/verify       (adım 4 — verify_delivery --dir)
#   ~/Library/Caches/com.freebuff/lean_reduct  (adım 4 — K9: ../lean_reduct/…)
# launchd GUI agent'ı /Users/.../Desktop altını TCC nedeniyle okuyamaz;
# mirror bunu aşar. İdempotent (yalnızca değişen dosya kopyalanır) ve
# fail-closed (eksik kaynak → exit 2, hiçbir şey kopyalanmaz).
#
# Kullanım:
#   sync_verify_mirror.sh             # senkron (değişeni kopyala, raporla)
#   sync_verify_mirror.sh --force     # hepsini koşulsuz kopyala
#   sync_verify_mirror.sh --check     # mirror güncel mi? (0 güncel/1 bayat/2 hata)
#   sync_verify_mirror.sh --list      # dosya eşlemesini bas (denetim için)
#   sync_verify_mirror.sh --help
#
# Ortam değişkenleri (override):
#   PREVIEW_MIRROR   preview mirror dizini (adım 2)
#                    (varsayılan: ~/Library/Caches/com.freebuff/preview)
#   MIRROR_DIR       verify mirror dizini (adım 4)
#                    (varsayılan: ~/Library/Caches/com.freebuff/verify)
#   LEAN_MIRROR_DIR  Lean mirror dizini (K9, adım 4)
#                    (varsayılan: ~/Library/Caches/com.freebuff/lean_reduct)
#   ROOT             repo kökü (varsayılan: script'in ../../)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
CIKTI="$ROOT/_calisma/CIKTI"
LEAN_SRC="$ROOT/_calisma/lean_reduct"

PREVIEW_MIRROR="${PREVIEW_MIRROR:-$HOME/Library/Caches/com.freebuff/preview}"
MIRROR_DIR="${MIRROR_DIR:-$HOME/Library/Caches/com.freebuff/verify}"
LEAN_MIRROR_DIR="${LEAN_MIRROR_DIR:-$HOME/Library/Caches/com.freebuff/lean_reduct}"

# (kaynak_rel | dest_rel) — kaynak CIKTI'ya, dest MIRROR_DIR'a göre.
# Sıra deterministic: her satır bir dosya; önce runtime, sonra zips.
FILES=(
  "verify_delivery.py|verify_delivery.py"
  "verify_delivery.config.json|verify_delivery.config.json"
  "verify_delivery.config.schema.json|verify_delivery.config.schema.json"
  "symbolic_proof_z3.py|symbolic_proof_z3.py"
  "verify_lean.sh|verify_lean.sh"
  "zip_lineage.json|zip_lineage.json"
  "gen_repro_manifest.py|gen_repro_manifest.py"
  "gen_config.py|gen_config.py"
  "cleanup_log.json|cleanup_log.json"
  "github_scripts_battery.py|github_scripts_battery.py"
  "github_scripts_selftest.js|github_scripts_selftest.js"
  "daemon_http_test.py|daemon_http_test.py"
  "preview_server.py|preview_server.py"
  "_daemonize.py|_daemonize.py"
  "preview.html|preview.html"
  "sw.js|sw.js"
  "fresh_clone_setup.sh|fresh_clone_setup.sh"
  "test_fresh_clone_setup.py|test_fresh_clone_setup.py"
  "update_preview.sh|update_preview.sh"
  "sync_check_unit_tests.py|sync_check_unit_tests.py"
  "check_unit_tests.list|check_unit_tests.list"
  "check_unit_tests_hook.sh|check_unit_tests_hook.sh"
  "github_scripts/config_diff_comment.js|github_scripts/config_diff_comment.js"
  "github_scripts/config_drift_comment.js|github_scripts/config_drift_comment.js"
  "github_scripts/label_gate.js|github_scripts/label_gate.js"
  "github_scripts/label_gate_p1.js|github_scripts/label_gate_p1.js"
  "github_scripts/commit_msg_gate.js|github_scripts/commit_msg_gate.js"
  "github_scripts/sync_labels.js|github_scripts/sync_labels.js"
  "github_scripts/validate_labels.js|github_scripts/validate_labels.js"
  "github_scripts/manifest_comment.js|github_scripts/manifest_comment.js"
  "github_scripts/unit_test_failure_comment.js|github_scripts/unit_test_failure_comment.js"
  "github_scripts/pr_status_comment.js|github_scripts/pr_status_comment.js"
  "github_scripts/tum_sapmalar_comment.js|github_scripts/tum_sapmalar_comment.js"
  "TESLIM_KLASOR_V5_2026-08-17.zip|TESLIM_KLASOR_V5_2026-08-17.zip"
  "TESLIM_KLASOR_V5_2026-08-17.zip.sha256|TESLIM_KLASOR_V5_2026-08-17.zip.sha256"
  "TESLIM_V5_FINAL_2026-08-17.zip|TESLIM_V5_FINAL_2026-08-17.zip"
  "TESLIM_V5_FINAL_2026-08-17.zip.sha256|TESLIM_V5_FINAL_2026-08-17.zip.sha256"
)

# Lean dosyaları: kaynak LEAN_SRC'ye, dest LEAN_MIRROR_DIR'a göre.
# K9 iki kapılıdır: (1) ReductInvariance.lean meta-teoremi, (2) 8 teoremli
# Sınır İspatı çekirdeği — lake build --wfail (lean-toolchain v4.14.0).
# Bu yüzden lake projesinin TÜM kaynak dosyaları mirror'a gider; yalnızca
# ReductInvariance.lean senkronlanırsa mirror rotasında K9-LAKE P0 üretir
# (canlı dashboard FAIL — dashboard_smoke.sh bunu yakalamıştı).
LEAN_FILES=(
  "ReductInvariance.lean|ReductInvariance.lean"
  "lean-toolchain|lean-toolchain"
  "lakefile.toml|lakefile.toml"
  "Leibniz2Reduct.lean|Leibniz2Reduct.lean"
  "Leibniz2Reduct/Content.lean|Leibniz2Reduct/Content.lean"
  "Content.lean|Content.lean"
)

# Preview mirror dosyaları (adım 2): kaynak CIKTI'ya, dest PREVIEW_MIRROR'a
# göre. preview_server.py launchd GUI agent'ının çalıştırıcısıdır;
# _daemonize.py daemon modda kullanılır.
PREVIEW_FILES=(
  "preview_server.py|preview_server.py"
  "_daemonize.py|_daemonize.py"
  "preview_prestart.py|preview_prestart.py"
)

# Branch protection görsel kılavuzu (adım 2, preview mirror): kaynak repo
# köküne göre (docs/), dest PREVIEW_MIRROR'a. self-contained HTML — sunucu
# /guide.html rotasında PREVIEW_DIR/guide.html'den servis eder.
GUIDE_FILES=(
  "docs/branch-protection-guide/guide.html|guide.html"
)

say() { printf '%s\n' "$*"; }
err() { printf 'HATA: %s\n' "$*" >&2; }

git_short() {
  git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || printf '%s' "-"
}

# Tüm kaynakların var olduğunu doğrula (fail-closed). Eksik → stderr + return 1.
validate_sources() {
  local rc=0 src dst
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    if [ ! -f "$CIKTI/$src" ]; then
      err "kaynak yok: $CIKTI/$src"
      rc=1
    fi
  done < <(printf '%s\n' "${FILES[@]}")
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    if [ ! -f "$LEAN_SRC/$src" ]; then
      err "kaynak yok: $LEAN_SRC/$src"
      rc=1
    fi
  done < <(printf '%s\n' "${LEAN_FILES[@]}")
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    if [ ! -f "$CIKTI/$src" ]; then
      err "kaynak yok: $CIKTI/$src (preview)"
      rc=1
    fi
  done < <(printf '%s\n' "${PREVIEW_FILES[@]}")
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    if [ ! -f "$ROOT/$src" ]; then
      err "kaynak yok: $ROOT/$src (guide)"
      rc=1
    fi
  done < <(printf '%s\n' "${GUIDE_FILES[@]}")
  return "$rc"
}

# Tek dosya: dest var ve içerik aynı mı? (0 aynı / 1 farklı/eksik)
same_file() {
  [ -f "$2" ] && cmp -s "$1" "$2"
}

# Tek dosyayı kopyala (yalnızca değiştiyse). Döndürür: "GÜNCEL"/"GÜNCELLENDİ"/"YAZILDI".
sync_one() {
  local src="$1" dst="$2" mode="${3:-sync}"
  # Alt dizin hedefleri (github_scripts/…): hedef klasör yoksa cp başarısız
  # olur — önce oluştur (exit kodu set -e ile yakalanır).
  mkdir -p "$(dirname "$dst")"
  if [ "$mode" = "force" ]; then
    cp "$src" "$dst"
    printf 'GÜNCELLENDİ'
  elif same_file "$src" "$dst"; then
    printf 'GÜNCEL'
  else
    cp "$src" "$dst"
    printf 'GÜNCELLENDİ'
  fi
}

# Her eşleme için sync_one çalıştır; "(rel)" başına durum basar.
run_sync() {
  local mode="${1:-sync}" src dst st
  local changed=0 total=0
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    total=$((total + 1))
    st="$(sync_one "$CIKTI/$src" "$MIRROR_DIR/$dst" "$mode")"
    [ "$st" = "GÜNCELLENDİ" ] && changed=$((changed + 1))
    say "$st: $dst"
  done < <(printf '%s\n' "${FILES[@]}")
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    total=$((total + 1))
    st="$(sync_one "$LEAN_SRC/$src" "$LEAN_MIRROR_DIR/$dst" "$mode")"
    [ "$st" = "GÜNCELLENDİ" ] && changed=$((changed + 1))
    say "$st: lean_reduct/$dst"
  done < <(printf '%s\n' "${LEAN_FILES[@]}")
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    total=$((total + 1))
    st="$(sync_one "$CIKTI/$src" "$PREVIEW_MIRROR/$dst" "$mode")"
    [ "$st" = "GÜNCELLENDİ" ] && changed=$((changed + 1))
    say "$st: preview/$dst"
  done < <(printf '%s\n' "${PREVIEW_FILES[@]}")
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    total=$((total + 1))
    st="$(sync_one "$ROOT/$src" "$PREVIEW_MIRROR/$dst" "$mode")"
    [ "$st" = "GÜNCELLENDİ" ] && changed=$((changed + 1))
    say "$st: preview/$dst (guide)"
  done < <(printf '%s\n' "${GUIDE_FILES[@]}")
  say "ÖZET: $total dosya, $changed güncellendi · git $(git_short)"
}

# Her eşleme için aynılık denetimi (--check). Bayat dosya → stdout + return 1.
run_check() {
  local src dst stale=0
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    if same_file "$CIKTI/$src" "$MIRROR_DIR/$dst"; then
      say "GÜNCEL: $dst"
    else
      say "BAYAT/EKSİK: $dst"
      stale=1
    fi
  done < <(printf '%s\n' "${FILES[@]}")
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    if same_file "$LEAN_SRC/$src" "$LEAN_MIRROR_DIR/$dst"; then
      say "GÜNCEL: lean_reduct/$dst"
    else
      say "BAYAT/EKSİK: lean_reduct/$dst"
      stale=1
    fi
  done < <(printf '%s\n' "${LEAN_FILES[@]}")
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    if same_file "$CIKTI/$src" "$PREVIEW_MIRROR/$dst"; then
      say "GÜNCEL: preview/$dst"
    else
      say "BAYAT/EKSİK: preview/$dst"
      stale=1
    fi
  done < <(printf '%s\n' "${PREVIEW_FILES[@]}")
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    if same_file "$ROOT/$src" "$PREVIEW_MIRROR/$dst"; then
      say "GÜNCEL: preview/$dst (guide)"
    else
      say "BAYAT/EKSİK: preview/$dst (guide)"
      stale=1
    fi
  done < <(printf '%s\n' "${GUIDE_FILES[@]}")
  return "$stale"
}

run_list() {
  local src dst
  say "PREVIEW_MIRROR  = $PREVIEW_MIRROR"
  say "MIRROR_DIR      = $MIRROR_DIR"
  say "LEAN_MIRROR_DIR = $LEAN_MIRROR_DIR"
  say "CIKTI           = $CIKTI"
  say "LEAN_SRC        = $LEAN_SRC"
  say "---"
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    say "$CIKTI/$src -> $MIRROR_DIR/$dst"
  done < <(printf '%s\n' "${FILES[@]}")
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    say "$LEAN_SRC/$src -> $LEAN_MIRROR_DIR/$dst"
  done < <(printf '%s\n' "${LEAN_FILES[@]}")
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    say "$CIKTI/$src -> $PREVIEW_MIRROR/$dst"
  done < <(printf '%s\n' "${PREVIEW_FILES[@]}")
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    say "$ROOT/$src -> $PREVIEW_MIRROR/$dst (guide)"
  done < <(printf '%s\n' "${GUIDE_FILES[@]}")
}

usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"
}

main() {
  local mode="${1:-sync}"
  case "$mode" in
    --help|-h)
      usage
      exit 0
      ;;
    --list)
      run_list
      exit 0
      ;;
    --check)
      validate_sources || exit 2
      mkdir -p "$PREVIEW_MIRROR" "$MIRROR_DIR" "$LEAN_MIRROR_DIR"
      if run_check; then
        say "SONUÇ: mirror güncel · git $(git_short)"
        exit 0
      else
        say "SONUÇ: mirror BAYAT — 'sync_verify_mirror.sh' çalıştırın"
        exit 1
      fi
      ;;
    --force)
      validate_sources || exit 2
      mkdir -p "$PREVIEW_MIRROR" "$MIRROR_DIR" "$LEAN_MIRROR_DIR"
      run_sync force
      exit 0
      ;;
    sync)
      validate_sources || exit 2
      mkdir -p "$PREVIEW_MIRROR" "$MIRROR_DIR" "$LEAN_MIRROR_DIR"
      run_sync sync
      exit 0
      ;;
    *)
      err "bilinmeyen mod: $mode (--help)"
      exit 2
      ;;
  esac
}

main "$@"
