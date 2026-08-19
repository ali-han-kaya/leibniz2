# GitHub Publish Senaryosu — Stoic-Hume V5

Bu senaryo, `_calisma/CIKTI/` ve kök config'leri (workflow, pre-commit, README) içeren
**yerel repo'yu** GitHub'a taşır ve **CI'ı ilk kez çalıştırır**.

> **Ana prensip:** `git push` zaten istenmeden yapılmaz. Bu senaryo **4 aşamalıdır**
> (4. opsiyonel); her aşama, bir sonrakine geçmeden önce bilinçli onay gerektirir.
>
> **Durum:** senaryo 2026-08-18'de uygulandı — repo **canlı**:
> https://github.com/ali-han-kaya/leibniz2 (PUBLIC, default `main`).
> AŞAMA 3'teki job tablosu, `.github/workflows/verify.yml`'deki canlı job
> `name:` alanlarının birebir aynısıdır (10 job); required check adları da aynı
> tek kaynaktan türer (`python3 _calisma/CIKTI/status_checks.py --json`).
> Yeniden çalıştırmak istersen AŞAMA 0'ı `bash docs/publish_precheck.sh
> --allow-remote` ile başlat (incremental push).

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

---

## TEK KOMUT — publish_wrapper.sh (tüm senaryo)

Aşağıdaki manuel aşamaların **birebir aynısını tek komutla, interaktif olmadan**
çalıştıran wrapper: [`docs/publish_wrapper.sh`](publish_wrapper.sh).

| Kullanım | Davranış |
|---|---|
| `bash docs/publish_wrapper.sh` | AŞAMA 0-3: precheck → repo oluştur → remote+push → CI izle (5-15 dk) |
| `bash docs/publish_wrapper.sh --with-stage4` | AŞAMA 0-4 (opsiyonel koruma testi dahil) |
| `bash docs/publish_wrapper.sh --dry-run` | **Prova:** hiçbir komut çalışmaz; her kalıcı komut `[DRY-RUN] çalıştırılacak: ...` olarak önizlenir (exit 0) |
| `bash docs/publish_wrapper.sh --dry-run --with-stage4` | AŞAMA 0-4'ün tam önizlemesi |
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
- pre-commit smoke test → **5/5 Passed (tamamen yeşil)** — update-config + verify-delivery
  (K1-K7) + verify-delivery-symbolic (K8/Z3, z3-solver izole ortamda) +
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

```bash
# (a) Kişisel hesabın altında boş repo oluştur
gh repo create leibniz2 \
    --description "Stoic-Hume V5 — fail-closed academic delivery with Z3 + Lean 4 proofs" \
    --public \
    --disable-issues=false \
    --disable-wiki=true \
    --disable-projects=true \
    --add-readme=false     # bizim README'miz commit'lenecek; çakışmasın

# Wrapper (publish_wrapper.sh) kullanılıyorsa burada OTOMATİK doğrulama koşar:
#   python3 _calisma/CIKTI/status_checks.py      # 8 ad workflow'dan türetilir
#   python3 _calisma/CIKTI/status_checks.py --gh # GitHub eşleşmesi (koruma yoksa UYARI,
#                                                # gerçek drift varsa FAIL — fail-closed)

# (b) Branch koruması — GitHub web UI (gh api yerine; manuel + şeffaf)
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
#           Budget shield (aggregated)
#           Pre-commit P0 label gate
#           Static markdown reports (incl. pre-commit findings)
#           Reproducibility bundle
#           Config drift check (gen_config + diff-on-drift)
#           Repack determinism + verify (sidecar sync)
#           Online verification trend (refs-online across runs)
#         (manifest-comment job'ı yalnızca PR'da koşar — required check değil;
#          label-gate de PR'da koşar ama BİLEREK required check — etiket kapısı)
#           → ✓ "Require branches to be up to date before merging" (strict)
#       ✓ Do not allow bypassing the above settings   (enforce_admins)
#       ✓ Disallow force pushes
#       ✓ Disallow deletions
```

### Branch protection — web UI adım adım (8 required check)

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
   - Arama kutusuna şu **8 adı** tek tek yazıp seç (birebir, `—` karakteri dahil):
     1. `Delivery verification — K1-K9 (single entry point)`
     2. `Budget shield (aggregated)`
     3. `Pre-commit P0 label gate`
     4. `Static markdown reports (incl. pre-commit findings)`
     5. `Reproducibility bundle`
     6. `Config drift check (gen_config + diff-on-drift)`
     7. `Repack determinism + verify (sidecar sync)`
     8. `Online verification trend (refs-online across runs)`
     > `manifest-comment` job'ı yalnızca PR'da koşar — required check DEĞİL; ekleme.
     > `Pre-commit P0 label gate` de yalnızca PR'da koşar ama BİLEREK required
     > check'tir: precommit-p0 etiketi varken FAIL verip merge'i bloke eder
     > (aşağıdaki "P0 label gate — etiket kapısı" bölümüne bak).
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
- `gh repo create` → "Created repository ali-han-kaya/leibniz2"
- Tarayıcıda Settings → Branches → `main` için kural eklendi (koruma aktif)

**Görsel doğrulama:** https://github.com/ali-han-kaya/leibniz2 adresi boş repo olarak açılmalı.

Koruma kurulduktan sonra doğrulama → yukarıdaki adım 9 (veya AŞAMA 0'ı
`--allow-remote` ile tekrar çalıştır — (e) adımı aynı eşleşmeyi denetler).

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
# → listede "Pre-commit P0 label gate" (toplam 8 check)
```

**Davranış tablosu:**

| PR'da `precommit-p0` | label-gate sonucu | Merge |
|---|---|---|
| Yok | ✅ PASS | izinli |
| Var | ❌ FAIL | bloke (P0 giderilene dek) |

> P1 (`precommit-p1`) bilinçli olarak kapı DEĞİLDİR — advisory uyarı olarak
> kalır (yalnızca P0 kritik bulgu merge'i bloke eder). İstenirse aynı desenle
> bir `precommit-p1` kapısı da eklenebilir.

---

## AŞAMA 2 — Remote ekle + push (geri dönüşü olan adım)

```bash
cd ~/Desktop/leibniz2

# (a) Remote ekle (token değil — SSH veya gh'nin auth'u yeterli)
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

## AŞAMA 3 — CI çalıştığını doğrula (5-15 dk bekle)

```bash
# (a) İlk run'ı tetikle (push zaten tetiklemiş olmalı; kontrol için bekle)
gh run list --limit 3 --json databaseId,status,conclusion,name
# Tüm run'lar "in_progress" veya "completed" olmalı

# (b) Belirli run'ın loglarını izle (tail modunda)
RUN_ID=$(gh run list --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch $RUN_ID --exit-status

# (c) Artifact'ları kontrol et (11 adet olmalı — liste aşağıda)
gh run view $RUN_ID --json artifacts --jq '.artifacts[] | "\(.name) (\(.size_in_bytes) B)"'
```

**Wrapper:** bu aşamayı `publish_wrapper.sh` otomatik yapar — `gh run watch
--exit-status` + artifact listesi; sonuç `SONUÇ: PASS/FAIL` olarak loglanır
(dry-run'da yalnızca önizlenir).

**Beklenen (10 job):**
| Job | Beklenen sonuç |
|---|---|
| Delivery verification — K1-K9 (single entry point) | ✅ PASS (P0=0, P1=0) — K1-K7 + K0 + soy hattı + bütçe + K8 (Z3 12/12) + K9 (Lean) tek komutta; pre-commit 4 hook'u advisory bölüm olarak aynı job içinde |
| Budget shield (aggregated) | ✅ limit içinde (sidecar birleştirildi); PR'da tek "PR doğrulama durumu" yorumu (bütçe + pre-commit) + precommit-p0/p1 etiketi |
| Pre-commit P0 label gate | ✅ precommit-p0 etiketi yoksa PASS; varsa FAIL (merge bloke — required check) |
| Static markdown reports (incl. pre-commit findings) | ✅ bundle yüklendi |
| Reproducibility bundle | ✅ manifest.txt + SHA-256 (run_id ile) |
| Config drift check (gen_config + diff-on-drift) | ✅ config paketle uyumlu |
| Repack determinism + verify (sidecar sync) | ✅ repack byte-identical, base verify PASS |
| Online verification trend (refs-online across runs) | ✅ trend tablosu üretildi (advisory, run'lar arası) |
| Publish precheck (AŞAMA 0, advisory) | ✅ AŞAMA 0 kapıları (tree/noise/gh/status_checks) her push'ta otomatik denetlenir; yerel-only kontroller INFO (required check DEĞİL) |
| Manifest PR comment | yalnızca PR'da: manifest.txt PR yorumu olarak düşer |

**Artifact listesi (12):**
- `verify-report` (tek log: K1-K9 + pre-commit bölümü + .sha256)
- `budget-verify` + `budget` (bütçe sidecar + aggregator)
- `config` (ham + şema + etkin config + diff)
- `k0-findings` (bayat-zip taraması JSON)
- `refs-online` (çevrimiçi referans denetimi VERSION JSON)
- `precommit-logs` (ham log + PRECOMMIT_RAPORU.md/.json + cache/env özeti)
- `reports` (statik markdown raporları)
- `reproducibility` (tüm artifact'ların SHA-256 manifest'i)
- `repack-verify` (repack sonrası base verify raporu)
- `refs-trend` (run'lar arası çevrimiçi referans zaman serisi)
- `precheck-report` (AŞAMA 0 ön-kontrol logu — advisory, her push'ta)

**Not:** Kapı artık `verify_delivery.py --full`'dur (K1-K9, fail-closed) ve yeşildir —
Beth 1953 / Fosl 1998 gibi referans düzeltmeleri V5h'te yapıldı; Kalan çevrimdışı
kaynaklar `refs-online`'da advisory olarak izlenir (kapıyı kırmaz).

---

## OPSİYONEL AŞAMA 4 — Branch protection'ın çalıştığını kanıtla

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
# required check'ler (8 kapı) TAMAMLANMADAN veya branch main'in gerisindeyken
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

| Adım | Komut | Ne zaman |
|---|---|---|
| 0. Ön-kontrol | `bash docs/publish_precheck.sh` (tek komut) | her şeyden önce |
| 0.5 Repack testi | `bash _calisma/CIKTI/ci_repack_test.sh` | AŞAMA 0 yeşilse (opsiyonel, önerilir) |
| 1. Repo oluştur | `gh repo create leibniz2 --public ...` | AŞAMA 0 yeşilse |
| 2. Push | `git push -u origin main` | AŞAMA 1 yeşilse |
| 3. CI izle | `gh run watch` | AŞAMA 2 sonrası 5-15 dk |
| 4. Doğrula | artifact listesi + PASS | AŞAMA 3 sonrası |
| — (tek komut) | `bash docs/publish_wrapper.sh [--with-stage4] [--dry-run]` | AŞAMA 0 yeşilse; önce `--dry-run` ile prova |

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