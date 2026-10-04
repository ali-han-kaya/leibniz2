#!/usr/bin/env python3
"""test_openapi_schema.py — OpenAPI şeması ↔ API_CONTRACT sözleşmesi.

Tek-kaynak zinciri: test_api_method_contract.API_CONTRACT → gen_openapi
→ openapi.json. Bu süit zincirin iki ucunu sabitler:

  1) Drift: diskteki openapi.json, API_CONTRACT'tan yeniden üretilen
     şemayla birebir aynı olmalı (deterministik üretim; fark = fail).
     Yeni endpoint eklenirse API_CONTRACT + openapi.json AYNI commit'te
     güncellenmeli — aksi halde bu test pre-commit'te kızarır.
  2) Yapısal invaryantlar: OpenAPI 3.1 uyumu, her /api/* yolu tam bir
     kez, her operasyon method-allow kümesiyle uyumlu, deprecated
     alanı yalnız politika-dokümanındaki iki-adım şablonla gelebilir
     (x-deprecated-since + x-sunset birlikte; tek başına yasak).
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import gen_openapi as gen  # noqa: E402
from test_api_method_contract import API_CONTRACT, SSE_PATHS  # noqa: E402

SCHEMA_PATH = CIKTI / "openapi.json"


class TestOpenApiGenerated(unittest.TestCase):
    """Şema ↔ sözleşme bütünlüğü (üretici saf — disk gerekmez)."""

    def test_generated_schema_is_deterministic(self):
        a = gen.generate()
        b = gen.generate()
        self.assertEqual(a, b, "üretici deterministik değil — json.dump "
                               "sıralaması sabitlenmeli")

    def test_schema_covers_exactly_the_contract(self):
        spec = gen.generate()
        schema_paths = set(spec["paths"])
        contract_paths = set(API_CONTRACT)
        self.assertEqual(schema_paths, contract_paths,
                         "openapi.json ↔ API_CONTRACT yol-kümesi farklı — "
                         "gen_openapi üretimini çalıştırın: python3 "
                         "_calisma/CIKTI/gen_openapi.py")

    def test_operations_match_allowed_methods(self):
        spec = gen.generate()
        for path, methods in API_CONTRACT.items():
            ops = {k for k in spec["paths"][path] if k in gen.HTTP_METHODS}
            self.assertEqual(ops, set(m.lower() for m in methods),
                             f"{path}: operasyon-kümesi izinli-metot "
                             "kümesiyle uyuşmuyor")

    def test_contract_drift_fails_closed(self):
        """API_CONTRACT'ta olmayan bir yol şemaya sızmamalı (ters-yön)."""
        spec = gen.generate()
        for path in spec["paths"]:
            self.assertTrue(path.startswith("/api/"),
                            f"şemada /api/-dışı yol sızdı: {path}")


class TestOpenApiOnDisk(unittest.TestCase):
    """Diskteki şema üretim-çıktısıyla birebir (drift kapısı)."""

    def test_disk_schema_matches_generator(self):
        self.assertTrue(SCHEMA_PATH.exists(),
                        "openapi.json yok — python3 _calisma/CIKTI/"
                        "gen_openapi.py ile üretin")
        disk = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(disk, gen.generate(),
                         "openapi.json bayat — API_CONTRACT ile yeniden "
                         "üretin: python3 _calisma/CIKTI/gen_openapi.py")


class TestOpenApiGateResponses(unittest.TestCase):
    """State-changing uçların KAPI yanıtları şemada belgeli olmalı.

    Boşluk (2026-10-04): /api/run-now handler'ı peer + Host/Origin reddinde
    403, bearer reddinde 401 döner; şema yalnız 200/404/409 diyordu.
    /api/stop'un 403'ü ise gerekçesiz "JSON yanıt" idi — üretilen şemayı
    okuyan istemci 403'ün neden geldiğini bilmiyordu.

    Kodeki `_peer_gate` tekliğinin şemadaki karşılığı: iki uç da AYNI 403
    açıklamasını taşır, uç başına kopya yazılmaz.
    """

    def _post_responses(self, schema, path):
        return schema["paths"][path]["post"]["responses"]

    def test_both_state_changing_endpoints_document_peer_host_403(self):
        schema = gen.generate()
        for path in ("/api/stop", "/api/run-now"):
            with self.subTest(path=path):
                resp = self._post_responses(schema, path)
                self.assertIn("403", resp, "%s 403'ü belgelemiyor" % path)
                desc = resp["403"]["description"]
                self.assertIn("forbidden peer", desc)
                self.assertIn("forbidden host", desc)

    def test_peer_host_403_is_not_generic(self):
        """403 gerekçesiz 'JSON yanıt' olamaz — istemci nedeni bilmeli."""
        schema = gen.generate()
        for path in ("/api/stop", "/api/run-now"):
            with self.subTest(path=path):
                desc = self._post_responses(schema, path)["403"]["description"]
                self.assertNotEqual(desc, "JSON yanıt",
                                    "%s 403'ü yine gerekçesiz" % path)

    def test_gate_403_description_is_shared_between_endpoints(self):
        """Tek kaynak: iki uç aynı metni taşır (kopya yazılmaz)."""
        schema = gen.generate()
        stop = self._post_responses(schema, "/api/stop")["403"]["description"]
        run = self._post_responses(schema, "/api/run-now")["403"]["description"]
        self.assertEqual(stop, run,
                         "gate 403 metni uçlar arasında ayrıştı")

    def test_run_now_documents_conditional_bearer_401(self):
        """Bearer yalnız run-now'da; şema bunu koşulla anlatmalı."""
        schema = gen.generate()
        self.assertIn("401", self._post_responses(schema, "/api/run-now"))
        self.assertNotIn("401", self._post_responses(schema, "/api/stop"),
                         "/api/stop bearer kapısı taşımaz")
        desc = self._post_responses(schema, "/api/run-now")["401"]["description"]
        self.assertIn("PREVIEW_RUN_NOW_TOKEN", desc)

    def test_schema_responses_match_live_handler_gates(self):
        """Şema, handler'daki gerçek kapı sırasını yansıtır.

        Handler'da peer → Host/Origin → bearer sırası var; şema en azından
        her katmanın dönebileceği durumu belgelemeli.
        """
        responses = self._post_responses(gen.generate(), "/api/run-now")
        for code in ("200", "401", "403", "404", "409"):
            self.assertIn(code, responses, "run-now %s belgelenmemiş" % code)
        stop = self._post_responses(gen.generate(), "/api/stop")
        for code in ("202", "403", "404", "503"):
            self.assertIn(code, stop, "stop %s belgelenmemiş" % code)


class TestOpenApiDriftGate(unittest.TestCase):
    """`gen_openapi.py --check` CLI sözleşmesi + pre-commit kaydı.

    `TestOpenApiOnDisk` aynı bayatlığı KARŞILAŞTIRMA düzeyinde doğrular;
    buradaki sınıf kapının commit'i GERÇEKTEN blokladığı yüzü pinler:
    --check sıfari (CLI sezi) + config kaydı.
    """

    CONFIG = CIKTI.parent.parent / ".pre-commit-config.yaml"
    HOOK_ID = "check-openapi-drift"

    def _hook_block(self) -> str:
        text = self.CONFIG.read_text(encoding="utf-8")
        needle = "- id: %s" % self.HOOK_ID
        self.assertIn(needle, text,
                      "%s .pre-commit-config.yaml'da tanımlı değil — "
                      "bayatlık kapısı çalışmıyor" % self.HOOK_ID)
        start = text.index(needle)
        nxt = text.find("\n      - id:", start + 1)
        return text[start:] if nxt == -1 else text[start:nxt]

    def _run(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = gen.main(list(argv))
        return rc, buf.getvalue()

    def test_check_passes_on_fresh_schema(self):
        """Depodaki openapi.json güncelse kapı rc=0 döner."""
        rc, out = self._run("--check", "--output", str(SCHEMA_PATH))
        self.assertEqual(rc, 0, "kapı güncel şemada kırmızı: %r" % out)
        self.assertIn("openapi.json güncel", out)

    def test_check_fails_on_stale_schema(self):
        """Bayat şema rc=1 + düzeltme komutu yazdırır (fail-closed)."""
        with tempfile.TemporaryDirectory() as td:
            stale = pathlib.Path(td) / "openapi.json"
            spec = gen.generate()
            spec["info"]["version"] = "0.0.1-bayat"
            stale.write_text(json.dumps(spec, indent=2, ensure_ascii=False,
                                        sort_keys=True) + "\n",
                             encoding="utf-8")
            rc, out = self._run("--check", "--output", str(stale))
        self.assertEqual(rc, 1, "bayat şema geçti: %r" % out)
        self.assertIn("ŞEMA BAYAT", out)
        self.assertIn("gen_openapi.py", out,
                      "düzeltme komutu çıktıda olmalı — kullanıcı ne "
                      "yapacağını bilemez")

    def test_check_fails_when_schema_missing(self):
        """Eksik şema sessizce geçmez: rc=1 + üretim komutu."""
        with tempfile.TemporaryDirectory() as td:
            rc, out = self._run("--check", "--output",
                                str(pathlib.Path(td) / "yok.json"))
        self.assertEqual(rc, 1, "eksik şema geçti: %r" % out)
        self.assertIn("ŞEMA YOK", out)

    def test_generate_is_idempotent(self):
        """Düzeltme komutu idempotent: üret → bayat olmaz."""
        with tempfile.TemporaryDirectory() as td:
            out_path = str(pathlib.Path(td) / "openapi.json")
            rc, _ = self._run("--output", out_path)
            self.assertEqual(rc, 0, "üretim komutu başarısız")
            rc, out = self._run("--check", "--output", out_path)
        self.assertEqual(rc, 0, "taze üretim bayat sayıldı: %r" % out)

    def test_hook_registered_with_check_entry(self):
        """Config kaydı: --check girişi + ağaç-geniş (always_run) tetikleme."""
        block = self._hook_block()
        self.assertIn("gen_openapi.py --check", block,
                      "kapı --check girişiyle tanımlı olmalı")
        self.assertIn("always_run: true", block,
                      "bayatlık kaynak-sözleşmesiz de oluşabilir; kapı "
                      "always_run olmazsa sadece yanlış dosyada koşar")
        self.assertIn("pass_filenames: false", block)


class TestOpenApiStructure(unittest.TestCase):
    """Yapısal invaryantlar + deprecation politika-sabiti."""

    def test_openapi_version_and_info(self):
        spec = gen.generate()
        self.assertTrue(spec["openapi"].startswith("3.1"))
        self.assertIn("title", spec["info"])
        self.assertIn("version", spec["info"])
        self.assertIn("description", spec["info"])

    def test_every_operation_has_error_responses(self):
        """Operasyon-başına yanıt-sözleşmesi (matris-uyumlu).

        - Okuma/POST uçları: 200/202 + 404 (fallback) — 405/409/403/503
          nerede zorunlusa operasyon-düzeyinde belgelenir.
        - SSE hücresi: yalnız 200 — izinli-metot hücresi routing-404
          alamaz (test_api_method_matrix fail-closed şartı).
        """
        spec = gen.generate()
        sse = {p for p in SSE_PATHS}
        for path, item in spec["paths"].items():
            for op, body in item.items():
                if op not in gen.HTTP_METHODS:
                    continue
                self.assertIn("responses", body,
                              f"{op.upper()} {path}: responses eksik")
                codes = set(body["responses"])
                if path in sse and op == "get":
                    self.assertEqual(codes, {"200"},
                                     f"{op.upper()} {path}: SSE hücresi "
                                     "yalnız 200 — routing-404 yasak")
                    continue
                self.assertTrue(codes & {"200", "202"},
                                f"{op.upper()} {path}: 200/202 eksik")
                self.assertIn("404", codes,
                              f"{op.upper()} {path}: fallback 404 "
                              "belgelenmeli")

    def test_unsupported_methods_documented_501(self):
        """Yöntem-matrisiyle uyum: desteklenmeyen metot 501 default'tur.

        OpenAPI'de declare-edilmeyen operasyon zaten "desteklenmiyor"
        anlamına gelir; şema buna ek olarak info.description'da 501
        davranışını belgelemeli (politika: 405 = bilinçli reddin tek
        aracı, 404 = bilinmeyen yol, 501 = tanımsız metot).
        """
        spec = gen.generate()
        self.assertIn("501", spec["info"]["description"])

    def test_deprecation_requires_both_fields(self):
        """Politika: deprecated yalnız iki-adım şablonla — tek başına yasak.

        x-deprecated-since (duyuru sürümü) + x-sunset (kaldırma hedefi)
        BİRLİKTE zorunlu; bunlarsan deprecated=true şemayı üretime
        geçiremez (test fail-closed). Şu an hiçbir uç deprecated değil;
        bu test gelecekteki ihlalleri yakalar.
        """
        spec = gen.generate()
        for path, item in spec["paths"].items():
            for op, body in item.items():
                if op not in gen.HTTP_METHODS:
                    continue
                if body.get("deprecated"):
                    self.assertIn("x-deprecated-since", body,
                                  f"{op.upper()} {path}: deprecated "
                                  "x-deprecated-since'siz yasak")
                    self.assertIn("x-sunset", body,
                                  f"{op.upper()} {path}: deprecated "
                                  "x-sunset'siz yasak")

    def test_policy_doc_exists_and_pins_template(self):
        """Politika dokümanı şema-ülaliciyle aynı sabiti taşımali."""
        doc = (CIKTI.parent.parent / "docs" / "API_VERSIONING.md")
        self.assertTrue(doc.exists(),
                        "docs/API_VERSIONING.md yok — politika "
                        "dokümansız sürümleme olmaz")
        text = doc.read_text(encoding="utf-8")
        self.assertIn("x-deprecated-since", text)
        self.assertIn("x-sunset", text)
        self.assertIn("PREVIEW_API_VERSION", text)


if __name__ == "__main__":
    unittest.main()
