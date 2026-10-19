#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_ci_artifact_retention.py — artifact retention politikası sözleşmesi.

Politika (K4, `ci_hygiene_gate.py` ile aynı sabitler):

  * HER `actions/upload-artifact` adımı `with.retention-days` BİLDİRİR.
    Bildirmezse GitHub'ın 90 günlük varsayılanı sessizce uygulanır —
    depo maliyeti ve gizlilik yüzeyi bildirilmeden büyür.
  * Değer 1..90 aralığında int olur (bool reddedilir: bool, int alt-tipidir;
    `retention-days: true` yasal görünmemeli).
  * SINIF kuralı: kanıt sınıfı (`EVIDENCE_ARTIFACTS`: teslim/koruma kanıtı)
    TAM 90 gün; diğer tüm (tanı/log/rapor) adımlar ≤ 30 gün.

Bu dosya politikanın İKİ yüzeyini ayrı ayrı doğrular ve ikisini birbirine
karşı çaprazlar:

  T1 KAPSAM   : satır-tabanlı bağımsız tarayıcı tüm upload adımlarını görür;
                sayım `uses: actions/upload-artifact` ile BİREBİR uyuşur
                (parser sessizce adım atlarsa sözleşme vakum olurdu).
  T2 AĞAÇ     : gerçek repoda her adım politikaya uyar; kanıt sınıfı kümesi
                tam olarak ilan edilmiş iki artefakttır (yeni bir kanıt
                artefaktı sessizce eklenemez).
  T3 KAPI     : `ci_hygiene_gate.py` gerçek ağaçta rc=0 verir ve retention
                bulgusu üretmez; kapsam sayacı 36 adımı görür (kör kapı yok).
  T4 KIRMIZI : her ihlal tipi FIXTURE'da rc=1 üretir — iddialar non-vacuous
                (eksik / aralık dışı / bool / kanıt-30 / tanı-90 / adı boş).

PyYAML yoksa yalnız T3/T4'ün kapı-çağrıları SKIP edilir; T1/T2 statik katman
HER ortamda koşar ve yalnız başına kırmızıya düşebilir.
"""
import pathlib
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
GATE = HERE / "ci_hygiene_gate.py"

UPLOAD_MARK = "uses: actions/upload-artifact"
RETENTION_MIN, RETENTION_MAX = 1, 90
RETENTION_DIAG_MAX = 30
EVIDENCE_ARTIFACTS = {"reproducibility", "protection-drift"}

try:
    import yaml  # noqa: F401 — kapının import yüzeyi
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ── bağımsız tarayıcı (satır tabanlı, PyYAML'siz) ─────────────────────────
def scan_uploads(path):
    """[(artifact_name, retention|None, adım satır no)] — blok farkındalıklı."""
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for i, line in enumerate(lines):
        if UPLOAD_MARK not in line:
            continue
        name, retention = None, None
        for nxt in lines[i + 1:]:
            if re.match(r"^\s{0,6}- ", nxt) or re.match(r"^  [a-zA-Z]", nxt):
                break                      # adım/job bitti
            m = re.match(r"^\s+name:\s*(\S+)", nxt)
            if m and name is None:
                name = m.group(1)
            m = re.match(r"^\s+retention-days:\s*(\S+)", nxt)
            if m:
                retention = m.group(1)
        out.append((name, retention, i + 1))
    return out


class TestScopeNotVacuous(unittest.TestCase):
    """T1: tarayıcı tüm adımları görür; iki bağımsız sayım birebir."""

    def test_scanner_sees_every_upload_step(self):
        total = 0
        for wf in sorted(WORKFLOWS.glob("*.yml")):
            marks = len(re.findall(re.escape(UPLOAD_MARK),
                                   wf.read_text(encoding="utf-8")))
            seen = len(scan_uploads(wf))
            self.assertEqual(seen, marks,
                             f"{wf.name}: tarayıcı {seen}, işaret {marks}")
            total += seen
        # 40: 2026-10-19'da docx-export + capture-gate-dark +
        # lean-lake-build-log + statement-inventory yüklemeleri eklendi
        # (hepsi 30 gün). Pin bilinçli: yeni upload adımı geldiğinde bu
        # sayı ve retention politikası YENİDEN değerlendirilir.
        self.assertEqual(total, 40,
                         "upload adımı sayısı değişti — politikayı yeniden "
                         "değerlendir (yeni adım mı, silinen mi?)")

    def test_every_workflow_is_scanned(self):
        self.assertTrue(sorted(WORKFLOWS.glob("*.yml")), "workflow bulunamadı")


class TestPolicyOnRealTree(unittest.TestCase):
    """T2: gerçek ağaç politikaya uyar (statik katman — her ortamda koşar)."""

    def test_every_upload_declares_retention_days(self):
        missing = [(p.name, n, ln) for p in sorted(WORKFLOWS.glob("*.yml"))
                   for n, r, ln in scan_uploads(p) if r is None]
        self.assertEqual(missing, [], f"retention-days yok: {missing}")

    def test_retention_values_are_ints_in_range(self):
        bad = []
        for p in sorted(WORKFLOWS.glob("*.yml")):
            for n, r, ln in scan_uploads(p):
                if r is None or not r.isdigit():
                    bad.append((p.name, n, r))
                    continue
                if not RETENTION_MIN <= int(r) <= RETENTION_MAX:
                    bad.append((p.name, n, r))
        self.assertEqual(bad, [], f"aralık dışı/ondalık değer: {bad}")

    def test_class_rule_evidence_90_diagnostics_le_30(self):
        wrong = []
        for p in sorted(WORKFLOWS.glob("*.yml")):
            for n, r, ln in scan_uploads(p):
                if r is None or not r.isdigit():
                    continue
                value = int(r)
                plain = (n or "").split("${{")[0].rstrip("-")
                if plain in EVIDENCE_ARTIFACTS:
                    if value != RETENTION_MAX:
                        wrong.append((p.name, n, "kanıt≠90", value))
                elif value > RETENTION_DIAG_MAX:
                    wrong.append((p.name, n, f"tanı>{RETENTION_DIAG_MAX}", value))
        self.assertEqual(wrong, [], f"sınıf kuralı ihlali: {wrong}")

    def test_evidence_set_is_exactly_declared(self):
        """Yeni bir kanıt artefaktı sessizce eklenemez: 90 gün kimlerde?"""
        ninty = {(p.name, n) for p in sorted(WORKFLOWS.glob("*.yml"))
                 for n, r, ln in scan_uploads(p) if r == str(RETENTION_MAX)}
        self.assertEqual(
            sorted(n for _, n in ninty), sorted(EVIDENCE_ARTIFACTS),
            "90 günlük artefakt kümesi ilan edilmiş kanıt sınıfıyla "
            "uyuşmuyor (yeni kanıt → EVIDENCE_ARTIFACTS'a gerekçesiyle ekle)")


@unittest.skipUnless(HAS_YAML, "PyYAML yok — kapı import yüzeyi koşulamaz")
class TestGateAgrees(unittest.TestCase):
    """T3: kapı gerçek ağaçta yeşil, kapsamı sayıyor, retention bulgusu yok."""

    def run_gate(self, target):
        return subprocess.run(
            [sys.executable, str(GATE), "--workflow", str(target)],
            capture_output=True, text=True, timeout=60)

    def test_real_tree_passes_gate_and_reports_scope(self):
        r = self.run_gate(WORKFLOWS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("40 upload adımı", r.stdout)
        self.assertNotIn("retention-days", r.stdout)

    def test_gate_counts_match_static_scanner(self):
        r = self.run_gate(WORKFLOWS)
        m = re.search(r"(\d+) upload adımı", r.stdout)
        self.assertIsNotNone(m, r.stdout)
        total = sum(len(scan_uploads(p))
                    for p in sorted(WORKFLOWS.glob("*.yml")))
        self.assertEqual(int(m.group(1)), total,
                         "kapı ile bağımsız tarayıcı farklı sayıyor")


@unittest.skipUnless(HAS_YAML, "PyYAML yok — kapı import yüzeyi koşulamaz")
class TestEveryViolationIsRed(unittest.TestCase):
    """T4: her ihlal tipi tek başına rc=1 (iddialar non-vacuous)."""

    HEAD = """\
        name: x
        on: push
        permissions: {contents: read}
        concurrency: {group: g}
        jobs:
          a:
            runs-on: ubuntu-latest
            timeout-minutes: 5
            steps:
    """

    def gate(self, step_yaml):
        yml = textwrap.dedent(self.HEAD) + textwrap.indent(
            textwrap.dedent(step_yaml), " " * 6)
        with tempfile.TemporaryDirectory() as td:
            (pathlib.Path(td) / "wf.yml").write_text(yml, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(GATE), "--workflow", td],
                capture_output=True, text=True, timeout=60)

    def assert_red(self, step_yaml, needle):
        r = self.gate(step_yaml)
        self.assertEqual(r.returncode, 1, f"rc={r.returncode}\n{r.stdout}")
        self.assertIn(needle, r.stdout)

    def test_missing_retention_is_red(self):
        self.assert_red("""\
            - uses: actions/upload-artifact@v6
              with:
                name: logs
                path: logs/
        """, "retention-days yok")

    def test_out_of_range_is_red(self):
        self.assert_red("""\
            - uses: actions/upload-artifact@v6
              with:
                name: logs
                path: logs/
                retention-days: 120
        """, "aralık dışı")

    def test_bool_retention_is_red(self):
        self.assert_red("""\
            - uses: actions/upload-artifact@v6
              with:
                name: logs
                path: logs/
                retention-days: true
        """, "int olmalı")

    def test_evidence_at_diagnostic_tier_is_red(self):
        self.assert_red("""\
            - uses: actions/upload-artifact@v6
              with:
                name: reproducibility
                path: reproducibility/
                retention-days: 30
        """, "kanıt artefaktı")

    def test_diagnostic_at_evidence_tier_is_red(self):
        self.assert_red("""\
            - uses: actions/upload-artifact@v6
              with:
                name: unit-tests
                path: unit_tests.log
                retention-days: 90
        """, "tanı sınıfı")

    def test_compliant_steps_are_green(self):
        r = self.gate("""\
            - uses: actions/upload-artifact@v6
              with:
                name: unit-tests
                path: x
                retention-days: 30
            - uses: actions/upload-artifact@v6
              with:
                name: protection-drift
                path: y
                retention-days: 90
        """)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
