#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_attr_context_audit.py — attr_context_audit.py için kapı + mutasyonlar.

Kapı: gerçek ağaçta havuz temiz olmalı (0 bulgu). Mutasyon sınıfları
(sentetik metin + geçici baseline) kuralın GERÇEKTEN ayırt ettiğini kanıtlar:
ham veri nitelikte → bulgu; bilinmeyen ifade → bulgu; pin kaybı → bulgu;
sink TSX'te → bulgu. Yeşil tek başına kanıt değildir; her sınıf kırmızıya
düşebilmelidir.

Çalıştırma: python3 -m unittest test_attr_context_audit -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import attr_context_audit as aca  # noqa: E402

P = aca.P


def _kinds(findings):
    return sorted(f["kind"] for f in findings)


class PoolCoverageTest(unittest.TestCase):
    """Pozitif kontrol: havuz boş ya da yanlış filtrelenmiş olmamalı."""

    def setUp(self):
        self.pool = set(aca.pool())

    def test_pool_contains_preview_surface(self):
        self.assertIn(P, self.pool, "preview.js havuzda yok")

    def test_pool_contains_dashboard_next_tsx(self):
        self.assertTrue(
            any(p.startswith("apps/dashboard-next/") and p.endswith(".tsx")
                for p in self.pool),
            "dashboard-next TSX havuzda yok (filtre bozuk ya da git?)")

    def test_pool_excludes_vendor(self):
        self.assertFalse(any("vendor/" in p for p in self.pool),
                         "vendor dosyası havuza girmiş")


class RealTreeGateTest(unittest.TestCase):
    """Kapı: gerçek ağaçta bulgu yok (fail-closed)."""

    def test_real_tree_has_no_findings(self):
        inventory, findings, hits = aca.audit()
        self.assertGreater(inventory["attr_sites"], 0,
                           "sıfır nitelik enterpolasyonu — tarama boş")
        self.assertEqual(findings, [],
                         "attr-context bulguları: %s" % findings[:5])


class UnreviewedAndSinkTest(unittest.TestCase):
    """Sentetik metinler: ham veri / bilinmeyen ifade / TSX sink'i."""

    def test_raw_data_in_attribute_is_unreviewed(self):
        text = 'const h = `<span class="a ${r.source}">x</span>`;\n'
        _, _, hits = aca.scan_text("x/fake.js", text)
        unreviewed = [h for h in hits
                      if ("x/fake.js", h["expr"]) not in aca.BASELINE]
        self.assertEqual([h["expr"] for h in unreviewed], ["r.source"])

    def test_text_context_is_not_an_attribute(self):
        text = 'const h = `<span>${r.source}</span>`;\n'
        _, _, hits = aca.scan_text("x/fake.js", text)
        self.assertEqual(hits, [], "metin bağlamı nitelik sayılmamalı")

    def test_closed_quote_ends_attribute_context(self):
        text = 'const h = `<a title="ok">x</a> ${r.source}`;\n'
        _, _, hits = aca.scan_text("x/fake.js", text)
        self.assertEqual(hits, [], "kapanmış nitelikten sonra metin sayıldı")

    def test_tsx_raw_html_sink_is_a_finding(self):
        text = "export const X = () => <div dangerouslySetInnerHTML={{__html: y}} />;\n"
        _, raw, _ = aca.scan_text("apps/dashboard-next/x.tsx", text)
        self.assertEqual(len(raw), 1)
        self.assertEqual(raw[0]["kind"], "R1-sink")

    def test_js_innerhtml_is_inventoried_not_failed(self):
        text = "el.innerHTML = '<b>' + safe + '</b>';\n"
        inner, raw, _ = aca.scan_text("x/fake.js", text)
        self.assertEqual(inner, 1)
        self.assertEqual(raw, [], "JS innerHTML R1 bulgusu olmamalı")

    def test_escape_call_inline_still_needs_review(self):
        # escapeHTML(...) satır-içi ise de baseline dışı → bilinmeyen = güvensiz.
        text = 'h = `<i title="${escapeHTML(r.lean_detail)}">`;\n'
        _, _, hits = aca.scan_text("x/fake.js", text)
        self.assertEqual([h["expr"] for h in hits],
                         ["escapeHTML(r.lean_detail)"])
        self.assertNotIn((("x/fake.js"), "escapeHTML(r.lean_detail)"),
                         aca.BASELINE)


class BaselineIntegrityTest(unittest.TestCase):
    """Baseline çürümez: pin'ler ve sınıf-şekil uyumu."""

    def _repo_with(self, rel, text):
        tmp = tempfile.mkdtemp()
        path = Path(tmp) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return Path(tmp)

    def test_pin_loss_is_a_finding(self):
        base = {(P, "tsAttr"): {"class": "ESCAPED", "reason": "x",
                                "pin": 'const tsAttr = r.ts ? escapeHTML(r.ts) : "";'}}
        repo = self._repo_with(P, 'const tsAttr = r.ts;\n')  # kaçırma kaldırıldı
        f = aca.check_entries(repo, base)
        self.assertEqual(_kinds(f), ["R2-PIN"])

    def test_pin_present_is_clean(self):
        base = {(P, "tsAttr"): {"class": "ESCAPED", "reason": "x",
                                "pin": 'const tsAttr = r.ts ? escapeHTML(r.ts) : "";'}}
        repo = self._repo_with(P, 'const tsAttr = r.ts ? escapeHTML(r.ts) : "";\n')
        self.assertEqual(aca.check_entries(repo, base), [])

    def test_escaped_identifier_without_pin_is_a_finding(self):
        base = {(P, "tsAttr"): {"class": "ESCAPED", "reason": "x"}}
        repo = self._repo_with(P, "\n")
        self.assertEqual(_kinds(aca.check_entries(repo, base)), ["R2-CLASS"])

    def test_numeric_class_with_text_is_a_finding(self):
        base = {(P, 'r.source + "x"'): {"class": "NUMERIC", "reason": "x"}}
        repo = self._repo_with(P, "\n")
        self.assertEqual(_kinds(aca.check_entries(repo, base)), ["R2-CLASS"])

    def test_stale_entry_is_a_finding(self):
        base = dict(aca.BASELINE)
        base[(P, "no_such_expression_zz")] = {"class": "NUMERIC", "reason": "x"}
        _, findings, _ = aca.audit(aca.REPO, base)
        self.assertIn("R2-STALE", _kinds(findings))


if __name__ == "__main__":
    unittest.main()
