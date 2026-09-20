/** @type {import('next').NextConfig} */
const nextConfig = {
  // PREVIEW_API runtime env'dir (lib/preview.ts — NEXT_PUBLIC_ öneksiz, bilinçli):
  // server fetch URL'i build'e gömülmemeli, aksi halde `next start` sonrası
  // override etmek hiçbir şeyi değiştirmez. Varsayılan: preview_server sözleşmesi.
  // (NEXT_PUBLIC_PREVIEW_API okunmaz — yalnızca mevcut kullanıları kırmamak için
  // ignoredKeys değil, tamamen kaldırıldı.)
};

module.exports = nextConfig;
