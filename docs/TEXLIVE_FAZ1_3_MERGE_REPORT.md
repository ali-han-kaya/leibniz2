# TeXLive Faz 1-3 Teslim Raporu (PR #52)

Bu doküman, `texlive-faz-1-3` dalının teslimini kalıcı kayda geçirir. Dal
PR #52 ile merge edildiği için (aşağıya bak) PR açıklaması bir daha
yazılamıyordu; içerik burada yaşar.

Kapsam: 11 commit, dört mantıksal birim. Docker güvenlik katmanı ayrı
bölümde ayrıntılı — çünkü bu dalın asıl kalıcı katkısı o katmandır.

## Nasıl main'e girdi

| | |
|---|---|
| Dal | `texlive-faz-1-3` → `f265a87` (çakışma çözümü merge commit'i) |
| PR | #52 — `ci(docker): weekly cron security smoke + Dockerfile patching hook` |
| main merge commit'i | `8314fde` (merge-commit konvansiyonu) |
| PR CI | 54 pass / 5 skipping / 0 fail |
| Ölçek | 14 commit / 34 dosya, +3215 / −1019 (çözüm öncesi) |

main 19 commit öne geçtiği için PR `CONFLICTING/DIRTY` idi. Çakışma 6
dosyada çözüldü: `README.md`, `check_unit_tests.list`,
`test_coverage_report.py` (main'in sürümü esas alındı, changelog satırları
ve test listesi yeniden üretildi); `test_dockerfile_security_patching.py`
ve `docs/DOCKER_SECURITY_PATCHING.md` (BİRLEŞİM: main'in npm katmanı +
#52'nin pip ARG katmanı); `determinism_trend.jsonl` (append-only birleşim).

### Merge sırasında bulunan üç sessiz hata

Bunlar çözümün kendisinden çıktı ve dalın tesliminden daha değerli kayıtlar:

1. **Sessiz `import re` kaybı.** Auto-merge, `sync_check_unit_tests.py`'de
   main'in `import re`'sini düşürmüştü. D1'in `run_check_exclude_binding`
   kapısı `re.findall` kullanıyor ve `NameError` veriyordu → import geri
   eklendi, kapı rc=0'a döndü. Auto-merge'in "sorunsuz" görünmesi bu
   yüzden yeterli kanıt değildir.
2. **README'de bölüm kaybı.** main'in README'si esas alınınca #52'nin
   "PDF üretimi — iki motor paralel yaşam" bölümü düştü;
   `test_makefile_texlive` bunu zorunlu kılıyordu → geri eklendi.
3. **Test izolasyonu: canlı index imhası.** `test_update_changelog_hook.py`
   ve `test_sync_skills_index.py` sandbox'ta `git add -A` çalıştırıyordu.
   `git commit` pre-commit hook'larına `GIT_INDEX_FILE` verir ve pre-commit
   onu **mutlak** geçici dosyaya yönlendirir. Değişken temizlenmediği için
   sandbox'taki `git add -A`, `cwd=sandbox` olmasına rağmen canlı repo'nun
   index'ini yazıyordu: worktree kökü index'e göre farklılaştığı için tüm
   canlı girdiler düşüyor, sandbox fixture'ı yazılıyordu. Ölçüm: **613 → 4**
   ve **613 → 1** girdi; merge commit'i "files were modified by this hook"
   ile çöktü. `_GIT_ENV_STRIP` + `sandbox_env()` eklendi (`check_review_freshness.py`'deki
   mevcut desen), sonra 149 manifest testinin TAMAMI düşmanca `GIT_INDEX_FILE`
   altında tarandı: sıfır sızıntı.

## Dört birim

### B1 — Docker güvenlik yüzeyi (3 commit)

| Commit | Ne |
|---|---|
| `9c6e1b3` | `feat(ci)`: haftalık cron güvenlik yüzeyi — `docker_security_smoke.sh` + Dockerfile patching hook |
| `9b32376` | `feat(docker)`: pip yama katmanı ARG mekanizmasına katıldı |
| `b726e0c` | `docs(audit)`: R4 kapatıldı — haftalık docker-security taraması canlı |

Cron'un varlık sebebi: yeni CVE'ler en çok hazırlıksız anda gelir. Push
tetiklemesi o anda olmayabilir. Ayrıntılı aşağıda.

### B2 — TeXLive Faz 0-1: motor kilidi + paralel yaşam (1 commit)

`173a2f4` — `docs(texlive)`: iki Makefile (`docs/Makefile.texlive` ve
`docs/Makefile.tectonic`) yan yana yaşar; motor geçişi sürerken geri dönüş
yolu korunur. Sözleşme: `SOURCE_DATE_EPOCH` geçmiş commit'i yeniden
üretmez, `TEXINPUTS`/`TEXMFOUTPUT` kaynak dizinine asla yazmaz, 3 geçiş +
son geçişte `Rerun to get`=0, motor sürüm kilidi `engineinfo` ile kanıtlanır.

### B3 — Determinism trend yolu (3 commit)

| Commit | Ne |
|---|---|
| `abd3ec5` | `refactor(trend)`: kayıt yolundan bayat-48-saatlik rapor guard'ı kaldırıldı |
| `5fdf2e4` | `test(sync)`: sync lifecycle alt süreç regresyon kapısı olarak sabitlendi |
| `49008e6` | `feat(dashboard)`: TeX motor determinism trend paneli |

### B4 — CI kanıt kaydı (4 commit)

`5621c4e` (PR rotası için 3/3 CI kanıtı) + haftalık determinism ölçüm
kayıtları `6fe7c86`, `b5126f9`, `23a6ece`.

## Docker güvenlik katmanı

### Üç katman, tek desen

| Katman | Nerede | Floor örneği |
|---|---|---|
| Sistem (apt) | Dockerfile runtime stage, `SECURITY_PATCH_PACKAGES` | `libpcre2-8-0=10.42-1+deb12u1` |
| Python (pip) | builder + runtime, `PYTHON_SECURITY_PATCH_PACKAGES` | `setuptools>=80 wheel>=0.46.2` |
| Node (npm) | `apps/*/package.json` `overrides` + lockfile + `.dockerignore` | `next 15.5.15`, `postcss ^8.5.18`, `sharp ^0.35.4` |

Üç kural her katmanda aynı: (1) yalnız etkilenen paket, (2) floor minimumdur
— pin değil, (3) kanıt zorunludur (apt: `dpkg-query -W`, pip: `pip show`).
Floor satırları bulgu kapandıktan sonra **silinmez**: base-image geri
kayması durumunda hızlı tekrar yama ve sürüm-için-dokümantasyon.

Kapatılan CVE'ler: `CVE-2026-86145`, `CVE-2026-89161` (pcre2) ve npm
tarafında `GHSA-mwv6-3258-q52c` / `GHSA-q4gf-8mx6-v5v3` (next),
`CVE-2026-45623` / `CVE-2026-73646` (postcss), `GHSA-f88m-g3jw-g9cj` /
`GHSA-rgj7-g3m4-5g8c` (sharp).

npm katmanının kendi kapalı döngüsü vardır: image'e `node_modules`
**kurulmaz**, dolayısıyla Trivy'nin image taraması node ağacını göremez —
sızıntı varsa görür. Yani npm'in kapısı tarama değil, **context sözleşmesi
+ sürüm floor'larıdır**. İlk ölçümdeki 4 HIGH'ın tamamı context sızıntısıydı
(`.worktrees/`'daki bayat lock) ve sürüm yükselterek kapatılmamalıydı;
gerçek sürüm bulgusu ayrıydı (`next 15.5.4`).

### Zamanlanmış tarama: SKIP'ten gerçek koşuma

`docker-security.yml` Pazartesi 03:43 UTC'de koşar (determinism-trend
03:17 ile bilinçli çakışmaz). `smoke` job'ı `docker_security_smoke.sh`'i
koşar: build → Trivy gate (CRITICAL,HIGH, `ignore-unfixed`, `exit-code 1`)
→ konteyner + `/api/health` + HEALTHCHECK.

Bu üç aşamalı zincirin bugünkü hâli iki PR ile tamamlandı:

- **#61** — cron runbook satırı: beklenen log deseni ve sapma tablosu.
  O an job SKIP üretiyordu (ubuntu-latest'te Trivy yok).
- **#62** — `smoke` job'ına **pin'li Trivy kurulumu** (sürüm `0.69.3`,
  sha256 `1816b632…`, `sha256sum -c` ile doğrulamalı) + `Assert real run`
  adımı. Sürüm, `trivy-action@v0.35.0`'in varsayılanıyla **aynı** seçildi:
  `image-scan` job'ı o action'la taradığı için iki job tek motorla çalışır,
  kapılar birbirini çürütemez.

Sonuç: SKIP bir hata değildir ama CI'da **kanıt da değildir** — Trivy
kurulu bir runner'da SKIP, kurulumun sessizce bozulduğunun işaretidir ve
assert adımı onu kırmızıya çevirir. Script'in SKIP sözleşmesi korunur
(triviysiz yerel makine). Ölçülen iki mod:

| | SKIP modu | Gerçek koşum |
|---|---|---|
| Log | 3 satır | ~15 satır |
| Kanıt satırları | `trivy=`, `verdict=` **yok** | `trivy=0.69.3`, `trivy_findings=0`, `trivy_clean=Clean`, `health_http=200`, `container_health=healthy`, `verdict=PASS` |
| Sağlık zinciri | koşulmadı | HTTP 200 + `healthy` |

### Kapılar

`test_gated_schedules.py` (manifest'te, her commit'te koşar):

- **K1/K2** — schedule'lı workflow en az bir kapı script'i çağırır ve gate
  script'i `run:` adımında çağrılır (`uses:` action'ları substitute edemez)
- **K3** — smoke job'ı Trivy'yi kurar; sürüm + sha256 pin'li ve hash
  `sha256sum -c` ile **gerçekten** doğrulanır
- **K4** — runbook'un beklenen deseni kaynaktan **türetilir** (cron ifadesi,
  kanıt satırları, SKIP satırı, fallback notu elle kopyalanmaz)
- **K5** — CI'da SKIP kanıt sayılmaz: `verdict=PASS` yoksa job kırmızı, ve
  assert smoke adımından sonra çalışır
- **K6** — runbook'un `trivy=<sürüm>` satırı workflow'un `TRIVY_VERSION`
  pin'iyle eşleşmeli (motor paritesi)

`test_dockerfile_security_patching.py` deseni (üç katman, floor'lar,
`dpkg-query`/`pip show` kanıtları, `.dockerignore` hijyeni, `overrides` +
lock uyumu) sabitler.

## Ölçülmüş kanıt

| Koşum | Run | Sonuç |
|---|---|---|
| PR #52 | — | 54 pass / 5 skipping / 0 fail |
| PR #62 smoke job | `36791434082` (job `110144991391`) | `trivy.tgz: OK` · `trivy=0.69.3` · 0 bulgu · `verdict=PASS` |
| main push (#62 sonrası) | `36795021299` | `verdict=PASS`, `health_http=200`, `container_health=healthy` — SKIP satırı yok |
| main `verify-delivery` | `36795021220` | 23 pass / 5 skipping |
| pre-commit (merge) | — | 48 `Passed`, `COMMIT_RC=0`; tam manifest **149/149** |

## Kapanmamış

- **İlk Pazartesi cron koşumu henüz olmadı.** Runbook'un kayıt satırı boş
  duruyor ve ilk gerçek cron koşumundan sonra doldurulacak. Beklenen desen
  push koşumunda doğrulandı, ama cron'un kendi koşumu ayrı bir olaydır.
- `trivy_sarif_pr_comment.js:21-28` `severityOf()` eksik severity'yi HIGH
  sayıyor (#54'te 25 sahte HIGH bloğu) — bu dalın kapsamı dışında.
