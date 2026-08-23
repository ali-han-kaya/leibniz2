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

# VERIFY_CHECKS_OUT setse: makine-okur JSON sidecar'ı yaz (verdict/rc/note +
# status_checks.py --gh --json ham detayı). Çağıranlar (precheck/wrapper) bu
# env'i --verify-checks-out bayrağıyla doldurur; boşsa hiçbir şey yazılmaz.
# $1=sc_py  $2=verdict(PASS|WARN|FAIL)  $3=note
_verify_checks_write_sidecar() {
  local sc_py="$1" verdict="$2" note="$3"
  local out="${VERIFY_CHECKS_OUT:-}" json_tmp
  [ -n "$out" ] || return 0
  json_tmp="$(mktemp)"
  # Ham detay (verdict/missing/extra/smoke[]) — CI'da UNREADABLE/NOT_SET_UP de
  # gerçek durumu belgeler (exit 1 olabilir; if koşulu set -e'yi tetiklemez).
  if "$sc_py" _calisma/CIKTI/status_checks.py --gh --json >"$json_tmp" 2>/dev/null; then
    :
  fi
  SC_GH_JSON="$json_tmp" V_OUT="$out" V_VERDICT="$verdict" V_NOTE="$note" \
    "$sc_py" - <<'PY'
import json, os
from datetime import datetime, timezone

detail = {}
try:
    with open(os.environ["SC_GH_JSON"], encoding="utf-8") as f:
        detail = json.load(f)
except Exception as e:  # noqa: BLE001
    detail = {"error": f"status_checks --gh --json ayrıştırılamadı: {e}"}

verdict = os.environ["V_VERDICT"]
sidecar = {
    "tool": "verify_checks.sh",
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "rc": 0 if verdict != "FAIL" else 1,
    "verdict": verdict,
    "note": os.environ["V_NOTE"],
    "protection": detail,
}
out = os.environ["V_OUT"]
parent = os.path.dirname(os.path.abspath(out))
if parent:
    os.makedirs(parent, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(sidecar, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
  rm -f "$json_tmp"
}

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
  local sc_gh_out="" sc_gh_exit=0 vc_verdict="PASS" vc_note=""
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
      vc_verdict="PASS"; vc_note="birebir eşleşme (workflow ↔ GitHub)"
    else
      log "branch protection henüz kurulu değil — AŞAMA 1 (b) web UI'da kur (beklenen)"
      vc_verdict="WARN"; vc_note="branch protection kurulu değil (beklenen)"
    fi
  elif echo "$sc_gh_out" | grep -q "kurulu değil"; then
    warn "branch protection kurulu değil — AŞAMA 1 (b) web UI'da kur (gh api 404; publish öncesi normal)"
    vc_verdict="WARN"; vc_note="branch protection kurulu değil (gh api 404)"
  elif echo "$sc_gh_out" | grep -q "erişilemedi"; then
    warn "branch protection okunamadı (yetki/ağ) — gerçek doğrulama yerelde gh auth ile yapılır (exit $sc_gh_exit)"
    vc_verdict="WARN"; vc_note="branch protection okunamadı (yetki/ağ)"
  elif [ "${DRY_RUN:-0}" = "1" ]; then
    warn "status_checks.py --gh dry-run'da GitHub'a ulaşamadı (repo yeni oluşturulacak?) — önizleme devam"
    vc_verdict="WARN"; vc_note="dry-run — GitHub'a ulaşılamadı"
  else
    vc_verdict="FAIL"; vc_note="eksik/fazla check (exit $sc_gh_exit)"
    # Sidecar'ı fail()'den ÖNCE yaz — wrapper bağlamında fail exit 1 verir.
    _verify_checks_write_sidecar "$sc_py" "$vc_verdict" "$vc_note" \
      || warn "verify_checks sidecar yazılamadı"
    fail "status_checks.py --gh FAIL (exit $sc_gh_exit) — eksik/fazla check; listeyi workflow'la eşitle"
    return 1
  fi

  # Branch protection web UI üzerinden (manuel). Linki logla + hatırlat:
  # ilk push'tan SONRA kurmak daha pratiktir (enforce-admins ilk push'u
  # bloke edebilir).
  log "branch protection (manuel, push sonrası):"
  log "    https://github.com/$owner/$repo_name/settings/branches"
  log "sonrasında doğrulama (tekrar):    python3 _calisma/CIKTI/status_checks.py --gh"
  _verify_checks_write_sidecar "$sc_py" "$vc_verdict" "$vc_note" \
    || warn "verify_checks sidecar yazılamadı"
  return 0
}
