# \_calisma/video — LeibnizChain (Remotion)

Kanonik teslim zincirinin **6 sahneli mp4 anlatımı**. 1280×720 @ 30 fps,
760 kare (25,33 sn).

| Sahne        | Kare    | Süre    | İçerik                                                |
| ------------ | ------- | ------- | ----------------------------------------------------- |
| 1 · Title    | 0–89    | 3,00 sn | kompozisyon künyesi + kare bütçesi                    |
| 2 · Timeline | 90–289  | 6,67 sn | koşu zaman çizelgesi + **verdict/çıkış kodu grafiği** |
| 3 · Evidence | 290–409 | 4,00 sn | donmuş kanıt kartları (suite/a11y/seal/RC)            |
| 4 · Gates    | 410–609 | 6,67 sn | kapı zinciri K0–K15 + **kırılma animasyonu** + tahta  |
| 5 · Seal     | 610–709 | 3,33 sn | üç SHA-256 mührü                                      |
| 6 · Closing  | 710–759 | 1,67 sn | kapanış kartı                                         |

Toplam **760 kare** değişmez (25,33 sn) — `Root.tsx`, `check_render.py` ve CI
sözleşmesi bu sayıya bağlıdır. Yeni sahne içeriğine kare, **statik** sahnelerden
(Evidence, Closing) alındı: animasyon kare ister, kart göstermek istemez.

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

## Dağılım grafiği ve kapı kırılması

İkisi de `history.jsonl`'dan **türetilir**, sabit yazılmaz:

| Sahne öğesi          | Veri kaynağı (`make_data.py`)                         |
| -------------------- | ----------------------------------------------------- |
| VERDICT çubuğu       | `run_span.verdicts` (sayım)                           |
| ÇIKIŞ KODU çubuğu    | `run_span.exits` — `exit_code` + `signal.Signals` adı |
| P0/P1/bulgu/sapma/Z3 | `run_span.severity`, `run_span.drift`                 |
| KAPI TELEMETRİSİ     | `run_span.telemetry` — dolu/boş sütun ayrımı          |
| Kırılma animasyonu   | `gates.break` — `exit_code < 0` olan koşular          |
| Durum tahtası        | `status_board` → `parse_status_board()`               |
| Kapı işaretleri      | `gates.ok_ids` (yalnız tahtada **adı geçen** kapılar) |

**Dürüstlük kuralları** (birim testleriyle de zorlanır):

- Dağılım tek sonuçluysa (şu an 7/7 FAIL) grafik tek renkli olur; bu bir
  görsel hata değil, verinin kendisidir. Sahne bunu açıkça yazar.
- `0` ile `null` ayrıdır: `z3_*` sütunları dolu ama `0/0`'dır (yükümlülük
  çözülmedi); diğer 9 kapı telemetrisi sütunu **hiç dolmadı**. "Rapor yok"
  denir, PASS denmez.
- `status_board` içindeki `K katmanları ⚠️` bir kapı numarası değildir: 15
  kapıya uydurma kırmızı dağıtılmaz, **grup sinyali** olarak gösterilir.
  Yeşil işaret yalnız `K0` alır — çünkü tahtada adı geçen tek kapı odur.
- Tanınmayan tahta işareti `UNKNOWN` olur, `PASS`'a yükseltilmez.
- `history.jsonl` yoksa (temiz klon/CI) grafik boş iskelet çizilir:
  `StackBar` `total=0`'da `safe=1` ile böler, sıfıra bölme olmaz.

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
  (`make_data.py`, `src/Root.tsx`, `src/LeibnizChainView.tsx`); test bu üçünün
  aynı kare sayısını söylediğini fail-closed doğrular. Sahne süreleri
  toplamı, `Sequence` başlangıçları ve boşluk/örtüşme de denetlenir.
  Dağılım/kırılma blokları için ayrı sınıf: dağılımlar koşu sayısına
  toplanır, kırılma sayısı `exit_code < 0` olan koşularla **birebir** eşleşir,
  sentinel'da bloklar boş (uydurma değil) kalır.
- `test_check_video_typecheck.py`: tip kapısının SKIP/OK/fail-closed üç dalı.
- `check_render.py` + `test_check_video_render.py`: render çıktısı **ölçülür**
  (kare = 760, süre = 25,33 sn, 1280×720) ve sapma fail-closed. Ayrıştırıcı
  mp4 kutu (box) ağacını stdlib ile gezer — paketlenmiş `ffprobe` macOS'ta
  `libavdevice.dylib` bulamadığı için kullanılamıyor. Birim testi dosyayı elle
  kurar; render beklenmez.

## Tarayıcı içi oynatma (preview sunucusu)

`npm run build:player` paketi üretir; preview sunucusu bunu üç rota ile
servis eder:

| Rota                  | İçerik                                                      |
| --------------------- | ----------------------------------------------------------- |
| `/video.html`         | sayfa kabuğu (`build/player.html`)                          |
| `/video/player.js`    | esbuild paketi (~368 KiB, `@remotion/player` + sahne ağacı) |
| `/video/leibniz.json` | `make_data.py` çıktısının kopyası                           |
| `/video/player.css`   | sayfa kabuğu stilleri                                       |

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
