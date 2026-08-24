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
