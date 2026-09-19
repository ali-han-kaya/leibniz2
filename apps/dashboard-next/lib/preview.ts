// Veri katmanı — Server Component'ler buradan okur (colocated fetching).
// Kaynak: preview_server.py sözleşmesi (7 salt-okuma GET ucu).
//
// PREVIEW_API bilinçli olarak NEXT_PUBLIC_ öneksizdir: sunucu tarafı runtime
// değişkenidir. NEXT_PUBLIC_* build zamanında client bundle'a gömülür; sunucu
// fetch'ini `next start` sonrasında override etmek çalışmaz (Next.js docs:
// "Next.js can only inline environment variables that are used with a
// $ prefix in the bundle"). Server Components'te env'e $ önekiyle
// referans vermediğimiz için değer her istekte runtime'dan okunur.

export const API_BASE = process.env.PREVIEW_API ?? "http://127.0.0.1:8000";

export type Latest = {
  verdict?: string;
  ts?: string;
  p0?: number;
  p1?: number;
  stripped_sha256?: string;
  z3?: { pass?: number; total?: number };
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

export function getLatest(): Promise<Latest> {
  return getJson<Latest>("/api/latest");
}

export function getTrend(limit = 20): Promise<{ history: TrendRow[] }> {
  return getJson<{ history: TrendRow[] }>(`/api/trend?limit=${limit}`);
}
