#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_ia_ol_fallback_evidence.py — ia_ol_fallback_evidence.py kapısı.

5 IA kapsam-dışı kaynağın fallback kanıtını AĞSIZ ve deterministik doğrular:
ia_ol_fallback_evidence.collect_evidence(offline=True) mock router'ıyla
verify_delivery._archive_with_fallback zincirini (IA → HT → LoC → OL → GB)
koşar; beklenen V5w durumu — Xunzi → hathitrust, diğer 4 → loc (LoC katalog
kaydı), TÜMÜ PASS — bozulursa test FAIL (fail-closed). Ayrıca kaynak
anahtarları/ht_ids varlığını ve offline determinizmi kapılar. stdlib unittest
— ek bağımlılık yok.
"""
import pathlib
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import ia_ol_fallback_evidence as ev  # noqa: E402
import verify_delivery as vd  # noqa: E402


class TestOfflineEvidence(unittest.TestCase):
    def test_all_five_pass_offline(self):
        results = ev.collect_evidence(offline=True)
        self.assertEqual({r["key"] for r in results},
                         set(ev.IA_OUT_OF_SCOPE))
        for r in results:
            self.assertEqual(r["verdict"], "PASS",
                             f"{r['key']} offline'ta PASS olmalı: {r['detail']}")

    def test_sources_match_v5w(self):
        """V5w: Xunzi → hathitrust; Fine/Lagrée/Millican/Schmitt → loc (LoC)."""
        results = {r["key"]: r for r in ev.collect_evidence(offline=True)}
        for key in ev.LOC_SOURCES:
            self.assertEqual(results[key]["source"], "loc",
                             f"{key} LoC katalog kaynağı olmalı")
        self.assertEqual(results[ev.HT_SOURCE]["source"], "hathitrust",
                         "Xunzi HT katalog kaydıyla eşleşmeli")

    def test_evidence_shows_fallback_chain(self):
        """Detay zinciri belgelemeli: IA kapsam dışı + HT kayıt yok + LoC yanıtı."""
        results = {r["key"]: r for r in ev.collect_evidence(offline=True)}
        for key in ev.LOC_SOURCES:
            self.assertIn("Internet Archive", results[key]["detail"])
            self.assertIn("LoC", results[key]["detail"])
        x = results[ev.HT_SOURCE]
        self.assertIn("HathiTrust", x["detail"])
        self.assertIn("Xunzi", x["detail"])

    def test_offline_deterministic(self):
        a = ev.collect_evidence(offline=True)
        b = ev.collect_evidence(offline=True)
        self.assertEqual(a, b)

    def test_missing_key_raises(self):
        with self.assertRaises(KeyError):
            ev.collect_evidence(["Nope 9999"], offline=True)

    def test_subset_keys(self):
        results = ev.collect_evidence(["Fine 2012", "Xunzi Knoblock"],
                                      offline=True)
        self.assertEqual({r["key"] for r in results},
                         {"Fine 2012", "Xunzi Knoblock"})
        self.assertTrue(all(r["verdict"] == "PASS" for r in results))


class TestCoverage(unittest.TestCase):
    """5 kaynak REFERENCE_ARCHIVE'de ve ht_ids ile tanımlı — düşerse FAIL."""

    def test_five_keys_present_with_ht_ids(self):
        by_key = {r["key"]: r for r in vd.REFERENCE_ARCHIVE}
        for key in ev.IA_OUT_OF_SCOPE:
            self.assertIn(key, by_key, f"{key} arşiv listesinde yok")
            self.assertTrue(by_key[key].get("ht_ids"),
                            f"{key} ht_ids içermeli")

    def test_queries_target_specific_books(self):
        by_key = {r["key"]: r for r in vd.REFERENCE_ARCHIVE}
        expect = {
            "Fine 2012": "Metaphysical Grounding",
            "Lagree 1994": "Lipse",
            "Millican 2002": "Hume",
            "Schmitt 1972": "Cicero",
            "Xunzi Knoblock": "Xunzi",
        }
        for key, frag in expect.items():
            self.assertIn(frag.lower(), by_key[key]["query"].lower(),
                          f"{key} sorgusu {frag} içermeli")


if __name__ == "__main__":
    unittest.main()
