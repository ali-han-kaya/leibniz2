import RunsTable from "@/components/RunsTable";

// Paralel rota slotu (`app/(panel)/@trend`) — ana panonun kompakt koşum geçmişi.
// Tam liste `/trend` sayfasında; burada pencere küçük tutulur ki panel
// panonun altında hızlı akan (dolayısıyla erken gelen) bir özet olsun.
//
// `force-dynamic` gerekçesi: bkz. app/@verdict/page.tsx.
export const dynamic = "force-dynamic";

export default function TrendSlot() {
  return <RunsTable title="Son 5 Koşum" limit={5} />;
}
