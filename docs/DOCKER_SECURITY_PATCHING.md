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

## İki katman

| Katman | Nerede | Ne zaman | Desen |
|---|---|---|---|
| Sistem paketleri (apt) | Dockerfile runtime stage, `SECURITY_PATCH_PACKAGES` ARG | Debian kütüphane CVE'leri (ör. libpcre2-8-0) | `--only-upgrade <pkg>=<floor>`, `--no-install-recommends`, liste temizliği, kurulan sürüm kanıta yazılır |
| Python zinciri (pip) | builder + runtime stage'lerde `PYTHON_SECURITY_PATCH_PACKAGES` ARG (global default + bare redeclare) | setuptools/wheel gibi image'e taşınan Python paketi CVE'leri | `--upgrade $PYTHON_SECURITY_PATCH_PACKAGES` — floor'lar ARG default'unda, asla floorsuz |

Aynı üç kural her iki katmanda da geçerli:

1. **Yalnız etkilenen paket** — genel `upgrade`/`dist-upgrade` yapılmaz; taban
   sürümü değişmez, diff yüzeyi küçük kalır, davranış kayması ölçülebilir olur.
2. **Floor minimumdur, pin maksimum değildir** — `>=`/`=` floor'ları yalnız
   en düşük yamalı sürümü zorlar; base image daha yenisini taşıyorsa o
   kullanılır (yamalar birikir, sürümler geri gitmez).
3. **Kanıt zorunludur** — yama iddiası kurulumun kendisinden doğrulanır
   (apt katmanı `dpkg-query -W` çıktısıyla — **yalın paket adıyla**:
   `pkg=sürüm` sözdizimi apt'a geçer ama dpkg-query'ye geçmez, canlı
   build'de ölçüldü; pip katmanı `pip show` sürümüyle — floor eki
   `sed 's/[><=!~].*//'` ile kırpılır, yalın paket adı). Aynı üç kural iki
   ARG mekanizmasına da uygulanır: floor'lar ARG default'unda yaşar (tek
   kopya — CVE-defteri), empty-guard net "yama yok" kanıtı verir, kurulum
   kanıtı build log'una yazılır.

## Lean (K9) varyantı — opt-in hedef ve AYRI Trivy job'ı

Taban imaj K9'suz kalır; Lean toolchain (~1 GB) yalnız bilinçli opt-in'de iner
ve **ayrı** bir Trivy job'unda taranır — iki gate yüzeyi birbirini örtmez
(taban tarama toolchain katmanlarıyla şişmez, varyant taraması tabanın
sonucunu gizlemez).

| Parça | Yer | Sözleşme |
|---|---|---|
| Opt-in anahtarı | `Dockerfile` → `ARG INSTALL_LEAN=0` (`lean-runtime` stage) | default `0` → taban build aynı paket yüzeyi; yalnız `--build-arg INSTALL_LEAN=1` kurulumu açar |
| Hedef | `FROM runtime AS lean-runtime` (son stage) | `docker build --target lean-runtime --build-arg INSTALL_LEAN=1 -t verify-dashboard:lean .` |
| Pinned bootstrap | `ELAN_RELEASE` + `ELAN_SHA256_AMD64` / `ELAN_SHA256_ARM64` | `sha256sum -c` uyuşmazlıkta build kırmızı; slim imajda `curl` yok (ölçüldü) → indirme python3 stdlib ile |
| Pinned toolchain | `ARG LEAN_TOOLCHAIN="leanprover/lean4:v4.14.0"` | tek kaynak: `_calisma/lean_reduct/lean-toolchain` + `verify_delivery.LEAN_TOOLCHAIN`; `stable`/`nightly` gibi yüz-üzeri kanal yasak |
| Kurulum kanıtı | `lean --version` + `lake --version` | çıktı pin'in sürümünü içermiyorsa build exit 1 (fail-closed) |
| Ayrı Trivy job'ı | `.github/workflows/docker-security.yml` → `lean-image-scan` | `target: lean-runtime` + `INSTALL_LEAN=1`, ayrı cache scope (`scope=lean`), Trivy `CRITICAL,HIGH` + `exit-code: 1`; kanıt adımı Trivy'den ÖNCE toolchain'i konteynerde çağırıp pin'e eşleştirir |

Sözleşme testleri: `test_dockerfile_security_patching.py::TestLeanVariantContract`
(Dockerfile) ve `test_gated_schedules.py::TestLeanImageScanJob` (workflow).

## Katkı sözleşmesi (yeni bulgu geldiğinde)

1. Trivy gate'inin tablo çıktısındaki paket + "Fixed version" değerini al.
2.   `SECURITY_PATCH_PACKAGES` default'una `paket=floor` ekle (aynı paketin
   mevcut floor'u varsa yükselt) ve CVE-defteri bloğuna kaydı yaz
   (CVE kimlikleri + floor + kanıt tarihi).
3. Sistem-paket katmanıysa aynı satırı bu dokümandaki CVE-defterine de işle;
   Python-paketi katmanıysa `PYTHON_SECURITY_PATCH_PACKAGES` default'una
   `paket>=floor` ekle (pip gereksinim sözdizimi) ve Dockerfile'daki
   PYTHON-CVE-defteri bloğuna kaydı yaz.
4. `_calisma/CIKTI/docker_security_smoke.sh` ile build+scan+health kanıtını
   üret; `test_dockerfile_security_patching.py` sözleşme testlerinin
   üzerinden geç.
5. `docs/FINAL_RC_REPORT.md` kanıt tablosuna before/after bulgu kaydını ekle.

## CVE-defteri

| Paket | CVE'ler | Floor | Kanıt |
|---|---|---|---|
| libpcre2-8-0 | CVE-2026-86145 (OOB write), CVE-2026-89161 (pcre2_jit_match memory corruption) | 10.42-1+deb12u2 (önce 10.42-1+deb12u1) | 2026-09-16: yerel trivy 0.74.0 ilk koşumda 2 HIGH yakaladı → yama → 0 bulgu; CI koşum 35161423659 (13 Eylül kırmızı run'ı aynı CVE'lerle) before/after kanıtı. 2026-09-17: desenle yeniden doğrulandı (smoke PASS, 0 bulgu). **2026-10-15: taze smoke KIRMIZI (fail-closed doğru çalıştı)** — u1 Debian pool'undan düştü, build `E: Version '10.42-1+deb12u1' for 'libpcre2-8-0' was not found` ile rc=100; `apt-cache policy` bookworm-security adayını **10.42-1+deb12u2** (Installed/Candidate) gösterdi → floor u2'ye yükseltildi, Dockerfile CVE-defteri bloğuna floor-geçmişi işlendi. **2026-10-16: taze smoke PASS (rc=0)** — yama kanıtı `dpkg-query` → `libpcre2-8-0 10.42-1+deb12u2` ("already the newest version"), trivy 0.74.0 **trivy_findings=0 (Clean)**, `health_http=200` / `health_body=ok` / `container_health=healthy`, `verdict=PASS`; `test_dockerfile_security_patching.py` 15/15 (floor u1'e geri alınınca kırmızıya döndüğü mutasyonla kanıtlandı). Kanıt: `docs/ci_simulate/docker_security_smoke/docker_security_smoke_report.txt` — gitignored yerel kanıt; kalıcı kayıt bu satır. |

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
