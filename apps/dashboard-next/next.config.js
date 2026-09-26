/** @type {import('next').NextConfig} */
const path = require("node:path");

// Neon kimlik bilgisi TEK yerde dursun: `apps/trend-db/.env` (neon env pull'un
// yazdigi dosya). Kimligi dashboard-next'e kopyalamak ayni parolayi iki dosyada
// tutmak olurdu; burada okuyup surec ortamina koyuyoruz.
//
// process.loadEnvFile Node >= 20.12 API'sidir (ek bagimlilik yok). Dosya yoksa
// (orn. sadece preview kaynagiyla calisan bir makine) sessizce gec: env zaten
// disaridan da verilebilir. Var olan ortam degiskenleri EZILMEZ — kabuk/CI
// degeri kazanir.
if (!process.env.DATABASE_URL) {
  try {
    process.loadEnvFile(path.join(__dirname, "..", "trend-db", ".env"));
  } catch {
    // .env yok — TREND_SOURCE=preview'a duser (bkz. lib/preview.ts).
  }
}

const nextConfig = {
  // PREVIEW_API runtime env'dir (lib/preview.ts — NEXT_PUBLIC_ öneksiz, bilinçli):
  // server fetch URL'i build'e gömülmemeli, aksi halde `next start` sonrası
  // override etmek hiçbir şeyi değiştirmez. Varsayılan: preview_server sözleşmesi.
  // (NEXT_PUBLIC_PREVIEW_API okunmaz — yalnızca mevcut kullanıları kırmamak için
  // ignoredKeys değil, tamamen kaldırıldı.)
  //
  // TREND_SOURCE / DATABASE_URL de aynı sınıftadır: sunucu tarafı runtime.

  // `pg` yerel bir TCP soketi açar ve Next'in paketleyicisine girerse sürümü
  // çakışabildiği için dışta tutulur (Next'in pg için önerdiği ayar). Prisma
  // istemcisi ise apps/trend-db/generated'dan TS kaynağı olarak gelir ve
  // derlenmesi gerekir — dışta TUTULMAZ.
  serverExternalPackages: ["pg"],
};

module.exports = nextConfig;
