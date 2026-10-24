#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_vercel_theme.py — Vercel adapter tema varyantının sözleşme testleri.

Varyant: `design-system/vercel/theme.css` (GENERATED, jeneratör
`design-system/vercel/scripts/generate_vercel_theme.py`). Kapı zinciri:
check_tokens.py contract 9 (+ jeneratörün `--check` modu) ve preview yüzeyi.

Sözleşmeler (hepsi fail-closed):
  V1 ÜRETİM    : theme.css jeneratörün render() çıktısıyla BİREBİR; `--check`
                 rc=0 ve sayıları (28/32 yuva, 4 ilan edilmiş istisna,
                 11/19 ayna token'ı) basar; `--check` mutasyonda rc=1 verir.
  V2 KAPSAM    : tek blok `:root[data-theme="vercel"]`; kanonik 32 yuva ya
                 bağlı ya UNBOUND_SLOTS'ta adıyla ilan edilmiş; ön-koşullar
                 aynadan birebir; aynadaki her token ya kullanılıyor ya
                 UNUSED_TOKENS'ta gerekçeli; stripe varyantıyla AYNI kanonik
                 yuva yüzeyi.
  V3 YÜZEY     : preview.html linki + [data-theme="vercel"] kuralları (stripe
                 bloğuyla aynı kural sayısı), preview.js tema döngüsü, servis
                 rotası DAVRANIŞSAL (`ps._route` döner; handler mirror'lı → 200
                 text/css, mirrorsız → 404) + mirror eşlemesi + kapsam kaydı.
  V4 KONTRAST  : metin rolleri çözülen renkler üzerinden WCAG AA (>= 4.5).
                 Ölçülen (2026-10-13): fg 17.94 · muted 8.52 · fg-dimmed 5.10 ·
                 accent 4.50 · err 4.58 · budget 4.50 · on-accent 4.50.
  V5 ÇÜRÜTME   : elle düzenleme / kapsam sızıntısı / ayna değer sapması /
                 istisnayı bağlama / eksik yuva / yüzey literali / çürük
                 referans mutasyonları kapıyı KIRMIZIYA düşürür — yeşil kanıt
                 değildir, önce fixture'ın temiz olduğu da pinlenir.

Koşum: `python3 -m unittest _calisma.CIKTI.test_vercel_theme`
"""
import importlib.util
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import preview_server as ps  # noqa: E402  (rota/handler davranışı burada koşar)
GEN = REPO / "design-system" / "vercel" / "scripts" / "generate_vercel_theme.py"
THEME = REPO / "design-system" / "vercel" / "theme.css"
MIRROR = REPO / "design-system" / "vercel" / "tokens.css"
GATE = REPO / "design-system" / "scripts" / "check_tokens.py"
PREVIEW_HTML = REPO / "_calisma" / "CIKTI" / "preview.html"
PREVIEW_JS = REPO / "_calisma" / "CIKTI" / "preview.js"
PREVIEW_SERVER = REPO / "_calisma" / "CIKTI" / "preview_server.py"
SYNC_MIRROR = REPO / "_calisma" / "CIKTI" / "sync_verify_mirror.sh"
MIRROR_COVERAGE = REPO / "_calisma" / "CIKTI" / "check_mirror_coverage.py"
STRIPE_GEN = (REPO / "design-system" / "stripe" / "scripts"
              / "generate_stripe_theme.py")
STRIPE_THEME = REPO / "design-system" / "stripe" / "theme.css"

SCOPE = ':root[data-theme="vercel"]'
AA = 4.5
# (ön plan, arka plan) — metin/ikon rolleri `--bg` üzerinde okunur.
PAIRS = (("--fg", "--bg"), ("--muted", "--bg"), ("--fg-dimmed", "--bg"),
         ("--accent", "--bg"), ("--err", "--bg"), ("--budget", "--bg"),
         ("--on-accent", "--accent"))


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pair(text: str) -> dict:
    return {n: re.sub(r"\s+", " ", v).strip()
            for n, v in re.findall(r"(--[\w-]+)\s*:\s*([^;{}]+?)\s*;", text)}


# ── renk çözümleme (WCAG) ──────────────────────────────────────────────────
def _rgb(value: str):
    m = re.match(r"hsla?\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%", value)
    if m:
        h, s, l = float(m.group(1)), float(m.group(2)) / 100, float(m.group(3)) / 100

        def ch(n):
            k = (n + h / 30) % 12
            a = s * min(l, 1 - l)
            return l - a * max(-1, min(k - 3, 9 - k, 1))

        return (ch(0) * 255, ch(8) * 255, ch(4) * 255)
    m = re.match(r"#([0-9a-fA-F]{6})", value)
    if m:
        return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
    raise AssertionError(f"çözülemeyen renk: {value!r}")


def _luminance(c) -> float:
    def ch(x):
        x = x / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _resolve(slot: str, slots: dict) -> str:
    """Yuva değerini literale indir: var() zinciri + `color-mix(in srgb, …)`.

    Yalnız varyantın kullandığı iki biçim desteklenir: düz `var(X)` ve
    `color-mix(in srgb, var(X) P%, black)` (srgb karışımı kanalların P
    oranıyla ölçeklenmesidir; siyah çapa ton taşımaz).
    """
    seen = set()
    value = slots[slot]
    while "--" in value:
        assert slot not in seen, f"döngüsel referans: {slot}"
        seen.add(slot)
        m = re.match(r"^var\((--[\w-]+)\)$", value)
        if m:
            value = slots[m.group(1)]
            continue
        m = re.match(
            r"^color-mix\(in srgb, var\((--[\w-]+)\) ([\d.]+)%, black\)$",
            value)
        assert m, f"çözülemeyen türev: {slot} = {value!r}"
        base = _rgb(slots[m.group(1)])
        p = float(m.group(2)) / 100
        if p == 1.0:
            return slots[m.group(1)]
        return "rgb(%s,%s,%s)" % tuple(str(round(c * p, 4)) for c in base)
    return value


def _rgb_str(value: str):
    m = re.match(r"rgb\(([\d.]+),([\d.]+),([\d.]+)\)$", value)
    if m:
        return tuple(float(g) for g in m.groups())
    return _rgb(value)


def _vercel_rules(text: str) -> int:
    return len(re.findall(r'\[data-theme="vercel"\]([^{}]*)\{', text))


def _tmp_repo() -> pathlib.Path:
    """Kapıyı izole koşmak için minimal repo düzeni (mutasyon testleri)."""
    td = pathlib.Path(tempfile.mkdtemp())
    (td / "_calisma" / "CIKTI").mkdir(parents=True)
    (td / "design-system").mkdir(parents=True)
    for name in ("tokens.css", "tokens.json", "tailwind.css"):
        shutil.copy(REPO / "design-system" / name, td / "design-system" / name)
    (td / "design-system" / "scripts").mkdir(parents=True)
    shutil.copy(GATE, td / "design-system" / "scripts" / "check_tokens.py")
    shutil.copy(PREVIEW_HTML, td / "_calisma" / "CIKTI" / "preview.html")
    for rel in (STRIPE_GEN, STRIPE_THEME,
                REPO / "design-system" / "stripe" / "tokens.css",
                GEN, THEME, MIRROR):
        target = td / rel.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(rel, target)
    return td


def _gate_findings(td: pathlib.Path):
    module = _load(td / "design-system" / "scripts" / "check_tokens.py",
                   "check_tokens_fixture_vercel")
    return module, module._vercel_variant_findings()


class TestProduction(unittest.TestCase):

    def test_v1_disk_file_is_generator_output(self):
        gen = _load(GEN, "vercel_theme_gen")
        self.assertEqual(THEME.read_text(encoding="utf-8"), gen.render(),
                         "theme.css jeneratör çıktısıyla birebir değil")

    def test_v1_check_cli_reports_counts(self):
        r = subprocess.run([sys.executable, str(GEN), "--check"],
                           capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK — vercel adapter varyantı", r.stdout)
        self.assertIn("28/32 yuva", r.stdout)
        self.assertIn("4 ilan edilmiş istisna", r.stdout)
        self.assertIn("11/19 ayna token'ı", r.stdout)

    def test_v1_check_fails_on_mutation(self):
        """`--check` yeşil değildir: bozuk kopya rc=1 + DRIFT mesajı."""
        gen = _load(GEN, "vercel_theme_gen")
        with tempfile.TemporaryDirectory(prefix="vercel-drift-") as tmp:
            drifted = pathlib.Path(tmp) / "theme.css"
            drifted.write_text(
                THEME.read_text(encoding="utf-8").replace(
                    "--accent: var(--develop-text);", "--accent: #0a72ef;"),
                encoding="utf-8")
            with mock.patch.object(gen, "OUT", drifted), \
                 mock.patch("sys.stderr") as err:
                rc = gen.main(["--check"])
            self.assertEqual(rc, 1)
            self.assertIn("VERCEL THEME DRIFT",
                          "".join(c.args[0] for c in err.write.call_args_list))


class TestScopeAndCoverage(unittest.TestCase):

    def test_v2_single_scope_block_and_bound_slots(self):
        gen = _load(GEN, "vercel_theme_gen")
        gate = _load(GATE, "check_tokens_scope")
        selectors = {selector for selector, _, _ in
                     gate._css_custom_props(THEME.read_text(encoding="utf-8"))}
        self.assertEqual(selectors, {gen.SCOPE},
                         "varyant yalnız kendi kapsam bloğunda tanımlar")
        in_scope = {n for s, n, _ in
                    gate._css_custom_props(THEME.read_text(encoding="utf-8"))
                    if s == gen.SCOPE}
        for slot in gen.SLOT_MAP:
            self.assertIn(slot, in_scope, f"{slot} bağlanmamış")
        for slot in gen.UNBOUND_SLOTS:
            self.assertNotIn(slot, in_scope,
                             f"{slot} ilan edilmiş istisna ama bağlanmış")
            self.assertIn(slot, THEME.read_text(encoding="utf-8"),
                          f"{slot} istisnası başlıkta ilan edilmemiş")

    def test_v2_slot_surface_matches_stripe_variant(self):
        gen = _load(GEN, "vercel_theme_gen")
        stripe = _load(STRIPE_GEN, "stripe_theme_gen")
        self.assertEqual(set(gen.REQUIRED_SLOTS), set(stripe.REQUIRED_SLOTS),
                         "iki varyantın kanonik renk yüzeyi ayrıştı")
        self.assertEqual(set(gen.SLOT_MAP) | set(gen.UNBOUND_SLOTS),
                         set(gen.REQUIRED_SLOTS))
        self.assertEqual(set(gen.SLOT_MAP) & set(gen.UNBOUND_SLOTS), set())

    def test_v2_preconditions_verbatim_and_mirror_coverage(self):
        gen = _load(GEN, "vercel_theme_gen")
        mirror = _pair(MIRROR.read_text(encoding="utf-8"))
        blocks = _pair(THEME.read_text(encoding="utf-8"))
        for name, value in blocks.items():
            if name in mirror:
                self.assertEqual(re.sub(r"\s+", "", value),
                                 re.sub(r"\s+", "", mirror[name]),
                                 f"{name} aynadan farklı")
        used = set(gen.closure(gen.referenced_tokens(), mirror))
        self.assertEqual(used & set(gen.UNUSED_TOKENS), set())
        self.assertEqual(used | set(gen.UNUSED_TOKENS), set(mirror),
                         "ayna token'ı ne kullanılıyor ne ilan edilmiş")
        self.assertEqual(len(mirror), 19)


class TestSurfaceWiring(unittest.TestCase):

    def test_v3_preview_html_loads_variant_and_mirrors_stripe_rules(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn('/design-system/vercel-theme.css', html)
        self.assertGreaterEqual(_vercel_rules(html), 10,
                                "yüzeyde [data-theme=\"vercel\"] kuralları yok")
        self.assertEqual(_vercel_rules(html),
                         len(re.findall(r'\[data-theme="stripe"\]([^{}]*)\{',
                                        html)),
                         "stripe ve vercel yüzey kuralları ayrıştı")

    def test_v3_theme_cycle_and_label(self):
        js = PREVIEW_JS.read_text(encoding="utf-8")
        self.assertIn('const THEMES = ["dark", "light", "stripe", "vercel"]', js)
        self.assertIn('vercel: "vercel theme"', js)

    def test_v3_service_route_is_really_wired(self):
        """Rota DAVRANIŞSAL: metin değil, `ps._route` gerçekten döner.

        Metin kontrolü tek başına yetersizdir — `_route` içindeki karşılaştırma
        dizesi değiştirilse bile dosyada URL başka yerde geçtiği için yeşil
        kalır (mutasyonla ölçüldü).
        """
        self.assertEqual(ps._route("/design-system/vercel-theme.css"),
                         "design_tokens_vercel")
        self.assertEqual(ps._route("/design-system/vercel-theme.css?v=9"),
                         "design_tokens_vercel")
        self.assertIsNone(ps._route("/design-system/vercel-theme"))
        self.assertIsNone(ps._route("/design-system/vercel-other.css"))

    def test_v3_handler_serves_mirror_or_fails_closed(self):
        """Handler mirror'daki dosyayı sunar; yoksa 404 (sessiz taban palet yok)."""
        class _Cap:
            sent = None

            def _send(self, status, body, content_type=None):
                self.sent = (status, body, content_type)

        theme = THEME.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="vercel-route-") as work:
            # PREVIEW_DIR main() içinde global olarak kurulur → import anında
            # modülde yoktur; patch `create=True` ile enjekte eder.
            with mock.patch.object(ps, "PREVIEW_DIR", work, create=True):
                missing = _Cap()
                ps.Handler.serve_vercel_theme(missing)
                self.assertEqual(missing.sent[0], 404)
                pathlib.Path(work, "design-system-vercel-theme.css").write_text(
                    theme, encoding="utf-8")
                present = _Cap()
                ps.Handler.serve_vercel_theme(present)
                self.assertEqual(present.sent[0], 200)
                self.assertIn("text/css", present.sent[2])
                self.assertEqual(present.sent[1], theme)

    def test_v3_mirror_chain_and_coverage_records(self):
        server = PREVIEW_SERVER.read_text(encoding="utf-8")
        self.assertIn('return "design_tokens_vercel"', server)
        self.assertIn("def serve_vercel_theme(self):", server)
        self.assertIn('"design-system-vercel-theme.css"', server)
        mirror = SYNC_MIRROR.read_text(encoding="utf-8")
        self.assertIn(
            '"design-system/vercel/theme.css|design-system-vercel-theme.css"',
            mirror, "mirror eşlemesi yok — sunucu rotası 404'e düşer")
        coverage = MIRROR_COVERAGE.read_text(encoding="utf-8")
        self.assertIn('VERCEL_THEME_REL = "design-system/vercel/theme.css"',
                      coverage)
        self.assertIn("expected.add(VERCEL_THEME_REL)", coverage)


class TestContrast(unittest.TestCase):

    def test_v4_text_roles_meet_aa_on_resolved_colors(self):
        slots = _pair(THEME.read_text(encoding="utf-8"))
        measured = {}
        for fg, bg in PAIRS:
            ratio = _contrast(_rgb_str(_resolve(fg, slots)),
                              _rgb_str(_resolve(bg, slots)))
            measured[f"{fg}/{bg}"] = round(ratio, 4)
            self.assertGreaterEqual(
                ratio, AA,
                f"{fg} → {bg} kontrastı {ratio:.3f} < {AA} (ölçülen: {measured})")

    def test_v4_derivations_are_pinned_recipes(self):
        """Türetilmiş iki ton aynadaki tondan bilinen reçeteyle gelir."""
        slots = _pair(THEME.read_text(encoding="utf-8"))
        mirror = _pair(MIRROR.read_text(encoding="utf-8"))
        self.assertEqual(slots["--err"],
                         "color-mix(in srgb, var(--ship-text) 80%, black)")
        self.assertEqual(slots["--fg-dimmed"],
                         "color-mix(in srgb, var(--color-gray-800) 88%, black)")
        self.assertEqual(slots["--accent"], "var(--develop-text)")
        self.assertEqual(mirror["--ship-text"], "#ff5b4f")


class TestGateIsNotVacuous(unittest.TestCase):
    """Mutasyonlar TEMİZ fixture üzerinde koşar: önce taban yeşil, sonra kırmızı."""

    def _mutate(self, rel: str, old: str, new: str):
        td = _tmp_repo()
        try:
            target = td / rel
            text = target.read_text(encoding="utf-8")
            self.assertIn(old, text, f"mutasyon çapası yok: {rel}")
            target.write_text(text.replace(old, new, 1), encoding="utf-8")
            return td
        except Exception:
            shutil.rmtree(td, ignore_errors=True)
            raise

    def test_v5_baseline_fixture_is_clean(self):
        td = _tmp_repo()
        try:
            _, findings = _gate_findings(td)
            self.assertEqual(findings, [], findings)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_v5_hand_edit_fails(self):
        td = self._mutate("design-system/vercel/theme.css",
                          "--accent: var(--develop-text);",
                          "--accent: #0a72ef;")
        try:
            _, findings = _gate_findings(td)
            self.assertTrue(any("jeneratörle birebir değil" in f
                                for f in findings), findings)
            self.assertTrue(any("renk literal" in f for f in findings), findings)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_v5_scope_leak_fails(self):
        td = _tmp_repo()
        try:
            theme = td / "design-system" / "vercel" / "theme.css"
            theme.write_text(
                theme.read_text(encoding="utf-8")
                + '\n:root { --sizinti: var(--develop-text); }\n',
                encoding="utf-8")
            _, findings = _gate_findings(td)
            self.assertTrue(any("beklenmeyen blok" in f for f in findings),
                            findings)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_v5_mirror_value_drift_fails(self):
        td = self._mutate("design-system/vercel/theme.css",
                          "--develop-text: #0a72ef;",
                          "--develop-text: #0a72f0;")
        try:
            _, findings = _gate_findings(td)
            self.assertTrue(any("aynadan farklı" in f for f in findings),
                            findings)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_v5_binding_a_declared_exception_fails(self):
        td = self._mutate("design-system/vercel/theme.css",
                          "  --paper: var(--color-background-100);",
                          "  --ok: var(--develop-text);\n"
                          "  --paper: var(--color-background-100);")
        try:
            _, findings = _gate_findings(td)
            self.assertTrue(any("ilan edilmiş istisna ama bağlanmış" in f
                                for f in findings), findings)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_v5_missing_slot_raises(self):
        td = _tmp_repo()
        try:
            module = _load(td / "design-system" / "scripts" / "check_tokens.py",
                           "check_tokens_fixture_missing")
            gen = module._load_vercel_generator()
            gen.SLOT_MAP.pop("--budget")
            with self.assertRaises(SystemExit):
                gen.render()
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_v5_dangling_reference_fails(self):
        td = self._mutate("design-system/vercel/theme.css",
                          "--border: var(--color-gray-300);",
                          "--border: var(--color-yok-boyle-token);")
        try:
            _, findings = _gate_findings(td)
            self.assertTrue(any("çürük" in f for f in findings), findings)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_v5_surface_literal_fails(self):
        td = self._mutate(
            "_calisma/CIKTI/preview.html",
            ':root[data-theme="vercel"] .z3-slide { '
            "background:var(--surface);",
            ':root[data-theme="vercel"] .z3-slide { background:#f6f6f6;')
        try:
            _, findings = _gate_findings(td)
            self.assertTrue(any("renk literal" in f for f in findings), findings)
        finally:
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
