# Sunucu Yaşam-Döngüsü Olay-Kaydı (server_events.jsonl)

Dashboard yerel-daemon'unun (`_calisma/CIKTI/preview_server.py`) çökme,
kapanış ve kurtarma olayları artık **kalıcı, append-only bir olay-kaydına**
yazılır. Bu doküman kaydın şemasını, konumunu, gerçek çökme→kurtarma
kanıtını ve tasarım-kararlarını tutar.

## Neden bu kayıt gerekliydi

Daemon stdout/stderr'i daemon-modunda `/dev/null`'a `dup2`'lenir
(`redirect_stdio_to_devnull` — EBADF-onarımı). Yani bir çökme ya da
sinyal-kapanışı olduğunda **kanıt akışı yok olurdu**: Freebuff preview-log
gibi dış-yüzeyler dosya-başına tutulur, döndürülür ve sunucunun kendisiyle
ilişkisi kaybolur. İlk olay-kaydı bu boşluğu kapatır:

- Daemon'ın kendi std-akışına bağımlı değildir (doğrudan diske yazar).
- Append-only: yeniden başlatmalar önceki kayıtları **asla ezmez**
  (`history.jsonl` aksine HISTORY_MAX ile buda).
- Telemetri servisi değildir: yazım her koşulda sessizce başarısız olabilir,
  sunucu-yüzeyi asla etkilenmez.

## Konum ve şema

| Özellik | Değer |
|---|---|
| Konum | `PREVIEW_DIR/logs/server_events.jsonl` (`logs/` gitignore'da) |
| Biçim | JSONL — her satır bağımsız JSON |
| Yazar | `preview_server._lifecycle_event()` |
| Yazım-semantiği | append (`"a"`); mevcut dosya truncate edilmez |

Her satır: `{"ts": ISO-8601-UTC (Z), "event": str, "pid": int, "detail"?: str}`

| Olay | Ne zaman |
|---|---|
| `start` | HTTP sunucu ayağa kalktı (`bind`, `port` detail) |
| `cache_loaded` | Restart sonrası son-run önbelleği yüklendi (`verdict`, `ts`) |
| `signal_exit` | SIGTERM/SIGINT alındı (`signum` detail) |
| `shutdown` | serve_forever bitti; finally-blok kapanışı tamamladı |

## Canlı kanıt: çökme → kurtarma (2026-09-22)

Gerçek daemon-alt-süreçleriyle iki başlatma → SIGTERM → yeniden başlatma
döngüsü; dosyanın birebir kendisi:

```jsonl
{"ts": "2026-09-22T18:36:56.942359Z", "event": "start",       "pid": 71532, "detail": "bind=127.0.0.1 port=18778"}
{"ts": "2026-09-22T18:36:57.084381Z", "event": "signal_exit", "pid": 71532, "detail": "signum=15"}
{"ts": "2026-09-22T18:36:57.084627Z", "event": "shutdown",    "pid": 71532}
{"ts": "2026-09-22T18:36:57.153321Z", "event": "cache_loaded", "pid": 71542, "detail": "verdict=PASS ts=2026-09-22T18:36:56.959009+00:00"}
{"ts": "2026-09-22T18:36:57.158738Z", "event": "start",       "pid": 71542, "detail": "bind=127.0.0.1 port=18778"}
{"ts": "2026-09-22T18:36:57.318741Z", "event": "signal_exit", "pid": 71542, "detail": "signum=15"}
{"ts": "2026-09-22T18:36:57.318976Z", "event": "shutdown",    "pid": 71542}
```

Kronolojiyi okuma: pid 71532 → `start` → SIGTERM (15) → graceful `shutdown`.
pid 71542 → **kurtarma**: aynı preview-dir'e ikinci başlatma; `cache_loaded`
önbellekten son-run durumunu geri yükledi (`verdict=PASS`) ve yeni `start`
düştü. Append-only güvence: ikinci sürecin kayıtları birincisini silmedi.

### Geçmiş çökme kanıtı (kayıt-öncesi dönem)

Kayıt mekanizması yokken daemon kapanışları yalnızca Freebuff preview-log
kuyruğunda görünüyordu — `.freebuff/preview-*.log` (2026-09-21):

```
[main] preview_server: serving … on http://127.0.0.1:8765
[main] SIGTERM/SIGINT received (<frame at 0x10a449440, … code select>), exiting
[verify_loop] done, sleeping 3600s
```

Bu çıktı iki boşluğu gösterir: kanıt dış-dosyada tutuluyordu (daemon-dışı
yüzey) ve `signum` alanı aslında **frame nesnesi**ydi (aşağıda). Olay-kaydı
her iki boşluğu da kapatır.

## Sözleşme-süiti

`_calisma/CIKTI/test_server_events.py` (8 test, hermetik, ~0.35s):

| Test | Sözleşme |
|---|---|
| `test_schema_required_fields` | ts (ISO-Z) + event + pid; detail opsiyonel |
| `test_append_only_across_restarts` | yeniden başlatma mevcut dosyayı ezmez |
| `test_missing_dir_created` | `logs/` yoksa oluşturulur |
| `test_event_failure_never_breaks_server_surface` | yazılamaz dizinde bile yazım exception'suz döner |
| `test_existing_garbage_is_preserved_not_crashed` | eski bozuk satır korunur; okuyucu geçersiz satırı atlar |
| `test_01_start_recorded` | gerçek alt-süreç `start` yazar (pid eşleşmesi) |
| `test_02_sigterm_writes_signal_exit` | SIGTERM → `signal_exit` kayıtta, `shutdown`'dan önce |
| `test_03_restart_recovery_appends_start_cache_loaded` | kurtarma: ikinci süreç append yapar, ts-monoton |

Canlı-testler preview_server.py'yi **stub verify-dir** ile koşar
(`--interval 3600`): gerçek verify-zinciri koşulursa verify-loop thread'i
kapanış-quiesce'ini (join+LOCK tavanı) doldurur — olay-kaydını test
ediyoruz, zinciri değil.

## Bu turda açığa çıkan ve kapatılan üretim-kusuru

`_sig` handler'ı `(term_frame, signum)` imzasıyla yazılmıştı; Python
signal-handler'ları `(signum, frame)` ile çağırır. Sonuç: hem stderr
satırında hem artık olay-detail'inde `signum=<frame at 0x…>` görünüyor.
Onarım: imza `(signum, frame)` — canlı kanıtta `signum=15` (düz).
Kayıt-öncesi .freebuff log'undaki aynı bozuk çıktı, kusurun eskiden
beri var olduğunu doğrular.

## Okuma/tüketme

```bash
tail -20 "$HOME/Library/Caches/com.freebuff/preview/logs/server_events.jsonl"
# veya yerel PREVIEW_DIR'e göre:
tail -20 _calisma/CIKTI/logs/server_events.jsonl
```

Satırlar ts-monoton; `signal_exit` + hemen-ardından `shutdown` normal
graceful-kapanıştır. `start`'ın `signal_exit`/`shutdown` olmadan ardından
gelmesi = **çökme** (sinyalsiz ölüm) — dosya bunu kalıcı olarak kanıtlar.
