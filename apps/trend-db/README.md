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

## Kurulum (tamamlanmış hali)

```bash
cd apps/trend-db
neon env pull --project-id orange-bar-58985004 -e DATABASE_URL -e DATABASE_URL_UNPOOLED -e NEON_BRANCH
DATABASE_URL="$DATABASE_URL_UNPOOLED" npx prisma migrate dev --name init
npm run load                     # TCC-mirror history.jsonl → TrendRun (idempotent, pooled)
```

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
