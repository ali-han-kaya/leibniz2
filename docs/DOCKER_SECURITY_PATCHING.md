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
| Python zinciri (pip) | builder + runtime stage'lerde `pip install --upgrade` floor'ları | setuptools/wheel gibi image'e taşınan Python paketi CVE'leri | `--upgrade "pkg>=<floor>"` — asla `latest` |

Aynı üç kural her iki katmanda da geçerli:

1. **Yalnız etkilenen paket** — genel `upgrade`/`dist-upgrade` yapılmaz; taban
   sürümü değişmez, diff yüzeyi küçük kalır, davranış kayması ölçülebilir olur.
2. **Floor minimumdur, pin maksimum değildir** — `>=`/`=` floor'ları yalnız
   en düşük yamalı sürümü zorlar; base image daha yenisini taşıyorsa o
   kullanılır (yamalar birikir, sürümler geri gitmez).
3. **Kanıt zorunludur** — yama iddiası kurulumun kendisinden doğrulanır
   (apt katmanı `dpkg-query -W` çıktısıyla — **yalın paket adıyla**:
   `pkg=sürüm` sözdizimi apt'a geçer ama dpkg-query'ye geçmez, canlı
   build'de ölçüldü; pip katmanı `pip show` sürümüyle) ve Trivy'nin
   yeniden taramasıyla kapanır.

## Katkı sözleşmesi (yeni bulgu geldiğinde)

1. Trivy gate'inin tablo çıktısındaki paket + "Fixed version" değerini al.
2. `SECURITY_PATCH_PACKAGES` default'una `paket=floor` ekle (aynı paketin
   mevcut floor'u varsa yükselt) ve CVE-defteri bloğuna kaydı yaz
   (CVE kimlikleri + floor + kanıt tarihi).
3. Sistem-paket katmanıysa aynı satırı bu dokümandaki CVE-defterine de işle.
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
bookworm dağıtım pini ve pip floor deseni (`--upgrade "pkg>=x"` + asla
`pip install --upgrade` tek başına). Desenin bozulması (ör. floor'un
silinmesi, tüm-upgrade'e geçilmesi) testi fail yapar → commit bloke olur.
