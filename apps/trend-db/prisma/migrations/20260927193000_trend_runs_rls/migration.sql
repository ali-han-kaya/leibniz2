-- =============================================================================
-- trend_runs — RLS şablonu (skill: supabase-postgres-best-practices)
-- =============================================================================
-- Sözleşme: **service-role YAZAR, anonim YALNIZ aggregate OKUR.**
--   • yazma  → `trend_service` (uygulama/loader trafiğinin bağlandığı grup rol)
--   • anonim → temel tabloda HİÇ yetkisi yok; yalnız `trend_runs_daily`
--     aggregate görünümünü okur (satır düzeyi detay, hash, bulgu, JSON kolon YOK)
--
-- Skill referansı ve neden bu şekilde yazıldığı:
--   • security-rls-basics (CRITICAL) → `enable` + `force row level security`,
--     politika işlem-başına ve `to <rol>` ile AÇIKÇA kapsanır; uygulama
--     tarafında filtreye güvenilmez (kaçırılan bir sorgu tüm satırları sızdırır).
--   • security-privileges (MEDIUM) → en az yetki: `grant all` YOK, PUBLIC
--     varsayılanları geri alınır, uygulama superuser ile bağlanmaz.
--   • security-rls-performance (HIGH) → politika ifadelerinde satır-başına
--     fonksiyon çağrısı yok; politika kolonu yok (bu yüzden ek index
--     gerekmiyor, mevcut `@@index([verdict, ts(sort: Desc)])` yeter);
--     ileride satır-başına kontrol eklerseniz `(select ...)` sarmalayın.
--
-- Ölçülen ortam (2026-09-27, `neondb` / main branch):
--   PostgreSQL 18.6 · current_user=`neondb_owner` (CREATEROLE=true, SUPERUSER=false)
--   `trend_runs` 269 satır · RLS kapalı · policy 0 · sequence `trend_runs_id_seq`
--   PostgreSQL ≥ 15 olduğu için `security_invoker` görünümü desteklenir.
--
-- UYGULAMA (neon login + `neon env pull` sonrası; migration pooled üzerinden
-- KOŞMAZ — PgBouncer prepared-statement/session-state sorunları, README'deki
-- 2. adım):
--   cd apps/trend-db
--   set -a && . ./.env && set +a
--   DATABASE_URL="$DATABASE_URL_UNPOOLED" npx prisma migrate deploy
--
-- Bu dosya tek seferlik bir migration'dır; elle tekrar koşmak isterseniz DDL
-- idempotansı için `do $$`/`if not exists` guard'ları kullanıldı.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1) Roller — nologin GRUP rolleri (login rolü ayrı verilir, Neon konsolundan
--    veya `create role ... login password` ile; en az yetki ilkesi).
--    Guard'lı: aynı migration shadow/ikinci kez koşarsa hata vermez.
-- -----------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'trend_service') then
    execute 'create role trend_service nologin noinherit';
  end if;
  if not exists (select 1 from pg_roles where rolname = 'trend_anon') then
    execute 'create role trend_anon nologin noinherit';
  end if;
end
$$;

-- -----------------------------------------------------------------------------
-- 2) Yetkiler (en az yetki) — PUBLIC varsayılanları geri alınır.
--    NOT: `revoke all on schema public from public` veritabanı genelinde
--    PUBLIC'in şema USAGE/CREATE'ini kaldırır (sertleştirme). Bu veritabanında
--    `public` şemasına başka bir rolün PUBLIC üzerinden erişmesi gerekmiyorsa
--    kalabilir; gerekiyorsa bu satırı çıkarın ve ilgili role açıkça
--    `grant usage on schema public` verin.
-- -----------------------------------------------------------------------------
revoke all on schema public from public;
revoke all on public.trend_runs from public;
revoke all on all sequences in schema public from public;

grant usage on schema public to trend_service, trend_anon;

-- Yazar: tablo CRUD + id üretimi için sequence (DELETE dahil: arşiv bakımı).
grant select, insert, update, delete on public.trend_runs to trend_service;
grant usage, select on sequence public.trend_runs_id_seq to trend_service;

-- Anonim: temel tabloda TEMEL YETKİ YOK (aşağıdaki 6. adımda yalnız görünüm).
-- Yetki verilmemiş + POLICY'siz tablo, RLS'te "deny" demektir — iki kat savunma:
-- yanlışlıkla anon'a grant eklenirse bile policy olmadığı için satır dönmez.

-- -----------------------------------------------------------------------------
-- 3) RLS — enable + FORCE (tablo sahibi de policy'ye tabidir; security-rls-basics).
-- -----------------------------------------------------------------------------
alter table public.trend_runs enable row level security;
alter table public.trend_runs force row level security;

-- -----------------------------------------------------------------------------
-- 4) Politikalar — işlem-başına, `to <rol>` ile açık kapsam.
--    `for all` yalnız yazarda: USING + WITH CHECK birlikte (yazma sınırı).
-- -----------------------------------------------------------------------------
drop policy if exists trend_runs_service_all on public.trend_runs;
create policy trend_runs_service_all on public.trend_runs
  for all
  to trend_service
  using (true)
  with check (true);

-- Anon için temel tabloda policy YOK — bilinçli: anonim yalnız aggregate okur.
-- (İleride satır düzeyi anon okuma istenirse 7. bloktaki alternatife bakın.)

-- -----------------------------------------------------------------------------
-- 5) Köprü (geçici) — mevcut yükleme hattı hâlâ `neondb_owner` ile bağlanıyor
--    (apps/trend-db/.env → DATABASE_URL). FORCE RLS owner'ı da kapsadığı için
--    bu köprü olmadan `npm run load` "permission denied" ile düşer.
--    Kalıcı çözüm: loader için ayrı bir Neon login rolü açıp `trend_service`
--    üyeliği vermek, sonra bu köprüyü kaldırmak:
--       create role trend_loader login password '…';
--       grant trend_service to trend_loader;        -- Neon'da login rolleri
--       revoke trend_service from neondb_owner;     -- köprüyü düşür
-- -----------------------------------------------------------------------------
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'neondb_owner') then
    execute 'grant trend_service to neondb_owner';
  else
    raise notice 'neondb_owner yok: loader rolünü elle `grant trend_service to <rol>` ile bağlayın';
  end if;
end
$$;

-- -----------------------------------------------------------------------------
-- 6) Anonim aggregate yüzeyi — satır düzeyi detay SIZMAZ, JSON/hash/bulgu YOK.
--    Görünüm varsayılan olarak (security_invoker = false) SAHİBİNİN yetkisiyle
--    koşar; sahibi `trend_service` yazma politikasına sahip olduğu için RLS'ten
--    geçer. Bu bilinçli ve dar bir "bypass"tır (skill'in SECURITY DEFINER
--    uyarısı): görünüm YALNIZ aggregate kolonları seçer, taban tabloya anon
--    erişimi yoktur ve görünüm sahibi olan rol güvenilen (owner) roldür.
--    → Köprü (5. adım) kaldırılacaksa önce görünüm sahibinin policy'sinin
--      politikası olduğundan emin olun, aksi halde görünüm de düşer.
-- -----------------------------------------------------------------------------
create or replace view public.trend_runs_daily as
  select
    (date_trunc('day', ts))::date          as day,
    verdict,
    count(*)::int                          as runs,
    sum(p0)::int                           as p0_total,
    sum(p1)::int                           as p1_total,
    round(avg(duration_s)::numeric, 2)     as avg_duration_s,
    round(avg(budget_usd)::numeric, 2)     as avg_budget_usd,
    sum(z3_passed)::int                    as z3_passed_total,
    sum(z3_failed)::int                    as z3_failed_total
  from public.trend_runs
  group by 1, 2;

revoke all on public.trend_runs_daily from public;
grant select on public.trend_runs_daily to trend_anon;

-- -----------------------------------------------------------------------------
-- 7) ALTERNATİF (bilinçli olarak yorumda): anon'a dar kolon-kapsamlı satır
--    okuma. Aggregate-only kısıtını gevşetir; görünüm "bypass"ı olmadan,
--    tamamen RLS güdümlü kalır. Satır düzeyi anon okuma GEREKİRSE:
--
--    alter view public.trend_runs_daily set (security_invoker = true);
--    grant select (ts, verdict, p0, p1, duration_s, budget_usd,
--                  z3_passed, z3_failed, z3_total, exit_code)
--      on public.trend_runs to trend_anon;
--    drop policy if exists trend_runs_anon_select on public.trend_runs;
--    create policy trend_runs_anon_select on public.trend_runs
--      for select to trend_anon using (true);
--
--    (findings / cli_overrides / hook_env / *sha256 / lineage_* / status_board
--     gibi kolonlar bu listede YOKTUR ve OLMAMALIDIR.)
-- -----------------------------------------------------------------------------

-- -----------------------------------------------------------------------------
-- 8) DOĞRULAMA (uygulandıktan sonra; `neondb_owner` üye olduğu için SET ROLE
--    ile test edilebilir):
--    set role trend_anon;
--      select * from public.trend_runs_daily limit 5;   -- ✅ aggregate okuma
--      select count(*) from public.trend_runs;          -- ❌ permission denied
--      insert into public.trend_runs default values;    -- ❌ permission denied
--    reset role;
--    set role trend_service;
--      select count(*) from public.trend_runs;          -- ✅
--    reset role;
--    -- Politikaların kaydı:
--    select polname, polcmd, polroles::regrole[] from pg_policy
--      where polrelid = 'public.trend_runs'::regclass;
-- -----------------------------------------------------------------------------

-- -----------------------------------------------------------------------------
-- 9) GERİ ALMA (acil durum; ayrı bir migration olarak):
--    drop view if exists public.trend_runs_daily;
--    drop policy if exists trend_runs_service_all on public.trend_runs;
--    alter table public.trend_runs no force row level security;
--    alter table public.trend_runs disable row level security;
--    revoke trend_service from neondb_owner;
--    -- Roller başka nesnelerce kullanılmıyorsa: drop role trend_anon; trend_service;
-- -----------------------------------------------------------------------------
