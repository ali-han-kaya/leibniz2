# trend-db — doğrulama-zinciri trend geçmişinin Postgres katmanı

`history.jsonl` (verify koşumları, 40+ alan) → Neon Postgres `TrendRun` tablosu.
Skill: `prisma-database-setup` (Prisma 7 + `@prisma/adapter-pg`) + `neon-postgres`
bağlantı sözleşmesi (pooled/direct ayrımı).

## Durum (2026-09-18)

- ✅ Şema (`prisma/schema.prisma` — HISTORY_KEYS'in 42 alanının tam modeli), config, loader, testler
- ✅ Drift-guard: `test_trend_db_contract.py` HISTORY_KEYS ↔ şema ↔ loader sürüklenmesini yakalar
- ✅ Credentialsuz kapılar: `prisma validate` + `prisma generate`
- ⏳ **Bekleyen: `neon login` (kullanıcı adımı)** — ardından aşağıdaki 3 komut

## `neon login` sonrası (3 adım)

```bash
cd apps/trend-db
neon env pull                    # DATABASE_URL (pooled) + DATABASE_URL_UNPOOLED üretir → .env'e
DATABASE_URL="$DATABASE_URL_UNPOOLED" npx prisma migrate dev --name init
npm run load                     # TCC-mirror history.jsonl → TrendRun (idempotent upsert, pooled)
```

## Notlar

- **Pooled/direct ayrımı (Neon sözleşmesi):** `DATABASE_URL` pooled'dır
  (PgBouncer, transaction-mode) — uygulama/loader trafiği buna gider.
  **Migration pooled üzerinden koşmaz** (`prepared statement "s0" already
  exists`, kayıp `SET` session-state, `SQLSTATE 25006` riski) — migration'da
  `DATABASE_URL`'i `DATABASE_URL_UNPOOLED` değeriyle override et (yukarıdaki
  2. komut). `neon env pull` her ikisini de .env'e yazar.
- Loader her satırın SHA-256'sını `source_row_sha256`'a basar → aynı kaynak
  tekrar yüklenirse upsert no-op (idempotent).
- Şema Prisma 7 sözleşmesindedir: URL `prisma.config.ts`'te, generator
  `prisma-client` + explicit output (`generated/`).
- Alan-kapsamı: şema HISTORY_KEYS'in tamamını kollar (`refs_by_source` dahil,
  `Json` kolon); sürükleme = CI'da `test_trend_db_contract` kırılır.
