#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_brand_mirror_gate.py — marka-mirror drift kapısının birim testleri.

Kapı: design-system/scripts/check_brand_mirrors.py + brand_mirrors.list.
Sözleşme (hepsi fail-closed): roster bütünlüğü (R1), kayıt bütünlüğü (R2),
roster kapsamı (R3: kayıtsız/exempt'siz mirror yok), checker rc=0 (R4) ve
pin eşleşmesi + vacuous-PASS yasağı (R5).

Test izolasyonu: R1-R5 vakaları kendi sahte repo ağacını kurar (sürücü
roster'ı VE mirroları --root'tan okur); gerçek çalışma ağacına yazılmaz.
Son iki vaka gerçek repo üzerinde koşar: pinlerin canlı mirror'larla
birebir olduğunu ve hook wiring'inin config'te durduğunu kanıtlar.

Wiring: bu modül check-unit-tests bataryasındadır ve HOOK_COVERAGE'ta
`check-brand-mirrors` hook'una bağlanır.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
DRIVER = REPO / "design-system" / "scripts" / "check_brand_mirrors.py"
ROSTER_NAME = "brand_mirrors.list"
PRECOMMIT_CONFIG = REPO / ".pre-commit-config.yaml"
MANIFEST = HERE / "check_unit_tests.list"
COVERAGE = HERE / "test_coverage_report.py"
THIS_FILE = "test_brand_mirror_gate.py"

# Üretimdeki dört mirror'ın pinleri; fixture'lar aynı adları kullanır ki
# wiring testi ile canlı pin testi birbirini teyit etsin.
PROD_PINS = {"stripe": 710, "linear": 398, "primer": 2051, "vercel": 19}

CHECKER_TEMPLATE = """#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
{body}
sys.exit({rc})
"""


# ── fixture yardımcıları ────────────────────────────────────────────────────

def _write_checker(path: pathlib.Path, report=None, rc=0, raw="raw.css",
                   message=None):
    """Sahte checker: OK — N satırı ya da verilen mesaj + rc."""
    if message is not None:
        body = f"print({message!r})"
    elif report is not None:
        line = (f"OK \u2014 {report} Fake tokens verbatim against {raw} "
                f"(tokens.css + tokens.json in sync)")
        body = f"print({line!r})"
    else:
        body = "print('fake checker: karsilastirma yapildi')"
    path.write_text(CHECKER_TEMPLATE.format(body=body, rc=rc),
                    encoding="utf-8")


def _spec(name, pin=None, raw=None, rc=0, report=None, message=None,
          with_raw=True, with_checker=True):
    pin = PROD_PINS.get(name, 100) if pin is None else pin
    return {
        "name": name,
        "pin": pin,
        "raw": raw or ("raw.json" if name == "vercel" else "raw.css"),
        "checker": f"scripts/check_{name}_tokens.py",
        "rc": rc,
        "report": pin if report is None else report,
        "message": message,
        "with_raw": with_raw,
        "with_checker": with_checker,
    }


def _four_specs():
    return [_spec(name) for name in ("stripe", "linear", "primer", "vercel")]


def _roster_lines(specs, exempt=None):
    lines = [f"{s['name']}  {s['raw']}  {s['pin']}  {s['checker']}"
             for s in specs]
    for name, reason in (exempt or {}).items():
        lines.append(f"# exempt: {name} \u2014 {reason}")
    return lines


def _fake_repo(specs, roster_lines="auto", with_roster=True):
    """Sahte repo: design-system/scripts/{driver,roster} + mirror'lar."""
    td = pathlib.Path(tempfile.mkdtemp())
    scripts = td / "design-system" / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy(DRIVER, scripts / DRIVER.name)
    for spec in specs:
        mirror = td / "design-system" / spec["name"]
        (mirror / "scripts").mkdir(parents=True)
        if spec["with_raw"]:
            (mirror / spec["raw"]).write_text("--fake: 1;\n", encoding="utf-8")
        (mirror / "tokens.css").write_text(":root { --fake: 1; }\n",
                                           encoding="utf-8")
        (mirror / "tokens.json").write_text(
            '{"tokens": {"fake": {"--fake": "1"}}}\n', encoding="utf-8")
        if spec["with_checker"]:
            _write_checker(mirror / spec["checker"], report=spec["report"],
                           rc=spec["rc"], raw=spec["raw"],
                           message=spec["message"])
    if with_roster:
        lines = _roster_lines(specs, exempt={}) if roster_lines == "auto" \
            else roster_lines
        (scripts / ROSTER_NAME).write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")
    return td


def _run_driver(root: pathlib.Path, roster=True):
    cmd = [sys.executable, str(root / "design-system" / "scripts"
                               / DRIVER.name), "--root", str(root)]
    if not roster:
        cmd += ["--roster", str(root / "design-system" / "scripts" / "yok.list")]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                          stdin=subprocess.DEVNULL)


class _FixtureCase(unittest.TestCase):
    def setUp(self):
        self._dirs = []

    def tearDown(self):
        for td in self._dirs:
            shutil.rmtree(td, ignore_errors=True)

    def make(self, specs, roster_lines="auto", with_roster=True):
        td = _fake_repo(specs, roster_lines=roster_lines,
                        with_roster=with_roster)
        self._dirs.append(td)
        return td


# ── R1/R2/R3: yapısal (exit 2) ──────────────────────────────────────────────

class StructuralFailClosedTest(_FixtureCase):
    def test_all_four_pass(self):
        r = _run_driver(self.make(_four_specs()))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("4/4", r.stdout)
        for name in PROD_PINS:
            self.assertIn(f"design-system/{name}", r.stdout)

    def test_missing_roster_blocks(self):
        td = self.make(_four_specs(), with_roster=False)
        r = _run_driver(td)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("roster yok", r.stderr)

    def test_below_min_entry_blocks(self):
        """>4 giriş beklenmez ama 4'ün altı toplu-silme şüphesidir."""
        specs = _four_specs()[:2]
        td = self.make(specs)
        r = _run_driver(td)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("roster yetersiz", r.stderr)

    def test_registered_mirror_missing_on_disk_blocks(self):
        specs = _four_specs()
        roster = _roster_lines(specs) + [
            f"figma  raw.css  42  scripts/check_figma_tokens.py"]
        r = _run_driver(self.make(specs, roster_lines=roster))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("design-system/figma", r.stderr)

    def test_registered_raw_missing_blocks(self):
        specs = _four_specs()
        specs[0]["with_raw"] = False  # stripe raw'ı silindi
        r = _run_driver(self.make(specs))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("raw.css", r.stderr)
        self.assertIn("design-system/stripe", r.stderr)

    def test_registered_checker_missing_blocks(self):
        specs = _four_specs()
        specs[2]["with_checker"] = False  # primer checker'ı silindi
        r = _run_driver(self.make(specs))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("check_primer_tokens.py", r.stderr)

    def test_unregistered_mirror_blocks(self):
        """tokens.json + raw.* taşıyan yeni mirror kayıtsız kalamaz."""
        specs = _four_specs()
        td = self.make(specs)
        new_mirror = td / "design-system" / "figma"
        (new_mirror / "scripts").mkdir(parents=True)
        (new_mirror / "raw.css").write_text("--x: 1;\n", encoding="utf-8")
        (new_mirror / "tokens.json").write_text("{}\n", encoding="utf-8")
        r = _run_driver(td)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("kayıtsız mirror", r.stderr)
        self.assertIn("figma", r.stderr)

    def test_exempt_mirror_is_allowed_with_reason(self):
        specs = _four_specs()
        td = self.make(specs)
        new_mirror = td / "design-system" / "figma"
        (new_mirror / "scripts").mkdir(parents=True)
        (new_mirror / "raw.css").write_text("--x: 1;\n", encoding="utf-8")
        (new_mirror / "tokens.json").write_text("{}\n", encoding="utf-8")
        (td / "design-system" / "scripts" / ROSTER_NAME).write_text(
            "\n".join(_roster_lines(specs, exempt={"figma": "ayri sozlesme"}))
            + "\n", encoding="utf-8")
        r = _run_driver(td)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("exempt: figma", r.stdout)

    def test_exempt_without_reason_blocks(self):
        specs = _four_specs()
        roster = _roster_lines(specs) + ["# exempt: figma"]
        r = _run_driver(self.make(specs, roster_lines=roster))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("exempt", r.stderr)

    def test_stale_exempt_entry_blocks(self):
        """Diskte olmayan mirror için exempt satırı = bayat kayıt."""
        specs = _four_specs()
        roster = _roster_lines(specs, exempt={"figma": "hayali mirror"})
        r = _run_driver(self.make(specs, roster_lines=roster))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("bayat kayıt", r.stderr)

    def test_path_escape_in_roster_blocks(self):
        specs = _four_specs()
        roster = _roster_lines(specs)
        roster[0] = ("stripe  ../../etc/passwd  710  "
                     "scripts/check_stripe_tokens.py")
        r = _run_driver(self.make(specs, roster_lines=roster))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("dışına çıkamaz", r.stderr)


# ── R4/R5: drift + pin (exit 1) ─────────────────────────────────────────────

class DriftFailClosedTest(_FixtureCase):
    def test_checker_drift_blocks_and_shows_output(self):
        specs = _four_specs()
        specs[1]["rc"] = 1
        specs[1]["message"] = "LINEAR TOKEN DRIFT: --x mismatch"
        r = _run_driver(self.make(specs))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("design-system/linear", r.stderr)
        self.assertIn("LINEAR TOKEN DRIFT", r.stderr)
        self.assertIn("commit BLOKE", r.stderr)

    def test_pin_mismatch_requires_explicit_re_pin(self):
        specs = _four_specs()
        specs[0]["report"] = 711  # mirror değişti, pin güncellenmedi
        r = _run_driver(self.make(specs))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("pin 710 != gözlenen 711", r.stderr)
        self.assertIn(ROSTER_NAME, r.stderr)

    def test_vacuous_zero_token_pass_blocks(self):
        specs = _four_specs()
        specs[3]["report"] = 0
        r = _run_driver(self.make(specs))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("0 token", r.stderr)

    def test_missing_ok_line_blocks(self):
        specs = _four_specs()
        specs[2]["report"] = None  # OK satırı yok, rc=0
        r = _run_driver(self.make(specs))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("üretmedi", r.stderr)

    def test_ok_line_requires_dash_number_shape(self):
        """'OK' kelimesi yetmez: sayısal doğrulama kanıtı şart."""
        specs = _four_specs()
        specs[0]["message"] = "OK, her sey yolunda"
        r = _run_driver(self.make(specs))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("üretmedi", r.stderr)


# ── gerçek repo + wiring ────────────────────────────────────────────────────

class RealRepoAndWiringTest(unittest.TestCase):
    def test_real_mirrors_pass_with_pinned_counts(self):
        """Canlı mirror'lar pinlerle birebir: roster bayatlamamış."""
        r = subprocess.run([sys.executable, str(DRIVER)], capture_output=True,
                           text=True, timeout=120, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("4/4", r.stdout)
        for name, pin in PROD_PINS.items():
            self.assertIn(f"design-system/{name}", r.stdout)
            self.assertIn(f"{pin}/{pin}", r.stdout)

    def test_roster_matches_production_pins(self):
        roster = (REPO / "design-system" / "scripts" / ROSTER_NAME).read_text(
            encoding="utf-8")
        for name, pin in PROD_PINS.items():
            self.assertRegex(
                roster,
                rf"(?m)^{name}\s+raw\.(css|json)\s+{pin}\s+scripts/check_{name}_tokens\.py\s*$")

    def test_hook_is_wired_change_triggered_fail_closed(self):
        text = PRECOMMIT_CONFIG.read_text(encoding="utf-8")
        self.assertIn("- id: check-brand-mirrors", text)
        start = text.index("- id: check-brand-mirrors")
        block = text[start:]
        nxt = block.find("\n      - id: ")
        block = block[:nxt] if nxt != -1 else block

        self.assertIn(
            "entry: python3 design-system/scripts/check_brand_mirrors.py", block)
        self.assertIn("pass_filenames: false", block)
        self.assertIn("stages: [pre-commit]", block)
        # Değişim-farkında tetikleme: mirror surface'i değişmedikçe koşmaz.
        # (Yalnız anahtar aranır; açıklama metninde 'always_run yok' geçer.)
        self.assertNotRegex(block, r"(?m)^\s*always_run:")

        m = re.search(r"files:\s*(\S.*)", block)
        self.assertIsNotNone(m, f"files: filtresi yok:\n{block}")
        pattern = re.compile(m.group(1).strip().strip('"'))
        for path in ("design-system/stripe/tokens.css",
                     "design-system/linear/raw.css",
                     "design-system/vercel/raw.json",
                     "design-system/scripts/brand_mirrors.list"):
            self.assertTrue(pattern.search(path),
                            f"filtre mirror yolunu kaçırıyor: {path}")
        for path in ("apps/dashboard-next/app/page.tsx",
                     "_calisma/CIKTI/test_brand_mirror_gate.py"):
            self.assertFalse(pattern.search(path),
                             f"filtre ilgisiz yolu yakalıyor: {path}")

        self.assertTrue(DRIVER.is_file(), "hook entry diskte yok")

    def test_gate_is_registered_in_manifest_and_coverage(self):
        manifest = [ln.strip() for ln in
                    MANIFEST.read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.startswith("#")]
        self.assertIn(THIS_FILE, manifest,
                      "check_unit_tests.list senkron değil "
                      "(remedy: sync_check_unit_tests.py --update)")
        coverage = COVERAGE.read_text(encoding="utf-8")
        self.assertRegex(
            coverage,
            r'"check-brand-mirrors":\s*\[\s*"%s"\s*\]' % re.escape(THIS_FILE))


if __name__ == "__main__":
    unittest.main()
