# Tam Kapsam Denetim Raporu — 2026-09-17

**Kapsam:** Repo'nun tüm katmanları — hook zinciri, unit test gövdesi, CI
workflow'ları, Docker güvenlik hattı, TeX/PDF üretim hattı, plist/launchd
zinciri, teslim/mirror sözleşmeleri ve dokümantasyon.
**Yöntem:** Ölçüm-öncelikli denetim: her iddia ya çalıştırılmış kapıyla ya da
kaydedilmiş canlı koşumla desteklenir; "önce tahmin et, sonra ölç" yerine
"önce ölç" ilkesi uygulanmış, iki kez tahmin zinciri kuruluğu ölçümle kırılmıştır
(aşağıda **Yöntem dersi**). Ortam yokluğu (`SKIP`) ile kusur (`FAIL`) her yerde
ayrıştırılmıştır — SKIP kararları gerekçesiyle kaydedilir, sessiz atlanmaz.

---

## 1. Taranan katmanlar

| Katman | Kapsam | Kapı / araç | Sonuç (2026-09-17) |
|---|---|---|---|
| Pre-commit hook zinciri | ~70 hook'un her biri kendi sözleşme testiyle; smoke | `test_all_hooks_smoke.py`, `check_unit_tests_hook.sh` | smoke 25/25; unit batarya **132/132 PASS** (docker güvenlik smoke + yama deseni testleriyle büyüdü: 130→132) |
| Unit test gövdesi + manifest senkronu | `check_unit_tests.list` + `HOOK_COVERAGE` çift manifest'i | `sync_check_unit_tests.py --check` (iki hedefli, fail-closed), `test_coverage_report.py --check`, `ci_full_discover_drift_guard.py` | üç kapı rc=0; fail-closed kanıtı: HOOK_COVERAGE'dan satır silinince rc=1 + adıyla rapor, restore rc=0 |
| CI workflow'ları | verify.yml (2800+ satır), docker-security, test-smoke | `lint_actionlint.sh` kontratı + **gerçek GitHub Actions koşumları** | push zinciri: ilk koşum 3 gizli borç yakaladı (→ §2), 2. ve 3. koşum **3/3 workflow success** (27 job: 22 success + 5 by-design skip; ardından 23 success) |
| Docker güvenlik hattı | Dockerfile + trivy gate + canlı smoke | `docker_security_smoke.sh` (build+scan+health tek komut), Trivy 0.74.0 CI parametreleri | canlı koşum PASS ×3 (ilk tespit, fix sonrası, desen genelleştirmesi sonrası); trivy **before: 2 HIGH → after: 0 bulgu**; 13 Eylül CI kırmızı run'ı aynı CVE'lerle — before/after zinciri kapalı |
| TeX/PDF üretim hattı | determinizm (SDE), motor eşitliği, göç hazırlığı | `texlive_determinism_hook.sh` gerçek motorlarla + çapraz-motor probe | verdict=PASS: kanonik hash `a75c3409…` oturumlar arası 3 bağımsız ölçümde kararlı; tek kalıntı pdfTeX rastgele `/ID`; SDE-tectonic sızıntısı düzeltildi (→ §2); TeXLive 3-geçiş pipeline'ı iki bağımsız koşumda birebir |
| plist / launchd / preview | plist profilleri, prestart, K20 | `plist_render` + `check_plist_drift` + K20 canlı | P0-9 onarımı sonrası K20 PASS (birincil canlı HTTP 200; yedek BILGI = steady-state kontratı) |
| Teslim / mirror sözleşmeleri | zip↔sidecar, mirror coverage, changelog, refs | `repack_delivery.py --verify`, `check_mirror_coverage.py`, changelog-sync | TÜMÜ PASS (zip ×2 ↔ sidecar; refs 61/61) |
| Dokümantasyon | kanıt zincirinin yazılı hali | FINAL_RC_REPORT + 3 yeni doküman | `MERGE_DECISION_reword-working_to_main.md`, `TEXLIVE_MIGRATION_PLAN.md`, `DOCKER_SECURITY_PATCHING.md` + bu rapor — tümü ölçülmüş kanıta bağlı |

## 2. Kapatılan borçlar

### Devralınan P0'lar (önceki derin denetimden, FINAL_RC_REPORT'ta ayrıntılı)

| ID | Borç | Durum |
|---|---|---|
| P0-1..P0-8 | heredoc kırığı, actionlint kontrat modeli, 7 shellcheck bulgusu, lean stdin bloğu, smoke timeout/pattern, changelog eski hash'leri, disk doluluk ×2 | kapatıldı (kanıtları FINAL_RC_REPORT §P0 tablosunda) |
| P0-9 | plist `keepalive` ölü alanı → yedek login'de port tutuyor, birincil crash-loop | kapatıldı + canlı makine onarıldı |
| P0-10 | elan tmp kalıntısı 58 GB → ENOSPC | temizlendi, temiz kopya 2228 OK |

### Bu haftanın denetiminde kapatılanlar

| Borç | Nasıl yakalandı | Kapanış kanıtı |
|---|---|---|
| "TeXLive determinism ölçülmedi" SKIP'i | kullanıcı isteğiyle ölçüme açıldı | verdict=PASS; kanonik hash oturumlar arası kararlı; `/ID` kalıntısı dürüstçe raporlandı |
| SDE tectonic'e sızmıyordu (betik yalnız pdflatex'e export ediyordu) | tectonic hash'inin oturumlar arası kayması (`4ad65b9b…`→`6cfc6c0a…`) teşhis edildi | export düzeltildi → `ad8fca69…` bağlamlar arası birebir; fail-closed stub testiyle sabitlendi |
| Kardeş hook testleri gerçek kanıt dosyasını eziyordu | batarya koşusu sonrası kanıt hash'i değişmişti | `DETERMINISM_OUT` izolasyonu test tarafına; hash öncesi/sonrası eşitliğiyle kanıtlı |
| HOOK_COVERAGE senkron boşluğu (manifest güncel, harita unutulur) | yeni testim "kapaksız dosya" olarak düştü | `sync_check_unit_tests.py` iki hedefli genişletildi + fail-closed kanıtı + 17 test |
| Docker/Trivy canlı koşum SKIP'i | colima başlatıldı, uçtan uca ölçüldü | trivy 2 HIGH yakaladı (gate'in işi) → pcre2 yaması → 0 bulgu; canlı smoke healthy |
| pcre2 CVE çifti (CVE-2026-86145/89161) | yerel trivy + 13 Eylül CI kırmızı run'ı | yama + CVE-defteri; CI'da da doğrulandı |
| CI "gerçek koşum" borcu (push gerektirir) | `reword-working` push edildi | 1. koşum: actionlint SC2002 + hook-install `--check-only` kalıcı FAIL + zincirleme audit kırılması → hepsi düzeltildi; 2./3. koşum 3/3 success |
| Docker smoke'un tek komutluk yeri yoktu | bu denetim turu | `docker_security_smoke.sh` + 4 stub test + manifest kaydı |
| Güvenlik-yama deseni tek pakete gömülüydü | aynı tur | `SECURITY_PATCH_PACKAGES` ARG + CVE-defteri + `DOCKER_SECURITY_PATCHING.md` + 7 sözleşme testi; canlı build, `dpkg-query`'nin `pkg=sürüm` reddini yakalayıp deseni daha ilk turunda olgunlaştırdı |

**Yöntem dersi:** Denetim sırasında iki kez tahmin zinciri kuruldu ("5 dosya
eksik", "son 2 test failing") — her ikisi de taze koşumda çürütüldü (17/17 OK,
rc=0). Rapor içindeki her sayı bu yüzden koşum-kanıtına bağlıdır, hafızaya değil.

## 3. Kalan riskler

| # | Risk | Etki | Azaltım / durum |
|---|---|---|---|
| R1 | tectonic→TeXLive göçü **planlandı, uygulanmadı** | iki motor paralel yaşamaya devam; byte-düzeyi çapraz eşitlik imkânsız (font/ligatür farkı — ölçüldü) | `TEXLIVE_MIGRATION_PLAN.md` 7 faz; Faz 3 `/ID` kabul raporu; her faz ölçüm kapılı |
| R2 | pdfTeX rastgele trailer `/ID` kalıntısı kalıcı | qpdf `--static-id`/`--remove-metadata` gideremiyor (donmuş bulgu ×2 doğrulandı) | sözleşme /ID-kanonik karşılaştırmaya bağlı; kanonik hash oturumlar arası kararlı — içerik determinizmi zaten kanıtlı; **haftalık determinism-trend CI job'ı (2026-09-17) kararlılığı sürekli izler**: `determinism-trend.yml` cron + `record_determinism_trend.py` jsonl trendi (tazelik + kaynak-uzlaşma [platform-scoped] + darwin/linux kapsam değişmezleri, fail-closed) |
| R3 | CI runner'ında TeXLive paket seti yerel Homebrew'dan farklı olabilir | Faz 6 CI koşumunda hash sapması | plan kuralı: **ölçmeden varsayma** — sapma çıkarsa kabul raporu CI'ya özgü ikiliyle genişler |
| R4 | base-image güncellemeleri yeni CVE getirebilir | trivy gate kırmızı (fail-closed — beklenen davranış) | desen: floor + defter + tek build-arg; haftalık tarama önerisi: docker-security'ye schedule job'ı |
| R5 | colima arm64 → amd64 qemu emülasyonu | yerel build yavaş; CI amd64 native olduğundan **CI riski değil** | `DOCKER_SMOKE_PLATFORM` override; dokümante |
| R6 | `reword-working`→`main` birleştirmesi **karar aşamasında** | 22 dosyada çakışma (çoğu add/add — aynı işin iki kopyası); main'in 5 bağımsız düzeltmesi merge'de korunmalı | `MERGE_DECISION_…md`: 3-way merge-commit önerisi + dosya tablosu + siper zinciri; tek `revert -m 1` geri dönüş |
| R7 | 15 untracked test dosyası (CI job'larında koşan ortam-bağımlılar) + pre-commit bataryası (132) ile kayıtlı full liste (141) farkı | kafa karışıklığı riski; kapsam sessizce zayıflamaz (drift guard + coverage kapısı) | drift-guard çıktısı farkı açıkça not eder; EXCLUDE listesi gerekçeli |
| R8 | K19 coqtop yok / K9 lake ağırlığı | opsiyonel katmanlar SKIP | tasarım gereği; `--coq-proof` bayrağı dokümante; K9 elan kurulumu ile açılabilir |

## 4. Kanıt dizini

- `docs/FINAL_RC_REPORT.md` — P0 tabloları, ölçülen kanıtlar, açık borç kapanışları
- `docs/ci_simulate/texlive_determinism/texlive_determinism_report.txt` — determinizm kanıtı
- `docs/ci_simulate/docker_security_smoke/docker_security_smoke_report.txt` — build+scan+health kanıtı
- `docs/MERGE_DECISION_reword-working_to_main.md` · `docs/TEXLIVE_MIGRATION_PLAN.md` · `docs/DOCKER_SECURITY_PATCHING.md`
- GitHub Actions: koşum 35161423568 (ilk — 3 borç), 35163054257 (3/3 success), 35163906063 (rapor commit'i, 3/3 success)
- Bu oturum koşumları: unit batarya 132/132; smoke 25/25; sync/coverage/drift kapıları rc=0; stub testler 4/4 + 7/7 + 17/17

## 5. Sonuç

Taranan sekiz katmanın yedisi **ölçülmüş yeşil** kanıtla kapalı; sekizincisi
(TeXLive göçü) planlı ve her fazı ölçüm kapılı. Kalan risklerin tamamı ya
tasarım gereği SKIP (R2/R5/R7/R8), ya karar bekleyen işlem (R6 birleştirme),
ya da planı yazılmış göç (R1) sınıfında — **bilinmeyen/belgelenmemiş risk kalmadı.**
