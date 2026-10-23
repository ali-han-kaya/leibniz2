"""apps/trend-db Prisma kurulum sözleşmesi — skill: prisma-database-setup
(PostgreSQL + Prisma 7 yolu).

Bu paket `.ts` kaynaklari (scripts/load.ts, prisma.config.ts) satiyordu ama
NE TypeScript bagimligi NE de tsconfig.json vardi — yani hicbir sey tip
denetlenmiyordu. Skill'in on kosulu ("TypeScript 5.4.0+") ve "Re-run
`prisma generate` after every schema change" kurali sessizce ihlal ediliyordu.

Kapı şunları fail-closed tutar:
  1. TypeScript bagimligi + tsconfig.json + `typecheck` script'i var mi?
  2. `prisma` CLI `dependencies` degil `devDependencies` icinde mi?
     (skill: `npm install prisma --save-dev` — CLI bir build aracidir.)
  3. Generator Prisma 7 kanonik bicimi: `prisma-client` + acik `output`.
  4. datasource yalniz `provider` tasir (Prisma 7 URL'i config'e tasidi;
     `directUrl` P1012 ile reddediliyor — olculdu).
  5. Loader gercekten surucu-adaptoru kullaniyor (`PrismaPg`) ve TEK
     PrismaClient ornegi kuruyor (her ornek bir havuz acar).

Statik denetim — node/npm gerektirmez.
"""
import json
import pathlib
import re
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1] if HERE.name == "CIKTI" else HERE.parents[2]
APP = REPO_ROOT / "apps" / "trend-db"
PKG = APP / "package.json"
SCHEMA = APP / "prisma" / "schema.prisma"
TSCONFIG = APP / "tsconfig.json"
LOADER = APP / "scripts" / "load.ts"
CONFIG = APP / "prisma.config.ts"


def read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


class TestTypescriptPrerequisite(unittest.TestCase):
    """Skill on kosulu: TypeScript 5.4.0+. Bu depoda hic yoktu."""

    def test_typescript_is_declared(self):
        pkg = json.loads(read(PKG))
        version = pkg.get("devDependencies", {}).get("typescript") or pkg.get(
            "dependencies", {}
        ).get("typescript")
        self.assertIsNotNone(version, "typescript bagimligi yok")
        major_minor = re.match(r"[\^~]?(\d+)\.(\d+)", version or "")
        self.assertIsNotNone(major_minor, f"surum parse edilemedi: {version}")
        major, minor = int(major_minor.group(1)), int(major_minor.group(2))
        self.assertGreaterEqual(
            (major, minor),
            (5, 4),
            f"TypeScript {version} — skill 5.4.0+ istiyor",
        )

    def test_tsconfig_exists(self):
        self.assertTrue(TSCONFIG.exists(), "tsconfig.json yok — .ts kaynaklar denetlenmiyor")

    def test_tsconfig_covers_the_actual_sources(self):
        """include gercekten derlenen dosyalari kapsiyor mu?

        NOT: `generated/` dislamak bir sir degil. Prisma 7 uretilmis her
        dosyaya `// @ts-nocheck` basiyor, dolayisiyla uretilmis dosyalar
        hicbir zaman tip kontrolune girmez — olculdu (uretilmis modele tip
        hatasi eklendi, tsc yesil kaldi). Bu yuzden bu kapı, client drift
        YAKALAMAZ; drift'in sahibi test_trend_db_contract.py'dir. Buradaki
        tek dogrulanabilir sart: kaynaklar include icinde.
        """
        body = read(TSCONFIG)
        m = re.search(r'"include"\s*:\s*\[(.*?)\]', body, re.S)
        self.assertIsNotNone(m, "include blogu bulunamadi")
        include = m.group(1)
        self.assertIn("prisma.config.ts", include)
        self.assertIn("scripts/**/*.ts", include)

    def test_no_paths_remap_for_prisma_client(self):
        """load.ts runtime SUBPATH'i iceriyor; bare @prisma/client deseni
        hicbir zaman eslesmez (tsc --traceResolution ile olculdu) ve gelecekte
        bir kok import'u yanlis yonlendirirdi."""
        body = read(TSCONFIG)
        self.assertNotRegex(
            body,
            r'"@prisma/client"\s*:',
            "tsconfig'te @prisma/client paths eslemesi var — olu ve yaniltici",
        )

    def test_strict_and_unused_checks_on(self):
        body = read(TSCONFIG)
        for flag in ("strict", "noUnusedLocals", "noUnusedParameters"):
            self.assertRegex(
                body,
                rf'"{flag}"\s*:\s*true',
                f"tsconfig'de `{flag}: true` yok",
            )

    def test_typecheck_script_exists(self):
        scripts = json.loads(read(PKG)).get("scripts", {})
        self.assertIn("typecheck", scripts, "`npm run typecheck` script'i yok")
        self.assertIn("tsc --noEmit", scripts["typecheck"])

    def test_generate_script_exists(self):
        """`prisma generate` skill kurali: schema her degistiginde calismali."""
        scripts = json.loads(read(PKG)).get("scripts", {})
        self.assertIn("db:generate", scripts)
        self.assertIn("prisma generate", scripts["db:generate"])


class TestCliIsDevDependency(unittest.TestCase):
    """Skill: `npm install prisma --save-dev` — CLI calisma aracidir."""

    def test_prisma_not_in_runtime_dependencies(self):
        deps = json.loads(read(PKG)).get("dependencies", {})
        self.assertNotIn(
            "prisma",
            deps,
            "`prisma` CLI'si runtime dependencies icinde — uretim kurulumunu "
            "sisiriyor ve client ile suruklenebilir",
        )

    def test_prisma_in_dev_dependencies(self):
        dev = json.loads(read(PKG)).get("devDependencies", {})
        self.assertIn("prisma", dev)

    def test_runtime_deps_keep_client_and_adapter(self):
        """Bunlar gercekten runtime: adapter + client + driver + dotenv."""
        deps = json.loads(read(PKG)).get("dependencies", {})
        for pkg in ("@prisma/client", "@prisma/adapter-pg", "pg"):
            self.assertIn(pkg, deps, f"{pkg} runtime dependencies icinde olmali")


class TestGeneratorShape(unittest.TestCase):
    """Prisma 7 kanonik generator: `prisma-client` + acik output."""

    def test_generator_uses_prisma_client_with_output(self):
        body = read(SCHEMA)
        m = re.search(r"generator\s+client\s*\{(.*?)\}", body, re.S)
        self.assertIsNotNone(m, "generator client blogu yok")
        block = m.group(1)
        self.assertRegex(block, r'provider\s*=\s*"prisma-client"')
        self.assertRegex(block, r'output\s*=\s*"', "output zorunlu (prisma-client node_modules'a uretmez)")

    def test_datasource_has_no_directurl(self):
        """Prisma 7 `directUrl`'i P1012 ile reddeder (olculdu)."""
        body = read(SCHEMA)
        self.assertNotIn("directUrl", body)

    def test_datasource_carries_provider_only(self):
        """URL config'e tasindi; datasource'da url satiri olmamali."""
        m = re.search(r"datasource\s+db\s*\{(.*?)\}", read(SCHEMA), re.S)
        self.assertIsNotNone(m)
        self.assertNotRegex(
            m.group(1),
            r"^\s*url\s*=",
            "datasource'ta url var — Prisma 7 config'ten cozuyor",
        )


class TestRuntimeWiring(unittest.TestCase):
    """Driver adapter + tek client ornegi (skill: 'Use a single instance')."""

    def test_loader_uses_pg_driver_adapter(self):
        body = read(LOADER)
        self.assertIn("@prisma/adapter-pg", body)
        self.assertRegex(body, r"new\s+PrismaPg\s*\(")

    def test_loader_imports_generated_client_relatively(self):
        body = read(LOADER)
        self.assertRegex(
            body,
            r"from\s+'\.\./generated/client'",
            "client generated/ dizininden goreli alinmali",
        )

    def test_single_prisma_client_instance(self):
        """Her PrismaClient ornegi bir baglanti havuzu acar."""
        body = read(LOADER)
        self.assertEqual(
            len(re.findall(r"new\s+PrismaClient\s*\(", body)),
            1,
            "birden fazla PrismaClient ornegi — her biri ayri havuz acar",
        )

    def test_config_resolves_url_from_env(self):
        body = read(CONFIG)
        self.assertIn("DATABASE_URL", body)
        self.assertRegex(body, r"datasource\s*:\s*\{", "config datasource tanımlamali")
        self.assertRegex(body, r"url\s*:")


if __name__ == "__main__":
    unittest.main()