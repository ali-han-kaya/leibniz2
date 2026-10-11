# Run-Stream Replay Kuyruğu: "Son 2 Run + Keepalive" Tasarımı ve SSE-Flood Ölçümü

**Tarih:** 2026-10-08 · **Durum:** tasarım + ölçüm (kod değişikliği YAPILMADI)
**Kapsam:** `_calisma/CIKTI/preview_server.py` `/api/run-stream` replay derinliği
**İlgili:** QA bulgusu F4 (istemci tarafı rAF-birleştirme), F3 (mirror tazeliği), F2 (bayat SW)

---

## 1. Özet (TL;DR)

Bağlantı kurulduğunda `/api/run-stream` **son ≤20 run'un tüm satırlarını** tek buffer'da
replay ediyor. Gerçek canlı veriyle ölçüm:

- 20 run → **19.084 SSE olayı**, **2.097.860 B** (framed) replay; 2 run → **2.008 olay**,
  **220.621 B** → **9,51×** azalma.
- İstemci yalnız **600 satır** tutuyor (`STREAM_MAX`): 20-run replay'inin **%96,85'i**
  atılıyor. Ayrıca **oturmuş (settled) kutu 20 ve 2 run'da birebir aynı** (600 çocuk,
  23.903 karakter) — replay derinliğinin görünür kalıcı etkisi yok.
- Maliyet istemcide: canlıda bugün servis edilen **F4'süz** istemcide 20-run replay
  açılışta **~132 s** main-thread kilidi üretiyor (tek long task 68,5 s); 2 run'da
  11 s; **F4'lü** istemcide 20 run 561 ms, 2 run **0 long task**.

**Öneri:** replay derinliğini **2**'ye indir (`RUN_STREAM_REPLAY_RUNS = 2`), disk
saklamayı 20'de **ayrı** tut (`RUN_LOG_MAX`), keepalive değişmesin (15 s).
`--replay-runs 20` operatör kaçış kapısı olarak eski davranışı geri getirir.

---

## 2. Mevcut davranış (kod sözleşmesi)

`_calisma/CIKTI/preview_server.py`:

| Yer | Ne |
| --- | --- |
| `:171` | `RUN_LOG_MAX = 20` — **hem disk saklama hem replay** derinliği |
| `:172` | `SSE_POLL_TIMEOUT = 15` — keepalive periyodu (`: keepalive\n\n`) |
| `:512-519` | `_prune_run_logs()` — `RUNS_DIR`'i `RUN_LOG_MAX`'a budar |
| `:548-566` | `load_run_logs(limit)` — son `limit` run logunu okur; `limit=None` → `RUN_LOG_MAX` |
| `:617-680` | `build_replay_events*` — run başına `replay-start` … satırlar … `replay-end` (son run `last: true`) |
| `:1537-1585` | `serve_run_stream()` — `info` → `_replay_runs(load_run_logs(RUN_LOG_MAX))` → canlı kuyruk + 15 s keepalive |
| `:2195-2206` | `--replay-runs` → **`RUN_LOG_MAX`'ı global olarak ezer** |

**Tespit edilen iki tasarım kusuru (ölçüldü, §6):**

1. **Saklama ↔ replay eşleşmesi:** `--replay-runs 2` demek disk saklamayı da 2'ye
   düşürür (prune aynı sabiti kullanır) → geçmiş run logları silinir.
2. **`limit ≤ 0` footgun'u:** `load_run_logs(0)` → `files[-0:]` = **tüm run'lar**
   (20); `load_run_logs(-3)` → **sondan 3 hariç 17**. Yani "0 = replay yok" bekleyen
   operatör en kötü durumu (tam replay) alır.

Canlı sunucu (port 8000, başka thread) `--replay-runs` **vermeden** koşuyor
(`--port 8000 --bind 127.0.0.1 --interval 3600`) → bugün 20-run replay aktiftir.

---

## 3. Ölçüm yöntemi (gerçek veri)

- **Veri:** canlı preview-dir `~/Library/Caches/com.freebuff/preview`'in anlık kopyası
  (`/tmp/rs_live`, 2026-10-08 04:59): **20 run logu** (840 KB), `history.jsonl`,
  `klayers.json`. Kimlikler §8'de.
- **Sunucu-tarafı replay yükü:** `build_replay_events_multi` doğrudan çağrılarak olay
  sayısı ve byte'lar birebir hesaplandı (`/tmp/rs_measure.py` → `/tmp/rs_payload.json`).
- **Ham HTTP:** socket ile `GET /api/run-stream`; byte/olay/keepalive sayımı (`/tmp/rs_probe.py --keepalive`).
- **Tarayıcı:** Playwright **Chromium 148 headless**; her hücre **kendi sunucusuyla**
  (stub `verify_delivery.py` — canlı run gürültüsü yok), gerçek snapshot'a karşı:
  - CDP `Network.eventSourceMessageReceived` → olay sayısı/byte/zaman aralığı
  - `PerformanceObserver(longtask)`, rAF boşlukları, `MutationObserver(#runstream)`
  - CDP `Accessibility.getFullAXTree` → gecikme + düğüm sayısı + ağaç boyutu
  - Etkileşim probe'u: `requestAnimationFrame` gecikmesi + zorunlu layout (`scrollHeight`)
- Hücreler: **W** = bu dalın `preview.js`'i (F4'lü, sha `e91f8d41…`);
  **L** = canlı dizindeki **4 Ekim** kopyası (F4'süz, sha `e1444a34…`).
- Her hücre: `--replay-runs {20,2}`; ham sonuçlar `/tmp/rs_cells.jsonl`.

---

## 4. Ölçümler

### 4.1 Replay yükü (sunucu tarafı, gerçek 20 run)

| Metrik | 20 run | 2 run | Oran |
| --- | --- | --- | --- |
| Replay olayı | 19.084 | 2.008 | 9,50× |
| Satır olayı (stdout+stderr) | 19.044 | 2.004 | 9,50× |
| SSE framed byte | **2.097.860** | **220.621** | **9,51×** |
| Yalnız-veri byte (`data:` gövdeleri) | 1.677.812 | 176.425 | 9,51× |
| Ham run-log byte | 728.642 | 76.562 | 9,52× |
| Çerçeveleme şişmesi | 2,88× | 2,88× | — |

İstemci `STREAM_MAX = 600` satır → 20-run replay'inin **%96,85'i** atılır; 2 run bile
600'ün **3,34 katıdır** (%70'i atılır).

### 4.2 Tarayıcı hücreleri (Chromium 148 headless)

| Hücre | replay | istemci | SSE olay | varış aralığı | goto→sakin | long task (adet/toplam/maks) | rAF gap maks | mutasyon | flood probe (rAF/wall) | sakin probe | AX (ms / düğüm / MB) | son DOM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **W20** | 20 | F4 | 19.086 | 594 ms | 2.210 ms | 4 / 561 ms / **210 ms** | 283 ms | 43 | **256 ms / 1.184 ms** | 12 ms | 164 / 5.234 / 1,94 | 600 çocuk, 23.903 kr |
| **W2** | 2 | F4 | 2.010 | 56 ms | 1.081 ms | **0 / 0 / 0** | 66 ms | 5 | **1 ms / 22 ms** | 2 ms | 217 / 4.821 / 1,75 | 600 çocuk, 23.903 kr |
| **L20** | 20 | 4 Eki (F4 yok) | 19.088 | **131.884 ms** | **133.186 ms** | 5 / **131.745 ms** / **68.540 ms** | **68.816 ms** | 19.085 | **68.602 ms / 132.181 ms** | 4 ms | 179 / 5.145 / 1,94 | 600 çocuk, 23.889 kr |
| **L2** | 2 | 4 Eki (F4 yok) | 2.010 | 11.024 ms | 12.129 ms | 2 / 11.076 ms / 11.013 ms | 11.084 ms | 2.008 | 14 ms / 11.104 ms | 13 ms | 211 / 4.827 / 1,78 | 600 çocuk, 23.903 kr |

### 4.3 Keepalive (2 run)

`: keepalive` **15,03 s**'de geldi; 2.008 olay ~anında (ilk byte 0,00 s) indi; 18 s'lik
okuma boyunca bağlantı açık kaldı (221.239 ham byte, HTTP başlıkları dahil).
Replay sonrası boşta bekleyen bağlantıyı keepalive canlı tutuyor — **değişiklik gerekmez**.

---

## 5. a11y / webview etkisi

- **Main-thread starvation (asıl etki):** flood sırasında etkileşim gecikmesi
  (rAF probe) F4'lü istemcide **256 ms** (20 run) → **1 ms** (2 run); F4'süz istemcide
  **68,6 s** (20 run) → 14 ms (2 run). Long task toplamı: 561 ms → 0 (F4'lü),
  131,7 s → 11,1 s (F4'süz). Ekran okuyucu/klavye kullanıcısı, canlı istemcide
  sekmeyi açtığında **dakikalarca** tepki alamıyor.
- **A11y ağacı üretimi flood'a duyarlı değil:** `Accessibility.getFullAXTree`
  gecikmesi ~180-220 ms ve ağaç ~5.000 düğüm / ~1,9 MB — flood sırasında da sakin
  hâlde de aynı (hesap tarayıcı sürecinde yürüyor). Yani etki "a11y ağacı yavaşlıyor"
  değil, "a11y tüketicisi main-thread'e erişemiyor".
- **Canlı bölge fırtınası yok:** `preview.html`'de tek `aria-live` bölgesi
  `duration-pct-warn`; akış kutusu (`#runstream`) canlı bölge değil → etki duyuru
  fırtınası değil, tepkisizlik. (Yine de 19k DOM değişikliği, AT'li kullanıcıda
  tarayıcı-seviyesi yeniden hesaplamaları tetikler.)
- **Webview notu:** ölçüm Chromium 148 headless ile yapıldı (WKWebView/gömülü
  motor **ölçülmedi** — sınır, §7). F2 (bayat SW ile asılı kalma) bu ölçümün dışında.

---

## 6. Tasarım

### 6.1 Ayrıştırma (bloklayıcı)

```python
# sabitler
RUN_LOG_MAX = 20             # disk saklama (prune) — DEĞİŞMEZ
RUN_STREAM_REPLAY_RUNS = 2   # YENİ: replay derinliği

def load_run_logs(limit=None):
    ...
    if limit is None:
        limit = RUN_LOG_MAX
    if limit <= 0:           # 0 = replay yok; negatif de aynı (footgun kapanır)
        return []
    ...
    files = files[-limit:]

def _prune_run_logs():       # RUN_LOG_MAX (saklama) kullanır — DEĞİŞMEZ
    ...

# serve_run_stream()
replay_records = load_run_logs(RUN_STREAM_REPLAY_RUNS)

# argparse
ap.add_argument("--replay-runs", type=int, default=RUN_STREAM_REPLAY_RUNS,
                help="/api/run-stream'de replay edilecek son run sayısı (0 = replay yok)")
ap.add_argument("--run-log-max", type=int, default=RUN_LOG_MAX,
                help="disk'te tutulacak run logu sayısı")
...
RUN_STREAM_REPLAY_RUNS = args.replay_runs
RUN_LOG_MAX = args.run_log_max
```

- **Keepalive:** değişmez (15 s `: keepalive`); replay bittikten sonra bağlantı boşta kalır.
- **Geri uyumluluk:** istemci derinlik-agnostiktir (`first`/`last` işaretleriyle); yeni
  istemci gerekmez. `--replay-runs 20` eski davranışı aynen verir.
- **Neden 2:** oturmuş kutu 600-satır cap'iyle zaten son run'ların kuyruğunu gösteriyor
  (§4.2: W20 ve W2 son DOM birebir aynı); 2 run "önceki run" bağlamını korur ve
  mevcut run'ın sınırını (`── canlı akış ──`) doğru çizer.

### 6.2 Opsiyonel sertleştirme (bloklayıcı değil)

1. **Run başına satır tavanı** (ör. son 400 satır): 2 run bile 2.004 satır → cap'in
   3,34 katı. Ölçülmedi; ürün kararı gerektirir (geçmiş run özet satırları azalır).
2. **`replay-start`'a `truncated: true`** + istemcide "…" göstergesi: istemci
   değişikliği (preview.js) gerektirir — bu turda ölçülmedi.
3. **Replay yazımını parçalama (yield):** sunucu tarafı tek `wfile.write` zaten tek
   syscall; ölçümde darboğaz **istemci JS'i** (L20: 132 s'nin tamamı çizim/serileştirme).
   Sunucu-tarafı parçalama kazancı **ölçülmedi** → spekülatif, şimdilik gereksiz.

### 6.3 Ürün kararı notu

20 → 2, akış kutusunda **görünen geçmiş run özet satırı sayısını** azaltır; ancak
oturmuş kutu birebir aynıdır (600-satır cap'i zaten eskisini atıyor — ölçüldü).
Fark yalnızca replay sürerken ara karelerde görünür. Bu yüzden değişiklik
"veri kaybı" değil, "boşa iş + donma" kaybıdır.

---

## 7. Sınırlar ve belirsizlikler

- **Proxy motor:** Chromium 148 headless; gömülü WKWebView davranışı ölçülmedi.
- **Tek makine / tek snapshot:** 8 Ekim 04:59 kopyası, 20 run. Farklı run boylarında
  oranlar ölçülmedi (run başına ~36 KB istikrarlı görünüyor: 20 run'da 19.044 satır ≈
  952 satır/run).
- **Canlı akış sırasında ölçüm yok:** stub `verify_delivery.py` kullanıldı (canlı
  satır gürültüsü engellendi).
- **"Canlıda tam olarak bu çalışıyor" iddiası** iki kanıta dayanır: port 8000 sürecinin
  argv'si (`--replay-runs` yok) ve canlı dizindeki `preview.js`'in F4'süz olması
  (sha `e1444a34…`). Canlı sunucu **yeniden başlatılmadı** (başka thread'in süreci).
- **Enstrümantasyon farkı:** CDP olay sayısı ±2 ve veri-byte'ı ±%3 sapabiliyor
  (ör. 2-run: sunucu 176.425 B ↔ CDP 181.921 B). Kanonik sayılar sunucu-tarafı build
  ve ham socket ölçümüdür; CDP tarafı davranış için kullanıldı.
- **AT (VoiceOver) senaryosu** ölçülmedi; a11y etkisi main-thread gecikmesi ve AX ağacı
  metrikleri üzerinden raporlandı.

---

## 8. Artefaktlar (izlenebilirlik)

| Artefakt | Yol / kimlik |
| --- | --- |
| Snapshot (ölçüm verisi) | `/tmp/rs_live` — `preview.html 0f771ad3…`, `preview.js e91f8d41…` (bu dal), `history.jsonl c3a844e4…`, `runs/` 20 dosya (liste `66f88d0e…`), 840 KB |
| Canlı dizin kimliği | `preview.js e1444a34…` (105.893 B, 4 Eki 22:38, **0 F4 işareti**), `preview.html 0227766a…` |
| Sunucu-tarafı yük | `/tmp/rs_payload.json` (üretici `/tmp/rs_measure.py`) |
| Ham HTTP/keepalive | `/tmp/rs_cells.jsonl` → `K2-sse` (2.008 olay, keepalive 15,03 s) |
| Tarayıcı hücreleri | `/tmp/rs_cells.jsonl` → `W20`, `W2`, `L20`, `L2` (üretici `/tmp/rs_probe.py`) |
| Sunucu logları | `/tmp/rs_case_{W20,W2,L20,L2}/server.log` |
| Olay adı doğrulaması | `/tmp/rs_names.py` çıktısı: 2 run = `replay-start`×2 + `stderr`×92 + `stdout`×1.912 + `replay-end`×2 |

**Uygulama durumu:** bu turda `preview_server.py` **değiştirilmedi**; teslim edilen
tasarım + ölçümdür. Kod değişikliği istendiğinde §6.1 birebir uygulanabilir durumda.
