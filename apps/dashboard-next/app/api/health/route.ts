import { securitySurface } from "@/lib/security-surface";

// Sağlık ucu = panonun **güvenlik yüzeyi** de olur: hangi kapı hangi durumda.
// Durum burada ÜRETİLMEZ, `lib/security-surface.ts`ten gelir (tek kaynak) —
// uç yalnız ortamı verir. Böylece panel, testler ve uç aynı kararı okur;
// id/durum literalleri bu dosyada TEKRARLANMAZ.
export async function GET() {
  return Response.json({
    status: "ok",
    archil: "/mnt/archil",
    a11y: "gate-ready",
    security: securitySurface(),
  });
}
