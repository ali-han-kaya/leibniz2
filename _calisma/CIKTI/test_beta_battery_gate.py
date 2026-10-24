#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_beta_battery_gate.py — `refs-index.json` artifact kapısı (Faz 0).

Sözleşme `docs/AZURE_SEARCH_REFS_DESIGN.md` §3-4'te tanımlıdır:
üretici (`gen_refs_index.py`) artifact'ı yazar, kapı artifact'ın **var**,
**şemaya uygun** ve **bozuk veriyi geçirmez** olduğunu doğrular. Ağ yoktur;
kapı üreticiyi çağırmaz (üretimi tetikleyip kırığı gizlemez).

Not: Bu dosya daha önce tanımsız adlar (`plugin_dir`, `base_dir`) içeren,
import bile edilemeyen bir gövdeyle duruyordu; aşağıdaki sözleşme dokümandaki
TDD döngüsünün (kırmızı → yeşil → geri dönüş) ölçülebilir hâlidir.
"""

import datetime
import importlib.util
import json
import pathlib
import re
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
ARTIFACT = HERE / "refs-index.json"
GENERATOR = REPO_ROOT / "gen_refs_index.py"

REQUIRED_KEYS = {"generated_at", "refs", "source"}

# RFC 3339 / ISO-8601 UTC, `Z` eki (doküman §3).
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def load_index(path=ARTIFACT):
    """Kapının okuma adımı: yokluk ve bozuk JSON fail-closed'dır."""
    path = pathlib.Path(path)
    if not path.is_file():
        raise AssertionError("refs-index.json yok: %s" % path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError("refs-index.json bozuk JSON: %s" % exc)
    if not isinstance(data, dict):
        raise AssertionError("refs-index.json kökü nesne değil: %r"
                             % type(data).__name__)
    missing = REQUIRED_KEYS - set(data)
    if missing:
        raise AssertionError("refs-index.json eksik anahtar(lar): %s"
                             % ", ".join(sorted(missing)))
    if not isinstance(data["refs"], list):
        raise AssertionError("refs bir liste değil: %r" % type(data["refs"]).__name__)
    if not isinstance(data["source"], str) or not data["source"].strip():
        raise AssertionError("source boş/metin değil: %r" % (data["source"],))
    if not isinstance(data["generated_at"], str) \
            or not _TS_RE.match(data["generated_at"]):
        raise AssertionError("generated_at RFC 3339 UTC (Z) değil: %r"
                             % (data["generated_at"],))
    return data


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_refs_index", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRefsIndexArtifact(unittest.TestCase):
    """Commit'li artifact sözleşmeye uyar (yeşil dal)."""

    def test_artifact_matches_documented_schema(self):
        data = load_index()
        self.assertEqual(set(data), REQUIRED_KEYS,
                         "anahtar kümesi dokümandaki şema ile birebir olmalı")
        self.assertEqual(data["source"], "azure-search")
        # Faz 0'da `refs` bilinçli olarak boş olabilir; kapı doluluk KOŞMAZ.
        for i, ref in enumerate(data["refs"]):
            self.assertIsInstance(ref, dict, "refs[%d] nesne değil" % i)

    def test_generated_at_is_parseable_utc(self):
        data = load_index()
        parsed = datetime.datetime.fromisoformat(
            data["generated_at"].replace("Z", "+00:00"))
        self.assertEqual(parsed.utcoffset(), datetime.timedelta(0))


class TestRefsIndexGateIsFailClosed(unittest.TestCase):
    """Kırmızı dal: yokluk, bozuk JSON ve eksik anahtar PASS vermez."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = pathlib.Path(self.tmp.name) / "refs-index.json"

    def test_missing_artifact_is_rejected(self):
        with self.assertRaises(AssertionError) as ctx:
            load_index(self.path)
        self.assertIn("yok", str(ctx.exception))

    def test_broken_json_is_rejected(self):
        self.path.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(AssertionError) as ctx:
            load_index(self.path)
        self.assertIn("bozuk JSON", str(ctx.exception))

    def test_missing_refs_key_is_rejected(self):
        self.path.write_text(json.dumps(
            {"generated_at": "2026-10-06T10:19:06.396502Z",
             "source": "azure-search"}), encoding="utf-8")
        with self.assertRaises(AssertionError) as ctx:
            load_index(self.path)
        self.assertIn("refs", str(ctx.exception))

    def test_non_list_refs_is_rejected(self):
        self.path.write_text(json.dumps(
            {"generated_at": "2026-10-06T10:19:06.396502Z",
             "refs": {}, "source": "azure-search"}), encoding="utf-8")
        with self.assertRaises(AssertionError):
            load_index(self.path)

    def test_naive_timestamp_is_rejected(self):
        self.path.write_text(json.dumps(
            {"generated_at": "2026-10-06T10:19:06",
             "refs": [], "source": "azure-search"}), encoding="utf-8")
        with self.assertRaises(AssertionError):
            load_index(self.path)


class TestGeneratorContract(unittest.TestCase):
    """Üretici ile kapı aynı anahtar kümesini paylaşır (tek kaynak)."""

    def test_generator_output_passes_gate(self):
        gen = _load_generator()
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "refs-index.json"
            gen.gen(str(out))
            data = load_index(out)
        self.assertEqual(set(data), REQUIRED_KEYS)
        self.assertEqual(data["source"], "azure-search")


if __name__ == "__main__":
    sys.exit(unittest.main())
