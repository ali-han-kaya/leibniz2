# \_calisma/video — LeibnizChain + GateChainRuns (Remotion)

İki kompozisyon, tek sahne/veri altyapısı:

| Kompozisyon     | Kare | Süre     | Kaynak                                                  |
| --------------- | ---- | -------- | ------------------------------------------------------- |
| `LeibnizChain`  | 760  | 25,33 sn | `history.jsonl` + `klayers.runs.json` + donmuş mühürler |
| `GateChainRuns` | 630  | 21,00 sn | **yalnız** `history.jsonl` — koşu-başına 16 kapı        |

Kare sayıları `make_data.py`'de tek yerde yaşar (`FRAMES`,
`GATE_HISTORY_FRAMES`, `FRAMES_BY_COMPOSITION`); `src/Root.tsx`,
`check_render.py` ve testler bu sabitlere bağlıdır.

## LeibnizChain — 6 sahne

Kanonik teslim zincirinin **6 sahneli mp4 anlatımı**. 1280×720 @ 30 fps,
760 kare (25,33 sn).

| Sahne         | Kare    | Süre    | İçerik                                                |
| ------------- | ------- | ------- | ----------------------------------------------------- |
| 1 · Title     | 0–89    | 3,00 sn | kompozisyon künyesi + kare bütçesi                    |
| 2 · Timeline  | 90–289  | 6,67 sn | koşu zaman çizelgesi + **verdict/çıkış kodu grafiği** |
| 3 · Evidence  | 290–399 | 3,67 sn | donmuş kanıt kartları (suite/a11y/seal/RC)            |
| 4 · GateChain | 400–609 | 7,00 sn | **K0–K15 canlı zinciri** + son 3 koşu özeti           |
| 5 · Seal      | 610–709 | 3,33 sn | üç SHA-256 mührü                                      |
| 6 · Closing   | 710–759 | 1,67 sn | kapanış kartı                                         |

Toplam **760 kare** değişmez (25,33 sn) — `Root.tsx`, `check_render.py` ve CI
sözleşmesi bu sayıya bağlıdır. Yeni kapı zinciri sahnesine kare, **statik**
Evidence kartlarından alındı: animasyon kare ister, kart göstermek istemez.

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
| Kırılma animasyonu   | `gates.break` — kanıtlı kırılma + `newest`            |
| Durum tahtası        | `status_board` → `parse_status_board()`               |
| Kapı işaretleri      | `gates.ok_ids` (yalnız tahtada **adı geçen** kapılar) |
| K0–K15 durumu        | `klayers.runs.json` → `gate_chain.runs` (son 3 koşu)  |

Satır listesi 720 px yüksekliğe sığan son **10 koşuyu** çizer; toplam sayı ve
tarih aralığı başlıkta kalır (`100 kayıt · … · son 10 koşu`). Pencere yokken
100 satır × ~31 px ≈ 3100 px ediyor ve alt blok — VERDICT/ÇIKIŞ barları ile
KIRILMA animasyonu — karenin **dışına** taşıyordu (1280×720 still ile ölçüldü).

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
- `status_board` bir **özet**tir: “K0 🔴” ikonu P0/P1 sayısından türer, K0
  katmanının kendi durumu değildir. Satırda gerçek `layers` haritası varsa
  kapı durumları ORADAN okunur (`from: "layers"`); tahta yalnız harita yoksa
  devreye girer (`from: "board"`). Ölçüldü: 2026-10-06 koşusunda tahta
  “K0 🔴 · K katmanları 🔴” derken harita K0 PASS, K16/K17 FAIL diyor.
- Zincir K0–K15 çizer; arşiv K16–K21'i de taşır. Kapsam dışı kayıtlar
  silinmez: kırılma gerçekten K16/K17'de ise sahne “kapsam dışı FAIL” yazar.
  Silinselerdi FAIL veren bir koşu “16/16 kapı, FAIL yok” görünürdü.
- Sinyalle kesilen koşu (ör. `-15`) kapı raporu üretemez. Animasyon bu
  yüzden kanıtı olan en yeni kırılmayı çizer ve en yeni kırılmayı ayrıca
  `newest` satırıyla adlandırır; rapor yoksa PASS/FAIL uydurulmaz.
- `history.jsonl` yoksa (temiz klon/CI) grafik boş iskelet çizilir:
  `StackBar` `total=0`'da `safe=1` ile böler, sıfıra bölme olmaz.

## Kullanım

```bash
cd _calisma/video
npm ci                 # bağımlılıklar (node_modules repoda tutulmaz)

npm run fetch:live     # gh ile son verify history + son 3 klayers indir
npm run data           # public/data/leibniz.json üret (history + klayers)
npm run typecheck      # tsc --noEmit
npm run check          # mp4 sözleşmesini ölç (kare/süre/çözünürlük)
npm run build:player   # tarayıcı paketi (preview sunucusu /video.html + pano kartı)
npm run format         # prettier --write
npm run render         # 760 kare → out/leibniz-chain.mp4
npm run studio         # Remotion Studio (kullanıcı terminalinde açılmalı)
```

`render` ve `studio` veriyi önce üretir; elde `out/` yoksa `make_data.py`
`public/data/` altını kendisi oluşturur.

### Canlı kapı zinciri (K0–K15)

`GateChain` sahnesi 16 kapıyı iki sırada çizer; her düğümün rengi ve etiketi
**gerçek** `klayers.json` kaydından gelir:

- `PASS` → yeşil `GEÇTİ`
- `FAIL` → kırmızı `KALDI` (+ bulgu sayısı)
- `SKIP` → sarı `KOŞMADI` (bu job'da koşmadı; FAIL sayılmaz)
- `MISSING` → soluk `KAYIT YOK` (raporda o kapı yok; PASS'a yükseltilmez)

Sahne son 3 başarılı verify koşumunu sırayla tarar; üst sağdaki `KOŞU n/3`
ve `verify #id` damgası hangi koşumun gösterildiğini söyler. Alt şerit üç
koşumun PASS/FAIL/SKIP özetini yan yana gösterir ve aktif koşuyu vurgular.
Kırılma ve genel dağılım Timeline sahnesinde kalır; bu sahne yalnız gerçek
kapı kaydını konuşur.

`klayers.runs.json` yoksa sahne boş iskelet çizer ve `K KATMANI RAPORU YOK`
yazar; sahte yeşil üretmez. Yerelde `npm run fetch:live`, CI'da workflow'un
"Fetch latest verified history + gate layers" adımı bu dosyayı üretir.

## GateChainRuns — koşu başına 16 kapı (K0–K15)

İkinci kompozisyon farklı bir soruyu cevaplar: **tarih boyunca her koşuda 16
kapının durumu neydi?** Kaynak yalnız `_calisma/CIKTI/history.jsonl`.

| Kare    | İçerik                                                       |
| ------- | ------------------------------------------------------------ |
| 0–44    | künye + dürüstlük kuralları + 5 durumluk gösterge            |
| 45–584  | 6 koşu × 90 kare: 16 kapı soldan sağa yanar, alt şerit özeti |
| 585–629 | kapsam kapanışı: `raporlanan / hücre`, “KAYIT YOK ≠ PASS”    |

**Durum çözümlemesi tek fonksiyonda** (`make_data.gate_states_for_run`) ve
sıra sabittir:

1. `history` satırının `layers` haritası → `PASS` / `FAIL` / `SKIP`;
2. satırın `status_board`'unda **adı geçen** kapı (ör. `K0 🔴`) → `PASS` /
   `FAIL` / `WARN`;
3. aksi hâlde `MISSING` → sahnede “KAYIT YOK”. PASS'a **yükseltilmez**.

Her kutunun köşesindeki `LAYERS` / `BOARD` / `—` damgası, o rengin hangi
kanıttan geldiğini söyler. `K katmanları ⚠️` gibi **grup sinyali** 16 kutuya
dağıtılmaz; sahne onu alt şeritte “grup sinyali: WARN” olarak ayrı gösterir.

Bugünkü yerel arşivde (100 koşu) `layers` alanı **yoktur**: eski satırlar
koşu-başına katman haritası yazmıyordu, `status_board` ise çoğu koşuda yalnız
`K0`'ı adlandırıyor. Bu yüzden sahne çoğu kutuyu “KAYIT YOK” çizer — bu bir
render hatası değil, **arşivin kendi kapsamıdır**. Yeni koşular `layers`
yazdıkça zincir dolar.

### CI'da render

`.github/workflows/video-render.yml` bu yüzeyi gerçek runner'da render eder:
`npm ci` → `fetch_live_data.sh` → `tsc --noEmit` → `scripts/render_ci.sh` →
**iki** kompozisyonun sözleşme ölçümü (760 + 630 kare) →
`leibniz-chain-video` artifact'ı (`out/leibniz-chain.mp4`,
`out/gate-chain.mp4`, `out/render_report.json`, `out/render_check.txt`,
`out/gate_render_report.json`, `out/gate_render_check.txt`,
`out/render_mode.txt`, `out/render_elapsed_s.txt`, 30 gün). Ölçülmeyen
kompozisyon sessizce çürür — bu yüzden ikisi de her koşuda render edilir.

- Tetikleme: **her push ve PR commit'i** (path filtresi yok); ayrıca elle
  `workflow_dispatch`. Video dışı bir değişiklik de 760 karelik render
  boru hattını ve sözleşme ölçümünü kanıtlar.
- PR yorumu: aynı repodaki PR'larda `video_render_comment.js` marker'lı tek
  yorumu günceller. Özet kare, video/kap süresi, render duvar saati, boyut
  (MiB + bayt), tam **SHA-256**, veri modu ve sözleşme hükmünü taşır. Render
  düşerse yorum metrik uydurmaz; `ölçülemedi`/`FAIL` yazar. Fork PR'larında
  `GITHUB_TOKEN` salt-okunur olduğu için adım atlanır.
- `render_ci.sh`, son başarılı `verify-delivery` koşumunun `run-history`
  artifact'ını ve son 3 koşumun `klayers` artifact'ını kullanmayı dener.
  Erişilemezse `make_data.py --allow-missing-data` ile **sentinel** moduna
  düşer; mod `out/render_mode.txt` ve run summary'de açıkça yazılır (sessiz
  sahte veri yok).
- Yerelde aynı sürücü: `bash scripts/render_ci.sh` (çıktılar gitignored).

`npm run render` ilk koşuda Chromium'u indirir (`npx remotion browser
ensure`, ~85 MB) ve Remotion'un webpack önbelleğini **bulunulan dizine**
yazar — bu yüzden proje kökünden değil, `_calisma/video` içinden koşulur.

İkinci kompozisyon: `npm run render:gates` → `out/gate-chain.mp4`;
ölçüm: `python3 check_render.py out/gate-chain.mp4 --composition GateChainRuns`.
İkisini birlikte: `npm run render:all`.

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
  sentinel'da bloklar boş (uydurma değil) kalır. `gate_chain` testi her
  koşunun tam K0–K15 listesini ve PASS/FAIL/SKIP/MISSING sayılarının 16'ya
  toplandığını doğrular.
- `test_check_video_typecheck.py`: tip kapısının SKIP/OK/fail-closed üç dalı.
- `check_player_routes.py` + `test_preview_video_player.TestPlayerRouteGate`:
  paket artifact'ları + `/video/*` rotaları gerçek HTTP ile (200/404,
  Content-Type, gövde marker'ları, `meta.frames`).
- `check_render.py` + `test_check_video_render.py`: render çıktısı **ölçülür**
  (kare = 760, süre = 25,33 sn, 1280×720) ve sapma fail-closed. Ayrıştırıcı
  mp4 kutu (box) ağacını stdlib ile gezer — paketlenmiş `ffprobe` macOS'ta
  `libavdevice.dylib` bulamadığı için kullanılamıyor. `--json` raporu tam
  dosya baytlarının **SHA-256**'sını da taşır; PR yorumu bu alanı kullanır.
  Birim testi dosyayı elle kurar; render beklenmez.

## Tarayıcı içi oynatma (preview sunucusu)

`npm run build:player` paketi üretir; preview sunucusu bunu üç rota ile
servis eder:

| Rota                  | İçerik                                                      |
| --------------------- | ----------------------------------------------------------- |
| `/video.html`         | sayfa kabuğu (`build/player.html`)                          |
| `/video/player.js`    | esbuild paketi (~525 KiB, `@remotion/player` + sahne ağacı) |
| `/video/leibniz.json` | `make_data.py` çıktısının kopyası                           |
| `/video/player.css`   | sayfa kabuğu stilleri                                       |

Remotion Studio **değil**: Studio ayrı bir sunucu + webpack dev-cache ile gelir
ve araç tarafından sürekli öldürülür. Player tek statik dosyada toplanır.

Aynı sahne ağacı iki yerde çalışır: `LeibnizChainView` hem mp4 render'ında
(`staticFile` verisi) hem oynatmada (`dataUrl` verisi) kullanılır — kopya
sahne yok.

Tarayıcı oynatıcısı **yalnız `LeibnizChain`** kompozisyonunu oynatır
(`src/player.tsx`). `GateChainRuns` mp4 tarafında yaşar: `npm run render:gates`
veya CI'daki `leibniz-chain-video` artefaktındaki `out/gate-chain.mp4`. Veri adresi sayfadaki `data-src` niteliğinden gelir; CSP
`script-src 'self' 'nonce-…'` olduğu için **inline script yoktur**.

Paket üretilmemişse `/video.html` boş sayfa değil, yol gösteren bir 404 döner
(`npm run build:player`).

### Erişilebilirlik sözleşmesi (a11y_gate yüzeyi)

`/video.html` artık `a11y_gate.py`'nin taranan yüzeylerinden biri
(`a11y_gate_config.json`, witness `LeibnizChain`; CI matrisi dark+light).
`dist/` gitignore'da olduğu için CI'da taramadan **önce** paket üretilir —
paket yoksa sayfa 404, witness eşleşmez ve kapı fail-closed FAIL verir.

Kontroller Remotion'in hazır `controls` çubuğu **değil**: o çubuk İngilizce
sabit etiketler taşır ("Play video", "Mute sound", "Enter Fullscreen") ve
`aria-pressed` yaymaz — `lang="tr"` sayfada ekran okuyucu İngilizce düğme adı
okurdu. `controls={false}` + `PlayerControls` (`src/PlayerControls.tsx`):

- adlar Türkçe ve durumla değişir: Oynat/Duraklat, Sesi kapat/aç, Tam ekran/
  tam ekrandan çık; ses ve tam ekran `aria-pressed` ile durum bildirir,
- konum kaydırıcısı `aria-label="Oynatma konumu"` + `aria-valuetext="0:12 / 0:25"`,
- çubuk **opak** zeminlidir (yarı saydam katmanda axe `color-contrast`'ı
  "incomplete" yapar); ölçülen oran 15.08:1,
- odak halkası `:focus-visible` 2px + 2px offset (UA'nın 1px `auto` outline'ı
  koyu zeminde inceydi).

Sözleşme `test_preview_video_player.TestPlayerA11ySource` (statik) ile pinlenir;
canlı doğrulama `a11y_gate.py --page /video.html --theme dark|light` koşumudur.

### Paket + rota kapısı (`check_player_routes.py`)

`dist/` gitignore'da olduğu için "kapı yeşil ama paket yok" sessizce mümkündü:
preview_server paket yoksa `/video.html` için yol gösteren 404 döner. Bu yüzden
ayrı bir fail-closed kapı var (`check_player_routes.py`), CI'da **her push/PR'da**
`video-render.yml` içindeki `player` job'ı olarak koşar:

1. `npm ci` + `npm run build:player:ci` (CI'da `history.jsonl` yok —
   gitignore'da — strict `build:player` exit 1 verir; `:ci` varyantı
   `--allow-missing-data` ile sentinel üretir, `meta.frames` yine 760),
2. dört artifact'ın (player.html/js/css + leibniz.json) var ve boş olmadığını,
3. **gerçek HTTP** üzerinden `/video.html`, `/video/player.js`,
   `/video/player.css`, `/video/leibniz.json` → 200 + doğru Content-Type +
   `charset=utf-8`,
4. gövde iddiaları: kabukta `#root`/`data-src`/tek `<main>`, pakette erişilebilirlik
   marker'ları (`Oynatıcı kontrolleri`, `Oynatma konumu`, `Sesi kapat` — ASCII
   kaçışları çözülerek), JSON'da `meta.frames=760`,
5. allowlist sözleşmesi: `/video/yok.js`, `/video/player.json`,
   `/video/../README.md` → 404

Herhangi biri tutmazsa exit 1. Yerel koşum: `python3
_calisma/video/check_player_routes.py --json-out player_routes.json`.
Sayfa kabuğu tek `<main>` landmark'ı taşır (onsuz `landmark-one-main` + `region`
uyarıları düşüyordu).

Aynı oynatıcı pano (`_calisma/CIKTI/preview.html`) içinde bir **kart** olarak da
yaşar. Kart `player.js`'i açılışta indirmez (React + player ~525 KiB): paket
kart viewport'a girince (`IntersectionObserver`) ya da "Oynatıcıyı yükle"
düğmesiyle enjekte edilir. Enjeksiyon başarısız olursa (paket derlenmemiş →
`/video/player.js` 404) kart boş kutu yerine build talimatını gösterir. Sözleşme
`_calisma/CIKTI/test_preview_video_player.py` (statik) ve
`_calisma/CIKTI/test_preview_interaction_dom.js` (tarayıcısız DOM: lazy /
başarı / hata / tekrar dene) ile pinlenir.

## Repoda tutulmayanlar

`node_modules/`, `out/` (mp4 + still'ler), `dist/` (oynatma paketi),
`.remotion/` (indirilen tarayıcı), `public/data/leibniz.json`,
`_calisma/CIKTI/klayers.json` ve `_calisma/CIKTI/klayers.runs.json` — hepsi
yeniden üretilebilir çıktıdır. Kaynak yalnız `src/`, `scripts/`, `build/`,
`make_data.py`, `check_render.py`, `package.json`, `tsconfig.json` ve bu
dosyadır.
