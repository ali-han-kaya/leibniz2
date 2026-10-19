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

// Tel şekli tek kaynaktan gelir: _calisma/CIKTI/preview_contract.schema.json →
// lib/preview-contract.generated.ts (elle düzenlenmez). Alanlar düz JSON'dur
// (iç içe `z3` nesnesi yok); preview ve DB yolu aynı tipi paylaşır.
import type {
  HistoryRow,
  Latest,
  TrendResponse,
} from "./preview-contract.generated";

export type { Latest };

/**
 * Trend satırının panonun okuduğu alt kümesi. Tam `HistoryRow` şeması (19 alan)
 * şemada durur; bu tip tüketici sözleşmesini (6 alan) dar tutar.
 */
export type TrendRow = Pick<
  HistoryRow,
  "ts" | "p0" | "p1" | "duration_s" | "budget_usd" | "z3_total"
>;

/**
 * Refs grafiğinin okuduğu alt küme. `TrendRow`dan AYRI: tablo sözleşmesi
 * (6 alan) tip testinde dondurulmuş, refs alanları oraya eklenirse o sözleşme
 * genişler. Grafik kendi dar kümesini ister — aynı tel yanıtından okunur.
 */
export type RefsRow = Pick<
  HistoryRow,
  "ts" | "refs_verified" | "refs_total" | "refs_mismatch" | "refs_by_source"
>;

/**
 * Koşumlar arası karşılaştırmanın okuduğu alt küme (süre/bütçe paneli).
 *
 * `TrendRow`dan AYRI: tablo sözleşmesi 6 alan olarak dondurulmuş, karşılaştırma
 * `budget_limit` + `verdict` ister. Aynı tel yanıtından okunur; DB yolunda ek
 * sorgu yok (tek `findMany` satırından üç görünüm türetilir).
 */
export type CompareRow = Pick<
  HistoryRow,
  | "ts"
  | "verdict"
  | "p0"
  | "p1"
  | "duration_s"
  | "budget_usd"
  | "budget_limit"
  | "z3_total"
>;

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

/**
 * Tek upstream turunda hem koşum tablosu hem refs grafiği.
 *
 * Neden ayrı kapı: `getTrend`in dönüş tipi tip testinde
 * `{ history: TrendRow[] }` olarak DONDURULMUŞ; `refs_trend` yarımı oraya
 * eklenirse sözleşme genişler. `/trend` sayfası bu kapıyı bir kez çağırır,
 * `getTrend` de AYNI önbellek girdisini paylaşır — ikinci bir HTTP turu yok.
 *
 * İki kaynak da iki yarımı verir: DB tek sorguda refsVerified/refsTotal
 * alanlarını da seçer (apps/trend-db şemasında VAR), preview yolu aynı
 * `history` satırlarını iki dar görünüme böler. Refs alanı null olan satırlar
 * grafikte nokta üretmez (`lib/refs-trend.ts`) — sıfır uydurulmaz.
 */
export const getTrendBundle = cache(
  async (
    limit = 20
  ): Promise<{
    history: TrendRow[];
    refs: RefsRow[];
    compare: CompareRow[];
  }> => {
    if (trendSource() === "db") {
      const { getTrendFromDb } = await import("./trend-db");
      return getTrendFromDb(limit);
    }
    const body = await getJson<TrendResponse>(`/api/trend?limit=${limit}`);
    // Preview yolu aynı `HistoryRow` satırlarını üç dar görünüme böler —
    // karşılaştırma alanları tel sözleşmesinde zaten var (`budget_limit`,
    // `verdict`), ikinci bir istek yok.
    return { history: body.history, refs: body.history, compare: body.history };
  }
);

export const getTrend = cache(
  async (limit = 20): Promise<{ history: TrendRow[] }> => {
    const { history } = await getTrendBundle(limit);
    return { history };
  }
);

/**
 * K0-K21 katman fotoğrafı + P0/P1 bulgu ayrıntısı — iki kaynak, tek şekil.
 *
 *   db      → `trend_runs.layers` / `trend_runs.findings` (son satır).
 *   preview → `/api/latest.layers` + `findings` (verify_delivery.py'nin
 *             `--klayers-out` çıktısıyla aynı `build_layers_summary`).
 *
 * `source` ve `ts` sonuçla BİRLİKTE döner: pano hangi arşivi gösterdiğini
 * yazmadan "son koşum" dememeli (DB satırı bayat olabilir). Veri yoksa/erişilemezse
 * `ok: false` + sebep döner; pano sessizce boşalmaz ("0 katman" ile "veri yok"
 * aynı ekran olmamalı).
 */
export type LayersResult =
  | {
      ok: true;
      source: TrendSource;
      ts: string | null;
      verdict: string | null;
      layers: Record<string, unknown>;
      findings: unknown;
    }
  | { ok: false; source: TrendSource; reason: string };

export const getLayers = cache(async (): Promise<LayersResult> => {
  const source = trendSource();
  if (source === "db") {
    const { getLayersFromDb } = await import("./trend-db");
    return getLayersFromDb();
  }
  try {
    const raw = await getJson<{
      layers?: unknown;
      verdict?: unknown;
      ts?: unknown;
      findings?: unknown;
    }>("/api/latest");
    const layers = raw.layers;
    if (!layers || typeof layers !== "object" || Array.isArray(layers)) {
      return {
        ok: false,
        source,
        reason: "preview_server /api/latest katman alanı yayınlamıyor",
      };
    }
    return {
      ok: true,
      source,
      ts: typeof raw.ts === "string" ? raw.ts : null,
      verdict: typeof raw.verdict === "string" ? raw.verdict : null,
      layers: layers as Record<string, unknown>,
      findings: raw.findings ?? [],
    };
  } catch (error) {
    return {
      ok: false,
      source,
      reason: `veri kaynağına ulaşılamadı: ${String(error)}`,
    };
  }
});
