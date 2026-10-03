-- ============================================================================
-- live-backup-2026-10-03.sql
-- CANLI Neon ŞEMASININ YEDEĞİ — yapı + migration defteri (VERİ YOK)
--
-- NEDEN VAR: prisma/migrations/ repoda YOK, ama canlı DB'de 3 migration
-- UYGULANMIŞ. Bu dosya, o geçmişi repo'ya geri getirmeden ÖNCE alınmış
-- geri dönüş noktasıdır. Migration onarımına başlamadan önce bu dosya
-- yeterli bir güvenlik ağıdır.
--
-- ÖLÇÜM (2026-10-03):
--   proje  leibniz2-trend (orange-bar-58985004), branch main
--          (br-morning-queen-b1zibof0), aws-eu-central-1, PostgreSQL 18.6
--   nesne  trend_runs 42 kolon / 269 satır · trend_runs_daily 9 kolon / 3 satır
--          · 3 migration · 1 RLS politikası
--   veri   bu dosyada YOK (yalnız yapı + migration kayıtları)
--
-- KAPSAM DIŞI (bilerek): ROLLERİN KENDİSİ ve parolaları. Roller Neon
-- tarafında yönetilir; aşağıdaki GRANT'ler onların VAR OLMAŞINI varsayar.
--
-- NASIL KULLANILIR (TEHLİKELİ — yalnız boş/deneme hedefte):
--   psql "$DATABASE_URL_UNPOOLED" -v ON_ERROR_STOP=1 -f live-backup-2026-10-03.sql
--   Canlıya ASLA çalıştırma: bu bir GERİ YÜKLEME betiğidir, veriyi silmez
--   ama şemayı oluşturur; mevcut şemayla birlikte çalıştırılırsa hata verir.
--
-- ÜRETİM: bölüm (a) `prisma migrate diff --from-empty --to-config-datasource
-- --script` çıktısıdır (Prisma 7.10.0). Bu araç trend_runs_daily'yı
-- ATLADI — çünkü tabloda primary key yok (aşağıda bkz. (c)) — bu yüzden
-- (b), (c), (d) elle ve information_schema/pg_catalog'dan alındı.
-- ============================================================================

-- (a) Prisma üretimi: şema + indeksler (olduğu gibi)
CREATE SCHEMA IF NOT EXISTS "public";

CREATE TABLE "public"."trend_runs" (
    "id" SERIAL NOT NULL,
    "ts" TIMESTAMPTZ(6) NOT NULL,
    "verdict" TEXT NOT NULL,
    "p0" INTEGER NOT NULL,
    "p1" INTEGER NOT NULL,
    "duration_s" DOUBLE PRECISION,
    "duration_pct_warn" BOOLEAN,
    "budget_usd" DECIMAL(10,2),
    "budget_limit" DECIMAL(10,2),
    "budget_method" TEXT,
    "ref_count" INTEGER,
    "refs_verified" INTEGER,
    "refs_total" INTEGER,
    "refs_mismatch" INTEGER,
    "refs_by_source" JSONB,
    "z3_passed" INTEGER,
    "z3_failed" INTEGER,
    "z3_total" INTEGER,
    "lean_ok" BOOLEAN,
    "lean_source" TEXT,
    "lean_override" BOOLEAN,
    "lean_detail" JSONB,
    "lineage_ok" BOOLEAN,
    "lineage_count" INTEGER,
    "lineage_summary" JSONB,
    "pattern_drift" JSONB,
    "pattern_drift_detail" JSONB,
    "cli_override_count" INTEGER,
    "cli_overrides" JSONB,
    "hook_env" JSONB,
    "precommit_hooks" JSONB,
    "status_board" JSONB,
    "findings" JSONB,
    "audit_refs_trend" TEXT,
    "flaky_count" INTEGER,
    "deterministic_count" INTEGER,
    "exit_code" INTEGER,
    "raw_sha256" TEXT,
    "stripped_sha256" TEXT,
    "history_sidecar_sha256" TEXT,
    "pdf_pages" INTEGER,
    "source_row_sha256" TEXT,

    CONSTRAINT "trend_runs_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "trend_runs_fail_ts_cover_idx" ON "public"."trend_runs"("ts" DESC, "p0" ASC, "p1" ASC, "z3_total" ASC);
CREATE UNIQUE INDEX "trend_runs_source_row_sha256_key" ON "public"."trend_runs"("source_row_sha256" ASC);
CREATE INDEX "trend_runs_ts_cover_idx" ON "public"."trend_runs"("ts" ASC, "verdict" ASC, "p0" ASC, "p1" ASC, "duration_s" ASC, "budget_usd" ASC, "z3_total" ASC);
CREATE UNIQUE INDEX "trend_runs_ts_key" ON "public"."trend_runs"("ts" ASC);
CREATE INDEX "trend_runs_verdict_ts_idx" ON "public"."trend_runs"("verdict" ASC, "ts" DESC);

-- (b) ELLE: trend_runs_daily — Prisma tarafından ÜRETİLEMEZ.
--    information_schema'dan birebir. Primary key YOK, hiçbir constraint ve
--    indeks yok, 9 kolonun tamamı nullable. Bu yüzden Prisma bunu model
--     olarak temsil EDEMEZ ("Each model must have at least one unique
--     criteria that has only required fields" — P1012, ölçüldü) ve
--     migrate diff çıktısına da girmiyor. Bu tablo Prisma DIŞINDA,
--     elle yönetilir. (c) bkz.
CREATE TABLE "public"."trend_runs_daily" (
    "day" DATE,
    "verdict" TEXT,
    "runs" INTEGER,
    "p0_total" INTEGER,
    "p1_total" INTEGER,
    "avg_duration_s" NUMERIC,
    "avg_budget_usd" NUMERIC,
    "z3_passed_total" INTEGER,
    "z3_failed_total" INTEGER
);

-- (c) RLS — canlıda ENABLE + FORCE, politika yalnız trend_service için.
--     Dikkat: politika USING (true) olduğu için RLS trend_service'i
--     KISITLAMAZ; asıl kısıtlama GRANT katmanındadır (aşağıda).
ALTER TABLE "public"."trend_runs" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."trend_runs" FORCE ROW LEVEL SECURITY;

CREATE POLICY "trend_runs_service_all" ON "public"."trend_runs"
    FOR ALL TO trend_service
    USING (true)
    WITH CHECK (true);

-- (d) GRANT'ler — canlıdaki yetkiler birebir.
GRANT USAGE ON SCHEMA "public" TO trend_service;
GRANT USAGE ON SCHEMA "public" TO trend_anon;

GRANT SELECT, INSERT, UPDATE, DELETE ON "public"."trend_runs" TO trend_service;
GRANT SELECT ON "public"."trend_runs_daily" TO trend_anon;

-- (e) Migration defteri — kayıp 3 kayıt, checksum'leriyle.
--     ÖNCE tablo kendisi: Prisma bu defter tablosunu introspeksiyondan
--     DAŞARI bırakır, bu yüzden (a)'daki migrate diff çıktısında YOKTUR.
--     İlk geri-yükleme denemesi bu yüzden 42P01 (undefined_table) ile
--     düştü — düzeltildi ve atılabilir branch'te yeniden doğrulandı.
CREATE TABLE "public"."_prisma_migrations" (
    "id" VARCHAR(36) NOT NULL,
    "checksum" VARCHAR(64) NOT NULL,
    "finished_at" TIMESTAMPTZ,
    "migration_name" VARCHAR(255) NOT NULL,
    "logs" TEXT,
    "rolled_back_at" TIMESTAMPTZ,
    "started_at" TIMESTAMPTZ NOT NULL DEFAULT now(),
    "applied_steps_count" INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX "_prisma_migrations_pkey" ON "public"."_prisma_migrations" USING btree ("id");

--     Bunlar repodaki migration dosyalarıyla BİREBİR eşleşmelidir; aksi
--     halde Prisma "migration history diverge" hatası verir. Checksum'ler
--     buradan alınmıştır; dosyaları üretirken aynı checksum çıkmalıdır.
INSERT INTO "_prisma_migrations" (id, migration_name, checksum, started_at, finished_at, rolled_back_at, applied_steps_count, logs) VALUES (gen_random_uuid()::text, '20260925171004_init', 'e65772c59d339714629a6f275afe2d967c9e13cda4ad533527a29abd54f1a4e3', '2026-09-25T17:10:04.689Z', '2026-09-25T17:10:04.902Z', NULL, 1, NULL);
INSERT INTO "_prisma_migrations" (id, migration_name, checksum, started_at, finished_at, rolled_back_at, applied_steps_count, logs) VALUES (gen_random_uuid()::text, '20260927193000_trend_runs_rls', '41ab7f4525704a9b5e71b409645456555c4ab5522087d8b6f081b060025fb6d3', '2026-09-28T00:42:50.349Z', '2026-09-28T00:42:50.582Z', NULL, 1, NULL);
INSERT INTO "_prisma_migrations" (id, migration_name, checksum, started_at, finished_at, rolled_back_at, applied_steps_count, logs) VALUES (gen_random_uuid()::text, '20260927194500_trend_runs_query_indexes', 'a7d2e02e30d6649ce814ad85d0b788aa4d13f829cf021493be2c5737fe03467d', '2026-09-28T00:42:50.627Z', '2026-09-28T00:42:50.795Z', NULL, 1, NULL);

-- ============================================================================
-- ÖLÇÜLMEYENLER (bu yedek kapsam dışı):
--   * satır verisi (269 + 3 satır) — yedekte YOK; amaç yapı/geçmiş kurtarması
--   * rol tanımları ve parolaları — Neon tarafında yönetilir
--   * branch/endpoint kimlikleri — proje meta verisi, şema değil
-- ============================================================================
