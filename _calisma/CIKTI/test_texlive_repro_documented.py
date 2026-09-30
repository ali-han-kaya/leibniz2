#!/usr/bin/env python3
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "_calisma" / "CIKTI" / "texlive_determinism_test.sh"
HOOK = ROOT / "_calisma" / "CIKTI" / "texlive_determinism_hook.sh"
PRE_COMMIT_CONFIG = ROOT / ".pre-commit-config.yaml"
REPORT_REL = "logs/texlive_determinism_report.txt"
PACKAGE = ROOT / "_calisma" / "V5_ICERIK" / "TESLIM_V5_FINAL_2026-08-17" / "stoic_hume_package" / "Stoic_Hume_Formal_Section_2026-08-17"
DOC = PACKAGE / "REPRODUCIBILITY.md"
MAKEFILE = ROOT / "docs" / "Makefile.tectonic"


class TestDocumentedTexliveRepro(unittest.TestCase):
    def test_documented_contract_and_hash_report(self):
        text = DOC.read_text(encoding="utf-8")
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("tectonic", text.lower())
        self.assertIn("SOURCE_DATE_EPOCH", text)
        self.assertIn("SOURCE_DATE_EPOCH", makefile)
        self.assertIn("--outdir", makefile)
        self.assertIn("make pdf", text)

        with tempfile.TemporaryDirectory(prefix="texlive-doc-") as td:
            root = Path(td)
            source = root / "sample.tex"
            source.write_text("\\documentclass{article}\\begin{document}x\\end{document}\n")
            tools = root / "tools"
            tools.mkdir()
            pdf = b"deterministic-pdf"
            # Gerçek motor her geçişte bir .log bırakır; çok-geçiş
            # varsayılanında (Faz 4) script son geçiş logunda 'Rerun to get'
            # KALMADIĞINI denetler — stub bunu taklit etmeli.
            stub = (
                "#!/bin/sh\n"
                "for arg in \"$@\"; do case \"$arg\" in *.tex) src=\"$arg\";; esac; done\n"
                "out=$(basename -- \"${src:-sample.tex}\" .tex).pdf; "
                "printf 'deterministic-pdf' > \"$out\"\n"
                "printf 'no rerun needed\\n' > \"${out%.pdf}.log\"\n"
            )
            for name in ("tectonic", "pdflatex"):
                path = tools / name
                path.write_text(stub, encoding="utf-8")
                path.chmod(0o755)
            report = root / "report.txt"
            env = dict(os.environ, TEX_SOURCE=str(source), TECTONIC_BIN=str(tools / "tectonic"),
                       TEXLIVE_BIN=str(tools), DETERMINISM_OUT=str(report),
                       SOURCE_DATE_EPOCH="123")
            result = subprocess.run(["bash", str(SCRIPT)], env=env,
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report_text = report.read_text(encoding="utf-8")
            expected = hashlib.sha256(pdf).hexdigest()
            self.assertIn(f"tectonic_sha256={expected}", report_text)
            self.assertIn(f"texlive_run1_sha256={expected}", report_text)
            self.assertIn(f"texlive_run2_sha256={expected}", report_text)
            self.assertIn("source_date_epoch=123", report_text)
            self.assertIn("verdict=PASS", report_text)


class TestTexliveReportPersistence(unittest.TestCase):
    """Rapor yolu sözleşmesi: varsayılan logs/ (precommit-logs artifact'ı).

    coe A sınıfı maskeleme regresyonu: rapor eskiden GITIGNORE'LU
    docs/ci_simulate/texlive_determinism/ altına yazılıyordu — CI'da hiçbir
    upload'ın path'i onu kapsamıyordu, yani PASS kanıtı (3 sha256 + verdict)
    runner workspace'inde ölüyordu. Artık varsayılan logs/ (precommit-logs
    artifact'ı) ve kanıt ayrıca stdout'a (logs/precommit.log) basılır.
    """

    def _stage(self, td):
        """Script'i temsili repo köküne kopyala → ROOT = td (gerçek logs/ kirletilmez)."""
        dest = Path(td) / "_calisma" / "CIKTI"
        dest.mkdir(parents=True)
        shutil.copy2(SCRIPT, dest / SCRIPT.name)
        return dest / SCRIPT.name

    def _stub_tools(self, td):
        tools = Path(td) / "tools"
        tools.mkdir()
        # .log: çok-geçiş modunun (default) 'son geçiş logu' denetimi için;
        # gerçek pdflatex de her geçişte log yazar.
        stub = (
            "#!/bin/sh\n"
            "for arg in \"$@\"; do case \"$arg\" in *.tex) src=\"$arg\";; esac; done\n"
            "out=$(basename -- \"${src:-sample.tex}\" .tex).pdf; "
            "printf 'deterministic-pdf' > \"$out\"\n"
            "printf 'no rerun needed\\n' > \"${out%.pdf}.log\"\n"
        )
        for name in ("tectonic", "pdflatex"):
            path = tools / name
            path.write_text(stub, encoding="utf-8")
            path.chmod(0o755)
        return tools

    def _run(self, td, script, tools, env_extra=None):
        source = Path(td) / "sample.tex"
        source.write_text("\\documentclass{article}\\begin{document}x\\end{document}\n")
        env = dict(os.environ, TEX_SOURCE=str(source),
                   TECTONIC_BIN=str(tools / "tectonic"),
                   TEXLIVE_BIN=str(tools), SOURCE_DATE_EPOCH="123")
        env.pop("DETERMINISM_OUT", None)
        env.update(env_extra or {})
        return subprocess.run(["bash", str(script)], env=env, cwd=td,
                              capture_output=True, text=True)

    def test_default_report_path_is_under_logs(self):
        with tempfile.TemporaryDirectory(prefix="texlive-logs-") as td:
            script = self._stage(td)
            tools = self._stub_tools(td)
            r = self._run(td, script, tools)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            report = Path(td) / REPORT_REL
            self.assertTrue(report.is_file(),
                            f"varsayılan rapor {REPORT_REL} altında olmalı "
                            "(precommit-logs artifact'ı logs/ dizinini yükler)")
            self.assertIn("verdict=PASS", report.read_text(encoding="utf-8"))
            self.assertFalse((Path(td) / "docs" / "ci_simulate").exists(),
                             "gitignore'lu docs/ci_simulate/ yolu kullanılmamalı "
                             "— CI'da hiçbir upload kapsamında değil")

    def test_evidence_is_also_printed_to_stdout(self):
        with tempfile.TemporaryDirectory(prefix="texlive-stdout-") as td:
            script = self._stage(td)
            tools = self._stub_tools(td)
            r = self._run(td, script, tools)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("verdict=PASS", r.stdout,
                          "kanıt stdout'a da basılmalı — artifact indirilmese "
                          "bile logs/precommit.log'da görünür")
            self.assertIn("tectonic_sha256=", r.stdout)

    def test_determinism_out_override_still_wins(self):
        with tempfile.TemporaryDirectory(prefix="texlive-override-") as td:
            script = self._stage(td)
            tools = self._stub_tools(td)
            custom = Path(td) / "custom_report.txt"
            r = self._run(td, script, tools, {"DETERMINISM_OUT": str(custom)})
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(custom.is_file(), "DETERMINISM_OUT override korunmalı")
            self.assertIn("verdict=PASS", custom.read_text(encoding="utf-8"))

    def test_hook_and_config_point_at_the_persisted_path(self):
        """İki yanlış referans pinlenir: hook başlığı ve pre-commit açıklaması."""
        hook = HOOK.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(REPORT_REL, hook)
        self.assertNotIn("docs/ci_simulate", hook)
        self.assertIn(REPORT_REL, script)
        self.assertIn('DETERMINISM_OUT:-$ROOT/logs/texlive_determinism_report.txt',
                      script, "varsayılan OUT logs/ altında olmalı")
        # Yorum satırları eski yolu (kaldırma gerekçesi olarak) anabilir —
        # pin KOD üzerinde: hiçbir çalıştırılabilir satır eski yolu kullanmamalı.
        code = "\n".join(l for l in script.splitlines()
                         if not l.lstrip().startswith("#"))
        self.assertNotIn("docs/ci_simulate", code)

        config = PRE_COMMIT_CONFIG.read_text(encoding="utf-8")
        start = config.index("- id: texlive-determinism")
        rest = config[start:]
        end = rest.find("\n      - id:", 1)
        block = rest if end == -1 else rest[:end]
        self.assertIn(REPORT_REL, block,
                      "pre-commit açıklaması gerçek rapor yolunu göstermeli")
        self.assertNotIn(".freebuff/sim/", block,
                         "bayat .freebuff/sim/ referansı kaldırılmalı")


if __name__ == "__main__":
    unittest.main()
