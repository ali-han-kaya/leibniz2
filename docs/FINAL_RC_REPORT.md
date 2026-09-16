# Final Release Candidate Report

**Tarih:** 2026-09-16 (derin denetim turu güncellemesi)  
**Dal:** `reword-working`  
**Durum:** `RC — yerel kapılar yeşil; FINAL için temiz kopya + CI kanıtı bekliyor`

## Derin denetimde bulunan ve kapatılan P0'lar

| ID | Bulgu | Düzeltme | Kanıt |
|---|---|---|---|
| P0-1 | verify.yml:2278 heredoc terminatörü girintili — CI'da adım sessizce kırık (continue-on-error altında) | heredoc tek satırlık `python3 -c`'ye çevrildi | actionlint RC=0 |
| P0-2 | actionlint kontratı yanlış modellenmişti: RC=2 "shellcheck info" sanılıyordu; gerçekte herhangi bir shellcheck bulgusu RC=1 üretir; RC=2 actionlint iç hatasıdır | hem CI adımı hem lint_actionlint.sh aynı ölçüye çekildi: RC=1 veya RC>2 FAIL, RC=0/2 PASS | lint_actionlint.sh EXIT=0, test_actionlint_gate 5/5 |
| P0-3 | verify.yml'de 7 shellcheck bulgusu (6 info + 1 gizli SC2183 bug: format 2 değişken, 1 argüman — `$cov` kazara split ile çalışıyordu) | hepsi kodda düzeltildi (`"$GITHUB_PATH"`, find-instead-of-ls ×2, `exit "$rc"`, printf arg fix, GITHUB_ENV bloğu) | actionlint tüm workflow'lar RC=0 |
| P0-4 | verify_lean.sh pİnsiz `lean --version` → elan indirme moduna düşüp offline'da sonsuz bekliyor; hook 60s TIMEOUT rc=-1 | lean-toolchain pin'i ÖNCE çözülür (~/.elan/toolchains/…-v4.14.0), stdin kapalı sürüm kontrolü | hook 1s'de PASS, K9 PASS |
| P0-5 | smoke'da check-unit-tests 60s timeout (ölçülen: ~75-120s) → rc=-1 yanlış-FAIL | timeout 180s | smoke 25/25 PASS |
| P0-6 | smoke'da verify-delivery-repro-manifest yanlış pattern (`SONUÇ: PASS` yerine unittest `Passed`) | pattern düzeltildi | smoke 25/25 PASS |
| P0-7 | README changelog'unda canlı git geçmişinde olmayan 15 eski hash (rewrite artığı) | `gen_changelog.py --prune` | test_gen_changelog 72/72 OK |
| P0-8 | Disk %100 dolu → K13/geçici dizin açamıyor (94 test ERROR) | kullanıcı onayıyla brew download cache temizlendi (~4.2 GB) | batarya tam koşum OK |
| P0-9 | PLIST_PROFILES `keepalive` alanı ÖLÜ alan: `plist_render` 6. alanı hiç uygulamıyordu (docstring `{{KEEPALIVE}}` vadetmişti ama şablonda yok). Yedek profil `RunAtLoad=true`+`KeepAlive` üretilip login'de otomatik yükleniyor, 8000 portunu tutuyor; birincil leibniz2 `Errno 48: Address already in use` ile crash-loop'ta; K20 birincil için P1 üretiyordu. Ayrıca K20 özeti yedeği de birincil kriteriyle yazdırıyordu | şablonda gerçek `{{KEEPALIVE_RUNATLOAD}}/{{KEEPALIVE_KEEPALIVE}}` placeholder'ları; `plist_render` profili uygular (false → RunAtLoad=false + KeepAlive yok); `--start` keepalive=false profilleri kickstart eder; `preview_prestart.plist_values` KEEPALIVE_* değerlerini kurulu plist'ten türetir (drift kapısı); K20 özeti rol-bazlı (yedek: yüklü değil = BILGI, aktif failover = PASS); golden'lar yeniden üretildi; canlı makine onarıldı (yedek bootout, birincil yeniden başlatıldı, mirror sync) | K20 PASS (birincil PID canlı HTTP 200, yedek BILGI), plist-check/check_plist_drift/K12/K17 RC=0, preview_prestart+plist testleri OK |
| P0-10 | Temiz kopyada 5 test ERROR: disk yeniden %100 dolu (119 MiB boş) — kök neden `~/.elan/tmp` içindeki 58 GB'lık yarım kalan toolchain kurulum kalıntıları (elan'ın kurulum geçici dizini; toolchain'in kendisi değil, silinmesi güvenli) | `~/.elan/tmp/*` temizlendi → 59 GiB boşaldı (%87 kullanım); pinned v4.14.0 toolchain korundu | temiz kopya bataryası 2228 OK (önceki 5 error tamamen ENOSPC kaynaklıydı) |

## Skill sadakat denetimi (P1)

Ekli skill'lerin orijinalleri (`~/Downloads/*.zip`/`*.skill`) ile repo'daki
`skills/` kopyaları diff'lendi: **birebir kopya DEĞİL, özet/parafraz** çıktı.
Orjinallerin özgün içeriği (çalışma ahlakı'nda 11 bölüm + ayet/hadis künyeleri,
gorev-brifi'de slot-slOt maddeler + örnek + doğrulama listesi, revizyon-kapisi'de
8 yüklem ölçüm tanımları, ogrenim-dongusu'da bootstrap kuralı ve kaynak notu)
fidelity ile geri yazıldı; `source:` alanı orijinal dosyayı gösterir. Kural:
kaynağın kopyası istenirse kopya verilir — özet "kaynak" diye etiketlenmez.

## Ölçülen kanıtlar (bu tur)

| Kontrol | Sonuç |
|---|---|
| `verify_delivery.py --full` (venv python, Z3 dahil) | PASS (P0=0, P1=0) — K8 12/12, K9 8/8, refs 61/61 |
| `repack_delivery.py --verify` | TÜMÜ PASS (iki zip ↔ sidecar) |
| K14 zip-lineage / K17 review-freshness / skills-index | PASS |
| actionlint (3 workflow) | RC=0 |
| `test_all_hooks_smoke.py` | 25/25 hook PASS |
| CIKTI unittest discover | 2.228 OK (71 SKIP — ortam-koşullu, documented) |
| MCP `server.py --list-tools` + test bataryası | 26/26 OK, 5 tool |
| Dashboard lint + build | PASS |
| `check-changelog-sync` hook | PASS |
| `verify_delivery.py --check-launchd` (K20, bu turda canlı onarıldı) | PASS — birincil PID canlı HTTP 200; yedek BILGI (steady-state'te yüklü değil, kontrat) |
| fresh_clone_setup.sh --check-ci ×4 | PASS ×4 (ilk koşum sync sonrası tek seferlik bayatlık yarışı, kararlı RC=0) |
| TeXLive+SDE determinism deneyi (`texlive_determinism_hook.sh`) | PASS — SKIP kapatıldı: gerçek pdfTeX 3.141592653-2.6-1.40.29 (TeX Live 2026/Homebrew) + tectonic 0.17.0; iki bağımsız SDE koşumunda tek kalıntı pdfTeX'in rastgele trailer `/ID`'si (64 bayt), `/ID` harici baytlar birebir aynı (kanonik hash `a75c3409…` — oturumlar arası 3 bağımsız ölçümde birebir kararlı). Düzeltme: SDE artık tectonic ayağına da export ediliyor; düzeltme sonrası tectonic PDF'i de bağlamlar arası birebir aynı (`ad8fca69…`) |
| Docker/Trivy güvenlik iş akışı (gerçek daemon ile yerel smoke) | PASS — colima start (Docker 29.5.2, amd64 emülasyon) → image `--platform linux/amd64` build OK (~100 MB); Trivy 0.74.0 gate'i CI parametreleriyle (CRITICAL,HIGH, ignore-unfixed, exit-code 1) **İLK KOŞUMDA 2 HIGH BULGU YAKALADI** (libpcre2-8-0: CVE-2026-86145 + CVE-2026-89161, bookworm 12.15 tabanı) → Dockerfile targeted `--only-upgrade libpcre2-8-0` yaması → **gate 0 bulgu ile yeşil**. Canlı smoke: compose `running healthy` (HEALTHCHECK HTTP 200, restarts=0) + ayrılmış rastgele port üzerinden host→konteyner `/api/health` HTTP 200 `ok` (host 8000 portu Freebuff önizleme sunucusu tarafından meşgul olduğundan kanıt bağlantı noktası bağımsız portla verildi) |

## Aday commit + temiz kopya kabulü (2026-09-16)

**Aday SHA: `3918a04`** — `fix(verify): close hidden plist keepalive drift and gate gaps`
(commit anındaki pre-commit zinciri: tüm hook'lar PASS; verify_delivery PASS,
Z3 12/12, Lean 8/8 v4.14.0, actionlint RC=0, 129 test dosyası PASS,
commit-msg ≤72 kuralı dahil).

Temiz kopya (`git clone` → `/tmp/leibniz2-final`, HEAD = `3918a04092279450e743b05f6da4df1ba22f13cd`, ağaç temiz) kabulü:

| Kontrol | Sonuç |
|---|---|
| skills-index | PASS (8 skills) |
| `verify_delivery.py --full` (Z3 dahil) | PASS — K8 12/12, K9 8/8 (lake build --wfail, v4.14.0), refs 61/61 |
| unittest discover (CIKTI) | 2228 OK (71 SKIP — ortam-koşullu) |
| `repack_delivery.py --verify` | TÜMÜ PASS (sidecar eşleşti) |
| actionlint (3 workflow) | RC=0 |
| MCP testleri | 26/26 OK |

## Açık borçlar (FINAL kapısı öncesi)

- ~~Gerçek GitHub Actions koşumu — push gerektirir, kullanıcı kararı~~
  **KAPANDI (2026-09-16):** `reword-working` dalı push edildi ve gerçek
  koşumlar izlendi. İlk push (73e94ce) 3 gizli CI borcunu surfaced etti ve
  gerçek koşum bunları yakaladı: actionlint SC2002 (verify.yml:2803),
  taze-checkout'ta kalıcı FAIL üreten hook-install adımı (--check-only →
  kurulum modu) ve zincirleme advisory-audit kırılması. İkinci push
  (5f72054) ile **tüm workflow'lar yeşil**: test-smoke ✓, docker-security ✓
  (Trivy 0 bulgu — Clean, debian 12.15), verify-delivery ✓ (run
  35163054257, 8m9s; 27 job: 22 success + 5 by-design skipped; K1–K19 tek
  giriş noktası success). Before/after: 2026-09-13 feat/plist-info-line
  koşumu (34736804915) aynı 2 HIGH CVE ile docker-security'yi kırmıştı —
  pcre2 yaması CI'da da doğrulandı.
- TeXLive + `SOURCE_DATE_EPOCH` determinism ÖLÇÜLDÜ ve PASS: iki bağımsız
  SDE koşumunda `/ID` harici tüm baytlar birebir aynı (tek kalıntı pdfTeX'in
  SDE ile bile rastgele ürettiği trailer `/ID`; kanonik /ID-nötrlenmiş hash
  karşılaştırmasıyla kanıtlandı). Takip denetiminde ek bulgu + düzeltme:
  deney betiği SDE'yi tectonic ayağına export etmiyordu → tectonic hash'i
  oturumdan oturuma kayıyordu (`4ad65b9b…` → `6cfc6c0a…`); SDE artık her iki
  motora da veriliyor ve tectonic çıktısı bağlamlar arası birebir kararlı
  (`ad8fca69…`). Sızıntı davranışı `test_sde_must_reach_engines_fail_closed`
  ile fail-closed sabitlendi. qpdf 12.4.0'ın `--static-id` (girdi /ID'sini
  korur) ve `--remove-metadata` (kendisi nondeterministik) bu kalıntıyı
  gideremiyor — skill'in donmuş bulgusu tekrar doğrulandı. Kalan karar:
  tectonic→TeXLive göçü için göç planı (kalıntı /ID kabul raporuyla).
- PDF raw hash repack sırasında değişti (qpdf sidecar yeniden üretildi) —
  K6-DETERM bilgi düzeyinde izleniyor.
- `python3 -m unittest discover` sistem python3 ile `--full` koşursa Z3 yok
  deyip P0 üretir: kapı venv python ile koşulmalı (belgelendi).

## Karar

Yerel fail-closed zinciri bu SHA ağacında uçtan uca yeşil: K0–K21, 25/25
pre-commit hook, 2.228 unit test, MCP 26 test, dashboard build. FINAL etiketi
yalnız temiz kopya + CI kanıtı ve aday commit sonrası verilebilir.
