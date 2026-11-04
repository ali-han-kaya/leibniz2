# PR #54 tasnif raporu — konu bazlı bölme neden tek dilime indi

**Tarih:** 2026-11-03
**Kaynak PR:** #54 (CLOSED, birleştirilmedi) — dal `land/migration-gates-2026-09-30`
**Dal başı:** `2ab649f8` · **merge-base:** `da58b144` · **o anki `origin/main`:** `85da7690`

Bu rapor, "PR #54'ü konu bazlı küçük PR'lara böl" isteğinin ölçümle neden
tek küçük dilime indiğini kaydeder. Rapor bir öneri değil, **yeniden
üretilebilir ölçüm** içerir: aşağıdaki her sayı verilen komutlarla
yeniden üretilebilir.

## 1. Ölçek

| Ölçü | Değer |
|---|---|
| Dalın kendi commit'leri | 167 |
| Merge-base'ten sonra main'in ilerlediği commit | 317 |
| Merge-base'e göre değişen dosya | 513 |
| Satır | +112.695 / −5.222 |

Dosya sınıflandırması (merge-base'e göre):

| Sınıf | Dosya |
|---|---|
| Dalda eklenmiş, main'de HİÇ yok | 225 |
| Dalda eklenmiş ama main'de zaten var | 79 |
| İki tarafta da değişmiş (çakışma yüzeyi) | 134 |
| Yalnız dalda değişmiş (temiz taşınabilir) | 71 |
| Birebir aynı | 4 |

134 dosya iki tarafta da değişmiş: dal 317 commit geride olduğu için
"konu bazlı rebase" bu yüzeyin tamamında çakışma çözmek demek.

## 2. Üç konunun durumu

İstenen üç konu da bugünkü `main`'de **zaten ve daha ileri biçimde**
bulunuyor. Ölçüm, dosya bazında "main'de var mı / dal mı daha yeni"
karşılaştırmasıdır (`git show origin/main:<yol>` ↔ `git show <dal>:<yol>`).

### T1 — unit-test manifest / coverage

| Dosya | main | Dal vs main |
|---|---|---|
| `_calisma/CIKTI/sync_check_unit_tests.py` | var | +78 / −270 (dal daha dar) |
| `_calisma/CIKTI/check_unit_tests_hook.sh` | var | +99 / −242 |
| `_calisma/CIKTI/run_unit_tests_parallel.py` | var | dalda HİÇ yok |
| `_calisma/CIKTI/test_bootstrap_unit_coverage.py` | var | dalda HİÇ yok |
| `_calisma/CIKTI/check_unit_tests_timing.py` | var | birebir aynı |

Main'in `sync_check_unit_tests.py`'ında dalda bulunmayan fonksiyonlar var:
`precommit_hook_ids`, `read_workflows_text`, `run_check_exclude_binding`,
`workflow_ci_tokens`. Yani dal bu konuda main'in **eski ve dar** hâli.

### T2 — TeXLive göçü

| Dosya | main | Dal vs main |
|---|---|---|
| `docs/Makefile.texlive` | var | farklı (main daha yeni) |
| `_calisma/CIKTI/texlive_determinism_hook.sh` | var | farklı |
| `_calisma/CIKTI/texlive_determinism_test.sh` | var | farklı |
| `_calisma/CIKTI/test_makefile_texlive.py` | var | farklı |
| `docs/TEXLIVE_MIGRATION_PLAN.md` | var | farklı |
| `docs/TEX_RENDER_PIPELINE.md` | var | farklı |
| `_calisma/CIKTI/test_texlive_determinism_hook.py` | var | birebir aynı |

### T3 — Kapılar

| Dosya | main | Dal |
|---|---|---|
| `_calisma/CIKTI/check_zero_check_fail_open.py` + testi | var | dalda HİÇ yok |
| `_calisma/CIKTI/check_advisory_exit_sidecars.py` + testi | var | dalda HİÇ yok |
| `_calisma/CIKTI/ci_full_discover_drift_guard.py` | var | birebir aynı |

## 3. Test dosyaları: neden "testleri taşı" işe yaramıyor

| Ölçü | Dal | main |
|---|---|---|
| `test_*.py` dosyası | 234 | 228 |
| Yalnız dalda olan | 46 | — |
| Yalnız main'de olan | — | 40 |

Yalnız dalda olan 46 testin **43'ünün konu dosyası main'de hiç yok**
(`test_<ad>.py` → `<ad>` diskte yok). Bunlar main'e konursa ölü dosya olur:
ne bir davranışı ölçer ne bir kapıyı kapsar; `check-unit-tests` listesine
girip sürekli import hatası üretirler.

Kalan 3 testin konu dosyası main'de var, bu yüzden üçü bugünkü main'e karşı
gerçekten koşturuldu:

| Test | Bugünkü main'e karşı sonuç |
|---|---|
| `test_check_bootstrap_toolchain.py` | **13 hata** — `check-bootstrap-toolchain` hook'u main'de yok |
| `_calisma/landing/test_build_landing.py` | **4 hata + 1 başarısızlık** — main'in builder'ı `stripe` temasını desteklemiyor, `design-system/tokens.css` bekliyor |
| `test_check_seal_hash.py` | **2 başarısızlık** — sidecar sözleşmesi main'de değişmiş |

Sonuç: cherry-pick edilebilir test yok. Dal testleri, main'in artık
tanımlamadığı sözleşmeleri çiviliyor.

## 4. Bu PR'da ne land oldu

Tek gerçek boşluk LaTeX yüzeyindeydi: main'de `.tex` yüzeyini denetleyen
**hiçbir kapı yok** (11 tracked `.tex`, `$$` kullanımı sıfır, ama denetim
de sıfır). Dal bu kapıyı taşıyordu; kapı hiçbir zaman main'e girmedi.

Bu PR onu bugünkü main'e yeniden inşa eder:

- `_calisma/CIKTI/check_latex_surface.py` — tracked `.tex` yüzeyinde:
  - aktif `$$` display delimiter,
  - aynı `\input`/`\include` grafiğinde label'ı olmayan
    `\ref`/`\eqref`/`\autoref`/`\cref`/`\pageref`,
  - çözülemeyen `\input` hedefi (makro taşıyan hedef dahil — fail-closed),
  - aynı grafta yinelenen `\label`
  bulgularını üretir. Yorumlar byte offset korunarak soyulur; bağımsız el
  yazması kopyalarındaki aynı label yanlış-pozitif üretmez.
- `_calisma/CIKTI/test_check_latex_surface.py` — 12 sözleşme testi
  (pozitif/negatif senaryo, CLI exit 0/1/2, gerçek repo yüzeyi, kablolama).
- Kablolama: `.pre-commit-config.yaml` hook'u (`check-latex-surface`),
  `verify.yml` fail-closed adımı + `logs/latex_surface_findings.json`
  sidecar'ı, `check_unit_tests.list`, `HOOK_COVERAGE`, `verify-chain`
  envanteri.

Kapı bugünkü yüzeyde temiz (`11 TeX dosyası → SONUÇ: temiz`).

## 5. Bilerek land edilmeyenler

| Küme | Adet | Neden |
|---|---|---|
| Yalnız daldaki test dosyaları | 43 | Konu dosyası main'de yok — ölü dosya |
| Konu dosyası olan 3 test | 3 | Bugünkü main'e karşı kırmızı — yeniden yazım işi |
| `_calisma/CIKTI/recovery_patches_2026092*` | ~90 | pre-commit patch dökümü — artefakt, kod değil |
| `_calisma/CIKTI/equation_gallery/*.png` + `canvas/*.png` | ~20 | üretilmiş görüntü; üreticisi (`render_equation_gallery.py`) ayrı iş |
| Dalın eski T1/T2/T3 dosyaları | 71 | Main'de daha yeni karşılığı var — kopyalamak regresyon |

## 6. Yeniden üretim

```bash
B=origin/land/migration-gates-2026-09-30
MB=$(git merge-base $B origin/main)
git rev-list --count $MB..origin/main          # 317
git rev-list --count $MB..$B                   # 167
git diff --shortstat $MB $B                    # 513 dosya, +112.695 / -5.222

# Konu dosyası main'de mi?
git cat-file -e origin/main:_calisma/CIKTI/check_zero_check_fail_open.py && echo "main: VAR"

# Dalda olup main'de olmayan testler
comm -23 <(git ls-tree -r --name-only $B | grep -E '(^|/)test_[^/]*\.py$' | sort) \
         <(git ls-tree -r --name-only origin/main | grep -E '(^|/)test_[^/]*\.py$' | sort) | wc -l   # 46
```

## 7. Sonuç

PR #54 konu bazlı üç PR'a bölünemez: üç konunun ikisi (T1, T2) main'de daha
ileri, üçüncüsünde (T3) kapıların çoğu main'de mevcut. Bölme girişimi, main'i
geriletme riski taşıyan 134 çakışma dosyası ve ölü test kümesi üretirdi.
Kalan tek gerçek boşluk (LaTeX yüzey kapısı) bu PR'da main'e iniyor; geri
kalan dal içeriği bu raporla kapsam dışı bırakıldı.
