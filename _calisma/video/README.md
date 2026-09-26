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

## Repoda tutulmayanlar

`node_modules/`, `out/` (mp4 + still'ler), `.remotion/` (indirilen tarayıcı)
ve `public/data/leibniz.json` — hepsi yeniden üretilebilir çıktıdır. Kaynak
yalnız `src/`, `make_data.py`, `package.json`, `tsconfig.json` ve bu dosyadır.
