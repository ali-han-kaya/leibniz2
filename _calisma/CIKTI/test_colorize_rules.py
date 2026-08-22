#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_colorize_rules.py — preview.html colorizeLine renk kurallarının regresyon kapısı.

colorizeLine() regex kalıplarını bilinen girdilere karşı test eder.
pre-commit hook'u olarak çağrılabilir: regex'ler değişirse veya beklenen
renkler değişirse test başarısız olur.

Kurallar preview.html'deki function colorizeLine() ile senkron tutulmalıdır.
Değişiklik sonrası bu dosyadaki EXPECTED_RULES ve TEST_CASES güncellenmelidir.

Kullanım:
  python3 -m pytest test_colorize_rules.py -v
"""
import pathlib
import re
import sys
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PREVIEW_HTML = SCRIPT_DIR / "preview.html"

# ── colorizeLine regex kuralları — preview.html function colorizeLine() ile senkron ──
# Her kural: (compiled_regex, css_class, description)
# JS regex: \[K8\] = literal [K8], \bUNSAT\b = word boundary
EXPECTED_RULES = [
    (re.compile(r"^\[P0\]|^\[FAIL\]|^SONUÇ: FAIL|FAIL \(P0=|^Error|Exception|^Traceback|^HATA"),
     "err", "P0/FAIL/hata → kırmızı"),
    (re.compile(r"^\[BÜTÇE\]|^Bütçe:|^Budget:|^\$[0-9.]+ / \$[0-9.]+|aşım"),
     "budget", "Bütçe satırları → mor"),
    (re.compile(r"^\[P1\]|\[CLI override\]|\[CLI-OVERRIDE\]"),
     "warn", "P1/CLI override → sarı"),
    (re.compile(r"\[K8\]|\bUNSAT\b|\bSAT\b|^\[PASS\]|^SONUÇ: PASS|^SONUÇ: TÜMÜ PASS|^Verdict: PASS"),
     "ok", "K8/PASS → yeşil"),
    (re.compile(r"^=== |^--- |^\[K[0-9]"),
     "muted", "Bölüm ayırıcı/K katmanı → gri"),
]


def colorize_line(line):
    """preview.html colorizeLine() ile aynı mantık (Python karşılığı)."""
    for pat, css_class, _ in EXPECTED_RULES:
        if pat.search(line):
            return css_class
    return None


# ── Test çiftleri: (input_line, expected_css_class_or_None) ──
TEST_CASES = [
    # err (P0/FAIL)
    ("[P0] K0-STALE bayat zip", "err"),
    ("[FAIL] K12 plist drift", "err"),
    ("SONUÇ: FAIL (P0=1, P1=0)", "err"),
    ("FAIL (P0=2, P1=1)", "err"),
    ("Error: file not found", "err"),
    ("Exception: timeout", "err"),
    ("Traceback (most recent call last):", "err"),
    ("HATA: config geçersiz JSON", "err"),
    # budget
    ("[BÜTÇE] ~175990 token → $1.08 (limit $30.0)", "budget"),
    ("Bütçe: ~175990 token → $1.08 (limit $30.0)", "budget"),
    ("Budget: ~175990 token → $1.08 (limit $30.0)", "budget"),
    ("$1.08 / $30.00", "budget"),
    ("bütçe aşım", "budget"),
    # warn (P1)
    ("[P1] K17 mirror eski", "warn"),
    ("[CLI override] budget=25", "warn"),
    ("[CLI-OVERRIDE] budget_method=weighted", "warn"),
    # ok (PASS/K8)
    ("[K8] Z3: 12/12 PASS", "ok"),
    ("[PASS] P1-a     (T2 ∧ M0) ⊨ T1", "ok"),
    ("SONUÇ: PASS (P0=0, P1=0)", "ok"),
    ("SONUÇ: TÜMÜ PASS", "ok"),
    ("Verdict: PASS", "ok"),
    ("UNSAT (beklenen UNSAT)", "ok"),
    ("SAT (beklenen SAT)", "ok"),
    # muted (bölüm ayırıcı)
    ("=== Stoic-Hume V5 teslim doğrulaması ===", "muted"),
    ("--- soak test ---", "muted"),
    ("[K0] Stale zip taraması", "muted"),
    ("[K5] Referans denetimi", "muted"),
    ("[K12] Plist şablon", "muted"),
    # default (hiçbiri eşleşmez)
    ("PDF: 33 sayfa | References: 64", None),
    ("Config: file ← /path/to/config.json", None),
    ("Merhaba dünya", None),
    ("", None),
]


class TestColorizeRulesSync(unittest.TestCase):
    """preview.html'deki function colorizeLine() ile EXPECTED_RULES senkron mu?"""

    def test_html_exists(self):
        self.assertTrue(PREVIEW_HTML.is_file(),
                        f"preview.html bulunamadı: {PREVIEW_HTML}")

    def test_html_contains_colorize_function(self):
        text = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn("function colorizeLine(line)", text)

    def test_html_has_all_css_classes(self):
        """preview.html colorizeLine'da beklenen tüm CSS class'ları mevcut mu?"""
        text = PREVIEW_HTML.read_text(encoding="utf-8")
        for _, css_class, desc in EXPECTED_RULES:
            self.assertIn(
                f"class=\"{css_class}\"", text,
                f"CSS class '{css_class}' ({desc}) preview.html'de bulunamadı"
            )

    def test_html_rules_count_matches(self):
        """HTML'deki colorizeLine if bloğu sayısı kural sayısıyla eşleşmeli."""
        text = PREVIEW_HTML.read_text(encoding="utf-8")
        # colorizeLine fonksiyonunu izole et
        m = re.search(r"function colorizeLine\(line\)\s*\{(.*?)\nfunction ", text, re.DOTALL)
        self.assertIsNotNone(m, "colorizeLine fonksiyonu bulunamadı")
        body = m.group(1)
        # return '<span class=...appearing' pattern'ini say
        html_returns = re.findall(r"return\s*'<span class=", body)
        self.assertEqual(len(html_returns), len(EXPECTED_RULES),
                         f"Kural sayısı tutarsız: HTML={len(html_returns)} "
                         f"beklenen={len(EXPECTED_RULES)}")


class TestColorizeLine(unittest.TestCase):
    """Bilinen girdiler için renk eşleşme testleri."""

    def test_all_test_cases(self):
        failures = []
        for line, expected in TEST_CASES:
            got = colorize_line(line)
            if got != expected:
                failures.append(
                    f"  '{line[:60]}' → beklenen={expected} alınan={got}"
                )
        if failures:
            self.fail("Renk eşleşme hataları:\n" + "\n".join(failures))


class TestRegexCoverage(unittest.TestCase):
    """Her CSS class en az bir test case ile kaplı mı?"""

    def test_all_classes_covered(self):
        classes_in_rules = {r[1] for r in EXPECTED_RULES}
        classes_in_tests = {exp for _, exp in TEST_CASES if exp is not None}
        uncovered = classes_in_rules - classes_in_tests
        self.assertEqual(uncovered, set(),
                         f"Kapsanmamış CSS class'lar: {uncovered}")

    def test_no_false_positives(self):
        """Hiçbir test case'i yanlış renk eşleşmesi yapmamalı."""
        for line, expected in TEST_CASES:
            got = colorize_line(line)
            # Yanlış pozitif: başka bir class'a düşmüşse hata
            if expected is not None and got is not None and got != expected:
                self.fail(f"Yanlış renk: '{line[:40]}' → {got} (beklenen: {expected})")


if __name__ == "__main__":
    unittest.main()
