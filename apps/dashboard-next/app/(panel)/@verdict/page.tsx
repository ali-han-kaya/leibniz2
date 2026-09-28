import { ViewTransition } from "react";

import VerdictCard from "../../VerdictCard";

// Paralel rota slotu (`app/(panel)/@verdict`) — ana panonun verdict paneli.
//
// Kendi `loading.tsx`'i olduğu için Next bu slotu AYRI bir Suspense sınırına
// alır: iskelet anında akar, kart verisi geldiğinde yalnız bu sınır değişir.
// `@trend` slotu yavaş olsa bile bu panel beklemez (ve tersi).
//
// `force-dynamic` slot-seviyesinde tekrarlanır: paralel rotalar ayrı segment
// ağacıdır, grup sayfasının config'ini miras almaz.
export const dynamic = "force-dynamic";

export default function VerdictSlot() {
  // Suspense reveal (gezinme haritası maddesi): iskelet (slot loading.tsx)
  // HIZLI çıkar (slot-exit), gerçek kart yumuşak ve GECİKMELİ girer
  // (slot-enter) — CSS anahtar kareleri globals.css'te. `default: "none"`
  // bu sınırı navigasyon crossfade'inden AYRIR: kart, yalnız kendi
  // Suspense çözülümünde animasyonlu olur (yönsüz geçişte içerik zaten
  // root sarmalayıcıyla crossfade olur).
  return (
    <ViewTransition
      enter={{ "slot-enter": "slot-enter", default: "none" }}
      exit={{ "slot-exit": "slot-exit", default: "none" }}
      default="none"
    >
      <VerdictCard />
    </ViewTransition>
  );
}
