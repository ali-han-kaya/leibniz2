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

1. **Merge commit'i local'de oluştur, push etmeden önce tam doğrula:**
   `pre-commit run --all-files` + `check_unit_tests_hook.sh` (130 dosya) +
   `test_coverage_report.py --check` + `lint_actionlint.sh` +
   `sync_check_unit_tests.py --check`.
2. **PDF bütünlüğü:** `_calisma/REVIEW/*.sha256` merge sonrası `shasum -c`.
3. **Changelog:** README tabloları merge'de iki kopya satır üretebilir →
   `update_changelog_hook.sh` çalıştırıp stale-row pruning ile tekilleştir.
4. **CI kanıtı:** merge push'ı sonrası 3 workflow'un koşumu izlenir;
   docker-security Trivy 0 bulgu + verify-delivery 27 job success beklentisi.
5. **Geri alınabilirlik:** merge-commit tek `git revert -m 1` ile geri alınır.

## 6. Karar

**MERGE (3-way, merge-commit)** — koşullar:
- [ ] 22 dosya yukarıdaki tabloya göre çözülür (main'in 5 bağımsız düzeltmesi
  `16d4e06`, `f70779c`, `d37d6da`, `ba088ad`, `f8a1fa0` korunur).
- [ ] Yerel doğrulama zinciri (§5.1) yeşil.
- [ ] Merge push'ı sonrası 3/3 workflow success kanıtı alınır.
- Commit başlığı önerisi: `merge: land reword-working (verify chain RC, CI
  debt fixes, determinism evidence) preserving main-side independent fixes`

## 7. Uygulama doğrulaması (denetim: 2026-10-12)

Karar (2026-09-17) ile **uygulanan çakışma çözümü** karşılaştırıldı. Ölçülen
merge commit'i: `7c09956` — `Merge remote-tracking branch 'origin/main' into
reword-working`, 2026-09-17; PR #50 dalına push edilen **tek** merge commit'i.
Ebeveynler `352a615` (dal) ve `a4aa981` (origin/main); commit mesajı 22 çakışan
dosyayı listeler. Ölçüm yeniden koşturulabilir:

```bash
M=7c09956; A=$(git rev-parse "$M^1"); B=$(git rev-parse "$M^2")
git log -1 --format=%B "$M"      # çakışan 22 dosyanın listesi
# her çakışan yol için üç blob'u karşılaştır: A:$p, B:$p, M:$p (ve main:$p)
#   A == M ve B != M  -> dal tarafı kazandı
#   B == M ve A != M  -> main tarafı kazandı
#   A != M ve B != M  -> elle birleştirildi
```

### 7.1 Sınıflandırma

| Sınıf | Yol | §4 kararı | Uyum |
|---|---|---|---|
| Dal tarafı kazandı (`A == M`) | 11 | "dal" / "3-way" | ✅ (main'in pcre2 yaması dalda eşdeğeriyle; `actionlint_gate.py`'da dalın fail-closed severity fix'i main'in fail-open sürümünün önünde; plist golden'da dalın drift'siz sürümü) |
| Main tarafı kazandı (`B == M`) | 9 | "main" / "3-way" | ✅ (`check_review_freshness.py` + testi, `test_check_bootstrap_start_smoke.py`, `.dockerignore`; `verify_mcp/*` farkı yalnız K21↔K22 doküman satırı) |
| Elle birleştirildi | 2 | "3-way birleşim" | ✅ (`update_preview.sh` arg-order + dal dokunuşları; `README.md`) |

Bugün hâlâ dal blob'unu taşıyan 5 yol (`main == M != B`) var — bu, §4'ün
"dal" kararlarının sonradan sessizce geri alınmadığını gösterir.

### 7.2 Tek sapma — ve neden moot

§2/§4 REVIEW PDF çifti için "dal sürümü kalsın" demişti; uygulanan çözüm
main'in çiftini tuttu (`_calisma/REVIEW/Stoic_Hume_Review_Compilation_2026-08-17.pdf`
ve `.sha256`: `B == M`). Bugün **moot**: main'de `shasum -a 256 -c` OK,
dosya+sidecar tutarlı ve ikisi de sonraki inişlerde yeniden üretildi (bugünkü
blob'lar `81046b2` / `c8b941c`).

### 7.3 Sonuç

Denetimde **onarılacak bir kayıp bulunmadı**: 22 çakışmanın dosya-bazlı
çözümü §4 tablosuyla örtüşüyor, tek karar sapması (PDF çifti) doğrulanabilir
şekilde aşılmış durumda. Kayıt amacı, main'e giren bu çakışma çözümünü karar
dokümanıyla **kanıtla** bağlamaktır — yeniden ölçüm için §7'nin başındaki
komutlar yeterlidir.
