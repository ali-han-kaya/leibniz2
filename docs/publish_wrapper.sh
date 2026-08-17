#!/usr/bin/env bash
#
# publish_wrapper.sh — docs/PUBLISH_SCENARIO.md'yi TEK KOMUTLA, interaktif
# olmadan çalıştırır ve tüm çıktıyı loglar.
#
# Kullanım:
#   ./docs/publish_wrapper.sh                # AŞAMA 0-3 (ana publish akışı)
#   ./docs/publish_wrapper.sh --with-stage4   # AŞAMA 0-4 (opsiyonel koruma testi)
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
WITH_STAGE4="${1:-}"

mkdir -p "$LOG_DIR"

# Tüm stdout + stderr'i hem terminale hem log dosyasına yaz.
exec > >(tee -a "$LOG") 2>&1

log()  { echo "[$(date +%H:%M:%S)] $*"; }
fail() { log "HATA: $*"; log "SONUÇ: FAIL — log: $LOG"; exit 1; }
step() { echo ""; log "===== $* ====="; }

log "publish_wrapper.sh başladı"
log "repo_root: $REPO_ROOT · repo_name: $REPO_NAME · log: $LOG"

# ─────────────────────────────────────────────────────────────────────────────
step "AŞAMA 0 — Ön-kontrol"

# (a) Repo temiz + history temiz mi?
if [ -n "$(git status --short)" ]; then
  fail "working tree temiz değil — önce commit/stash et"
fi
log "git status: temiz ✓"

git log --oneline -5 | sed 's/^/    /'
if git log --oneline | grep -qiE "test marker"; then
  fail "history'de test-marker commit'i var — önce rebase ile temizle"
fi
log "history: temiz (test-marker yok) ✓"

# (b) pre-commit smoke test — GÜVENLİ: başarısızsa commit oluşmaz, reset atılmaz.
#     (doc'taki `git reset --hard HEAD^` hatasını tekrarlamaz.)
SMOKE_BEFORE="$(git rev-parse HEAD)"
if git commit --allow-empty -m "smoke: empty commit pre-commit test"; then
  git reset --hard "$SMOKE_BEFORE" >/dev/null
  log "pre-commit smoke: PASS ✓"
else
  fail "pre-commit smoke: FAIL — kapı kırmızı (genellikle K0/toolkit zip). Önce yeşile çevir."
fi

# (c) gh CLI + auth
command -v gh >/dev/null 2>&1 || fail "gh CLI kurulu değil (brew install gh)"
gh --version | head -1 | sed 's/^/    /'
gh auth status >/dev/null 2>&1 || fail "gh auth yok — önce 'gh auth login'"
OWNER="$(gh api user -q .login 2>/dev/null || true)"
[ -n "$OWNER" ] || fail "gh kullanıcı adı alınamadı"
log "gh auth: $OWNER ✓"

# (d) remote yokluğu + branch
if [ -n "$(git remote -v)" ]; then
  fail "remote zaten var: $(git remote -v)"
fi
log "remote: yok ✓"
BRANCH="$(git branch --show-current)"
[ "$BRANCH" = "main" ] || fail "branch '$BRANCH' — 'main' olmalı"
log "branch: $BRANCH ✓"

# ─────────────────────────────────────────────────────────────────────────────
step "AŞAMA 1 — GitHub repo oluştur (interaktif değil)"

# gh repo create: isim + --public verildiğinde prompt sormaz (non-interactive).
gh repo create "$REPO_NAME" \
  --description "$DESCRIPTION" \
  --public \
  --disable-wiki
log "repo oluşturuldu: $OWNER/$REPO_NAME ✓"

# Branch protection artık web UI üzerinden (manuel). Linki logla + hatırlat:
# ilk push'tan SONRA kurmak daha pratiktir (enforce-admins ilk push'u bloke edebilir).
log "branch protection (manuel, push sonrası):"
log "    https://github.com/$OWNER/$REPO_NAME/settings/branches"

# ─────────────────────────────────────────────────────────────────────────────
step "AŞAMA 2 — Remote ekle + push"

gh repo set-default "$REPO_NAME" >/dev/null 2>&1 || true
git remote add origin "git@github.com:$OWNER/$REPO_NAME.git"
git remote -v | sed 's/^/    /'
git push -u origin main
log "push tamamlandı: $OWNER/$REPO_NAME (main) ✓"

# ─────────────────────────────────────────────────────────────────────────────
step "AŞAMA 3 — CI çalıştığını doğrula (5-15 dk)"


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

# ─────────────────────────────────────────────────────────────────────────────
if [ "$WITH_STAGE4" = "--with-stage4" ]; then
  step "AŞAMA 4 (opsiyonel) — Branch protection'ın çalıştığını kanıtla"

  git checkout -b test/protection-check
  echo "protection smoke $(date +%s)" > protection_smoke.md
  git add protection_smoke.md
  # --no-verify: bu test uzak branch korumasını denetler, yerel pre-commit
  # kapısını değil (yerel kapı K0 yüzünden kırmızı olabilir — alakasız).
  git commit --no-verify -m "test: should be blocked by protection" || {
    git checkout main
    git branch -D test/protection-check >/dev/null 2>&1 || true
    rm -f protection_smoke.md
    fail "AŞAMA 4 test commit'i oluşturulamadı"
  }
  git push origin test/protection-check
  gh pr create --base main --head test/protection-check \
    --title "test: protection" --body "otomatik wrapper testi" >/dev/null

  # Merge denenir; koruma aktifse reddedilmeli.
  set +e
  gh pr merge --squash --delete-branch >/dev/null 2>&1
  MERGE_EXIT=$?
  set -e
  if [ "$MERGE_EXIT" -eq 0 ]; then
    log "UYARI: PR merge EDİLDİ — branch protection ÇALIŞMIYOR olabilir"
  else
    log "branch protection çalışıyor ✓ (merge reddedildi, exit=$MERGE_EXIT)"
  fi

  git checkout main
  git branch -D test/protection-check >/dev/null 2>&1 || true
  rm -f protection_smoke.md
  gh pr close test/protection-check >/dev/null 2>&1 || true
else
  step "AŞAMA 4 (opsiyonel) — atlandı (çalıştırmak için: --with-stage4)"
fi

# ─────────────────────────────────────────────────────────────────────────────
step "SONUÇ"

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
