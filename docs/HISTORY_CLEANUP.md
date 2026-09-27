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
| `_calisma/CIKTI/plist-golden/com.freebuff.preview-server.plist` | Golden kopyası (tanıklık) |
| `_calisma/CIKTI/plist-golden/com.freebuff.preview-leibniz2.plist` | Güncel tek profil golden'ı |
| `_calisma/CIKTI/test_plist_gate_exit.py` `TestPlistOutSidecar` | Birim test (tek profil) |
| `_calisma/CIKTI/check_plist_drift.py` | Drift denetimi (K12) |

**Güncelleme (2026-08-26):** `--remove-legacy` komutu **kaldırıldı** —
gerçek makinedeki legacy plist artık `PLIST_PROFILES` içinde yönetilen bir
profildir (`--plist-force` üretir, `--plist-check` denetler). Bir kerelik
taşıma amacıyla eklenen `plist_remove_legacy()` + `LEGACY_LABEL`/
`LEGACY_LOGNAME` değişkenleri ve `TestRemoveLegacy` test sınıfı (5 test)
repo'dan çıkarıldı; `--status` çıktısındaki ayrı "legacy (PLIST_PROFILES
dışı)" bloğu da silindi (legacy artık ana döngüde yönetilen profil olarak
görünür).

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

**Çözüm (1. katman, `0524f6a`):** "Run full verification" adımına
`if: always()` eklendi; lineage-findings upload `if-no-files-found: error`
→ `warn`.

**Kök çözüm (2. katman):** `verify_delivery.py` artık `--lineage-out`
sidecar'ını **HER ZAMAN** yazar — `--check-lineage` koşulmadıysa dürüst
`{"ok": false, "detail": "check_lineage koşulmadı"}` kaydı (yanlış PASS
yok, eksik dosya yok). Ayrıca verify.yml'deki "Guarantee summary sidecars
exist (anti-cascade)" adımı `k0_findings.json` / `klayers.json` /
`budget_verify.json` için de placeholder üretir — upload adımları
(`if-no-files-found: error` dahil) ASLA eksik dosyayla karşılaşmaz,
reports/reproducibility job'larına cascade bulaşmaz. Regresyon kapısı:
`test_lineage_sidecar_guarantee.py`.

**Ne zaman görülür:** Artık görülmez — sidecar varlığı garantilidir.
Yeni bir test regresyonu olduğunda birim testler fail olur; full
verification buna rağmen koşar ve sidecar'ları üretir. Yine de birim test
hatası giderilene kadar job FAIL kalır — ama cascade önlenir.

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
| lineage_findings.json eksik + cascade FAIL | ✅ kökten düzeltildi (`0524f6a` + anti-cascade garantisi) | sidecar garantisi + placeholder adımı yerinde mi |
| refs-online 58/61 UNVERIFIED | ⚠️ flaky (V5aa) | `workflow_dispatch` ile taze run |
| test_combined_scenario_shares_comment_list FAIL | ⚠️ flaky (CI-only) | Yerelde yeşilse güven, yeniden push |
| pre-commit exit 127 | ⚠️ advisory (atlanır) | Görmezden gel, bir sonraki run'da düzelir |
| `gh push origin main` red | ℹ️ beklenen | PR aç, CI bekle, merge et |

---

## 8. Ref envanteri (stale inventory) — 2026-09-12

History rewrite'ları (reword + force-push) ve taşınan worktree'lerden kalan
ulaşılamaz nesnelerin sayımı. Amaç: `git gc` öncesi/sonrası durumu tek yerde
kayıtlı tutmak — sonraki temizlik turu bu sayılarla karşılaştırılır.

**Yöntem (yeniden üretilebilir):**

```bash
git fsck --no-reflogs --dangling        # dangling commit/blob/tree sayımı
git worktree list; git branch -a; git stash list
git count-objects -vH; du -sh .git
git reflog expire --expire-unreachable=now --all   # yalnız ULAŞILAMAZ girdiler
git gc --prune=now
```

`--expire-unreachable` bilinçli: erişilebilir commit'lerin reflog geçmişi
(undo ağı) korunur, yalnız ulaşılamaz girdiler düşer.

| Ölçüm | Önce | Sonra |
|---|---|---|
| dangling commit | 159 | **0** |
| dangling blob | 35 | **0** |
| dangling tree | (tam sayım saklanmadı) | **0** |
| loose object (boyut) | 6826 (116.30 MiB) | 0 (0 B) |
| pack (boyut) | 2 pack (6.97 MiB) | 1 pack (6.88 MiB) |
| `.git` dizin boyutu | 128 MiB | **11 MiB** |
| reflog girdisi | 178 | 118 |

### 8.1 Kaynaklanan içerik kaybı doğrulaması

`gc` öncesi ulaşılamaz nesnelerdeki **120 benzersiz blob** (6.51 MiB) tek tek
çıkarıldı. Bunların dağıldığı 64 yolun:

- **40'ı HEAD'de hâlâ var olan dosyaların eski revizyonları** (rewrite artığı):
  README 18, PUBLISH_SCENARIO 12, verify.yml 8, check_unit_tests.list 7,
  eski teslim zip'leri + sha256 sidecar'ları, eski PDF/qpdf kayıtları.
- **23'ü artık gitignore'da** (`.gitignore` satır 5: `docs/ci_simulate/`) olan
  CI-simülasyon çıktıları — koşularak yeniden üretilir.
- **1'i** `_calisma/CIKTI/test-hook-dummy.txt` (6 bayt, hook denemesi artığı).

**Hedefli doğrulama — kurtarılan iki zincir:**
`.github/workflows/docker-security.yml`, `Dockerfile` ve `design-system/**`
yollarında **benzersiz blob sayısı 0**. İki bağımsız yöntemle doğrulandı:
(1) bu yollardaki her blob refs'ten erişilebilir (blob-hash kümesi testi),
(2) ilgili dangling commit'lerin (`52c87cb`, `031f7f4`, `d4f095e`, `4ec2706`)
bu yollardaki içeriği HEAD'de mevcut (yol-yol `rev-parse` karşılaştırması).

**Kanıt arşivi (silmeden önce alındı):**
`/tmp/leibniz2-dangling-salvage-20260912.tar.gz` — 3.7 MiB, sha256
`4ae0a92d16d51b39e700ca5193c928df694be5bf1f18a4b3f7db56fdf8731d2f`.
İçerik: 120 blob + `MANIFEST.json` (blob → yol → kaynak dangling commit →
sha256 → boyut). `/tmp` kalıcı değildir; saklanacaksa repoya/arşive taşınmalı.

### 8.2 Kalan envanter (orphan-ref süpürmesi sonrası)

| Öğe | Adet | Durum |
|---|---|---|
| `backup/*` ref'leri | 6 → 1 | Yalnız `backup/orphan-pre-reword-33e9b8a` kaldı: **benzersiz kurtarılabilir içerik** taşıyor (§8.4) |
| stash | 2 → 1 | `stash@{0}` korundu (`refs/stash` = `7d58b5d`; reflog girdisi `git stash store` ile geri yazıldı). `stash@{1}` ("stale-audit wiring") yalnız reflog'la ayakta kalıyordu: `--expire-unreachable` onu düşürdü, commit'i prune edildi — **içeriği arşivde** (`d7343f0`: 3 benzersiz blob) |
| harici worktree | 2 | `/private/tmp/followup` (`feat/plist-info-line-followup`), `/private/tmp/wt224` (detached `224dcd7`) |
| yerel-only branch | 2 → 1 | `pr/bf506c0` kaldı: 84 benzersiz yol taşıyan ayrı bir eski hat (ayrıca `origin/pr/bf506c0`'da mevcut). `feat/compact-json`, `rewrite-preview-test` silindi (0 ahead) |

### 8.3 Yan etki: `--expire-unreachable` stash reflog'unu da kapsar

`refs/stash` bir reflog-ref'idir; `--expire-unreachable=now --all` bu reflog'u da
işler, dolayısıyla **@{0} dışındaki stash girdileri düşer** (bu turda stash
listesi boşaldı). @{0}'ın commit'i `refs/stash` ref korumasında olduğu için
nesnesi duruyordu; liste `git stash store 7d58b5d` ile aynı sha'ya geri yazıldı.
Bir sonraki temizlikte stash'ler korunacaksa refine yalnız ref'ler üzerinde
koşturulmalı (`git reflog expire --expire-unreachable=now refs/heads/<b>` gibi)
veya stash'ler önce `git stash push` ile yeniden yazılmalı.

### 8.4 Orphan-ref süpürmesi — 2026-09-12

Kriter: **ref'i sil, ancak ve ancak hiçbir yerde bulunmayan kurtarılabilir içerik
yoksa.** Ölçüm, `git rev-list --objects <ref> --not main feat/plist-info-line
feat/plist-info-line-followup` ile her ref'in spine'a göre benzersiz nesnelerini
çıkarıp yol-yol HEAD ile karşılaştırarak yapıldı.

**Silinen 9 ref — üç sınıf:**

| Ref | Sınıf | Gerekçe |
|---|---|---|
| `backup/orig-091635c-73chars` | yalnız commit | Reword öncesi aynı ağaç; 4 commit, **0 benzersiz yol** |
| `backup/orig-b5e74dc-91chars` | yalnız commit | Aynı; 1 commit, 0 benzersiz yol |
| `backup/reword-091635c-56chars` | yalnız commit | Aynı; 4 commit, 0 benzersiz yol |
| `backup/reword-b5e74dc-57chars` | yalnız commit | Aynı; 1 commit, 0 benzersiz yol |
| `backup/self-loop-a345284` | tamamen birleşik | Spine'a göre **0 commit ahead** |
| `feat/compact-json` | tamamen birleşik | 0 commit ahead |
| `rewrite-preview-test` | tamamen birleşik | 0 commit ahead |
| `refs/original/HEAD` | eskimiş taslak | 12 commit; benzersiz blob'lar yalnız `preview_server.py` + `test_preview_server.py`'nin **eski** hali. HEAD `_write_atomic`/`SSE_POLL_TIMEOUT`/`OVERRIDE_TREND_PATH` içeriyor, bu ref içermiyor; test dosyası 90 KB vs 72 KB |
| `feat/compact-json-patch` | eskimiş taslak | Aynı iki dosyanın daha eski hali; ayrıca `origin/feat/compact-json-patch`'te duruyor |

`refs/original/HEAD` ve `feat/compact-json-patch`'in "HEAD'de yok" görünen 13
yolu `_calisma/slides_z3/**` idi; bunlar `_calisma/CIKTI/slides_z3/**`'a
**taşınmış** ve 13 dosyanın **13'ünde blob hash'i birebir aynı** — kayıp yok.

**Korunan ref ve gerekçesi:** `backup/orphan-pre-reword-33e9b8a` (`33e9b8a`) —
tek başına benzersiz içerik taşıyan ref:

- `_calisma/CIKTI/update_preview.sh` (`43adbac8`, +27 satır): `--no-mirror` /
  `--no-html` bayraklarını `--bootstrap`'dan **önce** verildiğinde de işleyen
  üst-seviye `case` dalı. HEAD bu sırayı işlemiyor (`bootstrap_all "${@:2}"`
  yalnız sonraki argümanları geçirir; `--no-mirror` doğrudan `${1:-build}` olur
  ve `ERR bilinmeyen mod` + `exit 2` ile düşer).
- `_calisma/CIKTI/test_check_bootstrap_start_smoke.py` (`8c895433`, +26 satır):
  `test_leading_flags_before_bootstrap` — bu sıra için regresyon testi.

İki blob da HEAD'de **ve** çalışma ağacında yok (çalışma ağacı hash'leri
`cbf8adc6` / `76cee799`, yani HEAD ile aynı). Bu yüzden ref silinmedi.

**Geri alma ağı:** silinen tüm tip SHA'ları
`/tmp/leibniz2-refs-sweep-manifest-20260912.txt` (sha256 `3687d826…`) içinde;
nesneler `gc --prune` koşmadığı için hâlâ nesne veritabanında. Geri alma:
`git branch <ad> <sha>`.

**Not:** Job/artifact doc-senkron kapıları (`test_doc_job_sync`,
`test_doc_artifact_sync`, `check_workflow_artifact_docs`) yalnız
`docs/PUBLISH_SCENARIO.md`'yi ayrıştırır; bu bölüm onları etkilemez.
