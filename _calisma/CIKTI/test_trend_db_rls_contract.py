"""trend_runs RLS şablonu sözleşme testleri (statik — DB/ağ gerekmez).

Kapı: `apps/trend-db/prisma/migrations/*_trend_runs_rls/migration.sql`
içindeki şablonun skill sözleşmesini (supabase-postgres-best-practices)
koruduğunu kanıtlar:

  • security-rls-basics (CRITICAL): RLS enable + **force**, politikalar
    işlem-başına ve `to <rol>` ile açık kapsamlı (`USING`/`WITH CHECK`).
  • security-privileges (MEDIUM): `grant all` yok, PUBLIC varsayılanları
    geri alınmış, anon temel tabloda yetkisiz (en az yetki).
  • Sözleşme: service-role YAZAR, anonim YALNIZ aggregate OKUR — anon
    yalnız `trend_runs_daily` görünümünü görebilir ve o görünüm hassas
    kolonları (hash/JSON/bulgu) SEÇEMEZ.

Yorumlar ayıklanarak denetlenir: dosyadaki "ALTERNATİF" bloğu bilinçli
olarak yorumdadır ve uygulanan SQL sayılmaz.
"""
import pathlib
import re
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1] if HERE.name == "CIKTI" else HERE.parents[2]
TREND_DB = REPO_ROOT / "apps" / "trend-db"
MIGRATIONS = TREND_DB / "prisma" / "migrations"
INIT_MIGRATION = "20260925171004_init"

WRITER = "trend_service"
ANON = "trend_anon"

# Anon'a ASLA açılmayacak kolonlar (hash'ler, ham JSON'lar, bulgu detayları).
SENSITIVE = (
    "findings",
    "cli_overrides",
    "hook_env",
    "precommit_hooks",
    "status_board",
    "pattern_drift",
    "pattern_drift_detail",
    "lean_detail",
    "lean_source",
    "lineage_summary",
    "refs_by_source",
    "audit_refs_trend",
    "raw_sha256",
    "stripped_sha256",
    "history_sidecar_sha256",
    "source_row_sha256",
)


def rls_migration():
    """trend_runs RLS migration dosyasını (tek) bulur."""
    hits = sorted(MIGRATIONS.glob("*_trend_runs_rls/migration.sql"))
    if len(hits) != 1:
        raise AssertionError(
            "tam olarak 1 RLS migration'ı beklenirdi, bulunan: %s" % hits)
    return hits[0]


def strip_comments(sql):
    """`--` satır yorumlarını ve `/* */` bloklarını ayıklar (statik denetim)."""
    without_block = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    lines = []
    for line in without_block.splitlines():
        code = line.split("--", 1)[0]
        if code.strip():
            lines.append(code)
    return "\n".join(lines)


class TestTrendDbRlsTemplate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = rls_migration()
        cls.raw = cls.path.read_text(encoding="utf-8")
        cls.sql = strip_comments(cls.raw)
        cls.lower = cls.sql.lower()

    def test_migration_directory_is_timestamped_and_newer_than_init(self):
        name = self.path.parent.name
        self.assertRegex(name, r"^\d{14}_[a-z0-9_]+$",
                         "Prisma migration dizini <timestamp>_<ad> olmalı")
        self.assertGreater(name, INIT_MIGRATION,
                           "RLS migration'ı init'ten sonra sıralanmalı")
        lock = MIGRATIONS / "migration_lock.toml"
        self.assertIn("postgresql", lock.read_text(encoding="utf-8"))

    def test_rls_enabled_and_forced_on_trend_runs(self):
        self.assertIn("alter table public.trend_runs enable row level security",
                      self.lower)
        self.assertIn("alter table public.trend_runs force row level security",
                      self.lower,
                      "force yoksa tablo sahibi RLS'i atlar (skill: CRITICAL)")

    def test_no_disable_or_bypass_shortcuts(self):
        for forbidden in ("disable row level security", "bypassrls",
                          "no force row level security"):
            self.assertNotIn(forbidden, self.lower,
                             "RLS'i kapatan kısayol yasak: %s" % forbidden)

    def test_roles_are_created_idempotently_and_actually_used(self):
        created = set(re.findall(r"create role (\w+)", self.lower))
        self.assertEqual(created, {WRITER, ANON})
        self.assertIn("from pg_roles where rolname", self.lower,
                      "roller guard'sız yaratılırsa ikinci/eşgörüntü koşusu kırılır")
        self.assertIn("nologin", self.lower,
                      "grup rolleri login OLMAMALI (en az yetki)")
        # Her iki rol de en az bir yetki/politikada geçmeli.
        self.assertRegex(self.lower, r"to %s" % WRITER)
        self.assertRegex(self.lower, r"to %s" % ANON)

    def test_writer_policy_is_scoped_and_has_check(self):
        policy = re.search(
            r"create policy (\w+) on public\.trend_runs\s+for all\s+to %s\s+"
            r"using \(true\)\s+with check \(true\)" % WRITER, self.lower)
        self.assertIsNotNone(
            policy, "yazar politikası `for all to trend_service using/with check` olmalı")
        # Politika hedefi açık rol olmalı — PUBLIC'e yazma politikası yok.
        self.assertNotRegex(self.lower, r"create policy[^;]*\bto public\b")

    def test_anon_has_no_privilege_on_the_base_table(self):
        grants_to_anon = re.findall(
            r"grant ([^;]+?) on ([^;]+?) to %s" % ANON, self.lower)
        self.assertTrue(grants_to_anon, "anon en azından aggregate yüzeyini okumalı")
        for _, target in grants_to_anon:
            self.assertNotIn("trend_runs ", target.replace("public.", "") + " ",
                             "anon temel tabloya yetkili OLMAMALI: %s" % target)
        self.assertNotRegex(
            self.lower, r"create policy[^;]*on public\.trend_runs[^;]*to %s" % ANON,
            "anon için temel tablo politikası yok (policy'siz = deny)")

    def test_anon_reads_only_the_aggregate_view(self):
        self.assertIn("create or replace view public.trend_runs_daily", self.lower)
        self.assertIn("grant select on public.trend_runs_daily to %s" % ANON,
                      self.lower)
        self.assertIn("revoke all on public.trend_runs_daily from public",
                      self.lower)
        # Görünüm gövdesi yalnız aggregate seçmeli (group by zorunlu).
        view = re.search(r"create or replace view[^;]+?;", self.lower, re.S)
        self.assertIsNotNone(view)
        body = view.group(0)
        self.assertIn("group by", body, "anon yüzeyi satır düzeyi liste OLMAMALI")

    def test_aggregate_view_never_selects_sensitive_columns(self):
        view = re.search(r"create or replace view[^;]+?;", self.lower, re.S)
        body = view.group(0)
        for column in SENSITIVE:
            self.assertNotIn(column, body,
                             "hassas kolon anon görünümünde: %s" % column)

    def test_no_grant_all_and_public_defaults_revoked(self):
        self.assertNotIn("grant all", self.lower,
                         "`grant all` en az yetki ilkesini ihlal eder")
        self.assertNotRegex(self.lower, r"grant [^;]*\bto public\b",
                            "PUBLIC'e grant yasak")
        self.assertIn("revoke all on public.trend_runs from public", self.lower)
        self.assertIn("revoke all on schema public from public", self.lower)
        self.assertIn("grant usage on schema public to %s, %s" % (WRITER, ANON),
                      self.lower)

    def test_sequence_granted_to_writer_only(self):
        self.assertIn(
            "grant usage, select on sequence public.trend_runs_id_seq to %s"
            % WRITER, self.lower)
        self.assertNotRegex(self.lower, r"sequence[^;]*to %s" % ANON)

    def test_header_documents_skill_rules_and_unpooled_apply_path(self):
        header = self.raw
        for token in ("security-rls-basics", "security-privileges",
                      "security-rls-performance"):
            self.assertIn(token, header, "skill kuralı referansı eksik: %s" % token)
        self.assertIn("DATABASE_URL_UNPOOLED", header,
                      "migration'ın pooled üzerinden koşmaması belgelenmeli")
        self.assertIn("migrate deploy", header)
        self.assertIn("service-role YAZAR", header)
        self.assertIn(ANON, header)

    def test_owner_bridge_is_documented_and_guarded(self):
        # FORCE RLS yükleyiciyi de kapsar: köprü guard'lı ve geri alınması yazılı.
        # Köprü GERÇEK SQL olmalı (guard + notice), kaldırma yolu ise belge
        # olduğu için yorumlarda aranır.
        self.assertIn("neondb_owner", self.lower)
        self.assertIn("execute 'grant %s to neondb_owner'" % WRITER, self.lower,
                      "köprü guard'lı bir execute ile kurulmalı")
        self.assertIn("raise notice", self.lower)
        self.assertIn("revoke %s from neondb_owner" % WRITER, self.raw,
                      "köprünün kaldırılma yolu belgelenmeli")


if __name__ == "__main__":
    unittest.main()
