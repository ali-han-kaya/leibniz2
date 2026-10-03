# trend-db — doğrulama-zinciri trend geçmişinin Postgres katmanı

`history.jsonl` (verify koşumları, 40+ alan) → Neon Postgres `TrendRun` tablosu.
Skill: `prisma-database-setup` (Prisma 7 + `@prisma/adapter-pg`) + `neon-postgres`
bağlantı sözleşmesi (pooled/direct ayrımı).

## Durum (2026-10-03 ölçümüyle güncellendi)

- ✅ Şema (`prisma/schema.prisma` — HISTORY_KEYS'in 42 alanının tam modeli), config, loader, testler
- ✅ Drift-guard: `test_trend_db_contract.py` HISTORY_KEYS ↔ şema ↔ loader sürüklenmesini yakalar
- ✅ Canlı proje **var**: `leibniz2-trend` (`orange-bar-58985004`, `aws-eu-central-1`, PG 18,
  branch `main` = `br-morning-queen-b1zibof0`), 2026-09-25'te console'dan açılmış
- ⏳ **Bekleyen: `prisma migrate dev --name init`** — `prisma/migrations/` **dizini YOK**,
  yani şema hiç migration olarak uygulanmadı (aşağıdaki 3 adım)

### Düzeltme: kapılar "credentialsuz" değil, "secret'sız" (2026-10-03)

Eski durum satırı `prisma validate` + `prisma generate`'ı *credentialsuz* kapı olarak
listeliyordu. Bu **yanlıştı**: `prisma.config.ts` URL'yi `env('DATABASE_URL')` ile
config modülü yüklenirken çözdüğü için, `DATABASE_URL` tanımlı değilken ikisi de

```
PrismaConfigEnvError: Cannot resolve environment variable: DATABASE_URL.
```

ile düşüyor. **Bağlantı gerekmez** — herhangi bir sözdizimsel olarak geçerli bir URL
(ölçümde dummy değer kullanıldı) ikisini de geçirir (`schema is valid` / client üretildi).
Yani doğru ifade: *gerçek kimlik bilgisi gerektirmez, ama `DATABASE_URL` ortam
değişkeninin tanımlı olmasını gerektirir.* CI'da secret'sız koşacaksa bu ayrım önemli.

## Yapılacak 3 adım

```bash
cd apps/trend-db
neon env pull                    # DATABASE_URL (pooled) + DATABASE_URL_UNPOOLED üretir → .env'e
DATABASE_URL="$DATABASE_URL_UNPOOLED" npx prisma migrate dev --name init
npm run load                     # TCC-mirror history.jsonl → TrendRun (idempotent upsert, pooled)
```

`neon env pull` çalışmak için hesap gerektirir; ölçümde hesap **zaten** vardı
(`neon profile list` → `DEFAULT`, `account` UUID dolu, `file: ok`), yani `neon login`
adımı artık gerekmiyor — yalnızca bu dizinde bağlam (`neon link`) eksik.

### Canlı projede ÜÇ rol var (2026-10-03 ölçümü)

`neondb_owner`'a ek olarak `trend_service` ve `trend_anon` rolleri 2026-09-28'de
ayrılmış; `trend_anon` `no_login` (parolasız). Bu iki rol `.env.example`'a ve
bu dosyaya daha önce hiç yazılmamıştı — niyetleri yalnız canlı veritabanında
duruyordu. **GRANT'leri ölçülemedi** (`neon psql` bu ortamda `psql` binary'si
bulamadı, gömülü TypeScript istemcisi zaman aşımına uğradı; `neon sql` CLI 5.0.0'da
yok). RLS/least-privilege tasarımı varsayımı **doğrulanmadan** bu rollere
bağlanma; önce GRANT'leri oku.

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
- **DOĞRULANMADI (2026-10-03):** `prisma/migrations/` dizinin olmaması, depodaki
  şemanın hiç migration olarak uygulanmadığını gösterir — ama canlı veritabanında
  `trend_runs` tablosunun **var olup olmadığı** ölçülemedi (bkz. yukarıdaki rol notu:
  canlı SQL okunamadı). `npx prisma migrate dev` hâlâ çalıştırılmalı; schema'yı
  push etmeden önce canlı tabloları doğrula.
