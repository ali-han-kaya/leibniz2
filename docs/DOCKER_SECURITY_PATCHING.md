# Docker Güvenlik-Yama Deseni (Trivy fail-closed döngüsü)

Bu doküman, base-image güncellemelerinin getirdiği CRITICAL/HIGH Trivy
bulgularını **otomatik kapatan** güvenlik-yama deseninin referansıdır. Desen,
2026-09-16'da `libpcre2-8-0` HIGH CVE çiftinde (CVE-2026-86145,
CVE-2026-89161) doğdu ve 2026-09-17'de `SECURITY_PATCH_PACKAGES` build-arg
ile genelleştirildi.

## Kapalı döngü

```
Trivy gate kırmızı
  (CI: docker-security workflow — CRITICAL,HIGH + ignore-unfixed + exit-code 1)
        │
        ▼
Bulgunun paketi + yamalı sürümü tespit edilir
  (trivy tablosunda "Fixed version" sütunu; Debian tracker'dan teyit)
        │
        ▼
Floor sürüm CVE-defterine yazılır
  (Dockerfile: SECURITY_PATCH_PACKAGES default'u — kalıcı, işlenmiş kayıt)
        │
        ▼
Image yeniden build + scan
  (yerel tek komut: _calisma/CIKTI/docker_security_smoke.sh)
        │
        ▼
Gate yeşil → satırlar Dockerfile'da DURUR
```

Son adım kasıtlıdır: bulgu kapandıktan sonra da floor satırları silinmez.
Amaçları (1) base-image geri kayması durumunda **hızlı tekrar yama** —
default arg her build'de taze uygulanır, (2) **sürüm-için-dokümantasyon** —
hangi CVE'nin hangi floor'la kapatıldığı image'in kendisinde yaşar.

## Üç katman

| Katman | Nerede | Ne zaman | Desen |
|---|---|---|---|
| Sistem paketleri (apt) | Dockerfile runtime stage, `SECURITY_PATCH_PACKAGES` ARG | Debian kütüphane CVE'leri (ör. libpcre2-8-0) | `--only-upgrade <pkg>=<floor>`, `--no-install-recommends`, liste temizliği, kurulan sürüm kanıta yazılır |
| Python zinciri (pip) | builder + runtime stage'lerde `PYTHON_SECURITY_PATCH_PACKAGES` ARG (global default + bare redeclare) | setuptools/wheel gibi image'e taşınan Python paketi CVE'leri | `--upgrade $PYTHON_SECURITY_PATCH_PACKAGES` — floor'lar ARG default'ında, asla floorsuz |
| Node zinciri (npm) | `apps/*/package.json` (`dependencies` + `overrides`) + `package-lock.json`; **tarama yüzeyi** `.dockerignore` | image'e girebilecek JS bağımlılığı CVE'leri (postcss/sharp/next) | `overrides` floor'ları (`^` = `>=`) + commit'lenmiş lockfile + context hijyeni |

Aynı üç kural üç katmanda da geçerli (npm karşılıkları parantez içinde):

1. **Yalnız etkilenen paket** — genel `upgrade`/`dist-upgrade` yapılmaz; taban
   sürümü değişmez, diff yüzeyi küçük kalır, davranış kayması ölçülebilir olur.
   (npm: yalnız ilgili `overrides` girdisi / doğrudan pin; `npm audit fix
   --force` tüm ağacı yeniden yazar — yasak.)
2. **Floor minimumdur, pin maksimum değildir** — `>=`/`=` floor'ları yalnız
   en düşük yamalı sürümü zorlar; base image daha yenisini taşıyorsa o
   kullanılır (yamalar birikir, sürümler geri gitmez). (npm: `^8.5.18` de
   floor'dur; `=8.5.18` **pin**'dir ve bu desende yanlıştır.)
3. **Kanıt zorunludur** — yama iddiası kurulumun kendisinden doğrulanır
   (apt katmanı `dpkg-query -W` çıktısıyla — **yalın paket adıyla**:
   `pkg=sürüm` sözdizimi apt'a geçer ama dpkg-query'ye geçmez, canlı
   build'de ölçüldü; pip katmanı `pip show` sürümüyle — floor eki
   `sed 's/[><=!~].*//'` ile kırpılır, yalın paket adı). Aynı üç kural iki
   ARG mekanizmasına da uygulanır: floor'lar ARG default'unda yaşar (tek
   kopya — CVE-defteri), empty-guard net "yama yok" kanıtı verir, kurulum
   kanıtı build log'una yazılır.

## npm katmanı: context hijyeni + `overrides` deseni

npm zinciri iki yönden farklıdır ve bu yüzden **kendi kapalı döngüsü** vardır.
Image'e `node_modules` **kurulmaz** — Dockerfile yalnız repo runtime setini
kopyalar, dashboard bağımlılıkları image'in parçası değildir. Trivy'nin image
taraması bu yüzden node ağacını **göremez**; image'de yalnız manifestler
(`package.json`) durur ve `node-pkg` satırı tanımı gereği `0` verir. Yani
Trivy npm katmanını ancak **sızıntı** varsa görür: bu katmanın kapısı
context sözleşmesi + sürüm floor'larıdır, image taraması değil.

### Önce iki hata sınıfını ayır

| Sınıf | Belirti | Kök neden | Düzeltme |
|---|---|---|---|
| Context sızıntısı | Bulgu var, **aynı commit CI'da hiç görünmüyor** | Host artefaktı build context'e sızdı: `.worktrees/`'daki bayat lock + `node_modules`, `.venv_z3` | `.dockerignore` hijyeni (kurallar aşağıda) — **sürüm yükseltme değil** |
| Gerçek sürüm bulgusu | Bulgu, image'e girebilecek pakete ait | Paketin yamalı sürümü floor'un altında | `dependencies`/`overrides` floor'u + lockfile |

2026-09-20 ölçümü (yerel canlı smoke, Trivy 0.74.0): ilk koşum **4 HIGH** —
postcss ×2 (CVE-2026-45623, CVE-2026-73646) + sharp ×2 (GHSA-f88m-g3jw-g9cj,
GHSA-rgj7-g3m4-5g8c); dördü de **context sızıntısı** (`.worktrees/`'daki eski
lock: postcss 8.4.31, sharp 0.34.5). Ayrıca **gerçek sürüm** bulgusu vardı:
`next 15.5.4` → GHSA-mwv6-3258-q52c + GHSA-q4gf-8mx6-v5v3 (fixed 15.5.15).
Döngü ikisini **ayrı yollarla** kapatır; sızıntıyı sürüm yükselterek kapatmak
yanlış teşhistir (o commit'te kapı yine kırmızı kalır).

### Context hijyeni kuralları

1. **Bare ad yalnız context kökünü eşler.** `.dockerignore`'daki
   `node_modules` satırı sadece kökteki dizini dışlar; `apps/*/node_modules`
   ve `_calisma/*/node_modules` sızar. Derinlik deseni `**/`'dir
   (`**/node_modules`, `**/.next`) — venv olayının (`.venv_z3` → pillow +
   setuptools dist-info, 16+ HIGH) aynı sınıf ve aynı çözümü.
2. **Her scratch dizini envanterde.** Bağlam üreticisi olan her dizin
   `.dockerignore`'da satır olarak yaşar: `.worktrees`, `**/node_modules`,
   `**/.next`, `.venv`, `**/.venv*`, `.lake`, `.vercel`. Yeni scratch dizini
   eklenirse ignore listesine de eklenir.
3. **Parite kuralı:** "CI'da görünmeyen bulgu kapı değildir, bağlam
   sızıntısıdır." Yerelde görüp CI'da görünmeyen her bulgu önce bir context
   sorunudur; sürüm floor'u en son çaredir.
4. **Ignore listesi bir yüzey sözleşmesidir:** image'e giren = taramanın
   gördüğü. Listede olmayan scratch dizini sessiz tarama körlüğüdür.
5. **Kapı fail-closed çalışır.** `check-unit-tests` her commit'te manifest'in
   tamamını koşar; `test_dockerfile_security_patching.py` manifest'te yer
   aldığı için `.dockerignore`/`package.json` sessizce bozulursa commit
   bloklanır — hijyen ya da floor geri alınamaz.

### `overrides` deseni

| Durum | Alan | Örnek |
|---|---|---|
| Doğrudan bağımlılık | `dependencies` | `next`: floor **15.5.15** (GHSA-mwv6-3258-q52c, GHSA-q4gf-8mx6-v5v3) — taban yükselince `^16.x` olabilir, floor geri gitmez |
| Geçişli (transitive) bağımlılık | `overrides` | `postcss: ^8.5.18`, `sharp: ^0.35.4` |
| Uygulanmış hâli (kanıt) | `package-lock.json` | `npm ci` CI'da aynı ağacı kurar |

- **Lockfile commit'lenir ve kanıttır:** floor'un gerçekten uygulandığının
  tek kanıtı `package-lock.json`'daki çözümlenmiş sürümlerdir (`npm ci`
  determinizmi korur). Sözleşme testi lock'u okur: floor → lock uyumu.
- **Kanıt komutları:** `npm ls postcss sharp next`, `npm audit`,
  `npm run typecheck`, `npm run build`.
- **Trivy'nin npm kanıtı dolaylıdır:** image node ağacını taşımadığı için
  npm floor'unun Trivy kanıtı **doğrudan** alınamaz. Zincir üçlüdür:
  `npm audit` (ağaç) + lock/`npm ls` (çözümleme) + Trivy Clean (image yüzeyi).
  2026-09-30 CI teyidi: PR #56 push koşusu (36756975805) ve main push koşusu
  (36760575089, `43c688b`) DB'yi her ikisinde koşum anında yeniden indirdi
  (`trivy-db:2`, 118.54 MiB) ve her hedefte 0 bulgu verdi (`'0': Clean`) —
  image yüzeyi, npm sızıntısı dahil, boş.

### npm-CVE-defteri

| Paket | Advisory/CVE | Floor | Kanıt |
|---|---|---|---|
| next | GHSA-mwv6-3258-q52c, GHSA-q4gf-8mx6-v5v3 | 15.5.15 | 2026-09-20 gerçek sürüm bulgusu (image'e girecek paket) → `dependencies` floor'u + lock; ikinci koşum `trivy_findings=0` (Clean), `verdict=PASS` |
| postcss | CVE-2026-45623, CVE-2026-73646 | `^8.5.18` (çözülen 8.5.28) | 2026-09-20 `.worktrees` sızıntısı (bayat lock 8.4.31) → `.dockerignore` `**/node_modules` + `overrides`; `npm audit` 0 bulgu |
| sharp | GHSA-f88m-g3jw-g9cj, GHSA-rgj7-g3m4-5g8c | `^0.35.4` | aynı koşum, aynı sınıf (bayat lock 0.34.5) |

Yeni girdiler buraya ve `package.json`'ın `overrides` bloğuna eklenir.

## Katkı sözleşmesi (yeni bulgu geldiğinde)

1. Trivy gate'inin tablo çıktısındaki paket + "Fixed version" değerini al.
2.   `SECURITY_PATCH_PACKAGES` default'una `paket=floor` ekle (aynı paketin
   mevcut floor'u varsa yükselt) ve CVE-defteri bloğuna kaydı yaz
   (CVE kimlikleri + floor + kanıt tarihi).
3. Sistem-paket katmanıysa aynı satırı bu dokümandaki CVE-defterine de işle;
   Python-paketi katmanıysa `PYTHON_SECURITY_PATCH_PACKAGES` default'una
   `paket>=floor` ekle (pip gereksinim sözdizimi) ve Dockerfile'daki
   PYTHON-CVE-defteri bloğuna kaydı yaz.

   npm katmanıysa önce **hata sınıfını ayır** (context sızıntısı mı, gerçek
   sürüm bulgusu mu): sızıntıysa `.dockerignore`'a `**/` deseni ekle, sürümse
   `overrides`/`dependencies` floor'u (`^`, asla `=`) + lockfile'ı güncelle ve
   npm-CVE-defterine yaz.

4. `_calisma/CIKTI/docker_security_smoke.sh` ile build+scan+health kanıtını
   üret; `test_dockerfile_security_patching.py` sözleşme testlerinin
   üzerinden geç.
5. `docs/FINAL_RC_REPORT.md` kanıt tablosuna before/after bulgu kaydını ekle.

## CVE-defteri

| Paket | CVE'ler | Floor | Kanıt |
|---|---|---|---|
| libpcre2-8-0 | CVE-2026-86145 (OOB write), CVE-2026-89161 (pcre2_jit_match memory corruption) | 10.42-1+deb12u1 | 2026-09-16: yerel trivy 0.74.0 ilk koşumda 2 HIGH yakaladı → yama → 0 bulgu; CI koşum 35161423659 (13 Eylül kırmızı run'ı aynı CVE'lerle) before/after kanıtı. 2026-09-17: desenle yeniden doğrulandı (smoke PASS, 0 bulgu). |

Yeni girdiler buraya ve Dockerfile'daki defter bloğuna eklenir.

## Test sabitlemesi

`_calisma/CIKTI/test_dockerfile_security_patching.py` (offline, stdlib-only)
Dockerfile'daki deseni sözleşme satırlarıyla sabitler: ARG default'unda
CVE-defteri girdisi, `--only-upgrade` (tüm-upgrade yasağı), apt liste
hijyeni, `dpkg-query` kanıt satırı, `rm -rf /var/lib/apt/lists/*`,
bookworm dağıtım pini, iki katmanın ortak ARG mekanizması
(`SECURITY_PATCH_PACKAGES` apt + `PYTHON_SECURITY_PATCH_PACKAGES` pip:
floor'lar ARG default'unda tek kopya, empty-guard, kurulum-kanıtı satırı)
ve pip floor deseni (`--upgrade $PYTHON_SECURITY_PATCH_PACKAGES` + asla
floorsuz). Desenin bozulması (ör. floor'un
silinmesi, tüm-upgrade'e geçilmesi) testi fail yapar → commit bloke olur.

bookworm dağıtım pini ve pip floor deseni (`--upgrade "pkg>=x"` + asla
`pip install --upgrade` tek başına). Aynı süit **npm katmanını** da sabitler:
context hijyeni (`.dockerignore`'da `**/node_modules`, `**/.next`, `.worktrees`
— bare ad tuzağı dahil), `overrides` floor'ları (`^`, asla `=`) + `next`
doğrudan floor'u, lockfile'ın floor'ları karşıladığı (`floor → lock` uyumu) ve
npm bölümünün doküman sözleşmesi. Süit manifest'te olduğu için
`check-unit-tests` her commit'te koşar: yüzeylerden biri sessizce bozulursa
commit bloklanır. Desenin bozulması (ör. floor'un silinmesi, tüm-upgrade'e
geçilmesi, `**/node_modules`'in bare'a düşmesi) testi fail yapar → commit
bloke olur.

