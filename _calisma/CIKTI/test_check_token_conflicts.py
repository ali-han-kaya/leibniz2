#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_token_conflicts.py — token drift/çakışma kapısı sözleşmeleri.

Kapı: design-system/scripts/check_token_conflicts.py (+ roster
design-system/scripts/token_layers.list). Her kural İZOLE bir fixture'da
kırmızıya düşürülür; yeşil kanıt sayılmaz — önce fixture'ın temiz olduğu
pinlenir (vacuous-PASS yasağı, test_vercel_theme.py ile aynı disiplin).

Sözleşmeler:
  T1 TEMEL    : fixture temiz → rc=0, bulgu yok; her kuralın KENDİ
                tetikleyicisi rc=1.
  T2 KURALLAR : K1 blok-içi tekrar (değer farklıysa), K2 katman çakışması
                (aynı değer serbest), K3 varyant kapsam sızıntısı, K4 kopya
                drifti (eksik/fazla/değer), K5 kayıtsız/ölü kayıt, K6 tüketici
                gölgesi (aynı değer serbest).
  T3 FAIL-CLOSED: roster yok → rc=2; capture gerekçesiz → rc=2; tarama kümesi
                boş → rc=2; ayrıştırma mutabakatı bozuk (blok dışı tanım) → rc=2.
  T4 ÇIKTI    : `--json` stdout'u TEK JSON belgesi (teşhis stderr'de),
                şema/durum/sayımlar sabit; `--md-out` yazılır.
  T5 GERÇEK   : gerçek ağaçta kapı yeşil ve roster gerçek katmanları çözüyor
                (subprocess: gerçek CLI + çıkış kodu).

Koşum: python3 -m unittest _calisma.CIKTI.test_check_token_conflicts
"""
import contextlib
import importlib.util
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
GATE = REPO / "design-system" / "scripts" / "check_token_conflicts.py"

CANON = """:root {
  --bg: #0e1116;
  --fg: #e6edf3;
}
:root[data-theme="light"] {
  --bg: #ffffff;
}
"""

BRIDGE = """:root {
  --demo-color-gray-900: hsla(0, 0%, 30%, 1);
}
@theme {
  --color-demo-gray-900: var(--demo-color-gray-900);
}
"""

VARIANT = """:root[data-theme="demo"] {
  --bg: var(--demo-color-gray-900);
  --fg: #000;
}
"""

COPY = """:root {
  --bg: #0e1116;
  --fg: #e6edf3;
}
:root[data-theme="light"] {
  --bg: #ffffff;
}
"""

CONSUMER = """:root {
  --background: var(--bg);
}
@theme inline {
  --color-background: var(--background);
}
"""

ROSTER = """# fixture roster
canonical  design-system/tokens.css
bridge     design-system/demo/tailwind.css
variant    design-system/demo/theme.css
consumer   apps/dashboard-next/app/globals.css
copy       _calisma/landing/landing.html
capture    design-system/demo/raw.css  ham yakalama (girdi)
"""


def _load():
    spec = importlib.util.spec_from_file_location("token_conflicts_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE_MOD = _load()


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _html(css):
    """HTML katmanı, gerçek `landing.html` gibi <style> bloğu taşır.

    read_style_text() yalnız <style> içeriğini okur: tagsiz bir fixture
    sessizce "tanım yok" olurdu (ölçüm değil fixture hatası).
    """
    return '<!doctype html>\n<html><head><style>\n%s</style></head></html>\n' % css


def _fixture(tmp, roster=ROSTER, canon=CANON, bridge=BRIDGE, variant=VARIANT,
             copy=COPY, consumer=CONSUMER, raw=":root {\n  --demo-raw: 1;\n}\n"):
    root = pathlib.Path(tmp)
    _write(root / "design-system" / "tokens.css", canon)
    _write(root / "design-system" / "demo" / "tailwind.css", bridge)
    _write(root / "design-system" / "demo" / "theme.css", variant)
    _write(root / "design-system" / "demo" / "raw.css", raw)
    _write(root / "apps" / "dashboard-next" / "app" / "globals.css", consumer)
    _write(root / "_calisma" / "landing" / "landing.html", _html(copy))
    _write(root / "design-system" / "scripts" / "token_layers.list", roster)
    return root


class GateTest(unittest.TestCase):
    """Fixture'ı izole koşar: modülün REPO/ROSTER'ı geçici ağaca bakar."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="token-conflicts-")
        self.old = (GATE_MOD.REPO, GATE_MOD.ROSTER)
        self.root = _fixture(self.tmp.name)
        GATE_MOD.REPO = self.root
        GATE_MOD.ROSTER = (self.root / "design-system" / "scripts"
                           / "token_layers.list")

    def tearDown(self):
        GATE_MOD.REPO, GATE_MOD.ROSTER = self.old
        self.tmp.cleanup()

    def run_gate(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = GATE_MOD.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def set_canonical(self, css):
        """Kanonik katmanı değiştir + kopyayı SENKRON tut.

        `copy` katmanı kanonik anlık görüntüsüdür: kanonik mutasyonu kopyayı da
        kaydırır ve K4 haklı olarak kırmızıya düşer. K1/K3 gibi testler tek
        kuralı izole etmek istediği için kopya birlikte güncellenir.
        """
        _write(self.root / "design-system" / "tokens.css", css)
        _write(self.root / "_calisma" / "landing" / "landing.html", _html(css))

    def findings(self, *argv):
        rc, out, _ = self.run_gate("--json", *argv)
        return rc, json.loads(out)["findings"]

    def rules(self, *argv):
        rc, found = self.findings(*argv)
        return rc, sorted({f["rule"] for f in found})


class BaselineTest(GateTest):

    def test_t1_fixture_is_clean(self):
        rc, out, _ = self.run_gate()
        self.assertEqual(rc, 0, out)
        self.assertIn("ÇAKIŞMA/DRIFT YOK", out)

    def test_t1_json_shape(self):
        rc, found = self.findings()
        self.assertEqual(rc, 0)
        doc = json.loads(self.run_gate("--json")[1])
        self.assertEqual(doc["schema"], "token-conflicts/1")
        self.assertEqual(doc["status"], "ok")
        self.assertEqual(doc["counts"], {"K1": 0, "K2": 0, "K3": 0, "K4": 0,
                                        "K5": 0, "K6": 0, "total": 0})
        self.assertEqual(doc["canonical"], "design-system/tokens.css")
        self.assertEqual(sorted(doc["unit"]),
                         ["bridge", "canonical", "variant"])
        self.assertIn("apps/dashboard-next/app/globals.css",
                      [layer["path"] for layer in doc["layers"]])


class RuleTest(GateTest):

    def test_t2_k1_intra_block_duplicate(self):
        self.set_canonical(":root {\n  --bg: #000;\n  --bg: #fff;\n}\n")
        rc, rules = self.rules()
        self.assertEqual(rules, ["K1"])
        self.assertEqual(rc, 1)

    def test_t2_k1_same_value_twice_is_allowed(self):
        self.set_canonical(":root {\n  --bg: #000;\n}\n:root {\n  --bg: #000;\n}\n")
        rc, rules = self.rules()
        self.assertEqual((rc, rules), (0, []))

    def test_t2_k2_cross_layer_conflict(self):
        _write(self.root / "design-system" / "demo" / "tailwind.css",
               ":root {\n  --bg: #123456;\n}\n")
        rc, found = self.findings()
        self.assertEqual(sorted({f["rule"] for f in found}), ["K2"])
        self.assertEqual(found[0]["name"], "--bg")
        self.assertEqual(sorted(found[0]["layers"]), [
            "design-system/demo/tailwind.css", "design-system/tokens.css"])
        self.assertEqual(rc, 1)

    def test_t2_k2_same_value_across_layers_is_allowed(self):
        _write(self.root / "design-system" / "demo" / "tailwind.css",
               ":root {\n  --bg: #0e1116;\n}\n")
        rc, rules = self.rules()
        self.assertEqual((rc, rules), (0, []))

    def test_t2_k3_variant_scope_leak(self):
        # Kanonik'te OLMAYAN bir adla sızdır: tek başına K3 izole edilsin
        # (kanonik bir adı sızdırmak K2'yi de haklı olarak tetikler).
        _write(self.root / "design-system" / "demo" / "theme.css",
               ":root {\n  --only-variant: #000;\n}\n"
               ':root[data-theme="demo"] {\n  --fg: #fff;\n}\n')
        rc, found = self.findings()
        self.assertEqual([f["rule"] for f in found], ["K3"])
        self.assertIn("kapsam", found[0]["detail"])
        self.assertEqual(rc, 1)

    def test_t2_k3_and_k2_both_fire_on_global_leak(self):
        # Kanonik adı global kapsama sızdırmak İKİ kuralı da haklı çıkarır:
        # kapsam ihlali (K3) + katman çakışması (K2). İkisi de görünmeli.
        _write(self.root / "design-system" / "demo" / "theme.css",
               ":root {\n  --bg: #123456;\n}\n")
        rc, rules = self.rules()
        self.assertEqual(rules, ["K2", "K3"])
        self.assertEqual(rc, 1)

    def test_t2_k4_copy_drift_missing_extra_differing(self):
        _write(self.root / "_calisma" / "landing" / "landing.html",
               _html(':root {\n  --bg: #ffffff;\n  --extra: 1;\n}\n'))
        rc, found = self.findings()
        self.assertEqual([f["rule"] for f in found], ["K4"])
        self.assertEqual(found[0]["missing"], ["global --fg",
                                               "theme:light --bg"])
        self.assertEqual(found[0]["extra"], ["global --extra"])
        self.assertIn("global --bg", found[0]["differing"])
        self.assertEqual(rc, 1)

    def test_t2_k5_unregistered_layer(self):
        _write(self.root / "design-system" / "dark.css",
               ":root {\n  --bg: #000;\n}\n")
        rc, found = self.findings()
        self.assertEqual([f["rule"] for f in found], ["K5"])
        self.assertEqual(found[0]["file"], "design-system/dark.css")
        self.assertEqual(rc, 1)

    def test_t2_k5_dead_roster_line(self):
        _write(self.root / "design-system" / "scripts" / "token_layers.list",
               ROSTER + "bridge     design-system/hayalet/tailwind.css\n")
        rc, found = self.findings()
        self.assertEqual([f["rule"] for f in found], ["K5"])
        self.assertIn("ölü kayıt", found[0]["detail"])
        self.assertEqual(rc, 1)

    def test_t2_k6_consumer_shadow_with_different_value(self):
        _write(self.root / "apps" / "dashboard-next" / "app" / "globals.css",
               ":root {\n  --bg: #ff00ff;\n  --background: var(--bg);\n}\n")
        rc, found = self.findings()
        self.assertEqual([f["rule"] for f in found], ["K6"])
        self.assertEqual(found[0]["differing"]["--bg"],
                         {"kanonik": "#0e1116", "tüketici": "#ff00ff"})
        self.assertEqual(rc, 1)

    def test_t2_k6_consumer_same_value_is_allowed(self):
        _write(self.root / "apps" / "dashboard-next" / "app" / "globals.css",
               ":root {\n  --bg: #0e1116;\n}\n")
        rc, rules = self.rules()
        self.assertEqual((rc, rules), (0, []))


class FailClosedTest(GateTest):

    def test_t3_missing_roster(self):
        GATE_MOD.ROSTER = self.root / "yok.list"
        rc, out, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("roster yok", err)

    def test_t3_capture_line_without_reason(self):
        _write(self.root / "design-system" / "scripts" / "token_layers.list",
               ROSTER + "capture    design-system/demo/raw2.css\n")
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("gerekçesiz", err)

    def test_t3_empty_scan_set(self):
        # Roster durur, TARANACAK dosyalar gider → kapı körleşir (rc=2).
        keep = self.root / "design-system" / "scripts" / "token_layers.list"
        for rel in ("design-system", "apps", "_calisma"):
            path = self.root / rel
            if path.exists():
                for child in sorted(path.rglob("*"), reverse=True):
                    if child.is_file() and child != keep:
                        child.unlink()
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("tarama kümesi boş", err)

    def test_t3_measurement_reconciliation(self):
        # Blok DIŞINDA tanım: regex görür, blok ayrıştırıcısı göremez →
        # kapsam ataması güvenilmez, kör kapı PASS üretmemeli.
        _write(self.root / "design-system" / "tokens.css",
               "--orphan: 1;\n:root {\n  --bg: #000;\n}\n")
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("uyuşmuyor", err)

    def test_t3_canonical_must_be_registered(self):
        _write(self.root / "design-system" / "scripts" / "token_layers.list",
               ROSTER.replace("canonical  design-system/tokens.css\n", ""))
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("kanonik referans", err)


class OutputTest(GateTest):

    def test_t4_json_stdout_is_single_document_with_findings(self):
        _write(self.root / "design-system" / "dark.css",
               ":root {\n  --bg: #000;\n}\n")
        rc, out, err = self.run_gate("--json")
        self.assertEqual(rc, 1)
        doc = json.loads(out)               # stdout'ta başka hiçbir şey yok
        self.assertEqual(doc["status"], "blocked")
        self.assertEqual(doc["counts"]["K5"], 1)
        self.assertIn("durum=blocked", err)

    def test_t4_md_out_is_written(self):
        target = self.root / "rapor.md"
        rc, _, _ = self.run_gate("--md-out", str(target))
        self.assertEqual(rc, 0)
        text = target.read_text(encoding="utf-8")
        self.assertIn("token-conflicts/1", text)
        self.assertIn("BULGU YOK", text)

    def test_t4_list_shows_roles_and_excluded(self):
        rc, out, _ = self.run_gate("--list")
        self.assertEqual(rc, 0)
        self.assertIn("copy", out)
        self.assertIn("(taranmadı)", out)
        self.assertIn("design-system/demo/raw.css", out)


class RealTreeTest(unittest.TestCase):
    """Gerçek CLI: gerçek ağaçta yeşil + roster gerçek katmanları çözüyor."""

    def test_t5_real_tree_is_green_via_cli(self):
        proc = subprocess.run([sys.executable, str(GATE), "--json"],
                              cwd=str(REPO), capture_output=True, text=True,
                              timeout=120)
        doc = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0,
                         proc.stdout + proc.stderr)
        self.assertEqual(doc["status"], "ok")
        self.assertEqual(doc["counts"]["total"], 0)
        roles = {layer["role"] for layer in doc["layers"]}
        self.assertEqual(roles, {"canonical", "bridge", "variant",
                                 "consumer", "copy"})
        paths = {layer["path"] for layer in doc["layers"]}
        for must in ("design-system/tokens.css", "design-system/tailwind.css",
                     "design-system/vercel/theme.css",
                     "design-system/vercel/tailwind.css",
                     "apps/dashboard-next/app/globals.css",
                     "_calisma/landing/landing.html"):
            self.assertIn(must, paths)
        self.assertIn("theme:vercel", doc["scanned"]["by_scope"])
        self.assertIn("[token-conflicts] durum=ok", proc.stderr)

    def test_t5_roster_has_no_dead_line_on_real_tree(self):
        proc = subprocess.run([sys.executable, str(GATE), "--list"],
                              cwd=str(REPO), capture_output=True, text=True,
                              timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for role in ("canonical", "bridge", "variant", "consumer", "copy"):
            self.assertIn(role, proc.stdout)


if __name__ == "__main__":
    unittest.main()
