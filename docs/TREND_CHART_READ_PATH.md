# Trend grafiği → TrendRun okuma yolu (Tasarım)

> Dashboard'un trend yüzeyini **kalıcı `trend_runs` tablosundan** besleyen okuma
> yolu. İlkeler: (1) tek şema kaynağı + drift-guard kapsamı
> (`test_trend_db_contract`), (2) DB parolası olmayan makinede pano çalışmaya
> devam eder (preview kaynağı), (3) bozulma sessiz kalmaz — grafik yuvası boş
> kutu olarak gösterilmez, nedeni yazar, (4) yeni bağımlılık yok.
>
> Durum: **tasarım** (2026-09-26). Tablo için DB okuma yolu zaten çalışıyor
> (§1); eksik olan grafik bileşeni ve agrega okuma yoludur.
>
> **Okuma notu (commit durumu):** Satır numaraları *çalışma ağacındaki* sürüme
> göredir. DB okuma katmanı henüz commit'li değil: `lib/trend-db.ts`,
> `components/RunsTable.tsx`, `app/(panel)/` HEAD'de **yok**; `lib/preview.ts`
> HEAD'de var ama HEAD sürümünde `TREND_SOURCE` geçmez. Yani bu tasarımın
> 1-3. katmanları commit bekleyen iş üstüne oturur (§9 adım 0).

## 1. Bugünkü durum (kanıt)

| Katman | Konum | Bugünkü davranış |
|---|---|---|
| Görünüm | `components/RunsTable.tsx:25-35` | Server Component; `await getTrend(limit)`, `history.slice(-limit).reverse()` |
| Pencere | `app/(panel)/@trend/page.tsx:11`, `app/trend/page.tsx:12` | 5 / 20 satır |
| Kaynak anahtarı | `lib/preview.ts:57-64` | `TREND_SOURCE` = `db` \| `preview`; yoksa `DATABASE_URL` varsa `db` |
| Facade | `lib/preview.ts:81-89` | `getTrend` → `db` ise dinamik `import("./trend-db")` |
| DB okuma | `lib/trend-db.ts:75-94` | `orderBy ts desc, take limit` + `reverse()` (eskiden-yeniye) |
| Sözleşme | `lib/preview.ts:39-46` | `TrendRow` = ts, p0, p1, duration_s, budget_usd, z3_total |
| Kimlik | `next.config.js:12-18` | `process.loadEnvFile("../trend-db/.env")` — parola tek yerde |
| Tekilleştirme | `lib/trend-db.ts:30-49` | `globalThis.__trendDb` (dev'de havuz çoğalmaz), pooled URL |

Commit durumu (HEAD'e göre, doğrulandı): `lib/preview.ts`, `app/trend/page.tsx`,
`next.config.js` **HEAD'de var** (ilk ikisi değiştirilmiş); `lib/trend-db.ts`,
`components/RunsTable.tsx`, `app/(panel)/@trend/page.tsx` **HEAD'de yok** —
bu yüzden tasarımın uygulama sırası §9'da "mevcut WIP'i commit'le" adımıyla başlar.

**İki boşluk:**

1. **Grafik bileşeni yok.** `grep -rniE "chart|sparkline|recharts|victory|d3" app
   components lib` yalnız `app/globals.css:38-42`'deki kullanılmayan
   `--chart-1..5` şablon token'larını bulur; `package.json` bağımlılıklarında
   (next, react, prisma, pg, cva, base-ui, lucide-react) grafik kütüphanesi yok.
2. **`TrendRow` verdict taşımıyor** (`lib/preview.ts:39-46`) — segment/renk kararı
   için gerekli; grafik sözleşmesi bunu ekler.

**Arşiv tarafı hazır:** `trend_runs` kalıcıdır ve kayan 100'lük pencerenin dışına
düşen koşuları da tutar (`apps/trend-db/README.md`, "kalıcı arşiv" + `HISTORY_MAX=100`);
2026-09-26 ölçümü: **233 satır** (`npm run load` sonrası 100 eklendi), tempo
~100 koşum/gün. Yani grafiğin penceresi tablonun kendi derinliğinden gelir,
JSONL penceresinden değil.

## 2. Grafiğin istediği seri (minimal)

Tek seri: **UTC kova** (boyut: gün ya da saat — §2 ölçümü) — yığın: PASS/FAIL
sayısı; ikinci eksen: p0+p1 toplamı; alt satır: koşum sayısı (ve isteğe bağlı süre).

```
TrendBucket = { bucket: "YYYY-MM-DD" | "YYYY-MM-DDTHH" (UTC),
                runs, pass, fail, p0, p1, z3_total }
TrendSeries = { buckets: TrendBucket[], from: string, to: string,
                granularity: "hour" | "day", truncated: boolean }
```

- Kova günlük: tablo zaten koşu-satırı gösteriyor; grafik "zaman içinde ne oldu"
  sorusunu yanıtlar ve **pencere N'e bağlı kalmaz**.
- **Boş kova atlanmaz**, 0 değerleriyle üretilir: koşusuz günü düşürmek grafiği
  sıkıştırır ve "kesintisiz koşum" izlenimi verir (kanıt-görünümü ilkesi).
- `truncated` = sorgu `ROW_CAP`'e dayandı (§5).

**Ölçüm (2026-09-26, canlı `trend_runs`):** 14 günlük pencere = 233 satır →
**2 kova** (2026-09-25: 133 koşum, z3=1596; 2026-09-26: 100 koşum, z3=1200;
tümü PASS). Yani arşiv bugün **2 günlük** — günlük kova ile grafik seyrek kalır.
İki tasarım sonucu:

1. **Kova boyutu parametre olsun:** `granularity: "hour" | "day"`; span ≤ 48 saat
   → saatlik, üstü günlük. 2026-09-26 koşumları 08:10–10:13Z arasında toplanmış
   (saatlik ~3 nokta) — günlükün 1 noktasından okunur.
2. **Eşik: ≥ 5 dolu kova** olmadan grafik çizilmez; yerine tablo + açık not
   ("grafik için yeterli geçmiş yok — N gün"). 2 noktalı bir "trend" çizgisi
   yön iddia eder, halbuki kanıt sadece 2 günlük.

## 3. Okuma yolu (katmanlar)

RSC → `lib/preview.ts` facade → kaynak anahtarı → `lib/trend-db.ts` | HTTP

| Dosya | Değişiklik | Not |
|---|---|---|
| `lib/trend-buckets.ts` | **YENİ, saf**: `bucketSeries(rows, { from, to, rowCap }) → TrendSeries` | DB/pg/React importu yok → birim testi DB'siz koşar |
| `lib/trend-db.ts` | **EKLER**: `getTrendSeriesFromDb(days)` | `findMany({ select: { ts, verdict, p0, p1, z3Total }, where: { ts: { gte } }, orderBy: { ts: "desc" }, take: ROW_CAP })` + `bucketSeries(...)`; jsonb kolonlar OKUNMAZ |
| `lib/preview.ts` | **EKLER**: `getTrendSeries(days)` | `db` ise `(await import("./trend-db")).getTrendSeriesFromDb`, değilse `{ ok: false, reason: "preview-source" }`; `cache()` sarmalı korunur (`lib/preview.ts:73-89`) |
| `components/TrendChart.tsx` | **YENİ** | Server Component, **inline SVG** (yeni bağımlılık yok), token renkleri (`ok`/`err`/`warn`/`border`/`surface`), sabit yükseklik, `role="img"` + `<title>` |
| `components/RunsTable.tsx` | **DOKUNULMAZ** | Tablo denetim görünümü olarak kalır; grafik onun üstüne yerleşir |

Seri tüketicisi pencereyi kendisi kısmaz (kovalar zaten hedef çözünürlükte);
sıra sözleşmesi için §5.

## 4. Toplama neden JS'te (reddedilen: `date_trunc` + `$queryRaw`)

| Ölçüt | JS kovalama (seçilen) | SQL `date_trunc` |
|---|---|---|
| Şema tek-kaynak | Prisma tipleri; drift-guard kapsar (`lib/trend-db.ts:1-6` gerekçesinin devamı) | Elle SQL, `test_trend_db_contract` dışında **ikinci yüzey** |
| Hacim | 14 gün × ~100 = ~1.4k satır, dar `select` → küçük | Agrega sunucuda (avantaj) |
| Test | Saf fonksiyon, DB'siz | Canlı DB ya da SQL dizesi testi |
| Risk | Pencere büyürse bellek | Kolon adı sürüklenmesi sessiz kalır |

**Geri dönüş tetiği (yazılı):** pencere > **50k satır** (≈ 500 gün @100 koşum/gün)
ya da `truncated` sürekli `true` → `$queryRaw` + `date_trunc('day', ts)` + şemaya
bağlayan kontrat testi. Sayı yazılı ki karar sessizce eskimesin.

**Ölçüm (aynı sorgu, 2026-09-26):** plan `Seq Scan on trend_runs` +
quicksort 41 kB, execution **0.28 ms**, 233 satır — bu boyutta planner'ın seq
scan seçmesi **doğru** (indeks kurulumu daha pahalı). `trend_runs_ts_key` arşiv
büyüdükçe devreye girer; 50k tetiği zaten o noktayı işaretliyor.

**İndeks (2026-09-27 güncellemesi):** init migration'ın `trend_runs_ts_key`
(unique `ts`) ve `trend_runs_verdict_ts_idx (verdict, ts DESC)` indeksleri
kova sorgusunun ts-aralığı/verdict-eşitliği şeklini karşılar. Üzerine iki
**sorgu-deseni indeksi** eklendi
(`apps/trend-db/prisma/migrations/20260927194500_trend_runs_query_indexes/`):

| İndeks | Şekil | Hangi deseni karşılar |
|---|---|---|
| `trend_runs_ts_cover_idx` | `(ts) INCLUDE (verdict, p0, p1, duration_s, budget_usd, z3_total)` | Pencere/seri sorgusu (§3 dar `select`) → index-only scan |
| `trend_runs_fail_ts_cover_idx` | `(ts DESC) INCLUDE (p0, p1, z3_total) WHERE verdict = 'FAIL'` | Yalnız-FAIL ucu; FAIL azınlık (%13,4) → kısmi indeks PASS hacmiyle büyümez |

- **Neden raw SQL:** Prisma 7.10 `@@index` partial/covering ifade edemiyor
  (`include:`/`where:` → "No such argument", ölçüldü); şemada not bloğu adları
  aynalar, `test_trend_db_index_contract.py` drift'i kapatır.
- **Bugün neden hâlâ seq scan:** 269 satırda sıralı tarama 0,28 ms; planner
  doğru kararı veriyor (yukarıdaki ölçüm). İndeksler arşiv büyüdükçe ve
  `select` daraldıkça (bugünkü pencere sorgusu tüm kolonları çekiyor) devreye
  girer — tetik §4'teki **50k satır** ya da `truncated` sürekliliği.
- **INCLUDE seti kuralı:** yalnız dar `select`'lerin birleşimi; kolon eklemek
  index-only scan'i bozar, kolon eksiltmek heap fetch'e döndürür.
- **Ölçek kanıtı (100k satır / 78 MB heap, TEMP tablo, %12,5 FAIL):** seri
  sorgusu `ts_key` ile 528 buffer / 1,46–1,53 ms → covering ile **46 buffer /
  0,82 ms** (index-only); yalnız-FAIL ucu 45 buffer / 0,15–0,18 ms → partial ile
  **4 buffer / 0,09–0,10 ms**. Boyut: covering 6,6 MB, partial **512 kB**
  (unique `ts_key` 3,95 MB). Tam tablo + yöntem: `apps/trend-db/README.md`
  "Sorgu indeksleri" (oturuma özel ölçüm, kalıcı iz yok).
- Verdict-filtreli kova composite indeksin eşitlik→aralık sırasını kullanır
  (`prisma/schema.prisma`, "query-composite-indexes" notu); `p0 > 0` için
  kısmi indeks **özellikle reddedildi** (bugün 0 satır + DB'de P0 ucu yok —
  gerekçe migration dosyasının "REDDEDILENLER" bloğunda).

## 5. Sıra, saat dilimi, kırpma

- Kovalar **UTC** kova sınırında (gün ya da saat): `ts` → `Timestamptz(6)`;
  yerel saat, gece yarısı civarı koşuları iki kovaya bölerdi.
- **Kova anahtarı string üretilir** (`(ts at time zone 'UTC')::date::text`),
  `Date` nesnesi değil. Ölçüldü: `DATE` değerini JS `Date`'e çevirip
  `toISOString().slice(0,10)` yapmak UTC+2 istemcisinde kovayı **bir gün geriye
  kaydırıyor** (2026-09-25/26 kovaları 09-24/09-25 gibi göründü). JS kovalama bu
  yüzden Prisma'nın döndürdüğü `Date`'ten doğrudan `ts.toISOString().slice(0,10)`
  üretmeli (UTC günü), SQL tarafına geçilirse `::text` kullanılmalı.
- Çıktı **eskiden-yeniye** — mevcut `history` sözleşmesiyle aynı
  (`lib/trend-db.ts:71-74`); tüketici çevirir. Bu, sayfanın sessizce en eski
  pencereyi "son pencere" diye göstermesini engelleyen kuralın devamı.
- `ROW_CAP` (başlangıç **5000**) dolduysa `truncated: true`; grafik "pencere
  kırpıldı" notu gösterir — eksik veriyi sessizce tam gibi göstermez.

## 6. Bozulma: preview modu — sessiz boş kutu yok

`TREND_SOURCE=preview` (ya da `DATABASE_URL` yok) iken toplama ucu yoktur:
`getTrendSeries` → `{ ok: false, reason: "preview-source" }`; grafik yuvası
yerine açık not: *"grafik yalnız DB kaynağında (`TREND_SOURCE=db`)"*. Tablo aynen
kalır. Gerekçe `lib/preview.ts:8-10`: DB parolası olmayan makinede pano çalışmaya
devam eder — ama grafiği boş kutu/boş eksen olarak göstermek "veri yok" demek
olurdu; eksik olan veri değil, **kaynaktır**.

**Reddedilen:** preview'da istemci-taraflı kovalama — `/api/trend?limit=N` yalnız
son N koşu satırını verir, kova sayısı N'e bağlı kalır (§2 ile çelişir).

## 7. Test ve kapı planı (dosya-kaynaklı)

| Kapı | Dosya | Eklenecek iddia |
|---|---|---|
| Drift-guard | `_calisma/CIKTI/test_trend_db_contract.py` | Seri alanları (`verdict` dahil) ↔ `TrendRun` şeması; loader eşlemesi sürmez |
| Saflık | aynı dosya (ya da `test_trend_buckets.py`) | `bucketSeries`: boş kova üretimi, UTC sınırı (23:59/00:01), `truncated`, saf fonksiyon (DB/pg'siz import) |
| Manifest + kapsam | `_calisma/CIKTI/check_unit_tests.list`, `test_coverage_report.py` HOOK_COVERAGE | Yeni test dosyası kaydı; `sync_check_unit_tests.py --check` yeşil |
| Biçim | `_calisma/CIKTI/check_prettier_format.py` (`files: \.(js\|jsx\|ts\|tsx\|json)$`) | Yeni `.ts`/`.tsx` dosyaları prettier temiz |
| Dashboard | `test_dashboard_playwright_smoke.py`, `test_dashboard_cls_budget.py` | Grafik yuvası erişilebilir ad taşır; CLS bütçesi aşılmaz (sabit yükseklik) |

## 8. Karar özeti

| # | Karar | Alternatif | Neden |
|---|---|---|---|
| 1 | UTC kova, boyut parametreli (gün/saat) | Ham koşu satırlarını çizmek | Pencere N'den bağımsız; arşivin derinliği kullanılır; seyrek veride saatlik çözünürlük (§2 ölçümü) |
| 2 | JS kovalama | `date_trunc` + `$queryRaw` | Tek şema kaynağı + drift-guard kapsamı (§4) |
| 3 | Facade `lib/preview.ts`'te | Bileşende doğrudan DB | Kaynak anahtarı tek yerde kalır (`lib/preview.ts:57-64`) |
| 4 | preview'da açık "grafik yok" notu | Boş grafik / sessiz gizleme | Kanıt-görünümü; sessiz-PASS yok |
| 5 | Inline SVG | recharts/victory | Bağımlılık disiplini; ~14 nokta için kütüphane gereksiz |
| 6 | `RunsTable` değişmez | Tabloyu grafikle değiştirmek | Denetim görünümü (ts/p0/p1/süre/z3) erişilebilir kalır |

## 9. Uygulama sırası (küçük diff'ler, her adım tek başına yeşil)

0. **Commit bekleyeni kapat:** `lib/trend-db.ts`, `components/RunsTable.tsx`,
   `app/(panel)/`, `lib/preview.ts` değişikliği, `next.config.js`, ayrıca
   `apps/trend-db/prisma/migrations/20260925171004_init/` (untracked) — grafik
   bu katmanların üstüne biner; commit'siz zeminde yeni yol eklemek
   sürüklenmeyi ikiye katlar.
1. `lib/trend-buckets.ts` + saflık testleri (DB'siz; ilk adım tek başına değer üretir).
2. `lib/trend-db.ts::getTrendSeriesFromDb` + dar `select`.
3. `lib/preview.ts::getTrendSeries` (kaynak anahtarı + `{ ok: false }` bozulması).
4. `components/TrendChart.tsx` + iki rotaya (5/20) yerleştirme.
5. Kontrat testi, manifest/kapsam kayıtları, `check_unit_tests.list` senkronu.

## 10. Açık sorular

- Süre serisi (p50/ortalama) grafikte ikinci eksene girecek mi, yoksa tooltip'te mi kalacak?
- Kova boyutu: §2'deki `granularity` eşiği (48 saat) yeterli mi, pencere uzadıkça haftalığa da geçilmeli mi? (Tetik §4'teki sayıya bağlı.)
- `budget_usd` trendi (maliyet) aynı grafikte mi, ayrı mini seride mi gösterilecek?
