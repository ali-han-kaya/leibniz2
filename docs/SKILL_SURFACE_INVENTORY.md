# Skill ↔ Yüzey Envanteri

<!-- ÜRETİLMİŞ DOSYA — elle düzenleme. Kaynak: `_calisma/CIKTI/skill_surfaces.list` + `check_skill_surfaces.py` canlı ölçümü. -->

Bu depoda hangi beceri alanının **gerçek kod yüzeyi** var, hangisinin yok — tek bakışta. Alan yüzeyleri `skill_surfaces.list` manifest'inden, paket sayıları canlı `package.json` taramasından gelir; ikisi de elle yazılmaz.

- **Kaynak manifest**: `_calisma/CIKTI/skill_surfaces.list` (18 satır, sha256:`c403f9b57d6d`)
- **Denetleyen kapı**: `python3 _calisma/CIKTI/check_skill_surfaces.py --check` (fail-closed)
- **Bu dokümanı yeniden üret**: `python3 _calisma/CIKTI/gen_skill_surface_inventory.py`
- **Drift denetimi**: `--check` → doküman bayatlarsa exit 1

> `SIFIR-YÜZEY` bir eksiklik değil, **kanıtlanmış bir iddia**: o alanda iş kasten yapılmadı, çünkü uygulanacak hedef yoktu. Böyle bir alan beklenmedik bir iş üretmek zorunda değildir (pinokio emsali).

## Sıfır-yüzey alanlar (3) — iddia, ölçümle destekli

| Alan | İmza paketleri | Ölçülen | Durum | Kanıt |
|---|---|---|---|---|
| `rn-expo` | `react-native`, `expo`, `@expo/cli`, `expo-image`, `react-native-reanimated`, `@react-navigation/native`, `@shopify/flash-list` | 0/7 imza paketi görünüyor | ✅ iddia geçerli | §vercel-react-native-skills survey (2026-09-19) |
| `wrangler` | `wrangler`, `@cloudflare/workers-types` | 0/2 imza paketi görünüyor | ✅ iddia geçerli | §wrangler skill turn (2026-09-19, work/2026-09-19) |
| `xlsx` | `xlsx`, `exceljs`, `sheetjs` | 0/3 imza paketi görünüyor | ✅ iddia geçerli | §xlsx surface audit (2026-09-19, work/2026-09-19) |

- **`rn-expo`** — modül-belirteci araması (substring değil — "export" kelimesi 3 dosyada yanlış alarm üretti), hiçbir package.json'da RN bağımlılığı, expo/metro/babel yapılandırması veya ios/android dizini yok
- **`wrangler`** — CLI yok → yönetilecek komut yok; kurulum bilinçli atlandı
- **`xlsx`** — xlsx/exceljs bağımlılığı ve okuma/yazma yüzeyi yok

## Aktif alanlar (15 satır) — kod yüzeyi olan

| Alan | Paket imzası | Kaç package.json | Yüzey yolu |
|---|---|---|---|
| `nextjs` | `next` | 1 | `apps/dashboard-next` |
| `react-web` | `react` | 3 | `apps/dashboard-next` |
| `react-web` | `react` | 3 | `apps/dashboard-shadcn` |
| `react-web` | `react` | 3 | `_calisma/video` |
| `prisma` | `@prisma/client` | 2 | `apps/trend-db/prisma/schema.prisma` |
| `prisma` | `@prisma/adapter-pg` | 2 | `apps/dashboard-next/lib/trend-db.ts` |
| `postgres` | `pg` | 2 | `apps/trend-db` |
| `remotion` | `remotion` | 1 | `_calisma/video` |
| `pptx` | `pptxgenjs` | 1 | `_calisma/pptx` |
| `docx` | `docx` | 1 | `_calisma/docx/make_docx.js` |
| `tailwind` | `tailwindcss` | 1 | `design-system/tailwind.css` |

### Kimlik aynaları (4) — bağımlılık taşımaz, yalnız token yüzeyi

| Alan | Takma ad | Yüzey yolu |
|---|---|---|
| `stripe-tokens` | `stripe-tokens` | `design-system/stripe/tokens.css` |
| `linear-tokens` | `linear-tokens` | `design-system/linear/tokens.css` |
| `primer-tokens` | `primer-tokens` | `design-system/primer/tokens.css` |
| `vercel-tokens` | `vercel-tokens` | `design-system/vercel/tokens.json` |

> Bunlar **paket imzası değil kimliktir**: snapshot `raw.css`/`raw.json` taşırlar, hiçbir `package.json` bağımlılığı yoktur. Kapı bunları yalnız yol varlığıyla denetler; yoksa meşru satırlarını hayalet sanırdı.

## ⚠️ Manifest'te olmayan kanıt

Aşağıdaki alanlar `findings.md`'de **kanıtlanmış** ama `skill_surfaces.list`'te **yazılı değil**. Kapı yalnız manifest'te yazılı alanları denetlediği için bu boşluğu kendi kapatamaz — manifest'e eklenmeleri gerekir.

| Alan | Kanıt | Bağımsız ölçüm (git-tracked) | Durum |
|---|---|---|---|
| `rust-async-patterns` | §Rust surface: zero (rust-async-patterns skill) | `*.rs` = 0, `Cargo.toml` = 0, `rust-toolchain*` = 0 | manifest'te **YOK** — eklenmeli |

Not: bu bir **eksik kayıt**, yüzey ihlali değildir. Ölçülen değerler sıfırdır, yani iddia bugün de geçerli. Ama alan manifest'te GÖRÜNMEDİĞİ için kapı, yüzey ileride açılsa (bir `Cargo.toml` eklense) bunu sessizce geçecekti — denetlenmeyen alan, denetlenmeyen yüzey demektir.

Ölçüm `git ls-files` ile yapılır (disk değil): venv/vendor içindeki izlenmeyen dosyalar alan yüzeyi sayılmaz.

## Bu tabloyu güncel tutmak

1. Yeni bir alan yüzeyi eklendi/silindiyse önce `skill_surfaces.list`i güncelle (`check_skill_surfaces.py --update` yalnız ÖNERİ üretir, alan kararı insana aittir).
2. Ardından bu dokümanı yeniden üret.
3. `--check` kırmızıysa doküman bayattır; elle düzeltme değil, yeniden üretim gerekir.

