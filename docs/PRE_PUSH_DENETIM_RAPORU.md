# Pre-Push Denetim Raporu — CI Yeşile Kadar Geçen 3 Kırılma

Bu belge, "bekleyen commit'leri push et + CI'ı yeşil doğrula" denetiminde ortaya
çıkan **üç gerçek hatanın** tam kaydıdır. Amaç: her kırılmanın belirtisi, kök
nedeni, düzeltmesi ve kanıtı **tek kaynaktan** denetlenebilir olsun; aynı sınıf
hatalar bir daha `gh run watch` sırasında sürpriz olmasın.

---

## 0. Kapsam ve son durum

- **Başlangıç:** `origin/main` `e0552a2`'deydi; yerel `main` **68 commit** öndeydi.
  (Kullanıcı istemindeki "28 commit" gerçek bekleyen kümenin alt kümesiydi — 68'in
  tamamı push edildi.)
- **Push edilen toplam:** 68 bekleyen commit + 3 düzeltme commit'i = **71 commit**.
- **Son durum:** `origin/main` == `HEAD` == `da6cb21`, working tree temiz,
  son run **`32243532153` → ✓ success**, `##[error]` yok, ANNOTATIONS boş.

| Deneme | Run | Sonuç | Bulunan hata |
|---|---|---|---|
| 1. push (`5d53ccc`) | `32241471102` | failure, 0s, 0 job | #1 Yapışık YAML satırı |
| 2. push (`d57a60c`) | `32241821709` | failure (unit test exit 1) | #2 env snapshot (`GITHUB_STEP_SUMMARY`) |
| 3. push (`5d10771`) | `32242938612` | success ama advisory pre-commit FAIL | #3 dash/bash uyumsuzluğu |
| 4. push (`da6cb21`) | `32243532153` | **success, tamamen yeşil** | — |

---

## 1. Kırılma #1 — Yapışık YAML satırı (workflow ayrıştırılamadı)

**Belirti:** Run `32241471102` — `completed failure, 0s`, 0 job,
`gh run view` çıktısı: *"This run likely failed because of a workflow file issue."*

**Kök neden:** `budget` job'ının "PR status — labels + comment" adımındaki
`github-script` bloğunun kapanış `}` ile bir sonraki adım
`- name: Upload budget bundle` **aynı satıra yapışmıştı**:

```yaml
              console.log('Durum yorumu oluşturuldu');
            }      - name: Upload budget bundle
```

Bu, `- name: Upload budget bundle` satırını literal block scalar'ın içine gömdü;
sonuçta aynı step'e iki `uses:` ve iki `if:` anahtarı düştü (duplicate key).
GitHub Actions bunu reddeder.

**Tespit yöntemi (kanıt):** Standart `yaml.safe_load` **bu hatayı sessizce
tolare eder** (son anahtar kazanır). Hata ancak **strict duplicate-key YAML
loader** ile yakalandı. Düzeltme sonrası strict loader `no duplicate keys` verdi.

**Düzeltme:** Satır ayrıldı; `Upload budget bundle` yeniden bağımsız adım oldu
(budget job 9 adıma döndü). Commit **`d57a60c`** (`ci: verify.yml bütçe job'ında
yapışık adım satırını düzelt`). Diff: `+2 / -1` satır.

**Doğrulama:** Sonraki push'ta workflow ayrıştı ve 9 job oluştu.

---

## 2. Kırılma #2 — `GITHUB_STEP_SUMMARY` import-anı yakalaması

**Belirti:** Run `32241821709` — fail-closed "Run CIKTI unit tests" adımı
`exit 1` (15 test FAIL). Adım `if: always()` taşımadığından sonraki tüm kurulum
adımları (pre-commit, Z3, Lean) **atlandı**; bu yüzden advisory pre-commit adımı
da `exit 127` (komut yok) verdi — zincirleme, ama kökü unit test'ti.

**Kök neden:** `run_summary_budget.py`, `run_summary_k0.py`,
`run_summary_klayers.py`, `run_summary_lineage.py`, `run_summary_precommit.py` ve
`consolidate_summary.py` modülleri şunu yapıyordu:

```python
SUMMARY_PATH = os.environ.get("GITHUB_STEP_SUMMARY")   # import anında!
```

GitHub Actions her adıma `GITHUB_STEP_SUMMARY` env'ini **set eder**. Bu yüzden
CI'da `summary_sink()` özeti **dosyaya** yazıp stdout'a yalnızca
`"Budget summary written to run summary."` gibi kısa bir onay basıyordu. Testler
ise özetin **stdout'ta** olduğunu doğruluyordu → CI'da FAIL, yerelde (env yok)
PASS. Klasik "yalnızca CI'da patlayan test" sınıfı.

**Düzeltme:** Env **çağrı anında** okunur hale getirildi (modül sabiti kaldırıldı);
4 test sınıfı `setUp`/`tearDown` ile env'i temizleyip stdout davranışını sabitledi.
Üretim davranışı **değişmedi** (env setken dosyaya yazar). Commit **`5d10771`**
(`fix: run summary summary_sink GITHUB_STEP_SUMMARY'yi çağrıda okusun`).

**Doğrulama:** `GITHUB_STEP_SUMMARY=/tmp/... python3 -m unittest` (CI simülasyonu)
→ **19/19 OK**; tam paket **116/116 OK**; üretim modu (env set) hâlâ dosyaya yazar.

---

## 3. Kırılma #3 — `sh` (dash) ile koşan bash hook'u

**Belirti:** Run `32242938612` **success** idi ama advisory pre-commit adımında
`update-config` hook'u `Failed` görünüyordu:

```
Sync config from package content (gen_config.py).........................Failed
- hook id: update-config
- exit code: 2
_calisma/CIKTI/update_config_hook.sh: 28: set: Illegal option -o pipefail
```

**Kök neden:** `update_config_hook.sh` bash'a özgü `set -o pipefail` ve
`${BASH_SOURCE[0]}` kullanıyor (shebang'i de `#!/usr/bin/env bash`), ama
`.pre-commit-config.yaml`'de `entry: sh _calisma/CIKTI/update_config_hook.sh`
olarak tanımlıydı. Ubuntu'da `sh` = `dash`, `pipefail`'i tanımaz → exit 2.
macOS'ta `sh` = bash olduğundan **yerelde gizli kalan** bir hataydı.

**Düzeltme:** `entry` `bash` yapıldı. Commit **`da6cb21`**
(`fix: pre-commit update-config hook'unu sh yerine bash ile çalıştır`).
Diğer `sh` entry'li betikler (`verify_lean.sh`, `commit_msg_hook.sh`) bashism
içermiyor (grep ile doğrulandı) — onlara dokunulmadı.

**Doğrulama:** Son run `32243532153`'te advisory pre-commit bölümü
**4/4 hook Passed** (update-config, verify-delivery, Z3 12/12, Lean).

---

## 4. Yeşil kanıt (kaynaklı)

Run `32243532153`:

| Job | Sonuç |
|---|---|
| Delivery verification — K1-K9 (single entry point) | ✓ 1m37s |
| Repack determinism + verify (sidecar sync) | ✓ 2m12s |
| Static markdown reports | ✓ |
| Budget shield (aggregated) | ✓ |
| Config drift check (gen_config + diff-on-drift) | ✓ |
| Online verification trend (refs-online) | ✓ |
| Reproducibility bundle (K10 bütünlüğü dahil) | ✓ |
| Pre-commit P0 label gate / Manifest PR comment | `-` (push'ta skip — beklenen) |

Verify job iç çıktısı: `SONUÇ: PASS (P0=0, P1=0)`, K8 Z3 **12/12**, K9 Lean
**PASS**, K11/K13/K14 PASS, çevrimiçi referans **49/54** doğrulandı
(CrossRef 4 + SEP 5 + OpenLibrary 22). Yerelde: unit test paketi **116/116 OK**,
pre-commit **5/5 Passed**.

---

## 5. Önleme (aynı sınıfın tekrarına karşı)

| # | Sınıf | Önerilen kapı | Durum |
|---|---|---|---|
| 1 | Yapışık/duplicate-key YAML | **actionlint** (ya da strict duplicate-key YAML check) CI'a ekle | öneri |
| 2 | Env'e bağımlı test | Yerel simülasyon `GITHUB_STEP_SUMMARY` setken koşsun; testler env-bağımsız kaldı | kısmen (modül düzeltildi; simülasyona env set eklenmedi) |
| 3 | `sh` entry'li bash betiği | `sh` entry'li betikleri POSIX lint'le; bashism varsa `entry`'yi `bash` yap | öneri (verify_lean.sh + commit_msg_hook.sh tarandı, temiz) |

Bu üç sınıf, `docs/PUBLISH_SCENARIO.md` AŞAMA 0 ön-kontrolüne de
eklenebilir: push öncesi `actionlint` + `GITHUB_STEP_SUMMARY` setlenmiş yerel test
+ `sh`-entry hook taraması.

## 6. İlgili kayıt

- `d57a60c`, `5d10771`, `da6cb21` — bu rapordaki üç düzeltme commit'i.
- `docs/HISTORY_CLEANUP.md` — noise commit temizliği (farklı denetim alanı).
- `docs/PUBLISH_SCENARIO.md` — yayın akışı ve AŞAMA 0 ön-kontrolü.
