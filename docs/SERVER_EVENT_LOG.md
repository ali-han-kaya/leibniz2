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
  (`history.jsonl` aksine HISTORY_MAX ile buda). Boyut tavanı aşılınca dosya
  arşive taşınır — silinmez (bkz. rotasyon politikası).
- Telemetri servisi değildir: yazım her koşulda sessizce başarısız olabilir,
  sunucu-yüzeyi asla etkilenmez.

## Konum ve şema

| Özellik | Değer |
|---|---|
| Konum | `PREVIEW_DIR/logs/server_events.jsonl` (`logs/` gitignore'da) |
| Biçim | JSONL — her satır bağımsız JSON |
| Yazar | `preview_server._lifecycle_event()` |
| Yazım-semantiği | append (`"a"`); mevcut dosya truncate edilmez |
| Arşiv | `PREVIEW_DIR/logs/archive/server_events-<UTC-stamp>.jsonl` |
| Boyut tavanı | `SERVER_EVENTS_MAX_BYTES` = 256 KiB (aşılınca arşive taşınır) |
| Arşiv tavanı | `SERVER_EVENTS_ARCHIVES_MAX` = 5 (en eski arşiv budanır) |

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

## Rotasyon politikası (boyut tavanı + arşiv)

Append-only kayıt sınırsız büyüyemez: aylarca yaşayan bir daemon tek dosyayı
disk-şişmesine çevirir ve panelin okuduğu kuyruğu seyreltir. Politika iki
global ile yönetilir (`preview_server.py`):

| Karar | Kural | Neden |
|---|---|---|
| Tetik | geçerli dosya `SERVER_EVENTS_MAX_BYTES` (256 KiB) aşılınca | görünür tavan; daemon başına sabit disk maliyeti |
| Eylem | dosya `logs/archive/server_events-<UTC-stamp>.jsonl` adına **`os.replace` ile taşınır** | rename atomiktir; truncate DEĞİL — append-only sözü bozulmaz |
| Saklama | en yeni `SERVER_EVENTS_ARCHIVES_MAX` (5) arşiv; eskisi silinir | üst sınır ≈ 1.5 MiB (6 × 256 KiB) |
| Ad sırası | sabit-genişlikli UTC stamp | lexicographic sıra = kronolojik sıra (budama + okuma bu sıraya güvenir) |
| Okuma | `_read_server_events` **arşivler → geçerli dosya** sırasıyla okur | çökme kanıtı rotasyondan sonra da görünür kalır |

### Neden "önce yaz, sonra döndür"

Döndürme yazımdan SONRA çağrılır. Ters sıra (önce döndür, sonra yaz), tam o
pencerede ölen sürecin yazılmakta olan kaydını yok ederdi — ve o kayıt çoğu
kez `signal_exit`/`shutdown`'dır. Yani emniyet için eklenen mekanizma PANELDE
SAHTE ÇÖKME üretirdi (kapanışı düşen süreç "sinyalsiz öldü" görünür). Kayıt
önce diske iner, sonra taşınır: hiçbir olay rotasyon yüzünden kaybolmaz.

### Neden tek dev kayıt döndürülmez

Tek başına tavanı aşan bir kayıt (aşırı uzun `detail`) döndürülmez: aksi
halde her yazım yeni bir arşiv doğurur, budama da onu bir sonraki yazımda
silerek tüm geçmişi yok ederdi. Dev kayıt yerinde kalır; tavan ancak
arkasına İKİNCİ satır gelince işler.

### Canlı kanıt: rotasyon (2026-10-06)

Gerçek daemon, tavan kanıt için 150 bayta çekilerek iki kez koşuldu
(start → SIGTERM → yeniden başlatma). Dosya düzeni:

```
logs/server_events.jsonl                     72 B  (yalnız son kayıt)
logs/archive/server_events-20261006T005017995887Z.jsonl   206 B
logs/archive/server_events-20261006T005019098586Z.jsonl   210 B
logs/archive/server_events-20261006T005019303146Z.jsonl   206 B
```

Geçerli dosya: son `shutdown`. Arşivlerde ise tüm çökme-öncesi durum:

```jsonl
{"event": "start",       "pid": 6319, "detail": "bind=127.0.0.1 port=18992"}
{"event": "signal_exit", "pid": 6319, "detail": "signum=15"}
{"event": "shutdown",    "pid": 6319}
{"event": "cache_loaded", "pid": 6330, "detail": "verdict=FAIL ts=…"}
{"event": "start",       "pid": 6330, "detail": "bind=127.0.0.1 port=18992"}
{"event": "signal_exit", "pid": 6330, "detail": "signum=15"}
```

Okuyucu (`_read_server_events`, arşivler → geçerli) rotasyon SONRASI 7 kaydı
doğru kronolojik sırayla döndürdü ve tümevarım **sahte çökme üretmedi**
(`last_crash: None`, `last_recovery: recovery`). Yani: kayıt kaybolmadı,
kanıt arşivde yaşadı, "önce yaz sonra döndür" kararı sahada doğrulandı.

## Sözleşme-süiti

`_calisma/CIKTI/test_server_events.py` (22 test, hermetik, ~0.4s):

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
| `TestLifecycleSummary` (7 test) | çökme/kurtarma tümevarımı: sinyalsiz ölüm, graceful, recovery, sıra, garbage toleransı |
| `TestServerEventRotation` (7 test) | tavan/arşiv/budama + kayıpsızlık; tek-dev-kayıt koruması; arşiv-içi çökme kanıtı; arşiv kurulamazsa yazım sürer |

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
# rotasyondan sonra eski kayıtlar arşivde yaşar:
ls -1 _calisma/CIKTI/logs/archive/
tail -20 _calisma/CIKTI/logs/archive/server_events-*.jsonl
```

Satırlar ts-monoton; `signal_exit` + hemen-ardından `shutdown` normal
graceful-kapanıştır. `start`'ın `signal_exit`/`shutdown` olmadan ardından
gelmesi = **çökme** (sinyalsiz ölüm) — dosya bunu kalıcı olarak kanıtlar.
