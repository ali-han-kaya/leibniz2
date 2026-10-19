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
import json
import pathlib
import sys
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
