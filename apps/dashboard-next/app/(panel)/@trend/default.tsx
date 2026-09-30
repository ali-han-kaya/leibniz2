// Paralel rota slotunun VARSAYILAN durumu.
//
// Bugün panel grubunda tek rota var (`/`), yani bu slot her zaman eşleşir ve
// bu dosya hiç devreye girmez. Yine de duruyor: gruba ikinci bir sayfa
// eklendiğinde, eşleşmeyen slot için `default.tsx` yoksa Next 404 döndürür ve
// o sayfa tümden düşer. Varsayılan davranış "hiçbir şey render etme"dir.
export default function TrendDefault() {
  return null;
}
