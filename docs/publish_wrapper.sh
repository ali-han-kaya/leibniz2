#!/usr/bin/env bash
#
# publish_wrapper.sh — docs/PUBLISH_SCENARIO.md'yi TEK KOMUTLA, interaktif
# olmadan çalıştırır ve tüm çıktıyı loglar.
#
# Kullanım:
#   ./docs/publish_wrapper.sh                 # AŞAMA 0-3 (ana publish akışı)
#   ./docs/publish_wrapper.sh --with-stage4   # AŞAMA 0-4 (opsiyonel koruma testi)
#   ./docs/publish_wrapper.sh --dry-run       # GÜVENLİ PROVA: repo oluşturma,
#                                             # push, PR gibi kalıcı komutlar
#                                             # ÇALIŞTIRILMAZ; akış önizlenir
#   ./docs/publish_wrapper.sh --dry-run --with-stage4
#
# DRY-RUN: her kalıcı komut "[DRY-RUN] çalıştırılacak: ..." olarak basılır;
# AŞAMA 0 precheck --skip-smoke --allow-remote ile koşar (fail olsa bile akış
# önizlenmeye devam eder — hiçbir yan etki yoktur). Çıkış 0 (önizleme).
#
# Log: logs/publish_<timestamp>.log  (hem stdout'a hem dosyaya yazılır).
#
# GÜVENLİK:
#   - AŞAMA 0 kapıları (repo temiz, gh auth, remote yok, branch main) başarısız
#     olursa senaryo DURUR; `git push` yalnızca tüm kapılar yeşilse çalışır.
#   - Bu script'i çalıştırmak = publish senaryosunu onaylamak demektir
#     (GitHub'da PUBLIC repo oluşturur + push eder).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

REPO_NAME="leibniz2"
DESCRIPTION="Stoic-Hume V5 — fail-closed academic delivery with Z3 + Lean 4 proofs"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="$REPO_ROOT/logs"
LOG="$LOG_DIR/publish_${TIMESTAMP}.log"

WITH_STAGE4=0
DRY_RUN=0
for a in "$@"; do
  case "$a" in
    --with-stage4) WITH_STAGE4=1 ;;
    --dry-run)     DRY_RUN=1 ;;
    *) echo "Bilinmeyen bayrak: $a (geçerli: --with-stage4, --dry-run)" >&2; exit 2 ;;
  esac
done

mkdir -p "$LOG_DIR"

# Tüm stdout + stderr'i hem terminale hem log dosyasına yaz.
exec > >(tee -a "$LOG") 2>&1

log()  { echo "[$(date +%H:%M:%S)] $*"; }
warn() { log "UYARI: $*"; }
fail() { log "HATA: $*"; log "SONUÇ: FAIL — log: $LOG"; exit 1; }
step() { echo ""; log "===== $* ====="; }

# DRY-RUN'da komut ÇALIŞTIRILMAZ, yalnızca önizlenir (kalıcı etkisi yok).
run() {
  if [ "$DRY_RUN" = "1" ]; then
    log "[DRY-RUN] çalıştırılacak: $*"
    return 0
  fi
  "$@"
}

# DRY-RUN dışında tamamlanma mesajı basar (önizlemede yalnızca run() yeter).
done_msg() { [ "$DRY_RUN" = "1" ] || log "$*"; }

if [ "$DRY_RUN" = "1" ]; then
  log "publish_wrapper.sh DRY-RUN modunda — hiçbir komut çalıştırılmayacak"
else
  log "publish_wrapper.sh başladı"
fi
log "repo_root: $REPO_ROOT · repo_name: $REPO_NAME · log: $LOG"

# ─────────────────────────────────────────────────────────────────────────────
step "AŞAMA 0 — Ön-kontrol (publish_precheck.sh — tek komut)"

# AŞAMA 0'ın tamamı tek kaynak scriptte (docs/publish_precheck.sh): repo/tree/
# history temizliği + commit-msg kuralı + pre-commit smoke (5 kapı) + gh auth +
# branch/remote + status check adları. Herhangi bir FAIL → senaryo DURUR.
# Not: smoke testi artık commit-msg kuralına uygun mesajla koşar ("docs: ...");
# eski "smoke:" başlığı commit-msg-style hook'u tarafından reddedilir.
if [ "$DRY_RUN" = "1" ]; then
  log "[DRY-RUN] bash docs/publish_precheck.sh --skip-smoke --allow-remote"
  log "[DRY-RUN]   (dry-run'da smoke atlanır; remote zaten varsa toleranslı)"
  if bash docs/publish_precheck.sh --skip-smoke --allow-remote; then
    log "precheck: PASS ✓ (dry-run yine de devam ediyor)"
  else
    warn "precheck FAIL — dry-run olduğundan akış önizlenmeye devam ediyor"
  fi
else
  if ! bash docs/publish_precheck.sh; then
    fail "AŞAMA 0 kapıları geçilemedi — log: $LOG"
  fi
fi

# gh kullanıcısı AŞAMA 1/2 için gerekli (precheck içinde doğrulandı).
OWNER="$(gh api user -q .login 2>/dev/null || true)"

# ─────────────────────────────────────────────────────────────────────────────
step "AŞAMA 1 — GitHub repo oluştur (interaktif değil)"

# gh repo create: isim + --public verildiğinde prompt sormaz (non-interactive).
run gh repo create "$REPO_NAME" \
  --description "$DESCRIPTION" \
  --public \
  --disable-issues=false \
  --disable-wiki=true \
  --disable-projects=true \
  --add-readme=false
done_msg "repo oluşturuldu: $OWNER/$REPO_NAME ✓"

# Branch protection artık web UI üzerinden (manuel). Linki logla + hatırlat:
# ilk push'tan SONRA kurmak daha pratiktir (enforce-admins ilk push'u bloke edebilir).
log "branch protection (manuel, push sonrası):"
log "    https://github.com/$OWNER/$REPO_NAME/settings/branches"
log "required check adları otomatik: python3 _calisma/CIKTI/status_checks.py"
log "sonrasında doğrulama:            python3 _calisma/CIKTI/status_checks.py --gh"

# ─────────────────────────────────────────────────────────────────────────────
step "AŞAMA 2 — Remote ekle + push"

run gh repo set-default "$REPO_NAME" || true
run git remote add origin "git@github.com:$OWNER/$REPO_NAME.git"
log "remote -v: (güncel durum)"
git remote -v | sed 's/^/    /' || true
run git push -u origin main
done_msg "push tamamlandı: $OWNER/$REPO_NAME (main) ✓"

# ─────────────────────────────────────────────────────────────────────────────
step "AŞAMA 3 — CI çalıştığını doğrula (5-15 dk)"

if [ "$DRY_RUN" = "1" ]; then
  log "[DRY-RUN] push sonrası otomatik tetiklenen CI run'ı şöyle izlenir:"
  log "[DRY-RUN]   gh run list --limit 3 --json databaseId,status,conclusion,name"
  log "[DRY-RUN]   gh run watch <RUN_ID> --exit-status   (5-15 dk bloklar)"
  log "[DRY-RUN]   gh run view <RUN_ID> --json artifacts \\"
  log "[DRY-RUN]     --jq '.artifacts[] | \"\\(.name) (\\(.size_in_bytes) B)\"'"
  RUN_ID="" ; CONCL="(dry-run — çalıştırılmadı)"
else
  # Push'un tetiklediği run'ın listede görünmesini bekle (birkaç sn gecikebilir).
  RUN_ID=""
  for _ in $(seq 1 12); do
    RUN_ID="$(gh run list --limit 1 --json databaseId -q '.[0].databaseId' 2>/dev/null || true)"
    [ -n "$RUN_ID" ] && break
    sleep 5
  done
  [ -n "$RUN_ID" ] || fail "CI run listelenemedi (gh run list boş)"
  log "CI run ID: $RUN_ID"

  # Run bitene kadar izle (non-interactive). Sonuç FAIL olsa bile script'i
  # düşürmemek için exit kodu elle yakalanır (FAIL bir SONUÇ, script hatası değil).
  set +e
  gh run watch "$RUN_ID" --exit-status
  CI_EXIT=$?
  set -e
  CONCL="$(gh run view "$RUN_ID" --json conclusion -q '.conclusion' 2>/dev/null || echo "unknown")"
  log "CI sonucu: $CONCL (gh run watch exit=$CI_EXIT)"

  log "Artifact'lar:"
  gh run view "$RUN_ID" --json artifacts \
    --jq '.artifacts[] | "    \(.name) (\(.size_in_bytes) B)"' 2>/dev/null || true
fi

# ─────────────────────────────────────────────────────────────────────────────
if [ "$WITH_STAGE4" = "1" ]; then
  step "AŞAMA 4 (opsiyonel) — Branch protection'ın çalıştığını kanıtla"

  run git checkout -b test/protection-check
  if [ "$DRY_RUN" = "1" ]; then
    log "[DRY-RUN] marker dosyası oluşturulur + commit atılır:"
    log "[DRY-RUN]   printf '# protection smoke\\n' > _calisma/CIKTI/PROTECTION_SMOKE.md"
    log "[DRY-RUN]   git add _calisma/CIKTI/PROTECTION_SMOKE.md && git commit --no-verify"
  else
    # Doc ile aynı yol (PUBLISH_SCENARIO AŞAMA 4).
    printf '# protection smoke\n' > _calisma/CIKTI/PROTECTION_SMOKE.md
    git add _calisma/CIKTI/PROTECTION_SMOKE.md
    # --no-verify: bu test uzak branch korumasını denetler, yerel pre-commit
    # kapısını değil.
    git commit --no-verify -m "docs: protection smoke marker" || {
      git checkout main
      git branch -D test/protection-check >/dev/null 2>&1 || true
      rm -f _calisma/CIKTI/PROTECTION_SMOKE.md
      fail "AŞAMA 4 test commit'i oluşturulamadı"
    }
  fi
  run git push origin test/protection-check
  run gh pr create --base main --head test/protection-check \
    --title "docs: protection smoke" --body "otomatik wrapper testi"

  if [ "$DRY_RUN" = "1" ]; then
    log "[DRY-RUN] merge denenir: gh pr merge --squash --delete-branch"
    log "[DRY-RUN]   (beklenen: required check'ler TAMAMLANMADAN reddedilir)"
  else
    # Merge denenir; koruma aktifse reddedilmeli.
    set +e
    gh pr merge --squash --delete-branch >/dev/null 2>&1
    MERGE_EXIT=$?
    set -e
    if [ "$MERGE_EXIT" -eq 0 ]; then
      warn "PR merge EDİLDİ — branch protection ÇALIŞMIYOR olabilir"
    else
      log "branch protection çalışıyor ✓ (merge reddedildi, exit=$MERGE_EXIT)"
    fi
  fi

  run git checkout main
  if [ "$DRY_RUN" = "1" ]; then
    log "[DRY-RUN] temizlik: branch -D + marker sil + PR kapat + uzak branch sil"
  else
    git branch -D test/protection-check >/dev/null 2>&1 || true
    rm -f _calisma/CIKTI/PROTECTION_SMOKE.md
    gh pr close test/protection-check --comment "protection smoke sonlandı" >/dev/null 2>&1 || true
    git push origin --delete test/protection-check >/dev/null 2>&1 || true
  fi
else
  step "AŞAMA 4 (opsiyonel) — atlandı (çalıştırmak için: --with-stage4)"
fi

# ─────────────────────────────────────────────────────────────────────────────
step "SONUÇ"

if [ "$DRY_RUN" = "1" ]; then
  log "Repo:        https://github.com/$OWNER/$REPO_NAME  (dry-run — oluşturulmayacak)"
  log "CI run:      $RUN_ID (dry-run — çalıştırılmadı)"
  log "Log dosyası: $LOG"
  log "SONUÇ: DRY-RUN ✓ — hiçbir komut çalıştırılmadı (yalnızca önizleme)"
  exit 0
fi

log "Repo:        https://github.com/$OWNER/$REPO_NAME"
log "CI run:      $RUN_ID (sonuç: $CONCL)"
log "Artifacts:   https://github.com/$OWNER/$REPO_NAME/actions/runs/$RUN_ID"
log "Protection:  https://github.com/$OWNER/$REPO_NAME/settings/branches"
log "Log dosyası: $LOG"

if [ "${CONCL:-unknown}" = "success" ]; then
  log "SONUÇ: PASS ✓"
else
  log "SONUÇ: CI conclusion '$CONCL' — raporları incele (fail-closed kapı bir bulgu yakalamış olabilir)"
fi
