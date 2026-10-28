# Yerel ağaç uzlaşma planı (2026-10-24 ölçümü)

> **Bu belge ölçüm kaydıdır, eylem değil.** Hiçbir dosya silinmedi, atlanmadı,
> `checkout`/`reset` ile değiştirilmedi. Sınıflandırma `git status --porcelain`,
> `git diff HEAD`, `git diff HEAD origin/main` ve `git diff origin/main` ile
> yapıldı — tahmin yok, ölçüm var. Onay verilmeden uygulama yapılmaz.

## 0. Zemin

| Ölçüm | Değer |
|---|---|
| Checkout dalı | `fix/restore-freebuff-id-clean` @ `437003b2` |
| `origin/main` | `0f1f2c78` (verify-delivery ✓, docker-security ✓, test-smoke ✓) |
| Geride / ileride | **159 commit geride**, 5 commit ileride |
| Değişen dosya | **58** = 46 `M` + 12 `??` |
| Dağılım | 42 × `_calisma/CIKTI`, 5 × `docs`, 3 × `.github/workflows`, 4 binary zip/checksum, diğerleri |

Bu dosyaların son commit'leri 2026-09-12 / 10-01 / 10-23 tarihlerinde —
**oturumlardan miras kalan iş**, bu çalışma tarafından üretilmedi.

## 1. Sınıflandırma özeti

| Sınıf | Anlam | Adet | Kayıp riski |
|---|---|---|---|
| **A** | Lokal içerik `origin/main` ile **birebir aynı** | **5** | yok — `main`'e geçince kendiliğinden kaybolur |
| **B** | **Yalnız lokal** değiştirdi, main aynı | **9** | yüksek — main'de karşılığı yok, taşınmazsa kaybolur |
| **C** | **İkisi de** değiştirdi → üç yol birleştirme gerekir | **32** | orta — göz kararı alınca bir taraf kaybolur |
| **??** | Track edilmemiş (yeni) dosya | **12** | bakın §4 |

## 2. A sınıfı — 5 dosya, sıfır risk

Lokal içerik `origin/main` ile `git diff --quiet` ile **sessiz**:
`_calisma/CIKTI/check_plist_drift.py`, `gen_plist_golden.py`,
`test_check_mirror_coverage.py`, `test_check_plist_drift.py`,
`test_plist_gate_exit.py`.

Eylem: **hiçbir şey.** `origin/main` üzerine checkout edildiğinde bu 5 `M`
kendiliğinden yok olur; içerik zaten main'inkinin aynısı olduğu için
**kurtarılacak bir şey yok**.

## 3. B sınıfı — 9 dosya, main'de karşılığı yok → **taşınmalı**

Yalnız lokal taraf değişmiş; `HEAD..origin/main` bu dosyalarda neredeyse
dokunulmamış. Toplam **+1 094 / −41** satır. Bunlar main'de **olmayan gerçek iş**:

| Dosya | Lokal | Not |
|---|---|---|
| `_calisma/dev_bootstrap.sh` | +402/−18 | en büyük lokal iş |
| `_calisma/CIKTI/test_check_protection_drift.py` | +192/−0 | tamamen yeni test |
| `_calisma/CIKTI/test_sync_lifecycle.py` | +150/−0 | tamamen yeni test |
| `_calisma/CIKTI/check_protection_drift.py` | +145/−3 | |
| `_calisma/CIKTI/test_render_z3_slides.py` | +132/−0 | tamamen yeni test |
| `_calisma/CIKTI/test_reproducible_pdf_skill.py` | +29/−10 | |
| `.github/workflows/protection-drift.yml` | +13/−2 | |
| `_calisma/CIKTI/test_plist_check_workflow.py` | +24/−2 | |
| `_calisma/CIKTI/test_sync_check_unit_tests.py` | +4/−0 | |

Eylem: **tek bir dal + PR olarak taşı** (`sync/local-b-checkpoint` gibi).
Önce `origin/main`'e göre yeniden uygula, odak bataryayı koş, sonra PR aç.
**Atma.**

## 4. C sınıfı — 32 dosya, üç yol birleştirme gerekir

En riskli alt küme: **main'in dosyanın içini silip yeniden yazdığı** yerler,
üstelik lokal taraf test eklemiş. Burada `--theirs` demek lokal işi,
`--ours` demek main işini yok eder.

**Yüksek öncelik — main büyük silme yapmış, lokal ekleme yapmış:**

| Dosya | Lokal | main |
|---|---|---|
| `_calisma/CIKTI/check_status_check_doc_sync.py` | +137/−4 | **+0/−444** |
| `_calisma/CIKTI/test_check_status_check_doc_sync.py` | +106/−0 | **+0/−406** |
| `_calisma/CIKTI/test_fail_closed_gates.py` | +266/−129 | **+0/−296** |
| `_calisma/CIKTI/test_check_id_residual_doc_sync.py` | +28/−1 | **+0/−319** |
| `_calisma/CIKTI/test_plist_keepalive_golden.py` | +3/−2 | **+0/236** |
| `_calisma/CIKTI/test_check_zero_check_fail_open.py` | +4/−0 | **+0/−187** |
| `docs/FIRST_RUN_TUTORIAL.md` | +1/−0 | **+0/−235** |
| `_calisma/CIKTI/test_makefile_texlive.py` | +82/−3 | **+560/−47** |
| `.github/workflows/verify.yml` | +37/−13 | **+712/−28** |

`main` tarafındaki büyük `-` değerleri bu dosyaların bir bölümünün main'den
**kaldırıldığını** gösterir. Karar: önce main'in neyi neden kaldırdığını
`git log -p origin/main -- <dosya>` ile oku; lokal ekleme hâlâ anlamlıysa
main'in yeni biçimine **yeniden uygula**, çakışma işaretini olduğu gibi bırakma.

**Binary + checksum (4 zip/checksum + 2 repack sidecar):**
`TESLIM_KLASOR_V5_*.zip`, `TESLIM_V5_FINAL_*.zip` ve `.sha256`'lar iki tarafta
da değişmiş. Bunlar **repack çıktısı**; AGENTS uyarısı gereği repack
`cleanup_log.json` / `zip_lineage.json`'ı güncellemez, o yüzden tek başlarına
alınırsa K14/lineage kırmızıya döner. Repack'ı **tek başına** yeniden üret,
yanında `cleanup_log.json` (+4/−4) ve `zip_lineage.json` (+6/−0) ile birlikte.

**Kalan C dosyaları** (düşük çakışma hacmi):
`README.md` (+7/−0 | +136/−2 — changelog tablosu, `gen_changelog.py --update`
ile çözülür), `.pre-commit-config.yaml`, `docs/PUBLISH_SCENARIO.md`,
`docs/Makefile.texlive`, `docs/TEXLIVE_MIGRATION_PLAN.md`,
`docs/ID_RESIDUAL_ACCEPTANCE.md`, `skills/reproducible-pdf-build/SKILL.md`,
`_calisma/CIKTI/check_mirror_coverage.py`, `check_unit_tests.list`,
`check_unit_tests_hook.sh`, `sync_verify_mirror.sh`, `verify_delivery.py`,
`repack_delivery.py`, `test_coverage_report.py`, `test_dev_bootstrap.py`,
`test_fail_closed_gates.py`, `test_plist_keepalive_golden.py`,
`test_check_zero_check_fail_open.py`, `test_check_id_residual_doc_sync.py`,
`test_check_status_check_doc_sync.py`, `test_makefile_texlive.py`,
`test_repack_canonical_binding` ile ilgili belgeler, V5 checksum dosyaları.

## 5. Untracked (??) — 12 dosya: **silme, atomik taşı**

Önemli ölçüm: bu 12 dosyanın **`origin/main` içinde referansı `main_refs=0`**.
Yani temiz bir main klonu bunlar olmadan **kırmızıya dönmüyor** —
referansların hepsi **commit'lenmemiş lokal düzenlemelerden** geliyor.

Bu, kararı ikiye böler:

**a) Lokal düzenlemelerin bağımlı olduğu 7 dosya → PR içinde *atomik* commit'lenmeli**
(birini tek başına commit'lemek temiz klonu kırar):

| Dosya | Local referans |
|---|---|
| `_calisma/bootstrap_units.conf` | `dev_bootstrap.sh`, `test_dev_bootstrap.py` |
| `_calisma/CIKTI/check_bootstrap_units.py` | `dev_bootstrap.sh`, `test_dev_bootstrap.py` |
| `_calisma/CIKTI/run_unit_tests_parallel.py` | `check_unit_tests_hook.sh`, `test_sync_lifecycle.py` |
| `_calisma/CIKTI/mutation_guard.py` | `test_fail_closed_gates.py`, `test_render_z3_slides.py` |
| `_calisma/CIKTI/check_bootstrap_toolchain.py` | `generated_surfaces.py` |
| `_calisma/CIKTI/test_bootstrap_unit_coverage.py` | `check_unit_tests.list`, `test_coverage_report.py` |
| `_calisma/CIKTI/test_repack_canonical_binding.py` | `docs/ID_RESIDUAL_ACCEPTANCE.md` |

**b) Referansı olmayan 5 dosya → karar bekliyor (WIP mi, reddedilmiş iş mi):**
`.github/workflows/fresh-bootstrap.yml`,
`_calisma/CIKTI/check_doc_protection_count.py`,
`_calisma/CIKTI/test_doc_protection_count.py`,
`_calisma/CIKTI/test_bootstrap_units_validate.py`,
`_calisma/CIKTI/test_mutation_battery_canonical.py`.

Eylem: (a) grubu ilgili B/C değişiklikleriyle **aynı PR'da** taşı; (b) grubu
için içeriklerini okuyup "commit'le / bırak" kararı iste.

## 6. Önerilen sıra (onaydan sonra)

1. B sınıfını **tek checkpoint dalına** taşı → PR → yeşil → birleştir.
   (Bunlar main'de olmayan tek iş; en acil kayıp riski bu.)
2. 7 referanslı untracked dosyayı **ilgili lokal editlerle aynı PR'da** commit'le.
3. A sınıfını **at** (içerik zaten main'de) — bu 5 `M` otomatik yok olur.
4. C sınıfını **dosya bazında** `git diff origin/main` üzerinden yeniden uygula;
   §4'teki yüksek öncelikli 9 dosyada önce main'in neyi kaldırdığını oku.
5. Repack binary'lerini **yan sidecar'larıyla birlikte** tek adımda üret.
6. Checkout'u `origin/main`'e getir, `git status` → **0** hedefi.
7. §5b'deki 5 dosya için karar.

**Doğrulama (uygulama sonrası):** `git status` boş ·
`git rev-list --count HEAD..origin/main` = 0 ·
`test_gen_changelog` + `test_update_changelog_hook` + `test_deploy_evidence`
OK · `deploy_evidence.py --check` exit 0 · main üç işi yeşil.

## 7. Bu planın uygulanmadığına dair kanıt

Uygulama anında `git status --porcelain` = **58 satır** (46 `M` + 12 `??`),
`HEAD` = `437003b2`. Plan onaylanana kadar bu sayı değişmez.

## 8. Güncelleme — 2026-10-25 oturum denetimi (DONE/OPEN)

Bu bölüm planın **uygulanmadığını** değil, denetim turunda **neyin kapandığını
ve neyin açık kaldığını** yazar. Yukarıdaki sınıflandırma tarih olarak durur;
§0 ölçümü artık eskidir.

### 8.1 Zemin (güncel ölçüm)

| Ölçüm | 2026-10-24 (plan) | 2026-10-25 (denetim) |
|---|---|---|
| Checkout dalı | `fix/restore-freebuff-id-clean` @ `437003b2` | **`main` @ `930c41ad`** |
| `origin/main` | `0f1f2c78` | **`684cf5eb`** |
| Geride | 159 commit | **10 commit** |
| Değişen dosya | 58 (46 `M` + 12 `??`) | **59** |

### 8.2 DONE — bu turda kapandı

| Kalem | Verdict | Kanıt |
|---|---|---|
| §2 A sınıfı (5 plist dosyası) | **DONE / artık konu dışı** | A sınıfının taşıdığı plist işi main'e indi: #116 → `865de95f` (`Plist P1 drift gate` job'ı), #119 → `6e750548` (türetim↔canlı hizalama). Kapı **canlı required sette**: 16 context, `strict: true`, `enforce_admins: true`; `status_checks.py --gh` → `names_ok: true`, extra/missing boş. |
| §4 C sınıfı — `README.md` changelog | **DONE (ölü hash) / kısmi (eksik satır)** | Ölü hash #118 → `7bdbd76d` ile düzeltildi (`74926cec` → `865de95f`); `test_gen_changelog` main'de 72/72 OK. Eksik 4 merge satırı için **PR #123 açık** (advisory `gen_changelog --check` 4 → 1). |
| Prettier borcu (§task_plan / Phase 3) | **DONE** | #122 → `684cf5eb`: 13 kaynak dosya reformat + üretilen `video/public/data/` `.prettierignore`'a. `check_prettier_format --all` OK (88 dosya), AST 13/13 eşdeğer, `tsc --noEmit` rc=0. |
| Kanıt-defteri tazeliği | **DONE** | `0f6a9bb8` satırı (#121) → `deploy_evidence.py --check` PASS, `substantive_gap = 0`. |

### 8.3 OPEN — denetimde **doğrulanmadı veya dokunulmadı**

| Kalem | Verdict | Neden / sıradaki adım |
|---|---|---|
| §3 B sınıfı (9 dosya, +1 094/−41) | **OPEN** | Bu turda taşınmadı; hâlâ "main'de karşılığı yok" ve kayıp riski sınıfı. Tek checkpoint dalı + PR hâlâ doğru adım. |
| §4 C sınıfı (kalan ~30 dosya, repack binary'leri) | **OPEN** | Repack + `cleanup_log.json`/`zip_lineage.json` birlikte üretilmeden ele alınmamalı (K14/lineage). |
| §5a 7 referanslı untracked dosya | **OPEN** | İlgili B/C değişiklikleriyle aynı PR'da taşınmalı. |
| §5b 5 referanssız dosya | **OPEN** | "Commit'le / bırak" kararı hâlâ kullanıcıda. |

**Not:** §6 sırası ve §7'deki "plan uygulanmadı" kanıtı, 59 değişen dosya ve
`HEAD` = `930c41ad` ölçümüyle hâlâ geçerlidir — bu bölüm onları **iptal etmez**,
yalnızca hangi kalemin kapandığını kaydeder.
