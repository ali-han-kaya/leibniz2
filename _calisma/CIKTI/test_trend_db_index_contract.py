"""trend_runs sorgu-deseni indeksleri sözleşme testleri (statik — DB/ağ yok).

Kapı: `apps/trend-db/prisma/migrations/*_trend_runs_query_indexes/migration.sql`
içindeki partial/covering indekslerin, panonun okuma desenleriyle ve şema
notuyla ayrışmadığını kanıtlar.

  • query-partial-indexes (HIGH): kısmi indeks predicate'i sorgudaki
    değişmezle BİREBİR aynı olmalı (`verdict = 'FAIL'`), yoksa planner
    indeksi kullanamaz.
  • query-covering-indexes (MEDIUM-HIGH): INCLUDE seti dar `select`'lerin
    kolonlarını kapsar — kolon eklemek/eksiltmek index-only scan'i bozar.
  • Prisma 7.10 partial/covering ifade EDEMEZ (ölçüldü: `include:`/`where:`
    → "No such argument"); bu yüzden indeksler raw SQL'de yaşar ve şemadaki
    not bloğu adlarını aynalar — bu test iki tarafı birbirine bağlar.
"""
import pathlib
import re
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1] if HERE.name == "CIKTI" else HERE.parents[2]
TREND_DB = REPO_ROOT / "apps" / "trend-db"
MIGRATIONS = TREND_DB / "prisma" / "migrations"

COVER = "trend_runs_ts_cover_idx"
FAIL_PARTIAL = "trend_runs_fail_ts_cover_idx"

# Panonun dar select'lerinin BİRLEŞİMİ (docs/TREND_CHART_READ_PATH.md §3):
# bugünkü pencere sorgusu {ts, p0, p1, duration_s, budget_usd, z3_total} +
# planlanan seri sorgusu {ts, verdict, p0, p1, z3_total}.
EXPECTED_INCLUDE = ("verdict", "p0", "p1", "duration_s", "budget_usd", "z3_total")
FAIL_INCLUDE = ("p0", "p1", "z3_total")
# Predicate'in birebir eşleşmesi için sorgudaki hâliyle AYNI olmalı.
FAIL_PREDICATE = "verdict = 'FAIL'"


def index_migration():
    hits = sorted(MIGRATIONS.glob("*_trend_runs_query_indexes/migration.sql"))
    if len(hits) != 1:
        raise AssertionError(
            "tam olarak 1 indeks migration'ı beklenirdi, bulunan: %s" % hits)
    return hits[0]


def strip_comments(sql):
    """`--` satır yorumlarını ve `/* */` bloklarını ayıklar."""
    without_block = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    return "\n".join(
        code for code in (line.split("--", 1)[0] for line in without_block.splitlines())
        if code.strip())


class TestTrendDbIndexPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = index_migration()
        cls.raw = cls.path.read_text(encoding="utf-8")
        cls.sql = strip_comments(cls.raw)
        cls.lower = cls.sql.lower()
        cls.schema = (TREND_DB / "prisma" / "schema.prisma").read_text(
            encoding="utf-8")
        cls.readme = (TREND_DB / "README.md").read_text(encoding="utf-8")

    def test_migration_is_timestamped_and_after_init(self):
        name = self.path.parent.name
        self.assertRegex(name, r"^\d{14}_[a-z0-9_]+$")
        self.assertGreater(name, "20260925171004_init")

    def test_indexes_are_created_idempotently(self):
        created = re.findall(r"create index if not exists (\w+)", self.lower)
        self.assertEqual(sorted(created), sorted([COVER, FAIL_PARTIAL]),
                         "indeksler `if not exists` ile idempotent olmalı")
        self.assertNotIn("create unique index", self.lower,
                         "bu migration tekil kısıt eklemez (init'te var)")

    def test_covering_index_matches_documented_select_columns(self):
        m = re.search(
            r"create index if not exists %s\s+on public\.trend_runs \(([^)]*)\)\s+"
            r"include \(([^)]*)\)" % COVER, self.lower)
        self.assertIsNotNone(m, "covering indeks beklenen şekilde değil")
        keys = [k.strip() for k in m.group(1).split(",")]
        include = [c.strip() for c in m.group(2).split(",")]
        self.assertEqual(keys, ["ts"], "sıralama anahtarı tek kolon: ts")
        self.assertEqual(sorted(include), sorted(EXPECTED_INCLUDE),
                         "INCLUDE seti pano dar select'lerinin birleşimi olmalı")

    def test_partial_index_predicate_matches_query_literal(self):
        # DİKKAT: predicate metin-karşılaştırmalı bir SQL değişmezidir
        # ('FAIL' ≠ 'fail') — bu yüzden lower()'lanmış metinde DEĞİL,
        # yorumları ayıklanmış orijinal SQL'de aranır.
        m = re.search(
            r"create index if not exists %s\s+on public\.trend_runs \(([^)]*)\)\s+"
            r"include \(([^)]*)\)\s+where ([^;]+);" % FAIL_PARTIAL,
            self.sql, re.I)
        self.assertIsNotNone(m, "partial indeks beklenen şekilde değil")
        self.assertEqual([k.strip().lower() for k in m.group(1).split(",")],
                         ["ts desc"],
                         "yalnız-FAIL indeksi ts DESC ile sıralanmalı")
        self.assertEqual(sorted(c.strip().lower() for c in m.group(2).split(",")),
                         sorted(FAIL_INCLUDE))
        self.assertEqual(m.group(3).strip(), FAIL_PREDICATE,
                         "predicate sorgudaki değişmezle BİREBİR aynı olmalı")

    def test_covering_index_does_not_include_wide_columns(self):
        # INCLUDE'a jsonb/hash/bulgu kolonu sızarsa index-only scan şişer.
        forbidden = ("findings", "cli_overrides", "hook_env", "precommit_hooks",
                     "status_board", "pattern_drift", "lean_detail",
                     "lineage_summary", "refs_by_source", "raw_sha256",
                     "stripped_sha256", "history_sidecar_sha256",
                     "source_row_sha256", "id")
        for column in forbidden:
            # Sözcük sınırı şart: `..._idx` gibi indeks adları çıplak `id`
            # aramasına takılırdı.
            self.assertIsNone(re.search(r"\b%s\b" % column, self.lower),
                              "geniş/hassas kolon indekste: %s" % column)

    def test_schema_mirrors_the_raw_sql_indexes(self):
        # Şema `@@index` ile ifade EDEMEZ ama adları/gerekçeyi aynalamalı.
        for token in (COVER, FAIL_PARTIAL, self.path.parent.name):
            self.assertIn(token, self.schema,
                          "şema notu indeksleri aynamıyor: %s" % token)
        # Yorum satır sonlarında bölündüğü için boşluk normalize edilir.
        flat = re.sub(r"\s+", " ", self.schema.replace("//", " "))
        self.assertIn("No such argument", flat,
                      "Prisma sınırı (ölçüm) şemada yazılı olmalı")

    def test_plan_documents_rejections_and_engagement(self):
        # Reddedilenler ve devreye girme koşulu yazılı olmalı (sessiz eskime yok).
        for token in ("REDDEDİLENLER", "p0 > 0", "CONCURRENTLY", "0,28 ms"):
            self.assertIn(token, self.raw,
                          "migration gerekçesinde eksik: %s" % token)
        for token in (COVER, FAIL_PARTIAL, "%13"):
            self.assertIn(token, self.readme,
                          "README indeks planını belgelemiyor: %s" % token)

    def test_no_counterproductive_indexes_sneak_in(self):
        # Tek-kolonlu geniş indeksler / tekrar eden init indeksleri eklenmemeli.
        for wrong in ("on public.trend_runs (verdict)", "on public.trend_runs (p0",
                      "on public.trend_runs (budget_usd)",
                      "on public.trend_runs (source_row_sha256)",
                      "on public.trend_runs (id)"):
            self.assertNotIn(wrong, self.lower,
                             "gereksiz/reddedilen indeks eklendi: %s" % wrong)


if __name__ == "__main__":
    unittest.main()
