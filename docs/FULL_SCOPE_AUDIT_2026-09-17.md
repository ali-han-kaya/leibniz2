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

### R6 turu (2026-10-02): `reword-working` → `main` birleştirmesi kapatıldı

`MERGE_DECISION_reword-working_to_main.md` §5'in güvenlik ağı birebir
uygulandı. Merge iki aşamalı oldu — çünkü ilk aşamada kalan bicim borcu
`pre-commit run --all-files` kapısını tutuyordu:

| Aşama | PR | Merge commit | İçerik |
|---|---|---|---|
| 1 | #77 | `ddde854` | `reword-working` → `main` (dokümanın asıl hedefi) |
| 2 | #78 | `18e0403` | bicim borcu (42 dosya) + K6 strict determinizm bağlaması + Faz 4/5 + V5p repack |

**§5 güvenlik ağı — ölçülen:**

| Adım | Kanıt |
|---|---|
| §5.1 push öncesi `pre-commit run --all-files` | **EXIT=0** (52 Passed / 0 Failed); push öncesi ölçüm EXIT=1 idi, tek hata `check-prettier-format` |
| §5.2 teslim PDF'i `shasum -c` | OK |
| §5.3 changelog tek yazıcı | `gen_changelog.py --prune` + iki writer-2 yazımı (`a63c996`, `80d5801`) |
| §5.4 merge sonrası 3 workflow | `verify-delivery` (P0=0, P1=0) · `docker-security` (Trivy 28 hedef, 0 bulgu) · `test-smoke` — üçü de success |
| §5.5 geri dönüş | her iki merge için `git revert -m 1` açık |

14 required check'in tamamı yeşil (54 pass / 0 fail); merge sonrası ana-dal
koşumları doğrulandı: `byte-identical repack OK` (kanıt 2/2), lineage
`K14-DRIFT PASS`, teslim kanonik hash'i `d4f67e39…` **korundu** (PDF değişmedi).

**Planda olmayan iki blokaj — hiçbir kapı atlanmadan çözüldü:**

1. **Changelog stale-row tavuk-yumurta.** `0baa72f` henüz HEAD'e ulaşmamış
   olduğu için tabloda *stale* sayılıyor ve `check-unit-tests` blokluyordu;
   yazan hook `--update` stale satırı silmediği için boşuna çalışıyordu.
   Tool'ın **kendi `--prune` modu** kullanıldı → `--check` rc=0. `--no-verify`
   gerekmedi. Kayıt repo'nun gecikmeli yazım (writer-2) sözleşmesiyle
   kapatıldı; yeniden üretilen `0baa72f` satırı prune öncesiyle byte-özdeş.
2. **Repack byte-identical ihlali.** Faz 4 (`e3651c1`) **üreticiyi**
   (`repack_delivery.py`) değiştirdi ama gemideki teslim paketini yeniden
   üretmedi; CI'ın her push'ta koşan fail-closed kapısı bunu yakaladı
   (`main` bu kapıda yeşildi — kırılma PR'ye özgüydü). V5p repack +
   `zip_lineage.json`/`cleanup_log.json` senkronu; `check_zip_lineage_drift.py`
   rc=0 (P0 3 → 0). Linux CI ile macOS repack'i **ayni** zip hash'ini üretti
   (`c205a02e…` / `fba120ce…`) — platform-bağımsız determinizm kanıtlandı.

**Yöntem dersi (bu tur):** "Bir sonraki repack'ta ödenir" diye deftere
yazılmış bir borç, o repack'i **her push'ta koşan bir kapı** üretiyorsa
gerçekte defer edilemez; iki commit ötede patlar. Plan, borcun kapatıcısını
değil, **kapatmayı hangi kapının ne zaman zorladığını** da yazmalı.

**Kalan operasyonel adım (kod dışı):** teslim zip'lerinin hash'i değişti
(iç `fba120ce…`, dış `c205a02e…`); Dropbox taşıma birimine yeniden
kopyalanmalı. `ID_RESIDUAL_ACCEPTANCE.md`'ye kaydedildi.

**Yöntem dersi:** Denetim sırasında iki kez tahmin zinciri kuruldu ("5 dosya
eksik", "son 2 test failing") — her ikisi de taze koşumda çürütüldü (17/17 OK,
rc=0). Rapor içindeki her sayı bu yüzden koşum-kanıtına bağlıdır, hafızaya değil.

### A11y turu (2026-10-02): kapı iki yüzeye yayıldı, eşikler sayfa-bazlı

Kapsam genişletmeden önce **hangi HTML yüzeylerinin görünür olduğu ölçüldü**
(`preview_server` CI ile birebir konfigürasyonda başlatılıp rotalar tarandı):

| Yüzey | Sunucu yanıtı | Hüküm |
|---|---|---|
| `/preview.html` (+ `/`, `/index.html`) | 200 (32 672 B) | taranıyordu |
| `/guide.html` | **404** — *"mirror'da yok"* | gerçek ikinci yüzey → **kapsama alındı** |
| `/slides_z3/preview.html` | 404 | rota `endswith(".png")` kabul ediyor — HTML yüzeyi değil |
| `apps/dashboard-shadcn/index.html` | servis edilmiyor | Vite kabuğu (`<script src="/src/main.tsx">`); taramak boş `<div id="root">` |
| `_calisma/landing/landing.html` | servis edilmiyor | `landing_src.html`'den derleniyor, **publish workflow'u repo'da hiç yok** (deploy/pages/netlify/vercel: 0 eşleşme) |

Yani "diğer görünür sayfalar" **tek bir** yüzey demekti. Kapsam
`a11y_gate_config.json` → `pages` listesine taşındı: koddan gizli sayfa
taranmaz, `pages` boş olamaz, her sayfa kendi `blocking`/`warn` eşiğini ve
**kendisine ait** allowlist kayıtlarını kullanır (`page` anahtarı olmayan
kayıt tüm sayfalarda geçerlidir; `pages`'te olmayan bir sayfaya yazılan
kayıt reddedilir — gerekçeli olsa bile **ölü konfig** sayılır).

**Kapsam genişletmesi 44 gerçek ihlali açığa çıkardı** — hepsi ölçüldü ve
düzeltildi:

| Sayfa | Bulgu | Düzeltme |
|---|---|---|
| `/guide.html` | `label` **critical ×43** (47 input'un 43'ü etiketsiz) | 39 checkbox'a yanındaki `.title`/`span` metninden `aria-label`; 4 text input'a `id`+`for` |
| `/preview.html` | `scrollable-region-focusable` **serious ×2** (`#runstream`, `#stdout`) | `tabindex="0"` — klavye ile kaydırılabilirlik (WCAG 2.1.1) |

Düzeltmenin kör regex değil **ölçümle** doğrulandı: uygulanan desenler
39 + 4 = **43** eşleşme verdi, yani axe'in işaret ettiği 43 node ile birebir
örtüştü. `guide.html`'de `region` ×32 ve `landmark-one-main` ×1 kaldı; ikisi de
`warn` seviyesidir ve tanımı gereği kapıyı düşürmez.

**Kontrast düzeltmesi (aynı tur).** `a11y_gate.py` yalnız **varsayılan (koyu)
temayı** tarıyor; açık tema hiç görülmüyor. Elle ölçüldü: `--muted: #70695f`
açık temada `#live-status` üzerinde **4.34:1**, `--surface-raised` üzerinde
**4.17:1** — AA 4.5:1'in altında, yani **gerçek** bir kusur. Düzeltildi:
`#655e56` → en kötü **4.92:1**. `tokens.css` + `tailwind.css` birlikte
(`check_tokens.py` kural 6) ve kontrast sözleşmesi
`test_design_token_contrast.py` ile kilitlendi (mutasyon kanıtlı: eski değer
3 testi kırmızıya düşürüyor).

**Artefakt şeması sözleşmeye bağlandı.** `a11y_report.json`'ın üst düzey
anahtarları, `summary`'nin beş eşik kovası ve `violations` satır yapısı
**birebir** sabitlendi (ekleme de silme de kapıyı kırar); `sum(summary) ==
len(violations)` bütünlük eşitsizliği, kovası olmayan yeni bir level'in
sessizce yutulmasını engelliyor. Sözleşmeyi yazarken **gerçek bir
tutarsızlık** bulundu: level adı tire, summary kovası alt çizgiyle
ayrışmıştı → ikisi birebir aynı yapıldı.

**Fail-closed'in tarayıcı katmanı.** Sayfa 404/5xx verirse kapı FAIL eder.
Bu şart: Playwright 404'te exception atmaz, boş `<body>`'yi tarayıp "0 ihlal"
der ve kapı yeşil geçerdi — yani kapsam genişletilmiş *görünürken* hiçbir şey
taranmamış olurdu. Ölçüldü: kapsamdaki `/guide.html` mirror kopyası olmadan
kapı `FAIL` + net hata verdi.

**Yöntem dersi (ölü allowlist):** allowlist `incomplete` girdilerine **hiç
uygulanmıyordu** (`classify_violations`'ın incomplete döngüsü
`_allowlisted_nodes`'i çağırmıyordu). Yazılacak gerekçeli kayıt defterde
"allowlist'li" görünür, kapıda **hiçbir şey yapmazdı** — kayıt gibi görünen
etkisiz kalem. `incomplete` yolu da allowlist'e uyar hâle getirildi ve
mutasyonla kanıtlandı (kayıt, başka sayfaya sızmıyor).

### R3 turu (2026-10-02): `make accept` CI bağlamında gerçekten yeşile getirildi

İstek "CI-linux satırını ekle, `make accept`'i CI-bağlamında yeşile çıkar"
 idi. **Satır 6 zaten vardı** (`c934c16`, main'de); ölçüm iki ayrı gerçeği
 ortaya çıkardı:

1. **`make accept` hiçbir workflow'da koşmuyordu.** "CI-bağlamında yeşil"
   bir çıkarımdı, ölçülmüş bir gerçek değil.
2. **Satır 6 artık üretilmiyordu.** CI'yi vekil konteynerde (`ubuntu:24.04`
   + CI'ın birebir tarifi + digest-pini tectonic) çalıştırıldı:
   tectonic kanonik hash'i **birebir** `ad8fca69…` (= satır 1) çıktı →
   ölçüm ortamı sadık; sapma **yalnız pdflatex**'te ve sürüm kayması
   (defter 1.40.29, güncel apt 1.40.25). `make accept` → **FAIL**.

**Ayrıca ölçülen, R3'ün konusu olmayan bir kusur:** `pdf` hedefi
`SOURCE_DATE_EPOCH`'u motor ortamına **ihraç ediyor**, `check`/`accept`
**etmiyordu** (beton `:-0`'a düşüyor). Yani **kabul edilen PDF ile teslim
edilen PDF farklı epoch ile derleniyordu** — kabul edilen şey gönderilen
şey değildi. Ölçüm: epoch 12345 verilince kanonik hash `544516b0…` →
`95900f50…` değişiyor.

**Varsayılan SDE tuzağı (aynı turda ölçüldü, kapatıldı):** ilk düzeltmede
varsayılan `HEAD`'in commit zamanı yapıldı; bu, kanonik hash'i **her
commit'te** değiştirdiği için yerel `make accept` yalnız HEAD'in doğru
commit'e denk gelmesi hâlinde yeşil kalıyordu (`HEAD=bcb963b` iken
kırmızı ölçüldü). Kabul edilebilir çıktı commit'e bağlı olamaz; varsayılan
teslim sabitine (`1786924800`) çivilendi. Artık `pdf`/`check`/`accept`
aynı epoch'ta çalışır ve iki bağlam da yeşildir:

| bağlam | kanonik hash | defter satırı | sonuç |
|---|---|---|---|
| CI-linux (`ubuntu:24.04` digest-pini, tectonic 0.17.0 digest-pini) | `ca3c5918…` | 8 | `KABUL`, EXIT=0 |
| yerel (macOS/Homebrew, aynı epoch) | `10d44856…` | 7 | `KABUL`, EXIT=0 |

**Kalan tek engel — repo dışı:** `texlive-accept` işi workflow'a eklendi ve
15. required adayı olarak kayıt altına alındı (gate_jobs kümesi, smoke
sayıları 14→15, `PUBLISH_SCENARIO` tablosu 29 job). Ancak canlı branch
protection `main` üzerinde hâlâ **14** context tutuyor (ölçüldü:
`strict=true`, `enforce_admins=true`, 14 context); `check-status-check-names`
kapısı bu yüzden `"missing": ["TeXLive acceptance — CI-linux pinned
(fail-closed)"]` ile kırmızı. Bu repodan düzeltilemez — GitHub ayarıdır ve
`PUT` koruma nesnesinin tamamını değiştirdiği için `enforce_admins` ve
`strict` alanlarını da geri yazmadan yapılmamalıdır. Karar insanın.

**Düzeltme ve kanıt:**

| | `pdf` üretir | `check`/`accept` ölçerdi |
|---|---|---|
| öncesi | SDE=HEAD → `57c91a07…` | SDE=0 → `544516b0…` |
| sonrası | SDE=HEAD → `57c91a07…` | **SDE=HEAD → `57c91a07…`** |

Motor **CI'da pinlendi**: kabul artık `ubuntu@sha256:a853f94d…` digest-pini
konteynerde + SDE `1786924800` sabitiyle koşuyor (`runs-on: ubuntu-latest`
üzerinde koşmak aynı borcu yeniden üretirdi). Kapanış kanıtı:

| bağlam | kanonik hash | `make accept` |
|---|---|---|
| CI vekili (pinli) | `ca3c5918…` | **KABUL**, EXIT=0 |
| yerel (Homebrew, aynı SDE) | `10d44856…` | **KABUL**, EXIT=0 |

`§4`'e satır 7 (yerel) ve satır 8 (CI-pinli) eklendi; ikisi de SDE'yi
taşıyor (kanonik hash SDE'ye bağlı). Satır 6 **silinmedi** — protokol
"yeni bağlam → yeni satır, üstüne yazma" diyor; sapma gerekçesiyle kayda
geçti. 7 yeni test, ikisi mutasyon kanıtlı: epoch ihracı geri alınınca ve
digest pini etikete düşünce kırmızıya dönüyor.

**Mutasyon kanıtı ve bulunan boşluk.** Dört senaryo denendi (sayfa filtresi
silindi, eşik override'ı yok sayıldı, toplam özet ilk sayfadan alındı, 404
kontrolü silindi). **Dördüncüsü hiçbir testi kırmadı**: 404'ün *tespiti* test
kapsamı dışındaydı, yalnız hata *işleme*si test edilmişti. Boşluk kapatıldı
(sahte playwright ile tarayıcı katmanı testleri); artık kontrolü silmek 3
testi kırmızıya düşürüyor.

Kapanış kanıtı: `pre-commit run --all-files` **EXIT=0** (52/52) ·
`check_unit_tests_hook.sh` **RC=0** (152 test dosyası) · CI-benzeri gerçek
koşu (verisiz taze runner taklidi + iki mirror kopyası) **`verdict: PASS`,
EXIT=0, iki sayfada da PASS**.

## 3. Kalan riskler

| # | Risk | Etki | Azaltım / durum |
|---|---|---|---|
| R1 | tectonic→TeXLive göçü **planlandı, uygulanmadı** | iki motor paralel yaşamaya devam; byte-düzeyi çapraz eşitlik imkânsız (font/ligatür farkı — ölçüldü) | `TEXLIVE_MIGRATION_PLAN.md` 7 faz; Faz 3 `/ID` kabul raporu; her faz ölçüm kapılı |
| R2 | pdfTeX rastgele trailer `/ID` kalıntısı kalıcı | qpdf `--static-id`/`--remove-metadata` gideremiyor (donmuş bulgu ×2 doğrulandı) | sözleşme /ID-kanonik karşılaştırmaya bağlı; kanonik hash oturumlar arası kararlı — içerik determinizmi zaten kanıtlı; **haftalık determinism-trend CI job'ı (2026-09-17) kararlılığı sürekli izler**: `determinism-trend.yml` cron + `record_determinism_trend.py` jsonl trendi (tazelik + kaynak-uzlaşma [platform-scoped] + darwin/linux kapsam değişmezleri, fail-closed) |
| R3 | CI runner'ında TeXLive paket seti yerel Homebrew'dan farklı olabilir — **KAPATILDI (2026-10-02)** | öngörülen "Faz 6'da hash sapması" **gerçekleşti**: `§4` satır 6 (`092154a0…`) oluşturulduğu gün 5 bağımsız koşumda birebir tekrarlanmıştı, aynı tarif bugün üretmiyor. Ölçülen sapma pdfTeX **1.40.29 → 1.40.25**; tectonic tarafı birebir `ad8fca69…` çıktığı için sapma ölçüm ortamı değil **motor sürümü** kayması | CI-linux kabulü **`ubuntu@sha256:a853f94d…` digest-pini konteynerde** koşuyor (yeni `texlive-accept` işi, fail-closed), SDE **1786924800** sabit; `§4` satır 7 (yerel) + satır 8 (CI-pinli) aynı SDE ile ölçüldü. Satır 6 **silinmedi** — protokol "yeni bağlam → yeni satır" diyor, kayma gerekçesiyle kayda geçti. Ayrıca: `make accept` daha önce **hiçbir workflow'da koşmuyordu** |
| R4 | base-image güncellemeleri yeni CVE getirebilir | trivy gate kırmızı (fail-closed — beklenen davranış) | desen: floor + defter + tek build-arg (apt + pip iki katman); **haftalık tarama yerleşti (2026-09-20): `docker-security.yml` cron `43 3 * * 1` + script-parite smoke job'ı** — push koşumu 35516666559 success (image-scan + smoke, runner'da SKIP yolu logda dürüst); cron **PR #52 merge'i ile tetiklenebilir hâle geldi, ancak henüz ateşlenmedi**. PR #52 merge: 2026-09-30T22:19:48Z, `ali-han-kaya` → `8314fde4a4` (schedule yalnız default branch'ten koşar; ölçüldü: `docker-security.yml` main'de `schedule: cron 43 3 * * 1` içeriyor, API `state=active`). **İlk ateşleme 2026-10-05T03:43Z'de** (Pzt) — 2026-10-02 ölçümünde `event=schedule` tetikli koşum sayısı **0**; tüm koşumlar push/workflow_dispatch. Kontrol (mekanizma çalışıyor): `determinism-trend` aynı repoda schedule ile iki kez ateşlendi (2026-09-21 failure, 2026-09-28 success). Yani bu satır **kapalı değil, bekliyor** — kayıt `test_security_cron_schedule.py` ile mekanik olarak çivilendi |
| R5 | colima arm64 → amd64 qemu emülasyonu | yerel build yavaş; CI amd64 native olduğundan **CI riski değil** | `DOCKER_SMOKE_PLATFORM` override; dokümante |
| R6 | `reword-working`→`main` birleştirmesi — **KAPATILDI (2026-10-02)** | öngörülen 22 dosyalık çakışma **1** ölçüldü (README.md changelog tablosu, saf add/add); iki blokaj plan dışı çıktı | iki aşamalı merge: PR #77 (`ddde854`) + PR #78 (`18e0403`); `MERGE_DECISION_…md` §5 güvenlik ağı birebir uygulandı → §2 "R6 turu"; her iki merge için `git revert -m 1` açık |
| R7 | 15 untracked test dosyası (CI job'larında koşan ortam-bağımlılar) + pre-commit bataryası (132) ile kayıtlı full liste (141) farkı | kafa karışıklığı riski; kapsam sessizce zayıflamaz (drift guard + coverage kapısı) | drift-guard çıktısı farkı açıkça not eder; EXCLUDE listesi gerekçeli |
| R8 | K19 coqtop yok / K9 lake ağırlığı | opsiyonel katmanlar SKIP | tasarım gereği; `--coq-proof` bayrağı dokümante; K9 elan kurulumu ile açılabilir |
| R9 | **CI'daki a11y taraması veri varken oluşan pano yüzeyini görmüyor** | a11y kapsamı dolu panonun kapsamından **dar**; ölçüm: yerelde `preview.html` 36 `incomplete` node veriyor, CI artefaktında 2, verisiz CI-benzeri koşuda 5. `#trend` grafiğinin SVG `<text>` node'ları ancak veri varken DOM'a girdiği için taranmıyor; `scrollable-region-focusable` de bu yüzden kayıtta yoktu (verisiz koşuda da çıktı) | **açık** — a11y job'una tohumlanmış bir trend geçmişi verilmeli. Yerel/CI farkının kalan kısmı çalışma ortamından (chromium/font) geliyor; nedeni tam ölçülmedi |
| R10 | a11y kapısı **tek temayı** tarıyor (varsayılan/koyu) | açık temadaki kontrast hataları kapıdan görünmez; ölçülen `--muted` 4.17:1 kusuru bu yüzden yakalanmadı, elle ölçümle bulundu | kısmen kapatıldı: kontrart sözleşmesi testi **her iki temayı** da kilitliyor. Tarama yüzeyinin iki temaya genişlemesi yapılmadı |

## 4. Kanıt dizini

- `docs/FINAL_RC_REPORT.md` — P0 tabloları, ölçülen kanıtlar, açık borç kapanışları
- `docs/ci_simulate/texlive_determinism/texlive_determinism_report.txt` — determinizm kanıtı
- `docs/ci_simulate/docker_security_smoke/docker_security_smoke_report.txt` — build+scan+health kanıtı
- `docs/MERGE_DECISION_reword-working_to_main.md` · `docs/TEXLIVE_MIGRATION_PLAN.md` · `docs/DOCKER_SECURITY_PATCHING.md`
- GitHub Actions: koşum 35161423568 (ilk — 3 borç), 35163054257 (3/3 success), 35163906063 (rapor commit'i, 3/3 success)
- **R6 turu (2026-10-02):** PR #77 (`ddde854`) + PR #78 (`18e0403`). PR koşumları 37034123236 / 37034128875 — 14/14 required check, 54 pass / 0 fail. Merge sonrası ana-dal: `verify-delivery` 37035461060 (P0=0, P1=0 · `byte-identical repack OK` kanıt 2/2), `docker-security` 37035460831 (Trivy 28 hedef, 0 bulgu), `test-smoke`. Kapı zinciri yerelde: `pre-commit run --all-files` EXIT=0 (52 Passed), `verify_delivery.py --full` TÜMÜ PASS, `gen_changelog --check` rc=0, `test_gen_changelog` 72/72, `test_k6_determ_canonical` 44/44
- **A11y turu (2026-10-02):** rota envanteri ölçüldü (`preview_server` yalnız `/preview.html` + `/guide.html` HTML servis ediyor); kapsam 2 sayfaya yayıldı ve **44 gerçek blocking ihlal** bulundu (`label` ×43 · `scrollable-region-focusable` ×2) ve düzeltildi. Kontrast: `--muted` #70695f → #655e56 (açık tema en kötü 4.17:1 → 4.92:1). Artefakt şeması sözleşmeye bağlandı (`REPORT_KEYS`/`SUMMARY_KEYS`/satır yapısı + `sum(summary)==len(violations)`). Zincir: `pre-commit run --all-files` EXIT=0 (52/52), `check_unit_tests_hook.sh` RC=0 (152 dosya), CI-benzeri gerçek koşu `verdict: PASS` / EXIT=0. Testler: `test_a11y_gate.py` 73 test · `test_design_token_contrast.py` 6 test
- Bu oturum koşumları: unit batarya 132/132; smoke 25/25; sync/coverage/drift kapıları rc=0; stub testler 4/4 + 7/7 + 17/17

## 5. Sonuç

Taranan sekiz katmanın yedisi **ölçülmüş yeşil** kanıtla kapalı; sekizincisi
(TeXLive göçü) planlı ve her fazı ölçüm kapılı. Kalan risklerin tamamı ya
tasarım gereği SKIP (R2/R5/R7/R8), ya da planı yazılmış göç (R1) sınıfında;
R6 birleştirme riski 2026-10-02'de ölçülerek kapatıldı (§2 "R6 turu").
A11y yüzeyi de aynı gün iki sayfaya yayıldı ve sayfa-bazlı eşik konfigine
geçti; genişleme 44 gerçek ihlali ortaya çıkardı, hepsi düzeltildi (§2
"A11y turu"). Kalan iki a11y riski **ölçülmüş olarak açık** kaydedildi:
**R9** (CI taraması veri varken oluşan pano yüzeyini görmüyor) ve **R10**
(kapı tek temayı tarıyor).
