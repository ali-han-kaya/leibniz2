import { ViewTransition } from "react";

import RunsTableData from "@/components/RunsTableData";

// Paralel rota slotu (`app/(panel)/@trend`) — ana panonun kompakt koşum geçmişi.
// Tam liste `/trend` sayfasında; burada pencere küçük tutulur ki panel
// panonun altında hızlı akan (dolayısıyla erken gelen) bir özet olsun.
//
// `force-dynamic` gerekçesi: bkz. app/@verdict/page.tsx.
export const dynamic = "force-dynamic";

export default function TrendSlot() {
  // Suspense reveal sözleşmesi @verdict slotuyla AYNI (tek kural, iki slot):
  // sınıf adları globals.css'teki .slot-exit/.slot-enter pseudo-element
  // kurallarıyla eşleşir. İki slot birbirinden bağımsız animasyonlu olur —
  // Next her slotu ayrı Suspense sınırına aldığı için (bkz. grup layout'u).
  return (
    <ViewTransition
      enter={{ "slot-enter": "slot-enter", default: "none" }}
      exit={{ "slot-exit": "slot-exit", default: "none" }}
      default="none"
    >
      <RunsTableData title="Son 5 Koşum" limit={5} />
    </ViewTransition>
  );
}
