#!/usr/bin/env python3
"""test_openapi_docs.py — yayınlanmış API referansının (Redoc) sözleşmesi.

Zincirin yayın halkası: openapi.json → gen_openapi_docs.py →
docs/api/index.html → preview `/api-docs.html`.

Bu süit, dokümanın üç farklı yönünü sabitler:

  1) Drift kapısı: `--check` taze sayfada rc=0, bayat/eksik sayfada rc=1
     ve çıktıda düzeltme komutu.
  2) Taşıma bütünlüğü: sayfanın gömülü şeması, `openapi.json`'ın birebir
     baytlarını taşır — iki kopya sessizce ayrışamaz.
  3) Render önkoşulları: `Redoc.init` nesne alır (ölçülmüş hata: string
     verilince Redoc onu URL sanıp fetch eder ve "Failed to load" basar),
     CDN sürüm sabitlidir, `</script>` erken kapama kaçışlıdır.
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
REPO_ROOT = CIKTI.parent.parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import gen_openapi_docs as gen  # noqa: E402

SPEC_PATH = CIKTI / "openapi.json"
PAGE_PATH = gen.OUT_PATH
CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
MIRROR_SH = CIKTI / "sync_verify_mirror.sh"

OPEN_SCRIPT = '<script id="openapi-spec" type="application/json">'
CLOSE_SCRIPT = "</script>"


def embedded_spec(html):
    """Sayfadaki gömülü şemayı metin olarak çıkarır."""
    start = html.index(OPEN_SCRIPT) + len(OPEN_SCRIPT)
    end = html.index(CLOSE_SCRIPT, start)
    return html[start:end].strip()


class TestDocsCliContract(unittest.TestCase):
    """`gen_openapi_docs.py --check` sözleşmesi."""

    def _run(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = gen.main(list(argv))
        return rc, buf.getvalue()

    def test_check_passes_on_committed_page(self):
        rc, out = self._run("--check")
        self.assertEqual(rc, 0, "yayınlanmış sayfa bayat: %r" % out)
        self.assertIn("api-docs güncel", out)

    def test_check_fails_on_stale_page(self):
        with tempfile.TemporaryDirectory() as td:
            stale = pathlib.Path(td) / "index.html"
            stale.write_text("<html>eski sayfa</html>\n", encoding="utf-8")
            rc, out = self._run("--check", "--output", str(stale))
        self.assertEqual(rc, 1, "bayat sayfa geçti: %r" % out)
        self.assertIn("DOKÜMAN BAYAT", out)
        self.assertIn("gen_openapi_docs.py", out,
                      "düzeltme komutu çıktıda olmalı")

    def test_check_fails_when_page_missing(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = self._run("--check", "--output",
                                str(pathlib.Path(td) / "yok.html"))
        self.assertEqual(rc, 1, "eksik sayfa geçti: %r" % out)
        self.assertIn("DOKÜMAN YOK", out)

    def test_generate_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = str(pathlib.Path(td) / "index.html")
            rc, _ = self._run("--output", out_path)
            self.assertEqual(rc, 0, "üretim komutu başarısız")
            rc, out = self._run("--check", "--output", out_path)
        self.assertEqual(rc, 0, "taze üretim bayat sayıldı: %r" % out)

    def test_render_is_pure(self):
        spec = SPEC_PATH.read_text(encoding="utf-8")
        self.assertEqual(gen.render(spec), gen.render(spec),
                         "render saf değil — iki çağrı farklı bayt veriyor")


class TestPageCarriesSchema(unittest.TestCase):
    """Sayfa, şemanın birebir baytlarını gömülü taşır."""

    def setUp(self):
        self.page = PAGE_PATH.read_text(encoding="utf-8")

    def test_embedded_spec_equals_checked_in_schema(self):
        raw = embedded_spec(self.page).replace("<\\/", "</")
        self.assertEqual(json.loads(raw), json.loads(SPEC_PATH.read_text(
            encoding="utf-8")),
            "sayfadaki gömülü şema openapi.json ile ayrışmış — yayınlanan "
            "referans başka bir sözleşme gösteriyor")

    def test_embedded_spec_does_not_close_script_early(self):
        """Gömülü blokta kaçışsız '</' yok — script erken kapanmamalı."""
        block = embedded_spec(self.page)
        self.assertNotIn("</", block.replace("<\\/", ""),
                         "gömülü blokta kaçışsız '</' var — script erken kapanır")

    def test_render_escapes_script_closing_in_spec(self):
        """Kaçış, veriye bağlı olmamalı: '<' dizisi içeren şema da güvenli.

        Bugünki openapi.json '<' içermiyor, yani kaçış üretimde hiç
        görünmüyor; yarın bir description'a '</' girdiğinde erken kapanma
        olmasın diye SENTETİK şemayla kanıtlanır.
        """
        synthetic = json.dumps(
            {"openapi": "3.1.0", "info": {"title": "t", "version": "1",
                                          "description": "a </script> b"}})
        block = embedded_spec(gen.render(synthetic))
        self.assertNotIn("</", block.replace("<\\/", ""),
                         "kaçış uygulanmamış — script erken kapanır")
        self.assertIn("<\\/", block)
        self.assertEqual(
            json.loads(block.replace("<\\/", "</"))["info"]["description"],
            "a </script> b", "kaçış round-trip'i bozuyor")

    def test_page_declares_language_and_main(self):
        self.assertIn('<html lang="tr">', self.page)
        self.assertEqual(self.page.count("<main>"), 1)

    def test_noscript_fallback_points_at_source_spec(self):
        self.assertIn("<noscript>", self.page)
        self.assertIn("openapi.json", self.page)


class TestRedocRenderPreconditions(unittest.TestCase):
    """Render'ın çalışması için gereken önkoşullar (ölçülmüş hatalar)."""

    def setUp(self):
        self.page = PAGE_PATH.read_text(encoding="utf-8")

    def test_init_receives_parsed_object_not_raw_string(self):
        """Redoc.init string'i URL sanar (ölçüldü: 'Failed to load').

        Gömülü şemayı olduğu gibi metin olarak geçmek render'ı komple
        kırar; nesne (JSON.parse) geçmeli.
        """
        self.assertIn("JSON.parse(document.getElementById(\"openapi-spec\")",
                      self.page)
        self.assertNotIn('Redoc.init(\n    document.getElementById("openapi-'
                         'spec").textContent,', self.page,
                         "şema metni doğrudan geçiriliyor — Redoc onu URL "
                         "sanar ve sayfa boş kalır")

    def test_cdn_url_is_version_pinned(self):
        self.assertIn(gen.REDOC_URL, self.page)
        self.assertIn("/redoc/v%s/" % gen.REDOC_VERSION, gen.REDOC_URL)
        self.assertNotIn("/latest/", self.page,
                         "`latest` render'ı commit'ler arasında sessizce "
                         "değiştirir")

    def test_mount_point_exists(self):
        self.assertIn('id="redoc"', self.page)


class TestPublishWiring(unittest.TestCase):
    """Yayın zinciri: kapı kaydı, rota, mirror listesi."""

    def test_hook_registered_with_check_entry(self):
        text = CONFIG.read_text(encoding="utf-8")
        needle = "- id: check-openapi-docs"
        self.assertIn(needle, text, "check-openapi-docs config'te tanımlı değil")
        start = text.index(needle)
        nxt = text.find("\n      - id:", start + 1)
        block = text[start:] if nxt == -1 else text[start:nxt]
        self.assertIn("gen_openapi_docs.py --check", block)
        self.assertIn("always_run: true", block)
        self.assertIn("pass_filenames: false", block)

    def test_preview_route_serves_page_outside_api_contract(self):
        """`/api-docs.html` statik yüzeydir: Host/Origin kapısına tabi
        değil, API_CONTRACT'a girmez (şema/sözleşme testleri kırılmaz)."""
        import preview_server as ps
        for url in ("/api-docs.html", "/api-docs", "/api-docs.html?_t=1"):
            self.assertEqual(ps._route(url), "api_docs")
        self.assertNotIn("api_docs", ps._API_GET_ROUTES)

    def test_mirror_carries_page_into_preview_dir(self):
        sh = MIRROR_SH.read_text(encoding="utf-8")
        self.assertIn("docs/api/index.html|api-docs.html", sh,
                      "mirror listesi sayfayı taşımıyor — /api-docs.html "
                      "404 döner")

    def test_mirror_coverage_expects_page(self):
        import check_mirror_coverage as cmc
        self.assertEqual(cmc.API_DOCS_REL, "docs/api/index.html")


if __name__ == "__main__":
    unittest.main()
