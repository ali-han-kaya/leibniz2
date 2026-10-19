# Merge Kararı: `reword-working` → `main` (2026-09-17)

**Öneri:** Üç yönlü **merge-commit** ile land et (rebase YOK, squash YOK).
Dal, main'in içeriğinin büyük ölçüde üst kümesidir; main'in 5 bağımsız
düzeltmesi çözüm sırasında **elle korunarak** taşınır. Gerekçe aşağıda
topoloji → commit → dosya katmanında kanıtlanmıştır.

---

## 1. Topoloji ve sayılar

| Ölçüm | Değer |
|---|---|
| merge-base | `7333a55` |
| Daldа main'e girmemiş commit | **104** |
| main'de daldа olmayan commit | 29 (3'ü merge: PR #48/#47/#45) |
| Dal commit'lerinden main'de **patch-dengi** (`git cherry -`) | 16 |
| Dal commit'lerinden gerçekten benzersiz (`git cherry +`) | 88 |
| main tarafında benzersiz commit | 10 |
| `git merge-tree` simülasyonu | **rc=1 — 22 dosyada çakışma** |
| Net içerik farkı `origin/main..HEAD` | 45 dosya, +1211/−378 |

**Kök durum:** Aynı işin büyük bölümü daldan PR'lerle (squash/rebase
edilerek) main'e girmiş; SHA'lar farklı ama içerikler çakışıyor
(`git cherry` 16 patch-dengi buldu). Bu yüzden merge simülasyonunda
ağırlıklı **add/add** çakışmaları var — semantik olarak "iki kopya iş".

## 2. main tarafındaki 10 benzersiz commit — tek tek değerlendirme

| Commit | Konu | Merge'de akıbeti |
|---|---|---|
| `e6572d1` | PR #42 dev squash (262 dosya, +32.570) — reproducibility gates, verify_mcp, dashboard hardening | Dal bu işin tamamını içeriyor (aynı işin uzun serisi) → dal ucu kazanır |
| `4c483d4`, `534b468`, `cfcaf91` | README changelog resync/prune | Dalın changelog'una işlenmiş (dalandaki README +109 satır) → dal ucu kazanır, merge sonrası `check-changelog-sync` hook'u otomatik senkronlar |
| `f8a1fa0` | Review PDF rebuild + sha256 | **Korunacak**: PDF dalda da değişmiş (add/add çakışma). Karar: dalın PDF'i (V5 zincirinin resmi üretimi) + sha256 yeniden doğrulama; main'in PDF'i eski delivery-resync öncesi |
| `ba088ad` | V5m lineage pin (zip_lineage.json) | **Korunacak satır**: daldaki zip_lineage b69de33 pin'ini içeriyor (`3965c31`); çözümde iki pin setinin birleşimi alınır, `check-zip-lineage-drift` gate doğrular |
| `16d4e06` | review-freshness kendi-repo-zaman düzeltmesi (+test, 64 satır) | **main-e-özeli=13/51, dal-e-özeli=0** — daldа YOK. Çözümde main sürümü esas alınır (dalın dokunuşu bu dosyada yok) |
| `f70779c` | .dockerignore: host z3 venv'i build dışı (4 kural) | **main-e-özeli=6, dal-e-özeli=0** — daldа YOK. main sürümü esas alınır (güvenlik/build hijyeni) |
| `d37d6da` | update_preview.sh bootstrap-arg sırası (+test) | **İki yönlü 27↔33**: dal da bu dosyayı değiştirmiş. 3-way çözüm + main'in arg-order testi korunur |
| `a4aa981` (+#48,#47,#45) | Merge commitleri | Otomatik (3-way) |

## 3. Daldaki benzersiz katkılar (main'e taşınacak asıl değer)

- **3918a04** — plist keepalive drift kapısı: placeholder+profile mimarisi,
  golden'lar, K20 rol-duyarlı summary, verify.yml heredoc/shellcheck onarımı.
  **Kanıt:** main'in plist-golden'ı hâlâ eski `RunAtLoad=true+KeepAlive`
  (drift'li) içeriyor — dalın golden'ı doğru/derin olan taraf.
- **73e94ce** — TeXLive+SDE determinism zinciri (SDE tectonic leak fix,
  kanonik /ID raporlaması, id-residual fail-closed testi), test izolasyonu,
  `.gitignore` hijyeni.
- **5f72054** — **İki CI borcunun tek gerçek kaynağı**: main hâlâ
  `verify.yml:585`'te `--check-only` (taze checkout'ta kalıcı FAIL) ve
  SC2002'li `cat | tail` içeriyor. Gerçek CI (run 35161423568) ikisini de
  yakaladı; düzeltmeler üç yeşil koşumla kanıtlandı (35163054257,
  35163906063: 3/3 workflow success).
- **88 benzersiz commit'in geri kalanı** — skills, claim-evidence matrix,
  FINAL_RC_REPORT, dashboard-shadcn, PUBLISH_SCENARIO, repack zip güncellemesi.

## 4. Çakışan 22 dosya — çözüm tablosu

Dosya başına iki yönlü ölçüm (`git diff origin/main HEAD`, `^−`=main'e özel,
`^+`=dala özel):

| Dosya | main↔dal | Karar |
|---|---|---|
| `.dockerignore` | 6↔0 | **main** (z3 venv kuralları) |
| `check_review_freshness.py` | 13↔0 | **main** (16d4e06) |
| `test_check_review_freshness.py` | 51↔0 | **main** |
| `test_check_bootstrap_start_smoke.py` | 32↔0 | **main** (d37d6da) |
| `update_preview.sh` | 27↔33 | **3-way birleşim** — main'in arg-order düzeltmesi + dalın diğer dokunuşları, elle |
| `Dockerfile` | 4↔5 | **3-way birleşim** — main'in pcre2 yaması (5bf6ebe, bizimkiyle eşdeğer) + dalın yorum bütünlüğü |
| `verify.yml` | 32↔32 | **dal** (CI borç düzeltmeleri + plist zinciri) — main'in 32'si changelog/açıklama satırları; SC2002 ve hook-install düzeltmesi dalda |
| `preview_server.py` | 0↔24 | **dal** |
| `test_texlive_determinism_*`, `texlive_determinism_*` | 0..9↔12..61 | **dal** (sadece dalda; add/add kopyaları dalınca çözülür) |
| `test_coverage_report.py` | 0↔1 | **dal** (HOOK_COVERAGE satırı) |
| `check_unit_tests.list` | 0↔1 | **dal** + merge sonrası `sync_check_unit_tests.py --check` |
| `.gitignore` | 0↔16 | **dal** |
| `README.md` | 26↔109 | **dal** (changelog tabloları dalınca güncel; hook resync'i doğrular) |
| `actionlint_gate.py` | 6↔19 | **dal** (kontrat fix'leri) |
| `plist-golden/*server.plist` | 6↔2 | **dal** (3918a04 golden'ları — main'inki drift'li eski model) |
| `plist-golden/*leibniz2.plist` | — | **dal** (yalnız daldа değişmiş) |
| `verify_mcp/{README,server}` | 1↔1 | **3-way** (tek satırlık dokunuşlar; dalın performans fix'i esas) |
| `findings.md` | 72↔77 | **dal** (denetim raporu dalınca güncel) |
| `_calisma/REVIEW/*.pdf(+sha256)` | add/add | **dal** + sha256'yı dosyayla yeniden doğrula |
| `.dockerignore` (add/add kısmı), `Dockerfile` (add/add kısmı) | — | 3-way; yukarıdaki satır kararlarına uy |

## 5. Riskler ve siperler (safety net)

1. **Merge commit'i local'de oluştur, push etmeden önce tam doğrula.**
   Betikler PATH'te DEĞİL — `_calisma/CIKTI/` öneki şart:
   - `pre-commit run --all-files`
   - `bash _calisma/CIKTI/check_unit_tests_hook.sh` — tam batarya;
     manifest artık **193** test dosyası (bu satır 130 diyordu: sayı
     bayattı, güncellendi)
   - `python3 _calisma/CIKTI/test_coverage_report.py --check` — kapsam
     kapısı (`check-coverage-report` hook'unun girdisi); ölçüldü rc=0
   - `bash _calisma/CIKTI/lint_actionlint.sh` — `.github/workflows/*.yml`
   - `python3 _calisma/CIKTI/sync_check_unit_tests.py --check` —
     manifest + HOOK_COVERAGE + glob-kapsam drift'i (rc=0 ölçüldü)

   **Ortam uyarısı (ölçüldü 2026-09-30):** `preview_server.py` daemon'u
   (`--port 8000 --interval 3600`) saatlik olarak KENDİ
   `pre-commit run --all-files` koşumunu başlatır (gözlenen süreç ağacı:
   `preview_server.py` → `pre_commit run --all-files` → onlarca
   `check_unit_tests_hook.sh`). Yani bu adım tasarım gereği **çakışmalı**
   bir ortamda ölçülür: hook'lar kendi içinde paralel parti koşar,
   daemon'ın koşumu üstüne biner. Bu ortamda tek seferlik kırmızı kesin
   kanıt değildir — deterministik olanı (dosya dosya doğrulanabilen)
   ayır, yeniden üretilemeyeni "yeniden üretilemedi" diye yaz.
2. **PDF bütünlüğü:** `_calisma/REVIEW/*.sha256` merge sonrası `shasum -c`.
3. **Changelog:** README tabloları merge'de iki kopya satır üretebilir →
   `update_changelog_hook.sh` çalıştırıp stale-row pruning ile tekilleştir.
4. **CI kanıtı:** merge push'ı sonrası 3 workflow'un koşumu izlenir;
   docker-security Trivy 0 bulgu + verify-delivery job success beklentisi.
   *(Bu satır "27 job" diyordu — sayı bayat ve tanımı belirsiz: `verify.yml`
   şu an **31** job TANIMLIYOR, ölçülen son `main` koşumu ise 23 success +
   5 skipped üretti. Hangisinin kastedildiği belgelenmeden sayı yazmak
   yanıltıcı; bkz. §7.)*
5. **Geri alınabilirlik:** merge-commit tek `git revert -m 1` ile geri alınır.

## 6. Karar — uygulama durumu (post-merge, ölçüm 2026-09-30)

**MERGE (3-way, merge-commit)** — koşullar:

- [x] **Çakışmalar çözüldü, main'in 5 bağımsız düzeltmesi korundu.**
  Ölçülen çakışma sayısı yukarıdaki **22 DEĞİL**: gerçek merge'lerde iki
  tarafta da değişen dosya sayısı **5** (merge A) ve **4** (merge B).
  22, `git merge-tree` simülasyonunun sonradan kayan bir base'e karşı
  ürettiği *tahmindi*; add/add sanılan dosyaların çoğu otomatik birleşti.
  5 düzeltmenin **5'i de içerik düzeyinde doğrulandı** (§7 tablosu) —
  soyagacı yeterli değildi, çünkü bir çözüm atasının satırını da
  düşürebilir.
- [ ] **Yerel doğrulama zinciri (§5.1) yeşil.** — **HAYIR**, ölçüldü:
  `pre-commit run --all-files` **rc=1**. İki hook kırmızı:
  `check-prettier-format` (**26** js/ts/json dosyası — ölçüm düzeltildi:
  ilk okunan "7" pre-commit'in parti bölmesinden geliyordu; hook her parti
  için ayrı koştuğu için günlük yalnız o partinin dosyalarını gösterir.
  `--all-tracked` ile tam tarama 26 verir; her biri tek tek `--check` ile
  doğrulandı) ve `check-unit-tests` (2 dashboard testi; tekil koşumda 18/18
  ve 26/26 yeşil, 2'li eşzamanlılıkta da yeşil → **yeniden üretilemedi**).
  Bu borç artık görünür: `.github/workflows/prettier-drift.yml` haftalık
  olarak tüm takipli JS/TS/JSON yüzeyini tarar.
- [ ] **Merge push'ı sonrası 3/3 workflow success kanıtı.** — **HAYIR**:
  push yapılmadı. `origin/main` hâlâ `da58b14`; yerel `main` **156**
  commit ileride. Koruma duvarı doğrudan push'u reddediyor
  (14 zorunlu kontrolün 3'ü başarısız).
- **Gerçekleşen merge başlığı** (önerilen uzun başlık değil):
  `Merge branch 'reword-working'` → `008b1aa`, **iki ebeveynli gerçek merge
  commit'i** (`32c1a44` + `a24c4db`). Squash/rebase YOK — öneriye uygun.

## 7. Post-merge gerçeklik (ölçülen)

| Ölçüm | Değer |
|---|---|
| Merge A — `32c1a44`, `origin/main` → `reword-working` | iki tarafta da değişen **5** dosya |
| Merge B — `008b1aa`, `reword-working` → `main` | iki tarafta da değişen **4** dosya |
| Merge B ebeveynleri | `32c1a44`, `a24c4db` (2 ebeveyn = gerçek merge) |
| `origin/main` ↔ yerel `main` | `da58b14` ← **156 commit geride** |

Main tarafı 5 bağımsız düzeltmenin **içerik** doğrulaması (soyagacı +
kanıt):

| Commit | Doğrulama | Sonuç |
|---|---|---|
| `16d4e06` review-freshness kendi-repo zamanı | `check_review_freshness.py` + testi diskte | ✓ |
| `f70779c` .dockerignore z3 venv kuralları | `.dockerignore`'da `.venv_z3` + `**/.venv_z3` + gerekçe yorumu | ✓ |
| `d37d6da` update_preview.sh arg sırası | `update_preview.sh` + `test_check_bootstrap_start_smoke.py` diskte | ✓ |
| `ba088ad` V5m lineage pini | `zip_lineage.json` → `"commit": "b69de33"` | ✓ |
| `f8a1fa0` Review PDF + sha256 | `shasum -c` → **OK** | ✓ |

§5.1 zincirinin bugünkü ölçümü:

| Adım | Sonuç |
|---|---|
| `pre-commit run --all-files` | **rc=1** |
| ↳ `check-prettier-format` | **FAIL** — **26/119** takipli dosya biçim-dışı (tam liste: `--all-tracked` çıktısı). `pre-commit run --all-files` günlüğünde yalnız 7 görünür, çünkü hook PARTİ partí koşar |
| ↳ `check-unit-tests` | **FAIL** — `test_dashboard_keyboard_nav`, `test_dashboard_next_style_gates` (ikisi de tekil yeşil → yeniden üretilemedi) |
| `check_unit_tests_hook.sh` (tam batarya) | **193/193 PASS** |
| `test_coverage_report.py --check` | rc=0 |
| `lint_actionlint.sh` | PASS (5 workflow) |
| `sync_check_unit_tests.py --check` | rc=0 |
| `verify.yml` job tanımı | **31** (ölçüldü) |
| Son `main` verify-delivery koşumu (run `35593197353`) | 23 success + 5 skipped, 0 failure |
| §5.4'teki "27 job success" | **bayat ve tanımı belirsiz** — 27 hiçbir ölçüme karşılık gelmiyor (31 tanım, 28 check-run). Bilerek sayı uydurulmadı; hangi kümenin kastedildiği bir karar |

**Not:** `check-prettier-format` yalnız `\.(js|jsx|ts|tsx|json)$` dosyalarına
bakar. Yani `docs/*.md` prettier kapsamı DIŞINDADIR: bu belgedeki gibi bir
markdown kendi başına drift'li olsa bile hiçbir kapı onu görmez ve görmez.
JS/TS yüzeyindeki 26 dosya ise kapının tam içindedir — orası gerçek borç.

**Muafiyet (tek, gerekçeli):** `_calisma/CIKTI/vendor/axe.min.js` — üçüncü
parti minified a11y motoru, 553 KB, `axe.min.js.sha256` sidecar'ı ile pinli
ve `a11y_gate.py` onu bu pinle doğrular. Biçimlendirmek vendor bütünlüğünü
bozacağı için `.prettierignore` ile kapsam dışı (27 → 26). Bu dosya hariç
hiçbir muafiyet yok: elle yazılmış biçim-dışı dosya borçtur ve görünür kalır.

---

## 8. Ek bölüm — 3-way birleşim *rewrite-rekonsilasyonunda* gerçekleşti mi?

**(ölçüm 2026-09-30; §1'in "16 patch-dengi / 22 çakışma" sayıları bu bölümde
çürütülür ve yerine gerçek merge noktalarında ölçülmüş sayılar konur.)**

§1'in kök-teşhisi şuydu: "aynı işin büyük bölümü daldan PR'lerle (squash/rebase
edilerek) main'e girmiş; SHA'lar farklı ama içerikler çakışıyor." Bu teşhis
**doğru**dur ancak rakamlarının **zamanlaması** yanlıştı: §1 sayıları `7333a55`
base'ine karşı yapılmış bir `git merge-tree` **simülasyonundan** geliyordu ve o
base, gerçekleşen merge'lerin base'i değil. Aşağıda aynı soru **gerçek merge
noktalarında** üç katmanda (yama / byte / semantik) yeniden ölçülür.

### 8.1 Yama (patch-id) katmanı — merge anında taraflar ayrık

`git cherry` gerçek merge-base ile alındığında dahî **tek bir patch-dengi
satırı (`-`) üretmez**; ve SHA'dan bağımsız `git patch-id --stable` kümelerinin
kesişimi **boştur**:

| Merge | merge-base | Sol taraf (commit / patch-id) | Sağ taraf (commit / patch-id) | Paylaşılan patch-id |
|---|---|---|---|---|
| **A** — `origin/main` → `reword-working` | `6db5a2643` | `50d13b6` (dal): **145 / 145** | `da58b14` (main): **3 / 3** | **0** |
| **B** — `reword-working` → `main` | `34b6ea353` | `32c1a44` (main): **98 / 98** | `a24c4db` (reword): **4 / 4** | **0** |
| **PR #50** (birleşim öncesi son PR) | `619913d40` | `53967f6` (main): 1 commit (merge) | `3cabbff` (dal): **34 / 34** | **0** |

`git cherry da58b14 50d13b6` → **145 satırın 145'i `+`** (0 patch-dengi).
`git cherry a24c4db 32c1a44` → **98 satırın 98'i `+`**. `--no-merges`
nedeniyle commit sayıları (147/4 ve 100/6) merge commit'leri dışarıda bırakır;
patch-id kümeleri merge commit'lerinden zaten yama üretmez.

**Yorum:** §1'deki "16 patch-dengi" ölçümü, gerçek merge anında **sıfırdır**.
Yani aynı işin farklı SHA'larla ikinci kez var olması durumu, merge'den **önce**
(branch'i hedefleyen PR birleşimlerinde) tamamen çözülmüştü. Merge commit'leri
yeniden yazma (reword/replay) yapmadı; **zaten ayrıklaşmış iki tarihi birleştirdi**.
Birleşim, rewrite-rekonsilasyonunun *tamamlanmış olduğu* bir tarihte gerçekleşti —
yani birleşim fazı "ayrık tarihlerin kompozisyonu", rekonsilasyon fazı ise ondan
önceydi. §1'in teşhisi doğru, sayısı bayat.

### 8.2 Byte katmanı — birleşmiş ağaç = bir taraf + minik delta

Gerçek merge'lerin bayt düzeyinde ürettiği tek değişiklik:

| Ölçüm | Sonuç |
|---|---|
| Merge A sonucu `32c1a44`, **dal ucundan** (`50d13b6`) | **6 dosya, +102 / −4** |
| Merge A sonucu `32c1a44`, main ucundan (`da58b14`) | 457 dosya, +105196 / −3422 |
| Merge B sonucu `008b1aa`, **main ucundan** (`32c1a44`) | **3 dosya, +118 / −3** |
| Merge B sonucu `008b1aa`, reword ucundan (`a24c4db`) | 355 dosya, +87491 / −1623 |
| `HEAD` (bugün), Merge B'den (`008b1aa`) | 12 dosya, +1182 / −22 (bu oturumun gate işleri) |
| Dal ucu ↔ main ucu (`50d13b6` vs `da58b14`) | 458 dosya, +3516 / **−105192** |

Son satır kritik: dal ucu, `origin/main`'in **105 bin satır üstünde** yani bariz
süpersettir. Dolayısıyla merge A'nın işi, süperseti bozmadan main'in minik
katkısını almaktı — ve madde 1 bunu doğrular: sonuç, dal ucundan **yalnız 6
dosya** ayrı. Merge B'de ise sonuç, main ucundan **yalnız 3 dosya** ayrı:

- **Merge A'daki 6 satır:** `determinism-trend.yml`, `README.md` (+1),
  `check_unit_tests.list` (+1), `test_coverage_report.py` (+7),
  `test_trend_record_pr_contract.py` (**yeni dosya**, +67),
  `determinism_trend.jsonl` (+1). İlk 5'i §7'deki 5 ortak dosyanın **dal
  tarafındaki kazanımı**; 6.'sı merge'in tek saf icadı.
- **Merge B'deki 3 dosya:** `verify.yml` (+4), `audit_live_ci_sync.py` (+68),
  `test_audit_live_ci_sync.py` (+49). `README.md` **yoktur** — yani Merge B'de
  changelog'u main tarafı kazandı (bkz. 8.3).

### 8.3 Semantik katman — changelog SHA-index ölçümü (dürüst sınırıyla)

`README.md`'de `commit/<sha>)` desenine uyan **farklı SHA** sayısı (ham
occurrence değil — aynı SHA birden çok satırda geçebilir: 389 vs 399):

| Rev | Rol | Farklı SHA-index |
|---|---|---|
| `50d13b6` | dal ucu (merge A sol) | 388 |
| `da58b14` | `origin/main` (merge A sağ) | 247 |
| `32c1a44` | **Merge A sonucu** | **389** |
| `a24c4db` | reword ucu (merge B sağ) | 307 |
| `008b1aa` | **Merge B sonucu** | **389** |
| `b72b303` / `HEAD` | bugün | 389 |

Yan farklar: Merge A **dal-yalnız 142 / main-yalnız 1**; Merge B
**reword-yalnız 3 / main-yalnız 95**. Sonuç anatomisi:

- **Merge A:** sonuç = dal(388) + main'in tek yeni satırı(1) = **389**. main'in
  eski satırları budanmış.
- **Merge B:** sonuç = main ile **birebir aynı küme** (`O == L`, 389 = 389).
  reword'ün 3 yalnız satırı budanmış; main'in 95 yalnız satırı aynen kalmış.

**Dürüst sınır (naif birleşim YANLIŞ olur):** her iki merge için de
"sonuç ⊇ (sol ∪ sağ)" testi **False**'tur. Sebep hata değil, tasarımdır: merge
sonrası `update_changelog_hook.sh` ölü/geçersiz SHA satırlarını **budar**.
Dolayısıyla merge changelog'u "iki tarafın kaba birleşimi" değil, **canlı
SHA'ların budanmış bir üst kümesidir**. Birlik kapsanmayan satırlar: Merge A'da
main'in tek yalnız satırı (yeniden üretilmiş haliyle değişti), Merge B'de
reword'ün 3 yalnız satırı. **Hiçbir sol-yalnız (dal/main-hedef) canlı satır
kaybolmadı** (A: 0, B: 0) — yani hedef tarafın changelog katkısı korunmuştur.
`HEAD ⊇ Merge B sonucu` = **True**, kayıp 0: Merge B'nin changelog'u bugüne dek
korunmuş.

**Üretim komutları (yeniden üretilebilirlik):**

```bash
# 1) Gerçek base + iki yönlü patch-dengi taraması
git merge-base 50d13b6 da58b14            # 6db5a2643…
git cherry da58b14 50d13b6 | uniq -c       #  145 +   → 0 patch-dengi
git cherry a24c4db 32c1a44 | uniq -c       #   98 +   → 0 patch-dengi

# 2) SHA'dan bağımsız yama-kimliği kümeleri ve kesişim
python3 - <<'PY'
import subprocess
def ids(rng):
    out = set()
    for s in subprocess.run(["git","rev-list","--no-merges",rng],
                            capture_output=True, text=True).stdout.split():
        d = subprocess.run(["git","show","--format=",s],
                           capture_output=True, text=True).stdout
        p = subprocess.run(["git","patch-id","--stable"], input=d,
                           capture_output=True, text=True).stdout
        if p.strip():
            out.add(p.split()[0])
    return out
big = ids("6db5a2643..50d13b6"); small = ids("6db5a2643..da58b14")
print(len(big), len(small), len(big & small))   # 145 3 0
PY

# 3) Byte deltası + changelog satır sayısı
git diff --shortstat 50d13b6 32c1a44       # 6 files, 102 insertions, 4 deletions
git diff --shortstat 32c1a44 008b1aa       # 3 files, 118 insertions, 3 deletions
git show 32c1a44:README.md | grep -o 'commit/[0-9a-f]\{7,40\})' | sort -u | wc -l   # 389
```

### 8.4 §1 ile çelişkinin çözümü

| Ölçüm | §1 (eski, bayat base) | Bu bölüm (gerçek merge noktaları) | Neden farklı |
|---|---|---|---|
| Dal commit'inde patch-dengi | **16** | **0** | 16, `7333a55` base'li simülasyonun add/add sandığı çiftlerdi; gerçek base'de taraflar ayrık |
| Çakışan dosya | **22** | **5** (A) / **4** (B) | 22, simülasyonun tahminiydi; gerçek merge'de dosyaların çoğu otomatik birleşti |
| Birleşim biçimi | `merge-tree` rc=1 (tahmin) | **2 ebeveynli gerçek merge commit'i** | Öneriye uygun: squash/rebase YOK |

**Karar (değişmez):** "MERGE — gerçek merge-commit, rebase/squash YOK" önerisi
geçerliliğini korur. Yalnız *gerekçe* netleşir: birleşimin zorluğu "16
patch-dengi + 22 add/add çakışması" değildi — o sayılar farklı bir base'e karşı
üretilmiş tahminlerdi. Gerçek tablo şudur: **rekonsilasyon (aynı işin farklı
SHA'larla tekilleştirilmesi) merge'den önce tamamlanmıştı**; merge commit'leri
yama-düzeyinde ayrık, byte-düzeyinde ise "süperset + minik delta" ilişkili iki
tarihi birleştirdi. Bu, merge'in doğru araç olduğunu §1'den **daha güçlü**
kanıtlar: yeniden yazılacak ortak yama yoktu, korunacak ayrık katkı vardı.
