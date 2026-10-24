import { API_BASE } from "@/lib/preview";

// `/api/events` — preview_server'ın SSE akışını panoya SUNAN TARAMA KATMANI.
//
// Neden bu katman var (ölçüldü 2026-09-28):
//   preview_server SSE ucu `/api/run`'dır (`/api/events` YOK — rota tablosunda
//   böyle bir yol yok; yalnız test fixture'ında geçen sahte bir HTTP haritası).
//   Tarayıcı preview_server'a DOĞRUDAN bağlanamaz: sunucu hiçbir
//   `Access-Control-*` başlığı göndermiyor (grep: 0 eşleşme), pano ise
//   başka bir origin'de (localhost:3000). CORS'suz bir yanıt tarayıcı tarafından
//   okunamaz — EventSource açılsa bile ilk `message` gelmez.
//   Bu yüzden akış SUNUCU TARAFINDA tünelir: tarayıcı aynı origin'deki
//   `/api/events`'e bağlanır, Next upstream'e bağlanır. preview_server'a
//   DOKUNULMAZ (CORS eklemek yerine) — sınır tarayıcıda değil, sunucuda kalır.
//
// Zenginleştirme: upstream olayı yalnız verdict snapshot'ı taşır; trend
// geçmişi ayrı uçtan (`/api/trend`) gelir. İstemci iki ayrı istek yapmasın
// diye her olayda trend bir kez sunucu tarafında okunup birleştirilir — tek
// akış, tek tur, tarayıcıdan tek istek.
//
// Okuma SÖZLEŞMESİ (istemci `LiveEvent` diye adlandırır):
//   { ts, verdict, p0, p1, budget_usd, budget_limit, …  // snapshot alanları
//     trend: { history: TrendRow[] } }
// Sunucu kapanırsa `event: error` yayınlanır; istemci SSR verisinde kalır
// (canlı olmak zorunlu değil — sayfa yine doğru render edilir).

export const dynamic = "force-dynamic";
// Akış sunucu tarafında tünelir; Edge runtime'da upstream fetch + uzun ömürlü
// okuma daha kırılgan. Node runtime açıkça sabitlenir.
export const runtime = "nodejs";

/** Yukarı akışın okuma sırasında takılı kalmaması için güvenlik tavanı. */
const UPSTREAM_TIMEOUT_MS = 15_000;

type Snapshot = Record<string, unknown>;

function eventChunk(name: string, data: unknown): string {
  return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** SSE çerçevesini ayrıştırır: `(event adı, data metni)` ya da null. */
function parseFrame(frame: string): { name: string; data: string } | null {
  // Yorum satırı (`: keepalive`) veri taşımaz — istemciye iletmeye değmez.
  if (frame.startsWith(":")) return null;
  let name = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  return { name, data: dataLines.join("\n") };
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const rawLimit = Number(url.searchParams.get("limit") ?? "20");
  // Pencere tüketicinin; sunucu bunu yalnız upstream'e geçirir. Sınır
  // koyulur çünkü bu değer upstream sorgu dizesine giriyor (serbest bırakılırsa
  // beklenmedik bir pencere talebi çıkar).
  const limit = Number.isFinite(rawLimit)
    ? Math.min(Math.max(Math.trunc(rawLimit), 1), 200)
    : 20;

  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      let upstream: AbortController | null = null;
      const close = (chunk: string) => {
        try {
          controller.enqueue(encoder.encode(chunk));
        } catch {
          /* istemci ayrıldı — yazma yutulur */
        }
      };
      try {
        upstream = new AbortController();
        // İstemci sekmeyi kapatırsa upstream bağlantısı da düşsün: ters yönde
        // sızan bir akış, preview_server'ın SSE client listesini şişirir.
        const onAbort = () => upstream?.abort();
        request.signal.addEventListener("abort", onAbort);

        const res = await fetch(`${API_BASE}/api/run`, {
          cache: "no-store",
          signal: upstream.signal,
          headers: { Accept: "text/event-stream" },
        });
        if (!res.ok || !res.body) {
          close(
            eventChunk("error", {
              message: `upstream /api/run → HTTP ${res.status}`,
            })
          );
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let boundary = buffer.indexOf("\n\n");
          while (boundary !== -1) {
            const frame = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            const parsed = parseFrame(frame);
            if (parsed) {
              let snapshot: Snapshot = {};
              try {
                snapshot = JSON.parse(parsed.data) as Snapshot;
              } catch {
                snapshot = {};
              }
              // Trend her olayda BİR kez okunur ve akışa iliştirilir.
              let trend: { history: unknown[] } = { history: [] };
              try {
                const trendRes = await fetch(
                  `${API_BASE}/api/trend?limit=${limit}`,
                  {
                    cache: "no-store",
                    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
                  }
                );
                if (trendRes.ok) {
                  trend = (await trendRes.json()) as { history: unknown[] };
                }
              } catch {
                // Trend okunamazsa: snapshot YİNE gönderilir. Canlılık tek
                // dikişin geçici kaybına bağlı olmamalı; ekranda eski trend
                // kalır, verdict tazelenir.
              }
              close(eventChunk("snapshot", { ...snapshot, trend }));
            }
            boundary = buffer.indexOf("\n\n");
          }
        }
      } catch (error) {
        close(eventChunk("error", { message: String(error) }));
      } finally {
        try {
          controller.close();
        } catch {
          /* zaten kapalı */
        }
      }
    },
    cancel() {
      /* istemci ayrıldı; upstream `abort` dinleyicisi akışı düşürür */
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      // `no-store` zorunlu: aksi halde ara katman tamponlayıp "canlı" akışı
      // ölü bir anlık görüntüye çevirir.
      "Cache-Control": "no-store",
      Connection: "keep-alive",
      // nginx/proxy tamponlamasını kapatır (upstream ile aynı başlık).
      "X-Accel-Buffering": "no",
    },
  });
}
