#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_verify_refs.py — verify_delivery.py referans fallback mantığı kapısı.

openlibrary_fallback_check ağ çağrısını _http_json üzerinden yapar; bu test
_http_json'u mock'layarak eşleşme mantığını (title + creator, aksan-duyarsız)
ağsız ve deterministik doğrular. Ayrıca _fold'un aksan katlama davranışını
test eder. stdlib unittest — ek bağımlılık yok.
"""
import pathlib
import sys
import unittest
from unittest import mock

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery as vd  # noqa: E402

# (title, author_name, year, publisher) listesi → OpenLibrary docs biçimi.
def _docs(*entries):
    return {"docs": [
        {"title": t, "author_name": a, "first_publish_year": y,
         "publisher": p}
        for (t, a, y, p) in entries
    ]}


class TestFold(unittest.TestCase):
    def test_accent_fold(self):
        self.assertEqual(vd._fold("Lagrée"), "lagree")
        self.assertEqual(vd._fold("stoïcisme"), "stoicisme")

    def test_no_accent_unchanged(self):
        self.assertEqual(vd._fold("Metaphysical Grounding"),
                         "metaphysicalgrounding")


class TestOpenLibraryFallback(unittest.TestCase):
    def _call(self, ref, payload):
        with mock.patch.object(vd, "_http_json", return_value=payload):
            return vd.openlibrary_fallback_check(ref)

    def test_pass_title_and_creator(self):
        ref = {"key": "Fine 2012", "query": "q",
               "title_needle": "metaphysical grounding",
               "creator_needle": "correia"}
        v, d = self._call(ref, _docs(
            ("Metaphysical Grounding", ["Fabrice Correia"], 2012,
             ["Cambridge University Press"]),
        ))
        self.assertEqual(v, "PASS")
        self.assertIn("Metaphysical Grounding", d)

    def test_pass_accent_insensitive_creator(self):
        # "Lagrée" (yazar) ↔ creator_needle "lagree" — aksan farkı engel olmaz.
        ref = {"key": "Lagree 1994", "query": "q", "title_needle": "lipse",
               "creator_needle": "lagree"}
        v, d = self._call(ref, _docs(
            ("Juste Lipse et la restauration du stoïcisme",
             ["Jacqueline Lagrée"], 1994, ["J. Vrin"]),
        ))
        self.assertEqual(v, "PASS")

    def test_pass_title_only_when_no_creator(self):
        ref = {"key": "Millican 2002", "query": "q",
               "title_needle": "reading hume"}
        v, d = self._call(ref, _docs(
            ("Reading Hume on Human Understanding", ["Peter Millican"],
             2002, ["Oxford University Press"]),
        ))
        self.assertEqual(v, "PASS")

    def test_mismatch_when_no_match(self):
        ref = {"key": "X", "query": "q", "title_needle": "cicero scepticus",
               "creator_needle": "schmitt"}
        v, d = self._call(ref, _docs(
            ("Something Else", ["Other Author"], 2000, ["X"]),
        ))
        self.assertEqual(v, "MISMATCH")

    def test_unverified_when_no_docs(self):
        ref = {"key": "X", "query": "q", "title_needle": "z"}
        v, d = self._call(ref, {"docs": []})
        self.assertEqual(v, "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
