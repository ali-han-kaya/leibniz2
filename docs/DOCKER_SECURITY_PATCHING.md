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
        │   ← kapı 3: cron "43 3 * * 1" (Pazartesi 03:43 UTC) · push · dispatch
        ▼
Bulgunun paketi + yamalı sürümü tespit edilir
  (trivy tablosunda "Fixed version" sütunu; Debian tracker'dan teyit)
        │
        ▼
Floor sürüm CVE-defterine yazılır
  (Dockerfile: SECURITY_PATCH_PACKAGES default'u — kalıcı, işlenmiş kayıt)
        │   ← kapı 2: check-dockerfile-security-patching (sözleşme)
        ▼
Image yeniden build + scan
  (yerel tek komut: _calisma/CIKTI/docker_security_smoke.sh)
        │   ← kapı 1: check-docker-security-smoke + CI smoke job
        ▼
Gate yeşil → satırlar Dockerfile'da DURUR
        │   ← kapı 3: sonraki Pazartesi aynı yüzeyi yeniden ölçer
        ▼
Döngü kapanır: yeni bulgu gelene kadar kayıt sabit kalır
```

Son adım kasıtlıdır: bulgu kapandıktan sonra da floor satırları silinmez.
Amaçları (1) base-image geri kayması durumunda **hızlı tekrar yama** —
default arg her build'de taze uygulanır, (2) **sürüm-için-dokümantasyon** —
hangi CVE'nin hangi floor'la kapatıldığı image'in kendisinde yaşar.

Döngünün her adımının **kim tarafından zorlandığı** aşağıdaki kapı
tablosunda tanımlıdır.

## Kapı zinciri — üç uygulama katmanı

Aşağıdaki "Üç katman" tablosu **paket** zinciridir (apt/pip/npm): *neyin*
yamandığını söyler. Bu tablo ise **zorlama** zinciridir: *deseni kim, ne
zaman uygular*. İkisi karıştırılmamalıdır — biri dosya/içerik yüzeyi,
öteki kapı tetiklemesidir.

| # | Kapı | Nerede tanımlı | Ne zaman koşar | Fail-closed kanıtı |
|---|---|---|---|---|
| 1 | **Smoke** — build + Trivy gate + canlı sağlık | CI: `docker-security.yml` → `smoke` job (`timeout-minutes: 30`). Yerel ikizi: `check-docker-security-smoke` (`bash _calisma/CIKTI/docker_security_smoke.sh`) | CI'da push + cron + `workflow_dispatch`; yerel ikiz yalnız `Dockerfile` stage'liyken | Kanıt dosyasında `verdict=PASS` yoksa `Assert real run` adımı `exit 1` — SKIP kanıt sayılmaz. Build/Trivy/sağlık hatasında script rc=1 |
| 2 | **Patching** — yama-desen sözleşmesi | `check-dockerfile-security-patching` (`python3 -m unittest _calisma.CIKTI.test_dockerfile_security_patching`, `files: (^\|/)(Dockerfile\|\.dockerignore\|package(-lock)?\.json)$`, `pass_filenames: false`) | Herhangi bir yolda `Dockerfile`, `.dockerignore` ya da bir `package.json`/`package-lock.json` stage'liyken (`always_run` yok — nedensel sinyal korunur) | Sözleşme satırı bozulursa test fail → commit blok. Kapsam dışı Dockerfile varsa `test_no_uncovered_dockerfile` da fail eder. Dosya manifest'te yer aldığı için `check-unit-tests` de koşar |
| 3 | **Cron** — zamanlanmış tazeleme | `docker-security.yml` → `on.schedule: "43 3 * * 1"` | Pazartesi 03:43 UTC, push tetiklemesi olmadan | Hazırlıksız çıkan CVE'yi yakalar; koşum kaydına yazılır, sapma tablosu yönlendirir |
| 4 | **npm audit** — bağımlılık advisory eşiği | CI: `docker-security.yml` → `npm-audit` job; araç `_calisma/CIKTI/npm_audit_gate.py`. Eşik **tek kaynak**: workflow env `NPM_AUDIT_GATE_LEVEL` (bugün `high`) | CI'da push + PR + cron + `workflow_dispatch` | Eşiğe eşit/ağır bulguda script `exit 1`. `--require-real` ölçülemeyen koşumu (SKIP) de kırmızıya çevirir — sessiz yeşil yok |

Kapı 1 ve 2 **yerelde** (pre-commit), kapı 3 ve 4 **uzakta** (CI) koşar.
Kapı 1-3 aynı yüzeye bakar (`Dockerfile` + smoke scripti); kapı 4 farklı bir
yüzeye — lockfile'daki **çözülmüş npm ağacına** — bakar, çünkü image'e
`node_modules` kurulmaz. Dördü de sessiz geçişe kapalıdır: 1 ve 2 sıfır-dışı
çıkışla commit'i bloklar, 4 kırmızı bir CI job'ı üretir, 3 ise kanıtı boş
bırakmaz — ilk Pazartesi koşumu gelene kadar `schedule` satırı boş kalır.

**"Zorlayıcı" ne demek (dar tanım).** Kapı 3 ve 4'ün blokaj gücü, mevcut
Trivy gate'iyle aynı sınıftadır: job `exit 1` verir, koşum kırmızıdır, PR ve
push görünürlüğünde kalır. Branch-protection'ın *required check* kümesi ise
`verify.yml`'den türetilir (`status_checks.py`) — `docker-security.yml`
job'ları o kümenin dışındadır. Kapı 4'ü required check yapmak ayrı bir
sözleşme kararıdır (branch protection + türetim kaynağı), bu turda
istenmedi; bugünkü blokaj "kırmızı koşum", merge-engeli değil.

Kapı 1'in CI job'ı Trivy'yi `image-scan` işinin kullandığı
`trivy-action@v0.35.0` varsayılanıyla **aynı sürümde** (`0.69.3`) ama
kendisi kurar (URL + sürüm + sha256 üçü de pin'li). İki iş böylece farklı
motorlarla değil aynı motorla döner; ayrıntı "Motor paritesi — ölçülmüş"
bölümündedir.

### Tetikleme yüzeyleri: ölçülen asimetri ve kapandığı

İki pre-commit kapısı aynı dosyaya bakar ama **eşleşme kalıpları
farklıdır**:

| Kapı | `files:` | `pass_filenames` | Sonuç |
|---|---|---|---|
| `check-docker-security-smoke` | `Dockerfile` — kök değil, yolun herhangi bir yerinde eşleşir | belirtilmemiş (varsayılan) | Alt dizinde bir `Dockerfile` da tam build+scan'i tetikler |
| `check-dockerfile-security-patching` | `(^\|/)(Dockerfile\|\.dockerignore\|package(-lock)?\.json)$` — kök **ve** kök altı | `false` | Herhangi bir yolda `Dockerfile` **veya** npm yüzeyi (`.dockerignore`, `package.json`, `package-lock.json`) sözleşmeyi tetikler |

**Boşluk (ölçüldü, kapandı).** Patching kapısı `^Dockerfile$` iken ikinci bir
`Dockerfile` eklenmesi onu tamamen kapsam dışı bırakıyordu: ne hook
ateşlenir ne sözleşme uygulanır. Bugün git-tracked Dockerfile sayısı 1,
yani boşluk gizliydi; ikinci dosya eklendiği anda sessizce açılırdı. Desen
`(^|/)Dockerfile$` yapıldı; 2026-10-28 genişlemesinde npm yüzeyleri de
eklendi (`\.dockerignore` + `package(-lock)?\.json`) — aksi hâlde bir floor
veya ignore satırı değişip de hook ateşlenmezse npm katmanı commit-anında
hiç denetlenmezdi (sözleşme yalnız Dockerfile'a bakardı).

Sözleşmenin **kendisi** iki stage'li bookworm pini beklediği için her
Dockerfile'a körlemesine uygulanamaz (meşru bir tek-stage yardımcı image'ı
kırılırdı). Bu yüzden çözüm genişletme değil **görünür kılma**dır:
`repo_dockerfiles()` keşfi, kapsam dışı bir Dockerfile varsa
`test_no_uncovered_dockerfile` fail-closed durur. Yani ikinci bir Dockerfile
artık sessizce geçmez — ya sözleşmeye eklenir ya da gerekçesiyle kapsam
dışı bildirilir.

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
4. **Override kapısı her build yolunda aynıdır** — CI `docker-security`
   image-scan build'i ve smoke build'i (yerel/CI) tek çözümleyiciden geçer:
   `_calisma/CIKTI/docker_patch_build_args.sh`. Floor'lar **Dockerfile
   ARG'larından** okunur (workflow'da ikinci kopya yok → drift imkânsız);
   `SECURITY_PATCH_PACKAGES` / `PYTHON_SECURITY_PATCH_PACKAGES` doluysa o
   kazanır (CI kanalı: `workflow_dispatch` input'u → repo değişkeni
   `vars.*`). Boş override "yama katmanını kapat" demek **değildir**
   (empty-guard zaten "yama yok" kanıtı verir) — bu yüzden boş değer
   default'u asla ezmez, default okunamazsa build fail-closed durur.

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
| Doğrudan bağımlılık | `dependencies` | `next`: floor **15.5.28** (GHSA-mwv6-3258-q52c, GHSA-q4gf-8mx6-v5v3 + 2026-10-28 CRITICAL advisory'leri) — taban yükselince `^16.x` olabilir, floor geri gitmez |
| Geçişli (transitive) bağımlılık | `overrides` | `postcss: ^8.5.18`, `sharp: ^0.35.5`, `source-map-js: ^1.2.2`, `undici: ^7.30.1`, `body-parser: ^2.3.1`, `fast-uri: ^3.1.9`, `zod: ^4.6.6`, `@modelcontextprotocol/sdk: ^1.31.1`, `hono: ^4.13.11`, `ip-address: ^10.7.4` |
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
| next | GHSA-mwv6-3258-q52c, GHSA-q4gf-8mx6-v5v3, GHSA-8h8q-6873-q5fj, GHSA-p293-qw3h-jr36, GHSA-2xp9-vwfh-vxw4, GHSA-2464-fhr4-w9xw | 15.5.28 | 2026-09-20 gerçek sürüm bulgusu (image'e girecek paket) → `dependencies` floor'u + lock; ikinci koşum `trivy_findings=0` (Clean), `verdict=PASS`. 2026-10-28: yeni advisory'ler 15.5.15'i **CRITICAL**'a düşürdü (30 GHSA, aralarında iki RCE) → floor 15.5.28 |
| postcss | CVE-2026-45623, CVE-2026-73646 | `^8.5.18` (çözülen 8.5.28) | 2026-09-20 `.worktrees` sızıntısı (bayat lock 8.4.31) → `.dockerignore` `**/node_modules` + `overrides`; `npm audit` 0 bulgu |
| sharp | GHSA-f88m-g3jw-g9cj, GHSA-rgj7-g3m4-5g8c, GHSA-wq5f-xc86-pv6w | `^0.35.5` | aynı koşum, aynı sınıf (bayat lock 0.34.5); 2026-10-28 librsvg CVE-2026-96889 → 0.35.5 |
| source-map-js | GHSA-68fv-2mgg-jv7q | `^1.2.2` | 2026-10-28: 1.2.1 → 1.2.2 (event-loop DoS) |
| undici | GHSA-4w7w-5xrc-9h26, GHSA-2m5v-pch6-74hx | `^7.30.1` | 2026-10-28: next'in geçişli HTTP istemcisi; 7.30.0 → 7.30.1 |
| body-parser | GHSA-27r3-jxmh-p828 | `^2.3.1` | 2026-10-28: sıkıştırılmış gövde sonrası trailing-byte DoS (2.3.1 çözüldü) |
| zod | GHSA-mrhx-c7xc-m3w5 | `^4.6.6` | 2026-10-28: aşırı-büyük koleksiyon doğrulamasında bellek tükenmesi (`shadcn` dev-CLI ağacı) |
| @modelcontextprotocol/sdk | GHSA-6qxp-vccf-f47h, GHSA-6prh-2h8m-c8cw | `^1.31.1` | 2026-10-28: OAuth kimlik sızıntısı + cross-origin redirect; `shadcn` dev-CLI'ın geçişlisi |
| fast-uri | GHSA-w74x-v6f9-j3xg, GHSA-xhq7-xmqj-769h, GHSA-wjr9-j795-jxcr, GHSA-333x-w4r6-6crp | `^3.1.9` | 2026-10-28: URI şema/path/host karışıklığı (trend-db ile aynı sınıf) |
| hono | GHSA-5r4p-p66f-jhc7 | `^4.13.11` | 2026-10-28: `serveStatic` çift decode → middleware bypass (4.13.14 çözüldü) |
| ip-address | GHSA-rxp7-6hxx-x8q5 | `^10.7.4` | 2026-10-28: zone-id eşleşmesinde kuadratik zaman (10.7.5 çözüldü) |

Yeni girdiler buraya ve `package.json`'ın `overrides` bloğuna eklenir.

### Çalışma alanı envanteri (2026-10-28 genişlemesi)

Sözleşme başlangıçta tek çalışma alanıyla (`apps/dashboard-next`) sınırlıydı.
Diğer node yüzeyleri de image bağlamına giren manifestler taşıdığı için aynı
iki yüzey (floor + hijyen) onlara da uygulandı. Ölçüm tek yönlüdür: her satır
`npm audit --package-lock-only` çıktısındaki advisory'ye dayanır, floor'lar
`npm install --package-lock-only` sonrası lock'ta doğrulanır.

| Çalışma alanı | Floor'lar | Advisory | Ölçüm / durum |
|---|---|---|---|
| `apps/dashboard-next` | `next` 15.5.28 · `postcss` ^8.5.18 · `sharp` ^0.35.5 · `source-map-js` ^1.2.2 · `undici` ^7.30.1 · `body-parser` ^2.3.1 · `fast-uri` ^3.1.9 · `zod` ^4.6.6 · `@modelcontextprotocol/sdk` ^1.31.1 · `hono` ^4.13.11 · `ip-address` ^10.7.4 | GHSA-mwv6-3258-q52c, GHSA-q4gf-8mx6-v5v3, GHSA-f88m-g3jw-g9cj, GHSA-8h8q-6873-q5fj, GHSA-wq5f-xc86-pv6w, GHSA-68fv-2mgg-jv7q, GHSA-4w7w-5xrc-9h26, GHSA-27r3-jxmh-p828, GHSA-w74x-v6f9-j3xg, GHSA-6qxp-vccf-f47h, GHSA-5r4p-p66f-jhc7 | 2026-10-28: zorlayıcı `npm audit` kapısı **ilk kez** ölçtü — 13 bulgu (1 CRITICAL, 7 HIGH, 4 MODERATE, 1 LOW) → eşik `high`'ta **0 bloklayan** (yalnız 2 LOW: `deepmerge`, `shadcn` dev-CLI). `npm ci` + `tsc --noEmit` + `next build` (7/7 sayfa) yeşil |
| `apps/dashboard-shadcn` | `vite` ^8.3.5 · `source-map-js` ^1.2.2 | GHSA-68fv-2mgg-jv7q (source-map-js), GHSA-698v-4r3x-3vcv + 4 vite/launch-editor GHSA'sı | 2026-10-28: `vite` 8.2.2 + `source-map-js` 1.2.1 → floor; `npm run build` (`tsc -b && vite build`) geçti, `npm audit` 0 |
| `apps/trend-db` | `prisma` / `@prisma/client` / `@prisma/adapter-pg` ^7.10.1 · `@prisma/config` ^7.10.1 · `deepmerge-ts` ^8.0.0 · `fast-uri` ^3.1.9 · `mysql2` ^3.23.1 | GHSA-ggr8-5vv4-36mx (deepmerge-ts), GHSA-3f6p-5ww8-9rcr (mysql2), GHSA-w74x-v6f9-j3xg (fast-uri) | 2026-10-28: 5 bulgu → 0; `prisma generate` + `tsc --noEmit` geçti (7.10.1 istemcisi üretildi) |
| `_calisma/pptx` | `image-size` ^2.0.3 | GHSA-5p2g-fcmc-qvqq (JXL/HEIF), GHSA-w3rx-r6r6-pgpr (ICNS) | 2026-10-28: floor uygulandı (pptxgenjs 4.0.1 → `image-size` ^1.2.1). `image-size` **runtime'da yüklenmiyor**: pptxgenjs dist'i yalnız `jszip` + `sizeof` require eder, ölçüldü (`require.cache` boş) → override sürüm tablosunu kapatır, davranış değişmez |
| `_calisma/docx` | (floor yok — `docx` 9.7.2 pin) | — | main'de **yok**: yalnız land edilmemiş dallarda (`fix/branch-red-jobs`, #54 soyu). Bugünkü ölçüm: `npm audit` 0 bulgu. Dal land ettiği gün (package.json göründüğü an) kayıt otomatik devreye girer |

**Kapsam dışı (gerekçeli):** `_calisma/video` — Remotion 4.0.530
advisory'lerinin yamalı sürümü yok; `npm audit`'in tek "fix"i 4.0.277'ye
**downgrade** öneriyor (`isSemVerMajor`). Floor yazılamaz, downgrade video
üretimini bozar. Kayıt süitteki `NPM_OUT_OF_SCOPE` içinde; gerekçesiz kayıt
FAIL eder. Remotion yamalı sürüm yayımladığında yeniden ölçülecek.

Bu turda sözleşmeye giren yeni kurallar:

6. **`latest` bir floor değildir.** `"latest"` / `"*"` / `"x"` aralıkları
   sürüm kararını registry'ye devreder: lock bir sürüme çözülür ama
   denetlenecek taban yoktur. dashboard-shadcn'ın altı `latest` girdisi
   ölçülen (lock'taki) sürümlerinin `^` floor'una çevrildi — `npm ci` aynı
   ağacı kurar, floor artık yazılı ve denetlenebilir.
7. **Scratch yüzeyi çalışma alanı başına beyan edilir.** Bu turda eklenen
   `.dockerignore` satırları: `**/dist`, `**/.vite`, `**/tsconfig.tsbuildinfo`,
   `**/*.pptx`, `apps/trend-db/generated`. Hepsi üretim artefaktı (git'te
   izlenmiyor: `git ls-files | grep -E '/dist/|/generated/'` → 0 satır). Bare
   `dist` yalnız kökte eşleşirdi; js build çıktısı derinlikte doğar
   (`apps/dashboard-shadcn/dist`, `_calisma/video/dist`).
8. **Kapsam keşfi fail-closed.** `repo_npm_workspaces()` repodaki her
   `package.json` dizinini bulur; kayıtlı olmayan ve gerekçeli kapsam-dışı
   listesinde yer almayan bir çalışma alanı varsa süit FAIL eder — yeni bir
   node yüzeyi sessizce kapsam dışı kalamaz (Dockerfile keşfiyle aynı desen).

### Zorlayıcı npm audit eşik kapısı (2026-10-28)

Floor'lar bir *desen* sözleşmesidir: `overrides` silinirse test düşer, ama
yeni bir advisory floor'ları güncelleyene kadar süit yeşil kalabilir — çünkü
offline test `npm audit` çalıştırmaz. Kırmızıyı üreten şey kapının kendisidir:
`npm-audit` job'ı, `npm_audit_gate.py`, eşik `NPM_AUDIT_GATE_LEVEL`.

| Soru | Cevap |
|---|---|
| Nereye bakar? | `npm_workspaces.present_workspaces()` — floor sözleşmesiyle **aynı kayıt** (tek kaynak). Yeni bir çalışma alanı eklendiğinde ikisi birlikte genişler |
| Nasıl ölçer? | `npm audit --package-lock-only --json --audit-level=<eşik>`; `node_modules` kurulmaz, lockfile'daki çözülmüş ağaç denetlenir |
| Eşik nerede? | Workflow `env: NPM_AUDIT_GATE_LEVEL` (**tek literal**). Script aynı env'i okur; CLI `--level` yalnız yerel/probe için. Adımda literal `--level` yasak (test pinler) |
| Hangi seviye bloklar? | `high` (varsayılan) → CRITICAL + HIGH. `critical` → yalnız CRITICAL. `moderate` / `low` → daha geniş |
| Ölçüm yapılamazsa? | SKIP: kanıt satırı `verdict=SKIP` yazar, çıkış 0. CI'da `--require-real` verildiği için SKIP **FAIL**'dir (npm kurulu bir runner'da SKIP = kapı körleşti) |
| Kanıt? | `docs/ci_simulate/npm_audit/npm_audit_report.txt` — çalışma alanı başına tek satır + son `verdict=` satırı; job log'unda da görünür (`if: always()`) |
| Yerel koşum? | `python3 _calisma/CIKTI/npm_audit_gate.py` (registry'deki her mevcut alan). Pre-commit'e **bilinçli olarak** bağlanmadı: hook ağ/registry gerektirir, offline commit'i bloklamamalı |

Kapsam-dışı bırakılan tek yüzey `_calisma/video`'dur (gerekçe yukarıda:
Remotion için yamalı sürüm yok) — gate onu taramaz, süit gerekçesiz kaydı
zaten FAIL eder. Yeni bir CVE düştüğünde akış: gate kırmızı → advisory
ölçülür → `package.json` `overrides`/`dependencies` floor'u → `npm install
--package-lock-only` → süit + gate yeşil. Gate hiçbir şeyi **otomatik
düzeltmez**; `npm audit fix --force` bilinçli olarak çağrılmaz (major
downgrade riski).

## Haftalık cron koşumu — ilk Pazartesi doğrulama (runbook)

`docker-security.yml` her Pazartesi **03:43 UTC**'de kendiliğinden koşar
(`43 3 * * 1`; determinism-trend 03:17 ile bilinçli çakışmaz). Push
tetiklemesi olmadan da koşmasının tek nedeni, yeni CVE'lerin en çok
hazırlıksız zamanda çıkmasıdır. Ama cron yalnızca koşmaz, **görünür
kanıt üretir** — bu bölüm o kanıtın nasıl okunacağını sabitler.

Önemli ayrım: cron ve push tetiklemesi **aynı workflow'u** çalıştırır, yani
log deseni aynıdır. Cron'un farkı tetikleyicidir, desenin kendisi değil.
Aşağıdaki desen henüz hiçbir Pazartesi cron koşumu gerçekleşmeden, bir
**push** koşumundan ölçülmüştür: run `36791434082`, job
`Local security smoke (script parity)` (PR #62). İlk Pazartesi koşumunda bu
satırların **aynen** çıkması, cron'un ilk doğrulamasıdır; çıkmazsa sapma
tablosuna geçilir.

### İki mod ve çıktılarının karşılaştırması

`docker_security_smoke.sh` iki meşru çıkış modu tanır. Hangisinin beklendiği
ortama bağlıdır; ikisi de exit 0'dır ve ikisi de "kanıt" üretir — ama
farklı miktarda:

| | SKIP modu (araç yok) | Gerçek koşum (CI'daki beklenti) |
|---|---|---|
| Tetikleyici | PATH'te docker **veya** trivy yok | `Install Trivy` adımı çalıştı |
| Çıkış kodu | 0 | 0 |
| Log satırı | 3 | ~15 |
| Kanıt satırları | `trivy=`, `verdict=` **yok** | `trivy=<sürüm>`, `trivy_findings=0`, `verdict=PASS` |
| Sağlık zinciri | yok (koşulmadı) | `health_http=200` + `container_health=healthy` |
| Nerede yaşar | Trivy'siz yerel makine | cron + push koşumu |

İki mod da ölçülerek karşılaştırıldı:

- **SKIP modu**, CI ile aynı koşulla yeniden üretildi (PATH'te docker ve
  colima var, trivy yok) → 3 satır, kanıt dosyası 2 satır, exit 0.
- **Gerçek koşum** yerelde çalıştırıldı → `verdict=PASS`, `trivy_findings=0`,
  `trivy_clean=Clean`, `health_http=200`, `container_health=healthy`,
  `PASS: build + trivy(CRITICAL,HIGH=0) + health(200, healthy)`.

İki ölçüm arasındaki tek yapısal fark kanıt miktarıdır: SKIP modu hiçbir
güvenlik iddiası üretmez (güvenlik gate'i **koşmadı**), gerçek koşum
üretir. Bu yüzden CI'da hangi modun geçerli sayıldığı bir karardır ve
aşağıdaki assert adımıyla **fail-closed** bağlanmıştır.

### Beklenen log deseni (CI)

`smoke` adımı ubuntu-latest'te Trivy'yi kendisi kurar (sürüm, `image-scan`
işinin kullandığı `trivy-action@v0.35.0` varsayılanıyla **aynı**: `0.69.3`;
URL + sürüm + sha256 üçü de pin'li). Script tam akışı koşar:

```
docker-security smoke evidence
image=leibniz2/verify-dashboard:smoke-local
docker_client=<sürüm>
docker_server=<sürüm>
colima=<durum>
platform=native
image_id=sha256:<hash>
trivy=0.69.3
trivy_findings=0
trivy_clean=Clean
host_port=<rastgele port>
health_http=200
health_body=ok
container_health=healthy
verdict=PASS
```

(stdout'da ayrıca: `PASS: build + trivy(CRITICAL,HIGH=0) + health(200, healthy)`)

Ardından `Assert real run (SKIP is not evidence in CI)` adımı yeşil verir:

```
OK: verdict=PASS — gerçek koşum kanıtı
```

`Show smoke evidence` adımı bu kez kanıt dosyasının **tamamını** basar
(`verdict=PASS` dahil) — SKIP koşumunda yalnız iki satır basıp fallback
notuna düşüyordu.

### SKIP modunun log deseni (fallback kanıt)

Trivy kurulamadığında ya da triviysiz bir makinede koşulduğunda:

```
docker-security smoke evidence
image=leibniz2/verify-dashboard:smoke-local
SKIP: trivy yok — güvenlik gate'i eksik, kısmi kanıt üretilmez
```

Kanıt dosyası bu modda da **üretilir** ve iki satırdır: `log()` başlık +
`image=` satırını `$OUT`'a yazar, SKIP satırı yalnız stderr'e gider. Bu
yüzden `cat ... || echo` fallback'i devreye girmez; fallback ancak script
`log()`'a ulaşmadan çökerse basılır:

```
(smoke kanıt dosyası yok — SKIP koşumunda üretilmez)
```

### Sapma tablosu

| Gözlenen | Anlamı | Yapılacak |
|---|---|---|
| `verdict=PASS` + `OK: verdict=PASS …` | Beklenen koşum; cron canlı ve gerçek kanıt üretti | Kayıt satırına yaz, sapma yok |
| `smoke` job **fail** (assert kırmızı) | Trivy kurulum adımı çalışmadı — SKIP'e düşüldü ya da script erken çıktı | `Install Trivy` adımının log'unu oku: sha256 uyuşmazlığı / ağ hatası. `sha256sum -c` çıktısını oku; `TRIVY_VERSION` + `TRIVY_SHA256` değerlerini release'in `trivy_<sürüm>_checksums.txt` dosyasıyla karşılaştır |
| `SKIP: trivy yok` logda **1 kez veya daha çok** | Kurulum sessizce bozuldu: Trivy gelmedi, yani **güvenlik gate'i hiç koşmadı**. Assert adımı bunu kırmızıya çevirir, ama sebebi SKIP'tir — `smoke` job'ının kızarması tek başına nedeni söylemez | Önce say: `gh run view <id> --log \| grep -c 'SKIP: trivy yok'`. `0` değilse koşum kanıt değildir, kayıt satırına **başarısız** yaz. Sonra `Install Trivy` adımına dön: `trivy.tgz: OK` ve `Version:` satırları yoksa kurulum adımı; `sha256sum -c` `FAILED` verdiyse `TRIVY_SHA256` sürümün `trivy_<sürüm>_checksums.txt` değeriyle uyuşmuyor |
| `smoke` job fail, `verdict=FAIL` | Gerçek ihlal: build / Trivy bulgusu / sağlık (fail-closed çalıştı) | `docs/ci_simulate/docker_security_smoke/docker_security_smoke_report.txt` kanıtını oku, bulguları "Katkı sözleşmesi" ile kapat, `docs/CI_GATE_TRIAGE.md`'ye kaydet |
| `Show smoke evidence` fallback notunu basıyor | Script `log()`'a ulaşmadan çöktü — hiç kanıt üretilmedi | Elle koşum log'unu oku; çökme noktası smoke adımına teşhis olarak eklenmeli |
| `trivy=` satırında beklenmeyen sürüm | `TRIVY_VERSION` ile `image-scan`'in motoru ayrışmış — iki job farklı motorla tarar, kapılar çelişebilir | Sürümü `trivy-action@v0.35.0` varsayılanıyla eşitle; parite bu eşitlikle korunur |
| `image-scan` job kırmızı | Cron'un **asıl** amacı gerçekleşti: CRITICAL/HIGH bulgu | Aynı Katkı sözleşmesi; `severity: CRITICAL,HIGH` + `ignore-unfixed` + `exit-code 1` sözleşmesi bozulmadıysa bu beklenen davranıştır |
| Ohafta hiç `docker-security` run yok | GitHub scheduler çalışmıyor (60 gün hareketsizlik politikası) ya da path filtresi | `gh run list --workflow docker-security.yml` ile doğrula; run yoksa `workflow_dispatch` ile elle koşup scheduler'ı canlandır |

Değişmez kural: **SKIP bir hata değildir, ama CI'da kanıt da değildir.**
SKIP'i "düzeltilecek sorun" sanıp betiği gevşetmek yerine, kurulumu
onarız; Trivy kurulu bir CI'da SKIP yalnızca **kurulumun sessizce
bozulduğunun** kanıtıdır ve assert adımı onu kırmızıya çevirir. Script'in
SKIP sözleşmesi korunur — çünkü triviysiz yerel makinelerde hâlâ doğru
davranıştır.

### Koşum kaydı

Cron'un ilk Pazartesi koşumu bittikten sonra **ilk satır** doldurulur. O
satır boş kaldığı sürece cron'un zamanlanmış koşumu doğrulanmamıştır.

| Koşum (run id) | Tetikleyici | Beklenen | Gözlenen | Sonuç |
|---|---|---|---|---|
| (henüz koşmadı — ilk Pazartesi 03:43 UTC) | `schedule` | gerçek koşum: `verdict=PASS` + `OK: verdict=PASS …` **+ `SKIP: trivy yok` 0 kez** | — | — |
| `36799425906` | `workflow_dispatch` (elle) | gerçek koşum | `trivy.tgz: OK` · `Version: 0.69.3` · `trivy=0.69.3` · `trivy_findings=0` · `trivy_clean=Clean` · `health_http=200` · `container_health=healthy` · `verdict=PASS` · `OK: verdict=PASS …` · **`SKIP: trivy yok` 0 kez** | ✅ |
| `36791434082` | `push` (PR #62) | gerçek koşum | `verdict=PASS`, 0 bulgu, health 200/healthy | ✅ |

**Elle koşum ne kanıtlar, ne kanıtlamaz.** `workflow_dispatch` aynı
workflow'u, aynı job'ı, aynı runner imajıyla çalıştırır — bu yüzden gerçek
koşum yolunu (kurulum → build → Trivy → health → assert) eksiksiz kanıtlar
ve runbook'un beklenen deseni üç ayrı koşumda (push, PR, dispatch) birebir
doğrulamıştır. Ama **scheduler'ı kanıtlamaz**: `schedule` tetikleyicisi
ayrı bir yoldur. Yani ilk satır boş kaldığı sürece "cron çalışıyor"
denemez.

Elle koşum komutu (CVE tazelemesi gibi olaylar için de aynı yol):

```bash
gh workflow run docker-security.yml --ref main
gh run list --workflow docker-security.yml --event workflow_dispatch
```

### İlk Pazartesi doğrulaması — SKIP dâhil

`schedule` tetikleyicisiyle koşan ilk run için tek bir koşum yeterlidir:
o run'un logu üç şeyi birden kanıtlar — gerçek koşumun kendisi, SKIP
olmadığı ve motor paritesi. Kabul ölçütü **üçünün birden** tutmasıdır:

| # | Ölçüm | Beklenen | Neden ayrı ölçüm |
|---|---|---|---|
| 1 | `grep -c 'OK: verdict=PASS'` | `1` | Gerçek koşumun çıktı adımı yeşil olduğunu kanıtlar |
| 2 | `grep -c 'SKIP: trivy yok'` | `0` | SKIP modu **exit 0** ve "kanıt" üretir; yalnız yeşil job bunu ele vermez |
| 3 | `grep -o 'trivy=[0-9.]*'` ↔ `TRIVY_VERSION` | eşit | `image-scan` ile aynı motor |

2 numaralı ölçümün ayrı olmasının sebebi: SKIP modu da başarılıdır. Script
SKIP'te de kanıt dosyasını üretir (başlık + `image=`), yalnız güvenlik
iddiası taşımaz — bu yüzden `smoke` job'ının yeşil olması tek başına
"gate koştu" demek değildir. `Assert real run` adımı bu yüzden vardır; ilk
Pazartesi doğrulamasında ise o adımın **kendi kanıtını** sayıyoruz.

```bash
# 1) schedule tetikleyicisiyle koşmuş run'ı bul (Elle koşumlar burada gelmez)
gh run list --workflow docker-security.yml --event schedule --limit 5

# 2) logu indir ve üç ölçümü yap
gh run view <run_id> --log > /tmp/cron-<run_id>.log
grep -c 'OK: verdict=PASS' /tmp/cron-<run_id>.log        # 1
grep -c 'SKIP: trivy yok'     /tmp/cron-<run_id>.log    # 0
grep -o 'trivy=[0-9.]*'       /tmp/cron-<run_id>.log | sort -u
```

Sonra "Koşum kaydı" tablosunun ilk satırına üç ölçümün ham çıktısı yazılır
(`Gözlenen` sütunu, `·` ile ayrılmış — `workflow_dispatch` satırındaki
biçimde). Ölçümlerden biri tutmazsa satır **boş bırakılmaz**, başarısız
işaretlenir: "satır boş = henüz doğrulanmadı" ile "satır kırmızı = doğrulandı
ama cron bozuk" farklı iddialardır.

`--event schedule` filtresi bilinçlidir: `push` ve `workflow_dispatch`
koşumları aynı job'ı çalıştırır ama `schedule` tetikleyicisinin **kendisi**
kanıtlamaz. Filtre olmadan ilk bulunan run `push` olur ve ilk Pazartesi
doğrulaması yanlışlıkla tamamlanmış sayılır.

### Motor paritesi — ölçülmüş

K6 (`trivy=<sürüm>` ↔ `TRIVY_VERSION`) yalnız workflow ↔ runbook eşleşmesini
zorlar; iki job'ın **gerçekten aynı motorla** taradığını koşum kanıtı
doğrular. `36799425906`'de ölçüldü:

| Job | Trivy sürümü | Kaynak |
|---|---|---|
| `image-scan` | `version: v0.69.3` | `trivy-action@v0.35.0` → `setup-trivy` (action'ın varsayılanı) |
| `smoke` | `Version: 0.69.3` | `Install Trivy` adımı, sha256 doğrulamalı |

Aynı koşumun logu ayrıca "current version is 0.69.3" diyerek bunu teyit
eder. Kapı iki işin birbirini çürütmesini böylece ölçülmüş olarak
engelliyor: sürüm ayrışırsa iki tarama farklı motorlarla döner ve
"biri yeşil biri kırmızı" belirsizliği oluşur.

## Katkı sözleşmesi (yeni bulgu geldiğinde)

1. Trivy gate'inin tablo çıktısındaki paket + "Fixed version" değerini al.
2. `SECURITY_PATCH_PACKAGES` default'una `paket=floor` ekle (aynı paketin
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
| libpcre2-8-0 | CVE-2026-86145 (OOB write), CVE-2026-89161 (pcre2_jit_match memory corruption) | 10.42-1+deb12u2 (önc. 10.42-1+deb12u1) | 2026-09-16: yerel trivy 0.74.0 ilk koşumda 2 HIGH yakaladı → yama → 0 bulgu; CI koşum 35161423659 (13 Eylül kırmızı run'ı aynı CVE'lerle) before/after kanıtı. 2026-09-17: desenle yeniden doğrulandı (smoke PASS, 0 bulgu). 2026-10-09 ROTASYON: Debian u1'i depodan çekti (E: Version '10.42-1+deb12u1' ... was not found → apt 100) — docker-security + audit_live_ci_sync kırmızısının kök nedeni; u2'ye taşındı (aday: apt-cache policy, bookworm-security). |
| libssl3 / openssl | CVE-2026-42767, CVE-2026-54874, CVE-2026-63072, CVE-2026-63074, CVE-2026-63076, CVE-2026-75803 (aynı kaynak paket iki adla taranıyor) | 3.0.22-1~deb12u2 | 2026-10-27: trivy bulgusu (libssl3 ×6 + openssl ×6); kurulu 3.0.20-1~deb12u2, aday `apt-cache policy` → bookworm-security. İki ad da floor'landı (tek kaynak paket). |
| tzdata | DLA-4792-1 (severity UNKNOWN; kurulu 2026b-0+deb12u1, düzeltme 2026c-0+deb12u1) | 2026e-0+deb12u1 | 2026-10-27: trivy bulgusu → yama; seviye-bilinmeyen sonuç kapı tarafından fail-closed bloklanır, floor `apt-cache policy` adayıyla sabitlendi. |
| pip (venv + sistem, ×2 katman) | CVE-2025-8869 (25.3), CVE-2026-1703 (26.0), CVE-2026-3219 (26.1), CVE-2026-6357 (26.1), CVE-2026-8643 (26.1.2), CVE-2026-13346 (26.2.0) — hepsi MEDIUM/LOW | **eklenmedi (kasıtlı)** | 2026-10-27: pip floor'u (>=26.1.2) pip'in kendi CVE'lerini kapatır ama son pip (26.2.2) vendor SBOM'unu (`pip/_vendor`) kapı setinde 4 HIGH taşıyor (trivy 0.69.3, rc=1); pip 24.0'ın CVE'leri MEDIUM/LOW olduğundan kapı setine girmez — floor **eklememek** doğru. Test bunu `assertNotIn("pip>=", …)` ile zorlar. |

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
npm bölümünün doküman sözleşmesi. 2026-10-28 genişlemesinde süit **çalışma
alanı kayıt defteriyle** (`NPM_WORKSPACES`) çalışır: her alan için floor →
lock uyumu, `latest` yasağı, scratch envanteri (.dockerignore'da tam satır),
gitignore paritesi ve hook `files:` deseni paritesi ayrı ayrı sınanır;
kayıtsız bir `package.json` keşif guard'ını düşürür (`NPM_OUT_OF_SCOPE`
gerekçesi zorunlu). Süit manifest'te olduğu için
`check-unit-tests` her commit'te koşar: yüzeylerden biri sessizce bozulursa
commit bloklanır. Desenin bozulması (ör. floor'un silinmesi, tüm-upgrade'e
geçilmesi, `**/node_modules`'in bare'a düşmesi) testi fail yapar → commit
bloke olur.

