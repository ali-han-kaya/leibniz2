#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""test_mirror_bridges.py — marka aynası @theme köprülerinin birim testleri.

Kapı: design-system/scripts/check_mirror_bridges.py
Üretici: design-system/scripts/generate_mirror_tailwind.py

İki yarı:
  * GERÇEK AĞAÇ — dört köprü de diske yazılı, kapı yeşil, temel paletle
    ayrıklık jeneratörden BAĞIMSIZ yeniden hesaplanır, hook wiring'i
    config'te durur.
  * SAHTE AĞAÇ — köprü eksikse yapısal hata (rc 2); elle düzenlenmiş köprü
    drift (rc 1). Kapsam/ad kuralları sentetik bir ayna üzerinde doğrudan
    jeneratör fonksiyonlarıyla sınanır (determinizm + gerekçe defteri).

Kapının B3–B7 sözleşmeleri disk üzerinde B2 tarafından kapsandığı için
(elle değişen dosya zaten birebirlik denetimine takılır), o yardımcıların
kendisi doğrudan çağrılarak test edilir — jeneratörde REGRESYON olursa
kapının yine de yakalayacağını kanıtlamak üzere.

Wiring: bu modül check-unit-tests bataryasındadır ve HOOK_COVERAGE'ta
`check-mirror-bridges` hook'una bağlanır.
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
SCRIPTS = REPO / "design-system" / "scripts"
GATE = SCRIPTS / "check_mirror_bridges.py"
GENERATOR = SCRIPTS / "generate_mirror_tailwind.py"
ROSTER_NAME = "brand_mirrors.list"
ROSTER = SCRIPTS / ROSTER_NAME
PRECOMMIT_CONFIG = REPO / ".pre-commit-config.yaml"
MANIFEST = HERE / "check_unit_tests.list"
COVERAGE = HERE / "test_coverage_report.py"
THIS_FILE = "test_mirror_bridges.py"
MIRRORS = ("stripe", "linear", "primer", "vercel")
HOOK_ID = "check-mirror-bridges"

sys.path.insert(0, str(SCRIPTS))
import check_mirror_bridges as gate  # noqa: E402
import generate_mirror_tailwind as gen  # noqa: E402

THEME_LINE_RE = re.compile(r"^  --[a-z-]+-([a-z0-9]+)-[a-z0-9-]+: var\(--",
                           re.M)


# ── yardımcılar ────────────────────────────────────────────────────────────

def _run(cmd, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable] + cmd, capture_output=True,
                          text=True, timeout=120, cwd=cwd)


def _synthetic_root(tokens: dict, mirror: str = "synth") -> pathlib.Path:
    """Geçici repo: tek ayna (tokens.css) + 4 girişli roster."""
    td = pathlib.Path(tempfile.mkdtemp())
    mirror_dir = td / "design-system" / mirror
    mirror_dir.mkdir(parents=True)
    body = "\n".join("  %s: %s;" % (k, v) for k, v in tokens.items())
    (mirror_dir / "tokens.css").write_text(
        "/* synthetic */\n:root {\n%s\n}\n" % body, encoding="utf-8")
    # temel palet (ayrıklık denetimi için) + roster'ın <4 giriş kuralı
    base = td / "design-system"
    (base / "tokens.css").write_text(":root {\n  --bg: #0e1116;\n}\n",
                                     encoding="utf-8")
    (base / "tailwind.css").write_text(
        "@theme {\n  --color-bg: var(--bg);\n}\n", encoding="utf-8")
    names = [mirror, "m2", "m3", "m4"]
    lines = ["# synthetic roster"]
    for name in names:
        d = base / name
        d.mkdir(exist_ok=True)
        (d / "tokens.json").write_text("{}\n", encoding="utf-8")
        (d / "raw.css").write_text("/* raw */\n", encoding="utf-8")
        if name != mirror:
            (d / "tokens.css").write_text(":root {\n  --x: #fff;\n}\n",
                                          encoding="utf-8")
            # roster'ın diğer girişleri de köprülü olmalı: kapı, rostera giren
            # HER aynayı denetler (köprüsüz ayna = yapısal hata).
            (d / gen.BRIDGE_NAME).write_text(gen.render(name, td),
                                             encoding="utf-8")
        lines.append("%s  raw.css  1  scripts/check.py" % name)
    roster = td / "roster.list"
    roster.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return td


MIRROR_LINE_RE = re.compile(r"^  --[a-z-]+-[a-z0-9]+(?:-[a-z0-9]+)*: var\(--",
                            re.M)


def _base_names() -> set:
    names = set(n for n, _ in gen.PAIR.findall(
        (REPO / "design-system" / "tokens.css").read_text(encoding="utf-8")))
    bridge = (REPO / "design-system" / "tailwind.css").read_text(encoding="utf-8")
    names.update(n for n, _ in gen.PAIR.findall(
        gate.BLOCK_RE["@theme"].search(bridge).group(1)))
    return names


def _bridge_text(mirror: str) -> str:
    return (REPO / "design-system" / mirror / gen.BRIDGE_NAME).read_text(
        encoding="utf-8")


def _hook(hook_id: str) -> dict:
    try:
        import yaml
    except ImportError:  # pragma: no cover
        raise unittest.SkipTest("pyyaml yok — hook wiring okunamadı")
    data = yaml.safe_load(PRECOMMIT_CONFIG.read_text(encoding="utf-8"))
    for repo in data.get("repos", []):
        for hook in repo.get("hooks", []):
            if hook["id"] == hook_id:
                return hook
    raise AssertionError("hook yok: %s" % hook_id)


# ── gerçek ağaç ────────────────────────────────────────────────────────────

class RealTreeTest(unittest.TestCase):
    def test_gate_passes_on_real_tree(self):
        r = _run([str(GATE)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK — 4/4 marka @theme köprüsü", r.stdout)
        for mirror in MIRRORS:
            self.assertIn("design-system/%s" % mirror, r.stdout)

    def test_generator_check_mode_is_clean(self):
        r = _run([str(GENERATOR), "--check"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK — 4/4 marka köprüsü jeneratörle birebir", r.stdout)

    def test_every_roster_mirror_has_a_generated_bridge(self):
        entries, _exempt = gen.load_roster(ROSTER)
        self.assertEqual(sorted(e["dir"] for e in entries), sorted(MIRRORS))
        for mirror in MIRRORS:
            text = _bridge_text(mirror)
            self.assertIn("GENERATED, DO NOT EDIT", text)
            self.assertIn("design-system/%s/%s" % (mirror, gen.BRIDGE_NAME), text)

    def test_real_bridges_are_disjoint_from_base_palette(self):
        """Temel palet ayrıklığı — kapıdan bağımsız yeniden hesaplanır.

        Bu, köprülerin var oluş sebebi: linear/vercel `--color-*` adları
        ön-eksiz üretilseydi `bg-bg`/`bg-accent` marka paletine kayardı.
        """
        base = _base_names()
        self.assertIn("--bg", base)
        self.assertIn("--color-bg", base)
        for mirror in MIRRORS:
            emitted = set()
            for selector in (":root", "@theme"):
                emitted.update(gate.parse_block(_bridge_text(mirror), selector))
            clash = emitted & base
            self.assertEqual(clash, set(), "%s temel paletle çakışıyor: %s"
                             % (mirror, sorted(clash)))

    def test_theme_values_are_var_references_only(self):
        for mirror in MIRRORS:
            theme = gate.parse_block(_bridge_text(mirror), "@theme")
            self.assertTrue(theme, mirror)
            for name, value in theme.items():
                self.assertIsNotNone(gate.ONLY_VAR_RE.match(value),
                                     "%s literal taşıyor: %s=%s"
                                     % (mirror, name, value))
                self.assertTrue(value.startswith("var(--%s-" % mirror),
                                "%s: %s" % (mirror, value))

    def test_theme_line_count_matches_alias_ledger(self):
        """@theme satır sayısı = defterdeki `aliases` (grup filtresi regresyonu)."""
        for mirror in MIRRORS:
            text = _bridge_text(mirror)
            block = gate.BLOCK_RE["@theme"].search(text).group(1)
            ledger = gate.parse_ledger(text)
            self.assertEqual(len(MIRROR_LINE_RE.findall(block)),
                             ledger["aliases"], mirror)
            self.assertGreater(ledger["aliases"], 0, mirror)

    def test_coverage_identity_holds_on_real_tree(self):
        for mirror in MIRRORS:
            info = gen.analyse(mirror, REPO)
            self.assertEqual(len(info["plans"]) + len(info["skipped"]),
                             len(info["tokens"]), mirror)
            self.assertEqual(set(info["plans"].values()) | set(info["skipped"]),
                             set(info["tokens"]), mirror)

    def test_hook_wiring(self):
        hook = _hook(HOOK_ID)
        self.assertEqual(hook["entry"],
                         "python3 design-system/scripts/check_mirror_bridges.py")
        self.assertEqual(hook["files"], "^design-system/")
        self.assertEqual(hook["stages"], ["pre-commit"])
        self.assertFalse(hook.get("always_run", False),
                         "değişim-farkında kalmalı (always_run yok)")

    def test_manifest_and_coverage_registration(self):
        listed = [ln.strip() for ln in MANIFEST.read_text(
            encoding="utf-8").splitlines()]
        self.assertIn(THIS_FILE, listed)
        sys.path.insert(0, str(HERE))
        import test_coverage_report as cov
        self.assertIn(HOOK_ID, cov.HOOK_COVERAGE)
        self.assertIn(THIS_FILE, cov.HOOK_COVERAGE[HOOK_ID])
        self.assertIn(THIS_FILE, cov.HOOK_COVERAGE["check-unit-tests"])


# ── sahte ağaç: kapı fail-closed mu? ───────────────────────────────────────

class GateFailClosedTest(unittest.TestCase):
    def _root_with_bridge(self, mirror="synth"):
        tokens = {"--hds-color-util-white": "#ffffff"}
        td = _synthetic_root(tokens, mirror)
        (td / "design-system" / mirror / gen.BRIDGE_NAME).write_text(
            gen.render(mirror, td), encoding="utf-8")
        return td, mirror

    def _gate(self, td):
        return _run([str(GATE), "--root", str(td),
                     "--roster", str(td / "roster.list")])

    def test_missing_bridge_is_structural(self):
        td = _synthetic_root({"--hds-color-x": "#fff"})
        try:
            r = self._gate(td)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("köprü yok", r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_hand_edited_bridge_is_drift(self):
        td, mirror = self._root_with_bridge()
        try:
            path = td / "design-system" / mirror / gen.BRIDGE_NAME
            path.write_text(path.read_text(encoding="utf-8").replace(
                "#ffffff", "#000000"), encoding="utf-8")
            r = self._gate(td)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("birebir değil", r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_unknown_mirror_cannot_silently_produce_a_bridge(self):
        """Roster'a yeni ayna girerse köprüsüz kalamaz (exit 2)."""
        td = _synthetic_root({"--hds-color-x": "#fff"})
        try:
            extra = td / "design-system" / "m9"
            extra.mkdir()
            for name, body in (("tokens.css", ":root {\n  --x: #fff;\n}\n"),
                               ("tokens.json", "{}\n"),
                               ("raw.css", "/* raw */\n")):
                (extra / name).write_text(body, encoding="utf-8")
            roster = td / "roster.list"
            roster.write_text(roster.read_text(encoding="utf-8")
                              + "m9  raw.css  1  scripts/check.py\n",
                              encoding="utf-8")
            r = self._gate(td)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("m9", r.stderr)
        finally:
            shutil.rmtree(td, ignore_errors=True)


# ── kapı sözleşmeleri doğrudan (jeneratör regresyonuna karşı) ──────────────

class ContractHelpersTest(unittest.TestCase):
    def test_base_disjointness_rejects_overlap(self):
        with self.assertRaises(gate.Violation):
            gate.check_base_disjoint({"--bg", "--synth-color-x"}, {"--bg"})
        gate.check_base_disjoint({"--synth-color-x"}, {"--bg"})

    def test_parse_block_rejects_duplicate_names(self):
        with self.assertRaises(gate.Violation):
            gate.parse_block(":root {\n  --a: 1;\n  --a: 2;\n}\n", ":root")

    def test_blocks_guard_rejects_stray_selector(self):
        text = ("/* c */\n:root {\n  --a: 1;\n}\n@theme {\n  --b: var(--a);\n}\n"
                ".leak { color: red; }\n")
        with self.assertRaises(gate.Violation):
            gate.check_blocks(text)

    def test_blocks_guard_requires_single_blocks(self):
        text = ":root {\n}\n:root {\n}\n@theme {\n}\n"
        with self.assertRaises(gate.Violation):
            gate.check_blocks(text)

    def test_ledger_parser_requires_counts(self):
        with self.assertRaises(gate.Violation):
            gate.parse_ledger("/* yorum */\n:root {}\n")
        ledger = gate.parse_ledger(
            "/* ── sayımlar ──\n *   tokens=1\n *   skip:class-number=1\n */")
        self.assertEqual(ledger["tokens"], 1)
        self.assertEqual(ledger["skip:class-number"], 1)

    def test_only_var_regex_rejects_literals(self):
        self.assertIsNotNone(gate.ONLY_VAR_RE.match("var(--synth-color-x)"))
        self.assertIsNotNone(gate.ONLY_VAR_RE.match("var(--a, #fff)"))
        self.assertIsNone(gate.ONLY_VAR_RE.match("#ffffff"))
        self.assertIsNone(gate.ONLY_VAR_RE.match("var(--a) var(--b)"))


# ── jeneratör kapsam/ad kuralları (sentetik ayna) ──────────────────────────

class GeneratorScopeTest(unittest.TestCase):
    TOKENS = {
        "--hds-color-surface-bg-quiet": "var(--hds-color-util-white)",
        "--hds-color-util-white": "#ffffff",
        "--hds-color-alpha": "255",
        "--hds-space-core-100": "8px",
        "--app-radius": "12px",
        "--hds-accordion-ease": "cubic-bezier(0.65,0.05,0.36,1)",
        "--hds-font-family": '"sohne-var","SF Pro Display",sans-serif',
        "--hds-canary-ui-shadow": "0 8px 24px rgba(0,0,0,.2)",
        "--hds-accordion-duration": "0.36s",
        "--hds-font-heading-1-size": "32px",
        "--hds-header-font": "700 16px/1.2 Inter, sans-serif",
    }

    def setUp(self):
        self.td = _synthetic_root(self.TOKENS)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _render(self, mirror="synth"):
        return gen.render(mirror, self.td)

    def test_namespace_routing(self):
        theme = gate.parse_block(self._render(), "@theme")
        self.assertIn("--color-synth-surface-bg-quiet", theme)
        self.assertIn("--spacing-synth-core-100", theme)      # hds-space-* + alias
        self.assertIn("--radius-synth-app-radius", theme)     # düşürme başarısız → ad ipucu
        self.assertIn("--font-synth-family", theme)
        self.assertIn("--ease-synth-hds-accordion-ease", theme)
        self.assertIn("--shadow-synth-hds-canary-ui-shadow", theme)
        self.assertTrue(all(v.startswith("var(--synth-") for v in theme.values()))

    def test_skips_are_reasoned_not_silent(self):
        info = gen.analyse("synth", self.td)
        self.assertEqual(info["skipped"]["--hds-color-alpha"], "class-mismatch")
        self.assertEqual(info["skipped"]["--hds-accordion-duration"], "class-time")
        self.assertEqual(info["skipped"]["--hds-font-heading-1-size"],
                         "class-mismatch")
        self.assertEqual(info["skipped"]["--hds-header-font"], "class-unknown")
        self.assertEqual(len(info["plans"]) + len(info["skipped"]),
                         len(info["tokens"]))

    def test_alias_chain_rewrites_var_references(self):
        text = self._render()
        pre = gate.parse_block(text, ":root")
        self.assertEqual(pre["--synth-hds-color-util-white"], "#ffffff")
        self.assertEqual(pre["--synth-hds-color-surface-bg-quiet"],
                         "var(--synth-hds-color-util-white)")
        theme = gate.parse_block(text, "@theme")
        self.assertEqual(theme["--color-synth-surface-bg-quiet"],
                         "var(--synth-hds-color-surface-bg-quiet)")

    def test_foreign_var_reference_is_left_alone(self):
        """Aynada olmayan referans (--sx-*, --Carousel-gap) ön-eklenmez."""
        tokens = {"--a": "var(--foreign, #fff)"}
        self.assertEqual(gen.rewrite_value("synth", "var(--foreign, #fff)",
                                           tokens), "var(--foreign, #fff)")
        self.assertEqual(gen.rewrite_value("synth", "var(--a)", tokens),
                         "var(--synth-a)")
        self.assertEqual(gen.rewrite_value("synth", "var(--a, 4px)", tokens),
                         "var(--synth-a, 4px)")

    def test_key_collision_prefers_declared_namespace(self):
        td = _synthetic_root({"--blue": "#56cdff", "--color-blue": "#4ea7fc"})
        try:
            info = gen.analyse("synth", td)
            self.assertEqual(info["plans"]["--color-synth-blue"], "--color-blue")
            self.assertEqual(info["skipped"]["--blue"], "key-collision")
            text = gen.render("synth", td)
            theme = gate.parse_block(text, "@theme")
            self.assertEqual(theme["--color-synth-blue"],
                             "var(--synth-color-blue)")
            # kaybeden yuva almaz ama değeri dosyada kalır
            pre = gate.parse_block(text, ":root")
            self.assertEqual(pre["--synth-blue"], "#56cdff")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_render_is_deterministic(self):
        self.assertEqual(self._render(), self._render())

    def test_bridge_satisfies_the_gate(self):
        """Sentetik köprü de sözleşmelerden geçmeli (kapı, jeneratörden bağımsız)."""
        mirror = "synth"
        (self.td / "design-system" / mirror / gen.BRIDGE_NAME).write_text(
            self._render(), encoding="utf-8")
        r = _run([str(GATE), "--root", str(self.td),
                  "--roster", str(self.td / "roster.list")])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK — 4/4 marka @theme köprüsü", r.stdout)


if __name__ == "__main__":
    unittest.main()
