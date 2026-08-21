#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dryrun_summary.py — publish_wrapper.sh `--dry-run-summary` regresyon kapısı.

`gen_dryrun_summary()` fonksiyonu, publish_wrapper.sh'nin dry-run log'undan TEK
markdown dosyası üretir (AŞAMA başlıkları + `[DRY-RUN]` komut önizlemeleri +
fenced tam çıktı). Bu test, fonksiyonu GERÇEK kaynaktan (docs/publish_wrapper.sh)
ayıklayıp örnek bir log üzerinde koşar ve markdown yapısını doğrular:

  - Başlık + repo/metadata satırları
  - `## Komut akışı` → `### AŞAMA X` başlıkları
  - `[DRY-RUN] çalıştırılacak: <cmd>` → `- \`<cmd>\`` (backtick'li komut)
  - `[DRY-RUN] <not>` → `- <not>` (backtick'siz not)
  - `## Tam çıktı (denetim)` + dengeli fenced blok (```)

Fonksiyon `docs/publish_wrapper.sh`'den satır aralığıyla ayıklanır
(`gen_dryrun_summary() {` satırından, onu izleyen ilk üst-seviye
`if [ "$DRY_RUN" = "1" ]; then` satırına kadar). Fonksiyon taşınırsa/bozulursa
ayıklama başarısız olur → test FAIL → commit bloke (gerçek regresyon kapısı).

stdlib unittest — ek bağımlılık yok. OFFLINE (ağ çağrısı yok, gh yok).
"""

import pathlib
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]  # leibniz2/
WRAPPER = REPO_ROOT / "docs" / "publish_wrapper.sh"

# Fonksiyon başlangıcı ve bitişi (üst-seviye `if [ "$DRY_RUN" = "1" ]; then`).
_FN_START = "gen_dryrun_summary() {"
_IF_DRY_RUN = re.compile(r'^if \[ "\$DRY_RUN" = "1" \]; then$')


def extract_gen_dryrun_summary(wrapper: pathlib.Path = WRAPPER) -> str:
    """publish_wrapper.sh'den gen_dryrun_summary fonksiyon gövdesini ayıkla."""
    if not wrapper.is_file():
        raise AssertionError(f"WRAPPER yok: {wrapper}")

    lines = wrapper.read_text(encoding="utf-8").splitlines()

    start = None
    for i, line in enumerate(lines):
        if line.strip() == _FN_START:
            start = i
            break
    if start is None:
        raise AssertionError(
            f"gen_dryrun_summary fonksiyonu bulunamadı ({wrapper.name}) — "
            "fonksiyon taşınmış/bozulmuş olabilir")

    end = None
    for i in range(start + 1, len(lines)):
        if _IF_DRY_RUN.match(lines[i]):
            end = i
            break
    if end is None:
        raise AssertionError(
            "gen_dryrun_summary bitiş sınırı bulunamadı — fonksiyon "
            "yapısı değişmiş olabilir")

    body = "\n".join(lines[start:end])
    # Fonksiyonun kapanış `}`'i dahil mi? start..end arası son satır `}` olmalı.
    if not body.rstrip().endswith("}"):
        raise AssertionError("gen_dryrun_summary kapanış `}` bulunamadı")
    return body


def run_generated(out_dir: pathlib.Path, sample_log: str) -> pathlib.Path:
    """Ayıklanan fonksiyonu örnek logla koş; üretilen markdown yolunu döndür."""
    fn = extract_gen_dryrun_summary()

    log = out_dir / "sample.log"
    summary = out_dir / "summary.md"
    log.write_text(sample_log, encoding="utf-8")

    script = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        OWNER="ali-han-kaya"
        REPO_NAME="leibniz2"
        {fn}
        gen_dryrun_summary "{log}" "{summary}"
        """)
    script_file = out_dir / "run.sh"
    script_file.write_text(script, encoding="utf-8")

    r = subprocess.run(["bash", str(script_file)],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(
            f"gen_dryrun_summary çalışmadı (exit {r.returncode})\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}")
    return summary


SAMPLE_LOG = textwrap.dedent("""\
    [12:00:00] publish_wrapper.sh DRY-RUN modunda — hiçbir komut çalıştırılmayacak
    [12:00:01] ===== AŞAMA 0 — Ön-kontrol (publish_precheck.sh — tek komut) =====
    [12:00:02] [DRY-RUN] bash docs/publish_precheck.sh --skip-smoke --allow-remote
    [12:00:03] [DRY-RUN]   (dry-run'da smoke atlanır; remote zaten varsa toleranslı)
    [12:00:04] ===== AŞAMA 1 — GitHub repo oluştur (interaktif değil, idempotent) =====
    [12:00:05] [DRY-RUN] çalıştırılacak: git push -u origin main
    [12:00:06] [DRY-RUN] gh run watch <RUN_ID> --exit-status
    [12:00:07] ===== SONUÇ (VERIFY-CHECKS) =====
    [12:00:08] SONUÇ: VERIFY-CHECKS ✓ — required check adları workflow ile birebir eşleşiyor
    """).strip("\n")


class TestExtractFunction(unittest.TestCase):
    """Fonksiyon ayıklama — regresyon sinyali."""

    def test_function_present_and_well_formed(self):
        body = extract_gen_dryrun_summary()
        self.assertIn("gen_dryrun_summary() {", body)
        self.assertIn("## Komut akışı", body)
        self.assertIn("## Tam çıktı (denetim)", body)
        self.assertIn("awk", body)
        self.assertIn("sed", body)

    def test_function_uses_expected_markers(self):
        body = extract_gen_dryrun_summary()
        # awk desenleri: AŞAMA başlıkları + [DRY-RUN] komut/not ayrımı.
        # awk regex'inde [ ] köşeli parantezler \\[...\\] olarak kaçışlıdır.
        self.assertIn("===== AŞAMA|===== SONUÇ", body)
        self.assertIn("\\[DRY-RUN\\] çalıştırılacak:", body)
        self.assertIn("\\[DRY-RUN\\] ", body)


class TestSummaryStructure(unittest.TestCase):
    """Üretilen markdown'un yapısı."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dryrun-summary-")
        self.out = pathlib.Path(self.tmp.name)
        self.summary = run_generated(self.out, SAMPLE_LOG)
        self.text = self.summary.read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_generated_nonempty(self):
        self.assertTrue(self.summary.is_file())
        self.assertGreater(len(self.text), 200)

    def test_header_and_metadata(self):
        self.assertIn("# Publish Wrapper — Dry-Run Komut Akışı", self.text)
        self.assertIn("- **Repo:** ali-han-kaya/leibniz2", self.text)
        self.assertIn("- **Mod:** dry-run — hiçbir kalıcı komut çalıştırılmadı", self.text)

    def test_section_headers(self):
        self.assertIn("## Komut akışı", self.text)
        self.assertIn("## Tam çıktı (denetim)", self.text)

    def test_stage_headings_generated(self):
        """AŞAMA başlıkları ### ile markdown başlığına dönüşür."""
        self.assertIn("### AŞAMA 0", self.text)
        self.assertIn("### AŞAMA 1", self.text)
        self.assertIn("### SONUÇ", self.text)

    def test_dryrun_command_backticked(self):
        """[DRY-RUN] çalıştırılacak → backtick'li `komut` satırı."""
        self.assertIn("- `git push -u origin main`", self.text)

    def test_dryrun_note_not_backticked(self):
        """[DRY-RUN] not satırı → backtick'siz düz liste öğesi."""
        self.assertIn("- bash docs/publish_precheck.sh --skip-smoke --allow-remote", self.text)

    def test_full_output_fenced_block(self):
        """Tam çıktı fenced blokta; ham log satırı korunur."""
        self.assertIn("```text", self.text)
        self.assertIn("[DRY-RUN] çalıştırılacak: git push -u origin main", self.text)

    def test_fences_balanced(self):
        """Fenced blok dengeli — tek sayıda ``` markdown'ı bozar."""
        count = self.text.count("```")
        self.assertEqual(count % 2, 0, f"dengesiz fenced blok: {count} adet ```")
        self.assertGreaterEqual(count, 2)

    def test_timestamp_stripped_in_fence(self):
        """Fenced blokta [HH:MM:SS] zaman damgası silinir."""
        self.assertNotIn("[12:00:01]", self.text)
        self.assertIn("===== AŞAMA 0", self.text)


class TestEdgeCases(unittest.TestCase):
    """Sınır senaryoları."""

    def test_empty_log_produces_valid_md(self):
        """Boş log → yine de başlık + boş bölümler üretir (çökmez)."""
        with tempfile.TemporaryDirectory(prefix="dryrun-summary-") as tmp:
            summary = run_generated(pathlib.Path(tmp), "")
            text = summary.read_text(encoding="utf-8")
            self.assertIn("# Publish Wrapper — Dry-Run Komut Akışı", text)
            self.assertIn("## Komut akışı", text)
            self.assertIn("## Tam çıktı (denetim)", text)

    def test_no_stage_lines_only_dryrun(self):
        """AŞAMA başlığı yok, yalnızca [DRY-RUN] satırları → liste üretilir."""
        log = "[12:00:00] [DRY-RUN] çalıştırılacak: git status\n"
        with tempfile.TemporaryDirectory(prefix="dryrun-summary-") as tmp:
            summary = run_generated(pathlib.Path(tmp), log)
            text = summary.read_text(encoding="utf-8")
            self.assertIn("- `git status`", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
