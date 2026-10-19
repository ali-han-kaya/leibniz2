#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_landing_repro.py — image-to-code kaynak smoke + landing build
reproducibility kapısının testleri.

Kapsanan davranışlar:
  - hermetik fixture (gerçek `build_landing.py` kopyası + minik kaynaklar +
    GERÇEK build ile üretilmiş committed artifact) → sıfır bulgu
  - kaynak smoke bulguları: eksik PNG/HTML çifti, bozuk PNG, analysis.json
    eksik/bozuk/kapsam açığı/boyut sapması, landing_src önkoşul kaybı
  - reproducibility bulguları: artifact drift (elle düzenleme), asset drift
    (committed + slides kaynağı), nondeterministik derleme (stub), build
    hatası (stub), eksik plaka, eksik PDF
  - CLI: exit 0/1/2 + --json/--out
  - gerçek repo invariant'ı: kaynaklar temiz + derleme yeniden üretilebilir
  - kapının süite bağlılığı (pre-commit + battery manifesti + coverage +
    verify-chain envanter bloğu)

Fixture notu: committed `landing.html`/`assets/` fixture'da GERÇEK derleyici
ile üretilir; böylece "temiz fixture" gerçekten temizdir ve mutasyonlar
yalnız testin hedeflediği bulguyu üretir.
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import check_landing_repro as gate  # noqa: E402

REAL_BUILD = (pathlib.Path(gate.REPO_ROOT) / "_calisma" / "landing"
              / "build_landing.py")
# Derleyici snapshot şekil sözleşmesini preview_server modülünden alır;
# yalıtılmış ağaç, üretim mirror'ı gibi modülü de taşımak zorunda.
REAL_PREVIEW_SERVER = (pathlib.Path(gate.REPO_ROOT) / "_calisma" / "CIKTI"
                       / "preview_server.py")
# Derleyici donmuş kayıt sözleşmesini de modülden alır (sidecar biçimi +
# committed PDF yolu); yalıtılmış ağaç onu da taşımak zorunda.
REAL_SEAL_RECORD = (pathlib.Path(gate.REPO_ROOT) / "_calisma" / "CIKTI"
                    / "check_seal_hash.py")

TOKENS = ":root{--fg:#e6edf3;--fg-dimmed:#8b949e;--on-accent:#ffffff;--accent:#58a6ff;}"

SRC_TEMPLATE = (
    "<!doctype html>\n"
    '<html lang="tr">\n'
    "<head>\n"
    '<meta charset="utf-8">\n'
    '<style>@import "../../design-system/tokens.css";</style>\n'
    "</head>\n"
    "<body>\n"
    '<span class="seal-big">{{SEAL_RING}} &middot; {{SEAL_CENTER}}</span>\n'
    '<img src="../../CIKTI/slides_z3/P1-a.png" alt="P1">\n'
    '<img src="../../CIKTI/slides_z3/P2.png" alt="P2">\n'
    '<img src="../../CIKTI/slides_z3/P3-a.png" alt="P3">\n'
    '<a class="btn-primary" href="#">Gonder</a>\n'
    "</body>\n"
    "</html>\n"
)

STUB_FAIL = (
    "#!/usr/bin/env python3\n"
    "import sys\n"
    "print('stub build failure', file=sys.stderr)\n"
    "sys.exit(3)\n"
)

STUB_COPY_DIFF = (
    "#!/usr/bin/env python3\n"
    "import pathlib\n"
    "import shutil\n"
    "import sys\n"
    "args = sys.argv[1:]\n"
    "def opt(name):\n"
    "    return args[args.index(name) + 1]\n"
    "out = pathlib.Path(opt('--output'))\n"
    "assets = pathlib.Path(opt('--assets-dir'))\n"
    "out.parent.mkdir(parents=True, exist_ok=True)\n"
    "assets.mkdir(parents=True, exist_ok=True)\n"
    "root = pathlib.Path(__file__).resolve().parents[2]\n"
    "committed = root / '_calisma' / 'landing' / 'landing.html'\n"
    "shutil.copyfile(committed, out)\n"
    "slides = root / '_calisma' / 'CIKTI' / 'slides_z3'\n"
    "for plate in ('P1-a.png', 'P2.png', 'P3-a.png'):\n"
    "    shutil.copyfile(slides / plate, assets / plate)\n"
    "# P1'i kasten farklı baytlarla (yeniden kodlama) yaz:\n"
    "target = assets / 'P1-a.png'\n"
    "target.write_bytes(target.read_bytes() + b'X')\n"
    "print('OK')\n"
)

STUB_NONDET = (
    "#!/usr/bin/env python3\n"
    "import pathlib\n"
    "import sys\n"
    "args = sys.argv[1:]\n"
    "def opt(name):\n"
    "    return args[args.index(name) + 1]\n"
    "out = pathlib.Path(opt('--output'))\n"
    "assets = pathlib.Path(opt('--assets-dir'))\n"
    "out.parent.mkdir(parents=True, exist_ok=True)\n"
    "assets.mkdir(parents=True, exist_ok=True)\n"
    "counter = pathlib.Path(__file__).with_name('counter.txt')\n"
    "n = int(counter.read_text()) + 1 if counter.is_file() else 1\n"
    "counter.write_text(str(n))\n"
    "out.write_text('<!doctype html><html lang=\"tr\">build %d</html>' % n,\n"
    "               encoding='utf-8')\n"
    "print('OK')\n"
)


def _png_bytes(width, height):
    """Gerçek (küçük) bir PNG: magic + IHDR + IDAT + IEND (stdlib zlib)."""
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    scanline = b"\x00" + b"\x00\x00\x00" * width
    raw = scanline * height
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height,
                                       8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) +
            chunk(b"IEND", b""))


class LandingFixture:
    """Geçici kökte image-to-code kaynakları + gerçek derleyici kopyası."""

    comp_dims = {
        "comp-1-hero": (8, 6),
        "comp-2-chain": (6, 8),
        "comp-3-proof": (12, 4),
        "comp-4-cta": (10, 10),
    }
    plate_dims = {"P1-a.png": (3, 5), "P2.png": (4, 4), "P3-a.png": (5, 3)}

    def __init__(self, root: pathlib.Path):
        self.root = root
        self.landing = root / "_calisma" / "landing"
        self.refs = self.landing / "refs"
        self.assets = self.landing / "assets"
        self.slides = root / "_calisma" / "CIKTI" / "slides_z3"
        self.pdf = root / "manuscript.pdf"
        self.sidecar = self.pdf.with_name(self.pdf.name + gate.SIDECAR_SUFFIX)

    def build_tree(self):
        self.refs.mkdir(parents=True, exist_ok=True)
        self.slides.mkdir(parents=True, exist_ok=True)
        (self.root / "design-system").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_BUILD, self.landing / "build_landing.py")
        shutil.copyfile(REAL_PREVIEW_SERVER,
                        self.root / "_calisma" / "CIKTI" / "preview_server.py")
        shutil.copyfile(REAL_SEAL_RECORD,
                        self.root / "_calisma" / "CIKTI" / "check_seal_hash.py")
        (self.root / "design-system" / "tokens.css").write_text(
            TOKENS, encoding="utf-8")
        (self.landing / "landing_src.html").write_text(
            SRC_TEMPLATE, encoding="utf-8")
        for plate, dims in self.plate_dims.items():
            (self.slides / plate).write_bytes(_png_bytes(*dims))
        for comp, dims in self.comp_dims.items():
            (self.refs / (comp + ".png")).write_bytes(_png_bytes(*dims))
            (self.refs / (comp + ".html")).write_text(
                "<!-- %s -->\n<p>fixture</p>\n" % comp, encoding="utf-8")
        analysis = {
            "pixels": [{"file": comp + ".png", "size": "%dx%d" % dims}
                       for comp, dims in self.comp_dims.items()],
            "dom": [{"file": comp + ".html", "size": None}
                    for comp in self.comp_dims],
        }
        (self.refs / "analysis.json").write_text(
            json.dumps(analysis), encoding="utf-8")
        self.pdf.write_bytes(b"%PDF-1.4 landing fixture\n%%EOF\n")
        self.write_frozen_record(gate.sha256_file(self.pdf))
        self.generate_committed()
        return self

    def write_frozen_record(self, raw):
        """Donmuş kayıt (sidecar) yaz: `# raw: <64 hex>  <name>` satırı."""
        self.sidecar.write_text(
            "%s  %s.metadata\n# raw: %s  %s\n"
            % ("a" * 64, self.pdf.name, raw, self.pdf.name),
            encoding="utf-8")

    def generate_committed(self):
        """Committed artifact'ı GERÇEK derleyiciyle üret (fixture invariant'ı).

        Mühür kaynağı donmuş kayıttır; uydurma/sentetik snapshot üretilmez.
        """
        with tempfile.TemporaryDirectory(prefix="landing-gen-"):
            rc, stderr = gate.run_build(self.root, self.sidecar,
                                        self.landing / "landing.html",
                                        self.assets)
            if rc != 0:
                raise AssertionError(
                    "fixture committed artifact uretilemedi: rc=%s %s"
                    % (rc, stderr))

    def analysis(self):
        return json.loads((self.refs / "analysis.json").read_text(
            encoding="utf-8"))

    def write_analysis(self, data):
        (self.refs / "analysis.json").write_text(
            json.dumps(data), encoding="utf-8")

    def check(self):
        return gate.check(self.root, pdf_path=self.pdf)

    def kinds(self):
        return [item["kind"] for item in self.check()[0]]


class FixtureBase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="landing-repro-"))
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        self.fx = LandingFixture(self.tmp).build_tree()


class SourceSmokeTests(FixtureBase):
    def test_clean_fixture_has_no_findings(self):
        findings, facts = self.fx.check()
        self.assertEqual(findings, [], findings)
        build = facts["build"]
        self.assertEqual(build["rebuild_sha256"][0],
                         build["rebuild_sha256"][1])
        self.assertEqual(build["rebuild_sha256"][0],
                         build["committed_sha256"])
        self.assertEqual(len(facts["sources"]["png_dims"]), 4)

    def test_missing_ref_pair_is_finding(self):
        (self.fx.refs / "comp-4-cta.html").unlink()
        self.assertIn("refs_pair_missing", self.fx.kinds())

    def test_broken_png_is_finding(self):
        (self.fx.refs / "comp-2-chain.png").write_bytes(b"not a png at all")
        self.assertIn("refs_png_invalid", self.fx.kinds())

    def test_analysis_size_mismatch_is_finding(self):
        data = self.fx.analysis()
        data["pixels"][0]["size"] = "1x1"
        self.fx.write_analysis(data)
        kinds = self.fx.kinds()
        self.assertIn("analysis_pixel_size_mismatch", kinds)

    def test_analysis_coverage_gap_is_finding(self):
        data = self.fx.analysis()
        data["pixels"] = [item for item in data["pixels"]
                          if item["file"] != "comp-3-proof.png"]
        data["dom"] = [item for item in data["dom"]
                       if item["file"] != "comp-4-cta.html"]
        self.fx.write_analysis(data)
        kinds = self.fx.kinds()
        self.assertIn("analysis_pixel_coverage_missing", kinds)
        self.assertIn("analysis_dom_coverage_missing", kinds)

    def test_missing_analysis_is_finding(self):
        (self.fx.refs / "analysis.json").unlink()
        self.assertIn("analysis_missing", self.fx.kinds())

    def test_malformed_analysis_is_finding(self):
        (self.fx.refs / "analysis.json").write_text("{ nope",
                                                    encoding="utf-8")
        self.assertIn("analysis_malformed", self.fx.kinds())

    def test_landing_src_precondition_loss_is_finding(self):
        src_path = self.fx.landing / "landing_src.html"
        src = src_path.read_text(encoding="utf-8")
        src = src.replace(gate.IMPORT_MARKER, "@import \"other.css\"")
        src = src.replace("{{SEAL_CENTER}}", "")
        src_path.write_text(src, encoding="utf-8")
        findings = self.fx.check()[0]
        tokens = [item["token"] for item in findings
                  if item["kind"] == "landing_src_precondition_missing"]
        self.assertIn(gate.IMPORT_MARKER, tokens)
        self.assertIn("{{SEAL_CENTER}}", tokens)


class ReproducibilityTests(FixtureBase):
    def test_artifact_drift_is_finding(self):
        landing = self.fx.landing / "landing.html"
        landing.write_text(landing.read_text(encoding="utf-8") +
                           "<!-- elle duzenleme -->\n", encoding="utf-8")
        findings, facts = self.fx.check()
        kinds = [item["kind"] for item in findings]
        self.assertIn("artifact_drift", kinds)
        # İki derleme yine birbirinindi — sapma committed artifact'a özgü.
        self.assertEqual(facts["build"]["rebuild_sha256"][0],
                         facts["build"]["rebuild_sha256"][1])
        drift = [item for item in findings
                 if item["kind"] == "artifact_drift"][0]
        self.assertNotEqual(drift["rebuild"], drift["committed"])

    def test_asset_drift_is_finding(self):
        (self.fx.assets / "P2.png").write_bytes(_png_bytes(9, 9))
        kinds = self.fx.kinds()
        self.assertIn("asset_drift", kinds)

    def test_plate_source_drift_is_finding(self):
        # Plaka yeniden render edildi ama committed kopya güncellenmedi.
        (self.fx.slides / "P2.png").write_bytes(_png_bytes(11, 11))
        findings = self.fx.check()[0]
        sources = [item.get("source") for item in findings
                   if item["kind"] == "asset_drift"]
        self.assertIn("committed-vs-slides", sources)
        self.assertIn("committed", sources)

    def test_staged_plate_not_copied_verbatim_is_finding(self):
        # Derleyici plakayı birebir kopyalamazsa (yeniden kodlama) yakalanır;
        # HTML birebir olduğu için yalnız plaka bulgusu çıkmalı.
        (self.fx.landing / "build_landing.py").write_text(
            STUB_COPY_DIFF, encoding="utf-8")
        findings = self.fx.check()[0]
        kinds = [item["kind"] for item in findings]
        sources = [item.get("source") for item in findings
                   if item["kind"] == "asset_drift"]
        self.assertIn("slides_z3", sources)
        self.assertNotIn("artifact_drift", kinds)

    def test_nondeterministic_build_is_finding(self):
        (self.fx.landing / "build_landing.py").write_text(
            STUB_NONDET, encoding="utf-8")
        self.assertIn("build_nondeterministic", self.fx.kinds())

    def test_build_failure_is_finding(self):
        (self.fx.landing / "build_landing.py").write_text(
            STUB_FAIL, encoding="utf-8")
        findings = self.fx.check()[0]
        failures = [item for item in findings if item["kind"] == "build_failed"]
        self.assertTrue(failures)
        self.assertIn("stub build failure", failures[0]["stderr"])

    def test_missing_plates_is_finding(self):
        (self.fx.slides / "P3-a.png").unlink()
        findings = self.fx.check()[0]
        plate_findings = [item for item in findings
                          if item["kind"] == "plates_missing"]
        self.assertTrue(plate_findings)
        self.assertIn("render_z3_slides.py", plate_findings[0]["detail"])

    def test_missing_pdf_is_finding(self):
        self.fx.pdf.unlink()
        self.assertIn("pdf_missing", self.fx.kinds())

    def test_clean_fixture_provenance_binds_committed_seal(self):
        prov_path = self.fx.landing / "landing.provenance.json"
        self.assertTrue(prov_path.is_file())
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
        html = (self.fx.landing / "landing.html").read_text(
            encoding="utf-8")
        marker = "VERIFIED • "
        at = html.find(marker)
        self.assertGreaterEqual(at, 0)
        seal = html[at + len(marker):at + len(marker) + 12]
        self.assertEqual(seal.upper(), prov["snapshot_hash"][:12].upper())
        kinds = self.fx.kinds()
        self.assertNotIn("provenance_missing", kinds)
        self.assertNotIn("provenance_drift", kinds)
        self.assertNotIn("seal_provenance_mismatch", kinds)

    def test_provenance_drift_is_finding(self):
        prov_path = self.fx.landing / "landing.provenance.json"
        data = json.loads(prov_path.read_text(encoding="utf-8"))
        data["theme"] = "light"
        prov_path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("provenance_drift", self.fx.kinds())

    def test_missing_provenance_is_finding(self):
        (self.fx.landing / "landing.provenance.json").unlink()
        self.assertIn("provenance_missing", self.fx.kinds())

    def test_seal_provenance_mismatch_is_finding(self):
        # Committed mühür elle değiştirilirse provenance bağı kopar (aynı
        # zamanda artifact_drift de çıkar — mühür HTML'in parçasıdır).
        landing = self.fx.landing / "landing.html"
        html = landing.read_text(encoding="utf-8")
        marker = "VERIFIED • "
        at = html.find(marker)
        self.assertGreaterEqual(at, 0)
        landing.write_text(
            html[:at + len(marker)] + "0" * 12 +
            html[at + len(marker) + 12:], encoding="utf-8")
        kinds = self.fx.kinds()
        self.assertIn("seal_provenance_mismatch", kinds)
        self.assertIn("artifact_drift", kinds)


class FrozenRecordTests(FixtureBase):
    """Mühür kaynağı donmuş kayıt: kapı onu önkoşul olarak arar ve
    derleyicinin hash↔PDF bağını gerçekten kurduğunu kanıtlar."""

    def test_missing_frozen_record_is_finding(self):
        self.fx.sidecar.unlink()
        kinds = self.fx.kinds()
        self.assertIn("frozen_record_missing", kinds)
        self.assertNotIn("build_failed", kinds)

    def test_stale_frozen_record_fails_the_build(self):
        # Kayıt bayat (hash ≠ committed PDF baytları) → derleyici fail-closed.
        self.fx.write_frozen_record("b" * 64)
        findings = self.fx.check()[0]
        failures = [item for item in findings
                    if item["kind"] == "build_failed"]
        self.assertTrue(failures, findings)
        self.assertIn("ayrışıyor", failures[0]["stderr"])


class CliTests(FixtureBase):
    def _run(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            rc = gate.main(argv)
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_cli_clean_json_and_out(self):
        report_path = self.tmp / "report.json"
        rc, out, err = self._run([
            "--root", str(self.tmp), "--pdf", str(self.fx.pdf),
            "--json", "--out", str(report_path)])
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(json.loads(report_path.read_text(encoding="utf-8")),
                         data)

    def test_cli_drift_is_rc1(self):
        (self.fx.assets / "P1-a.png").write_bytes(_png_bytes(7, 7))
        rc, out, _err = self._run([
            "--root", str(self.tmp), "--pdf", str(self.fx.pdf), "--json"])
        self.assertEqual(rc, 1)
        self.assertFalse(json.loads(out)["ok"])

    def test_bad_root_is_usage_error(self):
        rc, _out, err = self._run(["--root", "/nonexistent-landing-root"])
        self.assertEqual(rc, 2)
        self.assertIn("HATA", err)


class RealRepoIntegration(unittest.TestCase):
    def test_real_repository_is_reproducible(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = gate.main(["--root", str(gate.REPO_ROOT), "--json"])
        self.assertEqual(rc, 0, stdout.getvalue())
        data = json.loads(stdout.getvalue())
        build = data["facts"]["build"]
        self.assertEqual(build["rebuild_sha256"][0],
                         build["rebuild_sha256"][1])
        self.assertEqual(build["rebuild_sha256"][0],
                         build["committed_sha256"])
        self.assertEqual(build["assets"]["staged"],
                         sorted(gate.PLATES))
        self.assertEqual(build["assets"]["committed"],
                         sorted(gate.PLATES))
        self.assertEqual(len(data["facts"]["sources"]["png_dims"]),
                         len(gate.COMPS))


class WiringTests(unittest.TestCase):
    def test_gate_is_wired_into_the_suite(self):
        precommit = (gate.REPO_ROOT / ".pre-commit-config.yaml").read_text(
            encoding="utf-8")
        self.assertIn("id: check-landing-repro", precommit)
        self.assertIn("check_landing_repro.py", precommit)

        manifest = (HERE / "check_unit_tests.list").read_text(
            encoding="utf-8")
        self.assertIn("test_check_landing_repro.py", manifest)

        coverage = (HERE / "test_coverage_report.py").read_text(
            encoding="utf-8")
        self.assertIn('"check-landing-repro"', coverage)
        self.assertIn("test_check_landing_repro.py", coverage)

        skill = (gate.REPO_ROOT / "skills" / "verify-chain"
                 / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("check-landing-repro", skill)


if __name__ == "__main__":
    unittest.main()
