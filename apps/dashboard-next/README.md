# dashboard-next

Doğrulama zinciri mini panosu — `preview_server.py`'nin salt-okuma API'sini
Next.js App Router desenleriyle okur. (`apps/dashboard-shadcn` Vite SPA'sının
RSC'li kardeşi; ikisi birbirinin yerine geçmez.)

## Çalıştırma

```bash
cd apps/dashboard-next
npm install
npm run build && npm start          # prod (önerilen kanal)
# veya: npm run dev
```

API hedefi (runtime, build'de gömülmez):

```bash
PREVIEW_API=http://127.0.0.1:8000 npm start   # varsayılan: http://127.0.0.1:8000
```

> `PREVIEW_API` bilinçli olarak `NEXT_PUBLIC_` öneksizdir: sunucu tarafı
> runtime değişkenidir (`lib/preview.ts`). `NEXT_PUBLIC_*` build zamanında
> bundle'a gömülür; `next start` sonrası override etmek çalışmaz.

Önkoşul: `python3 _calisma/CIKTI/preview_server.py --preview-dir _calisma/CIKTI --port 8000`

## Uygulanan App Router desenleri (skill: nextjs-app-router-patterns)

| Desen | Dosya | Not |
|---|---|---|
| Server Component veri çekme (colocated fetch) | `app/page.tsx`, `app/trend/page.tsx` | `"use client"` yok; fetch `lib/preview.ts`'te |
| Dinamik render (`cache: "no-store"`) | `lib/preview.ts` | Pano gerçek-zamanlı verdict gösterir; `ƒ (Dynamic)` |
| Streaming + Suspense (loading.tsx) | `app/loading.tsx`, `app/trend/loading.tsx` | Kabuk anında akar, kartlar Suspense'te |
| Error boundary (actioned mesaj) | `app/error.tsx`, `app/trend/error.tsx` | preview_server kapalıyken "nasıl düzeltilir" önerisi + reset |
| Root layout + metadata | `app/layout.tsx` | `%s \| leibniz2` template başlık |
| Client bileşen yalnız sınırda | `app/error.tsx` | Tek `"use client"` dosyası: hata sınırı (zorunlu) |

## Tema zinciri (CSS) — preset-bağımsız

`app/globals.css` tema kaynağını **tek zincirden** alır:

```css
@import "tailwindcss";                            /* çekirdek */
@import "../../../design-system/tailwind.css";    /* GENERATED köprü (tokens.json → tokens.css) */
@import "tw-animate-css";                         /* utility animasyonları */
```

shadcn yuvaları (`--background`, `--card`, `--primary`, `--sidebar-*`,
`--chart-*`, `--radius`) bu dosyada **repo token'larına bağlanır**:
her değer `var(--bg)` / `var(--radius-6)` gibi bir referanstır, yazıyla
verilmiş renk/ölçü YOKTUR. `@theme inline` bloğu aynı yuvaları
`--color-*` alias'ı olarak yeniden sunar; böylece `bg-card`,
`text-muted-foreground`, `border-border` gibi utility'ler doğrudan pano
paletine düşer.

- **Preset bağımsızlığı (2026-09-27):** `@import "shadcn/tailwind.css"`
  (npm preset sheet'i: `data-*` variant'ları, `no-scrollbar`,
  `scroll-fade`, `shimmer`) **kaldırıldı** — ikinci bir tema kaynağıydı ve
  bileşenlerimiz bu yüzeyleri kullanmıyordu. Yeni bir shadcn bileşeni
  preset-only bir yüzey getirirse, karşılığı repo CSS'ine eklenir.
- **Kapı:** `python3 design-system/scripts/check_tokens.py` (pre-commit
  `check-design-tokens`, fail-closed) contract 7+8'i denetler: köprü
  importu zorunlu; token gölgelemesi, kopya değer, renk literal'i, dış
  preset importu, yazıyla verilmiş yuva değeri, çürük `var(--X)`
  referansı, `@theme` alias'sız yuva ve kaynakta preset-only yüzey
  kullanımı commit'i BLOKE eder.

## Trend grafiği okuma yolu (tasarım)

`docs/TREND_CHART_READ_PATH.md`: trend yüzeyini kalıcı `trend_runs` tablosundan
besleyen okuma yolu — UTC kova (gün/saat), JS kovalama (tek şema kaynağı +
drift-guard), preview modunda sessiz boş kutu yerine açık "grafik yok" notu.
Tablo (koşu listesi) için DB yolu çalışıyor; grafik bileşeni ve agrega katmanı
tasarımdadır.

## Doğrulama kanıtı (2026-09-18)

- `npm run build` yeşil: `/` ve `/trend` ƒ Dynamic, `_not-found` ○ Static
- Mock-API uçtan-uca (gerçek `next start` + curl): verdict kartı, stripped
  hash, Z3 12/12, trend tablosu — 5/5 PASS
- API-kapalı uçtan-uca: HTTP 200 + akışkan kabuk, uçuş verisinde
  `E{digest}` hata parçası (error boundary'nin istemci-tetiklenme mekanizması)
