#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_refs_table_sync.py birim testleri — §2 tablo ↔ kod listeleri senkronu.

PASS yolu + fail-closed drift senaryolarını mock'lu (ağsız) doğrular:
- Gerçek belge/kod üzerinde PASS (64↔64, bijection).
- Kod anahtarı eklenir ama tabloya satır eklenmez → orphan_key FAIL.
- Tablo satırı eklenir ama koda anahtar eklenmez → no_match FAIL.
- Tablo satırı silinir → orphan_key (ters yön) FAIL.
- Override anahtarı kodda yoksa → override_key_missing FAIL.
- Çok anlamlı çapa (soyad+yıl aynı, 2 key) → ambiguous FAIL.
"""

import pathlib
import sys
import unittest
from unittest import mock

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import check_refs_table_sync as crt  # noqa: E402

REAL_MD = CIKTI / "REFERANS_KANIT_DENETIMI.md"

# Test için minimal geçerli belge: gerçek tablo başlığı + bir satır + ayraç.
SAMPLE_TABLE = """## 2. Tam tablo (64 girdi)

| # | Kaynak | Sonuç | Kanıt |
|---|---|---|---|
| 1 | Artemov 2008, RSL 1(4):477–513 | GEÇTİ | CrossRef DOI 10.1017/s1755020308090060 |
| 2 | Beebee 2006, Routledge | GEÇTİ | Routledge/Taylor&Francis |

---
"""


class TestExtract(unittest.TestCase):
    def test_parse_table_rows(self):
        rows = crt.extract_table_rows(SAMPLE_TABLE)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][1], "Artemov 2008, RSL 1(4):477–513")

    def test_real_doc_has_64_rows(self):
        md = REAL_MD.read_text(encoding="utf-8")
        rows = crt.extract_table_rows(md)
        self.assertEqual(len(rows), 64)

    def test_fold_strips_accents(self):
        self.assertEqual(crt._fold("Lagrée 1994"), "lagree 1994")
        self.assertEqual(crt._fold("Rošker, SEP"), "rosker, sep")

    def test_anchor_extracts_surname_year(self):
        self.assertEqual(crt._anchor("Artemov 2008, RSL"),
                         ("artemov", "2008"))
        self.assertEqual(crt._anchor("Rošker, SEP \"Epistemology\""),
                         ("rosker,", None))


class TestRealSync(unittest.TestCase):
    def test_real_doc_and_code_pass(self):
        ok, findings, meta = crt.check()
        self.assertTrue(ok, findings)
        self.assertEqual(meta["table_rows"], 64)
        self.assertEqual(meta["code_keys"], 64)
        self.assertEqual(meta["mapped"], 64)


class TestFailClosed(unittest.TestCase):
    def _keys_with(self, code_keys, add=None, remove=None):
        """Gerçek kod anahtarlarını alıp add/remove uygular (mock için)."""
        keys = dict(code_keys)
        if remove:
            for k in remove:
                keys.pop(k, None)
        if add:
            for k in add:
                keys[k] = "TEST"
        return keys

    def test_orphan_key_when_code_has_extra(self):
        # Koda yeni anahtar eklenir, tabloya satır eklenmez → FAIL.
        code_keys = crt.extract_code_keys()
        code_keys["Fake 2099"] = "TEST"
        rows = crt.extract_table_rows(REAL_MD.read_text(encoding="utf-8"))
        mapping, findings = crt.build_mapping(rows, code_keys)
        kinds = {f["kind"] for f in findings}
        self.assertIn("orphan_key", kinds)
        self.assertIn("Fake 2099", [f["key"] for f in findings
                                    if f["kind"] == "orphan_key"])

    def test_no_match_when_table_has_extra(self):
        # Tabloya satır eklenir, koda anahtar eklenmez → FAIL.
        code_keys = crt.extract_code_keys()
        md = REAL_MD.read_text(encoding="utf-8")
        # Son satırdan sonra (---'den önce) sahte satır ekle.
        injected = md.replace(
            "| 64 | Xunzi 22, Knoblock tr. | GEÇTİ | Stanford UP (Knoblock 1988–94); ctext.org |",
            "| 64 | Xunzi 22, Knoblock tr. | GEÇTİ | Stanford UP (Knoblock 1988–94); ctext.org |\n"
            "| 65 | Hayali 2099, Test | GEÇTİ | Test |")
        rows = crt.extract_table_rows(injected)
        self.assertEqual(len(rows), 65)
        mapping, findings = crt.build_mapping(rows, code_keys)
        kinds = {f["kind"] for f in findings}
        self.assertIn("no_match", kinds)

    def test_deleted_table_row_becomes_orphan_key(self):
        # Tablo satırı silinir (kodda anahtar kalır) → orphan_key (ters yön).
        code_keys = crt.extract_code_keys()
        md = REAL_MD.read_text(encoding="utf-8")
        removed = md.replace(
            "| 1 | Artemov 2008, RSL 1(4):477–513 | GEÇTİ | CrossRef DOI 10.1017/s1755020308090060 |\n",
            "")
        rows = crt.extract_table_rows(removed)
        self.assertEqual(len(rows), 63)
        mapping, findings = crt.build_mapping(rows, code_keys)
        kinds = {f["kind"] for f in findings}
        self.assertIn("orphan_key", kinds)
        self.assertIn("Artemov 2008", [f["key"] for f in findings
                                       if f["kind"] == "orphan_key"])

    def test_override_key_missing_in_code(self):
        # Override tablosu kodda olmayan anahtara işaret ederse → FAIL.
        code_keys = crt.extract_code_keys()
        code_keys.pop("Leibniz 1714", None)
        rows = crt.extract_table_rows(REAL_MD.read_text(encoding="utf-8"))
        with mock.patch.object(crt, "TABLE_OVERRIDES",
                               {**crt.TABLE_OVERRIDES}):
            mapping, findings = crt.build_mapping(rows, code_keys)
        kinds = {f["kind"] for f in findings}
        self.assertIn("override_key_missing", kinds)

    def test_ambiguous_anchor_fails(self):
        # Aynı (soyad, yıl) iki anahtara eşleşirse → ambiguous FAIL.
        code_keys = {
            "Artemov 2008": "TEST", "Artemov 2008 dup": "TEST"}
        for r in crt.extract_code_keys():
            if r != "Artemov 2008":
                code_keys[r] = "TEST"
        rows = crt.extract_table_rows(
            "## 2. Tam tablo\n\n| # | Kaynak | Sonuç | Kanıt |\n"
            "|---|---|---|---|\n"
            "| 1 | Artemov 2008, RSL | GEÇTİ | x |\n\n---\n")
        mapping, findings = crt.build_mapping(rows, code_keys)
        kinds = {f["kind"] for f in findings}
        self.assertIn("ambiguous", kinds)


class TestMainExit(unittest.TestCase):
    def test_main_pass_exit_zero(self):
        rc = crt.main([])
        self.assertEqual(rc, 0)

    def test_main_json_shape(self):
        import io
        import json
        buf = io.StringIO()
        with mock.patch.object(sys, "stdout", buf):
            rc = crt.main(["--json"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertTrue(data["ok"])
        self.assertEqual(data["meta"]["table_rows"], 64)


if __name__ == "__main__":
    unittest.main()
