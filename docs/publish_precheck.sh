#!/usr/bin/env bash
#
# publish_precheck.sh — docs/PUBLISH_SCENARIO.md AŞAMA 0 ön-kontrolü (tek komut).
#
# Kullanım:
#   bash docs/publish_precheck.sh                 # ilk publish (remote boş beklenir)
#   bash docs/publish_precheck.sh --allow-remote  # repo zaten GitHub'da (incremental push öncesi)
#   bash docs/publish_precheck.sh --skip-smoke    # smoke testi atla (commit oluşturmaz)
#   bash docs/publish_precheck.sh --ci            # CI advisory job: yerel-only kontrolleri INFO yapar
#
# Her kontrol [PASS]/[FAIL] raporlanır; herhangi bir FAIL → exit 1 (fail-closed):
# senaryonun AŞAMA 1'ine ancak tüm kapılar yeşilse geçilir.
# AŞAMA 0'ın manuel karşılığı: docs/PUBLISH_SCENARIO.md → "AŞAMA 0".
set -uo pipefail

FAILED=0
pass() { printf '  [PASS] %s\n' "$*"; }
fail() { printf '  [FAIL] %s\n' "$*"; FAILED=1; }
warn() { printf '  [UYARI] %s\n' "$*"; }
info() { printf '  [INFO] %s\n' "$*"; }

ALLOW_REMOTE=0
SKIP_SMOKE=0
CI_MODE=0
for a in "$@"; do
  case "$a" in
    --allow-remote) ALLOW_REMOTE=1 ;;
    --skip-smoke)   SKIP_SMOKE=1 ;;
    --ci)           CI_MODE=1 ;;
    *) echo "Bilinmeyen bayrak: $a (geçerli: --allow-remote, --skip-smoke, --ci)" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# status_checks.py PyYAML ister — venv'de varsa onu kullan (yoksa python3).
if [ -x _calisma/.venv_z3/bin/python ]; then
  PY=_calisma/.venv_z3/bin/python
else
  PY=python3
fi

echo "════════════ AŞAMA 0 — Publish ön-kontrolü ════════════"

# ── (a) Repo + working tree + history ─────────────────────────────────────
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  pass "git repo mevcut: $REPO_ROOT"
else
  fail "git repo yok: $REPO_ROOT"
fi

if [ -z "$(git status --porcelain)" ]; then
  pass "working tree temiz"
else
  fail "working tree temiz değil — önce commit/stash et (git status --short)"
fi

# History'deki noise/marker başlıklar (commit-msg hook'uyla AYNI ölçüt).
if git log --oneline -5 | grep -qiE "test marker|^test:|^wip|^smoke"; then
  fail "son 5 commit'te noise/marker başlık var — temizle (docs/HISTORY_CLEANUP.md)"
else
  pass "son 5 commit temiz (noise/marker yok)"
fi

BRANCH="$(git branch --show-current 2>/dev/null || echo "")"
if [ "$BRANCH" = "main" ]; then
  pass "branch: main"
elif [ "$CI_MODE" = "1" ]; then
  info "branch: '$BRANCH' (CI — event branch'i; main push'unda 'main' olur)"
else
  fail "branch '$BRANCH' — 'main' olmalı"
fi

# ── (a2) Commit mesaj kuralı kurulu (docs/HISTORY_CLEANUP.md) ──────────────
# CI modunda bu kontroller anlamsızdır: runner'da hook kurulu değildir ama 5
# kapı verify job'unda `pre-commit run --all-files` + commit-msg CI denetimi
# ile zaten koşar. Yerel-only olduklarından INFO ile işaretlenir (FAIL değil).
if [ "$CI_MODE" = "1" ]; then
  info "(CI) hook kurulum kontrolü atlandı — pre-commit verify job'unda koşar; commit.template kurulumu yerel içindir (setup_commit_hooks.sh)"
else
  TMPL="$(git config commit.template || true)"
  if [ "$TMPL" = ".gitmessage" ] && [ -f .gitmessage ]; then
    pass "commit.template = .gitmessage"
  else
    fail "commit.template kurulu değil: git config commit.template .gitmessage"
  fi
  if [ -x .git/hooks/commit-msg ]; then
    pass "commit-msg git hook'u kurulu"
  else
    fail "commit-msg hook'u yok: pre-commit install --hook-type commit-msg"
  fi
  if [ -x .git/hooks/pre-commit ]; then
    pass "pre-commit git hook'u kurulu"
  else
    fail "pre-commit hook'u yok: pre-commit install"
  fi
fi

# ── (b) Pre-commit smoke test — GÜVENLİ ───────────────────────────────────
# Yalnızca tree temizse ve daha önce FAIL yoksa koşar. Başarısızsa commit
# oluşmaz; başarılıysa SMOKE_BEFORE'a reset atılır (doc'taki `reset --hard
# HEAD^` hatasını tekrarlamaz — HEAD'i kendisi geri alır).
if [ "$CI_MODE" = "1" ]; then
  info "smoke testi CI modunda atlanır — 5 kapı verify job'unda koşuyor (pre-commit run --all-files + commit-msg CI denetimi)"
elif [ "$SKIP_SMOKE" = "1" ]; then
  warn "smoke testi --skip-smoke ile atlandı"
elif [ "$FAILED" -ne 0 ] || [ -n "$(git status --porcelain)" ]; then
  warn "smoke testi atlandı (önceki FAIL veya kirli tree)"
else
  SMOKE_BEFORE="$(git rev-parse HEAD)"
  if git commit --allow-empty -m "docs: pre-commit smoke test" >/dev/null 2>&1; then
    git reset --hard "$SMOKE_BEFORE" >/dev/null 2>&1
    if [ "$(git rev-parse HEAD)" = "$SMOKE_BEFORE" ]; then
      pass "pre-commit smoke: 5 kapı (update-config/verify-delivery/Z3/Lean/commit-msg)"
    else
      fail "smoke sonrası HEAD geri alınamadı"
    fi
  else
    fail "pre-commit smoke FAIL — kapı kırmızı; önce yeşile çevir"
  fi
fi

# ── (c) gh CLI + auth ─────────────────────────────────────────────────────
if command -v gh >/dev/null 2>&1; then
  pass "gh CLI kurulu ($(gh --version 2>/dev/null | head -1 | awk '{print $3}'))"
  if [ "$CI_MODE" = "1" ]; then
    # CI: GH_TOKEN env token'ı — `gh auth status` env-token'ı her zaman
    # göstermeyebilir; gerçek API erişimini `gh api user` ile doğrula.
    if gh api user >/dev/null 2>&1; then
      pass "gh auth: $(gh api user -q .login 2>/dev/null || echo '?')"
    else
      fail "gh auth yok — workflow GH_TOKEN env'i set etmeli (github.token)"
    fi
  elif gh auth status >/dev/null 2>&1; then
    pass "gh auth: $(gh api user -q .login 2>/dev/null || echo '?')"
  else
    fail "gh auth yok — 'gh auth login' çalıştır"
  fi
else
  fail "gh CLI kurulu değil (brew install gh)"
fi

# ── (d) Remote + upstream durumu ──────────────────────────────────────────
REMOTE="$(git remote -v | head -1)"
if [ -n "$REMOTE" ]; then
  if [ "$ALLOW_REMOTE" = "1" ]; then
    pass "remote mevcut (--allow-remote): $REMOTE"
  else
    fail "remote zaten var — ilk publish için boş olmalı: $REMOTE"
  fi
else
  pass "remote yok"
fi

if git rev-parse --verify origin/main >/dev/null 2>&1; then
  AHEAD="$(git rev-list --count origin/main..main 2>/dev/null || echo '?')"
  BEHIND="$(git rev-list --count main..origin/main 2>/dev/null || echo '?')"
  if [ "$AHEAD" = "0" ] && [ "$BEHIND" = "0" ]; then
    pass "origin/main ile eşit (push bekleyen yok)"
  else
    warn "origin/main: $BEHIND geride / $AHEAD önde (incremental push)"
  fi
else
  info "origin/main yok (henüz push edilmemiş)"
fi

# ── (e) Status check adları — TEK KAYNAK: workflow job name'leri ──────────
# status_checks.py, verify.yml'deki job `name:` alanlarından required check
# adaylarını üretir (manifest-comment hariç). --gh ile GitHub branch
# protection'daki gerçek liste karşılaştırılır: eksik/fazla = FAIL (drift),
# koruma kurulu değilse UYARI (publish öncesi normal).
SC_OUT="$(mktemp)"
if "$PY" _calisma/CIKTI/status_checks.py >"$SC_OUT" 2>&1; then
  N="$(grep -cE '^  +[0-9]+\. ' "$SC_OUT")"
  pass "status check adları workflow'dan türetildi ($N kapı)"
else
  fail "status_checks.py çalışmadı — $(tail -1 "$SC_OUT")"
fi
if [ "$ALLOW_REMOTE" = "1" ] && command -v gh >/dev/null 2>&1; then
  if "$PY" _calisma/CIKTI/status_checks.py --gh >"$SC_OUT" 2>&1; then
    if grep -q "SONUÇ: PASS" "$SC_OUT"; then
      pass "branch protection: workflow ↔ GitHub birebir eşleşiyor"
    elif grep -q "UYARI: branch protection" "$SC_OUT"; then
      warn "branch protection kurulu değil — AŞAMA 1 (b) web UI'da kur"
    else
      info "branch protection durumu: $(grep -E 'SONUÇ|UYARI' "$SC_OUT" | head -1)"
    fi
  else
    fail "branch protection uyumsuz — _calisma/CIKTI/status_checks.py --gh"
  fi
else
  info "branch protection GitHub doğrulaması atlandı (--allow-remote + gh gerekli)"
fi
rm -f "$SC_OUT"

# ── Sonuç ─────────────────────────────────────────────────────────────────
echo ""
if [ "$FAILED" -eq 0 ]; then
  echo "SONUÇ: PASS ✓ — AŞAMA 1'e geçilebilir"
  exit 0
else
  echo "SONUÇ: FAIL ✗ — yukarıdaki [FAIL] satırlarını düzelt, tekrar çalıştır"
  exit 1
fi
