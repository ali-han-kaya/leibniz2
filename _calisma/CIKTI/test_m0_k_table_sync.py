#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_m0_k_table_sync.py — M0 raporu K tablosu ↔ LAYER_LABELS senkron kapısı.

_calisma/CIKTI/M0_TOOLKIT_DENETIM_RAPORU.md §6.2 "Katman tablosu" kendini
"güncel fail-closed zincirini katman katman listeler" diye tanımlar;
verify_delivery.py'deki LAYER_LABELS ise katman kümesinin TEK KAYNAĞIDIR
(verify-chain skill "Adding a new K-layer" adım 1: docstring tablosu +
LAYER_LABELS birlikte güncellenir).

Invariantlar (fail-closed — test_doc_job_sync.py / test_skill_layer_sync.py
ile aynı desen):
  1. Tablodaki HER K anahtarı LAYER_LABELS'te VAR olmalı (bayat/yanlış satır
     = doc güncellenmemiş; ör. katman yeniden adlandırılıp doc'a
     işlenmemişse yakalanır).
  2. LAYER_LABELS'teki HER katman tabloda VAR olmalı (yeni katman eklenip
     doc'a işlenmezse denetim izi eksik kalır).
  3. Tablo sırası numerik olmalı (K0..K23, atlama drift'i yakalanır).

M0 raporu bir denetim anlık görüntüsü olduğu için her satırın "Durum"
sütunu burada denetlenmez (canlı doğrulama ayrı katmanların işidir) —
yalnızca katman KÜMESİ kodla birebir tutulur.

stdlib unittest — tek dış bağımlılık yok.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_delivery as vd  # noqa: E402

M0_DOC = os.path.join(HERE, "M0_TOOLKIT_DENETIM_RAPORU.md")

# `| K0 | Bayat zip taraması (CIKTI dışı, recursive) | PASS |`
_ROW_RE = re.compile(r"^\|\s*(K\d+)\s*\|", re.M)


def parse_k0_layers(doc_text):
    """M0 raporundaki K tablosu satır anahtarlarını sırayla döndürür.

    Yalnızca `| K<n> |` ile başlayan satırlar yakalanır — diğer tablolar
    (Kayıt/Sonuç vb.) K anahtarı taşımaz, karışmaz.
    """
    return [m.group(1) for m in _ROW_RE.finditer(doc_text)]


class TestM0KTableSync(unittest.TestCase):
    """Gerçek M0 raporu K tablosu ↔ verify_delivery LAYER_LABELS çaprazı."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(M0_DOC):
            raise unittest.SkipTest(f"M0 raporu yok: {M0_DOC}")
        with open(M0_DOC, encoding="utf-8") as f:
            cls.doc_keys = parse_k0_layers(f.read())
        cls.code_keys = list(vd.LAYER_LABELS)

    def test_doc_has_layer_table(self):
        self.assertTrue(self.doc_keys, "M0 raporunda K tablosu yok "
                                      "(§6.2 Katman tablosu)")

    def test_every_doc_layer_exists_in_code(self):
        # Invariant 1: doc'taki her K anahtarı LAYER_LABELS'te var
        # (bayat/yanlış satır = doc güncellenmemiş).
        code_set = set(self.code_keys)
        stale = sorted(set(self.doc_keys) - code_set)
        self.assertEqual(stale, [],
                         "M0 tablosunda olup LAYER_LABELS'te OLMAYAN katmanlar "
                         f"(yeniden adlandırma/silme doc'a işlenmemiş): {stale}")

    def test_every_code_layer_documented(self):
        # Invariant 2: LAYER_LABELS'teki her katman tabloda var (yeni katman
        # doc'a işlenmemiş → denetim izi eksik).
        doc_set = set(self.doc_keys)
        missing = sorted(set(self.code_keys) - doc_set)
        self.assertEqual(missing, [],
                         "LAYER_LABELS'te olup M0 tablosunda OLMAYAN katmanlar: "
                         f"{missing} — §6.2 tablosuna ekleyin")

    def test_table_order_is_numeric(self):
        # Invariant 3: tablo sırası numerik olmalı (K1..K23, atlama yok).
        nums = [int(k[1:]) for k in self.doc_keys]
        self.assertEqual(nums, sorted(nums),
                         f"M0 tablo sırası bozuk: {self.doc_keys}")
        self.assertEqual(nums, list(range(nums[0], nums[-1] + 1)),
                         f"M0 tabloda katman atlaması var: "
                         f"{[n for n in range(nums[0], nums[-1] + 1) if n not in nums]}")


class TestM0KTableParsing(unittest.TestCase):
    """Parser'ın doc sözleşmesine duyarlılığı (mock metinler, OFFLINE)."""

    def test_parses_named_rows_only(self):
        doc = (
            "| Katman | Kontrol | Durum |\n"
            "|---|---|---|\n"
            "| K0 | Bayat zip taraması | PASS |\n"
            "| K1 | Dış zip sidecar | PASS |\n"
            "| Kayıt | Sonuç |\n"
            "| K2 | İç zip sidecar | PASS |\n"
        )
        self.assertEqual(parse_k0_layers(doc), ["K0", "K1", "K2"])

    def test_empty_when_no_rows(self):
        self.assertEqual(parse_k0_layers("başka metin\n"), [])


if __name__ == "__main__":
    unittest.main()