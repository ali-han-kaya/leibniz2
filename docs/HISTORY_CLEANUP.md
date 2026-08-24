# History Temizliği Kaydı — Test Marker'ların Ezilmesi

Bu belge, repo history'sinden silinen **noise commit'lerin** tam kaydını ve gelecekte
tekrar üretilmelerini önleyen kuralları tutar. Amaç: `git log`'un her zaman **tek
anlamlı, denetlenebilir** bir teslim kaydı olması.

---

## 1. Temizlenen commit'ler

| Commit | Başlık | İçerik | Sorun |
|---|---|---|---|
| `d863977` | `test marker — tracked file` | `_calisma/CIKTI/TEST_MARKER.md` eklendi (1 satır: `# Test marker — should commit and pass hooks`) | İçerikle ilgisiz, test amaçlı |
| `991473d` | `remove test marker` | Aynı dosya silindi | Net-sıfır diff — hiçbir anlam taşımıyor |

**Net etki:** `git diff --stat 5d62685 991473d` → **boş**. İki commit birlikte
ekleme+silme yaptığından tek anlamlı sonuç **silmekti**.

## 2. Temizlik yöntemi

```bash
git rebase --onto 5d62685 991473d
```

- `5d62685` = "Add budget shield aggregation, file-type weighted estimate, and config defaults" (temiz taban)
- `991473d` = rebase edilecek son noise commit
- `--onto 5d62685 991473d`: `991473d..HEAD` aralığındaki commit'leri `5d62685`
  üzerine yeniden oynatır → `d863977` ve `991473d` **history'den düşer**.
- Sonuç: ağaç birebir aynı (net diff boş), history kısalır ve anlamlı hale gelir.

**Öncesi:** `9f72b0e → 3d114e5 → 5d62685 → d863977 → 991473d → (devam)`
**Sonrası:** `9f72b0e → 3d114e5 → 5d62685 → (temiz devam)` — 5d62685'ten sonra 52 anlamlı commit.

## 3. Adli iz (şeffaflık)

Silinen commit'ler **yerel obje veritabanında ve reflog'da hâlâ izlenebilir**:

```bash
git cat-file -t d863977   # → commit (unreachable objede duruyor)
git reflog | grep -E "d863977|991473d"
# HEAD@{73}: commit: test marker — tracked file
# HEAD@{72}: commit: remove test marker
```

Bunlar `git gc --prune=now` ile tamamen silinebilir, ancak **gerek yok**: belgelenmiş
olmaları yeterli. Branch history'si (push edilen) temizdir; obje artıkları yalnızca
yerel diskteki denetim izidir.

## 4. Önleme (gelecekteki noise commit'ler)

Üç katmanlı önlem aktif:

1. **`.gitmessage`** (kökte, `git config commit.template .gitmessage`):
   - Başlık formatı: `<kapsam>: <eylem>` (≤72 karakter) — ör. `verify.yml: ...`,
     `M0 §10.5: ...`, `docs/: ...`
   - Şablon, düzenlenmemiş placeholder'ı (`<kapsam>: <eylem>`) commit mesajında
     bırakır → commit-msg hook'u reddeder.
2. **`commit-msg` hook'u** (`_calisma/CIKTI/commit_msg_hook.sh`,
   `.pre-commit-config.yaml` → `commit-msg-style`):
   - `wip`, `smoke*`, `test marker*`, `test:*`, `fix typo*`, `minor fix*`, `asd`,
     `foo`, `lorem` vb. noise başlıkları **commit'i BLOKE EDER**.
   - `Merge ...` / `Revert ...` başlıklarına izin verir (git üretir).
   - Kurulum (tek komut): `bash _calisma/CIKTI/setup_commit_hooks.sh`
     (→ `git config commit.template .gitmessage` + `pre-commit install` +
     `pre-commit install --hook-type commit-msg` hepsini kurar)
   - **Not:** commit-msg stage'i CI `pre-commit run --all-files`'ta ÇALIŞMAZ
     (yalnızca yerel commit'lerde) — CI davranışı değişmez.
3. **`docs/PUBLISH_SCENARIO.md` AŞAMA 0** ön-kontrolü: `git log --oneline -5`'te
   test-marker olmamalı; `.gitmessage` kurulu olmalı.

## 5. İlgili kayıt

- `0fab281` "Update publish scenario: record test-marker squash" — temizliğin
  ilk belgelemesi (PUBLISH_SCENARIO rollback bölümü).
- Bu belge (`docs/HISTORY_CLEANUP.md`) — tam kayıt + önleme kuralları.

---

## 6. Preview-server legacy.label temizliği (--remove-legacy)

**Durum (2026-08-24):** `update_preview.sh` önceden **iki launchd profil**
üretiyordu:

| Profil | Label | Role | KeepAlive |
|---|---|---|---|
| Birincil | `com.freebuff.preview-leibniz2` | İstek karşılama (HTTP 8000) | `true` |
| **Legacy** | `com.freebuff.preview-server` | Yedek (`SuccessfulExit: false` → restart yok) | `false` |

İki-profilli tasarım, preview tab'ının detach/meşgul olma sorunuyla mücadele
için bir yedek daemon stratejisiydi. Ancak yarış koşullarına yol açtı:

- **Port yarışı:** İki profil de port 8000'de dinler → `launchctl bootout`
  (legacy) + `launchctl bootstrap` (birincil) sırasında `Address already in
  use` hatası
- **Restart döngüsü:** `KeepAlive: false` olan legacy `exit 0`'da durur,
  `KeepAlive: true` olan birincil crash'te restart eder; asimetrik davranış
  tanıyı zorlaştırır
- **plist-golden tutarsızlığı:** Golden dizini iki profil tutuyordu ama
  testler tek profili (leibniz2) mock'luyordu → `TestPlistOutSidecar` hatası

### Temizlik adımları

1. **`update_preview.sh`**: `PLIST_PROFILES`'ten legacy profil çıkarıldı;
   yalnızca `com.freebuff.preview-leibniz2` orada kaldı.
2. **`--remove-legacy` komutu** eklendi: var olan legacy profilini launchd'den
   söker + plist/şablon/log dosyalarını siler.
3. **`plist-golden/`**: `com.freebuff.preview-server.plist` golden dosyası
   tanıklık için korundu (silinmedi) — `--remove-legacy` komutunun neyi
   hedeflediğini belgeler.
4. **`test_plist_gate_exit.py`**: iki-profilli beklentiden tek-profilli
   gerçeğe güncellendi.

### Bellek (kaynak referansları)

| Konum | Ne |
|---|---|
| `_calisma/CIKTI/update_preview.sh` satır 462-501 | `LEGACY_LABEL`, `plist_remove_legacy()` tanımı |
| `_calisma/CIKTI/update_preview.sh` satır 595 | `--status` çıktısında legacy label referansı |
| `_calisma/CIKTI/plist-golden/com.freebuff.preview-server.plist` | Golden kopyası (tanıklık) |
| `_calisma/CIKTI/plist-golden/com.freebuff.preview-leibniz2.plist` | Güncel tek profil golden'ı |
| `_calisma/CIKTI/test_plist_gate_exit.py` `TestPlistOutSidecar` | Birim test (tek profil) |
| `_calisma/CIKTI/check_plist_drift.py` | Drift denetimi (K12) |

### Neden temizlik kaydına girdi

Bu bir "bug fix" değil, **mimari sadeleştirme**: iki-profilli tasarımın
çözmeye çalıştığı preview-server tab detach sorunu, launchd `KeepAlive` +
`start_preview.sh` bootout→bootstrap akışıyla kökten çözüldü; legacy yedek
profile artık ihtiyaç kalmadı. Temizlik; kod, test, golden ve dokümantasyon
dahil tam bir iz bırakılarak yapıldı.

## 7. Pre-existing CI hataları (known incidents)

CI pipeline'da belgelenmiş, kök nedeni bilinen ama her zaman tamamen
önlenemeyen kalıcı hatalar. Bu bölüm, bir CI run'ı kırmızı göründüğünde
"gerçek regresyon mu, bilinen flaky mi" sorusunu hızla cevaplamak içindir.

### 7.1 lineage_findings.json cascade failure (Ağustos 2026)

**Belirti:** `Delivery verification` job'u FAIL olduğunda, altındaki
`lineage_findings.json`, `k0_findings.json`, `klayers.json` sidecar'ları
**hiç üretilmez**. Bunun sonucunda `Upload lineage findings sidecar`
(`if-no-files-found: error`) FAIL olur; `reports` ve `reproducibility`
job'ları da bu sidecar'ları tükettiğinden zincirleme FAIL.

**Kök neden:** `verify.yml`'deki "Run full verification (K1-K14, single
entry point)" adımında `if: always()` yoktu. Birim testleri fail olduğunda
job'un kalan adımları skip edilir, `verify_delivery.py --full` hiç çalışmaz,
sidecar'lar yazılmaz. Alt job'lar (`if: always()` ile koşan) eksik dosyalarla
karşılaşır.

**Çözüm:** `0524f6a`: "Run full verification" adımına `if: always()`
eklendi; lineage-findings upload `if-no-files-found: error` → `warn`.

**Ne zaman görülür:** Yeni bir test regresyonu olduğunda birim testler fail
olur; full verification buna rağmen koşar (sidecar üretir). Yine de birim
test hatası giderilene kadar job FAIL kalır — ama cascade önlenir.

### 7.2 OpenLibrary geçici timeout UNVERIFIED spike'ları (V5aa)

**Belirti:** CI push run'larında `refs-online` artifact'ı bazen 58/61 PASS
(3 UNVERIFIED) gösterir. `workflow_dispatch` ile taze koşuda 61/61 PASS.

**Kök neden:** OpenLibrary API'si rate-limit ve ağ zaman aşımına hassastır.
`urllib` timeout'ları geçicidir — aynı sorgu 10 saniye sonra başarılı olur.

**Mevcut azaltma:** `verify_delivery.py`'de `_ol_retry` dış katman retry
(3s bekle, bir kez daha dene). 429/0-sonuç kalıcı olarak geçirilir, timeout/
connection reset tekrarlanır. `REFERANS_KANIT_DENETIMI.md` V5aa'da belgeli.

**Ne zaman görülür:** Ayda birkaç run'da, özellikle yoğun saatlerde.
`workflow_dispatch` ile temiz run tetiklenerek 61/61 teyit edilebilir.

### 7.3 test_combined_scenario_shares_comment_list (K16 battery flaky)

**Belirti:** `test_github_scripts_battery.TestCallRecords.
test_combined_scenario_shares_comment_list` CI'da bazen `TypeError: Cannot
read properties of undefined` veya record-call uyuşmazlığı ile FAIL olur.
Yerelde (`_calisma/.venv_z3/bin/python3 -m unittest`) **her zaman PASS**.

**Kök neden:** `github_scripts_battery.py` Node.js alt süreçlerini `node -e`
ile çalıştırır. CI runner'ında Node.js sürümü, `require()` önbelleği veya
async callback sıralaması yerelden farklı olabilir. Mock `context.repo`
nesnesinin serileştirilmesi/parsing'i CI ortamında ek alanlar içerebilir.

**Ne zaman görülür:** Seyrek (ayda 1-2 run). Yerelde **her zaman yeşil**.
Henüz bir düzeltme yok — izole edilmesi zor (CI-only).

### 7.4 pre-commit exit 127 (binary PATH'te yok)

**Belirti:** `Run pre-commit (advisory, all files, show diff on failure)`
adımı `exit code 127` (command not found) ile FAIL olur. Job'u patlatmaz
(`continue-on-error: true`).

**Kök neden:** Pre-commit, CI runner'da `pip install pre-commit` ile
kurulur. Kurulum adımının `if: always()` olmaması veya PATH güncellemesinin
aynı adımda etkili olmaması nedeniyle bazen binary bulunamaz.

**Mevcut azaltma:** Advisory kapı (`continue-on-error: true`). Job FAIL
etmez, yalnızca log'da görünür. Bir sonraki run'da genellikle düzelir.

### 7.5 Branch protection required check sayısı (9→6, Ağustos 2026)

**Güncel durum (2026-08-24): 6 required check.** 3 flaky kapı kaldırıldı:

| Kaldırılan | Sebep |
|---|---|
| Online verification trend (refs-online across runs) | OL geçici timeout → UNVERIFIED spike (V5aa) |
| Reproducibility bundle | lineage_findings.json cascade bağımlı (§7.1) |
| Static markdown reports (incl. pre-commit findings) | Aynı cascade bağımlılık |

**Kalan 6 (stabil):**
1. Action runtime check (node24)
2. Budget shield (aggregated)
3. Config drift check (gen_config + diff-on-drift)
4. Repack determinism + verify (sidecar sync)
5. Delivery verification — K1-K14 (single entry point)
6. Pre-commit P0 label gate

**Not:** `status_checks.py --gh` hâlâ 12-check workflow listesiyle
karşılaştırır; "GitHub'da yok" uyarıları bilinçli eksiltmedir. Ci-simulate,
commit-msg-gate, config-sync de hiç eklenmemişti — drift yok.

**Belirti (beklenen davranış):** `git push origin main` →
`GH006: Protected branch update failed — 6 of 6 required status checks
are expected`.

**Doğru akış:** PR aç → CI koşsun → 6 check yeşil → `gh pr merge`.
Admin bypass: `gh pr merge --admin` ile koruma atlanabilir, ancak
`enforce_admins: true` ise önce toggle gerekir (`toggle_enforce` dansı).

---

### Tanı tablosu (hızlı bakış)

| Belirti | Hata mı? | Ne yapmalı |
|---|---|---|
| lineage_findings.json eksik + cascade FAIL | ✅ hata (düzeltildi: `0524f6a`) | `if: always()` var mı kontrol et |
| refs-online 58/61 UNVERIFIED | ⚠️ flaky (V5aa) | `workflow_dispatch` ile taze run |
| test_combined_scenario_shares_comment_list FAIL | ⚠️ flaky (CI-only) | Yerelde yeşilse güven, yeniden push |
| pre-commit exit 127 | ⚠️ advisory (atlanır) | Görmezden gel, bir sonraki run'da düzelir |
| `gh push origin main` red | ℹ️ beklenen | PR aç, CI bekle, merge et |
