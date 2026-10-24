#!/usr/bin/env python3
"""test_preview_contract.py — preview_server ↔ dashboard-next tel sözleşmesi.

Tek kaynak: preview_contract.schema.json. Bu dosya dört kapı tanımlar:

  1. Şema geçerli (Draft 2020-12) ve üreteç çıktısı commit'li TS dosyasıyla
     birebir (sürüklenme yok).
  2. Üretici alan kümeleri şemayla eşit: HISTORY_DASHBOARD_KEYS == HistoryRow
     alanları; Latest alanları LATEST'te yayınlanır. Bir alan silinir ya da
     yeniden adlanırsa burada düşer (eksik alan runtime'da hata vermez, pano
     \"—\" basar — bu yüzden statik kapı).
  3. Üretici çıktısı şemaya uyar: sabit fixture HER ortamda koşar; yerel
     history.jsonl varsa gerçek satırları da doğrular; /api/trend gövdesi ve
     /api/latest snapshot'ı şemaya uyar.
  4. Şema gevşerse kapı görünür biçimde kırılır (negatif iddialar).

Koşum: python3 -m unittest _calisma.CIKTI.test_preview_contract -v
"""
import copy
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import jsonschema  # noqa: E402  (requirements-z3.txt'te pinli)
import gen_preview_contract as gpc  # noqa: E402
import preview_server as ps  # noqa: E402

SCHEMA = gpc.load_schema()
DEFS = SCHEMA["$defs"]

# Gerçek history.jsonl satırının şekli (100 satırlık canlı örnekte her alan
# her satırda dolu ve tipleri aşağıdaki gibi). Sabit fixture bunu taklit eder.
FIXTURE_RAW = {
    "ts": "2026-10-17T09:00:00Z", "verdict": "PASS", "p0": 0, "p1": 0,
    "duration_s": 41.2, "budget_usd": 1.08, "budget_limit": 30.0,
    "budget_method": "both", "refs_verified": 61, "refs_total": 64,
    "refs_mismatch": 0, "refs_by_source": {"crossref": 61},
    "hook_env": {"python": "3.9.6"}, "z3_passed": 12, "z3_failed": 0,
    "z3_total": 12, "lean_ok": True, "lean_detail": "derlendi",
    "cli_override_count": 0,
    # Projeksiyonda OLMAYAN alanlar: düşmeli, şemaya girmemeli.
    "raw_sha256": "a" * 64, "stdout": "SONUÇ: PASS",
}

FIXTURE_LATEST = {
    "verdict": "PASS", "ts": "2026-10-17T09:00:00Z", "p0": 0, "p1": 0,
    "stripped_sha256": "b" * 64, "z3_passed": 12, "z3_total": 12,
    "z3_failed": 0, "budget_usd": 1.08, "budget_limit": 30.0,
}


def _validator(def_name):
    """Tek bir $defs girdisini doğrulayan şema (kökte $defs taşır, $ref çözülür)."""
    root = {"$ref": f"#/$defs/{def_name}", "$defs": DEFS}
    return jsonschema.Draft202012Validator(root)


class _FakeHandler:
    """Handler'ın _send çağrılarını yakalayan sahte istek nesnesi."""

    def __init__(self, path):
        self.path = path
        self.sent = []

    def _send(self, status, body, content_type="", extra_headers=None):
        self.sent.append((status, body))


class SchemaAndGeneratorTests(unittest.TestCase):
    """Kapı 1: şema geçerli, üreteç deterministik, TS dosyası sürüklenmemiş."""

    def test_schema_is_valid_draft_2020_12(self):
        jsonschema.Draft202012Validator.check_schema(SCHEMA)

    def test_generated_ts_matches_committed_file(self):
        with open(gpc.OUT_PATH, encoding="utf-8") as f:
            committed = f.read()
        self.assertEqual(
            committed, gpc.render(SCHEMA),
            "lib/preview-contract.generated.ts şemayla uyuşmuyor — "
            "`python3 _calisma/CIKTI/gen_preview_contract.py --write` çalıştırın")

    def test_generator_fails_closed_on_unsupported_keyword(self):
        bad = copy.deepcopy(SCHEMA)
        bad["$defs"]["HistoryRow"]["properties"]["p0"]["minimum"] = 0
        with self.assertRaisesRegex(gpc.ContractError, "desteklenmeyen"):
            gpc.render(bad)

    def test_generator_rejects_additional_properties(self):
        # Index imzası üretilmez: additionalProperties kaldırılmadan geçmez.
        bad = copy.deepcopy(SCHEMA)
        bad["$defs"]["Latest"]["additionalProperties"] = True
        with self.assertRaisesRegex(gpc.ContractError, "additionalProperties"):
            gpc.render(bad)

    def test_generator_rejects_unknown_ref(self):
        bad = copy.deepcopy(SCHEMA)
        bad["$defs"]["TrendResponse"]["properties"]["history"]["items"] = {
            "$ref": "#/definitions/Nope"}
        with self.assertRaisesRegex(gpc.ContractError, "referans"):
            gpc.render(bad)


class ProducerFieldSetTests(unittest.TestCase):
    """Kapı 2: üretici alan kümeleri şemayla eşit."""

    def test_history_projection_keys_equal_history_row_fields(self):
        schema_keys = set(DEFS["HistoryRow"]["properties"])
        self.assertEqual(set(ps.HISTORY_DASHBOARD_KEYS), schema_keys,
                         "HISTORY_DASHBOARD_KEYS ile HistoryRow alanları ayrıştı")

    def test_latest_fields_are_published_by_latest_snapshot(self):
        latest_fields = set(DEFS["Latest"]["properties"])
        self.assertTrue(latest_fields <= set(ps.LATEST),
                        f"LATEST'te olmayan Latest alanları: "
                        f"{sorted(latest_fields - set(ps.LATEST))}")


class ProducerConformanceTests(unittest.TestCase):
    """Kapı 3: gerçek üretici çıktısı şemaya uyar."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_history = ps.HISTORY_PATH
        self._old_refs = ps.REFS_TREND_PATH
        self.addCleanup(setattr, ps, "HISTORY_PATH", self._old_history)
        self.addCleanup(setattr, ps, "REFS_TREND_PATH", self._old_refs)

    def _write_history(self, rows):
        path = os.path.join(self._tmp.name, "history.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path

    def test_fixture_projection_has_every_dashboard_key(self):
        projected = ps._project_history_record(FIXTURE_RAW)
        self.assertEqual(set(projected), set(ps.HISTORY_DASHBOARD_KEYS))
        self.assertNotIn("raw_sha256", projected)
        self.assertNotIn("stdout", projected)

    def test_fixture_projection_validates_history_row(self):
        projected = ps._project_history_record(FIXTURE_RAW)
        _validator("HistoryRow").validate(projected)

    def test_real_history_rows_validate_when_present(self):
        path = os.path.join(ps.DEFAULT_PREVIEW_DIR, "history.jsonl")
        if not os.path.isfile(path):
            self.skipTest(f"gerçek history yok ({path}); sabit fixture kapısı koştu")
        validator = _validator("HistoryRow")
        count = 0
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                with self.subTest(line=line_no):
                    validator.validate(ps._project_history_record(record))
                count += 1
        self.assertGreater(count, 0, "history.jsonl var ama satır yok")

    def test_trend_body_validates_trend_response(self):
        ps.HISTORY_PATH = self._write_history(
            [dict(FIXTURE_RAW, ts=f"2026-10-17T0{i}:00:00Z") for i in range(4)])
        ps.REFS_TREND_PATH = None
        handler = _FakeHandler("/api/trend?limit=2")
        ps.Handler.serve_trend(handler)
        status, body = handler.sent[0]
        self.assertEqual(status, 200)
        payload = json.loads(body)
        _validator("TrendResponse").validate(payload)
        # /api/trend ignores limit query param by design (full-list contract)
        # Returns all history records; consumers window client-side
        self.assertEqual(len(payload["history"]), 4)

    def test_latest_snapshot_validates_latest(self):
        with mock.patch.dict(ps.LATEST, FIXTURE_LATEST):
            snapshot = json.loads(json.dumps(ps.snapshot_dict()))
        _validator("Latest").validate(snapshot)


class NegativeContractTests(unittest.TestCase):
    """Kapı 4: şema gerçekten ayrım yapıyor (yanlış tipler düşer)."""

    def test_string_p0_is_rejected(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validator("HistoryRow").validate({"p0": "3"})

    def test_lean_ok_as_string_is_rejected(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validator("HistoryRow").validate({"lean_ok": "true"})

    def test_history_must_be_array(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validator("TrendResponse").validate({"history": {"ts": "x"}})

    def test_missing_history_is_rejected(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validator("TrendResponse").validate({"limit": 3})





def _extract_ts_latest_fields():
    """TypeScript Latest tipinden alan isimlerini çıkar."""
    import re
    with open(gpc.OUT_PATH, encoding="utf-8") as f:
        tsc = f.read()
    match = re.search(r"export type Latest = \{([^}]+)\}", tsc)
    if not match:
        return set()
    body = match.group(1)
    fields = set()
    for line in body.splitlines():
        m = re.match(r"\s*([a-zA-Z_][a-zA-Z0-9_]*)?\??\s*:\s*", line)
        if m:
            fn = m.group(1)
            if fn:
                fields.add(fn)
    return fields
#!/usr/bin/env python3
"""test_preview_contract.py — preview_server ↔ dashboard-next tel sözleşmesi.

Tek kaynak: preview_contract.schema.json. Bu dosya dört kapı tanımlar:

  1. Şema geçerli (Draft 2020-12) ve üreteç çıktısı commit'li TS dosyasıyla
     birebir (sürüklenme yok).
  2. Üretici alan kümeleri şemayla eşit: HISTORY_DASHBOARD_KEYS == HistoryRow
     alanları; Latest alanları LATEST'te yayınlanır. Bir alan silinir ya da
     yeniden adlanırsa burada düşer (eksik alan runtime'da hata vermez, pano
     \"—\" basar — bu yüzden statik kapı).
  3. Üretici çıktısı şemaya uyar: sabit fixture HER ortamda koşar; yerel
     history.jsonl varsa gerçek satırları da doğrular; /api/trend gövdesi ve
     /api/latest snapshot'ı şemaya uyar.
  4. Şema gevşerse kapı görünür biçimde kırılır (negatif iddialar).

Koşum: python3 -m unittest _calisma.CIKTI.test_preview_contract -v
"""
import copy
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import jsonschema  # noqa: E402  (requirements-z3.txt'te pinli)
import gen_preview_contract as gpc  # noqa: E402
import preview_server as ps  # noqa: E402

SCHEMA = gpc.load_schema()
DEFS = SCHEMA["$defs"]

# Gerçek history.jsonl satırının şekli (100 satırlık canlı örnekte her alan
# her satırda dolu ve tipleri aşağıdaki gibi). Sabit fixture bunu taklit eder.
FIXTURE_RAW = {
    "ts": "2026-10-17T09:00:00Z", "verdict": "PASS", "p0": 0, "p1": 0,
    "duration_s": 41.2, "budget_usd": 1.08, "budget_limit": 30.0,
    "budget_method": "both", "refs_verified": 61, "refs_total": 64,
    "refs_mismatch": 0, "refs_by_source": {"crossref": 61},
    "hook_env": {"python": "3.9.6"}, "z3_passed": 12, "z3_failed": 0,
    "z3_total": 12, "lean_ok": True, "lean_detail": "derlendi",
    "cli_override_count": 0,
    # Projeksiyonda OLMAYAN alanlar: düşmeli, şemaya girmemeli.
    "raw_sha256": "a" * 64, "stdout": "SONUÇ: PASS",
}

FIXTURE_LATEST = {
    "verdict": "PASS", "ts": "2026-10-17T09:00:00Z", "p0": 0, "p1": 0,
    "stripped_sha256": "b" * 64, "z3_passed": 12, "z3_total": 12,
    "z3_failed": 0, "budget_usd": 1.08, "budget_limit": 30.0,
}


def _validator(def_name):
    """Tek bir $defs girdisini doğrulayan şema (kökte $defs taşır, $ref çözülür)."""
    root = {"$ref": f"#/$defs/{def_name}", "$defs": DEFS}
    return jsonschema.Draft202012Validator(root)


class _FakeHandler:
    """Handler'ın _send çağrılarını yakalayan sahte istek nesnesi."""

    def __init__(self, path):
        self.path = path
        self.sent = []

    def _send(self, status, body, content_type="", extra_headers=None):
        self.sent.append((status, body))


class SchemaAndGeneratorTests(unittest.TestCase):
    """Kapı 1: şema geçerli, üreteç deterministik, TS dosyası sürüklenmemiş."""

    def test_schema_is_valid_draft_2020_12(self):
        jsonschema.Draft202012Validator.check_schema(SCHEMA)

    def test_generated_ts_matches_committed_file(self):
        with open(gpc.OUT_PATH, encoding="utf-8") as f:
            committed = f.read()
        self.assertEqual(
            committed, gpc.render(SCHEMA),
            "lib/preview-contract.generated.ts şemayla uyuşmuyor — "
            "`python3 _calisma/CIKTI/gen_preview_contract.py --write` çalıştırın")

    def test_generator_fails_closed_on_unsupported_keyword(self):
        bad = copy.deepcopy(SCHEMA)
        bad["$defs"]["HistoryRow"]["properties"]["p0"]["minimum"] = 0
        with self.assertRaisesRegex(gpc.ContractError, "desteklenmeyen"):
            gpc.render(bad)

    def test_generator_rejects_additional_properties(self):
        # Index imzası üretilmez: additionalProperties kaldırılmadan geçmez.
        bad = copy.deepcopy(SCHEMA)
        bad["$defs"]["Latest"]["additionalProperties"] = True
        with self.assertRaisesRegex(gpc.ContractError, "additionalProperties"):
            gpc.render(bad)

    def test_generator_rejects_unknown_ref(self):
        bad = copy.deepcopy(SCHEMA)
        bad["$defs"]["TrendResponse"]["properties"]["history"]["items"] = {
            "$ref": "#/definitions/Nope"}
        with self.assertRaisesRegex(gpc.ContractError, "referans"):
            gpc.render(bad)


class ProducerFieldSetTests(unittest.TestCase):
    """Kapı 2: üretici alan kümeleri şemayla eşit."""

    def test_history_projection_keys_equal_history_row_fields(self):
        schema_keys = set(DEFS["HistoryRow"]["properties"])
        self.assertEqual(set(ps.HISTORY_DASHBOARD_KEYS), schema_keys,
                         "HISTORY_DASHBOARD_KEYS ile HistoryRow alanları ayrıştı")

    def test_latest_fields_are_published_by_latest_snapshot(self):
        latest_fields = set(DEFS["Latest"]["properties"])
        self.assertTrue(latest_fields <= set(ps.LATEST),
                        f"LATEST'te olmayan Latest alanları: "
                        f"{sorted(latest_fields - set(ps.LATEST))}")


class ProducerConformanceTests(unittest.TestCase):
    """Kapı 3: gerçek üretici çıktısı şemaya uyar."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_history = ps.HISTORY_PATH
        self._old_refs = ps.REFS_TREND_PATH
        self.addCleanup(setattr, ps, "HISTORY_PATH", self._old_history)
        self.addCleanup(setattr, ps, "REFS_TREND_PATH", self._old_refs)

    def _write_history(self, rows):
        path = os.path.join(self._tmp.name, "history.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path

    def test_fixture_projection_has_every_dashboard_key(self):
        projected = ps._project_history_record(FIXTURE_RAW)
        self.assertEqual(set(projected), set(ps.HISTORY_DASHBOARD_KEYS))
        self.assertNotIn("raw_sha256", projected)
        self.assertNotIn("stdout", projected)

    def test_fixture_projection_validates_history_row(self):
        projected = ps._project_history_record(FIXTURE_RAW)
        _validator("HistoryRow").validate(projected)

    def test_real_history_rows_validate_when_present(self):
        path = os.path.join(ps.DEFAULT_PREVIEW_DIR, "history.jsonl")
        if not os.path.isfile(path):
            self.skipTest(f"gerçek history yok ({path}); sabit fixture kapısı koştu")
        validator = _validator("HistoryRow")
        count = 0
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                with self.subTest(line=line_no):
                    validator.validate(ps._project_history_record(record))
                count += 1
        self.assertGreater(count, 0, "history.jsonl var ama satır yok")

    def test_trend_body_validates_trend_response(self):
        ps.HISTORY_PATH = self._write_history(
            [dict(FIXTURE_RAW, ts=f"2026-10-17T0{i}:00:00Z") for i in range(4)])
        ps.REFS_TREND_PATH = None
        handler = _FakeHandler("/api/trend?limit=2")
        ps.Handler.serve_trend(handler)
        status, body = handler.sent[0]
        self.assertEqual(status, 200)
        payload = json.loads(body)
        _validator("TrendResponse").validate(payload)
        # /api/trend ignores limit query param by design (full-list contract)
        # Returns all history records; consumers window client-side
        self.assertEqual(len(payload["history"]), 4)

    def test_latest_snapshot_validates_latest(self):
        with mock.patch.dict(ps.LATEST, FIXTURE_LATEST):
            snapshot = json.loads(json.dumps(ps.snapshot_dict()))
        _validator("Latest").validate(snapshot)


class NegativeContractTests(unittest.TestCase):
    """Kapı 4: şema gerçekten ayrım yapıyor (yanlış tipler düşer)."""

    def test_string_p0_is_rejected(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validator("HistoryRow").validate({"p0": "3"})

    def test_lean_ok_as_string_is_rejected(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validator("HistoryRow").validate({"lean_ok": "true"})

    def test_history_must_be_array(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validator("TrendResponse").validate({"history": {"ts": "x"}})

    def test_missing_history_is_rejected(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validator("TrendResponse").validate({"limit": 3})





def _extract_ts_latest_fields():
    """TypeScript Latest tipinden alan isimlerini çıkar."""
    import re
    with open(gpc.OUT_PATH, encoding="utf-8") as f:
        tsc = f.read()
    # export type Latest = { ... } bloğundan field isimlerini regex ile çıkar
    match = re.search(r'export type Latest = \{([^}]+)\}', tsc)
    if not match:
        return set()
    body = match.group(1)
    # Her satirin baslarinda key? varsa isimleri al
    fields = set()
    for line in body.splitlines():
        m = re.match(r'\s*([a-zA-Z_][a-zA-Z0-9_]*)?\??\s*:\s*', line)
        if m:
            fn = m.group(1)
            if fn:
                fields.add(fn)
    return fields
class CrossLanguageContractTests(unittest.TestCase):
    """Kapı 5: Python ve TypeScript alan kümeleri eşleşir."""

    def test_python_latest_fields_covered_by_ts_type(self):
        """Python'un /api/latest çıktısıyla TS Latest tipi tam olarak eşleşir.

        Eğer Python yeni bir alan üretirse TS tipine eklenmezse test kırmızıya düşer,
        commit bloke olur.
        """
        python_fields = set(ps.LATEST.keys())
        ts_fields = _extract_ts_latest_fields()
        
        missing = python_fields - ts_fields
        self.assertEqual(
            len(missing),
            0,
            f"TS Latest tipinde olmayan Python LATEST alanları: {sorted(missing)}"
        )
        
        extra = ts_fields - python_fields
        self.assertEqual(
            len(extra),
            0,
            f"Latest tipinde olan ancak Python LATEST'de olmayan TS alanları: {sorted(extra)}"
        )


def _extract_ts_latest_fields():
    """TypeScript Latest tipinden alan isimlerini çıkar."""
    import re
    with open(gpc.OUT_PATH, encoding="utf-8") as f:
        tsc = f.read()
    match = re.search(r"export type Latest = \{([^}]+)\}", tsc)
    if not match:
        return set()
    body = match.group(1)
    fields = set()
    for line in body.split("\n"):
        m = re.match(r"\s*([a-zA-Z_][a-zA-Z0-9_]*)?\??\s*:\s*", line)
        if m:
            fn = m.group(1)
            if fn:
                fields.add(fn)
    return fields


class CrossLanguageContractTests(unittest.TestCase):
    """Kapı 5: Python ve TypeScript alan kümeleri eşleşir."""

    def test_python_latest_fields_covered_by_ts_type(self):
        """Python'un /api/latest çıktısıyla TS Latest tipi tam olarak eşleşir.

        Eğer Python yeni bir alan üretirse TS tipine eklenmezse test kırmızıya düşer,
        commit bloke olur.
        """
        python_fields = set(ps.LATEST.keys())
        ts_fields = _extract_ts_latest_fields()
        
        missing = python_fields - ts_fields
        self.assertEqual(
            len(missing),
            0,
            f"TS Latest tipinde olmayan Python LATEST alanları: {sorted(missing)}"
        )
        
        extra = ts_fields - python_fields
        self.assertEqual(
            len(extra),
            0,
            f"Latest tipinde olan ancak Python LATEST'de olmayan TS alanları: {sorted(extra)}"
        )
if __name__ == "__main__":
    unittest.main()
