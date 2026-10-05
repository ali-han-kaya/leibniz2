# trend-db — doğrulama-zinciri trend geçmişinin Postgres katmanı

`history.jsonl` (verify koşumları, 40+ alan) → Neon Postgres `TrendRun` tablosu.
Skill: `prisma-database-setup` (Prisma 7 + `@prisma/adapter-pg`) + `neon-postgres`
bağlantı sözleşmesi (pooled/direct ayrımı).

## Durum (2026-10-03 ölçümüyle güncellendi)

- ✅ Şema (`prisma/schema.prisma` — HISTORY_KEYS'in 42 alanının tam modeli), config, loader, testler
- ✅ Drift-guard: `test_trend_db_contract.py` HISTORY_KEYS ↔ şema ↔ loader sürüklenmesini yakalar
- ✅ Canlı proje **var**: `leibniz2-trend` (`orange-bar-58985004`, `aws-eu-central-1`,
  PostgreSQL 18.6, branch `main` = `br-morning-queen-b1zibof0`), 2026-09-25'te açılmış
- ✅ Canlı şema **uygulanmış**: `trend_runs` (42 kolon, **269 satır**) + `trend_runs_daily`
  (9 kolon, 3 satır) + `_prisma_migrations` (**3 kayıt**)
- 🔴 **MIGRATION GEÇMİŞİ REPO'DA KAYIP** — aşağıdaki "TEHLİKE" bölümü

## 🔴 TEHLİKE: `prisma migrate dev` ŞEMAYI SİLER (2026-10-03'te ÖLÇÜLDÜ)

Canlı DB'de **3 migration uygulanmış**, ama `prisma/migrations/` dizini repo'da
**YOK** — geçmiş yalnız canlı veritabanında duruyor:

| #   | migration                                 | uygulanma            |
| --- | ----------------------------------------- | -------------------- |
| 1   | `20260925171004_init`                     | 2026-09-25 17:10:04Z |
| 2   | `20260927193000_trend_runs_rls`           | 2026-09-28 00:42:50Z |
| 3   | `20260927194500_trend_runs_query_indexes` | 2026-09-28 00:42:50Z |

Bu yüzden `npx prisma migrate dev --name init` **VERİYİ SİLER**. Ölçüm (canlıya
değil, atılmış bir branch'e — Neon branch'leri copy-on-write, `main` hiç etkilenmedi):

```
- Drift detected: Your database schema is not in sync with your migration history.
- The following migration(s) are applied to the database but missing from the
  local migrations directory: 20260925171004_init, 20260927193000_trend_runs_rls,
  20260927194500_trend_runs_query_indexes
We need to reset the "public" schema ... All data will be lost.
```

Sıfırlama **269 satırı**, `trend_runs_daily` tablosunu, RLS politikasını ve
`trend_service`/`trend_anon` GRANT'lerini de düşürür.

> ⚠️ `prisma migrate status` bunu **gizler**: "No migration found in
> prisma/migrations" + "Database schema is up to date!" der. Repo'da migration
> olmadığı için karşılaştıracak bir şey bulamaz — **yeşil gördürmek yanlış onay**.
> Sürükleme ancak `migrate dev` çalıştırılınca ortaya çıkar.

**Güvenli yol (henüz UYGULANMADI — karar bekliyor):** migration geçmişini canlı
şemadan geri üretip `prisma migrate resolve` ile kaydetmek. Bu, tarihçenin nasıl
temsil edileceğine dair bir karardır (üç kaydı tek bir baseline migration'a
toplama vs. üçünü ayrı ayrı geri üretme). Kurtarma **öncesi** migration geçmişi
repo'ya alınmadan hiçbir migration komutu çalıştırma.

### Canlıda repo'da olmayan ek yapı (2026-10-03 ölçümü)

| Nesne              | Detay                                                                                                                                                           |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `trend_runs_daily` | 9 kolon (`day, verdict, runs, p0_total, p1_total, avg_duration_s, avg_budget_usd, z3_passed_total, z3_failed_total`) — **şemada hiç yok**, dashboard okuma yüzü |
| RLS                | `trend_runs` üzerinde `ENABLE` + `FORCE ROW LEVEL SECURITY`                                                                                                     |
| Politika           | `trend_runs_service_all` — rol `{trend_service}`, `USING true`, `WITH CHECK true`                                                                               |
| İndeksler          | `(ts, p0, p1, z3_total)`, `(ts, verdict, p0, p1, duration_s, budget_usd, z3_total)`, `(verdict, ts)` + 2 unique                                                 |

`trend_runs`'ın 42 kolonu `prisma/schema.prisma` ile **birebir** uyuşuyor; sürüklenme
migration geçmişinde, kolonlarda değil.

#### `trend_runs_daily` NEDEN `schema.prisma`'da değil (ölçüldü)

Tablo **primary key içermiyor** — 9 kolonun tamamı nullable, hiçbir constraint ve
indeks yok. Prisma her modelin en az bir required benzersiz alan istediği için
tabloyu temsil EDEMİYOR (ölçülen hata: `P1012 — Each model must have at least one
unique criteria that has only required fields`). Aynı sebeple Prisma'nın
`migrate diff` çıktısına da girmiyor. Yani bu tablo **bilinçli olarak Prisma
dışında, elle yönetilen** bir nesnedir; `schema.prisma`'ya model olarak eklenemez.

Sonuç: RLS, GRANT'ler ve `trend_runs_daily` canlıda yaşar ama Prisma onları
göremez. Gerçek şemanın tek güvenilir kopyası **`prisma/live-backup-2026-10-03.sql`**
dosyasıdır (aşağıda).

### Yedek: `prisma/live-backup-2026-10-03.sql` (2026-10-03)

Kayıp migration geçmişi onarılmadan önce alınmış **geri dönüş noktası**. İçerir:
`trend_runs` (42 kolon + 6 indeks), `trend_runs_daily` (elle, bkz. yukarıdaki
gerekçe), RLS + politika, GRANT'ler ve **checksum'leriyle 3 migration kaydı**.

Gerçekten geri yüklendiği **ölçüldü**: atılabilir bir branch'in `public` şeması
silindi, dosya uygulandı, sonuç `main` ile karşılaştırıldı — 3 tablo, 42/9 kolon,
6 indeks, RLS açık, 1 politika, 3 migration kaydı, 5 GRANT: **birebir aynı**.
(İlk deneme `_prisma_migrations` tablosu olmadığı için 42P01 ile düştü; Prisma bu
defter tablosunu introspeksiyondan daşıyor — düzeltildi.) Branch silindi, `main`
dokunulmadan kaldı (269/3/3/1/5).

> **Beklenen ayrık — dizi (sequence) yetkisi.** Ölçülen geri yüklemede GRANT
> kümesi birebir aynıydı; sonraki adımda `trend_service` ile gerçek bir INSERT
> denemesi `permission denied for sequence trend_runs_id_seq` ile düştü
> (`"id" SERIAL` olduğu için INSERT dizinin `nextval()` iznini gerektirir;
> tablo INSERT'i tek başına yetmez). Yedeğe bu yüzden **tek bir GRANT
> ifadesi** daha eklendi:
> `GRANT USAGE ON SEQUENCE "public"."trend_runs_id_seq" TO trend_service`
> — **kasıtlı olarak canlıdan ayrılan tek satır**. Canlıdaki GRANT
> kümesi kopyalandığında dokümante edilen servis yazma yolu fiilen
> çalışmıyordu. Bu, yedeğin düzeltilmiş yazma yolunu verir; **canlıya
> dokunmaz** — canlıda aynı GRANT hâlâ eksik ve eklenmesi ayrı bir iştir.
> (Yukarıdaki "5 GRANT" sayısı canlıyla karşılaştırmadan gelen ölçümdür;
> dosyadaki GRANT *ifadesi* sayısı bir az daha fazladır.)

> Yedek **veri içermez** (269 + 3 satır yok) ve **rol parolalarını içermez**;
> amaç yapı + migration geçmişi kurtarmasıdır.

### Düzeltme: kapılar "credentialsuz" değil, "secret'sız" (2026-10-03)

Eski durum satırı `prisma validate` + `prisma generate`'ı _credentialsuz_ kapı olarak
listeliyordu. Bu **yanlıştı**: `prisma.config.ts` URL'yi `env('DATABASE_URL')` ile
config modülü yüklenirken çözdüğü için, `DATABASE_URL` tanımlı değilken ikisi de

```
PrismaConfigEnvError: Cannot resolve environment variable: DATABASE_URL.
```

ile düşüyor. **Bağlantı gerekmez** — herhangi bir sözdizimsel olarak geçerli bir URL
(ölçümde dummy değer kullanıldı) ikisini de geçirir (`schema is valid` / client üretildi).
Yani doğru ifade: _gerçek kimlik bilgisi gerektirmez, ama `DATABASE_URL` ortam
değişkeninin tanımlı olmasını gerektirir._ CI'da secret'sız koşacaksa bu ayrım önemli.

## Yapılacak adımlar

> 🔴 Aşağıdaki eski 3 adım (`prisma migrate dev --name init`) **veri siler**;
> yukarıdaki TEHLİKE bölümüne bak. Migration geçmişi kurtarılmadan
> `migrate dev` / `migrate reset` **çalıştırma**.

```bash
cd apps/trend-db
neon env pull     # DATABASE_URL (pooled) + DATABASE_URL_UNPOOLED üretir → .env'e
```

`neon env pull` çalışmak için hesap gerektirir; ölçümde hesap **zaten** vardı
(`neon profile list` → `DEFAULT`, `account` UUID dolu, `file: ok`), yani `neon login`
adımı gerekmiyor — yalnızca bu dizinde bağlam (`neon link`) eksik.

Migration geçmişi kurtarıldıktan sonra veri yükleme:

```bash
npm run load      # TCC-mirror history.jsonl → TrendRun (idempotent upsert, pooled)
```

### Canlı rolleri ve yetkileri (2026-10-03 ölçümü — canlı GRANT'ler okundu)

| Rol             | `rolcanlogin`          | Yetki                                                                           |
| --------------- | ---------------------- | ------------------------------------------------------------------------------- |
| `neondb_owner`  | true (+`BYPASSRLS`)    | sahip; migration + DDL                                                          |
| `trend_service` | **false**              | `trend_runs`: SELECT/INSERT/UPDATE/DELETE + RLS policy `trend_runs_service_all` |
| `trend_anon`    | **false** (`no_login`) | `trend_runs_daily`: **SELECT-only**                                             |

Bu, tutarlı bir least-privilege ayrımı: yazma rolü ham veride tam DML, okuma
rolü yalnız günlük özet tablosunda SELECT. İkisi de şu an `rolcanlogin=false`
ve Neon tarafında parolasız — **bağlanılabilir değiller**; kullanılacaksa önce
`neon roles update <ad> --role-name ...` ile parola atanmalı.

**Bu tabloyu canlıya uygulamadan önce iki ek GRANT gerekir** (yalnız
`trend_service` için):

```sql
GRANT USAGE ON SEQUENCE public.trend_runs_id_seq TO trend_service;
```

1. **Dizi USAGE'ı** — `"id" SERIAL` olduğu için tablo INSERT'i tek başına
   yetmez. Bu GRANT canlıda **yok**; olmadan INSERT yetki hatası verir
   (yedeğe eklenmiştir, bkz. yukarıdaki ayrık notu).
2. Parola (`rolcanlogin=false` olduğu için zaten ayrı bir iş).

RLS tarafında `trend_service` politika `USING true` olduğu için fiilen geçer
(kısıtlama GRANT katmanında, politika katmanında değil) — bu, INSERT'in
tek engelinin dizi yetkisi olduğu anlamına gelir.

## Notlar

- **Pooled/direct ayrımı (Neon sözleşmesi) — Prisma 7'de `directUrl` YOK.**
  `DATABASE_URL` pooled'dır (PgBouncer, transaction-mode) — uygulama/loader
  trafiği buna gider. **Migration havuzda koşmaz** (`prepared statement "s0"
already exists`, kaybolan `SET` session-state, `SQLSTATE 25006`; hiçbiri
  nedeni söylemez). Neon skill'in Prisma 5/6 için verdiği öneri — "URL'yi
  `directUrl` ile ayrı ver" — **bu projede imkânsız**, ölçüldü (prisma 7.10.0):

  ```
  error: The datasource property `directUrl` is no longer supported in schema
  files. Move connection URLs to `prisma.config.ts`.   [P1012]
  ```

  `@prisma/config` 7.10.0 `Datasource` tipi de yalnız `{ url, shadowDatabaseUrl }`
  taşıyor. **Gerçek çözüm: ayrım iki farklı yerde, iki farklı URL ile kurulur.**

  | Yer                | Okuyan                                         | URL                              | Neden                              |
  | ------------------ | ---------------------------------------------- | -------------------------------- | ---------------------------------- |
  | `prisma.config.ts` | **yalnız Prisma CLI** (migrate/db pull/studio) | `DATABASE_URL_UNPOOLED` (direct) | havuzda migration bozulur          |
  | `scripts/load.ts`  | **çalışma zamanı** (adapter'ı kendi kurar)     | `DATABASE_URL` (pooled)          | uygulama trafiği her zaman havuzda |

  Config sırası `unpooled ?? pooled`; ikisi de varsa direct kazanır, havuz
  migration boyunca "geçici olarak değiştirilmez" — hiç devreye girmez.
  Yalnız havuz varsa config **uyarır** (sessiz düşüş, kırılmayı beklemez):
  `[neon] DATABASE_URL_UNPOOLED yok — ...`. Hiçbiri yoksa `neon env pull` yönlendirmeli hata verir.

  Ölçüldü: `DATABASE_URL` geçerli bir havuz, `DATABASE_URL_UNPOOLED` ise
  kasıtlı olarak bilinmeyen bir host iken Prisma CLI **direct** host'a gitti
  (`Can't reach ... ep-also-invalid-direct.invalid`) — yani config gerçekten
  seçimini uyguluyor; negatif kontrol (yalnız havuz) havuz host'una gitti.
  Kapı: `_calisma/CIKTI/test_trend_db_connection.py` (9 test) bu sözleşmeyi
  statik olarak kilitler.

- Loader her satırın SHA-256'sını `source_row_sha256`'a basar → aynı kaynak
  tekrar yüklenirse upsert no-op (idempotent).
- Şema Prisma 7 sözleşmesindedir: URL `prisma.config.ts`'te, generator
  `prisma-client` + explicit output (`generated/`).
- Alan-kapsamı: şema HISTORY_KEYS'in tamamını kollar (`refs_by_source` dahil,
  `Json` kolon); sürükleme = CI'da `test_trend_db_contract` kırılır.
- **DOĞRULANDI (2026-10-03):** Canlı SQL artık okunabiliyor (doğrudan `pg`
  bağlantısı; `neon psql` bu ortamda çalışmıyor). `trend_runs` **var** (42 kolon,
  269 satır), `trend_runs_daily` var (3 satır) ve **3 migration uygulanmış**.
  Önceki "DOĞRULANMADI" notu geçersizdir. Canlıya bağlanmak için:
  `neon connection-string --branch main --pooled false` — migration/DDL için
  **direct** (hostname'de `-pooler` YOK; Neon skill bağlantı sözleşmesi).
