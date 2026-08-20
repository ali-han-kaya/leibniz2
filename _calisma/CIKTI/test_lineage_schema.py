#!/usr/bin/env python3
"""test_lineage_schema.py — K17 lineage şema doğrulaması regresyon kapısı.

Kapsanan senaryolar:
  Geçerli: tam şema, minimum geçerli, commit=null, tek current
  Geçersiz: eksik üst düzey alan, boş file, boş path_in_repo, boş generations,
    nesil dict değil, eksik note/hash/commit/current, hash formatı (kısa,
    uzun, büyük harf, boş), commit tipi (int, bool), current bool değil,
    current yok, birden fazla current

stdlib unittest — ek bağımlılık yok.
"""
import os
import pathlib
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery  # noqa: E402


def _make_lineage(*gens, file="test.zip", path_in_repo="test.zip"):
    """Geçerli bir lineage dict'i oluşturur (üst düzey alanlar + verilen nesiller)."""
    return {"file": file, "path_in_repo": path_in_repo, "generations": list(gens)}


def _make_gen(note="test", commit=None, current=False):
    """Geçerli bir nesil dict'i oluşturur (64-char hex hash)."""
    return {
        "note": note,
        "hash": "a" * 64,
        "commit": commit,
        "current": current,
    }


class TestValidSchemas(unittest.TestCase):
    """Geçerli şemalar K17'yi PASS etmeli."""

    def _validate(self, lineage):
        findings = []
        def add(pri, cid, check, issue, evidence=""):
            findings.append({"id": cid, "priority": pri, "issue": issue})
        ok, errors = verify_delivery.validate_lineage_schema(lineage, add)
        return ok, errors, findings

    def test_valid_full(self):
        ok, errors, findings = self._validate(_make_lineage(
            _make_gen(note="pre-git", current=False),
            _make_gen(note="git init", commit="abc1234", current=True),
        ))
        self.assertTrue(ok)
        self.assertEqual(errors, [])
        self.assertEqual(findings, [])

    def test_valid_minimum(self):
        ok, errors, _ = self._validate(_make_lineage(
            _make_gen(current=True),
        ))
        self.assertTrue(ok)

    def test_valid_many_generations(self):
        gens = [_make_gen(note=f"gen-{i}", current=(i == 9)) for i in range(10)]
        ok, errors, _ = self._validate(_make_lineage(*gens))
        self.assertTrue(ok)

    def test_valid_commit_null(self):
        ok, errors, _ = self._validate(_make_lineage(
            _make_gen(note="pre-git", commit=None, current=True),
        ))
        self.assertTrue(ok)

    def test_valid_commit_string(self):
        ok, errors, _ = self._validate(_make_lineage(
            _make_gen(commit="a1b2c3d", current=True),
        ))
        self.assertTrue(ok)


class TestInvalidTopLevel(unittest.TestCase):
    """Üst düzey alan hataları P1 ile raporlanmalı."""

    def _validate(self, lineage):
        findings = []
        def add(pri, cid, check, issue, evidence=""):
            findings.append({"id": cid, "priority": pri, "issue": issue})
        ok, errors = verify_delivery.validate_lineage_schema(lineage, add)
        return ok, errors, findings

    def test_missing_file(self):
        ok, errors, findings = self._validate(
            {"path_in_repo": "x.zip", "generations": [_make_gen(current=True)]})
        self.assertFalse(ok)
        self.assertTrue(any("file" in e for e in errors))
        self.assertTrue(any(f["id"] == "K17-LINEAGE" for f in findings))

    def test_missing_path_in_repo(self):
        ok, errors, findings = self._validate(
            {"file": "x.zip", "generations": [_make_gen(current=True)]})
        self.assertFalse(ok)
        self.assertTrue(any("path_in_repo" in e for e in errors))

    def test_missing_generations(self):
        ok, errors, findings = self._validate(
            {"file": "x.zip", "path_in_repo": "x.zip"})
        self.assertFalse(ok)
        self.assertTrue(any("generations" in e for e in errors))

    def test_empty_file(self):
        ok, errors, _ = self._validate(
            {"file": "", "path_in_repo": "x.zip", "generations": [_make_gen(current=True)]})
        self.assertFalse(ok)

    def test_empty_path_in_repo(self):
        ok, errors, _ = self._validate(
            {"file": "x.zip", "path_in_repo": "", "generations": [_make_gen(current=True)]})
        self.assertFalse(ok)

    def test_empty_generations(self):
        ok, errors, _ = self._validate(
            {"file": "x.zip", "path_in_repo": "x.zip", "generations": []})
        self.assertFalse(ok)

    def test_file_not_string(self):
        ok, errors, _ = self._validate(
            {"file": 123, "path_in_repo": "x.zip", "generations": [_make_gen(current=True)]})
        self.assertFalse(ok)

    def test_generations_not_list(self):
        ok, errors, _ = self._validate(
            {"file": "x.zip", "path_in_repo": "x.zip", "generations": "not-a-list"})
        self.assertFalse(ok)


class TestInvalidGeneration(unittest.TestCase):
    """Nesil düzeyindeki hatalar K17-LINEAGE ile raporlanmalı."""

    def _validate(self, lineage):
        findings = []
        def add(pri, cid, check, issue, evidence=""):
            findings.append({"id": cid, "priority": pri, "issue": issue})
        ok, errors = verify_delivery.validate_lineage_schema(lineage, add)
        return ok, errors, findings

    def test_generation_not_dict(self):
        ok, errors, findings = self._validate(
            _make_lineage("not-a-dict"))
        self.assertFalse(ok)
        self.assertTrue(any("dict değil" in e for e in errors))

    def test_missing_note(self):
        gen = {"hash": "a" * 64, "commit": None, "current": True}
        ok, errors, _ = self._validate(_make_lineage(gen))
        self.assertFalse(ok)
        self.assertTrue(any("note" in e for e in errors))

    def test_missing_hash(self):
        gen = {"note": "test", "commit": None, "current": True}
        ok, errors, _ = self._validate(_make_lineage(gen))
        self.assertFalse(ok)
        self.assertTrue(any("hash" in e for e in errors))

    def test_missing_commit(self):
        gen = {"note": "test", "hash": "a" * 64, "current": True}
        ok, errors, _ = self._validate(_make_lineage(gen))
        self.assertFalse(ok)
        self.assertTrue(any("commit" in e for e in errors))

    def test_missing_current(self):
        gen = {"note": "test", "hash": "a" * 64, "commit": None}
        ok, errors, _ = self._validate(_make_lineage(gen))
        self.assertFalse(ok)
        self.assertTrue(any("current" in e for e in errors))


class TestHashFormat(unittest.TestCase):
    """Hash formatı hataları K17-LINEAGE ile raporlanmalı."""

    def _validate_with_hash(self, h):
        findings = []
        def add(pri, cid, check, issue, evidence=""):
            findings.append({"id": cid, "priority": pri, "issue": issue})
        gen = {"note": "test", "hash": h, "commit": None, "current": True}
        lineage = {"file": "x.zip", "path_in_repo": "x.zip", "generations": [gen]}
        ok, errors = verify_delivery.validate_lineage_schema(lineage, add)
        return ok, errors, findings

    def test_hash_too_short(self):
        ok, errors, _ = self._validate_with_hash("abc123")
        self.assertFalse(ok)
        self.assertTrue(any("hash" in e for e in errors))

    def test_hash_too_long(self):
        ok, errors, _ = self._validate_with_hash("a" * 65)
        self.assertFalse(ok)

    def test_hash_uppercase(self):
        ok, errors, _ = self._validate_with_hash("A" * 64)
        self.assertFalse(ok)

    def test_hash_empty(self):
        ok, errors, _ = self._validate_with_hash("")
        self.assertFalse(ok)

    def test_hash_not_string(self):
        ok, errors, _ = self._validate_with_hash(12345)
        self.assertFalse(ok)


class TestCurrentField(unittest.TestCase):
    """current alanı bool olmalı ve tam olarak bir tane true olmalı."""

    def _validate(self, lineage):
        findings = []
        def add(pri, cid, check, issue, evidence=""):
            findings.append({"id": cid, "priority": pri, "issue": issue})
        ok, errors = verify_delivery.validate_lineage_schema(lineage, add)
        return ok, errors, findings

    def test_current_not_bool(self):
        gen = {"note": "test", "hash": "a" * 64, "commit": None, "current": "yes"}
        ok, errors, _ = self._validate(_make_lineage(gen))
        self.assertFalse(ok)
        self.assertTrue(any("bool" in e for e in errors))

    def test_current_int(self):
        gen = {"note": "test", "hash": "a" * 64, "commit": None, "current": 1}
        ok, errors, _ = self._validate(_make_lineage(gen))
        self.assertFalse(ok)

    def test_no_current(self):
        ok, errors, _ = self._validate(_make_lineage(
            _make_gen(current=False),
            _make_gen(commit="abc", current=False),
        ))
        self.assertFalse(ok)
        self.assertTrue(any("current=true nesli yok" in e for e in errors))

    def test_two_currents(self):
        ok, errors, _ = self._validate(_make_lineage(
            _make_gen(note="a", current=True),
            _make_gen(note="b", commit="abc", current=True),
        ))
        self.assertFalse(ok)
        self.assertTrue(any("2 tane" in e for e in errors))

    def test_three_currents(self):
        ok, errors, _ = self._validate(_make_lineage(
            _make_gen(note="a", current=True),
            _make_gen(note="b", current=True),
            _make_gen(note="c", current=True),
        ))
        self.assertFalse(ok)
        self.assertTrue(any("3 tane" in e for e in errors))


class TestCommitField(unittest.TestCase):
    """commit alanı null veya string olmalı."""

    def _validate_with_commit(self, c):
        findings = []
        def add(pri, cid, check, issue, evidence=""):
            findings.append({"id": cid, "priority": pri, "issue": issue})
        gen = {"note": "test", "hash": "a" * 64, "commit": c, "current": True}
        lineage = {"file": "x.zip", "path_in_repo": "x.zip", "generations": [gen]}
        ok, errors = verify_delivery.validate_lineage_schema(lineage, add)
        return ok, errors, findings

    def test_commit_int(self):
        ok, errors, _ = self._validate_with_commit(123)
        self.assertFalse(ok)

    def test_commit_bool(self):
        ok, errors, _ = self._validate_with_commit(True)
        self.assertFalse(ok)

    def test_commit_list(self):
        ok, errors, _ = self._validate_with_commit(["abc"])
        self.assertFalse(ok)


class TestMultipleErrors(unittest.TestCase):
    """Birden fazla hata varsa hepsi raporlanmalı."""

    def test_three_errors(self):
        findings = []
        def add(pri, cid, check, issue, evidence=""):
            findings.append({"id": cid, "priority": pri, "issue": issue})
        lineage = {"file": "", "generations": []}  # path_in_repo eksik, file boş, generations boş
        ok, errors = verify_delivery.validate_lineage_schema(lineage, add)
        self.assertFalse(ok)
        self.assertGreaterEqual(len(errors), 2)


if __name__ == "__main__":
    unittest.main()
