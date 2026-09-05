#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_skill_layer_sync.py — verify-chain SKILL.md ↔ verify_delivery.py senkronu.

Skill prosedürü (skills/verify-chain/SKILL.md "Adding a new K-layer" adım 1)
tek-kaynak kuralı koyar: yeni K katmanı HEM docstring tablosunda HEM
LAYER_LABELS'te olmalı. Bu test, o kuralı SKILL.md'nin kendi K-layer map
tablosuna genişletir — kod ile skill belgesi çapraz doğrulanır (fail-closed):

  1. SKILL.md K-layer map'teki katman seti == LAYER_LABELS anahtarları
     (eksik/fazla katman → drift; örn. K18-K20 tabloya işlenmezse yakalanır).
  2. SKILL.md "In --full?" sütunu, apply_full_flags(full=True) sonrası her
     katmanın getter'ıyla birebir tutarlı olmalı ("yes" → ran, "no" → değil;
     K12 plist / K15 history / K17 mirror / K20 launchctl gibi istisnalar
     sütunda işaretli olmalı).
  3. LAYER_LABELS sırası numerik olmalı (K0..K21, atlama drift'i yakalanır).

Skill belgesi güncellenmeden kod katman eklenirse bu test fail eder — kod ve
skill aynı commit'te senkron kalmak zorundadır.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_delivery as vd  # noqa: E402

SKILL_MD = os.path.normpath(os.path.join(
    HERE, "..", "..", "skills", "verify-chain", "SKILL.md"))

# K-layer map tablosu regex'i: | K<n> | ... | flag | yes/no |
_MAP_ROW = re.compile(r"^\|\s*(K\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(yes|no|separately)\s*\|")


def _full_test_args():
    """apply_full_flags için tüm getter alanlarını taşıyan boş namespace."""
    import argparse
    return argparse.Namespace(
        full=True, check_references=False, symbolic_proof=False,
        lean_proof=False, check_lineage=False, check_repro_manifest=False,
        check_config_drift=False, check_cleanup=False,
        check_github_scripts=False, check_mirror=False,
        mirror_auto_sync=False, check_daemon=False, coq_proof=False,
        check_history=None, check_sde=False, verify_manifest=None,
        check_plist=False, check_launchd=False)


def _parse_skill_map():
    """SKILL.md K-layer map tablosunu {K<n>: {desc, flag, full}} olarak ayrıştırır."""
    with open(SKILL_MD, encoding="utf-8") as f:
        text = f.read()
    sec = text.split("### The K-layer map", 1)
    if len(sec) != 2:
        raise AssertionError("SKILL.md'de '### The K-layer map' bölümü yok")
    body = sec[1].split("\n## ", 1)[0]
    rows = {}
    for ln in body.splitlines():
        m = _MAP_ROW.match(ln.strip())
        if m:
            key, desc, flag, full = m.group(1), m.group(2).strip(), \
                m.group(3).strip(), m.group(4)
            rows[key] = {"desc": desc, "flag": flag, "full": full}
    return rows


class TestSkillLayerMapSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(SKILL_MD):
            raise unittest.SkipTest("SKILL.md yok")
        cls.rows = _parse_skill_map()
        if not cls.rows:
            raise unittest.SkipTest("K-layer map boş ayrıştı")

    def test_skill_map_matches_layer_labels(self):
        """SKILL.md tablosundaki katman seti == LAYER_LABELS anahtarları."""
        skill_keys = set(self.rows)
        code_keys = set(vd.LAYER_LABELS)
        missing = skill_keys - code_keys  # skill'de var, kodda yok
        extra = code_keys - skill_keys    # kodda var, skill'de yok
        self.assertEqual(missing, set(),
                         f"SKILL.md'de var ama LAYER_LABELS'te yok: {missing}")
        self.assertEqual(extra, set(),
                         f"LAYER_LABELS'te var ama SKILL.md tablosunda yok: {extra}")

    def test_layer_labels_numeric_order(self):
        """LAYER_LABELS sırası K0..K21 numerik olmalı (atlama yok)."""
        nums = [int(k[1:]) for k in vd.LAYER_LABELS]
        self.assertEqual(nums, sorted(nums), "LAYER_LABELS sırası bozuk")
        expected = list(range(nums[0], nums[-1] + 1))
        self.assertEqual(nums, expected,
                         f"Katman atlaması var: {[n for n in expected if n not in nums]}")

    def test_full_column_matches_apply_full_flags(self):
        """SKILL.md 'In --full?' sütunu, --full sonrası katman durumuyla uyuşmalı."""
        ns = vd.apply_full_flags(_full_test_args())
        mismatches = []
        for key, row in sorted(self.rows.items()):
            getter = vd._OPTIONAL_LAYERS.get(key)
            if getter is None:
                continue  # çekirdek katmanlar (K0-K7) her zaman koşar
            try:
                ran = bool(getter(ns))
            except AttributeError:
                ran = False
            full = row["full"]
            if full == "yes" and not ran:
                mismatches.append(f"{key}: sütun 'yes' ama --full'da koşmuyor")
            elif full in ("no", "separately") and ran:
                mismatches.append(f"{key}: sütun '{full}' ama --full'da koşuyor")
        self.assertEqual(mismatches, [],
                         "SKILL.md --full sütunu kodla çelişiyor:\n" +
                         "\n".join(mismatches))

    def test_core_layers_marked_always(self):
        """K0-K7 çekirdek katmanlar SKILL.md'de 'always' olarak işaretli olmalı.

        K6 istisnadır: PDF sayfa denetimi her zaman koşar, ama çevrimiçi
        DOI/URL denetimi `--check-references` bayrağını gerektirir — bu yüzden
        bayrak sütununda 'always' yerine `--check-references` taşır.
        """
        for k in sorted(vd._CORE_LAYERS):
            self.assertIn(k, self.rows, f"çekirdek katman SKILL.md'de yok: {k}")
            if k == "K6":
                self.assertRegex(self.rows[k]["flag"], r"^`?--check-references",
                                 "K6 online denetimi --check-references bayrağıyla işaretli olmalı")
            else:
                self.assertEqual(self.rows[k]["flag"], "always",
                                 f"{k} 'always' işaretli olmalı (kod: {k} çekirdek)")

    def test_optional_flags_have_skill_rows(self):
        """Her isteğe bağlı katmanın SKILL.md'de satırı ve bayrağı olmalı."""
        for k, getter in sorted(vd._OPTIONAL_LAYERS.items()):
            self.assertIn(k, self.rows, f"opsiyonel katman SKILL.md'de yok: {k}")
            flag = self.rows[k]["flag"]
            if flag == "always":
                continue
            # Bayrak adı koddaki argparse flag'iyle eşleşmeli (--check-* deseni;
            # backtick'li `--flag` veya `--flag PATH` biçimlerini kabul et).
            self.assertRegex(flag, r"^`?--",
                             f"{k} bayrağı -- ile başlamalı: {flag}")


if __name__ == "__main__":
    unittest.main()
