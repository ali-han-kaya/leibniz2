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
| 2 | **Patching** — yama-desen sözleşmesi | `check-dockerfile-security-patching` (`python3 -m unittest _calisma.CIKTI.test_dockerfile_security_patching`, `files: (^|/)Dockerfile$`, `pass_filenames: false`) | Herhangi bir yolda `Dockerfile` stage'liyken (`always_run` yok — nedensel sinyal korunur) | Sözleşme satırı bozulursa test fail → commit blok. Kapsam dışı Dockerfile varsa `test_no_uncovered_dockerfile` da fail eder. Dosya manifest'te yer aldığı için `check-unit-tests` de koşar |
| 3 | **Cron** — zamanlanmış tazeleme | `docker-security.yml` → `on.schedule: "43 3 * * 1"` | Pazartesi 03:43 UTC, push tetiklemesi olmadan | Hazırlıksız çıkan CVE'yi yakalar; koşum kaydına yazılır, sapma tablosu yönlendirir |

Kapı 1 ve 2 **yerelde**, kapı 3 **uzakta** koşar; üçü de aynı yüzeye bakar
(`Dockerfile` + smoke scripti) ve üçü de sessiz geçişe kapalıdır: 1 ve 2
sıfır-dışı çıkışla commit'i bloklar, 3 ise kanıtı boş bırakmaz — ilk
Pazartesi koşumu gelene kadar `schedule` satırı boş kalır.

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
| `check-dockerfile-security-patching` | `(^|/)Dockerfile$` — kök **ve** kök altı | `false` | Herhangi bir yolda `Dockerfile` sözleşmeyi tetikler |

**Boşluk (ölçüldü, kapandı).** Patching kapısı `^Dockerfile$` iken ikinci bir
`Dockerfile` eklenmesi onu tamamen kapsam dışı bırakıyordu: ne hook
ateşlenir ne sözleşme uygulanır. Bugün git-tracked Dockerfile sayısı 1,
yani boşluk gizliydi; ikinci dosya eklendiği anda sessizce açılırdı. Desen
`(^|/)Dockerfile$` yapıldı.

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

