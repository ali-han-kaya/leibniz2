// Veri katmanı — Server Component'ler buradan okur (colocated fetching).
//
// İki kaynak var; sözleşme (Latest / TrendRow) tek:
//   1. `db`      → Neon Postgres `trend_runs` (apps/trend-db şeması, üretilmiş
//                  Prisma istemcisi üzerinden). Kalıcı trend geçmişi burada.
//   2. `preview` → preview_server.py'nin 7 salt-okuma GET ucu (canlı koşum,
//                  koşum sürerken tazelenen veri).
// Seçim TREND_SOURCE env'i ile: "db" | "preview". Set değilse DATABASE_URL
// varsa db'ye, yoksa preview'a düşer — böylece DB parolası olmayan bir makinede
// pano çalışmaya devam eder.
//
// PREVIEW_API bilinçli olarak NEXT_PUBLIC_ öneksizdir: sunucu tarafı runtime
// değişkenidir. NEXT_PUBLIC_* build zamanında client bundle'a gömülür; sunucu
// fetch'ini `next start` sonrasında override etmek çalışmaz (Next.js docs:
// "Next.js can only inline environment variables that are used with a
// $ prefix in the bundle"). Server Components'te env'e $ önekiyle
// referans vermediğimiz için değer her istekte runtime'dan okunur.

import { cache } from "react";

export const API_BASE = process.env.PREVIEW_API ?? "http://127.0.0.1:8000";

export type Latest = {
  verdict?: string;
  ts?: string;
  p0?: number;
  p1?: number;
  stripped_sha256?: string;
  // preview_server /api/latest Z3'yi düz alan olarak yayınlar (z3_passed /
  // z3_total / z3_failed) — iç içe `z3` nesnesi YOK. Trend satırları da aynı
  // düz şekli kullanır (z3_total); tek sözleşmede kal.
  z3_passed?: number;
  z3_total?: number;
  z3_failed?: number;
  budget_usd?: number;
  budget_limit?: number;
};

export type TrendRow = {
  ts?: string;
  p0?: number;
  p1?: number;
  duration_s?: number;
  budget_usd?: number;
  z3_total?: number;
};

async function getJson<T>(path: string, revalidate = 0): Promise<T> {
  // Dynamic istek: pano gerçek-zamanlı verdict gösterir (cache: no-store).
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`preview_server ${path} → HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export type TrendSource = "db" | "preview";

/** Etkin veri kaynağı. `TREND_SOURCE` açıkça verilmişse o kazanır. */
export function trendSource(): TrendSource {
  const explicit = process.env.TREND_SOURCE;
  if (explicit === "db" || explicit === "preview") return explicit;
  return process.env.DATABASE_URL ? "db" : "preview";
}

// server-cache-react: istek-basi dedup. fetch memoization no-store isteklerde
// calismaz (yalniz force-cache/default); cache() bunu kusar — ayni istekte
// birden fazla kart/bilesen ayni uca tek round-trip ile baglanir. DB dalinda
// da ayni yarar var: iki bilesen tek sorgu paylasir.
//
// `db` modulu dinamik yuklenir: preview modunda Prisma/pg hic acilmaz (soguk
// baslangic ve bagimlilik yuzeyi kucuk kalir).
export const getLatest = cache(async (): Promise<Latest> => {
  if (trendSource() === "db") {
    const { getLatestFromDb } = await import("./trend-db");
    return getLatestFromDb();
  }
  return getJson<Latest>("/api/latest");
});

export const getTrend = cache(
  async (limit = 20): Promise<{ history: TrendRow[] }> => {
    if (trendSource() === "db") {
      const { getTrendFromDb } = await import("./trend-db");
      return getTrendFromDb(limit);
    }
    return getJson<{ history: TrendRow[] }>(`/api/trend?limit=${limit}`);
  }
);
