#!/usr/bin/env bash
#
# simulate_verify_job.sh — verify job'unun tek-giriş-noktası akışını yerelde
# compose-style replay eder (GitHub Actions olmadan uçtan uca test).
#
# Akış (verify.yml `verify` job'ının birebir yerel karşılığı):
#   1. --full (K1-K13: referans + Z3 + Lean + soy hattı + config drift +
#      repro manifest) → verify_report.txt + sidecar'lar
#   2. pre-commit run --all-files (advisory) → verify_report.txt'ye APPEND
#   3. gen_precommit_report.py → logs/PRECOMMIT_RAPORU.md
#   4. pre-commit cache + hook env özeti → logs/PRECOMMIT_CACHE.md
#   5-7. run_summary_{precommit,k0,budget} → GITHUB_STEP_SUMMARY (3 bölüm)
#   8. sha256sum → verify_report.sha256 + refs/history .sha256
#   9. config bundle → config/ + config.sha256
#   10. diff_config_artifacts.py → config/config-diff.json (advisory)
#
# Çıktılar REPO köküne DEĞİL gitignored bir sim dizinine yazılır
# (varsayılan: <repo>/.freebuff/sim/verify_job). Soy hattı `git show`'u
# gerçek repo kökünden çalıştırır — bu yüzden --full repo kökünde koşar,
# yalnızca sidecar'lar sim dizinine yönlendirilir.
#
# Kullanım:
#   bash _calisma/CIKTI/simulate_verify_job.sh            # varsayılan sim dizini
#   SIM_DIR=/tmp/vj bash _calisma/CIKTI/simulate_verify_job.sh
#
# Fail-closed adımlar başarısızsa son exit != 0; advisory adımlar yalnızca
# raporlanır (CI'daki continue-on-error karşılığı).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SIM_DIR="${SIM_DIR:-$REPO_ROOT/.freebuff/sim/verify_job}"

# K8 (Z3) venv python'ında; K9 (Lean) PATH'te. pre-commit de PATH'te.
if [ -x "$REPO_ROOT/_calisma/.venv_z3/bin/python" ]; then
  PY="$REPO_ROOT/_calisma/.venv_z3/bin/python"
else
  PY=python3
fi
# pre-commit: yerelde venv'de (CI'da pip install pre-commit ile PATH'te).
if [ -x "$REPO_ROOT/_calisma/.venv_z3/bin/pre-commit" ]; then
  PC="$REPO_ROOT/_calisma/.venv_z3/bin/pre-commit"
elif command -v pre-commit >/dev/null 2>&1; then
  PC="pre-commit"
else
  PC=""
fi
export PATH="$HOME/.elan/bin:/opt/homebrew/bin:$PATH"

# SHA-256 aracı: CI `sha256sum` kullanır; macOS'ta yoksa shasum'a düş.
if command -v sha256sum >/dev/null 2>&1; then
  SHA="sha256sum"
else
  SHA="shasum -a 256"
fi

# ── compose-style adım izleme ──────────────────────────────────────────────
declare -a STEP_NAMES=() STEP_CODES=() STEP_KINDS=()

run_step() {  # run_step <name> <kind:closed|advisory> <func>
  local name="$1" kind="$2" fn="$3"
  printf '\n════════════════════════════════════════════════════════\n'
  printf 'ADIM: %s  [%s]\n' "$name" "$kind"
  printf '════════════════════════════════════════════════════════\n'
  "$fn"
  local rc=$?
  STEP_NAMES+=("$name"); STEP_CODES+=("$rc"); STEP_KINDS+=("$kind")
  if [ "$rc" -eq 0 ]; then
    printf '── ADIM SONUCU: PASS (exit 0)\n'
  else
    printf '── ADIM SONUCU: FAIL (exit %s)  [%s]\n' "$rc" "$kind"
  fi
  return 0
}

# ── 1) --full (tek giriş noktası; fail-closed) ────────────────────────────
step_full() {
  cd "$REPO_ROOT"
  "$PY" _calisma/CIKTI/verify_delivery.py \
    --dir "$REPO_ROOT/_calisma/CIKTI" --full \
    --budget-out "$SIM_DIR/budget_verify.json" \
    --config-out "$SIM_DIR/effective_config.json" \
    --refs-out "$SIM_DIR/references_online.json" \
    --history-out "$SIM_DIR/history.jsonl" \
    --k0-out "$SIM_DIR/k0_findings.json" \
    --lineage-out "$SIM_DIR/lineage_findings.json" \
    --klayers-out "$SIM_DIR/klayers.json" 2>&1 | tee "$SIM_DIR/verify_report.txt"
  return "${PIPESTATUS[0]}"
}

# ── 2) pre-commit (advisory; çıktı verify_report.txt'ye append) ───────────
step_precommit() {
  cd "$REPO_ROOT"
  mkdir -p "$SIM_DIR/logs"
  if [ -z "$PC" ]; then
    echo "pre-commit bulunamadı (venv'de yok, PATH'te yok) — adım atlanıyor"
    return 127
  fi
  "$PC" run --all-files --show-diff-on-failure --color=never \
    > "$SIM_DIR/logs/precommit.log" 2>&1
  local status=$?
  echo "$status" > "$SIM_DIR/logs/precommit.exit"
  {
    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "PRECOMMIT (ADVISORY) — pre-commit run --all-files"
    echo "exit code: $status"
    echo "════════════════════════════════════════════════════════"
    cat "$SIM_DIR/logs/precommit.log"
  } >> "$SIM_DIR/verify_report.txt"
  cat "$SIM_DIR/logs/precommit.log"
  return "$status"
}

# ── 3) commit-msg (advisory) — commit geçmişi kural denetimi ──────────────
# CI'daki "Check commit messages (advisory)" adımıyla birebir: son N commit'i
# commit_msg_hook.sh ile denetler, ihlalleri logs/commit_msg_findings.json'a
# yazar. step_gen_report bu sidecar'ı PRECOMMIT_RAPORU'na ekler.
step_commit_msg() {
  cd "$SIM_DIR"
  "$PY" "$REPO_ROOT/_calisma/CIKTI/check_commit_messages.py" \
    --range "HEAD~10...HEAD" \
    --out "$SIM_DIR/logs/commit_msg_findings.json"
}

# ── 4) pre-commit bulgu raporu ─────────────────────────────────────────────
step_gen_report() {
  cd "$SIM_DIR"
  "$PY" "$REPO_ROOT/_calisma/CIKTI/gen_precommit_report.py"
}

# ── 4) pre-commit cache + hook env özeti ───────────────────────────────────
step_cache_summary() {
  cd "$SIM_DIR"
  {
    echo "# PRECOMMIT ORTAM ÖZETİ (cache + hook env)"
    echo ""
    echo "- **pre-commit sürümü:** $([ -n "$PC" ] && "$PC" --version 2>/dev/null || echo yok)"
    echo "- **Toplamak zamanı (UTC):** $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo ""
    echo "## Hook env sürümleri"
    echo ""
    echo "| Araç | Sürüm |"
    echo "|---|---|"
    echo "| python3 | $("$PY" --version 2>&1 | awk '{print $2}') |"
    echo "| pre-commit | $([ -n "$PC" ] && "$PC" --version 2>/dev/null | awk '{print $2}' || echo yok) |"
    echo "| z3 | $("$PY" -c 'import z3; print(z3.get_version_string())' 2>/dev/null || echo yok) |"
    echo "| lean | $(lean --version 2>/dev/null | head -1 || echo yok) |"
    echo ""
    echo "## pre-commit cache durumu"
    echo ""
    echo '```text'
    if [ -d "$HOME/.cache/pre-commit" ]; then
      echo "cache dizini: $HOME/.cache/pre-commit"
      du -sh "$HOME/.cache/pre-commit" 2>/dev/null
      ls -1 "$HOME/.cache/pre-commit" 2>/dev/null | head -20
    else
      echo "cache dizini yok: $HOME/.cache/pre-commit"
    fi
    echo '```'
  } > logs/PRECOMMIT_CACHE.md
  echo "PRECOMMIT_CACHE.md yazıldı"
}

# ── 5) run summary bölümleri (tek GITHUB_STEP_SUMMARY, tek giriş noktası) ──
# consolidate_summary.py pre-commit + K0 + bütçe + soy hattı + K katmanları
# bölümlerini AYNI summary.md'ye sırayla yazar (CI'daki tek adımla birebir).
step_consolidate_summary() {
  cd "$SIM_DIR"
  GITHUB_STEP_SUMMARY="$SIM_DIR/summary.md" \
    "$PY" "$REPO_ROOT/_calisma/CIKTI/consolidate_summary.py"
}

# ── 8) SHA-256 sidecar'ları ────────────────────────────────────────────────
step_sha256() {
  cd "$SIM_DIR"
  $SHA verify_report.txt budget_verify.json references_online.json \
    2>/dev/null > verify_report.sha256 || true
  $SHA references_online.json 2>/dev/null > references_online.json.sha256 || true
  $SHA history.jsonl 2>/dev/null > history.jsonl.sha256 || true
}

# ── 9) config bundle + config.sha256 ───────────────────────────────────────
step_config_bundle() {
  cd "$SIM_DIR"
  mkdir -p config
  cp "$REPO_ROOT/_calisma/CIKTI/verify_delivery.config.json"        config/
  cp "$REPO_ROOT/_calisma/CIKTI/verify_delivery.config.schema.json" config/
  cp effective_config.json config/ 2>/dev/null || true
  $SHA config/* 2>/dev/null > config/config.sha256 || true
}

# ── 10) config diff (advisory) ─────────────────────────────────────────────
step_config_diff() {
  cd "$SIM_DIR"
  "$PY" "$REPO_ROOT/_calisma/CIKTI/diff_config_artifacts.py" \
    --config-dir config --out-dir config
}

# ── main ───────────────────────────────────────────────────────────────────
main() {
  echo "═══ VERIFY JOB YEREL SİMÜLASYONU (compose-style) ═══"
  echo "REPO : $REPO_ROOT"
  echo "SIM  : $SIM_DIR"
  echo "PY   : $PY ($("$PY" --version 2>&1))"
  echo "SHA  : $SHA"
  echo ""

  rm -rf "$SIM_DIR"
  mkdir -p "$SIM_DIR/logs" "$SIM_DIR/config"

  run_step "Run full verification (K1-K13, single entry)" closed step_full
  run_step "Run pre-commit (advisory, --all-files)"      advisory step_precommit
  run_step "Check commit messages (advisory)"            advisory step_commit_msg
  run_step "Generate pre-commit findings report"         closed step_gen_report
  run_step "Pre-commit cache + hook env summary"         closed step_cache_summary
  run_step "Consolidate run summary (5 bölüm)"            closed step_consolidate_summary
  run_step "Generate SHA-256 for verify artifacts"       closed step_sha256
  run_step "Bundle config snapshot"                      closed step_config_bundle
  run_step "Generate config diff (advisory)"             advisory step_config_diff

  # ── compose özet tablosu ─────────────────────────────────────────────
  local fail_closed=0
  echo ""
  echo "════════════════════════════════════════════════════════"
  echo "COMPOSE ÖZETİ (adım → exit)"
  echo "════════════════════════════════════════════════════════"
  printf '%-48s %-9s %-8s %s\n' "ADIM" "TÜR" "EXIT" "SONUÇ"
  printf '%-48s %-9s %-8s %s\n' "────" "───" "────" "─────"
  local i
  for i in "${!STEP_NAMES[@]}"; do
    local rc="${STEP_CODES[$i]}" kind="${STEP_KINDS[$i]}"
    local res="PASS"
    [ "$rc" -ne 0 ] && res="FAIL"
    if [ "$rc" -ne 0 ] && [ "$kind" = "closed" ]; then
      fail_closed=1
    fi
    printf '%-48s %-9s %-8s %s\n' "${STEP_NAMES[$i]}" "$kind" "$rc" "$res"
  done
  echo ""

  echo "Çıktılar: $SIM_DIR"
  echo "  verify_report.txt        (--full + pre-commit append, tek log)"
  echo "  summary.md               (durum panosu + pre-commit + K0 + bütçe + soy hattı + K katmanları)"
  echo "  verify_report.sha256     (+ refs/history .sha256)"
  echo "  config/                  (ham + şema + etkin + diff + .sha256)"
  echo "  logs/                    (precommit.log + PRECOMMIT_RAPORU.md/.json + CACHE)"

  if [ "$fail_closed" -ne 0 ]; then
    echo ""
    echo "SONUÇ: FAIL (en az bir fail-closed adım başarısız)"
    return 1
  fi
  echo ""
  echo "SONUÇ: PASS (tüm fail-closed adımlar yeşil)"
  return 0
}

main "$@"
