// Prisma 7: datasource URL burada çözülür (schema'da url yok) — kanonik şekil
// skill reference'ından (references/postgresql.md) alındı.
//
// Neon pooled/direct ayrımı (skill: neon-postgres), Prisma 7'ye uyarlandı:
// Prisma 5/6'daki `directUrl = env(...)` YANLIŞ burada — ölçüldü (2026-10-03):
//
//   error: The datasource property `directUrl` is no longer supported in schema
//   files. Move connection URLs to `prisma.config.ts`.   [P1012]
//
// @prisma/config 7.10.0 `Datasource` tipi de yalnız { url, shadowDatabaseUrl }
// taşıyor. Yani "migration direct, uygulama pooled" ayrımı schema'da iki
// URL ile DEĞİL, config/çalışma zamanı arasında ayrı URL'lerle kurulur:
//
//   - BU DOSYA (yalnız Prisma CLI okur: migrate / db pull / studio / validate)
//     -> direct. Neon skill: "Use a direct (non-pooled) connection string when
//     you run the migration." Havuzda migration = `prepared statement "s0"
//     already exists`, kaybolan `SET search_path`, ara sıra SQLSTATE 25006.
//   - scripts/load.ts (adapter'ı kendisi kurar) -> POOLED `DATABASE_URL`.
//     Uygulama trafiği her zaman havuzda kalır; havuz migration boyunca
//     "geçici olarak değiştirmek" yerine burada hiç devreye girmez.
//
// Sıra: DATABASE_URL_UNPOOLED (neon env pull'un ürettiği doğrudan bağlantı)
// > DATABASE_URL. Yedek yol yalnız geliştirme kolaylığı; canlıda ikisi de
// tanımlıysa direct kazanır.
import 'dotenv/config';
import { defineConfig } from 'prisma/config';

const unpooled = process.env.DATABASE_URL_UNPOOLED;
const pooled = process.env.DATABASE_URL;

const datasourceUrl = unpooled ?? pooled;

if (!datasourceUrl) {
  throw new Error(
    'Neon bağlantısı yok. `neon env pull` çalıştırın — DATABASE_URL (pooled) ' +
      've DATABASE_URL_UNPOOLED (direct) ikisini de .env üretir.'
  );
}

if (!unpooled && pooled) {
  // Sessizce havuz üzerinden migration koşmaktansa, kırılmasını beklemeden
  // söyle: hata "prepared statement already exists" olarak çok geç ve yanıltıcı
  // gelir, havuzdan kaynaklanan nedenselliği göstermez.
  console.warn(
    '[neon] DATABASE_URL_UNPOOLED yok — Prisma CLI bu bağlantıyla çalışıyor. ' +
      'Migration POOLED (-pooler) bağlantı üzerinden koşuyorsa ' +
      '"prepared statement s0 already exists" / 25006 hataları çıkabilir. ' +
      '`neon env pull` ile direct bağlantıyı da alın.'
  );
}

export default defineConfig({
  schema: 'prisma/schema.prisma',
  datasource: {
    url: datasourceUrl,
  },
});
