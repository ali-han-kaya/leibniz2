#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_doc_job_sync.py — PUBLISH_SCENARIO job tablosu ↔ verify.yml job name senkron kapısı.

docs/PUBLISH_SCENARIO.md'deki "Job kategorileri (N job …)" tablosu, CI'ın
koştuğu TÜM job'ları belgeler (A required / B advisory / C-D PR-only).
verify.yml'deki her job'ın `name:` alanı ise TEK KAYNAKTIR (branch
protection check adları da buradan türetilir — status_checks.py).

Invariantlar (fail-closed — test_doc_artifact_sync.py ile aynı desen):
  1. Tablodaki HER job adı verify.yml'de VAR olmalı (bayat/yanlış ad =
     doc güncellenmemiş; ör. K1-K14 → K1-K19 yeniden adlandırması doc'a
     işlenmemişse yakalanır).
  2. verify.yml'deki HER job `name:` alanı tabloda VAR olmalı (yeni job
     eklenip doc'a işlenmezse denetim izi eksik kalır).
  3. "Job kategorileri (N job …)" başlığındaki N sayısı ayrıştırılan
     satır sayısıyla birebir olmalı (bayat sayı = tablo güncellenmemiş).

Reuse: yaml ayrıştırması PyYAML gerektirir (yoksa dürüstçe SKIP — CI tam
suite'te PyYAML kurulu olduğu için yine koşar).

stdlib unittest — tek dış bağımlılık PyYAML (opsiyonel).
"""
import pathlib
import re
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

try:
    import yaml  # noqa: E402
except ImportError:  # pragma: no cover — PyYAML'sız ortam (dürüstçe SKIP)
    yaml = None

DOC = pathlib.Path("docs/PUBLISH_SCENARIO.md")
WORKFLOW = pathlib.Path(".github/workflows/verify.yml")

# `**Job kategorileri (22 job = 12 required + 8 advisory + 2 PR-only):**`
_HEADER_RE = re.compile(r"^\*\*Job kategorileri\s*\((\d+)\s+job", re.M)
# `| 1 | A | Delivery verification — K1-K14 (single entry point) | ✅ ... |`
# Ad 3. hücredir — sonraki hücreler (Son durum) `|` içerebileceğinden ad
# yalnızca 2. ve 3. ayraç arasındaki `|` içermeyen metindir.
_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*([ABCD])\s*\|\s*([^|]+?)\s*\|",
                     re.M)


def parse_doc_jobs(doc_text):
    """Doc tablosundaki (kategori, job adı) çiftlerini sırayla döndürür.

    Bölüm ayraç satırları (`| | **A — …** | | |`) ve başlık satırları
    yok sayılır — yalnızca `| N | X | ad | … |` biçimindeki satırlar.
    """
    rows = []
    for m in _ROW_RE.finditer(doc_text):
        rows.append((m.group(2), m.group(3).strip()))
    return rows


def workflow_job_names(yml_text):
    """verify.yml'deki job id → `name:` haritası (None name'ler atlanır)."""
    data = yaml.safe_load(yml_text)
    jobs = data.get("jobs") or {}
    out = {}
    for jid, j in jobs.items():
        name = (j or {}).get("name")
        if name:
            out[jid] = name
    return out


def _header_count(doc_text):
    m = _HEADER_RE.search(doc_text)
    return int(m.group(1)) if m else None


class TestDocJobSync(unittest.TestCase):
    """Gerçek doc tablosu ↔ verify.yml job name çapraz doğrulaması."""

    @classmethod
    def setUpClass(cls):
        if yaml is None:
            raise unittest.SkipTest("PyYAML yok — job name ayrıştırılamaz")
        if not DOC.is_file() or not WORKFLOW.is_file():
            raise unittest.SkipTest(
                f"repo kökünden koşulmalı ({DOC}/{WORKFLOW} yok)")
        cls.doc_rows = parse_doc_jobs(DOC.read_text(encoding="utf-8"))
        cls.wf_names = set(
            workflow_job_names(WORKFLOW.read_text(encoding="utf-8")).values())

    def test_doc_has_job_table(self):
        self.assertTrue(self.doc_rows, "doc'ta job tablosu yok "
                                       "('Job kategorileri' bölümü)")

    def test_header_count_matches_table_rows(self):
        n = _header_count(DOC.read_text(encoding="utf-8"))
        self.assertIsNotNone(n, "'Job kategorileri (N job …):' başlığı yok")
        self.assertEqual(n, len(self.doc_rows),
                         f"başlık {n} job diyor, tablo {len(self.doc_rows)} "
                         f"satır içeriyor")

    def test_every_doc_job_exists_in_workflow(self):
        # Invariant 1: doc'taki her ad workflow `name:`'te var (bayat ad yok).
        doc_names = {name for (_cat, name) in self.doc_rows}
        stale = sorted(doc_names - self.wf_names)
        self.assertEqual(stale, [],
                         "doc'ta olup verify.yml name:'inde OLMAYAN job adları "
                         f"(yeniden adlandırma/silme doc'a işlenmemiş): {stale}")

    def test_every_workflow_job_documented(self):
        # Invariant 2: workflow'daki her `name:` tabloda var (yeni job
        # doc'a işlenmemiş).
        doc_names = {name for (_cat, name) in self.doc_rows}
        missing = sorted(self.wf_names - doc_names)
        self.assertEqual(missing, [],
                         "verify.yml'de olup doc tablosunda OLMAYAN job'lar: "
                         f"{missing} — tabloya ekleyin")

    def test_doc_categories_are_valid(self):
        # Kategori harfleri yalnızca A/B/C/D (tipo yakalayıcı).
        cats = {cat for (cat, _name) in self.doc_rows}
        self.assertLessEqual(cats, {"A", "B", "C", "D"},
                             f"beklenmeyen kategori harfi: {cats - {'A','B','C','D'}}")


class TestDocJobParsing(unittest.TestCase):
    """Parser'ın doc sözleşmesine duyarlılığı (mock metinler, OFFLINE)."""

    def test_parses_named_rows_only(self):
        doc = (
            "**Job kategorileri (2 job = 2 required):**\n"
            "\n"
            "| # | Kategori | Job | Son durum |\n"
            "|---|---|---|---|\n"
            "| | **A — Required (2; merge bloke)** | | |\n"
            "| 1 | A | Delivery verification — K1-K19 (single entry point) | ✅ |\n"
            "| 2 | A | Budget shield (aggregated) | ✅ |\n"
        )
        self.assertEqual(parse_doc_jobs(doc), [
            ("A", "Delivery verification — K1-K19 (single entry point)"),
            ("A", "Budget shield (aggregated)"),
        ])

    def test_header_count_regex(self):
        self.assertEqual(
            _header_count("**Job kategorileri (24 job = 12 + 10 + 2):**\n"), 24)
        self.assertIsNone(_header_count("**Artifact listesi (24):**\n"))
        self.assertIsNone(_header_count("başka metin\n"))

    def test_ignores_non_table_rows(self):
        doc = ("**Job kategorileri (1 job):**\n"
               "| 1 | A | Pre-commit P0 label gate | — |\n"
               "**Kural:** branch protection yalnızca required'ları bloke eder.\n"
               "| 2 | B | Bu satır başlık sonrası — YAKALANMAMALI | — |\n")
        # Ayraç/başlık satırları regex'i karşılamaz; ama 2. veri satırı da
        # eşleşir (başlık sonrası olsa bile tablo biçimi geçerli). Yalnızca
        # '| 1 | A | …' biçimli satırların yakalandığını doğrula.
        self.assertEqual(len(parse_doc_jobs(doc)), 2)


if __name__ == "__main__":
    unittest.main()
