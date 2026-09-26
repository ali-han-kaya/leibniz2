// Panel rota grubu — paralel rota slotlarının KAPSAMI.
//
// Slotlar neden kök layout'ta değil: kök layout'a konsaydı `/trend` gibi
// eşleşmeyen rotalarda da devrede olurlardı ve Next'in paralel rota
// semantiği gereği soft navigasyonda slotlar ÖNCEKİ durumlarını korurdu —
// yani ana panodan `/trend`'e geçildiğinde verdict kartı ve kompakt tablo
// tam sayfa tablonun üstünde kalırdı. Rota grubu (`(panel)`) URL'yi
// değiştirmez ama layout'u yalnız bu alt ağaca uygular; `/trend` grubun
// dışında olduğu için slotları hiç görmez.
//
// Her slotun kendi `loading.tsx`'i var → Next her slotu AYRI Suspense
// sınırına alır: iki panel birbirini beklemeden bağımsız akar.
export default function PanelLayout({
  children,
  verdict,
  trend,
}: {
  children: React.ReactNode;
  verdict: React.ReactNode;
  trend: React.ReactNode;
}) {
  // Sıra bilinçli: paneller önce, sayfaya özel içerik (`children`) sonra.
  // Bu grupta children `/` rotasının bağlantı satırıdır ve panellerin
  // altında durmalı. `space-y-6` null render eden slotları atlar.
  return (
    <div className="space-y-6">
      {verdict}
      {trend}
      {children}
    </div>
  );
}
