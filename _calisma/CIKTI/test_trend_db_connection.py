"""Neon pooled/direct bağlantı sözleşmesi kapısı — apps/trend-db (Prisma 7 + Neon).

skill `neon-postgres` bağlantı sözleşmesi: uygulama trafiği POOLED
(-pooler, PgBouncer), migration/dump/replication/session-state DIRECT.
Ayrımı bir daha kimse yanlış yere taşımasın diye statik kapı:

  1. Prisma 7 `directUrl`'ı **desteklemiyor** — şemaya yazmak P1012 verir
     (ölçüldü 2026-10-03, prisma 7.10.0). Bu yüzden ayrım config/çalışma
     zamanı arasında kurulur; kapı yanlış "düzeltmeyi" geri getirmeyi yasaklar.
  2. `prisma.config.ts` (yalnız Prisma CLI okur) DIRECT çözmeli.
  3. `scripts/load.ts` (adapter'ı kendisi kurar) POOLED kullanmalı.
  4. `.env.example` ve README ikisini de belgellemeli.

Statik denetim — ağ/DB/node gerektirmez.
"""
import pathlib
import re
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1] if HERE.name == "CIKTI" else HERE.parents[2]
TREND_DB = REPO_ROOT / "apps" / "trend-db"

CONFIG = TREND_DB / "prisma.config.ts"
SCHEMA = TREND_DB / "prisma" / "schema.prisma"
LOADER = TREND_DB / "scripts" / "load.ts"
ENV_EXAMPLE = TREND_DB / ".env.example"
PACKAGE_JSON = TREND_DB / "package.json"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class TestNoDirectUrlInSchema(unittest.TestCase):
    """Prisma 5/6 sözleşmesinin Prisma 7'ye geri sızmasını engeller.

    Ölçüm: `directUrl = env(...)` şemaya yazılınca Prisma 7.10.0
    "The datasource property `directUrl` is no longer supported in schema
    files. Move connection URLs to `prisma.config.ts`." (P1012) ile düşer.
    """

    def test_schema_has_no_direct_url(self):
        self.assertNotIn(
            "directUrl",
            read(SCHEMA),
            "Prisma 7 şemada directUrl'ı reddediyor (P1012) — ayrım "
            "prisma.config.ts tarafında kurulmalı",
        )

    def test_schema_datasource_has_no_url_either(self):
        """Prisma 7'de bağlantı URL'i şemada hiç olmamalı (config'e taşındı)."""
        block = re.search(
            r"datasource\s+db\s*\{(.*?)\}", read(SCHEMA), re.S
        )
        self.assertIsNotNone(block, "datasource db bloğu bulunamadı")
        body = block.group(1)
        for banned in ("url", "directUrl"):
            self.assertNotRegex(
                body,
                rf"^\s*{banned}\s*=",
                f"datasource bloğunda `{banned}` var — Prisma 7 URL'i "
                f"prisma.config.ts'ten çözer",
            )


class TestCliUsesDirectUrl(unittest.TestCase):
    """Prisma CLI migration komutları direct bağlantıyla koşmalı.

    Havuzda migration = `prepared statement "s0" already exists`, kaybolan
    `SET search_path`, ara sıra SQLSTATE 25006 — ve hiçbiri hata mesajında
    "havuzdan kaynaklandı" demez.
    """

    def test_config_prefers_unpooled_over_pooled(self):
        body = read(CONFIG)
        self.assertIn(
            "DATABASE_URL_UNPOOLED",
            body,
            "config direct URL'yi bilmiyor — migration havuzda koşar",
        )
        # Seçim ifadesi: doğrudan bağlantı solda, havuz yedek olmalı.
        # İfadeler araya serpiştirilebilsin diye çok gevşek tutulur; asıl
        # belirleyici sıra denetimi aşağıdaki _selection_order testidir.
        self.assertRegex(
            body,
            r"unpooled\s*\?\?\s*pooled",
            "config'te sıra ters: doğrudan bağlantı yedekte kalmış "
            "(`unpooled ?? pooled` olmalı)",
        )

    def test_selection_order_puts_direct_first(self):
        """`unpooled ?? pooled` gerçekten doğrudan bağlantıyı seçiyor mu?

        Statik desen denetimi tek başına yanıltabilir; bu, ifadenin
        İKİ tarafının da doğru değişkenlere bağlandığını birlikte doğrular.
        """
        body = read(CONFIG)
        # değişken adı -> env değişkeni eşlemesi (dosyanın tamamından)
        env_of = dict(
            re.findall(r"const (\w+)\s*=\s*process\.env\.(\w+);", body)
        )
        m = re.search(r"(\w+)\s*\?\?\s*(\w+)", body)
        if m is None:
            self.skipTest("seçim ifadesi bulunamadı")
        left, right = env_of.get(m.group(1)), env_of.get(m.group(2))
        self.assertEqual(
            left,
            "DATABASE_URL_UNPOOLED",
            "sol operand doğrudan bağlantıyı çözmüyor",
        )
        self.assertEqual(
            right,
            "DATABASE_URL",
            "sağ operand havuz bağlantısını çözmüyor",
        )

    def test_config_does_not_silently_fall_back_to_pooled(self):
        """Yalnız havuz varsa migration sessizce havuzda koşmasın — uyar."""
        body = read(CONFIG)
        self.assertIn(
            "console.warn",
            body,
            "havuza sessiz düşüşte en az bir uyarı olmalı (nedensellik "
            "görünmez: hata 'prepared statement already exists' olur)",
        )

    def test_migration_script_does_not_force_a_url(self):
        """package.json migration'ı elle override etmemeli — config çözer.

        Aksi halde config'in DIRECT seçimi etkisizleşir.
        """
        import json

        pkg = json.loads(read(PACKAGE_JSON))
        for script, cmd in pkg.get("scripts", {}).items():
            if "prisma migrate" not in cmd:
                continue
            self.assertNotIn(
                "DATABASE_URL=",
                cmd,
                f"`npm run {script}` config'i baypas edip URL dayatıyor; "
                f"seçim tek yerden (config) olmalı",
            )


class TestRuntimeClientUsesPooledUrl(unittest.TestCase):
    """Uygulama trafiği havuzda kalmalı — config yalnız CLI içindir."""

    def test_loader_builds_adapter_from_pooled_url(self):
        body = read(LOADER)
        self.assertIn(
            "process.env.DATABASE_URL",
            body,
            "loader adapter'ı env'den kurmalı",
        )
        # Loader'da direct URL kullanılırsa uygulama trafiği havuzdan çıkar.
        self.assertNotIn(
            "DATABASE_URL_UNPOOLED",
            body,
            "loader direct bağlantıyı kullanıyor — uygulama trafiği "
            "havuzlanmaz (Neon sözleşmesinin tersi)",
        )


class TestDocumentedContract(unittest.TestCase):
    """Belge, ölçülmüş gerçeği anlatmalı — eski/yanlış öneri kalmasın."""

    def test_env_example_declares_both_urls(self):
        body = read(ENV_EXAMPLE)
        for var in ("DATABASE_URL=", "DATABASE_URL_UNPOOLED="):
            self.assertIn(var, body, f".env.example {var} tanımlamıyor")

    def test_env_example_marks_pooled_as_pooled(self):
        body = read(ENV_EXAMPLE)
        pooled_line = next(
            ln for ln in body.splitlines() if ln.startswith("DATABASE_URL=")
        )
        self.assertIn(
            "-pooler",
            pooled_line,
            "DATABASE_URL örneği pooled olmalı; havuz işareti kaybolursa "
            "okuyan yanılır",
        )

    def test_readme_does_not_recommend_direct_url(self):
        """README eskiden `directUrl` öneriyordu — Prisma 7'de imkânsız."""
        body = read(TREND_DB / "README.md")
        for line in body.splitlines():
            if "directUrl" not in line:
                continue
            # Yalnızca "yok/ desteklemiyor/reddediyor" diyen satırlar serbest.
            self.assertIsNotNone(
                re.search(
                    r"yok|desteklem|redded|P1012|taşınam|artık|imkânsız|no longer",
                    line,
                    re.IGNORECASE,
                ),
                f"README directUrl'ı kullanılabilir bir seçenek gibi anlatıyor: "
                f"{line.strip()!r} — Prisma 7 desteklemiyor",
            )


if __name__ == "__main__":
    unittest.main()