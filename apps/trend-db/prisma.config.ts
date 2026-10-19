// Prisma 7: datasource URL burada çözülür (schema'da url yok) — kanonik şekil
// skill reference'ından (references/postgresql.md) alındı.
// Neon sözleşmesi (skill: neon-postgres): DATABASE_URL = pooled (-pooler) —
// uygulama/migration CLI trafiği için; büyük dump/replication için direct gerekir.
import "dotenv/config";
import { defineConfig, env } from "prisma/config";

export default defineConfig({
  schema: "prisma/schema.prisma",
  datasource: {
    url: env("DATABASE_URL"),
  },
});
