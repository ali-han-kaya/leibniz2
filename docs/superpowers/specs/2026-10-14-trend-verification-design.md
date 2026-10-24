# Trend Doğrulama Tasarımı (2026-10-14)

**Status:** Tasarım kaydı — mevcut zincirin tanımı. Uygulama kodu eklenmedi;
bu belge yalnız bugünkü davranışı, değişmezleri ve sınırları kaydeder.

> **Kapsam ölçümü:** Bu belge `_calisma/CIKTI/` altındaki trend üreticileri +
> `.github/workflows/{determinism-trend,battery-trend,verify}.yml` kapıları +
> `docs/*_trend/` veri dosyaları + `determinism_trend_badge.py`/`api/*.py`
> tüketicileri kapsar. `apps/trend-db/**` (Prisma) ve `test_trend_db_*`
> sözleşmeleri ayrı bir depolama sözleşmesidir; burada derinleştirilmedi.

## 1. Amaç

Tek bir koşumun "PASS"i tek başına determinizm kanıtı değildir: aynı kaynağın
farklı oturumlarda aynı çıktıyı üretmesi **zaman içinde** gösterilmelidir.
Bu tasarım, ölçümleri satır-satır biriktirip ölçümün kendisini fail-closed
kapılarla doğrular: sapma (motor determinizmi, referans kapsamı, süre/bütçe,
batarya süresi) ilk haftada görünür olsun.

Temel ilke: **ölçülmemiş PASS yok.** Ölçüm kanıtlanamıyorsa (rapor yok, kanıt
satırı yok, kırmızı koşum) kayıt yazılmaz ve kapı kırmızı olur.

## 2. Ortak desen (dört aşama)

| Aşama | Ne yapar | Tipik kanıt |
|---|---|---|
| **Kaydet** (`--update`) | Ölçümü doğrular, `docs/*_trend/*.jsonl`'a **tek satır ekler** (asla geri yazmaz) | `OK: ölçüm eklendi` + satır özeti |
| **Doğrula** (`--check`) | Değişmezleri denetler; ihlalde rc=1, stderr'e gerekçe | `FAIL: trend değişmezi ihlali: …` |
| **Yayınla** | Rozet + SVG + JSON + run summary; özet tek kaynaktan taşınır | `docs/…/*.jsonl` son satırı |
| **Denetle** (audit) | Trend satırını **kaynak artifact'la** karşılaştırır (sahte/bayat satır avı) | `audit_refs_trend.json` |

**Kayıt yolu (bot):** ölçüm main'e doğrudan push edilmez — branch protection
(GH006) bare push'u reddeder. Desen: bot dalı → `--force` push → PR →
`gh pr merge --auto`. PR oluşturma izni kapalıysa ölçüm bot dalında güvende
kalır ve adım görünür yönergeyle biter (kayıp yok; koşum kanıtları
`35580855610` ve `35590265995` workflow yorumlarında kayıtlı).

**Kadans ve çakışma:** iki scheduled hat farklı dakikaya sabitlenmiştir
(determinism `17 3 * * 1`, battery `41 4 * * 1`; komşular 03:43/03:53/04:07) —
`test_gated_schedules.py`'deki aynı-cron yasağı (K7) ihlal edilmez. Her iki
workflow'da `concurrency: cancel-in-progress` → trend kaydı bir-bir yazılır.

## 3. Trend hatları

| Hat | Üretici | Veri / çıktı | Nerede koşar | Karakter |
|---|---|---|---|---|
| **determinism** | `record_determinism_trend.py` | `docs/determinism_trend/determinism_trend.jsonl` | `determinism-trend.yml` (haftalık + `workflow_dispatch`) | **fail-closed kapı** |
| **determinism (canvas)** | `canvas_determinism_test.sh` | `docs/ci_simulate/canvas_determinism/…` (ignore'lu kanıt) | aynı workflow, `canvas-determinism` job | tectonic-only, sabit SDE |
| **battery** | `record_battery_trend.py` | `docs/battery_trend/battery_trend.jsonl` | `battery-trend.yml` (haftalık) | **fail-closed kapı** |
| **refs** | `refs_trend.py` | `refs-trend/{refs-trend.md,refs-trend.json}` | `verify.yml` → `refs-trend` job (her push) | tablo **required**, veri advisory |
| **refs denetimi** | `audit_refs_trend.py` | `audit_refs_trend.json` | `verify.yml` → `audit-refs-trend` job | **advisory** (rc=2 tolere) |
| **override** | `override_trend.py` | `override-trend/{md,json}` | `verify.yml` → `override-trend` job | **advisory** |
| **ci (§9)** | `ci_stats.py` / `gen_ci_trend.py` | `docs/PRE_PUSH_DENETIM_RAPORU.md` §9 bloğu (satır 353) | **bağlı değil** — docstring'in iddia ettiği hook/job repoda yok (bkz. §9) | elle koşulur; `--strict` ile fail-closed |

`determinism-trend.yml` ayrıca motoru **tedarik zinciri piniyle** kurar:
tectonic `0.17.0` + sha256 digest. Gerekçe kayıtta yazılı — farklı motor
sürümü trendi karşılaştırılamaz kılar. Canvas job'ı aynı sürüm+digest'i
kullanır; `test_determinism_trend_canvas` iki job'ın pinini karşılıklı sabitler.

## 4. Değişmez (invariant) sözleşmesi

### 4.1 determinism — `--check`

| # | Değişmez | Kural | İhlal sonucu |
|---|---|---|---|
| 1 | **Gençlik** | son kayıt < 7 gün | FAIL ("haftalık koşum atlanmış") |
| 2 | **Uzlaşma** | son 5 kayıt içinde *aynı* `source_sha256` + *aynı* `platform` + *aynı* `passes` ise kanonik hash'ler değişmemeli | FAIL (`…_canonical_sha256 … değişti`) |
| 3 | **Platform kapsamı** | `2026-09-17` cutoff'undan sonra en az bir `darwin` + bir `linux` kaydı | FAIL ("platform kapsamı eksik") |

Bilinçli olarak **ihlal sayılmayan** iki durum (ikisi de stderr'e not düşer):

- **Çapraz-platform farkı:** farklı paket setleri (Homebrew ↔ Debian
  `texlive`+`cm-super`) farklı kanonik hash üretebilir; `_cross_platform_note`
  yalnızca bilgilendirir. Gerekçe/ölçüm: `docs/PDF_DETERMINISM_EXPLAINED.md` §6.
- **Geçiş modu değişimi:** 1-geçiş ve 3-geçiş kanonikleri tanım gereği
  farklıdır; mod değişimi bilinçli re-baseline'dır (`_mode_note`), uzlaşma
  karşılaştırması aynı mod içinde yapılır.

Fail-closed ayrıntılar: kanonik alanlar yoksa ham hash'e yalnız
`residual=none` kanıtıyla düşülür; çok-geçiş raporu hizalama kanıtı
(`*_rerun_left=0`) taşımıyorsa **ölçüm kaydedilmez**; hash 64-hex değilse,
`verdict != PASS` ise veya rapor içi iki kanonik koşum zıtsa `--update` rc=1.

### 4.2 battery — `--check`

| # | Değişmez | Kural |
|---|---|---|
| 1 | Gençlik | son kayıt < 7 gün |
| 2 | Yapısal | her satırda `0 < duration_s <= 7200` ve `tests >= 1` |
| 3 | Kapsam (scope) | son satırın `scope`'u kanonik keşif komutuyla **birebir** aynı |
| 4 | Bozukluk | bozuk JSONL / boş trend = FAIL (sessiz PASS yok) |

Bilgilendirici notlar (FAIL değil): süre medyanın 2× üzerindeyse ve test
sayısı önceki kayda göre değiştiyse not düşülür — makine yükü regresyon
sayılmaz, ama trendde görünür.

### 4.3 refs — tablo zorunlu, veri advisory

`refs-trend` job'ında üretim adımı `continue-on-error`, ama **sonuç adımı
fail-closed**: `refs-trend/refs-trend.md` yoksa job kırmızı
("trend tablosuz required kapı PASS edemez"). Tablonun içeriği advisory'dir.

### 4.4 refs denetimi — trend satırı ↔ kaynak artifact

| Eksen | Karşılaştırma |
|---|---|
| Kaynak varlığı | trend satırının `run_id`'si için `refs-online` artifact'ı var mı |
| Sayı eşleşmesi | `total_online` / `verified` / `unverified` / `mismatch` birebir |
| Kaynak dağılımı | `by_source` sözlüğü birebir + `{hathitrust, archive, perseus}` bulunmalı |
| Kapsam | kaynak artifact'ların run'ları trendde eksiksiz mi (yoksa trend bayat) |

Exit semantiği: `0` tutarlı, `1` uyumsuzluk (fail-closed), `2` çalışma hatası
(trend json yok / API çekilemedi — CI'da advisory tolere eder). Denetçi,
üreticinin fetch/parse fonksiyonlarını **yeniden kullanır**: "üretici ile
denetçi farklı şey okuyor" drift'i yapısal olarak kapanır.

### 4.5 refs — eşik uyarıları ve bayatlık

- `DURATION_WARN_S = 300`, `BUDGET_WARN_USD = 30` (kaynak: `verify_delivery.config`)
- Z3 FAIL varsa uyarı satırı üretilir (`z3_passed`/`z3_total` farkı)
- `detect_stale_artifacts(window=3)`: son 3 run'da `refs-online` artifact'ı
  olmayan run'lar `⚠️` bloğu olarak tabloya yazılır (advisory, rc'yi değiştirmez)

## 5. Veri sözleşmeleri

### 5.1 `determinism_trend.jsonl` (satır = ölçüm, yalnız eklenir)

```json
{"date":"YYYY-MM-DD","source_mtime":<int>,"source_sha256":"<64 hex>",
 "tectonic_bin":"…","texlive_bin":"…",
 "tectonic_canonical_sha256":"<64 hex>","texlive_canonical_sha256":"<64 hex>",
 "sde":<int>,"platform":"darwin|linux","gate":"PASS","passes":<int>}
```

`passes` alanı olmayan eski satırlar **1** kabul edilir. Güncellik
`source_mtime` + `source_sha256` ile izlenir; kaynak değişmediyse hash
değişmemelidir (değişmez 2).

### 5.2 `battery_trend.jsonl`

```json
{"date":"YYYY-MM-DD","duration_s":<float>,"tests":<int>,
 "platform":"darwin|linux","python":"3.x.y","gate":"PASS",
 "scope":"unittest discover -s _calisma/CIKTI -p test_*.py"}
```

Kapsam **tek kaynak**: battery-trend workflow'u ile `verify.yml`'deki
"Run CIKTI unit tests" adımı aynı keşif komutunu koşar; test iki dosyayı
karşılıklı pinler (kapsam kayması = karşılaştırılamaz trend).

### 5.3 `refs-trend.json`

`{generated, repo, rows[], totals, duration_budget{run_count, rows[], summary{duration_s,budget_usd}, warnings{duration_violations,budget_violations,total_runs,violations[]}}}`.
`duration_budget` bölümünün JSON şeması **tek kaynak**: üretici saf fonksiyon
(`build_duration_budget`), denetim aynı girdiden yeniden üretip birebir
karşılaştırır (DB-STRUCT + DB-CONSIST). `rows` dolu iken bölümün yokluğu
FAIL'dir (üretici drift'i).

### 5.4 `override-trend.json`

`{generated, repo, run_count, warning_run_count, rows[{date,run_id,artifact_id,warning,override_count,override_keys[],override_detail}], override_counts{count,min,max,avg}}`
— kaynak: `budget` artifact'larındaki `cli_overrides_version.json`.

## 6. Kapı ve exit-code semantiği

| Bileşen | Başarı | Fail-closed | Çalışma hatası | CI'da sınıf |
|---|---|---|---|---|
| `record_determinism_trend --update` | 0 | 1 (kanıtlanamayan ölçüm) | — | required (kendi workflow'unda) |
| `record_determinism_trend --check` | 0 | 1 (değişmez ihlali) | 1 | required |
| `record_battery_trend --update/--check` | 0 | 1 | 1 | required |
| `refs_trend.py` | 0 | — | 1 (API) | üretim adımı advisory, **tablo varlığı required** |
| `audit_refs_trend.py` | 0 | 1 (uyumsuzluk) | 2 | advisory |
| `override_trend.py` | 0 | 1 (API hatası) | 1 | advisory |
| `gen_ci_trend.py` | 0 | 1 yalnız `--strict` | 2 (kullanım) | **bağlı değil** (hook/job yok, bkz. §9) |

Tüm trend kapıları **CI içindedir**; pre-commit zincirine bağlı trend kapısı
yoktur (pre-commit'te yalnız audit-refs-trend *reproduce* akışının E2E
doğrulaması vardır). Yerelde doğrulamak isteyen `--check` modlarını elle
koşar; `--update` bataryayı yeniden koştuğu için dakikalar sürer.

## 7. Tüketiciler (görünürlük yüzeyi)

- **Rozet + grafik:** `determinism_trend_badge.py` → `determinism-trend.svg`
  (nokta = ölçüm, yeşil çizgi = ardışık aynı-hash zinciri; tooltip tarih +
  platform + hash öneki + gate) ve `determinism-trend.json`
  (`{generated, badge, rows[]}`). Rozet sınıfları: `ok` / `warn` / `unknown`.
  Çıktı dizini (`determinism-trend/`) **izlenmez** — üretilmiş artefakttır.
- **JS ikizi:** `preview.js` içindeki `determinismTrendBadge()` Python
  karşılığıyla birebir senkron tutulur (aynı metin/sınıf sözleşmesi).
- **Sunucu yüzeyi:** `preview_server.py` → `/api/determinism-trend` (route +
  handler + `DETERMINISM_TREND_PATH` init) ve `/api/trend`,
  `api/trend.py` / `api/determinism-trend.py` (Vercel) aynı adaptörden
  beslenir. `--update-preview` bağlamayı idempotent yapar; API sözleşmesi
  `test_api_method_contract.py` ile pinlidir.
- **Run summary:** `run_summary_refs_trend.py` tabloyu taşır (render
  çoğaltılmaz; `GITHUB_STEP_SUMMARY` yoksa stdout).
- **Artifact'lar:** `refs-trend`, `audit-refs-trend`, `override-trend` —
  30 gün saklanır.

## 8. Bugünkü durum (ölçüldü, 2026-10-14)

- `docs/determinism_trend/determinism_trend.jsonl`: **6 satır**, izleniyor;
  son ölçüm `2026-09-30`, `platform=darwin`, `passes=3`, `sde=0`.
- `docs/battery_trend/battery_trend.jsonl`: **diskte yok** → batarya trendi
  henüz ilk ölçümünü almamış; `--check` boş trendde fail-closed davranır.
- `refs-trend/`, `override-trend/`, `determinism-trend/` çıktıları üretilmiş
  dizinlerdir (izlenmez).
- Trend veri dosyaları `docs/` altında **izlenir**; bu yüzden Vercel
  checkout'unda gerçek değerle çalışan tek canlı-veri kaynağı
  `/api/determinism-trend`'dir.

## 9. Sınırlar ve açık noktalar

- **Platform kapsamı bir kanıt borcudur:** cutoff sonrası `linux` kaydı
  CI'dan gelir; yerel makinede yalnız `darwin` ölçümü alınabilir. Tek
  platformlu bir pencerede kapı `FAIL` verir — bu **bilinçli**dir (kapsam
  garantisi), kayıp değildir.
- **Çapraz-platform eşitliği ölçülmeden iddia edilmez** (R3 ilkesi): not
  üretilir, ihlal sayılmaz.
- **İzlenmeyen ağaçlar:** kanıt raporları `docs/ci_simulate/` altında
  (gitignore'lu) kalır; trend satırı bu yüzden rapor yoluna değil, raporun
  **içeriğinden çıkarılan** hash'lere dayanır.
- **Denetim katmanı advisory:** `audit-refs-trend` bugün required değildir;
  sahte/bayat trend satırı build'i bloke etmez, artifact'ta görünür.
- **§9 CI trendi bağlantısızdır (ölçüldü, 2026-10-14):** `gen_ci_trend.py`
  docstring'i `update_changelog_hook.sh` (pre-commit) üzerinden her push'ta ve
  bir `ci-stats-doc-sync` advisory job'ında koştuğunu iddia eder; ama izlenen
  ağaçta bu iki bağlantının **hiçbiri yok** — hook yalnız
  `gen_changelog.py --check/--prune` çağırır, hiçbir workflow'da `ci-stats`
  adlı job bulunmaz ve `git grep` repoda `gen_ci_trend`/`ci_stats` çağrısı
  göstermez. Yani §9 tablosu bugün canlı veriden kendiliğinden tazelenmiyor;
  sarmalayıcı yalnız elle koşulduğunda iş görür. (Aynı sınıf: sözleşme, adı
  geçen denetimi işaret ediyor ama denetim bağlı değil.)

## 10. Bu tasarımı doğrulayan testler

| Sözleşme | Test |
|---|---|
| determinism ölçüm/ekleme + değişmezler | `test_record_determinism_trend.py` (fail-closed, çok-geçiş kanıtı, residual=none fallback) |
| rozet/SVG/JS/Python senkronu + API yüzeyi | `test_determinism_trend_badge.py`, `test_trend_tooltip_dom.js` |
| motor pini iki job'da aynı | `test_determinism_trend_canvas.py` |
| batarya kaydı + değişmezler | `test_record_battery_trend.py` |
| refs trend parse/stats/bayat/bütçe | `test_refs_trend.py`, `test_refs_trend_badge.py`, `test_refs_trend_badge_node.js` |
| trend ↔ kaynak artifact denetimi | `test_audit_refs_trend.py` |
| override trend | `test_override_trend.py`, `test_override_trend_badge.py` |
| §9 blok senkronu | `test_gen_ci_trend.py`, `test_ci_stats.py` |
| cron aralığı (aynı-cron yasağı) | `test_gated_schedules.py` |
| trend → DB depolama sözleşmesi (kapsam dışı) | `test_trend_db_contract.py`, `test_trend_db_index_contract.py`, `test_trend_db_rls_contract.py`, `test_trend_db_js_runner.py` |
