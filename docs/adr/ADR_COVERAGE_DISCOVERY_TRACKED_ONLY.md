# ADR: Test keşfi — üyelik `git ls-files` (worktree ↔ CI paritesi)

**Durum:** Kabul edildi (2026-10-15 — `_calisma/CIKTI/test_coverage_report.py`
`discover_test_files`'inde uygulandı; bu ADR yazıldığı an worktree'dedir,
commit edilmemiştir).

**Bağlam:**

- Coverage checker dosya sisteminden `test_*.py`/`test_*.js` glob'u ile test
  dosyaları keşfediyordu. CI **HEAD'de** (fresh checkout) koşar: worktree'de
  var olup commit'lenmemiş (untracked) test dosyalarını hiç görmez.
- Sonuç: worktree'de6 untracked test dosyası "uncovered" sayılıyor ve checker
  local'de rc=1 verirken CI'da yeşildi — AGENTS kuralının birebir uygulandığı
  durum: *üyelik `git ls-files` ile belirlenir, dizin taramasıyla değil.*
- Aynı ailenin bilinen tuzağı: `check_unit_tests.list` üyeliğinin filesystem
  ile okunması Python sürümüne göre ya exit-5 ya da sessiz "0 test PASS"
  üretir — ikisi de aynı yanlış üyelik yaklaşımının sonuçları.

**Karar:**

1. `discover_test_files`, keşfettiği dosya adlarını `git ls-files -- test_*.py
   test_*.js` (TEST_DIR cwd) kümesiyle süzer; tracked olmayanlar keşfe girmez.
2. **Git başarısızsa** (yok / repo değil / timeout) None döner ve eski glob
   davranışıyla devam eder — keşif asla durmaz, filtre uygulanmaz
   (fail-closed değil **fail-bounded**: bulgu üretimi kesintiye uğramaz,
   üyelik iddiası da yapılmaz).
3. Bu filtre coverage checker içindir; `check_unit_tests` battery üyeliği
   hâlâ kendi sync betiğiyle (auto-sync, commit anında) yönetilir — iki
   mekanizma birbirine karıştırılmaz.

**Sonuçlar:**

- Local ve CI aynı test kümesini görür;6 phantom kırmızı + onları takip eden
 4 coverage testi düzeldi (batch 36/36, `--check` rc=0).
- Commit'lenmemiş test dosyaları artık checker'ı kirletemez; bunun yan etkisi:
  commit'lenmemiş bir test "kapı kırılabilirliği" de sunmaz (CI'da zaten yok).

**Reddedilen alternatifler:**

- *Durumu olduğu gibi bırakmak (glob):* local-CI asimetrisi kalıcı ve yanıltıcı
  (yeşil CI, kırmızı local — hangisi gerçek soru sorulamaz hale gelir).
- *Checker'ı fail-open yapmak:* uncovered tespiti fail-open = kapısızlık.

**Kapı bağı:** `test_coverage_report.py`, `test_test_coverage_report.py`,
`test_gate_coverage_sync.py` (36 test yeşil; keşif filtresinin kendisi için
taslak negative-test bkz. `NEGATIVE_TEST_CONTRACTS_DRAFT.md`).
