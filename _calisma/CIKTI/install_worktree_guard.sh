#!/usr/bin/env bash
# install_worktree_guard.sh — `.git/hooks/pre-commit` sarmalayıcısını kurar.
#
# NEDEN: pre-commit unstaged İZLENEN deltayı kendi cache'ine stash'ler,
# ağacı index'e eşitler ve geri-uygulamayı yalnız finally'deki
# `git apply`'e bırakır. Pencere-içi süreç-ölümü ya da apply-çakışması →
# ağaç sessizce revert olur, delta yalnız önbellekte kalır (2026-09-18
# revert-olayı; ~170 yetim patch). check_unstaged_delta.py bunu BLOKLAR
# ama yedek ALMAZ ve kayıp olduktan sonra OTOMATİK GERİ YÜKLEMEZ.
# Bu sarmalayıcı üç katmanlı kalıcı çözümün (precommit_worktree_guard.py)
# hook yüzeyidir: pencere AÇILMADAN yedekle → pre-commit'i koş →
# kapandıktan sonra doğrula/geri-yükle.
#
# Sarmalayıcı pre-commit'in KENDİ script'ini `.git/hooks/pre-commit.real`
# dosyasına taşır ve zinciri onun üzerinden koşar. `pre-commit install`
# her çalıştığında sarmalayıcıyı SİLER (pre-commit kendi hash'ini
# görmedikçe mevcut hook'u `.legacy`'e taşır) → kapı zinciri içinde
# check-worktree-guard-install bu dosyayı otomatik yeniden kurar
# (self-heal); bu betik yalnızca elle/kurulum anında çağrılır.
#
# UYARI (regresyon kaydı, 2026-10-21): sarmalayıcı gövdesi KESİNLEŞTİRİLMİŞ
# heredoc (<<'WRAP') ile yazılır. Önceki sürümde genişleyen heredoc
# (<<WRAP) kullanılmıştı; gövdeDEKİ backtick yorumları (`pre-commit install`
# gibi) o anda GERÇEKTEN ÇALIŞTI ve kurulum kendi hedef dosyasını
# 0 baytlık boş bir `.git/hooks/pre-commit` yaptı (ölçüldü: dosya 0 B,
# +x yok, zincir tamamen susmuş → sessiz fail-open). Tokenleştirme
# (@@GUARD@@/@@REAL@@/@@MARKER@@) genişlemeyi tümüyle ortadan kaldırır.
#
# Kullanım:
#   bash _calisma/CIKTI/install_worktree_guard.sh          # kur
#   bash _calisma/CIKTI/install_worktree_guard.sh --check  # kurulu mu? (0/1)
#   PRE_COMMIT_BIN=/path/pre-commit bash _calisma/CIKTI/install_worktree_guard.sh
#
# Çıkış: 0 = kurulu/kuruldu, 1 = --check'te yok, 2 = ortam hatası.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Kök: --root ile hedef repo (test izolasyonu / worktree), yoksa betiğin
# kendisi (_calisma/CIKTI/../..). KÖK her zaman açık: sarmalayıcı git-repo
# köküne değil, HEDEF repo'ya kurulur.
ROOT="$(cd "$HERE/../.." && pwd)"
CHECK_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK_ONLY=1; shift ;;
    --root)
      [ $# -ge 2 ] || { echo "--root dizin gerektirir" >&2; exit 2; }
      ROOT="$(cd "$2" && pwd)"; shift 2 ;;
    *) echo "bilinmeyen argüman: $1 (kullanım: [--check] [--root DIR])" >&2
       exit 2 ;;
  esac
done
cd "$ROOT"

MARKER="WORKTREE-GUARD-WRAPPER"

find_precommit() {
  if [ -n "${PRE_COMMIT_BIN:-}" ] && [ -x "${PRE_COMMIT_BIN}" ]; then
    printf '%s\n' "$PRE_COMMIT_BIN"; return 0
  fi
  if [ -x "$ROOT/_calisma/.venv_z3/bin/pre-commit" ]; then
    printf '%s\n' "$ROOT/_calisma/.venv_z3/bin/pre-commit"; return 0
  fi
  if command -v pre-commit >/dev/null 2>&1; then
    command -v pre-commit; return 0
  fi
  return 1
}

HOOKS_DIR="$(git rev-parse --git-path hooks)"
case "$HOOKS_DIR" in /*) ;; *) HOOKS_DIR="$ROOT/$HOOKS_DIR" ;; esac
HOOK="$HOOKS_DIR/pre-commit"
REAL="$HOOKS_DIR/pre-commit.real"
GUARD_PY="$HERE/precommit_worktree_guard.py"

is_installed() { [ -f "$HOOK" ] && grep -q "$MARKER" "$HOOK"; }

if [ "$CHECK_ONLY" -eq 1 ]; then
  if is_installed && [ -f "$GUARD_PY" ] && [ -f "$REAL" ]; then
    echo "worktree-guard: kurulu ($HOOK)"
    exit 0
  fi
  echo "worktree-guard: KURULU DEĞİL ($HOOK)" >&2
  exit 1
fi

PC="$(find_precommit || true)"

# 1) pre-commit'in kendi script'ini .real'e taşı.
#    - hook yoksa ve .real varsa: birisi sarmalayıcıyı silmiş → .real zaten
#      doğru aday, dokunma.
#    - hook var ve pre-commit'inkiyse: .real'e taşı (üstünü yaz — en taze
#      pre-commit script'i kazanır).
#    - hook bizim sarmalayıcıysa: .real'e dokunma (yoksa sonraki adımda
#      kurulum uyarır).
if [ -f "$HOOK" ] && ! grep -q "$MARKER" "$HOOK"; then
  mv "$HOOK" "$REAL"
  chmod +x "$REAL" 2>/dev/null || true
fi

# 2) Sarmalayıcıyı yaz — KESİNLEŞTİRİLMİŞ heredoc + token.
#    Gövdedeki hiçbir `$`, backtick veya `` ${} `` genişlemez; mutlak
#    yollar @@...@@ tokenlarıyla sonradan enjekte edilir.
cat > "$HOOK" <<'WRAP'
#!/usr/bin/env bash
# @@MARKER@@ (otomatik kurulum — elle DÜZENLEMEYİN)
#
# pre-commit'in unstaged-delta stash penceresine dayanıklı yedek/geri-yükleme
# katmanı ekler. Mantık: _calisma/CIKTI/precommit_worktree_guard.py
#   1) backup : pencere AÇILMADAN unstaged izlenen deltayı .git altına yedekle
#               (delta yoksa hiçbir şey yapma; yedek alınamazsa commit'i blokle)
#   2) real   : pre-commit'in kendi hook script'ini olduğu gibi koş
#   3) post   : pencere kapandıktan sonra delta'nın geri geldiğini doğrula;
#               kayıpsa yedekten otomatik geri yükle (arızayı GÜRÜLTÜLÜ raporla)
#
# pre-commit install bu dosyayı siler; kapı zincirindeki
# check-worktree-guard-install onu yeniden kurar (self-heal).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
GUARD="@@GUARD@@"
REAL="@@REAL@@"
PY="${WORKTREE_GUARD_PYTHON:-python3}"

if [ ! -f "$GUARD" ]; then
  # Guard yoksa sessizce pre-commit'e düş: kurulum-bozukluğu commit'i
  # kilitlemesin, ama görünür olsun (check-worktree-guard-install kapısı
  # bunu ayrıca fail-closed raporlar).
  echo "worktree-guard: $GUARD yok — yedek KATMANI DEVRE DIŞI" >&2
  if [ -f "$REAL" ]; then exec "$REAL" "$@"; fi
  exit 0
fi

rc_backup=0
"$PY" "$GUARD" backup --root "$ROOT" || rc_backup=$?
if [ "$rc_backup" -ne 0 ]; then
  echo "worktree-guard: yedek alınamadı — commit BLOKE (fail-closed:" >&2
  echo "  kanıtlanabilir yedek yokken kayıp-penceresi açılmaz)." >&2
  exit 1
fi

rc_real=0
if [ -f "$REAL" ]; then
  "$REAL" "$@" || rc_real=$?
elif command -v pre-commit >/dev/null 2>&1; then
  pre-commit hook-impl --config=.pre-commit-config.yaml --hook-type=pre-commit -- "$@" || rc_real=$?
else
  echo "worktree-guard: pre-commit bulunamadı ($REAL yok) — kapılar KOŞMADI" >&2
  exit 1
fi

# post: gerçek hook başarısız olsa bile delta'nın ağaçta olduğunu doğrula
# (pre-commit finally-apply'i hata yolunda da çalışır; arıza olursa geri
# yükleriz). Post'un kendi hatası gerçek rc'yi ezmesin, ama GÖRÜNÜR olsun.
"$PY" "$GUARD" post --root "$ROOT" || {
  echo "worktree-guard: post-adımı BAŞARISIZ (yedek duruyor; elle bakın:" >&2
  echo "  .git/precommit-worktree-backups/<en-yeni>/delta.patch)" >&2
  if [ "$rc_real" -eq 0 ]; then exit 1; fi
}

exit "$rc_real"
WRAP

# Tokenleri KESİN olarak değiştir (genişleme yok — sed deseni kaçışlı).
python3 - "$HOOK" "$MARKER" "$GUARD_PY" "$REAL" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
marker, guard, real = sys.argv[2], sys.argv[3], sys.argv[4]
text = path.read_text(encoding="utf-8")
for token, value in (("@@MARKER@@", marker), ("@@GUARD@@", guard),
                     ("@@REAL@@", real)):
    text = text.replace(token, value)
path.write_text(text, encoding="utf-8")
PY

chmod +x "$HOOK"

# 3) Doğrulama — yazılan dosya gerçekten çalışılabilir mi? (0 B / genişleme
#    felaketi gibi kurulum hatalarını kurulum anında yakala).
if [ ! -s "$HOOK" ]; then
  echo "HATA: sarmalayıcı BOŞ yazıldı ($HOOK) — kurulum geri alınıyor." >&2
  if [ -f "$REAL" ]; then mv "$REAL" "$HOOK"; chmod +x "$HOOK"; fi
  exit 2
fi
if ! bash -n "$HOOK"; then
  echo "HATA: sarmalayıcı SÖZDİZİM hatası içeriyor — kurulum geri alınıyor." >&2
  if [ -f "$REAL" ]; then mv "$REAL" "$HOOK"; chmod +x "$HOOK"; fi
  exit 2
fi
if ! grep -q "$MARKER" "$HOOK"; then
  echo "HATA: sarmalayıcı MARKER içermiyor — kurulum geri alınıyor." >&2
  if [ -f "$REAL" ]; then mv "$REAL" "$HOOK"; chmod +x "$HOOK"; fi
  exit 2
fi

if [ ! -f "$REAL" ] && [ -z "${PC:-}" ]; then
  echo "worktree-guard: sarmalayıcı KURULDU ama pre-commit YOK." >&2
  echo "  pre-commit kurulduğunda pre-commit install + bu betiği" >&2
  echo "  yeniden çalıştırın (ya da kapı zinciri self-heal yapar)." >&2
  exit 2
fi

echo "worktree-guard: sarmalayıcı kurulu → $HOOK"
if [ -f "$REAL" ]; then
  echo "  gerçek hook: $REAL"
else
  echo "  gerçek hook: henüz yok — 'pre-commit install' sonrası bu betiği" >&2
  echo "  yeniden çalıştırın (ya da kapı zinciri self-heal yapar)." >&2
fi
exit 0
