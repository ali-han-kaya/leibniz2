# \_calisma/video — LeibnizChain (Remotion)

Kanonik teslim zincirinin **6 sahneli mp4 anlatımı**. 1280×720 @ 30 fps,
760 kare (25,33 sn).

| Sahne        | Kare    | Süre    | İçerik                                     |
| ------------ | ------- | ------- | ------------------------------------------ |
| 1 · Title    | 0–89    | 3,00 sn | kompozisyon künyesi + kare bütçesi         |
| 2 · Timeline | 90–269  | 6,00 sn | `history.jsonl` koşu zaman çizelgesi       |
| 3 · Evidence | 270–449 | 6,00 sn | donmuş kanıt kartları (suite/a11y/seal/RC) |
| 4 · Gates    | 450–589 | 4,67 sn | kapı zinciri K0–K15                        |
| 5 · Seal     | 590–699 | 3,67 sn | üç SHA-256 mührü                           |
| 6 · Closing  | 700–759 | 2,00 sn | kapanış kartı                              |

## Neden "yeniden inşa"

Orijinal pilot 2026-09-18'de **repo dışında** (`/tmp/leibniz-chain-video`)
kurulmuş ve yalnız tarayıcı önbelleği temizliğinde kaybolmuştur. Bu dizindeki
sürüm, kayıtta kalan spesifikasyondan (`findings.md` Remotion bölümü ve
`recovery_patches_20260918/patch1789754982-84993` yaması) yeniden kurulmuştur:
aynı kompozisyon adı, aynı kare bütçesi, aynı sahne sırası.

**Sayıların kaynağı kompozisyonun kendisi değildir.** `make_data.py` her
üretimde veriyi depodan yeniden okur; sahne hiçbir değeri gömmez. Kaybolan
sürümün görselleri birebir kopyalanamaz, ama gösterilen her sayı ya repodan
gelir ya da `EVIDENCE` sabit listesinde kayıtla belgelidir.

## Kullanım

```bash
cd _calisma/video
npm ci                 # bağımlılıklar (node_modules repoda tutulmaz)

npm run data           # public/data/leibniz.json üret (history.jsonl'den)
npm run typecheck      # tsc --noEmit
npm run check          # mp4 sözleşmesini ölç (kare/süre/çözünürlük)
npm run build:player   # tarayıcı paketi (preview sunucusu /video.html)
npm run format         # prettier --write
npm run render         # 760 kare → out/leibniz-chain.mp4
npm run studio         # Remotion Studio (kullanıcı terminalinde açılmalı)
```

`render` ve `studio` veriyi önce üretir; elde `out/` yoksa `make_data.py`
`public/data/` altını kendisi oluşturur.

`npm run render` ilk koşuda Chromium'u indirir (`npx remotion browser
ensure`, ~85 MB) ve Remotion'un webpack önbelleğini **bulunulan dizine**
yazar — bu yüzden proje kökünden değil, `_calisma/video` içinden koşulur.

## Kapılar

- `check-video-typecheck` (pre-commit): video dosyaları stage'liyken
  `tsc --noEmit`; kurulum yoksa SKIP, tip hatası varsa fail-closed.
- `check-prettier-format` (pre-commit): stage'li `.ts/.tsx/.json` kök
  `.prettierrc`'ye göre biçim-uyumlu olmalı.
- `test_video_data_contract.py`: kare bütçesi **üç** yerde birden yaşar
  (`make_data.py`, `src/Root.tsx`, `src/LeibnizChain.tsx`); test bu üçünün
  aynı kare sayısını söylediğini fail-closed doğrular. Sahne süreleri
  toplamı, `Sequence` başlangıçları ve boşluk/örtüşme de denetlenir.
- `test_check_video_typecheck.py`: tip kapısının SKIP/OK/fail-closed üç dalı.
- `check_render.py` + `test_check_video_render.py`: render çıktısı **ölçülür**
  (kare = 760, süre = 25,33 sn, 1280×720) ve sapma fail-closed. Ayrıştırıcı
  mp4 kutu (box) ağacını stdlib ile gezer — paketlenmiş `ffprobe` macOS'ta
  `libavdevice.dylib` bulamadığı için kullanılamıyor. Birim testi dosyayı elle
  kurar; render beklenmez.

## Tarayıcı içi oynatma (preview sunucusu)

`npm run build:player` paketi üretir; preview sunucusu bunu üç rota ile
servis eder:

| Rota | İçerik |
|---|---|
| `/video.html` | sayfa kabuğu (`build/player.html`) |
| `/video/player.js` | esbuild paketi (~368 KiB, `@remotion/player` + sahne ağacı) |
| `/video/leibniz.json` | `make_data.py` çıktısının kopyası |
| `/video/player.css` | sayfa kabuğu stilleri |

Remotion Studio **değil**: Studio ayrı bir sunucu + webpack dev-cache ile gelir
ve araç tarafından sürekli öldürülür. Player tek statik dosyada toplanır.

Aynı sahne ağacı iki yerde çalışır: `LeibnizChainView` hem mp4 render'ında
(`staticFile` verisi) hem oynatmada (`dataUrl` verisi) kullanılır — kopya
sahne yok. Veri adresi sayfadaki `data-src` niteliğinden gelir; CSP
`script-src 'self' 'nonce-…'` olduğu için **inline script yoktur**.

Paket üretilmemişse `/video.html` boş sayfa değil, yol gösteren bir 404 döner
(`npm run build:player`).

## Repoda tutulmayanlar

`node_modules/`, `out/` (mp4 + still'ler), `dist/` (oynatma paketi),
`.remotion/` (indirilen tarayıcı) ve `public/data/leibniz.json` — hepsi yeniden
üretilebilir çıktıdır. Kaynak yalnız `src/`, `scripts/`, `build/`,
`make_data.py`, `check_render.py`, `package.json`, `tsconfig.json` ve bu
dosyadır.
