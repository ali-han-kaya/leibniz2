# GitHub Publish Senaryosu — Stoic-Hume V5

Bu senaryo, `_calisma/CIKTI/` ve kök config'leri (workflow, pre-commit, README) içeren
**yerel repo'yu** GitHub'a taşır ve CI'ı çalıştırır. Repo canlı olduğundan
(AŞAMA 1-2 UYGULANDI) ana akış **incremental push** döngüsüdür; aşağıdaki
aşamalar hem ilk kurulumun kaydı hem de günlük akışın parçasıdır.

> **Ana prensip:** `git push` zaten istenmeden yapılmaz. Her aşama, bir
> sonrakine geçmeden önce bilinçli onay gerektirir.
>
> **DURUM (2026-08-19):** repo **canlı** — https://github.com/ali-han-kaya/leibniz2
> (PUBLIC, default `main`). AŞAMA 1-2 **UYGULANDI**; kalan akış **incremental
> push** odaklıdır:
>
> | Aşama | Durum |
> |---|---|
> | AŞAMA 0 — ön-kontrol | ✅ araç hazır — her push öncesi koşulur |
> | AŞAMA 1 (a) — repo oluşturma | ✅ **UYGULANDI** (2026-08-18, `gh repo create leibniz2 --public`) |
> | AŞAMA 1 (b) — branch protection | ✅ **UYGULANDI** — GH API ile 8 required check, `enforce_admins=true`, `allow_force_pushes=false` |
> | AŞAMA 2 — remote + ilk push | ✅ **UYGULANDI** (2026-08-18) |
> | AŞAMA 3 — CI doğrulama | 🔄 **aktif** — her push'ta tekrarlanır (incremental) |
> | AŞAMA 4 — koruma kanıtı | ⏸️ opsiyonel (1 (b) sonrası) |
>
> Job tablosu (AŞAMA 3), `.github/workflows/verify.yml`'deki **14 job**'u 3 kategoride
> sunar: push'ta çalışan 8 **required** + 2 **advisory** + 3 **PR-only**.
> Branch protection yalnızca required job'ları bloke eder.
> Güncel listeyi üret: `python3 _calisma/CIKTI/status_checks.py --json`.

---

## Değişiklik Geçmişi (changelog)

> Her satır, ilgili commit ile denetlenebilir (`git show <commit>`).

| Tarih | Bölüm | Değişiklik | Commit |
|---|---|---|---|
| 2026-08-17 | (ilk oluşturma) | 4 aşamalı publish runbook + rollback bölümü | `a3544d8` |
| 2026-08-17 | Rollback | test-marker squash kaydı eklendi | `0fab281` |
| 2026-08-17 | AŞAMA 1 (b) | Branch protection: gh api yerine hazır web UI tarayıcı linki | `0a8afd8` |
| 2026-08-18 | AŞAMA 0 | commit-msg kuralı + history temizliği referansı (`HISTORY_CLEANUP.md`) | `b44b802` |
| 2026-08-18 | AŞAMA 3 / ÖZET | CI bölümleri güncel pipeline'a göre yenilendi (job tablosu, artifact listesi) | `0eedef1` |
| 2026-08-18 | AŞAMA 0 | Ön-kontrol tek komutluk `publish_precheck.sh`'e taşındı | `511fb22` |
| 2026-08-18 | AŞAMA 1/4, ÖZET | Kalan bayat kısımlar düzeltildi | `686671f` |
| 2026-08-18 | AŞAMA 1 | Status check adları workflow'dan türeyen `status_checks.py` eklendi (tek kaynak) | `b4f0f6c` |
| 2026-08-18 | TEK KOMUT | Wrapper'a `--dry-run` önizleme modu eklendi | `748bdea` |
| 2026-08-18 | TEK KOMUT | Wrapper kullanım bölümü + doc-script senkronu | `58fc563` |
| 2026-08-18 | AŞAMA 1 (b) | Branch protection — adım adım web UI yönergesi eklendi | `7cfa262` |
| 2026-08-18 | (tümü) | Gerçek repo URL'si + canlı job adlarıyla güncellendi ("Durum" notu) | `80334d0` |
| 2026-08-19 | AŞAMA 0 | Yerel pre-commit tam-yeşil notu eklendi | `8067da5` |
| 2026-08-19 | AŞAMA 0.5 | `ci_repack_test.sh` fresh-clone repack simülasyonu eklendi | `3d18ad0` |
| 2026-08-19 | AŞAMA 1 | Pre-commit etiketleri P0+P1 (`precommit-p0`/`precommit-p1`) olarak güncellendi | `3b87f5b` |
| 2026-08-19 | AŞAMA 1 | Budget + pre-commit PR durumu tek yorumda birleşti (notlar güncellendi) | `5935162` |
| 2026-08-19 | AŞAMA 1 | `Pre-commit P0 label gate` 8. required check olarak eklendi; check listesi 8'e çıktı | `feaa3dd` |
| 2026-08-19 | AŞAMA 0 (a2) | Tek komut `setup_commit_hooks.sh` kurulum referansı eklendi | `e6cbdca` |
| 2026-08-19 | AŞAMA 0/2 | Mutlak yollar `~/Desktop/leibniz2` yapıldı (taşınabilirlik) | `5d53ccc` |
| 2026-08-19 | AŞAMA 3 / yeni job | `Publish precheck (AŞAMA 0, advisory)` job'ı eklendi — her push'ta AŞAMA 0 kapıları otomatik denetlenir; job tablosu 10, artifact listesi 12 | `e373dd6` |
| 2026-08-19 | TEK KOMUT | publish_wrapper AŞAMA 0-3 idempotent yapıldı (repo zaten yayındaysa no-op re-run) | `6abf365` |
| 2026-08-19 | AŞAMA 1 | publish_wrapper'a status_checks.py otomatik doğrulaması bağlandı (repo oluşturma sonrası) | `5f614cf` |
| 2026-08-19 | TEK KOMUT | publish_wrapper'a `--dry-run-summary` bayrağı eklendi (komut akışını tek markdown'da özetler) | `c21b8e9` |
| 2026-08-20 | AŞAMA 3 | K12 (plist) katman listesine eklendi; job tablosu 12'ye, artifact listesi 19'a güncellendi (plist-check job + unit-tests/plist-check artifact'ları) | (çalışma ağacı — commit yok) |
| 2026-08-20 | AŞAMA 3 | Job tablosu `scriptPath` referanslarıyla senkronlandı: 5 github-script bloğu `github_scripts/*.js`'e çıkarıldı (pr_status_comment/label_gate/manifest_comment/config_diff_comment/config_drift_comment), inline `script:` yok; label-gate'e checkout eklendi; drift kapısı `test_github_scripts.py` (5 test) | (çalışma ağacı — commit yok) |
| 2026-08-20 | AŞAMA 1/3 | `Pre-commit P1 label gate (optional)` eklendi: `label_gate_p1.js` + `label-gate-p1` job'u + `test_label_gate_contracts.py` (19 test, CI advisory); required check listesi 9→10; job tablosu 13 | (çalışma ağacı — commit yok) |
| 2026-08-19 | (tümü) | Repo canlı duruma göre yeniden yazıldı: AŞAMA 1-2 `UYGULANDI` işaretlendi, ana akış `INCREMENTAL PUSH` günlük döngüsü oldu (AŞAMA 1 (b) BEKLEMEDE) | `e708e45` |
| 2026-08-19 | AŞAMA 1/3 | Node 24 yükseltmesi işlendi: `action-runtimes` job'ı + `check-action-pins` pre-commit kapısı (job 11, required check 9, pre-commit 6) | `1f84ba4` |
| 2026-08-21 | AŞAMA 3 | commit-msg blokaj kanıtı: `gen_commit_msg_evidence.py` (28 test senaryosu) + `COMMIT_MSG_BLOCK_EVIDENCE.md` CI'da periyodik üretilir; `setup_commit_hooks.sh --check-only` CI advisory adımı eklendi | (çalışma ağacı — commit yok) |
| 2026-08-21 | AŞAMA 3 | label sync/validate Octokit düzeltmesi: `listLabels` → `listLabelsForRepo` (selftest mock + battery expectations güncellendi) | `309a14f` |
| 2026-08-21 | AŞAMA 3 | simulate_verify_job.sh: GITHUB_STEP_SUMMARY + env-snapshot validation + iki aşamalı summary (dashboard-only → skip-dashboard) | `2282925` |
| 2026-08-21 | AŞAMA 3 | shellcheck lint: `shellcheck_hooks.sh` (sh: verify_lean + commit_msg; bash: update_config) + `lint_actionlint.sh` (RC≤2 advisory) + pre-commit + CI adımı | `ae55009` |
| 2026-08-21 | AŞAMA 1 (b) | Branch protection GH API ile kuruldu: 8 required check, `enforce_admins=true`, `strict=false`, `allow_force_pushes=false` | `dc9ab4f` |
| 2026-08-21 | AŞAMA 1 (b) | Job tablosu 3 kategoride yeniden yapılandırıldı: push-required (8), push-advisory (2), PR-only (4); status_checks.py `GATE_EXCLUDE` güncellendi | `df92ada` |
| 2026-08-21 | AŞAMA 3 | `status_checks.py --gh` fail-closed: protection kurulu değilken exit 1 | `df92ada` |
| 2026-08-21 | docs | add repo-level changelog + regression notes to README | `b07f5f4` |
| 2026-08-21 | feat | (ci) add precheck-report to reproducibility manifest | `694b367` |
| 2026-08-21 | docs | add §8 publish wrapper idempotency verification | `5d9b6c6` |
| 2026-08-21 | fix | (ci) remove local keyword outside function | `965182d` |
| 2026-08-21 | fix | (ci) use local var in ci-simulate OWNER | `994d359` |
| 2026-08-21 | feat | (ci) ci-simulate mode + doc integrity audit | `a309b23` |
| 2026-08-21 | docs | add §7 to PRE_PUSH_DENETIM_RAPORU + skip report from path check | `4e58931` |
| 2026-08-21 | docs | fix stale job/check counts in PUBLISH_SCENARIO (13→14, 10→8) | `8878847` |
| 2026-08-21 | feat | add check-absolute-paths pre-commit hook | `8116715` |
| 2026-08-21 | docs | clarify 8 required checks vs push-running jobs in PUBLISH_SCENARIO | `b393ddf` |
| 2026-08-21 | feat | (ci) git log'dan otomatik changelog üret (gen_changelog.py) | `4286b4a` |
| 2026-08-21 | fix | (ci) changelog hook'u auto-sync yap (update-config deseni) | `5d5daf2` |
| 2026-08-21 | feat | (publish) --verify-checks bağımsız AŞAMA 1 doğrulama modu | `e15d0f4` |
| 2026-08-21 | docs | §9 oturum 3 denetim kaydı | `c6a221c` |
| 2026-08-21 | feat | (ci) --dry-run-summary regresyon kapısı (test_dryrun_summary.py) | `b5327e5` |
| 2026-08-21 | refs | V5n satırını refs-trend changelog'una işle (54→56) | `4216895` |
| 2026-08-21 | refs | Della Rocca 2010'ı Handle System API ile doğrula (V5t) | `a124e66` |
| 2026-08-21 | feat | (ci) K17 mirror sync kapısı (sync_verify_mirror.sh --check) | `7c3ab53` |
| 2026-08-21 | feat | (preview) update_preview.sh --bootstrap tek adım modu | `169a6c8` |
| 2026-08-21 | feat | fresh_clone_setup.sh — tek komutta TCC-safe ortam kurulumu | `ee772b6` |
| 2026-08-21 | feat | fresh_clone_setup.sh — tek komutta TCC-safe ortam kurulumu | `a09f1a2` |
| 2026-08-21 | fix | (ci) mirror'a eksik github_scripts'i ekle (K16 launchd rotası) | `e1abea6` |
| 2026-08-21 | feat | (ci) daemon-modu HTTP 200 testini advisory job olarak ekle | `be60442` |

---

## Regresyon Notları — Son 3 CI Kırılması (2026-08-21)

> Bu bölüm, 2026-08-19/21 döneminde yaşanan ve CI'ıRED'e düşüren 3 kök-nedenli kırılmayı,
> nedenlerini ve kalıcı düzeltmelerini belgeler.

### R1: Yapışık YAML Adımı (`d57a60c`, 2026-08-19)

**Belirti:** CI run'ları 0 saniyede `success` dönüyordu amahiçbir job çalışmıyordu
(0 job); GitHub Actions UI'ında run boş görünüyordu.

**Kök neden:** `verify.yml` bütçe job'undaki "PR status" script'inin kapanış `}` karakteri ile
sonraki "Upload budget bundle" adımının `uses:`/`if:` anahtarı aynı satıra yapışmıştı.
Bu, YAML parser'ın script bloğunu sonraki adıma gömmesine yol açıyordu —
ıki uses:/if: aynı step'e düşüyordu ve workflow ayrıştırılamıyordu.

**Düzeltme:** Satır ayrımı + `yamllint`/`actionlint` ile doğrulama.

**Önleme:** `actionlint` pre-commit kapısı + CI advisory adımında her push'ta
YAML syntax doğrulanıyor; yapışık satır ≥2-Level hata olarak yakalanıyor.

### R2: Env-Snapshot Boşlu (`2282925`, 2026-08-21)

**Belirti:** `simulate_verify_job.sh` yerelde koşulduğunda, `consolidate_summary.py`
`GITHUB_STEP_SUMMARY` env'i set olmadığı için stdout'a yazıyordu —
write hatası,encoding sorunu veya boş summary yerelde yakalanmıyordu.

**Kök neden:** CI'da GitHub runner `GITHUB_STEP_SUMMARY` dosyasınıotomatik oluşturur;
yerel simülasyonda ise env boştu ve `summary_sink()` stdout'a düşüyordu.

**Düzeltme:** `simulate_verify_job.sh`'e 3 yeni adım eklendi:
1. `step_dashboard_header` — `GITHUB_STEP_SUMMARY="$SIM_DIR/summary.md"` + `--dashboard-only`
2. `step_consolidate_summary` — `--skip-dashboard` (CI ile aynı iki aşamalı akış)
3. `step_validate_summary` — dosya oluştu mu? boş mu? dashboard var mı? section sayısı?

**Önleme:** Env-snapshot validation artık yerelde de fail-closed çalışıyor;
boş/eksik summaryhatası simulate'da yakalanıyor.

### R3: Dash/Bash Lint Çelişkisi (`ae55009`, 2026-08-21)

**Belirti:** `actionlint` pre-commit hook'u, workflow YAML shell scriptlerindeki
SC2086/SC2012 info-level shellcheck uyarılarını hata olarak dönüyordu
(RC=1); pre-commit bu yüzden `Failed` veriyor, commit bloke oluyordu.

**Kök neden:** actionlint, yerleşik shellcheck'i ile workflow YAML'daki `run:` bloklarını
denetliyor ve info-level uyarılar için bile exit 1 dönüyordu.
Pre-commit hook'u bu exit kodunu olduğu gibi passOrFail olarak yorumluyordu.

**Düzeltme (3 katman):**
1. `lint_actionlint.sh` — standalone wrapper; RC≤2'yi PASS olarak kabul ediyor
   (RC=0: temiz, RC=1-2: shellcheck info/hint — advisory, RC>2: hata — FAIL)
2. `shellcheck_hooks.sh` — sh entry'li hook betiklerini (verify_lean.sh,
   commit_msg_hook.sh) POSIX shellcheck ile denetliyor; update_config_hook.sh'yi
   bash modunda denetliyor
3. `commit_msg_hook.sh` — SC2221/SC2222 disable directive eklendi
   (glob escape `\\` false-positive: `test:*` ≠ `fix\\ typo*`)

**Önleme:** Pre-commit'te 13/13 hook yeşil; actionlintinfo-level uyarıları advisory
olarak kabul ediliyor; sh hook betikleri POSIX uyumluluğu açısındanPeriyodik olarak denetleniyor.

### Ek: Octokit API Yanlış Adı (`309a14f`, 2026-08-21)

**Belirti:** CI annotation'larında `github.rest.issues.listLabels is not a function` hatası;
validate_labels.js ve sync_labels.js CI'da `TypeError` fırlatıyordu.

**Kök neden:** Octokit'te `issues.listLabels` yok — doğru的是 `issues.listLabelsForRepo`.
Selftest mock'u da eski adı kullanıyordu.

**Düzeltme:** 4 dosya güncellendi (validate_labels.js, sync_labels.js,
github_scripts_selftest.js, github_scripts_battery.py).


## TEK KOMUT — publish_wrapper.sh (tüm senaryo)

Aşağıdaki manuel aşamaların **birebir aynısını tek komutla, interaktif olmadan**
çalıştıran wrapper: [`docs/publish_wrapper.sh`](publish_wrapper.sh).

| Kullanım | Davranış |
|---|---|
| `bash docs/publish_wrapper.sh` | AŞAMA 0-3: precheck → repo oluştur → remote+push → CI izle (5-15 dk) |
| `bash docs/publish_wrapper.sh --with-stage4` | AŞAMA 0-4 (opsiyonel koruma testi dahil) |
| `bash docs/publish_wrapper.sh --dry-run` | **Prova:** hiçbir komut çalışmaz; her kalıcı komut `[DRY-RUN] çalıştırılacak: ...` olarak önizlenir (exit 0) |
| `bash docs/publish_wrapper.sh --dry-run --with-stage4` | AŞAMA 0-4'ün tam önizlemesi |
| `bash docs/publish_wrapper.sh --dry-run-summary` | **Prova + özet:** dry-run komut akışını tek markdown dosyasına yazar (`logs/PUBLISH_DRY_RUN_SUMMARY.md`) |
| `bash docs/publish_wrapper.sh --verify-checks` | **Yalnızca AŞAMA 1 doğrulaması:** `status_checks.py` + `--gh` (workflow ↔ GitHub eşleşmesi + merge engeli smoke). Repo oluşturma/push/CI izleme ÇALIŞMAZ; temiz tree gerektirmez (salt okunur) — `--dry-run` ile birleşince önizleme modunda koşar |
| `bash docs/publish_wrapper.sh` (repo zaten yayında) | **İdempotent:** repo/remote varsa atlanır; bekleyen commit yoksa push atlanır; HEAD için mevcut CI run'ı izlenir |

- **Log:** `logs/publish_<timestamp>.log` — hem terminale hem dosyaya yazılır.
- AŞAMA 0 kapıları (`publish_precheck.sh`) yeşil değilse DURUR; `git push`
  yalnızca tüm kapılar geçerse çalışır (fail-closed).
- Branch protection **web UI'dan manuel** kalır (şeffaflık) — wrapper yalnızca
  linki + `status_checks.py` adımlarını loglar.
- **Senkron:** wrapper, bu belgedeki manuel komutları birebir uygular (repo
  create bayrakları, marker yolu vb. aynıdır); fark oluşursa bu belgeyi ve
  wrapper'ı birlikte güncelle.

---

## INCREMENTAL PUSH — günlük döngü (repo canlı, 4 komut)

Repo yayında olduğundan **ana akış budur**: her değişiklik → kapılar → push → CI.

```bash
cd ~/Desktop/leibniz2

# 1) AŞAMA 0 kapıları (fail-closed: herhangi bir FAIL push'u durdurur)
bash docs/publish_precheck.sh --allow-remote

# 2) Push (kapılar yeşilse)
git push origin main

# 3) CI'ı izle (14 job — K1-K14 + action-runtimes + budget + plist-check + label-gate-p1 + ...)
RUN_ID=$(gh run list --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch $RUN_ID --exit-status

# 4) Son durum + artifact'lar (19 adet beklenir)
gh run view $RUN_ID --json jobs --jq '.jobs[] | "\(.name)\t\(.conclusion)"'
gh api "repos/ali-han-kaya/leibniz2/actions/runs/$RUN_ID/artifacts" \
  --jq '.artifacts[].name' | sort
```

> **Tek komut karşılığı:** `bash docs/publish_wrapper.sh` — repo zaten yayında
> olduğundan **idempotent**: precheck → push → CI izle; repo/remote adımları
> atlanır. Önce `--dry-run` ile önizle.
>
> **AŞAMA 1 (b) tamamlandıysa** 4. adıma ek olarak:
> `python3 _calisma/CIKTI/status_checks.py --gh` → `SONUÇ: PASS` (8 check +
> merge engeli smoke) — koruma/check eşleşmesini canlı doğrular.

Her adımın ayrıntısı aşağıdaki AŞAMA bölümlerindedir; bu döngü onların günlük
kullanım karşılığıdır.

---

## AŞAMA 0 — Ön-kontrol (güvenli, otomatik)

> **Tek komut (otomatik):** aşağıdaki tüm kontrollerin birebir aynısı
> [`docs/publish_precheck.sh`](publish_precheck.sh) ile koşar — her kontrol
> `[PASS]/[FAIL]` raporlanır, herhangi bir FAIL exit 1 (fail-closed):
> ```bash
> bash docs/publish_precheck.sh                 # ilk publish (remote boş beklenir)
> bash docs/publish_precheck.sh --allow-remote  # repo zaten GitHub'da (incremental)
> bash docs/publish_precheck.sh --skip-smoke    # smoke testini atla (commit yok)
> ```
> `publish_wrapper.sh` AŞAMA 0'da bu scripti çağırır — manuel adımlar yalnızca
> referans/denetim içindir. Tam akışı **risksiz** önizlemek için:
> ```bash
> bash docs/publish_wrapper.sh --dry-run                # AŞAMA 0-3 önizle
> bash docs/publish_wrapper.sh --dry-run --with-stage4  # AŞAMA 0-4 önizle
> ```
> Dry-run'da hiçbir komut çalışmaz: repo oluşturma/push/PR yalnızca
> `[DRY-RUN] çalıştırılacak: ...` olarak basılır (log: `logs/publish_*.log`).

```bash
cd ~/Desktop/leibniz2

# (a) Repo temiz mi?
git status --short         # ← boş olmalı
git log --oneline -5       # ← temiz linear history; test-marker commit'i olmamalı

# (a2) Commit mesaj kuralı kurulu mu? (bkz. docs/HISTORY_CLEANUP.md)
#      Kurulu değilse TEK komutla kur: bash _calisma/CIKTI/setup_commit_hooks.sh
git config commit.template      # ← ".gitmessage" olmalı
ls .git/hooks/commit-msg        # ← var olmalı (pre-commit install --hook-type commit-msg)
#      Kanıt: COMMIT_MSG_BLOCK_EVIDENCE.md — 28 test senaryosuyla hook'un
#      hangi başlıkları bloke ettiği/izni belgelenmiş (CI'da periyodik üretilir).

# (b) Pre-commit hooks çalışıyor mu? (commit-msg kuralına uygun mesaj —
#     "smoke:" başlığı artık commit-msg-style hook'u tarafından REDDEDİLİR)
git commit --allow-empty -m "docs: pre-commit smoke test" 2>&1 | grep -E "Passed|Failed"
git reset --hard HEAD^     # smoke commit'i geri al (branch ilerletme)

# (c) gh CLI kurulu mu ve auth var mı?
gh --version
gh auth status             # ← "Logged in to github.com as ali-han-kaya" görmeli

# (d) Push'lanacak branch + remote yokluğu:
git remote -v              # ← boş olmalı (henüz remote yok)
git branch --show-current  # ← "main" olmalı
```

**Beklenen çıktılar:**
- `git status` → boş
- pre-commit smoke test → **6/6 Passed (tamamen yeşil)** — update-config + verify-delivery
  (K1-K7) + check-action-pins (action major pinleme) +
  verify-delivery-symbolic (K8/Z3, z3-solver izole ortamda) +
  verify-delivery-lean (K9) `--all-files` içinde; commit-msg-style ayrı stage
  (`--hook-stage commit-msg` ile doğrulanır). ✅ Yerel pre-commit artık `--no-verify`
  olmadan tam yeşil — AŞAMA 1'e geçmeden bu doğrulandı.
- `gh auth status` → "Logged in"
- `git remote -v` → boş

⚠️ **Eğer bunlardan biri yanlışsa DURUR — AŞAMA 1'e geçme.**

---

## AŞAMA 0.5 — Yerel repack fresh-clone testi (tek komut, opsiyonel ama önerilir)

Push'tan önce `repack-verify` job'unun fresh-clone simülasyonunu yerelde koş
(`ci_repack_test.sh` — çalışma ağacını KİRLETMEZ, tüm adımlar geçici bir
worktree'de koşar):

```bash
bash _calisma/CIKTI/ci_repack_test.sh                  # PASS/FAIL özetler (exit 0/1)
KEEP_WORKTREE=1 bash _calisma/CIKTI/ci_repack_test.sh  # geçici worktree'yi sakla
```

**Ne kanıtlar (CI `repack-verify` job'uyla birebir):**
1. HEAD'in izole worktree kopyası (`git worktree add --detach HEAD` — CI checkout karşılığı)
2. `repack_delivery.py --verify` — deterministik repack + sidecar bütünlüğü
3. byte-identical kapısı — `git diff --exit-code` boş (commit'li ↔ repack çıktısı)
4. önce/sonra SHA-256 kanıtı — 2/2 zip identical (tam hash, kısaltılmamış)
5. base verify K1-K7 — `SONUÇ: PASS (P0=0, P1=0)`

Çıktılar gitignored `.freebuff/sim/repack_verify/` altına yazılır
(`repack_verify_report.txt` + `byte_identical_proof.md`).

---

## AŞAMA 1 — GitHub'da repo oluştur (`gh` ile, interaktif değil)

> **Durum:** (a) ✅ **UYGULANDI** (2026-08-18) — repo canlı; komutlar yalnızca
> kayıt/tarihçe içindir. (b) ⏳ **BEKLEMEDE** — branch protection henüz
> kurulmadı; kalan tek kurulum adımı (aşağıda adım adım + görsel kılavuz).

```bash
# (a) ✅ UYGULANDI — kişisel hesabın altında boş repo oluştur (kayıt amaçlı)
gh repo create leibniz2 \
    --description "Stoic-Hume V5 — fail-closed academic delivery with Z3 + Lean 4 proofs" \
    --public \
    --disable-issues=false \
    --disable-wiki=true \
    --disable-projects=true \
    --add-readme=false     # bizim README'miz commit'lenecek; çakışmasın

# Wrapper (publish_wrapper.sh) kullanılıyorsa burada OTOMATİK doğrulama koşar:
#   python3 _calisma/CIKTI/status_checks.py      # 9 ad workflow'dan türetilir
#   python3 _calisma/CIKTI/status_checks.py --gh # GitHub eşleşmesi (koruma yoksa UYARI,
#                                                # gerçek drift varsa FAIL — fail-closed)

# (b) ⏳ BEKLEMEDE — Branch koruması — GitHub web UI (gh api yerine; manuel + şeffaf)
#     Hazır tarayıcı linki (kopyala-yapıştır):
#       https://github.com/ali-han-kaya/leibniz2/settings/branches
#
#     macOS'ta doğrudan açmak için:
open "https://github.com/ali-han-kaya/leibniz2/settings/branches"
#
#     Web UI'da (adım adım → aşağıdaki "Branch protection — web UI adım adım"):
#       "Add branch protection rule" → Branch name pattern: `main`
#       ✓ Require status checks to pass before merging
#         → 8 check (adlar = workflow job `name:` alanları — tek kaynaktan al):
#             python3 _calisma/CIKTI/status_checks.py
#           Delivery verification — K1-K9 (single entry point)
#           Action runtime check (node24)
#           Budget shield (aggregated)
#           Static markdown reports (incl. pre-commit findings)
#           Reproducibility bundle
#           Config drift check (gen_config + diff-on-drift)
#           Repack determinism + verify (sidecar sync)
#           Online verification trend (refs-online across runs)
#         (PR-only job'lar: label-gate, label-gate-p1, commit-msg-gate, manifest-comment
#          — push'ta çalışmaz, required check DEĞİL)
#           → ✓ "Require branches to be up to date before merging" (strict)
#       ✓ Do not allow bypassing the above settings   (enforce_admins)
#       ✓ Disallow force pushes
#       ✓ Disallow deletions
```

### Branch protection — web UI adım adım (8 required check)

> 📷 **Görsel kılavuz:** her adımın ekran görüntüsü
> [`docs/branch-protection-guide/`](branch-protection-guide/) altında (8
> ekran, kırmızı numaralı rozetlerle işaretli). Aşağıdaki adımlar o
> kılavuzdaki ekranlarla birebir eşleşir.

> Kural yalnızca `main` içindir. Check adları TEK KAYNAKTAN (workflow job
> `name:` alanları) gelir — güncel listeyi üret:
> `python3 _calisma/CIKTI/status_checks.py`

1. **GitHub web'e gir** — tarayıcıda:
   `https://github.com/ali-han-kaya/leibniz2/settings/branches`
   (Repo sayfasında **Settings → Branches** — sol menüde "Code and automation" altında.)

2. **Yeni kural başlat** — sağ üstte **"Add branch protection rule"** (veya **"Add rule"**).

3. **Branch name pattern:** kutuya `main` yaz. **"All branches"** seçeneğini kullanma
   — kural yalnızca `main` için.

4. **PR şartı (önerilen):** **"Require a pull request before merging"** ✓ işaretle —
   main'e doğrudan push artık reddedilir. "Require approvals" için 1 bırak
   (tek kişilik repoda 0 da olur).

5. **Status checks (ANA kapı):** **"Require status checks to pass before merging"** ✓.
   Kutucuk genişleyince:
   - **Ön koşul:** check'lerin arama listesinde görünmesi için o branch'te CI'ın
     **en az bir kez koşmuş** olması gerekir. Yeni/boş repoda kural kuruyorsan önce
     bir push ya da PR ile workflow'u tetikle, yeşil run'ı bekle, sonra bu adıma dön.
   -   Arama kutusuna şu **8 adı** tek tek yazıp seç (birebir, `—` karakteri dahil):
     1. `Delivery verification — K1-K9 (single entry point)`
     2. `Action runtime check (node24)`
     3. `Budget shield (aggregated)`
     4. `Static markdown reports (incl. pre-commit findings)`
     5. `Reproducibility bundle`
     6. `Config drift check (gen_config + diff-on-drift)`
     7. `Repack determinism + verify (sidecar sync)`
     8. `Online verification trend (refs-online across runs)`
     > **Not:** PR-only job'lar (label-gate, label-gate-p1, commit-msg-gate) ve
     > advisory job'lar (precheck, plist-check) required check'ten hariç tutuldu —
     > push'ta çalışmadıkları için required yapılırsa main branch kilitlenir.
     > `manifest-comment` job'ı yalnızca PR'da koşar — required check DEĞİL; ekleme.
     > `Pre-commit P0 label gate` yalnızca PR'da koşar ama BİLEREK required
     > check'tir: precommit-p0 etiketi varken FAIL verip merge'i bloke eder
     > (aşağıdaki "P0 label gate" bölümüne bak).
     > `Pre-commit P1 label gate (optional)` aynı desende opsiyonel bir gatedir:
     > branch protection'a eklenirse P1 bulguları merge'i bloke eder; eklenmezse
     > sadece bilgilendirme rozeti olarak kalır.
   - **"Require branches to be up to date before merging"** ✓ (strict) — PR'ın base'i
     main'in gerisindeyse merge reddedilir.

6. **Enforce admins:** **"Do not allow bypassing the above settings"** ✓ — adminler de
   kapıya takılır.

7. **Güvenlik:** **"Disallow force pushes"** ✓ ve **"Disallow deletions"** ✓ (Allow
   seçenekleri kapalı kalmalı).

8. **Kaydet:** **"Create"** (kural zaten varsa **"Save changes"**).

9. **Doğrula (otomatik):** koruma kurulduktan sonra:
   ```bash
   python3 _calisma/CIKTI/status_checks.py --gh
   # SONUÇ: PASS — 8 check birebir eşleşiyor (workflow ↔ GitHub)
   ```
   Eksik/fazla check → exit 1 (fail-closed): listeyi `status_checks.py` çıktısıyla
   eşitle veya workflow'u güncelle.

**Beklenen çıktılar:**
- (a) ✅ UYGULANDI — `gh repo create` → "Created repository ali-han-kaya/leibniz2" (2026-08-18)
- (b) ⏳ BEKLEMEDE — Tarayıcıda Settings → Branches → `main` için kural eklendi (koruma aktif)

**Görsel doğrulama:** https://github.com/ali-han-kaya/leibniz2 — repo yayında
(README render edilmiş, Actions sekmesinde run'lar, `.github/workflows/verify.yml`
görünür).

Koruma kurulduktan sonra doğrulama → yukarıdaki adım 9 (veya AŞAMA 0'ı
`--allow-remote` ile tekrar çalıştır — (e) adımı aynı eşleşmeyi VE
merge engelini (strict/enforce_admins/force-push/deletions smoke) denetler).

### P0 label gate — precommit-p0 etiketini merge kapısına bağla

> **GitHub'da yerleşik "required labels" YOKTUR.** Branch protection settings
> listesi yalnızca status checks / reviews / conversation resolution / signed
> commits / linear history / merge queue / deployments içerir (kaynak:
> docs.github.com "About protected branches"). Bu yüzden etiketi kapıya
> bağlamanın desteklenen yolu, etiket VARSA FAIL veren bir **required status
> check**'tir — yukarıdaki 3. adımdaki `Pre-commit P0 label gate`.

**Nasıl çalışır (uçtan uca):**
1. `verify` job'u pre-commit bulgularını `PRECOMMIT_RAPORU.json`'a yazar.
2. `budget` job'ının "PR status" adımı P0 varsa PR'a `precommit-p0` etiketini
   ekler, yoksa kaldırır (etiket her zaman PR'nin güncel durumunu yansıtır).
3. `label-gate` job'ı (`needs: [budget]`) PR'ın **canlı** etiketini REST ile
   okur: `precommit-p0` varsa `core.setFailed` → check FAIL.
4. Bu check branch protection'da required olduğundan, etiket kalkana dek
   (P0 giderilene dek) merge butonu bloke kalır.

**Neden `needs: [budget]` ve REST okuma:** etiket aynı run içinde budget
adımında güncellenir; `context.payload.pull_request.labels` event başındaki
ESKİ anlık görüntüdür. Bu yüzden kapı etiketi REST ile canlı okur — bayat
etikete göre yanlış geçmez/bloke etmez.

**Doğrula (yerel, git gerektirmez):**
```bash
python3 _calisma/CIKTI/status_checks.py
# → listede "Pre-commit P0 label gate" ve "Pre-commit P1 label gate (optional)"
#   (toplam 8 check)
```

**Davranış tablosu (P0 — zorunlu):**

| PR'da `precommit-p0` | label-gate sonucu | Merge |
|---|---|---|
| Yok | ✅ PASS | izinli |
| Var | ❌ FAIL | bloke (P0 giderilene dek) |

**Davranış tablosu (P1 — opsiyonel):**

| PR'da `precommit-p1` | label-gate-p1 sonucu | Merge |
|---|---|---|
| Yok | ✅ PASS | izinli |
| Var | ❌ FAIL | branch protection'a ekliyse bloke, ekli değilse izinli |

> P0 ve P1 gate'leri aynı deseni kullanır: `budget` job'u etiketi PR'a ekler/
> kaldırır, `label-gate`/`label-gate-p1` job'u `needs: [budget]` ile canlı
> REST okumasıyla doğrular. P0 her zaman required; P1 opsiyoneldir —
> branch protection'a eklenirse merge'i bloke eder.

---

## AŞAMA 2 — Remote ekle + push (geri dönüşü olan adım)

> **Durum:** ✅ **UYGULANDI** (2026-08-18) — `origin` ekli, ilk push yapıldı.
> Komutlar yalnızca kayıt/tarihçe içindir; günlük push = `git push origin main`
> (yukarıdaki INCREMENTAL PUSH bölümü). Bu akışı tekrarlama.

```bash
cd ~/Desktop/leibniz2

# (a) ✅ UYGULANDI — Remote ekle (token değil — SSH veya gh'nin auth'u yeterli)
gh repo set-default leibniz2  # (opsiyonel; repo'yu default yapar)
git remote add origin git@github.com:$(gh repo view --json owner -q '.owner.login')/leibniz2.git

# Doğrula:
git remote -v
# origin  git@github.com:ali-han-kaya/leibniz2.git (fetch)
# origin  git@github.com:ali-han-kaya/leibniz2.git (push)

# (b) İlk push — main branch + upstream set
git push -u origin main
```

**Beklenen çıktı:**
```
Enumerating objects: N, done.
Counting objects: 100% (N/N), done.
...
To github.com:ali-han-kaya/leibniz2.git
 * [new branch]      main -> main
Branch 'main' set up to track remote 'origin/main'.
```

**Süre:** ~5-15 sn (küçük repo, 73 dosya, ~10 MiB).

**Görsel doğrulama:** https://github.com/ali-han-kaya/leibniz2 adresinde:
- Temiz linear history (56 commit; test-marker `d863977`/`991473d` rebase ile
  ezildi — tam kayıt: [`docs/HISTORY_CLEANUP.md`](HISTORY_CLEANUP.md))
- README.md render edilmiş
- `.github/workflows/verify.yml` görünür

---

## AŞAMA 3 — CI doğrulama (her push'ta — incremental)

> **Durum:** 🔄 **aktif** — her push'ta tekrarlanır. Bu bölüm, INCREMENTAL
> PUSH döngüsündeki 3-4. adımların detayıdır (job tablosu + artifact listesi).

```bash
# (a) Push'u tetikleyen run'ı bul (push zaten run başlatır; kontrol için bekle)
gh run list --limit 3 --json databaseId,status,conclusion,name
# Tüm run'lar "in_progress" veya "completed" olmalı

# (b) Belirli run'ın loglarını izle (tail modunda)
RUN_ID=$(gh run list --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch $RUN_ID --exit-status

# (c) Artifact'ları kontrol et (19 adet olmalı — liste aşağıda)
gh run view $RUN_ID --json artifacts --jq '.artifacts[] | "\(.name) (\(.size_in_bytes) B)"'
```

**Wrapper:** bu aşamayı `publish_wrapper.sh` otomatik yapar — `gh run watch
--exit-status` + artifact listesi; sonuç `SONUÇ: PASS/FAIL` olarak loglanır
(dry-run'da yalnızca önizlenir).

**Job kategorileri (14 job = 8 required + 2 advisory + 3 PR-only + 1 manifest):**

> **Kural:** Branch protection **yalnızca A kategorisindeki** job'ları required check olarak
> kabul eder. B (advisory) job'ları push'ta çalışır ama required değildir;
> C (PR-only) job'ları push'ta hiç çalışmaz.

| # | Kategori | Job | Beklenen sonuç |
|---|---|---|---|
| | **A — Required (push'ta çalışır, merge bloke)** | | |
| 1 | A | Delivery verification — K1-K9 (single entry point) | ✅ K0-K7 + K8 (Z3 12/12) + K9 (Lean) + K11 + K13 + K14 tek komutta (`--full`); pre-commit advisory bölüm |
| 2 | A | Action runtime check (node24) | ✅ her `uses:` action'ın `runs.using=node24` olduğu doğrulanır |
| 3 | A | Budget shield (aggregated) | ✅ limit içinde (sidecar birleştirildi); PR'da tek yorum |
| 4 | A | Static markdown reports (incl. pre-commit findings) | ✅ bundle yüklendi |
| 5 | A | Reproducibility bundle | ✅ manifest.txt + SHA-256 — K10 `--verify-manifest` + `manifest.sha256` |
| 6 | A | Config drift check (gen_config + diff-on-drift) | ✅ config uyumlu; drift PR yorumu olarak düşer |
| 7 | A | Repack determinism + verify (sidecar sync) | ✅ repack byte-identical, base verify PASS |
| 8 | A | Online verification trend (refs-online across runs) | ✅ trend tablosu üretildi |
| | **B — Advisory (push'ta çalışır, required değil)** | | |
| 9 | B | Publish precheck (AŞAMA 0, advisory) | ✅ AŞAMA 0 kapıları otomatik denetlenir (`continue-on-error`) |
| 10 | B | Plist drift check (macOS, advisory) | ✅ K12 — macOS-runner'lı, `continue-on-error` |
| 11 | B | Mirror sync check (macOS, fail-closed) | ✅ K17 — sync sonrası `--check-mirror` GÜNCEL olmalı; drift/hata → job FAIL |
| | **C — PR-only (push'ta çalışmaz, PR'da çalışır)** | | |
| 12 | C | Pre-commit P0 label gate | ✅ precommit-p0 etiketi varsa FAIL (merge bloke) |
| 13 | C | Pre-commit P1 label gate (optional) | ✅ precommit-p1 etiketi varsa FAIL |
| 14 | C | Commit-msg gate | ✅ commit_msg_findings.json ihlal varsa FAIL |
| | **D — PR-only (yorum/etiket düşürme)** | | |
| 15 | D | Manifest PR comment | ✅ manifest.txt + config-diff PR yorumu |

**Artifact listesi (20):**
- `unit-tests` (CIKTI birim test logu — `test_*.py` glob'u)
- `verify-report` (tek log: K1-K14 + pre-commit bölümü + .sha256)
- `action-runtimes` (her action'ın runs.using denetimi JSON — node24 kapısı)
- `budget-verify` + `budget` (bütçe sidecar + aggregator)
- `config` (ham + şema + etkin config + diff)
- `k0-findings` (bayat-zip taraması JSON)
- `lineage-findings` (zip soy hattı doğrulaması JSON)
- `klayers` (K1-K14 PASS/FAIL/SKIP özeti — run summary)
- `refs-online` (çevrimiçi referans denetimi VERSION JSON)
- `run-history` (history.jsonl — run zaman serisi)
- `precommit-logs` (ham log + PRECOMMIT_RAPORU.md/.json + cache/env özeti)
- `reports` (statik markdown raporları)
- `reproducibility` (tüm artifact'ların SHA-256 manifest'i)
- `config-drift` (gen_config + diff-on-drift bulguları)
- `repack-verify` (repack sonrası base verify raporu)
- `refs-trend` (run'lar arası çevrimiçi referans zaman serisi)
- `precheck-report` (AŞAMA 0 ön-kontrol logu — advisory, her push'ta)
- `plist-check` (K12 raporu + --plist-check sidecar JSON — macOS advisory job)
- `mirror-check` (K17 raporu + --check-mirror sidecar JSON — macOS fail-closed job)

**Not:** Kapı artık `verify_delivery.py --full`'dur (K1-K14, fail-closed) ve yeşildir —
Beth 1953 / Fosl 1998 gibi referans düzeltmeleri V5h'te yapıldı; Kalan çevrimdışı
kaynaklar `refs-online`'da advisory olarak izlenir (kapıyı kırmaz). K12 (plist)
`--full`'a dahil değildir — macOS'a özgü olduğundan ayrı `plist-check` advisory
job'ında koşar (Linux runner'larında SKIP). Aynı şekilde K17 (mirror sync)
`--full`'a dahil değildir — ayrı `mirror-check` macOS job'ında fail-closed koşar
(sync sonrası GÜNCEL olmalı; repo ↔ mirror drift'i P1 → job FAIL).

---

## OPSİYONEL AŞAMA 4 — Branch protection'ın çalıştığını kanıtla (1 (b) sonrası)

```bash
# (a) Main'e doğrudan bir değişiklik push'la — branch protection REDDETMELI.
#     (commit-msg kuralına uygun mesaj; "test:"/"should be blocked..." başlıkları
#     commit-msg hook'u tarafından REDDEDİLİR — --no-verify ile baypas edilir,
#     çünkü bu test UZAK branch korumasını denetler, yerel kapıyı değil.)
git checkout -b test/protection-check
printf '# protection smoke\n' > _calisma/CIKTI/PROTECTION_SMOKE.md
git add _calisma/CIKTI/PROTECTION_SMOKE.md
git commit --no-verify -m "docs: protection smoke marker"
git push origin test/protection-check  # ← feature branch: geçer
# Şimdi main'e PR aç:
gh pr create --base main --head test/protection-check --title "docs: protection smoke"
# Merge denenir. CI artık YEŞİL olduğundan reddedilme nedeni "FAIL check" değil:
# required check'ler (9 kapı) TAMAMLANMADAN veya branch main'in gerisindeyken
# (strict) merge REDDEDİLMELİ.
gh pr merge --squash
git checkout main
git branch -D test/protection-check
gh pr close test/protection-check --comment "protection smoke sonlandı"
git push origin --delete test/protection-check

# (b) Kullanıcı olarak "Status checks required" görünür
gh repo view --web
# Settings → Branches → main → "Require status checks to pass before merging" ✅
```

**Wrapper:** `bash docs/publish_wrapper.sh --with-stage4` bu adımları aynen koşar
(marker dosyası, commit, push, PR, merge denemesi, temizlik) ve merge reddedilme
beklentisini exit koduyla raporlar.

---

## GERİ DÖNÜŞ (rollback)

Senaryonun herhangi bir noktasında durmak istersen:

```bash
# 1) Remote'u kaldır (henüz push etmediysen)
git remote remove origin

# 2) GitHub repo'yu sil (push ettiysen ama silmek istiyorsan)
gh repo delete leibniz2 --yes

# 3) Lokalde branch'leri sıfırla (test commit'leri kaldı)
git log --oneline -5
git reset --hard <commit-hash-where-you-want-to-be>
```

**Saklananlar:**
- `9f72b0e` (ana kurulum, gerçek) — **kal**
- `3d114e5` (ignore eklentisi, gerçek) — **kal**
- `5d62685` (budget shield + config + rapor, gerçek) — **kal**
- `d863977` + `991473d` (test markers) — **EZİLDİ**: `git rebase --onto 5d62685 991473d` ile net-sıfır diff temizlendi (add+remove aynı dosya olduğundan tek anlamlı sonuç silmekti). **Tam kayıt + önleme kuralları: [`docs/HISTORY_CLEANUP.md`](HISTORY_CLEANUP.md)**

---

## GITHUB'A ÖZGÜ YAPILANDIRMA

Repo ilk açıldıktan sonra önerilen ayarlar:

| Ayar | Değer | Neden |
|---|---|---|
| Default branch | `main` | zaten bu |
| Allow merge commits | ✅ | history temizliği için gerekmez |
| Allow squash merging | ✅ | PR'leri squash etmek için |
| Allow rebase merging | ✅ | linear history için |
| Always suggest updating branch | ✅ | PR'leri güncel tut |
| Allow auto-merge | ✅ | yeşil CI sonrası otomatik |
| Automatically delete head branches | ✅ | merge sonrası temizlik |
| Pages | kapalı | preview ihtiyacımız workflow artifact'ları |

`gh` ile:
```bash
gh repo edit --enable-squash-merge --enable-rebase-merge \
  --delete-branch-on-merge --enable-auto-merge
```

---

## ÖZET (tek bakışta)

| Adım | Komut | Durum / Ne zaman |
|---|---|---|
| 0. Ön-kontrol | `bash docs/publish_precheck.sh --allow-remote` | ✅ hazır — her push öncesi |
| 0.5 Repack testi | `bash _calisma/CIKTI/ci_repack_test.sh` | opsiyonel, önerilir |
| 1 (a). Repo oluştur | `gh repo create leibniz2 --public ...` | ✅ UYGULANDI — kayıt amaçlı |
| 1 (b). Branch protection | web UI (link + görsel kılavuz) | ⏳ BEKLEMEDE — kalan kurulum adımı |
| 2. Remote + ilk push | `git remote add origin …; git push -u origin main` | ✅ UYGULANDI — kayıt amaçlı |
| 3. Push (günlük) | `git push origin main` | 🔄 her değişiklikte (INCREMENTAL PUSH) |
| 4. CI izle + doğrula | `gh run watch` + job/artifact kontrolü | 🔄 her push'ta |
| — (tek komut) | `bash docs/publish_wrapper.sh` | idempotent; önce `--dry-run` ile prova |

**Bilinen sınırlar:**
- K6-DETERM metadata-stripped PDF hash'i run'lar arası DEĞİŞEBİLİR — belgelenmiş
  qpdf non-determinizmi (MANIFEST V5i/V5k/V5l); bilgi amaçlı, P0/P1 üretmez.
  Repack tarafı sidecar reuse ile byte-identical (V5l + repack-verify kapısı).
- İlk run soğuk başlangıç: Z3 + Lean 4 (elan stable) kurulumu toplam süreyi
  uzatır (~5-15 dk); sonraki run'lar cache ile hızlanır.
- `manifest-comment` ve tek "PR doğrulama durumu" yorumu (bütçe + pre-commit
  P0/P1) yalnızca `pull_request` olayında çalışır; push'ta üretilmez.
- Branch protection `strict:true` — fork'tan PR'lerde CI çalışmayabilir; bu beklenen davranış.

---

## ŞEFFAFLIK

- `git push` **iki kez onay gerektirir**: (i) bu senaryoyu çalıştırma kararı (sen), (ii) terminalde push komutunun çalıştırılması (sen).
- Repo **public** oluşturulur — kişisel/özel veri yok ama workflow artifact'ları herkes erişebilir. İçerik tamamen akademik makale + matematiksel ispat; gizlilik riski yok.
- Branch protection **strict** — ilk push'ta CI yeşil olmalı. Eğer yanlışlıkla kırmızı kalırsa, tarayıcıda Settings → Branches → kuralı sil (`.../settings/branches`) ile koruma kaldırılabilir (geçici).
