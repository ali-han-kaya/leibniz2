#!/usr/bin/env bash
#
# ci_repack_test.sh — repack-verify job'unun fresh-clone simülasyonu (tek komut).
#
# GitHub Actions'taki `repack-verify` job'unu yerelde birebir replay eder:
#   1) HEAD'in izole bir worktree kopyası (CI `actions/checkout` karşılığı)
#   2) repack_delivery.py --verify  (deterministik repack + sidecar bütünlüğü)
#   3) byte-identical kapısı: git diff --exit-code (commit'li ↔ repack çıktısı)
#   4) önce/sonra SHA-256 kanıtı (HEAD hash ↔ repack hash)
#   5) base verify K1-K7 (repack'lenmiş paket üzerinde, tek log)
#
# Çalışma ağacını KİRLETMEZ: tüm adımlar geçici bir worktree'de koşar, sonunda
# worktree kaldırılır. Rapor + kanıt gitignored sim dizinine yazılır:
#   <repo>/.freebuff/sim/repack_verify/repack_verify_report.txt
#   <repo>/.freebuff/sim/repack_verify/byte_identical_proof.md
#
# Kullanım:
#   bash _calisma/CIKTI/ci_repack_test.sh
#   KEEP_WORKTREE=1 bash _calisma/CIKTI/ci_repack_test.sh   # worktree'yi sakla
#
# Fail-closed (CI ile aynı): repack --verify, byte-identical veya base verify
# P0/P1 üretirse exit 1.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SIM_DIR="$REPO_ROOT/.freebuff/sim/repack_verify"

OUTER_ZIP="TESLIM_KLASOR_V5_2026-08-17.zip"
INNER_ZIP="TESLIM_V5_FINAL_2026-08-17.zip"

# Python: repack + base verify stdlib-only; venv varsa o, yoksa python3.
if [ -x "$REPO_ROOT/_calisma/.venv_z3/bin/python" ]; then
  PY="$REPO_ROOT/_calisma/.venv_z3/bin/python"
else
  PY=python3
fi

# SHA-256: CI `sha256sum` kullanır; macOS'ta yoksa `shasum -a 256`.
if command -v sha256sum >/dev/null 2>&1; then
  hash_file() { sha256sum "$1" | awk '{print $1}'; }
else
  hash_file() { shasum -a 256 "$1" | awk '{print $1}'; }
fi

WT_DIR=""

cleanup() {
  # KEEP_WORKTREE=1 → worktree incelenmek üzere bırakılır (yol özetlenir).
  if [ "${KEEP_WORKTREE:-0}" = "1" ]; then
    return 0
  fi
  if [ -n "$WT_DIR" ] && [ -d "$WT_DIR" ]; then
    git -C "$REPO_ROOT" worktree remove --force "$WT_DIR" 2>/dev/null || true
  fi
}
trap cleanup EXIT

main() {
  local report="$SIM_DIR/repack_verify_report.txt"
  local proof="$SIM_DIR/byte_identical_proof.md"
  mkdir -p "$SIM_DIR"

  echo "═══ REPACK-VERIFY FRESH-CLONE SİMÜLASYONU ═══"
  echo "REPO : $REPO_ROOT"
  echo "PY   : $PY ($("$PY" --version 2>&1))"
  echo "SIM  : $SIM_DIR"

  # 1) fresh worktree (CI checkout karşılığı)
  WT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ci_repack_test.XXXXXX")"
  rmdir "$WT_DIR"  # git worktree add yolu kendisi yaratır
  echo ""
  echo "── ADIM 1: fresh worktree (HEAD) ──"
  if ! git -C "$REPO_ROOT" worktree add --detach "$WT_DIR" HEAD; then
    echo "HATA: worktree açılamadı (HEAD)." >&2
    return 1
  fi
  echo "worktree: $WT_DIR"

  local rc=0

  # 2) repack --verify (deterministik + sidecar bütünlüğü)
  echo ""
  echo "── ADIM 2: repack_delivery.py --verify ──"
  if ! (cd "$WT_DIR" && "$PY" _calisma/repack_delivery.py --verify); then
    echo "HATA: repack --verify FAIL (sidecar bütünlüğü bozuk)." >&2
    rc=1
  fi

  # 3) byte-identical kapısı (CI'daki git diff gate)
  echo ""
  echo "── ADIM 3: byte-identical (git diff) ──"
  if ! (cd "$WT_DIR" && git diff --exit-code -- \
         _calisma/CIKTI/ _calisma/V5_ICERIK/ _calisma/TESLIM/); then
    echo "HATA: repack çıktısı commit'li dosyalarla byte-identical DEĞİL." >&2
    (cd "$WT_DIR" && git diff --stat -- \
       _calisma/CIKTI/ _calisma/V5_ICERIK/ _calisma/TESLIM/)
    rc=1
  else
    echo "byte-identical OK: commit'li dosyalar ↔ repack çıktısı aynı."
  fi

  # 4) önce/sonra SHA-256 kanıtı (tam hash, kısaltılmamış)
  echo ""
  echo "── ADIM 4: önce/sonra SHA-256 kanıtı ──"
  {
    echo "## Repack byte-identical kanıtı (önce/sonra SHA-256)"
    echo
    echo "| Dosya | before (HEAD) | after (repack) | Sonuç |"
    echo "|---|---|---|---|"
  } > "$proof"
  local identical=0 total=0
  for z in "$OUTER_ZIP" "$INNER_ZIP"; do
    local tmp_before before after verdict
    tmp_before="$(mktemp)"
    git -C "$WT_DIR" show "HEAD:_calisma/CIKTI/$z" > "$tmp_before" 2>/dev/null
    before="$(hash_file "$tmp_before")"
    rm -f "$tmp_before"
    after="$(hash_file "$WT_DIR/_calisma/CIKTI/$z")"
    total=$((total + 1))
    if [ "$before" = "$after" ]; then
      verdict="✅ identical"
      identical=$((identical + 1))
    else
      verdict="❌ DIFF"
      rc=1
    fi
    echo "| \`$z\` | \`$before\` | \`$after\` | $verdict |" >> "$proof"
  done
  {
    echo
    echo "**SONUÇ:** $identical/$total zip byte-identical (HEAD ↔ repack çıktısı)."
  } >> "$proof"
  cat "$proof"

  # 5) base verify K1-K7 (repack'lenmiş paket üzerinde)
  echo ""
  echo "── ADIM 5: base verify K1-K7 ──"
  if ! (cd "$WT_DIR" && "$PY" _calisma/CIKTI/verify_delivery.py \
         --dir _calisma/CIKTI 2>&1 | tee "$report"); then
    echo "HATA: base verify FAIL (P0/P1 var)." >&2
    rc=1
  fi

  echo ""
  echo "════════════════════════════════════════════════════════"
  if [ "$rc" -eq 0 ]; then
    echo "SONUÇ: PASS — repack deterministik + byte-identical + base verify yeşil."
  else
    echo "SONUÇ: FAIL — yukarıdaki adım(lar)dan biri başarısız."
  fi
  echo "Rapor : $report"
  echo "Kanıt : $proof"
  if [ "${KEEP_WORKTREE:-0}" = "1" ]; then
    echo "Worktree (saklandı): $WT_DIR"
  fi
  echo "════════════════════════════════════════════════════════"
  return "$rc"
}

main "$@"
