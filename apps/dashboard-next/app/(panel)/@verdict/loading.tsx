import {
  PanelCard,
  PanelCardContent,
  PanelCardHeader,
} from "@/components/PanelCard";
import { microLabel } from "@/components/panel-style";

// `@verdict` slotunun akış iskeleti. Kartın son yerleşimini (başlık satırı,
// büyük verdict, 4 istatistik) taklit eder ki veri gelince yükseklik
// zıplamasın. Kabuk VerdictCard ile AYNI bileşim (`PanelCard`) — iskelet de
// gerçek kartla aynı ölçüleri paylaşır, gövde yüksekliği zıplamaz.
// Renkler repo-token'ları; animasyon tw-animate-css'ten.
//
// Başlık satırına metin yerine nabız çubukları konur: `PanelCardHeader` bir
// YERLEŞİM yuvasıdır, içeriğini çağrı yeri seçer (o yüzden `title` prop'u
// yoktur). Böylece satır yerleşimi tek yerde kalır.
//
// `role="region"`: göç öncesi bu iskelet `<section aria-label>` idi, yani
// ADLANDIRILMIŞ bir landmark. `Card` bir `div` basıyor ve rolü olmayan
// div'de `aria-label` yok sayılır (axe `aria-prohibited-attr`) → etiket
// düşerdi. Tek öznitelikle eski semantik aynen geri geliyor; `aria-busy`
// ise her elemanda geçerlidir.
export default function VerdictLoading() {
  return (
    <PanelCard role="region" aria-busy="true" aria-label="Son koşum yükleniyor">
      <PanelCardHeader>
        <div className="h-3 w-24 animate-pulse rounded bg-border" />
        <div className="h-3 w-48 animate-pulse rounded bg-border" />
      </PanelCardHeader>
      <PanelCardContent>
        <div className="mt-5 h-12 w-44 animate-pulse rounded bg-border" />
        <dl className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {["P0", "P1", "Z3", "STRIPPED"].map((label) => (
            <div key={label} className="bg-bg">
              <dt className={microLabel()}>{label}</dt>
              <dd className="mt-1">
                <div className="h-4 w-full animate-pulse rounded bg-border" />
              </dd>
            </div>
          ))}
        </dl>
      </PanelCardContent>
    </PanelCard>
  );
}
