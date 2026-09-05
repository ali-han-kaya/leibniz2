#!/bin/sh
# check_summary_writable.sh — GITHUB_STEP_SUMMARY (summary.md) write denetimi.
#
# step_validate_summary'nin readonly assert'i burada TEK KAYNAK olarak durur:
# simulate_verify_job.sh bu scripti çağırır (inline kopya yok) ve
# test_simulate_summary.sh POSIX-uyumlu üç senaryoyu (ok yazma / read-only /
# boş dosya) bu scriptle sabitler.
#
# GITHUB_STEP_SUMMARY'ya yazılamıyorsa (dosya chmod a-w / dizin yazılamaz /
# read-only filesystem) consolidate/summary_sink stdout'a düşer ve hata
# sessizce yutulur — bu script, write'ın GERÇEKTEN okunabildiğini ve APPEND
# (GitHub Actions summary'ye >> ile APPEND eder) edilebildiğini doğrular
# (fail-closed). Test satırı geri alınır (iz bırakmadan).
#
# Kullanım: check_summary_writable.sh <summary_path>
# Exit: 0 = yazılabilir; 1 = değil (eksik/boş/readonly/append hatası);
#       2 = kullanım hatası.
set -u

summary="${1:-}"
if [ -z "$summary" ]; then
  echo "HATA: kullanım: check_summary_writable.sh <summary_path>" >&2
  exit 2
fi

errors=0
if [ ! -f "$summary" ]; then
  echo "❌ HATA: summary.md oluşturulamadı — GITHUB_STEP_SUMMARY write başarısız"
  errors=$((errors + 1))
elif [ ! -s "$summary" ]; then
  echo "❌ HATA: summary.md boş — dashboard header veya detail sections yazmadı"
  errors=$((errors + 1))
elif [ ! -w "$summary" ]; then
  echo "❌ HATA: summary.md yazılabilir değil — GITHUB_STEP_SUMMARY readonly"
  errors=$((errors + 1))
else
  # APPEND derecesini denetle (GitHub Actions da summary'ye >> ile APPEND
  # eder): geçici satır ekle, başarılıysa geri al (iz bırakmadan).
  probe="# proj-readonly-assert"
  if ! (set -C; echo "$probe" >> "$summary") 2>/dev/null; then
    echo "❌ HATA: summary.md'ye APPEND yapılamadı — dosya/dizin read-only"
    errors=$((errors + 1))
  else
    # Test satırını geri al — içerik değişmemiş olmalı (iz bırakma).
    # sed -i GNU/macOS farklı bayraklar ister; POSIX-uyumlu: geçici dosyayla
    # son satırı at, yerine yaz, geçiciyi sil.
    if tail -1 "$summary" | grep -q "$probe"; then
      tmp="${summary}.probe"
      sed '$d' "$summary" > "$tmp" 2>/dev/null && mv "$tmp" "$summary" && rm -f "$tmp"
    fi
    echo "✅ summary.md: yazılabilir (APPEND OK)"
  fi
fi

exit $errors
