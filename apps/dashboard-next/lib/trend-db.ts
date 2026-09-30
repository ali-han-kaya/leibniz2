// Neon Postgres okuma katmanı — `apps/trend-db` şemasının üretilmiş istemcisi.
//
// Neden HTTP değil de doğrudan DB: `trend_runs` tablosu şemanın TEK kaynağı
// (`apps/trend-db/prisma/schema.prisma`); buradan okumak `test_trend_db_contract`
// drift-guard'ının kapsadığı sözleşmeyi tüketir. Ayrı bir elle yazılmış SQL
// katmanı üçüncü bir tüketici doğurur ve guard'ın dışında kalırdı.
//
// Neon sözleşmesi: DATABASE_URL = POOLED (-pooler). Uygulama trafiği buraya
// gider; migration/replication direct URL ister (bkz. apps/trend-db/README.md).
//
// Bu modül YALNIZCA sunucu tarafında çalışır (Server Component) — istemci
// paketine sızmaz; `pg` ve Prisma runtime `serverExternalPackages`'ta.

import { cache } from "react";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "../../trend-db/generated/client";
import type { Latest, TrendRow } from "./preview";

// Decimal (budget_usd / budget_limit) düz `number`'a iner: kartlar ve tablo
// sayı biçimlendiriyor, Decimal.js nesnesi React'te render edilemez.
type Decimalish = { toNumber(): number } | number | string | null;

function num(v: Decimalish | undefined): number | undefined {
  if (v === null || v === undefined) return undefined;
  if (typeof v === "number") return v;
  if (typeof v === "string") return Number(v);
  return v.toNumber();
}

// Next dev'de modül yeniden yüklenirken her seferinde yeni bir bağlantı havuzu
// açılmasın: istemciyi globalThis'te tekleştir (Prisma'nın Next için önerdiği
// örüntü).
const globalForTrendDb = globalThis as unknown as {
  __trendDb?: PrismaClient;
};

export function trendDb(): PrismaClient {
  if (!globalForTrendDb.__trendDb) {
    const connectionString = process.env.DATABASE_URL;
    if (!connectionString) {
      throw new Error(
        "DATABASE_URL yok — apps/trend-db/.env gerekli (neon env pull)"
      );
    }
    const adapter = new PrismaPg({ connectionString });
    globalForTrendDb.__trendDb = new PrismaClient({ adapter });
  }
  return globalForTrendDb.__trendDb;
}

// server-cache-react: aynı istekte iki kart aynı satırı isterse tek sorgu.
export const getLatestFromDb = cache(async (): Promise<Latest> => {
  const row = await trendDb().trendRun.findFirst({
    orderBy: { ts: "desc" },
  });
  if (!row) return { verdict: "UNKNOWN" };
  return {
    verdict: row.verdict,
    ts: row.ts.toISOString(),
    p0: row.p0,
    p1: row.p1,
    stripped_sha256: row.strippedSha256 ?? undefined,
    z3_passed: row.z3Passed ?? undefined,
    z3_total: row.z3Total ?? undefined,
    z3_failed: row.z3Failed ?? undefined,
    budget_usd: num(row.budgetUsd),
    budget_limit: num(row.budgetLimit),
  };
});

// Sıra sözleşmesi: `history` **eskiden yeniye** döner (preview_server
// `/api/trend` ile aynı). app/trend/page.tsx pencereyi `slice(-limit).reverse()`
// ile kendisi kısıyor — azalan dönerseydik sayfa sessizce EN ESKİ 20'yi
// "son 20" diye gösterirdi.
export const getTrendFromDb = cache(
  async (limit = 20): Promise<{ history: TrendRow[] }> => {
    // En yeni `limit` kaydı çek (desc + take), sonra tüketici sözleşmesi için
    // artan sıraya çevir.
    const rows = await trendDb().trendRun.findMany({
      orderBy: { ts: "desc" },
      take: limit,
    });
    rows.reverse();
    return {
      history: rows.map((r) => ({
        ts: r.ts.toISOString(),
        p0: r.p0,
        p1: r.p1,
        duration_s: r.durationS ?? undefined,
        budget_usd: num(r.budgetUsd),
        z3_total: r.z3Total ?? undefined,
      })),
    };
  }
);
