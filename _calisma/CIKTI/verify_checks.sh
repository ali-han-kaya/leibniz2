#!/usr/bin/env bash
#
# verify_checks.sh — AŞAMA 1 doğrulamasının TEK KAYNAK fonksiyonu.
#
# docs/publish_wrapper.sh (--verify-checks / AŞAMA 1 / INCREMENTAL AŞAMA 4) ve
# docs/publish_precheck.sh (--verify-checks) bu dosyayı source edip
# verify_checks()'i çağırır — iki giriş noktası arasında drift olmaması için
# (tek tanım, tek davranış).
#
# Çağıran tarafında tanımlıysa log/warn/fail kullanılır:
#   - publish_wrapper.sh:  log = zaman damgalı; fail = "SONUÇ: FAIL" + exit 1
#   - publish_precheck.sh: info/warn/fail = [INFO]/[UYARI]/[FAIL] biçimi;
#                          fail yalnızca FAILED=1 işaretler (exit etmez)
# Tanımlı değilse (test/sourcing güvenliği) burada yerel fallback'ler kurulur.
# REPO_NAME/DRY_RUN çağıran tanımlıysa kullanılır; yoksa yerel varsayılanlar.
#
# verify_checks() dönüş kodları:
#   0 — PASS (birebir eşleşme) VEYA koruma kurulu değil/okunamadı (UYARI;
#       publish öncesi normal — "kapı henüz yok" demektir)
#   1 — gerçek drift (eksik/fazla check) veya status_checks.py çalışmadı
#
# Bağımlılık: status_checks.py (PyYAML ister) + gh CLI + auth.
set -u

if ! declare -F log >/dev/null 2>&1; then
  log() { echo "[$(date +%H:%M:%S)] $*"; }
fi
if ! declare -F warn >/dev/null 2>&1; then
  warn() { log "UYARI: $*"; }
fi
if ! declare -F fail >/dev/null 2>&1; then
  fail() { echo "HATA: $*" >&2; exit 1; }
fi

verify_checks() {
  # gh kullanıcısı (repo linki için) — yoksa boş (auth hatası ayrı kapıdır;
  # burada yalnızca bilgi amaçlı).
  local owner
  owner="$(gh api user -q .login 2>/dev/null || true)"
  local repo_name="${REPO_NAME:-$(basename "$(pwd)")}"

  # status_checks.py PyYAML ister — venv'de varsa onu kullan.
  # SC_PY GLOBAL kalır: publish_wrapper.sh'deki toggle_enforce() da kullanır.
  if [ -x _calisma/.venv_z3/bin/python ]; then
    SC_PY=_calisma/.venv_z3/bin/python
  else
    SC_PY=python3
  fi
  local sc_py="$SC_PY"

  log "status_checks.py — beklenen required check adları:"
  if ! "$sc_py" _calisma/CIKTI/status_checks.py | sed 's/^/    /'; then
    fail "status_checks.py çalışmadı — workflow job adları ayrıştırılamadı"
    return 1
  fi

  log "status_checks.py --gh — GitHub eşleşmesi:"
  local sc_gh_out="" sc_gh_exit=0
  # set -e (wrapper) ve set -e'siz (precheck/test) her iki bağlamda güvenli:
  # `if` koşulu set -e'yi tetiklemez, başarısız çağrının kodu $? ile yakalanır.
  if sc_gh_out="$("$sc_py" _calisma/CIKTI/status_checks.py --gh 2>&1)"; then
    sc_gh_exit=0
  else
    sc_gh_exit=$?
  fi
  echo "$sc_gh_out" | sed 's/^/    /'

  # status_checks.py --gh çıkış/verdict sözleşmesi:
  #   exit 0 + "SONUÇ: PASS"                     → birebir eşleşme
  #   exit 1 + "kurulu değil" (HTTP 404)         → NOT_SET_UP (UYARI)
  #   exit 1 + "erişilemedi" (403 yetki/ağ)      → UNREADABLE (UYARI)
  #   exit 1 (başka çıktı)                       → gerçek drift (fail-closed)
  if [ "$sc_gh_exit" -eq 0 ]; then
    if echo "$sc_gh_out" | grep -q "SONUÇ: PASS"; then
      log "branch protection birebir eşleşiyor ✓ (workflow ↔ GitHub)"
    else
      log "branch protection henüz kurulu değil — AŞAMA 1 (b) web UI'da kur (beklenen)"
    fi
  elif echo "$sc_gh_out" | grep -q "kurulu değil"; then
    warn "branch protection kurulu değil — AŞAMA 1 (b) web UI'da kur (gh api 404; publish öncesi normal)"
  elif echo "$sc_gh_out" | grep -q "erişilemedi"; then
    warn "branch protection okunamadı (yetki/ağ) — gerçek doğrulama yerelde gh auth ile yapılır (exit $sc_gh_exit)"
  elif [ "${DRY_RUN:-0}" = "1" ]; then
    warn "status_checks.py --gh dry-run'da GitHub'a ulaşamadı (repo yeni oluşturulacak?) — önizleme devam"
  else
    fail "status_checks.py --gh FAIL (exit $sc_gh_exit) — eksik/fazla check; listeyi workflow'la eşitle"
    return 1
  fi

  # Branch protection web UI üzerinden (manuel). Linki logla + hatırlat:
  # ilk push'tan SONRA kurmak daha pratiktir (enforce-admins ilk push'u
  # bloke edebilir).
  log "branch protection (manuel, push sonrası):"
  log "    https://github.com/$owner/$repo_name/settings/branches"
  log "sonrasında doğrulama (tekrar):    python3 _calisma/CIKTI/status_checks.py --gh"
  return 0
}
