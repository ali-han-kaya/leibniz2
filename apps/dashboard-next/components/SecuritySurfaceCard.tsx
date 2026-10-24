import { headers } from "next/headers";

import { Badge } from "@/components/ui/badge";
import {
  PanelCard,
  PanelCardContent,
  PanelCardHeader,
  PanelCardTitle,
} from "@/components/PanelCard";
import { cardStack, defenseBadge, microLabel } from "@/components/panel-style";
import {
  defenseStateLabel,
  parseSecuritySurface,
  type SecuritySurface,
} from "@/lib/security-surface";

// Güvenlik yüzeyi kartı — `/api/health`in `security` bölümünün küçük görünümü.
//
// Neden `/api/health` üzerinden (tek-kaynak import yerine): kartın gösterdiği
// şey iddia değil GÖZLEM olmalı. Ucun gövdesini okumak, "panel ile health aynı
// şeyi söylüyor mu" sorusunu kendiliğinden yanıtlar; yalnız fonksiyonu import
// etseydik uç bozulsa bile kart yeşil kalabilirdi.
//
// Neden kendi ucumuzu mutlak URL ile çağırıyoruz: sunucu tarafında göreli
// adres çalışmaz (`fetch("/api/health")` Node'da geçersiz). Adres isteğin
// `Host` başlığından türetilir, yani hangi portta/alan adında koşarsa koşsun
// aynı süreçteki uca gider. Yerel `NEXT_PUBLIC_BASE_URL` idiomuna
// güvenilmedi: o değişken bu repoda HİÇBİR yerde tanımlı değil (ölü yol).
//
// Gövde `parseSecuritySurface`ten geçer: tanınmayan durum yeşile değil
// `unknown`a düşer. Uç okunamazsa kart "bilinmiyor" der — boş listeyi
// "hepsi aktif" diye basmak güvenlik panelindeki en pahalı yanlış-pozitif
// olurdu.
async function readSurface(): Promise<SecuritySurface | null> {
  const host = (await headers()).get("host");
  if (!host) return null;
  try {
    const res = await fetch(`http://${host}/api/health`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    return parseSecuritySurface(await res.json());
  } catch {
    return null;
  }
}

export default async function SecuritySurfaceCard() {
  const surface = await readSurface();
  const known = surface !== null && surface.length > 0;

  return (
    <PanelCard>
      <PanelCardHeader>
        <PanelCardTitle>Güvenlik Yüzeyi</PanelCardTitle>
        {/* Kaynak satırı kartın kendisinde yazılı: aynı sayılar iki yüzeyden
            (uç ve kart) gelebilir, hangisinin basıldığı görünmeli. */}
        <span className={microLabel()}>
          {known ? `${surface.length} kapı · /api/health` : "/api/health"}
        </span>
      </PanelCardHeader>

      <PanelCardContent>
        {known ? (
          <ul className={cardStack()}>
            {surface.map((defense) => (
              <li
                key={defense.id}
                className="flex flex-wrap items-baseline gap-x-(--panel-block-gap) gap-y-(--panel-tight-gap)"
              >
                <span className="text-sm text-fg">{defense.label}</span>
                <Badge className={defenseBadge({ state: defense.state })}>
                  {defenseStateLabel(defense.state)}
                </Badge>
                <span className="font-mono text-xs text-muted">
                  {defense.detail}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          // Okunamayan yüzey bir DURUM mesajıdır: `role="status"`.
          // "Hepsi aktif" varsayımı yapılmaz; listelenemeyen kapı, kapalı
          // varsayılan kapıdır.
          <p className="text-sm text-muted" role="status">
            güvenlik yüzeyi okunamadı — durum {defenseStateLabel("unknown")}
          </p>
        )}
      </PanelCardContent>
    </PanelCard>
  );
}
