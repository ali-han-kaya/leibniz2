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
  return <VerdictCard />;
}
