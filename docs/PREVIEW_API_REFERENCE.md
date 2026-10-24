# preview_server `/api/*` — Referans

> **Diátaxis: Reference** — Bilgi-yönelimli. Bu sayfa *tanımlar*, öğretmez ve
> yönlendirmez; arama için düzenlenmiştir.
> Öğrenme: [`FIRST_RUN_TUTORIAL.md`](FIRST_RUN_TUTORIAL.md) ·
> Görev: [`LOCAL_VERIFICATION_HOWTO.md`](LOCAL_VERIFICATION_HOWTO.md) ·
> Sunucuyu ayağa kaldırma run-doc'u: [`RUN_DASHBOARD.md`](RUN_DASHBOARD.md) ·
> Sürümleme politikası: [`API_VERSIONING.md`](API_VERSIONING.md).

**Tek kaynak.** Metot matrisi `API_CONTRACT`'tan türetilir
(`_calisma/CIKTI/test_api_method_contract.py`); bu sözlük kaynak sözleşmesi +
canlı prob olarak iki katmanda pinlidir (`test_api_method_matrix.py`,
`test_run_now_post_only.py`). Yeni bir `/api/*` ucu eklenirse hem
`preview_server.py` hem `API_CONTRACT` aynı commit'te güncellenir — aksi halde
test kırmızı olur.

**Makine-okur ayna.** `_calisma/CIKTI/openapi.json` (üretici:
`gen_openapi.py`, şema kapısı: `test_openapi_schema.py`). Bu sayfadaki alan
listeleri çalışan sunucudan ve handler gövdelerinden çıkarılmıştır; `openapi.json`
kaba (status + tip) katmandır — bkz. §6.

Sunucu: `preview_server.py` (stdlib-only). Varsayılan bind `127.0.0.1`, varsayılan
port `8000` (`--bind`, `--port`).

---

## 1. Metot matrisi

`API_CONTRACT` — tam ve değişmez:

| Yol | Metot | Tür | Dispatch | Yol eşleşmesi |
|---|---|---|---|---|
| `/api/latest` | `GET` | veri | `latest` | tam |
| `/api/trend` | `GET` | veri | `trend` | tam |
| `/api/history` | `GET` | veri | `history` | tam |
| `/api/refs-trend` | `GET` | veri | `refs_trend` | tam |
| `/api/override-trend` | `GET` | veri | `override_trend` | tam |
| `/api/determinism-trend` | `GET` | veri | `det_trend` | tam |
| `/api/a11y` | `GET` | veri | `a11y` | tam |
| `/api/run-history` | `GET` | veri | `run_history` | tam |
| `/api/run-stdout` | `GET` | veri | `run_stdout` | prefix (`?ts=`) |
| `/api/health` | `GET` | veri | `health` | tam |
| `/api/run` | `GET` | akış (SSE) | `sse` | tam |
| `/api/run-stream` | `GET` | akış (SSE) | `run_stream` | tam |
| `/api/run-now` | `POST` | durum değiştiren | `run_now` | prefix |
| `/api/stop` | `POST` | durum değiştiren | `stop` | prefix |

Ayrı pin: `SSE_PATHS = {"/api/run", "/api/run-stream"}` — canlı prob'da sonsuz
akış ürettikleri için yalnız header probu ile doğrulanırlar.

Ek (API dışı): `/slides_z3/` prefix'i `slides` rotasına gider. `.js`, `.html`,
`.png`, design-token ve service-worker yolları `_route`'ta ayrıca çözülür ve
API kapılarına tabi değildir.

## 2. Sunucu düzeyi sözleşmeler

### 2.1 Her yanıtta bulunan başlıklar

`BaseHTTPRequestHandler.end_headers` tek-funnel olarak override edilir; bu
başlıklar `_send`, statik yollar ve SSE dahil **tüm** yanıtlara girer:

| Başlık | Değer |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `no-referrer` |
| `Content-Security-Policy` | `default-src 'none'; script-src 'self' 'nonce-<süreç-başı>'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` |

Ek başlıklar:

| Yol grubu | Ek başlıklar |
|---|---|
| `_send` ile yazılan tüm JSON/düz yanıtlar | `Cache-Control: no-store`, `Content-Length` |
| SSE (`/api/run`, `/api/run-stream`) | `Cache-Control: no-store`, `Connection: keep-alive`, `X-Accel-Buffering: no` |
| `405` (metot kapısı) | `Allow: POST` |
| `401` (bearer) | `WWW-Authenticate: Bearer` |

Nonce **süreç başına bir kez** üretilir (`secrets.token_urlsafe(16)` →
`BUILD_TS_NONCE`): her restart'ta değer değişir, bu yüzden yanıtlar zaten
`Cache-Control: no-store` ile birlikte düşünülmelidir — nonce bir kimlik
token'ı değil, yalnız aynı sürecin enjekte ettiği `<script>`'i yetkilendiren
bir etikettir.

Nonce yalnız `<script>` etiketlerini yetkilendirir; CSP spec'i gereği **olay
niteliklerini kapsamaz**. Bu yüzden yüzeyde inline `on*=` kullanılamaz:
`preview.js` 21 `addEventListener` kaydıyla çalışır, `preview_server.py` ve
`preview.html` sıfır inline nitelik taşır. Sıkılaştırılmış bir CSP altında
inline bir `onclick` sessizce ölür (betik hiç çalışmaz, konsolda hata bile
görünmez) — yeni etkileşim eklerken kural: `on*=` değil, olay delegasyonu.

Bu kural iki katmanda ÖLÇÜLÜR (kağıt üzerinde değil):

- **Statik sayaç** — `test_preview_server.InlineEventHandlerContractTests`
  servis edilen her `.html` yüzeyini + `preview.js`'i + üretilen
  `design_preview.html`'i tarar; `inline-handler sayacı != 0` ise FAIL,
  taranan yüzey beklenenden azsa da FAIL (boş kanıt geçmez). Tarayıcı
  gerekmez, `verify` job'ında koşar.
- **Canlı DOM sayacı** — `test_dashboard_budget_rh_filters.py` gerçek
  Chromium'da filtre/detay etkileşimlerini sürdükten sonra `on*`
  niteliklerini sayar ve konsoldaki CSP ihlallerini toplar; ikisi de
  sıfır olmalı.
- **Artifact'ın tooltip kanıtı (tarayıcı tier'i)** —
  `test_design_preview_hover_csp.py` üretilen `design_preview.html`'i
  gerçek Chromium'da, ÜRETİM CSP başlığıyla (`preview_server`'dan okunur)
  açar ve iki şeyi pinler: (a) nonce'suz artifact'ın tek inline `<script>`'i
  CSP tarafından BLOKLANIR — yani artifact "CSP altında" ancak servis
  katmanı nonce enjekte ederse çalışır (`serve_preview`'ın `preview.html`
  için yaptığı şey); (b) nonce verilince üç grafiğin hover tooltip'i
  gerçek fare hareketiyle satıra bağlı içerik gösterir (#tip görünür,
  refs 2. sütun → 17/40, 4. sütun → 31), mouseleave gizler ve konsolda
  CSP ihlali olmaz. (a) bir pozitif kontroldür: CSP gevşetilirse test
  kırmızıya düşer, yani (b)'nin kanıtı çürük kalmaz. Süit `# SECURITY-TIER:
  browser` işaretiyle browser roster'ına girer → `a11y-gate` işinde
  `check_security_posture.sh` ile koşar ve SKIP'i REDDEDER.

Bu belgedeki "sıfır inline nitelik" ifadesi bir iddia değil, sayaçla
kilitlenmiş bir sözleşmedir.

### 2.2 Hata zarfı

`api_error(status, message)` → `(status, {"error": message})`. JSON hata
gövdeleri her zaman bu tek anahtarlı zarftır; içerik tipi
`application/json; charset=utf-8`.

### 2.3 Kapılar (guard) — sıra önemlidir

| Kapı | Kapsam | Reddi |
|---|---|---|
| TCP-peer | `POST /api/run-now`, `POST /api/stop` (`STOP_ALLOWLIST`) | `403 {"error": …}` |
| Host/Origin (DNS-rebinding) | query'den arındırılmış yolu `/api/` ile başlayan her `GET` ve `HEAD` isteği — route tablosunda karşılığı olmayan yollar **dahil** (karar yol önekinden, route token'ından değil; yeni bir uç eklenip kümeye yazılmazsa veri sızmaz) | `403 {"error": …}` |
| Bearer | yalnız `POST /api/run-now`, `PREVIEW_RUN_NOW_TOKEN` **set ise** | `401 {"error":"unauthorized"}` + `WWW-Authenticate: Bearer` |
| Metot | `GET` ile `run-now`/`stop` | `405 {"error":"method not allowed"}` + `Allow: POST` |

`PREVIEW_RUN_NOW_TOKEN` tanımsızsa bearer kapısı devre dışıdır (yerel varsayılan).

### 2.4 Yol ve metot çözümü

- Query string rotalamayı etkilemez: `?_t=…`, `?v=…` cache-buster'ları aynı
  rotaya düşer.
- Bilinmeyen `/api/*` → `404 {"error":"not found"}` (JSON) — **yalnız güvenilen
  Host/Origin'de**; güvenilmeyen istek route çözümünden önce `403` alır.
- Bilinmeyen `/api/` dışı yol → `404 not found` (düz metin).
- `HEAD` → tanınan rota için `200 text/plain; charset=utf-8`, gövdesiz;
  tanınmayan rota için `404`. GET metot matrisini değiştirmez. `/api/*`
  HEAD'leri GET ile aynı Host/Origin kapısına tabidir (`403`), çünkü
  başlıklar da rota keşfine yarar.

`_API_GET_ROUTES` kapı kararı **vermez**; ilan edilen GET yüzeyini belgeler ve
`_route()` token'larıyla iki yönlü senkron kalır (eksik/fazla ad
`test_local_security_surface` testini kırmızı düşürür).

### 2.5 Sabitler ve limitler

| Sabit | Değer | Anlam |
|---|---|---|
| `HISTORY_MAX` | `100` | `/api/history` kaynağında disk'te tutulan en son run sayısı |
| `RUN_LOG_MAX` | `20` | `/api/run-stream` replay'inde akıtılan en son run sayısı |
| `/api/run-history` penceresi | `15` | Döndürülen run özeti sayısı (kod içinde sabit) |
| `SSE_POLL_TIMEOUT` | `15` | SSE keepalive periyodu (saniye); boşta-tahliye denetiminin de tiki |
| `SSE_MAX_CLIENTS` | `8` | Kanal başına eşzamanlı SSE bağlantı tavanı (`0` = sınırsız) |
| `SSE_IDLE_TIMEOUT` | `300` | Gerçek olay almayan SSE bağlantısının ömrü (saniye; `0` = tahliye kapalı) |
| `SSE_RETRY_HINT_MS` | `60000` | `evicted` sonrası istemciye verilen yeniden-deneme ipucu (`retry:` alanı) |
| `HISTORY_DASHBOARD_KEYS` | 19 alan | `/api/history` yanıtında dışa verilen alt küme |

### 2.6 SSE kaynak politikası (`/api/run`, `/api/run-stream`)

Her SSE bağlantısı `ThreadingHTTPServer`'da bir iş parçacığı tutar; iki kanal
**ayrı** sayılır. Tavan doluysa bağlantı sessizce bekletilmez:

| Durum | Yanıt |
|---|---|
| Tavan (`SSE_MAX_CLIENTS`) dolu | `503 {"error":"too many SSE clients","channel":…,"limit":…}` + `Retry-After: 30`; istemci kaydedilmez |
| `SSE_IDLE_TIMEOUT` boyunca gerçek olay yok | `retry: 60000` + `event: evicted` (`reason:"idle-timeout"`, `idle_s`) → handler döner, soket kapanır, kayıt silinir |

Keepalive (`: keepalive`) ömrü **uzatmaz** — yalnızca canlılık sinyalidir.
`/api/run-stream`'de replay gerçek trafiktir; boşta sayacı replay bittikten
sonra başlar. Tahliye denetimi keepalive tikinde koşar, yani kapatma en geç
`SSE_IDLE_TIMEOUT + SSE_POLL_TIMEOUT` saniyede gerçekleşir. İstemci tarafı
(`preview.js`) `evicted` nedenini gösterip backoff'lu yeniden bağlanır.

## 3. Uç noktalar

### `GET /api/health`

| Alan | Değer |
|---|---|
| Durum | `200` |
| İçerik tipi | `text/plain; charset=utf-8` |
| Gövde | `ok` |

Yan etki yok. Host/Origin kapısına **tabidir** (bkz. §2.3).

### `GET /api/latest`

| Alan | Değer |
|---|---|
| Durum | `200` |
| İçerik tipi | `application/json; charset=utf-8` |
| Gövde | `snapshot_dict()` — son doğrulama koşusunun dashboard görünümü |

Alanlar (çalışan sunucudan, alfabetik): `audit_refs_trend, budget, budget_limit,
budget_method, budget_usd, cached, cli_override_count, cli_overrides,
config_diff, deterministic_count, duration_pct_warn, duration_s, exit_code,
failure_pattern, findings, flaky_count, history_sidecar_sha256, hook_env,
hook_env_matrix, layers, lean_detail, lean_ok, lean_override, lean_source,
lineage_count, lineage_ok, lineage_summary, mirror_stale, mirror_sync,
override_report, p0, p1, pattern_drift, pattern_drift_detail, pdf_pages,
precommit_hooks, raw_sha256, ref_count, refs_by_source, refs_mismatch,
refs_online, refs_total, refs_verified, status_board, stderr_short, stdout_short,
stripped_sha256, ts, verdict, z3_failed, z3_passed, z3_total`.

`stdout_short`/`stderr_short` tam çıktı değil, kuyruklardır (son 50 / son 20
satır). Tam stdout için `GET /api/run-stdout?ts=`.

### `GET /api/trend`

| Alan | Değer |
|---|---|
| Durum | `200` |
| Gövde | `{"history": […], "refs_trend": {…}}` |

Tek fetch'te `/api/history` + `/api/refs-trend` birleşimi; ikisi de ayrıca
sunulmaya devam eder (legacy).

### `GET /api/history`

| Alan | Değer |
|---|---|
| Durum | `200` |
| Gövde | JSON **dizi** — `load_history()` kayıtlarının dashboard projeksiyonu |

Projeksiyon `HISTORY_DASHBOARD_KEYS` ile sınırlıdır (19 alan): `ts, verdict, p0,
p1, duration_s, budget_usd, budget_limit, budget_method, refs_verified,
refs_total, refs_mismatch, refs_by_source, hook_env, z3_passed, z3_failed,
z3_total, lean_ok, lean_detail, cli_override_count`.

Kaynak: JSONL trend dosyası (`HISTORY_MAX` = 100 satır). Disk üzerindeki tam
şema `HISTORY_KEYS`'tir (37 alan) ve bu alt kümeden geniştir.

#### `status_board` ve arkasındaki `layers`

Her arşiv satırı iki kapı kaydı taşır:

- `status_board` — 5 ikonlu tek satır özet (`Pre-commit … · K0 … ·`) ve P0/P1
  sayılarından türeyen `K0` ikonu. Özet olduğu için K0 ikonu, K0 katmanının
  kendi durumu DEĞİLDİR.
- `layers` — koşunun **gerçek** K0–K21 haritası (`{"K0": {"status": "PASS"}}`).
  `_finalize_run` bunu verify `--json` çıktısından alır; çıktı taşımıyorsa
  aynı koşunun `klayers.json` sidecar'ından (verdict + P0/P1 + tazelik
  eşleşmesi) tamamlar; hiç kanıt yoksa `null` kalır — PASS uydurulmaz.
  `layers` büyük alan olduğu için `/api/trend` projeksiyonunda yoktur,
  kalıcı satırda ve `/api/latest`'te durur.

`layers` alanı 2026-10-17'de sözleşmeye girdi; önceki satırlar yalnız özeti
taşır. Onları `_calisma/CIKTI/backfill_history_layers.py` tamamlar: satırın
kendi `runs/run-<ts>.json` kaydındaki verify JSON'ından `layers` okur, aynı
`ts` dışında eşleşme kabul etmez, var olanı ezmez, atomik yazar ve
`history.jsonl.sha256` sidecar'ını (K15) yeniden üretir.

```bash
python3 _calisma/CIKTI/backfill_history_layers.py          # plan
python3 _calisma/CIKTI/backfill_history_layers.py --apply  # yaz
```

#### Önbellek — in-process, `mtime_ns` anahtarlı

| Özellik | Değer |
|---|---|
| Anahtar | `(HISTORY_PATH, st_mtime_ns, st_size)`; dosya yoksa `None` |
| Geçersizleşme | `persist_history` dosyayı `LOCK` altında `_write_atomic` ile yeniden üretir; `mtime_ns` değişimi önbelleği düşürür |
| Kapsam | `/api/history` ve `/api/trend` aynı önbelleği paylaşır; süreç yeniden başlayınca kaybolur |
| Dönen değer | Yeni **liste** (kopyadır); satır-dict'leri salt-okunur paylaşılır, çağıran mutasyon yapmamalı |
| Dosya yoksa | `[]` — önbellek atlanır, anahtar `None` |
| Gerekçe | Profil: `load_history` istek-işininin ~%45'i; istek başına ~100 `json.loads` atlanıyor (270 KB JSONL) |

Doğruluk **tek yazıcı** varsayımına dayanır: `persist_history` dosyayı atomik
olarak yeniden üreten tek yazıcıdır, bu yüzden "aynı `mtime_ns` + aynı boyut
= aynı içerik" eşitliği güvenlidir. Dosyaya ikinci bir yazıcı eklenirse bu
varsayım bozulur ve bayat satırlar okunabilir. Bozuk JSON satırları atlanır,
dosya silinmez.

### `GET /api/refs-trend`

| Alan | Değer |
|---|---|
| Durum | `200` |
| Gövde | `{"rows": […], "duration_budget": {"rows": […]}}` |
| Kaynak yok | `200 {"rows": [], "duration_budget": {"rows": []}}` |
| Ayrıştırma hatası | `500 {"error": "refs trend unavailable"}` |

### `GET /api/override-trend`

| Alan | Değer |
|---|---|
| Durum | `200` |
| Gövde | `{"rows": […], "run_count": <int>, "warning_run_count": <int>}` |
| Kaynak yok | `200 {"rows": []}` |
| Ayrıştırma hatası | `500 {"error": "override trend unavailable"}` |

### `GET /api/determinism-trend`

| Alan | Değer |
|---|---|
| Durum | `200` |
| Gövde | `{"badge": {…}, "rows": […]}` |

`badge`, `determinism_trend_badge.py` çıktısıdır (kendi pinli testi vardır).

### `GET /api/a11y`

| Alan | Değer |
|---|---|
| Durum | `200` |
| Gövde | `{"available": <bool>, "reports": [...], "note": <str|null>}` |
| Artifact yok | `200 {"available": false, "reports": [], "note": "… — kanıt yok"}` |
| Rapor okunamaz / tavan aşımı | `200`, ilgili satır `verdict: null` + `error` |

Satır alanları: `page` (`dashboard|guide|landing`), `theme` (`dark|light`),
`verdict` (`PASS|FAIL|null`), `summary` (`blocking/warn/allowlisted/incomplete`),
`error`, `file`.

**Kaynak.** CI artifact JSON'ları: `a11y_<sayfa>_<tema>.json` (verify.yml
a11y-gate job'ı; `a11y_dashboard_dark.json` vb.). Aranan konumlar sırayla
`<repo>/a11y-reports/`, `<repo>/`, `<preview-dir>/a11y-reports/`,
`<preview-dir>/` ve alt dizinler (`gh run download` her artifact için bir alt
dizin açar → `a11y-reports/a11y-report-dark/a11y_dashboard_dark.json`).

**Fail-closed.** Ham `raw` axe payload'ı bilerek dışarı VERİLMEZ (panel yalnız
verdict + özet görür); okunamayan/taşkın (> 4 MB) rapor `verdict: null` + gerekçe
döner — ölçülmemiş PASS panelde de yeşil görünmez. Panel:
`preview.html#a11y-panel` + `preview.js renderA11y()/loadA11y()`
(`test_preview_a11y_panel.py`).

```bash
gh run download <run-id> -n a11y-report-dark -n a11y-guide-report-dark \
  -n a11y-landing-report-dark -D a11y-reports
```

### `GET /api/run-history`

| Alan | Değer |
|---|---|
| Durum | `200` |
| Gövde | JSON **dizi** — son **15** run özeti (stdout/stderr hariç) |

Özet alanları: `ts, verdict, p0, p1, budget_usd, budget_limit, budget_method,
duration_s, refs_verified, refs_total, pdf_pages, z3_passed, z3_total, lean_ok,
lean_detail`.

### `GET /api/run-stdout?ts=<ISO-8601>`

| Alan | Değer |
|---|---|
| Durum | `200` |
| Gövde | `{"ts": …, "stdout": …, "stderr": …}` |
| `?ts=` yok | `400 {"error": "?ts= gerekli"}` |
| Run bulunamadı | `404 {"error": "run bulunamadı: <ts>"}` |

`ts`, `runs/run-<safe>.json` dosya adına `:` `+` `.` karakterleri atılarak
çözülür. Timestamp `+00:00` içerdiği için URL-encode edilmelidir (ham `+`
boşluğa dönüşür ve run bulunamaz).

### `GET /api/run` — SSE

| Alan | Değer |
|---|---|
| Durum | `200` |
| İçerik tipi | `text/event-stream; charset=utf-8` |
| Olaylar | `snapshot` (bağlantı anında tam görünüm), `update` (sonraki güncellemeler), `evicted` (boşta tahliye) |
| Keepalive | `: keepalive` yorum satırı, `SSE_POLL_TIMEOUT` = 15 s hareketsizlikte |
| Tavan / tahliye | `SSE_MAX_CLIENTS` = 8 (kanal başına) → üstü `503`; `SSE_IDLE_TIMEOUT` = 300 s → `evicted` |

`data:` yükü `/api/latest` ile aynı snapshot zarfıdır. Türetilmiş alanlar olay
içinde hesaplanır; tüketici her olayda `/api/latest`'e başvurmak zorunda değildir.

### `GET /api/run-stream` — SSE

| Alan | Değer |
|---|---|
| Durum | `200` |
| İçerik tipi | `text/event-stream; charset=utf-8` |
| Olay sırası | `info` → replay (`replay-start`, satırlar, `replay-end`) → canlı satırlar → `end` |
| Keepalive | `: keepalive` yorum satırı (15 s) |
| Tavan / tahliye | `/api/run` ile aynı (`SSE_MAX_CLIENTS`, `SSE_IDLE_TIMEOUT`); sayaç replay sonrası başlar |

Olay adları `data` içindeki `stream` alanından türetilir (§4).

### `POST /api/run-now`

Arka plan thread'inde doğrulama koşusu başlatır; istek anında döner.

| Durum | Gövde | Tetik |
|---|---|---|
| `200` | `{"status": "started", "ts": …, "note": …}` | Koşu başlatıldı |
| `409` | `{"status": "already_running", "ts": …, "note": "bir verify zaten koşuyor"}` | `VERIFY_BUSY` dolu |
| `401` | `{"error": "unauthorized"}` | Token set, `Authorization: Bearer <token>` yok/yanlış |
| `403` | `{"error": …}` | Peer veya Host/Origin kapısı |
| `405` | `{"error": "method not allowed"}` | `GET` ile çağrı (bkz. §2.3) |
| `404` | `{"error": "not found"}` | Eşleşmeyen `/api/*` |

### `POST /api/stop`

Sunucusu durdurur (daemon modu için).

| Durum | Gövde | Tetik |
|---|---|---|
| `202` | `{"status": "stopping"}` | Kabul edildi; kapanma ayrı thread'de |
| `503` | `{"error": "server not ready"}` | `STOP_EVENT`/`SERVER` henüz kurulmamış |
| `403` | `{"error": …}` | Peer veya Host/Origin kapısı |
| `405` | `{"error": "method not allowed"}` | `GET` ile çağrı |
| `404` | `{"error": "not found"}` | Eşleşmeyen `/api/*` |

`POST /api/run-now` ile aynı peer kapısını (`STOP_ALLOWLIST`) taşır; `/api/stop`
bearer kapısı **taşımaz**.

## 4. SSE olay sözlüğü

| Olay | Yayın | `data` alanları | Ne zaman |
|---|---|---|---|
| `snapshot` | `/api/run` | snapshot zarfı (§3 `latest`) | Bağlantı kurulur kurulmaz |
| `update` | `/api/run` | aynı zarf | Her yeni snapshot |
| `info` | `/api/run-stream` | `stream:"info"`, `ts`, `verdict` | Bağlantı kurulur kurulmaz |
| `replay-start` | `/api/run-stream` | `stream:"replay-start"`, `ts`, `verdict`, `p0`, `p1`, `budget_usd`, `duration_s`, `first`, `refs_verified`, `refs_total`, `pdf_pages` | Her replay edilen run'ın başında |
| `stdout` / `stderr` | `/api/run-stream` | `stream:"stdout"\|"stderr"`, `line`, (`replay:true` replay'de) | Canlı satır / replay satırı |
| `replay-end` | `/api/run-stream` | `stream:"replay-end"`, `ts` | Her replay edilen run'ın sonunda |
| `end` | `/api/run-stream` | `stream:"end"`, `snapshot` | Canlı koşu bittiğinde (son snapshot) |
| `evicted` | `/api/run`, `/api/run-stream` | `stream:"evicted"`, `channel`, `reason:"idle-timeout"`, `idle_s` | `SSE_IDLE_TIMEOUT` boyunca gerçek olay yoksa; öncesinde `retry: 60000` alanı gelir |

Replay, `load_run_logs(RUN_LOG_MAX)` kayıtlarını en eski→en yeni sırayla akıtır;
`replay-start`'ta `first: true` ilk kayda işaret eder. Tampon dolduğunda en eski
satırlar düşer (`_offer_latest`: non-blocking, tavan korunur; satır akışı
512, snapshot kanalı 64 satır/client). Yayın **asla bloklamaz** — yarı-kapalı
bir istemcinin dolu kuyruğu finalize'ı (LOCK altında) bekletmesin; bu yüzden
snapshot yayını da bloklayan `put` değil `_offer_latest` kullanır.

## 5. Durum kodu dizini

| Kod | Gövde biçimi | Tetikleyiciler |
|---|---|---|
| `200` | JSON / `ok` / event-stream | Başarılı veri, başarılı tetikleme |
| `202` | JSON | `POST /api/stop` kabul edildi |
| `400` | `{"error": …}` | `GET /api/run-stdout` — `?ts=` eksik |
| `401` | `{"error":"unauthorized"}` | `POST /api/run-now` — bearer eksik/yanlış |
| `403` | `{"error": …}` | Peer kapısı ya da Host/Origin kapısı |
| `404` | `{"error": …}` (JSON) / `404 not found` (düz) | Bilinmeyen `/api/*` (JSON); run bulunamadı; API dışı bilinmeyen yol (düz) |
| `405` | `{"error":"method not allowed"}` | `GET` ile `run-now`/`stop`; `Allow: POST` |
| `409` | `{"status":"already_running", …}` | `POST /api/run-now` — eşzamanlı koşu |
| `500` | `{"error": …}` | `refs-trend` / `override-trend` kaynağı ayrıştırılamadı |
| `503` | `{"error":"server not ready"}` / `{"error":"too many SSE clients",…}` | `POST /api/stop` — sunucu durumu kurulmamış; SSE `GET /api/run`·`/api/run-stream` — kanal tavanı dolu (+ `Retry-After: 30`) |

## 6. Bilinen farklar (makine-okur ayna)

`openapi.json` kaba katmandır; aşağıdaki noktalarda bu sayfadan daha zayıftır:

| Fark | Ayrıntı |
|---|---|
| Dizi gövdeler `object` tiplenir | `/api/history` ve `/api/run-history` runtime'da JSON **dizi** döner; `openapi.json` ikisini de `type: object` yazar (`gen_openapi.py` projeksiyonu) |
| Zarf durumları eksik | `400`, `401`, `403`, `405` `openapi.json`'da listelenmez |
| Yanıt şemaları boş | `components.schemas` boştur — alan düzeyi sözleşme yalnız bu sayfada ve kodda yaşar |
| SSE gövdesi | `openapi.json` SSE yollarını `type: string` ile işaretler; olay protokolü §4'tedir |

Sözleşmeyi pinleyen testler: `test_api_method_contract.py` (kaynak + canlı),
`test_api_method_matrix.py`, `test_run_now_post_only.py`,
`test_openapi_schema.py`, `test_preview_server.py`.

---

*Türetme:* metot matrisi `API_CONTRACT`'tan; durum kodları/gövdeler handler
gövdelerinden; alan listeleri çalışan bir `preview_server` örneğinden
(2026-09-24, throwaway port) ve `openapi.json` karşılaştırmasından. Yanıt
örnekleri koşum ortamına göre değişir; kodlar ve zarf biçimleri değişmez.
