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

### 2.2 Hata zarfı

`api_error(status, message)` → `(status, {"error": message})`. JSON hata
gövdeleri her zaman bu tek anahtarlı zarftır; içerik tipi
`application/json; charset=utf-8`.

### 2.3 Kapılar (guard) — sıra önemlidir

| Kapı | Kapsam | Reddi |
|---|---|---|
| TCP-peer | `POST /api/run-now`, `POST /api/stop` (`STOP_ALLOWLIST`) | `403 {"error": …}` |
| Host/Origin (DNS-rebinding) | `_API_GET_ROUTES` = `latest, sse, run_stream, history, refs_trend, trend, override_trend, determinism_trend, run_history, health, stop, run_now` | `403 {"error": …}` |
| Bearer | yalnız `POST /api/run-now`, `PREVIEW_RUN_NOW_TOKEN` **set ise** | `401 {"error":"unauthorized"}` + `WWW-Authenticate: Bearer` |
| Metot | `GET` ile `run-now`/`stop` | `405 {"error":"method not allowed"}` + `Allow: POST` |

`PREVIEW_RUN_NOW_TOKEN` tanımsızsa bearer kapısı devre dışıdır (yerel varsayılan).

### 2.4 Yol ve metot çözümü

- Query string rotalamayı etkilemez: `?_t=…`, `?v=…` cache-buster'ları aynı
  rotaya düşer.
- Bilinmeyen `/api/*` → `404 {"error":"not found"}` (JSON).
- Bilinmeyen `/api/` dışı yol → `404 not found` (düz metin).
- `HEAD` → tanınan rota için `200 text/plain; charset=utf-8`, gövdesiz;
  tanınmayan rota için `404`. GET metot matrisini değiştirmez.

### 2.5 Sabitler ve limitler

| Sabit | Değer | Anlam |
|---|---|---|
| `HISTORY_MAX` | `100` | `/api/history` kaynağında disk'te tutulan en son run sayısı |
| `RUN_LOG_MAX` | `20` | `/api/run-stream` replay'inde akıtılan en son run sayısı |
| `/api/run-history` penceresi | `15` | Döndürülen run özeti sayısı (kod içinde sabit) |
| `SSE_POLL_TIMEOUT` | `15` | SSE keepalive periyodu (saniye) |
| `HISTORY_DASHBOARD_KEYS` | 19 alan | `/api/history` yanıtında dışa verilen alt küme |

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
şema `HISTORY_KEYS`'tir (36 alan) ve bu alt kümeden geniştir.

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
| Olaylar | `snapshot` (bağlantı anında tam görünüm), `update` (sonraki güncellemeler) |
| Keepalive | `: keepalive` yorum satırı, `SSE_POLL_TIMEOUT` = 15 s hareketsizlikte |

`data:` yükü `/api/latest` ile aynı snapshot zarfıdır. Türetilmiş alanlar olay
içinde hesaplanır; tüketici her olayda `/api/latest`'e başvurmak zorunda değildir.

### `GET /api/run-stream` — SSE

| Alan | Değer |
|---|---|
| Durum | `200` |
| İçerik tipi | `text/event-stream; charset=utf-8` |
| Olay sırası | `info` → replay (`replay-start`, satırlar, `replay-end`) → canlı satırlar → `end` |
| Keepalive | `: keepalive` yorum satırı (15 s) |

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

Replay, `load_run_logs(RUN_LOG_MAX)` kayıtlarını en eski→en yeni sırayla akıtır;
`replay-start`'ta `first: true` ilk kayda işaret eder. Tampon dolduğunda en eski
satırlar düşer (`queue.put_nowait`, kapasite 512 satır/client).

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
| `503` | `{"error":"server not ready"}` | `POST /api/stop` — sunucu durumu kurulmamış |

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
