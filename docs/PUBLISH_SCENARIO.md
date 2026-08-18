# GitHub Publish Senaryosu — Stoic-Hume V5

Bu senaryo, `_calisma/CIKTI/` ve kök config'leri (workflow, pre-commit, README) içeren
**yerel repo'yu** GitHub'a taşır ve **CI'ı ilk kez çalıştırır**.

> **Ana prensip:** `git push` zaten istenmeden yapılmaz. Bu senaryo **4 aşamalıdır**
> (4. opsiyonel); her aşama, bir sonrakine geçmeden önce bilinçli onay gerektirir.
>
> **Durum:** senaryo 2026-08-18'de uygulandı — repo `ali-han-kaya/leibniz2`
> GitHub'da (PUBLIC, default `main`). Yeniden çalıştırmak istersen AŞAMA 0'ı
> `bash docs/publish_precheck.sh --allow-remote` ile başlat (incremental push).

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
cd /Users/alikaya/Desktop/leibniz2

# (a) Repo temiz mi?
git status --short         # ← boş olmalı
git log --oneline -5       # ← temiz linear history; test-marker commit'i olmamalı

# (a2) Commit mesaj kuralı kurulu mu? (bkz. docs/HISTORY_CLEANUP.md)
git config commit.template      # ← ".gitmessage" olmalı
ls .git/hooks/commit-msg        # ← var olmalı (pre-commit install --hook-type commit-msg)

# (b) Pre-commit hooks çalışıyor mu? (commit-msg kuralına uygun mesaj —
#     "smoke:" başlığı artık commit-msg-style hook'u tarafından REDDEDİLİR)
git commit --allow-empty -m "docs: pre-commit smoke test" 2>&1 | grep -E "Passed|Failed"
git reset --hard HEAD^     # smoke commit'i geri al (branch ilerletme)

# (c) gh CLI kurulu mu ve auth var mı?
gh --version
gh auth status             # ← "Logged in to github.com as <user>" görmeli

# (d) Push'lanacak branch + remote yokluğu:
git remote -v              # ← boş olmalı (henüz remote yok)
git branch --show-current  # ← "main" olmalı
```

**Beklenen çıktılar:**
- `git status` → boş
- pre-commit smoke test → 4 Passed (update-config + verify-delivery + symbolic + lean;
  commit-msg-style ayrı stage — `pre-commit run` çıktısında görünmez)
- `gh auth status` → "Logged in"
- `git remote -v` → boş

⚠️ **Eğer bunlardan biri yanlışsa DURUR — AŞAMA 1'e geçme.**

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

# (b) Branch koruması — GitHub web UI (gh api yerine; manuel + şeffaf)
#     Hazır tarayıcı linki (kopyala-yapıştır):
#       https://github.com/<user>/leibniz2/settings/branches
#
#     macOS'ta doğrudan açmak için:
open "https://github.com/<user>/leibniz2/settings/branches"
#
#     Web UI'da:
#       "Add branch protection rule" → Branch name pattern: `main`
#       ✓ Require status checks to pass before merging
#         → ara ve ekle: önce otomatik ad listesini al (tek kaynak = workflow):
#             python3 _calisma/CIKTI/status_checks.py
#           (6 kapı; adlar = workflow job `name:` alanları — elle yazma,
#           workflow değişince sürüklenmesin):
#           Delivery verification — K1-K9 (single entry point)
#           Budget shield (aggregated)
#           Static markdown reports (incl. pre-commit findings)
#           Reproducibility bundle
#           Config drift check (gen_config --dry-run)
#           Repack determinism + verify (sidecar sync)
#         (manifest-comment job'ı yalnızca PR'da koşar — required check değil)
#           → ✓ "Require branches to be up to date before merging" (strict)
#       ✓ Do not allow bypassing the above settings   (enforce_admins)
#       ✓ Disallow force pushes
#       ✓ Disallow deletions
```

**Beklenen çıktılar:**
- `gh repo create` → "Created repository <user>/leibniz2"
- Tarayıcıda Settings → Branches → `main` için kural eklendi (koruma aktif)

**Görsel doğrulama:** https://github.com/<user>/leibniz2 adresi boş repo olarak açılmalı.

**Sonraki doğrulama (koruma kurulduktan sonra):** workflow ↔ GitHub eşleşmesi
otomatik kontrol edilir — AŞAMA 0'ı `--allow-remote` ile tekrar çalıştır veya:
```bash
python3 _calisma/CIKTI/status_checks.py --gh
# SONUÇ: PASS — 6 check birebir eşleşiyor (workflow ↔ GitHub)
```
Eksik/fazla check → exit 1 (fail-closed): web UI'da listeyi `status_checks.py`
çıktısıyla eşitle veya workflow'u güncelle.

---

## AŞAMA 2 — Remote ekle + push (geri dönüşü olan adım)

```bash
cd /Users/alikaya/Desktop/leibniz2

# (a) Remote ekle (token değil — SSH veya gh'nin auth'u yeterli)
gh repo set-default leibniz2  # (opsiyonel; repo'yu default yapar)
git remote add origin git@github.com:$(gh repo view --json owner -q '.owner.login')/leibniz2.git

# Doğrula:
git remote -v
# origin  git@github.com:<user>/leibniz2.git (fetch)
# origin  git@github.com:<user>/leibniz2.git (push)

# (b) İlk push — main branch + upstream set
git push -u origin main
```

**Beklenen çıktı:**
```
Enumerating objects: N, done.
Counting objects: 100% (N/N), done.
...
To github.com:<user>/leibniz2.git
 * [new branch]      main -> main
Branch 'main' set up to track remote 'origin/main'.
```

**Süre:** ~5-15 sn (küçük repo, 73 dosya, ~10 MiB).

**Görsel doğrulama:** https://github.com/<user>/leibniz2 adresinde:
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

# (c) Artifact'ları kontrol et (10 adet olmalı — liste aşağıda)
gh run view $RUN_ID --json artifacts --jq '.artifacts[] | "\(.name) (\(.size_in_bytes) B)"'
```

**Beklenen (7 job):**
| Job | Beklenen sonuç |
|---|---|
| Delivery verification — K1-K9 (single entry point) | ✅ PASS (P0=0, P1=0) — K1-K7 + K0 + soy hattı + bütçe + K8 (Z3 12/12) + K9 (Lean) tek komutta; pre-commit 4 hook'u advisory bölüm olarak aynı job içinde |
| Budget shield (aggregated) | ✅ limit içinde (sidecar birleştirildi) |
| Static markdown reports (incl. pre-commit findings) | ✅ bundle yüklendi |
| Reproducibility bundle | ✅ manifest.txt + SHA-256 (run_id ile) |
| Config drift check (gen_config --dry-run) | ✅ config paketle uyumlu |
| Repack determinism + verify (sidecar sync) | ✅ repack byte-identical, base verify PASS |
| Manifest PR comment | yalnızca PR'da: manifest.txt PR yorumu olarak düşer |

**Artifact listesi (10):**
- `verify-report` (tek log: K1-K9 + pre-commit bölümü + .sha256)
- `budget-verify` + `budget` (bütçe sidecar + aggregator)
- `config` (ham + şema + etkin config + diff)
- `k0-findings` (bayat-zip taraması JSON)
- `refs-online` (çevrimiçi referans denetimi VERSION JSON)
- `precommit-logs` (ham log + PRECOMMIT_RAPORU.md + cache/env özeti)
- `reports` (statik markdown raporları)
- `reproducibility` (tüm artifact'ların SHA-256 manifest'i)
- `repack-verify` (repack sonrası base verify raporu)

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
# required check'ler (6 kapı) TAMAMLANMADAN veya branch main'in gerisindeyken
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
| 1. Repo oluştur | `gh repo create leibniz2 --public ...` | AŞAMA 0 yeşilse |
| 2. Push | `git push -u origin main` | AŞAMA 1 yeşilse |
| 3. CI izle | `gh run watch` | AŞAMA 2 sonrası 5-15 dk |
| 4. Doğrula | artifact listesi + PASS | AŞAMA 3 sonrası |

**Bilinen sınırlar:**
- K6-DETERM metadata-stripped PDF hash'i run'lar arası DEĞİŞEBİLİR — belgelenmiş
  qpdf non-determinizmi (MANIFEST V5i/V5k/V5l); bilgi amaçlı, P0/P1 üretmez.
  Repack tarafı sidecar reuse ile byte-identical (V5l + repack-verify kapısı).
- İlk run soğuk başlangıç: Z3 + Lean 4 (elan stable) kurulumu toplam süreyi
  uzatır (~5-15 dk); sonraki run'lar cache ile hızlanır.
- `manifest-comment` ve PR yorumları (bütçe aşımı, pre-commit P0) yalnızca
  `pull_request` olayında çalışır; push'ta üretilmez.
- Branch protection `strict:true` — fork'tan PR'lerde CI çalışmayabilir; bu beklenen davranış.

---

## ŞEFFAFLIK

- `git push` **iki kez onay gerektirir**: (i) bu senaryoyu çalıştırma kararı (sen), (ii) terminalde push komutunun çalıştırılması (sen).
- Repo **public** oluşturulur — kişisel/özel veri yok ama workflow artifact'ları herkes erişebilir. İçerik tamamen akademik makale + matematiksel ispat; gizlilik riski yok.
- Branch protection **strict** — ilk push'ta CI yeşil olmalı. Eğer yanlışlıkla kırmızı kalırsa, tarayıcıda Settings → Branches → kuralı sil (`.../settings/branches`) ile koruma kaldırılabilir (geçici).