-- =============================================================================
-- trend_runs — sorgu-deseni indeksleri (partial + covering)
-- =============================================================================
-- Panonun okuma desenleri (docs/TREND_CHART_READ_PATH.md §1/§3):
--   A) Pencere/seri : where ts >= $1 order by ts desc limit N
--                     dar select — bugünkü pencere sorgusu (lib/trend-db.ts::
--                     getTrendFromDb): ts, p0, p1, duration_s, budget_usd, z3_total
--                     planlanan seri sorgusu (§3): ts, verdict, p0, p1, z3_total
--   B) Yalnız-FAIL  : where verdict = 'FAIL' order by ts desc limit N
--   C) En yeni satır: order by ts desc limit 1 → tek satır tam olarak istenir,
--                     mevcut unique `trend_runs_ts_key` yeter (covering gereksiz:
--                     satırın 40 kolonunu INCLUDE etmek anlamsız olurdu).
--
-- Neden RAW SQL? Prisma 7.10 `@@index` partial (WHERE) ve covering (INCLUDE)
-- ifade EDEMEZ — ölçüldü: `@@index([ts], include: [...], where: "...")` →
-- `error: No such argument ... Validation Error Count: 3`. Şema tek kaynak
-- kalır; bu iki indeksin adı ve gerekçesi `prisma/schema.prisma`daki not
-- bloğunda aynalanır (drift'i test_trend_db_index_contract kapıya bağlar).
--
-- Skill referansı: query-partial-indexes (HIGH) → filtrelenen sorgular için
-- kısmi indeks; query-covering-indexes (MEDIUM-HIGH) → INCLUDE ile index-only
-- scan; query-composite-indexes → mevcut `(verdict, ts DESC)` eşitlik→aralık
-- sırası korunur.
--
-- Ölçülen dağılım (2026-09-27): 269 satır = 233 PASS + 36 FAIL (%13,4);
-- p0>0: 0 · p1>0: 0 · budget_usd dolu: 233; heap 376 kB, toplam 512 kB.
--
-- DİKKAT: bu boyutta planner SEQ SCAN seçer ve bu doğrudur (269 satırda sıralı
-- tarama 0,28 ms — docs §4 ölçümü). İndeksler arşiv büyüdükçe ve select
-- daraldıkça devreye girer; kurulum maliyeti satır başına ~40 B, yükleme
-- yolunda (500'lük createMany dilimleri) ihmal edilebilir.
-- Büyük tabloda bunlar `CONCURRENTLY` ister; Prisma migration'ı transaction
-- içinde koştuğu için CONCURRENTLY burada KULLANILAMAZ — bu boyutta gerek yok.
-- =============================================================================

-- A) ts-sıralı okumalar için COVERING indeks: sıralamayı ve dar select'in
--    kolonlarını taşır → index-only scan (heap fetch yok).
--    INCLUDE seti panonun dar select'lerinin BİRLEŞİMİdir (bugünkü pencere +
--    planlanan seri); fazladan kolon eklemeyin, index-only scan'i bozar.
create index if not exists trend_runs_ts_cover_idx
  on public.trend_runs (ts)
  include (verdict, p0, p1, duration_s, budget_usd, z3_total);

-- B) Yalnız-FAIL ucu için PARTIAL + COVERING indeks: FAIL satırları tablonun
--    azınlığıdır (%13) → kısmi indeks PASS hacmi büyüdükçe de küçük kalır.
--    Predicate sorgudaki değişmezle BİREBİR aynı olmalı (`verdict = 'FAIL'`);
--    farklı bir yazım (ör. `lower(verdict) = 'fail'`) planner'ı bu indeksten
--    eder.
create index if not exists trend_runs_fail_ts_cover_idx
  on public.trend_runs (ts desc)
  include (p0, p1, z3_total)
  where verdict = 'FAIL';

-- -----------------------------------------------------------------------------
-- REDDEDİLENLER (gerekçe yazılı ki karar sessizce eskimesin):
--   • `p0 > 0` partial indeks — bugün 0 satır ve DB tarafında P0-filtreli uç
--     YOK (P0 filtresi preview HTTP yolunda: `rhFilter`). DB'de P0 ucu açılınca:
--       create index ... on public.trend_runs (ts desc)
--         include (p1, verdict) where p0 > 0;
--   • `budget_usd` indeksi — eşik config'ten gelir (`budget_usd > limit`), yani
--     partial predicate olamaz; pencere okuması zaten A indeksinin INCLUDE'unda.
--   • Agrega görünümü (gün × verdict) — 269 satırda seq scan 0,28 ms; §4'teki
--     50k satır tetiğinde yeniden değerlendirilir (o noktada ifade indeksi
--     yerine agreganın SQL'e taşınması da masada).
--   • `source_row_sha256` / `ts` tekil indeksleri — yükleme idempotansı
--     (`ON CONFLICT DO NOTHING`) ve "en yeni satır" sorgusu bunları kullanır
--     (init migration); yenisi gerekmez.
-- -----------------------------------------------------------------------------

-- Geri alma (ayrı bir migration olarak):
--   drop index if exists public.trend_runs_fail_ts_cover_idx;
--   drop index if exists public.trend_runs_ts_cover_idx;
