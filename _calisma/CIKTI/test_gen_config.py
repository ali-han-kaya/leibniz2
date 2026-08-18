#!/usr/bin/env python3
"""test_gen_config.py — compute_budget_ratios birim testleri (CI fail-closed).

Kapsam (istek): pay 0, tam baskınlık, eşit karışım ve clamp sınırları.
Ayrıca gerçek paket regresyon çapası + eksik anahtar davranışı.

Formül (gen_config.py compute_budget_ratios, tek kaynak):
    pay_k   = bytes_k / total_bytes
    ratio_k = clamp(round(4 / pay_k), 1, 100)     # 4 = evrensel bytes/token
    total_bytes <= 0  →  varsayılan {3, 8, 12, 20}
    bytes_k <= 0      →  100 (marjinal, token katkısı yok)

stdlib `unittest` kullanır — ek bağımlılık yok. CI'da:
    python3 -m unittest discover -s _calisma/CIKTI -p "test_gen_config.py" -v
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gen_config  # noqa: E402  (compute_budget_ratios)

KEYS = ("text", "pdf", "archive", "binary")


class ComputeBudgetRatiosTests(unittest.TestCase):
    """compute_budget_ratios — pay 0 / baskınlık / eşit karışım / clamp."""

    def _ratios(self, type_bytes, total_bytes):
        return gen_config.compute_budget_ratios(type_bytes, total_bytes)

    # ── pay 0 / toplam bayt 0 ─────────────────────────────────────────
    def test_total_bytes_zero_returns_default_ratios(self):
        # total_bytes <= 0 → early return, hesaplama yapılmaz.
        self.assertEqual(self._ratios({}, 0),
                         {"text": 3, "pdf": 8, "archive": 12, "binary": 20})

    def test_total_bytes_negative_returns_default_ratios(self):
        self.assertEqual(self._ratios({"text": 5}, -3),
                         {"text": 3, "pdf": 8, "archive": 12, "binary": 20})

    def test_zero_byte_type_gets_100(self):
        # bytes_k <= 0 → marjinal: token katkısı yok → ratio 100.
        got = self._ratios({"text": 100, "pdf": 0, "archive": 0, "binary": 0},
                           100)
        self.assertEqual(got["text"], 4)      # pay=1.0 → round(4/1)=4
        self.assertEqual(got["pdf"], 100)
        self.assertEqual(got["archive"], 100)
        self.assertEqual(got["binary"], 100)

    def test_missing_key_treated_as_zero(self):
        # type_bytes.get(k, 0) → eksik anahtar = 0 bayt = 100.
        got = self._ratios({"text": 500, "pdf": 500}, 1000)
        self.assertEqual(got, {"text": 8, "pdf": 8,
                               "archive": 100, "binary": 100})

    # ── tam baskınlık ─────────────────────────────────────────────────
    def test_full_dominance_single_type_gets_4(self):
        # Tek tip paketin tamamını kaplar: pay=1.0 → round(4/1)=4.
        got = self._ratios({"text": 1000, "pdf": 0, "archive": 0, "binary": 0},
                           1000)
        self.assertEqual(got, {"text": 4, "pdf": 100,
                               "archive": 100, "binary": 100})

    # ── eşit karışım ──────────────────────────────────────────────────
    def test_equal_mix_four_ways_gets_16(self):
        # Her tip %25: pay=0.25 → round(4/0.25)=16.
        got = self._ratios({"text": 250, "pdf": 250,
                            "archive": 250, "binary": 250}, 1000)
        self.assertEqual(got, {"text": 16, "pdf": 16,
                               "archive": 16, "binary": 16})

    def test_equal_mix_two_ways_gets_8_others_100(self):
        # text/pdf %50-%50: pay=0.5 → round(8)=8; archive/binary 0 bayt → 100.
        got = self._ratios({"text": 500, "pdf": 500,
                            "archive": 0, "binary": 0}, 1000)
        self.assertEqual(got, {"text": 8, "pdf": 8,
                               "archive": 100, "binary": 100})

    # ── clamp sınırları ───────────────────────────────────────────────
    def test_upper_clamp_small_pay_gets_100(self):
        # binary=1/1000 → pay=0.001 → 4/0.001=4000 → clamp(…, 1, 100)=100.
        got = self._ratios({"text": 999, "pdf": 0, "archive": 0, "binary": 1},
                           1000)
        self.assertEqual(got["binary"], 100)
        self.assertEqual(got["text"], 4)   # pay=0.999 → round(4.004)=4

    def test_boundary_pay_004_gives_exactly_100(self):
        # pay=0.04 → 4/0.04=100 tam sınır (clamp gerekmez ama uç nokta).
        got = self._ratios({"text": 40, "pdf": 960,
                            "archive": 0, "binary": 0}, 1000)
        self.assertEqual(got["text"], 100)
        self.assertEqual(got["pdf"], 4)    # pay=0.96 → round(4.166…)=4

    def test_lower_clamp_defensive_bytes_gt_total_gets_1(self):
        # Savunmacı alt sınır: type_bytes > total_bytes (tutarsız girdi)
        # → pay=10 → 4/10=0.4 → round=0 → max(1, 0)=1 (negatif/0 oran yok).
        got = self._ratios({"text": 100, "pdf": 0, "archive": 0, "binary": 0},
                           10)
        self.assertEqual(got["text"], 1)
        self.assertEqual(got["pdf"], 100)

    def test_all_results_within_clamp_bounds_and_keys(self):
        # Her çıktı yalnızca 4 anahtarlı ve değerler [1, 100] içinde.
        got = self._ratios({"text": 363056, "pdf": 331822,
                            "archive": 0, "binary": 198}, 695076)
        self.assertEqual(tuple(got.keys()), KEYS)
        for v in got.values():
            self.assertGreaterEqual(v, 1)
            self.assertLessEqual(v, 100)

    # ── gerçek paket regresyon çapası ─────────────────────────────────
    def test_real_package_anchor_matches_config(self):
        # verify_delivery.config.json'daki güncel budget_ratios ile birebir.
        got = self._ratios({"text": 363056, "pdf": 331822,
                            "archive": 0, "binary": 198}, 695076)
        self.assertEqual(got, {"text": 8, "pdf": 8,
                               "archive": 100, "binary": 100})


if __name__ == "__main__":
    unittest.main()
