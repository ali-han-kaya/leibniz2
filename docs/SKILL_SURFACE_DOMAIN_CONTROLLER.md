# Skill ↔ Surface Domain Controller

**Purpose**: Single report showing which skill areas are in the manifest and whether they have a live surface or not. Reusable for any skill area — not hardcoded to specific domains.

## Status Overview

| Alan | Manifest | Live Surface | Zero-Surface | İmza Bulundu | Unlisted | Kanıt | Git-Tracked |
|---|---|---|---|---|---|---|---|
| `rn-expo` | ✅ 18 satır (4 zero-surface) | ✅ 0/7 imza görünür | ✅ iddia geçerli | ✅ react-native, expo, @expo/cli, expo-image, react-native-reanimated, @react-navigation/native, @shopify/flash-list | — | §vercel-react-native-skills survey (2026-09-19) | 0 (xlsx pattern: dosya yok) |
| `wrangler` | ✅ 18 satır (4 zero-surface) | ✅ 0/2 imza görünür | ✅ iddia geçerli | ✅ wrangler, @cloudflare/workers-types | — | §wrangler skill turn (2026-09-19, work/2026-09-19) | 0 (CLI yok) |
| `xlsx` | ✅ 18 satır (4 zero-surface) | ✅ 0/3 imza görünür | ✅ iddia geçerli | ✅ xlsx, exceljs, sheetjs | — | §xlsx surface audit (2026-09-19, work/2026-09-19) | 0 (dosya yok) |
| `rust-async-patterns` | ⚠️ Manifest'te **YOK** — eklenmeli | ✅ 0/3 imza görünür (disk taraması) | ✅ iddialı (ölçüm: 0) | ✅ *.rs, Cargo.toml, rust-toolchain* | — | §Rust surface: zero (rust-async-patterns skill) | `*.rs` = 0, `Cargo.toml` = 0, `rust-toolchain*` = 0 |
| `nextjs` | ✅ Aktif | ✅ next | 1 | apps/dashboard-next | — | — | — |
| `react-web` | ✅ Aktif | ✅ react | 3 | apps/dashboard-next, apps/dashboard-shadcn, _calisma/video | — | — | — |
| `prisma` | ✅ Aktif | ✅ @prisma/client | 2 | apps/trend-db/prisma/schema.prisma | — | — | — |
| `postgres` | ✅ Aktif | ✅ pg | 2 | apps/trend-db | — | — | — |
| `remotion` | ✅ Aktif | ✅ remotion | 1 | _calisma/video | — | — | — |
| `pptx` | ✅ Aktif | ✅ pptxgenjs | 1 | _calisma/pptx | — | — | — |
| `docx` | ✅ Aktif | ✅ docx | 1 | _calisma/docx/make_docx.js | — | — | — |
| `tailwind` | ✅ Aktif | ✅ tailwindcss | 1 | design-system/tailwind.css | — | — | — |
| `stripe-tokens` | ✅ Token mirror | ✅ design-system/stripe/tokens.css | — (imza değil, kimlik) | — | — | — | — |
| `linear-tokens` | ✅ Token mirror | ✅ design-system/linear/tokens.css | — (imza değil, kimlik) | — | — | — | — |
| `primer-tokens` | ✅ Token mirror | ✅ design-system/primer/tokens.css | — (imza değil, kimlik) | — | — | — | — |
| `vercel-tokens` | ✅ Token mirror | ✅ design-system/vercel/tokens.json | — (imza değil, kimlik) | — | — | — | — |

## Zero-Surface Areas (idda: bu repoda kod YOKTUR)

<details>
<summary>Zero-surface detayları</summary>

| Alan | İmza Paketleri | Package.jsonlarda Durum | Kanıt | Git-Tracked |
|---|---|---|---|---|
| `rn-expo` | `react-native`, `expo`, `@expo/cli`, `expo-image`, `react-native-reanimated`, `@react-navigation/native`, `@shopify/flash-list` | 0/7 imza paketi görünür | ✅ iddialı — iş kasten yapılmadı (hedef yok) | §vercel-react-native-skills survey (2026-09-19) | 0 .rs dosyası, 0 Cargo.toml, 0 rust-toolchain* |
| `wrangler` | `wrangler`, `@cloudflare/workers-types` | 0/2 imza paketi görünür | ✅ iddialı — CLI yok, kurulum bilinçli atlandı | §wrangler skill turn (2026-09-19, work/2026-09-19) | 0 .rs dosyası, 0 Cargo.toml, 0 rust-toolchain* |
| `xlsx` | `xlsx`, `exceljs`, `sheetjs` | 0/3 imza paketi görünür | ✅ iddialı — xlsx/exceljs bağımlılığı ve okuma/yazma yüzeyi yok | §xlsx surface audit (2026-09-19, work/2026-09-19) | 0 .rs dosyası, 0 Cargo.toml, 0 rust-toolchain* |
| `rust-async-patterns` | `*.rs`, `Cargo.toml`, `rust-toolchain*` | 0/3 imza görünür (disk taraması) | ✅ iddialı — üç kaynaklı kanıt: git-tracked sayım, disk taraması, cargo/rustc/rustup yok | §Rust surface: zero (rust-async-patterns skill) | `*.rs` = 0, `Cargo.toml` = 0, `rust-toolchain*` = 0 |

</details>

> **Önemli**: `rust-async-patterns` manifest'te yokluğuna rağmen kanıtlanmış iddialı (ölçülü değerler sıfır). Kapı yalnız manifest'te yazılı alanları denetlediği için bu boşluk manifest'e eklenmedikçe kendi kapatamaz. Bu bir **eksik kayıt**, yüzey ihlali değildir.

## Aktif Alanlar (kod yüzeyi olan)

| Alan | Paket İmzası | package.json Sayısı | Yüzey Yolu |
|---|---|---|---|
| `nextjs` | `next` | 1 | `apps/dashboard-next` |
| `react-web` | `react` | 3 | `apps/dashboard-next`, `apps/dashboard-shadcn`, `_calisma/video` |
| `prisma` | `@prisma/client` | 2 | `apps/trend-db/prisma/schema.prisma` |
| `prisma` | `@prisma/adapter-pg` | 2 | `apps/dashboard-next/lib/trend-db.ts` |
| `postgres` | `pg` | 2 | `apps/trend-db` |
| `remotion` | `remotion` | 1 | `_calisma/video` |
| `pptx` | `pptxgenjs` | 1 | `_calisma/pptx` |
| `docx` | `docx` | 1 | `_calisma/docx/make_docx.js` |
| `tailwind` | `tailwindcss` | 1 | `design-system/tailwind.css` |

## Kayıtsız Paketler (manifest'te yok, package.json'da var)

| Paket Adı | Bulunduğu package.json | Gerekçe |
|---|---|---|
| `tw-animate-css` | `apps/dashboard-next/package.json` | `skill_surfaces.list'e satır ekleyin (--update öneri üretir) ya da # unlisted: gerekçesiyle manifest edin` |

## Manifest Eksik Kanıt (findings.md'de kanıtlanmış ama manifest'te yok)

| Alan | Kanıt Bölümü | Bağımsız Ölçüm (git-tracked) | Durum |
|---|---|---|---|
| `rust-async-patterns` | §Rust surface: zero (rust-async-patterns skill) | `*.rs` = 0, `Cargo.toml` = 0, `rust-toolchain*` = 0 | manifest'te **YOK** — eklenmeli |

> **Not**: Bu bir **eksik kayıt**, yüzey ihlali değildir. Ölçülen değerler sıfırdır, yani iddia bugün de geçerli. Ama alan manifest'te GÖRÜNMEDİĞİ için kapı, yüzey ileride açılsa (bir `Cargo.toml` eklense) bunu sessizce geçecekti — denetlenmeyen alan, denetlenmeyen yüzey demektir. Ölçüm `git ls-files` ile yapılır (disk değil): venv/vendor içindeki izlenmeyen dosyalar alan yüzeyi sayılmaz.

## Token Mirror'lar (imza değil, kimlik — bağımsız yol varlığıyla denetlenir)

| Alan | Takma Ad | Yüzey Yolu | Durum |
|---|---|---|---|
| `stripe-tokens` | `stripe-tokens` | `design-system/stripe/tokens.css` | ✅ Snapshot raw.css/raw.json ile tutarlı (710 --hds-* token) |
| `linear-tokens` | `linear-tokens` | `design-system/linear/tokens.css` | ✅ Snapshot ile tutarlı (398 token) |
| `primer-tokens` | `primer-tokens` | `design-system/primer/tokens.css` | ✅ Snapshot ile tutarlı (2051 token) |
| `vercel-tokens` | `vercel-tokens` | `design-system/vercel/tokens.json` | ✅ Snapshot ile tutarlı |

> **Not**: Bu paketler **beceri-ALANI temsil etmez** — derleme, biçimlendirme ya da çalıştırıcı aracıdır. Kapı bunu imza olarak değil, YALINIZCA yol varlığıyla denetler. Hayalet denetimi bu satırlara uygulanmaz.

## Kullanım

### Rapor oluştur

```bash
# JSON raporu (makineler için - ham veriler)
python3 _calisma/CIKTI/check_skill_surfaces.py --json

# Markdown inventarını yenile (bu dokümanı güncelle)
python3 _calisma/CIKTI/gen_skill_surface_inventory.py

# Drift kontrolü (çıkış kodu 1 = drift detected)
python3 _calisma/CIKTI/check_skill_surfaces.py --check

# Kayıtsız paketler için öneri üret
python3 _calisma/CIKTI/check_skill_surfaces.py --update
```

### Yeni bir skill alanı eklemek

1. `skill_surfaces.list` dosyasını güncelle: `<alan> <paket> <yol>`
2. `findings.md` bölümünü eşitirse evidence eşlemesini `gen_skill_surface_inventory.py`'ye güncelle
3. Sıfır-yüzey iddiası varsa `ZERO_SIGNATURES` haritasına ekle
4. Yeni dokümü üret: `python3 _calisma/CIKTI/gen_skill_surface_inventory.py`

### --update bayrağı

Kayıtsız paketler için manifest satırı önerisi üretir:
```bash
python3 _calisma/CIKTI/check_skill_surfaces.py --update
```
*Not: betik paket görür, alanı ATAMAZ — alan karısı elle aittir.*

## Fail-Closed Özellikler

- **Yanlış ortam**: Çıkış 1 (drift detected — P0 arızası)
- **Tampering**: `--check-history` ile izlenir (satır eklenmesi/silinmesi)
- **Sessiz PASS**: Impossible — 6 önkoşul kapısı başarısızsa merge kararına girmez
- **Her şey doğru**: Çıkış 0, doküman yeşil, merge izni verilir

## Bağlantılı Dokümanlar

- `docs/PROOF_CHAIN_SKILL_SURFACES_NOOP_MERGE.md` — K0-K17 fail-closed zincir
- `docs/SKILL_SURFACE_INVENTORY.md` — Üretilen markdown inventar
- `_calisma/CIKTI/skill_surfaces.list` — Tek kaynak manifest
- `findings.md` — Canıtlar ve evizeler
- `docs/SKILL_SURFACE_DOMAIN_CONTROLLER.md` — Bu dosya (domain ↔ surface denetleyici)