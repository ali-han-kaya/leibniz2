// Veri katmanı — Server Component'ler buradan okur (colocated fetching).
// Kaynak: preview_server.py sözleşmesi (7 salt-okuma GET ucu).
//
// PREVIEW_API bilinçli olarak NEXT_PUBLIC_ öneksizdir: sunucu tarafı runtime
// değişkenidir. NEXT_PUBLIC_* build zamanında client bundle'a gömülür; sunucu
// fetch'ini `next start` sonrasında override etmek çalışmaz (Next.js docs:
// "Next.js can only inline environment variables that are used with a
// $ prefix in the bundle"). Server Components'te env'e $ önekiyle
// referans vermediğimiz için değer her istekte runtime'dan okunur.

import { cache } from 'react';

export const API_BASE = process.env.PREVIEW_API ?? 'http://127.0.0.1:8000';

export type Latest = {
  verdict?: string;
  ts?: string;
  p0?: number;
  p1?: number;
  stripped_sha256?: string;
  z3_passed?: number;
  z3_total?: number;
  z3_failed?: number;
  z3?: { pass?: number; total?: number };
  budget_usd?: number;
  budget_limit?: number;
  layers?: Record<string, unknown>;
};

export type TrendRow = {
  ts?: string;
  p0?: number;
  p1?: number;
  duration_s?: number;
  budget_usd?: number;
  z3_total?: number;
};

export type LayersResult = {
  ok: boolean;
  source: string;
  reason?: string;
  ts?: string;
  verdict?: string;
  layers?: Record<string, unknown>;
  findings?: any[];
};

async function getJson<T>(path: string): Promise<T> {
  // Dynamic istek: pano gerçek-zamanlı verdict gösterir (cache: no-store).
  const res = await fetch(`${API_BASE}${path}`, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`preview_server ${path} → HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

// server-cache-react: istek-basi dedup. fetch memoization no-store isteklerde
// calismaz (yalniz force-cache/default); cache() bunu kusar — ayni istekte
// birden fazla kart/bilesen ayni uca tek round-trip ile baglanir.
export const getLatest = cache(
  (): Promise<Latest> => getJson<Latest>('/api/latest')
);

export const getTrend = cache(
  (limit = 20): Promise<{ history: TrendRow[] }> =>
    getJson<{ history: TrendRow[] }>(`/api/trend?limit=${limit}`)
);

export const getTrendBundle = cache(
  (limit = 20): Promise<{ history: TrendRow[]; refs: RefsRow[]; compare: CompareRow[] }> =>
    getJson<{ history: TrendRow[]; refs: RefsRow[]; compare: CompareRow[] }>(`/api/trend?limit=${limit}`)
);

// Yaşam-döngüsü olay-kaydı (logs/server_events.jsonl) — bkz.
// docs/SERVER_EVENT_LOG.md. `phase` pano için DEĞİL, sunucuda türetilir:
// çökme kararı pid'ler arası sıraya bakar, tümevarım tek yerde yaşar
// (preview_server._classify_lifecycle).
export type LifecyclePhase =
  | 'start'
  | 'recovery'
  | 'graceful'
  | 'crash'
  | 'unknown';

// Layers — /api/latest.layers verisi.
export const getLayers = cache(
  (): Promise<{ ok: boolean; reason?: string; verdict?: string; layers: Record<string, unknown>; findings: any[]; source: string; ts?: string }> =>
    getJson<{ ok: boolean; reason?: string; verdict?: string; layers: Record<string, unknown>; findings: any[]; source: string; ts?: string }>('/api/latest/layers')
);

export type CompareRow = {
  ts: string;
  duration_s?: number;
  budget_usd?: number;
  budget?: number | null;
  budget_limit?: number | null;
  p0: number;
  p1: number;
  z3?: number | null;
  z3_total?: number;
  verdict: string | null;
};

export type RefsRow = {
  ts: string;
  refs_verified: number | undefined;
  refs_total: number | undefined;
  refs_mismatch?: number;
  refs?: Record<string, string>;
  refs_by_source?: unknown;
};

// Kaynak seçimi: TREND_SOURCE (db | preview) değerini döndürür.
export const trendSource = (): "db" | "preview" => {
  const source = process.env.TREND_SOURCE ?? (typeof process.env.DATABASE_URL !== "undefined" && process.env.DATABASE_URL ? "db" : "preview");
  return ([
    "db", "preview"
  ].includes(source) ? source : "preview") as "db" | "preview";
};

export type ServerEvent = {
  ts?: string;
  event?: string;
  pid?: number;
  detail?: string;
  phase: LifecyclePhase;
};

export type ServerEvents = {
  events: ServerEvent[];
  last_crash: ServerEvent | null;
  last_recovery: ServerEvent | null;
};

export const getServerEvents = cache(
  (limit = 12): Promise<ServerEvents> =>
    getJson<ServerEvents>(`/api/server-events?limit=${limit}`)
);
