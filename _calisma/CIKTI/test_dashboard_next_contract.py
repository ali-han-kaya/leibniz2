"""apps/dashboard-next App Router sözleşme kapısı (Next.js 15, skill:
nextjs-app-router-patterns).

Bu uygulamanın tip denetimi CI'da **koşmuyordu** — dashboard-next'e hicbir
workflow işaret etmiyor. Sonuç: ölü kod sessizce birikti ve `tsc --noEmit`
yeşil kaldı, çünkü `noUnusedLocals`/`noUnusedParameters` kapalıydı.

Ölçülen çürüme (2026-10-03, düzeltme öncesi):
  app/VerdictCard.tsx(1,20): TS6133 'VariantProps' is declared but never read.
  app/trend/page.tsx(1,20):  TS6133 'VariantProps' is declared but never read.
  lib/preview.ts(35,41):     TS6133 'revalidate' is declared but never read.
  (revalidate parametresi `cache: 'no-store'` olan isteğe hiç dokunmuyordu —
   yani sanki ISR koyuyormuş gibi görünüp hiçbir şey yapmayan bir API.)

Kapı iki iş yapar:
  1. `noUnusedLocals`/`noUnusedParameters` AÇIK olmalı (yoksa TS6133 geri gelir).
  2. dashboard-next GERÇEKTEN tip-denetlenmeli.

(2) için kapı `node_modules/.bin/tsc --noEmit`'i GERÇEKTEN çalıştırır
(ölçülen ~4 sn). TypeScript kurulu değilse açıkça skip eder ve bunu
raporlar — ama bu durum yanlış-negatife yol açmamalıdır, o yüzden
dashboard-next'e hiçbir workflow işaret etmeyen bu depoda kapının
skip'li hâli tek başına yeterli değildir: `npm ci` sonrası kapı
kırmızıya döner. Statik kısım (1) ise node/npm gerektirmez ve ortamda
node bulunmayan CI'da da çalışır.
"""
import json
import pathlib
import shutil
import subprocess
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1] if HERE.name == "CIKTI" else HERE.parents[2]
APP = REPO_ROOT / "apps" / "dashboard-next"
TSCONFIG = APP / "tsconfig.json"
# Proje prettier'ı ile aynı binary (node_modules/.bin/prettier 3.6.2);
# kökteki npx prettier farklı sürüm çözüyor ve kapıyla çelişiyor.
TSC = APP / "node_modules" / ".bin" / "tsc"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class TestUnusedChecksEnabled(unittest.TestCase):
    """Ölü kodun yeniden birikmesini baştan engelleyen iki bayrak."""

    def test_no_unused_locals_enabled(self):
        cfg = json.loads(read(TSCONFIG))
        self.assertIs(
            cfg["compilerOptions"].get("noUnusedLocals"),
            True,
            "noUnusedLocals kapalı — TS6133 (ölü import/param) tekrar sessizleşir",
        )

    def test_no_unused_parameters_enabled(self):
        cfg = json.loads(read(TSCONFIG))
        self.assertIs(
            cfg["compilerOptions"].get("noUnusedParameters"),
            True,
            "noUnusedParameters kapalı — kullanılmayan parametreler birikir "
            "(ölçülen: getJson'in `revalidate` argümanı hiç kullanılmıyordu)",
        )

    def test_strict_still_enabled(self):
        """Sıkı mod kapatılmış olabilirdi — regresyon yok."""
        cfg = json.loads(read(TSCONFIG))
        self.assertIs(cfg["compilerOptions"].get("strict"), True)


class TestRealTypecheckRuns(unittest.TestCase):
    """Statik bayrak denetimi TEK BAŞINA yetmez — gerçek tsc koşmalı.

    Ölçülen çürüme: kapı tsconfig'de `noUnusedLocals: true` görüp
    yeşil kalırken uygulamanın derlenemez hale gelmesi mümkündür;
    kırmızı bir TS2307/TS6133 ancak tsc'yi gerçekten çalıştıran
    bir kapı yakalar. `noUnused*` bayrakları ancak tsc koşarsa
    gerçekten uygulanır.
    """

    def test_tsc_no_emit_is_clean(self):
        if not TSC.is_file():
            self.skipTest(
                f"typescript kurulu değil ({TSC}) — statik denetim "
                "yine de koşar; CI'da npm ci sonrası bu kapı fiilen "
                "tip denetimi yapar")
        r = subprocess.run(
            [str(TSC), "--noEmit", "-p", str(TSCONFIG)],
            capture_output=True, text=True, timeout=300, cwd=str(APP))
        self.assertEqual(
            0, r.returncode,
            "tsc --noEmit hata verdi — dashboard-next derlenmiyor:\n"
            + (r.stdout + r.stderr)[-4000:])

    def test_typecheck_script_exists(self):
        """`npm run typecheck` bulunmalı (kapı/CI çağırabilsin)."""
        pkg = json.loads(read(APP / "package.json"))
        self.assertIn(
            "typecheck", pkg.get("scripts", {}),
            "package.json'da typecheck script'i yok — kapı doğrudan "
            "node_modules/.bin/tsc çağırıyor, ama geliştirici/CI için "
            "kararlı bir giriş noktası şart")


class TestLintScriptCoversUnusedChecks(unittest.TestCase):
    """`npm run lint` bayrakları baypas ediyorsa kapı işe yaramaz."""

    def test_lint_script_runs_tsc_no_emit(self):
        pkg = json.loads(read(APP / "package.json"))
        self.assertIn(
            "tsc --noEmit",
            pkg["scripts"].get("lint", ""),
            "lint script'i tsc --noEmit değil — tsconfig bayrakları uygulanmaz",
        )


class TestNoDeadImportsShipped(unittest.TestCase):
    """Düzeltilen ölü import'ların geri gelmediğini doğrudan sınırlar.

    TS6133'e ek savunma: `type VariantProps` gibi yalnız-tip import'ları
    silmek yerine `import type` biçimine çevirmek de yaygın bir kaçış yoludur;
    burada tip zaten hiç kullanılmıyor.
    """

    def test_variant_props_not_imported_unused(self):
        for rel in ("app/VerdictCard.tsx", "app/trend/page.tsx"):
            body = read(APP / rel)
            # Tek değişmez: tip kullanılmayacaksa dosyada hiç geçmemeli.
            # (Önceden aynı koşul iki assertion ile ayrı ayrı sınanıyordu —
            # regex sonucu hem boş hem de "tespit edilemedi" diye tekrar
            # denetleniyordu; ikincisi ilkinin alt kümesiydi.)
            mentions = [ln for ln in body.splitlines() if "VariantProps" in ln]
            self.assertEqual(
                [],
                mentions,
                f"{rel}: VariantProps import edilmiş ama hiç kullanılmıyor — "
                f"{mentions}",
            )

    def test_getjson_has_no_dead_revalidate_param(self):
        body = read(APP / "lib" / "preview.ts")
        self.assertNotIn(
            "revalidate",
            body,
            "lib/preview.ts: `revalidate` parametresi var ama `cache: 'no-store'` "
            "sabit — görünürde ISR koyar, hiçbir şey yapmaz (ölü API)",
        )


class TestAppRouterFileConventions(unittest.TestCase):
    """skill nextjs-app-router-patterns dosya sözleşmeleri."""

    def test_root_layout_exists_and_sets_metadata(self):
        body = read(APP / "app" / "layout.tsx")
        self.assertIn("export const metadata", body)
        # title.template olmadan çoklu route'un başlıkları birbirine karışır.
        self.assertRegex(body, r"template\s*:")

    def test_error_boundary_is_client_component(self):
        """App Router sözleşmesi: error.tsx 'use client' olmak ZORUNDA."""
        body = read(APP / "app" / "error.tsx")
        self.assertTrue(
            body.lstrip().startswith("'use client'")
            or body.lstrip().startswith('"use client"'),
            "error.tsx 'use client' ile başlamalı — reset() istemcide çalışır",
        )

    def test_loading_and_error_exist(self):
        for rel in ("app/loading.tsx", "app/error.tsx"):
            self.assertTrue(
                (APP / rel).exists(),
                f"{rel} yok — skill: 'Don't ignore loading states'",
            )

    def test_data_layer_is_server_only(self):
        """PREVIEW_API NEXT_PUBLIC_ olmamalı: sunucu URL'i client'a sızmasın.

        next.config.ts yorumu bunu bilinçli bir karar olarak belgeliyor.
        """
        body = read(APP / "lib" / "preview.ts")
        self.assertNotIn(
            "NEXT_PUBLIC_PREVIEW",
            body,
            "PREVIEW_API'ya NEXT_PUBLIC_ öneki sızdı — sunucu tarafı URL "
            "client bundle'ına gömülür ve runtime'da override edilemez",
        )


if __name__ == "__main__":
    unittest.main()