# trend-db — doğrulama-zinciri trend geçmişinin Postgres katmanı

`history.jsonl` (verify koşumları, 40+ alan) → Neon Postgres `TrendRun` tablosu.
Skill: `prisma-database-setup` (Prisma 7 + `@prisma/adapter-pg`) + `neon-postgres`
bağlantı sözleşmesi (pooled/direct ayrımı).

## Durum (2026-09-25)

- ✅ Şema (`prisma/schema.prisma` — HISTORY_KEYS'in 42 alanının tam modeli), config, loader, testler
- ✅ Drift-guard: `test_trend_db_contract.py` HISTORY_KEYS ↔ şema ↔ loader sürüklenmesini yakalar
- ✅ Credentialsuz kapılar: `prisma validate` + `prisma generate`
- ✅ **Neon kurulu** — proje `leibniz2-trend` (`orange-bar-58985004`, `aws-eu-central-1`),
  `neon env pull` ile `.env`, migration `20260925171004_init` uygulandı
- ✅ `trend_runs` **kalıcı arşivdir** — kayan 100-koşuluk `history.jsonl` penceresinin
  (`HISTORY_MAX=100`) düşürdüğü eski koşuları da saklar; `npm run load` ile idempotent senkron
- ✅ `dashboard-next` artık bu tablodan okuyor (`lib/trend-db.ts`)
- ✅ `--dry-run` ön-uçuş (2026-09-27; DB'siz satır sayacı + kaynak SHA-256)
- ✅ RLS şablonu (2026-09-27; service-role yazar / anon aggregate okur) — migration hazır, **uygulama bekliyor**

## Kurulum (tamamlanmış hali)

```bash
cd apps/trend-db
neon env pull --project-id orange-bar-58985004 -e DATABASE_URL -e DATABASE_URL_UNPOOLED -e NEON_BRANCH
set -a && . ./.env && set +a
DATABASE_URL="$DATABASE_URL_UNPOOLED" npx prisma migrate deploy   # init + RLS (pooled'a dokunmaz)
npm run load -- --dry-run        # ön-uçuş: DB'ye dokunmadan sayaç + kaynak SHA-256
npm run load                     # TCC-mirror history.jsonl → TrendRun (idempotent, pooled)
```

> `prisma migrate deploy` (interaktif olmayan, yalnız bekleyen migration'ları
> uygular) tercih edilir: `migrate dev` paylaşılan bir veritabanında drift
> tespit edip **reset** önerebilir. `DATABASE_URL` override'ı zorunludur —
> migration PgBouncer (pooled) üzerinden koşmaz (`prepared statement` çakışması,
> kayan `SET` session-state, `SQLSTATE 25006`).

## Dry-run (ön-uçuş): `--dry-run`

DB'ye **dokunmadan** yüklemenin ne yapacağını raporlar: eşleme gerçek koşuyla
aynı `prepare()` yolundan geçer (rapor ile yükleme ayrışamaz), Prisma Client
hiç kurulmaz ve `DATABASE_URL` **gerekmez** — kimlik bilgisi olmayan makinede
veya CI'da koşabilir.

```bash
cd apps/trend-db
npm run load -- --dry-run                      # TCC-mirror history.jsonl
npm run load -- /yol/history.jsonl --dry-run   # belirli kaynak
```

```
[DRY-RUN] kaynak: …/preview/history.jsonl (36612 bayt)
[DRY-RUN] sha256: ce8f66b0…eddb3759
[DRY-RUN] satır: 36 dolu / 37 fiziksel (boş atlanan: 1)
[DRY-RUN] aday: 36 · doğrulama-dışı atlanan: 0
[DRY-RUN] dosya-içi çakışma: 0 (aynı ts veya aynı satır-hash → ON CONFLICT DO NOTHING)
[DRY-RUN] eklenecek (en çok): 36 · atlanacak (en az): 0
[DRY-RUN] DB bağlantısı kurulmadı (DATABASE_URL gerekmez); mevcut satırlarla çakışma bu raporda YOK — kesin sayı için normal koşu
```

- **Sayaç sözleşmesi:** `aday` = dosyadan gelen geçerli kayıt; `atlanacak` =
  doğrulama-dışı satırlar (`ts` yok / `verdict` string değil / JSON nesnesi
  değil, ör. `null`) + dosya-içi çakışma (aynı `ts` veya aynı
  `source_row_sha256`). Çakışan satır JS'te elenir — sonuç
  `ON CONFLICT DO NOTHING` ile birebir aynı (ilk görülüm kazanır) ve böylece
  rapor ile gerçek koşunun sayaçları aynı olur.
- **Ölçülemeyen:** DB'de **zaten duran** satırlarla çakışma bağlantısız
  bilinemez; bu yüzden çıktı "en çok eklenecek / en az atlanacak" der. Kesin
  sayı ancak normal koşunun `bitti:` satırından okunur.
- **Kaynak SHA-256:** dosyanın **baytlarından** hesaplanır ve ayrıştırma aynı
  okumadan yapılır (ikinci okuma = TOCTOU penceresi yok); mühür/karşılaştırma
  için rapora basılır. Normal koşunun açılış satırı da sha256'yı yazar.
- **Çıkış kodları:** `0` = yüklenebilir, `1` = kaynak okunamaz / bozuk JSON
  (satır numarasıyla), `2` = kullanım hatası (bilinmeyen bayrak ya da fazla
  argüman — `--dri-run` yazım hatası sessizce yükleme başlatmaz).
- Sözleşme testleri: `_calisma/CIKTI/test_trend_db_contract.py`
  (`TestTrendDbDryRun` — gerçek `tsx` koşusu, kimlik bilgisi verilmeden).

## RLS (satır düzeyi güvenlik) — `20260927193000_trend_runs_rls`

Şablon: `prisma/migrations/20260927193000_trend_runs_rls/migration.sql`.
Sözleşme: **service-role YAZAR, anonim YALNIZ aggregate OKUR.** Skill
`supabase-postgres-best-practices` kuralları ve her kararın gerekçesi dosyanın
başındadır (`security-rls-basics` CRITICAL · `security-privileges` MEDIUM ·
`security-rls-performance` HIGH).

| Nesne | Rol | Yetki |
|---|---|---|
| `public.trend_runs` (yazma) | `trend_service` | `select/insert/update/delete` + sequence `usage,select` |
| `public.trend_runs` (okuma) | `trend_anon` | **yok** — grant ve policy yok (RLS'te "deny") |
| `public.trend_runs_daily` (view) | `trend_anon` | yalnız `select` — gün × verdict aggregate |

- **RLS enable + `force`:** tablo sahibi de politikalara tabidir; yazar
  politikası `for all to trend_service using (true) with check (true)`, anon
  için temel tabloda politika YOK (bilinçli deny).
- **En az yetki:** `grant all` yok, `revoke all ... from public` (şema + tablo +
  sequence), anon temel tabloya hiç yetkili değil.
- **Anon yüzeyi agregattır:** görünüm yalnız `day/verdict/counts/avg/sum` seçer;
  `findings`, `cli_overrides`, `hook_env`, `*_sha256`, `lineage_*`, `status_board`
  gibi hassas kolonlar gövdeye giremez — `_calisma/CIKTI/test_trend_db_rls_contract.py`
  bu sözleşmeyi statik olarak (DB'siz) kapıya bağlar.
- **Geçici köprü:** mevcut yükleme hattı `neondb_owner` ile bağlandığı için
  migration `grant trend_service to neondb_owner` yapar (guard'lı + `raise
  notice`). FORCE RLS owner'ı da kapsadığı için bu köprü olmadan `npm run load`
  düşer. Kalıcı çözüm: loader için ayrı login rolü (`grant trend_service to
  trend_loader`) ve köprünün düşürülmesi (dosyanın 5. ve 9. blokları).
- **Anon satır okuma GEREKİRSE:** dosyanın 7. bloğu (yorumda) dar kolon
  grant'ı + `security_invoker = true` görünüm verir; varsayılan yol bu değildir.

**Ölçülen davranış** (2026-09-27, rollback'li transaction — kalıcı iz yok,
`neondb_owner` + PG 18.6): `rls=true forced=true`, `trend_runs` policy 1
(`cmd=* → trend_service`), roller 2, görünüm 1.

| Probe | Sonuç |
|---|---|
| yazar `select/insert/update/delete` | **OK** |
| anon `select public.trend_runs_daily` | **OK** (3 gün; 133 PASS 09-25, 100 PASS + 36 FAIL 09-26) |
| anon `select/insert/update/delete public.trend_runs` | **DENIED** `42501` (dördü de) |
| anon `select findings, raw_sha256` | **DENIED** `42501` |
| görünüm kolon yüzeyi | yalnız 9 aggregate kolon |

> Köprüyü düşürmenin etkisini AYNI oturumda ölçmek mümkün değildir: aynı
transaction içindeki `revoke trend_service from neondb_owner` sonrasında bile
`pg_has_role(..., 'MEMBER')` `true` döner (backend membership cache'i).
Görünümün köprüye bağımlılığı bu yüzden **ölçülmedi, gerekçelendirildi**
(görünüm definer-haklarıyla koşar ve anon'un grant'ı olmadığı halde okur →
nitelendirme görünüm sahibinin policy'si üzerinden yapılır). Köprüyü
kaldıracaksanız görünüm için eşdeğer bir policy bırakın.

Uygulama ve doğrulama:

```bash
cd apps/trend-db
set -a && . ./.env && set +a
DATABASE_URL="$DATABASE_URL_UNPOOLED" npx prisma migrate status   # bekleyeni göster
DATABASE_URL="$DATABASE_URL_UNPOOLED" npx prisma migrate deploy   # uygula (pooled değil!)
# kanıt: migration dosyasının 8. bloğu
#   set role trend_anon; select * from public.trend_runs_daily;   -- ✅
#   set role trend_anon; select count(*) from public.trend_runs;  -- ❌ denied
```

## Sorgu indeksleri — `20260927194500_trend_runs_query_indexes`

Panonun **okuma desenlerine** göre planlandı (`docs/TREND_CHART_READ_PATH.md`);
partial (filtreli) ve covering (INCLUDE) indeksler Prisma şemasında **ifade
edilemez** (`@@index([ts], include: [...], where: "...")` → Prisma 7.10:
"No such argument", ölçüldü) — bu yüzden raw SQL migration'da yaşarlar,
şemadaki not bloğu adlarını aynalar.

| İndeks | Şekil | Desen |
|---|---|---|
| `trend_runs_ts_cover_idx` | `(ts) INCLUDE (verdict, p0, p1, duration_s, budget_usd, z3_total)` | `where ts >= $1 order by ts desc limit N` + dar `select` → index-only scan |
| `trend_runs_fail_ts_cover_idx` | `(ts DESC) INCLUDE (p0, p1, z3_total) WHERE verdict = 'FAIL'` | yalnız-FAIL ucu (`verdict = 'FAIL'` predicate'i birebir aynı olmalı) |
| `trend_runs_verdict_ts_idx` (init) | `(verdict, ts DESC)` | tüm verdict'ler için eşitlik→aralık |
| `trend_runs_ts_key` (init) | unique `(ts)` | "en yeni satır" (`order by ts desc limit 1`) |

- **Ölçüm (2026-09-27, canlı tablo, migration `BEGIN … ROLLBACK` ile
  uygulanmış — kalıcı iz yok):** 269 satır = 233 PASS + **36 FAIL (%13,4)**,
  `p0>0`: 0, `budget_usd` dolu: 233; heap 376 kB / toplam 512 kB. İndeks
  boyutları bu boyutta: `ts_cover_idx` 40 kB, `fail_ts_cover_idx` 16 kB
  (unique `ts_key` 16 kB). Planner'ın doğal kararı:
  - `yalnız-FAIL` → **`Index Only Scan using trend_runs_fail_ts_cover_idx`**,
    `actual rows=36`, `Heap Fetches: 36` — yani **partial indeks 269 satırda
    bile seçiliyor** (arşiv büyümesini beklemesi gerekmiyor).
  - seri/`select *` pencere → hâlâ `Index Scan Backward using trend_runs_ts_key`
    (62/12 buffer): covering indeks bu boyutta **seçilmiyor**, çünkü index-only
    scan eşikleri (all-visible sayfa oranı) arşivle birlikte gelir. 0,28 ms'lik
    seq scan ölçümü (`docs/TREND_CHART_READ_PATH.md` §4) kova/agrega desenine ait.
  - Migration **idempotent**: aynı dosya ikinci kez uygulandı, hata vermedi
    (`create index if not exists`); rollback sonrası indeks sayısı 4'e döndü.
- **Ölçek ölçümü (2026-09-27, TEMP tabloda 100k satır / 78 MB heap, ~1,4 kB
  satır, %12,5 FAIL — oturuma özel, kalıcı iz yok; plan node'u + `Buffers:` +
  koşu süresi, ısınma turu atılarak):**

  | Sorgu | S1: yalnız unique `ts` | S2: + bu iki indeks |
  |---|---|---|
  | seri (14g, 5000 satır, dar select) | Index Scan Backward `ts_key` — **528 buffer, 1,46–1,53 ms** | **Index Only Scan** `ts_cover_idx` — **46 buffer, 0,82 ms** |
  | yalnız-FAIL (limit 50) | Index Scan Backward `ts_key` — 45 buffer, 0,15–0,18 ms | **Index Only Scan** `fail_ts_cover_idx` — **4 buffer, 0,09–0,10 ms** |
  | en yeni satır (`select *`, limit 1) | `ts_key` | `ts_key` (değişmez — satırın tamamı istenir, 40 kolonu INCLUDE etmek anlamsız) |

  İndeks boyutları (aynı ölçekte, heap 78 MB): `ts_cover_idx` **6600 kB**
  (unique `ts_key` 3952 kB'ın ~1,7 katı), `fail_ts_cover_idx` **512 kB**
  (~7,7× `ts_key`'den, ~12,9× covering'den küçük), init'in
  `verdict_ts_idx` 3104 kB. Yani covering'in bedeli ilk anahtarın kopyası,
  kazancı pencere okumasında **~1,8× hız / ~11× az buffer**; partial'ın bedeli
  aynı ölçekte ~hiç.
- **Bulgu — mevcut `(verdict, ts DESC)` FAIL ucu için artık gerekli değil:**
  aynı ölçekte partial indeks kaldırılıp yerine `(verdict, ts DESC)` bırakılınca
  planner o composite'i **yine seçmedi**; covering indeksi seçti (8 buffer,
  0,18 ms) — eq→aralık taraması PASS satırlarını da geziyor, oysa covering
  planı yalnız indeksten okunuyor. Yani `verdict_ts_idx`'in FAIL desenine
  katkısı kalmıyor; **yine de duruyor**, çünkü PASS gibi öbür verdict
  filtrelerinde tek seçenek, 3,1 MB ve init migration'ın (şema `@@index`'inin)
  parçası — düşürmek ayrı bir şema+drift işi.
- **Ön koşul:** covering indeks ancak `select` daraldığında index-only scan'e
döner; bugünkü pencere sorgusu (`lib/trend-db.ts::getTrendFromDb`) tüm kolonları
çekiyor, planındaki dar `select` `docs/TREND_CHART_READ_PATH.md` §3'te planlı.
- **Reddedilenler** (gerekçe migration'ın sonunda yazılı): `p0 > 0` partial
  (bugün 0 satır, DB'de P0 ucu yok), `budget_usd` (eşik config'ten → partial
  predicate olamaz), agrega görünümü için ifade indeksi (50k tetiğine kadar seq scan).
- `CONCURRENTLY` bilinçli kullanılmadı: Prisma migration'ı transaction içinde
  koşar, CONCURRENTLY orada çalışmaz; bu boyutta kilit süresi ihmal edilebilir.
- Sözleşme testi: `_calisma/CIKTI/test_trend_db_index_contract.py` (statik —
  partial predicate, INCLUDE seti, `if not exists`, şema notu ile uyum).

## Notlar

- **Pooled/direct ayrımı (Neon sözleşmesi):** `DATABASE_URL` pooled'dır
  (PgBouncer, transaction-mode) — uygulama/loader trafiği buna gider.
  **Migration pooled üzerinden koşmaz** (`prepared statement "s0" already
  exists`, kayıp `SET` session-state, `SQLSTATE 25006` riski) — migration'da
  `DATABASE_URL`'i `DATABASE_URL_UNPOOLED` değeriyle override et (yukarıdaki
  2. komut). `neon env pull` her ikisini de .env'e yazar.
- `neon env pull` Free plan'da servis edilmeyen AI Gateway değişkenlerini de
  yazar (`NEON_AI_GATEWAY_*`); `.env.example` sözleşmesi yalnızca Postgres
  değişkenlerini kapsadığı için o iki satır `.env`'den temizlendi.
- Loader her satırın SHA-256'sını `source_row_sha256`'a basar → aynı kaynak
  tekrar yüklenirse upsert no-op (idempotent). `history.jsonl` canlı bir dosya
  (daemon son 100 koşumu tutar) — daemon koştukça load tekrar çağrılabilir,
  yalnız yeni `ts` eklenir. **Otomatik zamanlama yok:** arşivi güncel tutmak
  için `npm run load` elle/periyodik çağrılmalı (kaynak dosya daemon'ın
  mirrored `preview/` dizinidir).
- Şema Prisma 7 sözleşmesindedir: URL `prisma.config.ts`'te, generator
  `prisma-client` + explicit output (`generated/`).
- Alan-kapsamı: şema HISTORY_KEYS'in tamamını kollar (`refs_by_source` dahil,
  `Json` kolon); sürükleme = CI'da `test_trend_db_contract` kırılır.

## Tüketici: `apps/dashboard-next`

`apps/dashboard-next/lib/trend-db.ts` şemanın **üretilmiş** istemcisini
(`generated/client`) `@prisma/adapter-pg` ile kullanır. Böylece `trend_runs`'u
okuyan tek bir şema kaynağı kalır ve drift-guard'ın kapsadığı sözleşme tüketilir
— ayrı, elle yazılmış bir SQL katmanı eklenmedi.

- Kaynak seçimi `TREND_SOURCE` ile: `db` | `preview`. Verilmezse `DATABASE_URL`
  varsa `db`, yoksa `preview` (preview_server HTTP uçları) seçilir; DB parolası
  olmayan makinede pano çalışmaya devam eder.
- Kimlik bilgisi **tek yerde**: `next.config.js`, `process.loadEnvFile` ile
  `apps/trend-db/.env`'i okur (bu yüzden parola dashboard-next'e kopyalanmaz).
  Dışarıdan verilen `DATABASE_URL` ezilmez.
- İki uç arasında sözleşme ortaktır (`Latest` / `TrendRow`). **Sıra kuralı:**
  `/trend` gövdesi eskiden-yeniye döner; `app/trend/page.tsx` pencereyi
  `slice(-limit).reverse()` ile kendisi kısar. DB tarafı bu yüzden `desc + take`
  sonrası **reverse eder** — aksi halde sayfa en eski N'i "son N" diye gösterir.
- Her iki sayfa `dynamic = "force-dynamic"` taşır: DB kaynağında `fetch`in
  `no-store` sinyali olmadığı için Next sayfaları statik prerender edip verdict'i
  build anında dondururdu.

### Hızlı doğrulama

```bash
cd apps/dashboard-next
npm run lint                                        # tsc --noEmit
npx next build                                      # / ve /trend ƒ (Dynamic) olmalı
TREND_SOURCE=preview PREVIEW_API=http://127.0.0.1:8000 npx next start -p 3001
```
