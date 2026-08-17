# GitHub Publish Senaryosu — Stoic-Hume V5

Bu senaryo, `_calisma/CIKTI/` ve kök config'leri (workflow, pre-commit, README) içeren
**yerel repo'yu** GitHub'a taşır ve **CI'ı ilk kez çalıştırır**.

> **Ana prensip:** `git push` zaten istenmeden yapılmaz. Bu senaryo **3 aşamalıdır**;
> her aşama, bir sonrakine geçmeden önce bilinçli onay gerektirir.

---

## AŞAMA 0 — Ön-kontrol (güvenli, otomatik)

```bash
cd /Users/alikaya/Desktop/leibniz2

# (a) Repo temiz mi?
git status --short         # ← boş olmalı
git log --oneline -5       # ← temiz linear history; test-marker commit'i olmamalı

# (b) Pre-commit hooks çalışıyor mu?
git commit --allow-empty -m "smoke: empty commit pre-commit test" 2>&1 | grep -E "Passed|Failed"
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
- pre-commit smoke test → 3 Passed
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

# (b) Branch koruması ekle (main'e doğrudan push koruması — CI yeşil olmalı)
gh api -X PUT /repos/$(gh repo view --json owner,name -q '.owner.login + "/" + .name')/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["verify", "symbolic", "lean", "reports", "budget"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

**Beklenen çıktılar:**
- `gh repo create` → "Created repository <user>/leibniz2"
- API PUT → HTTP 200 (branch protection kuruldu)

**Görsel doğrulama:** https://github.com/<user>/leibniz2 adresi boş repo olarak açılmalı.

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

**Süre:** ~5-15 sn (küçük repo, ~30 dosya).

**Görsel doğrulama:** https://github.com/<user>/leibniz2 adresinde:
- Temiz linear history (20 commit; test-marker `d863977`/`991473d` rebase ile ezildi)
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

# (c) Artifact'ları kontrol et (5 adet olmalı)
gh run view $RUN_ID --json artifacts --jq '.artifacts[] | "\(.name) (\(.size_in_bytes) B)"'
```

**Beklenen:**
| Job | Beklenen sonuç |
|---|---|
| verify | ✅ PASS (K1-K7) |
| symbolic | ✅ PASS (12/12 Z3) |
| lean | ✅ PASS (Lean 4 reduct-invariance) |
| budget | ✅ PASS (3 sidecar birleştirildi) |
| reports | ✅ bundle yüklendi |

**Artifact listesi (5):**
- `verify-report` (~2 KB)
- `budget-verify` (~600 B)
- `symbolic-report` (~5 KB)
- `budget-symbolic` (~600 B)
- `lean-report` (~3 KB)
- `budget-lean` (~600 B)
- `budget` (~2 KB, aggregator)
- `reports` (~30 KB, 4 markdown)

**Not:** `--check-references` + Beth 1953 düzeltmesi olmadan `--full` exit 1 verir.
Bu BİLİNEN ve PLANLANMIŞ bir P1 bulgusudur; ilk commit'te yeşil olması **beklenmez**.

---

## OPSİYONEL AŞAMA 4 — Branch protection'ın çalıştığını kanıtla

```bash
# (a) Main'e doğrudan bir değişiklik push'la — branch protection REDDETMELI
echo "test" > /tmp/should-fail.md
git checkout -b test/protection-check
git add /tmp/should-fail.md  # (ya da uygun dosya)
git commit -m "should be blocked by protection"
git push origin test/protection-check  # ← feature branch: geçer
# Şimdi main'e PR aç:
gh pr create --base main --head test/protection-check --title "test: protection"
gh pr merge --squash  # ← status check FAIL olduğu için REDDEDİLMELI
git checkout main
git branch -D test/protection-check

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
- `d863977` + `991473d` (test markers) — **EZİLDİ**: `git rebase --onto 5d62685 991473d` ile net-sıfır diff temizlendi (add+remove aynı dosya olduğundan tek anlamlı sonuç silmekti)

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
| 0. Ön-kontrol | `git status` + `gh auth status` | her şeyden önce |
| 1. Repo oluştur | `gh repo create leibniz2 --public ...` | AŞAMA 0 yeşilse |
| 2. Push | `git push -u origin main` | AŞAMA 1 yeşilse |
| 3. CI izle | `gh run watch` | AŞAMA 2 sonrası 5-15 dk |
| 4. Doğrula | artifact listesi + PASS | AŞAMA 3 sonrası |

**Bilinen sınırlar:**
- İlk CI run'ı `--check-references` veya `--full` içermez (henüz eklenmedi); yeşil olur.
- `--full` eklemek için Beth 1953 düzeltmesi + manifest yeniden üretimi gerekir — ayrı görev.
- Branch protection `strict:true` — fork'tan PR'lerde CI çalışmayabilir; bu beklenen davranış.

---

## ŞEFFAFLIK

- `git push` **iki kez onay gerektirir**: (i) bu senaryoyu çalıştırma kararı (sen), (ii) terminalde push komutunun çalıştırılması (sen).
- Repo **public** oluşturulur — kişisel/özel veri yok ama workflow artifact'ları herkes erişebilir. İçerik tamamen akademik makale + matematiksel ispat; gizlilik riski yok.
- Branch protection **strict** — ilk push'ta CI yeşil olmalı. Eğer yanlışlıkla kırmızı kalırsa, `gh api DELETE .../branches/main/protection` ile koruma kaldırılabilir (geçici).