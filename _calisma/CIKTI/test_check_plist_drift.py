#!/usr/bin/env python3
"""check_plist_drift.py birim testleri — render/golden karşılaştırma mantığı."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_plist_drift import (  # noqa: E402
    DEFAULT_CANONICAL_HOME, check, normalize, plist_is_valid,
)

LEIBNIZ = """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>Label</key><string>com.freebuff.preview-leibniz2</string>
<key>KeepAlive</key><true/>
</dict></plist>
"""

SERVER = """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>Label</key><string>com.freebuff.preview-server</string>
<key>KeepAlive</key><false/>
</dict></plist>
"""


def make_tree(root, golden_map, rendered_map):
    """golden_map/rendered_map: {dosya_adı: içerik}. Dizin yapısını kurar."""
    gd = os.path.join(root, "golden")
    rd = os.path.join(root, "render", "Library", "LaunchAgents")
    os.makedirs(gd, exist_ok=True)
    os.makedirs(rd, exist_ok=True)
    for name, content in golden_map.items():
        with open(os.path.join(gd, name), "w", encoding="utf-8") as f:
            f.write(content)
    for name, content in rendered_map.items():
        with open(os.path.join(rd, name), "w", encoding="utf-8") as f:
            f.write(content)
    return gd, rd


class TestNormalize(unittest.TestCase):
    def test_replaces_prefix(self):
        self.assertEqual(
            normalize("/tmp/x/a/b", "/tmp/x", "/Users/ci"),
            "/Users/ci/a/b")

    def test_no_op_without_match(self):
        self.assertEqual(normalize("hello", "/tmp/x", "/Users/ci"), "hello")

    def test_empty(self):
        self.assertEqual(normalize("", "/a", "/b"), "")


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="plist-drift-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))

    def test_all_pass(self):
        gd, rd = make_tree(
            self.root,
            {"com.freebuff.preview-leibniz2.plist": LEIBNIZ,
             "com.freebuff.preview-server.plist": SERVER},
            {"com.freebuff.preview-leibniz2.plist": LEIBNIZ,
             "com.freebuff.preview-server.plist": SERVER})
        results, drift, error = check(os.path.join(self.root, "render"), gd,
                                      DEFAULT_CANONICAL_HOME)
        self.assertFalse(error)
        self.assertFalse(drift)
        self.assertEqual({r["verdict"] for r in results}, {"PASS"})
        self.assertEqual(len(results), 2)

    def test_drift_on_content_change(self):
        # golden'daki KeepAlive true, render'daki false → drift
        gd, rd = make_tree(
            self.root,
            {"com.freebuff.preview-leibniz2.plist": LEIBNIZ},
            {"com.freebuff.preview-leibniz2.plist": LEIBNIZ.replace("<true/>", "<false/>")})
        results, drift, error = check(os.path.join(self.root, "render"), gd,
                                      DEFAULT_CANONICAL_HOME)
        self.assertFalse(error)
        self.assertTrue(drift)
        self.assertEqual(results[0]["verdict"], "DRIFT")

    def test_drift_on_missing_rendered(self):
        gd, rd = make_tree(
            self.root,
            {"com.freebuff.preview-leibniz2.plist": LEIBNIZ,
             "com.freebuff.preview-server.plist": SERVER},
            {"com.freebuff.preview-leibniz2.plist": LEIBNIZ})
        results, drift, error = check(os.path.join(self.root, "render"), gd,
                                      DEFAULT_CANONICAL_HOME)
        self.assertFalse(error)
        self.assertTrue(drift)
        missing = [r for r in results if r["label"] == "com.freebuff.preview-server.plist"]
        self.assertEqual(missing[0]["verdict"], "DRIFT")

    def test_drift_on_extra_rendered(self):
        gd, rd = make_tree(
            self.root,
            {"com.freebuff.preview-leibniz2.plist": LEIBNIZ},
            {"com.freebuff.preview-leibniz2.plist": LEIBNIZ,
             "com.freebuff.preview-extra.plist": SERVER})
        results, drift, error = check(os.path.join(self.root, "render"), gd,
                                      DEFAULT_CANONICAL_HOME)
        self.assertFalse(error)
        self.assertTrue(drift)
        extra = [r for r in results if r["label"] == "com.freebuff.preview-extra.plist"]
        self.assertEqual(extra[0]["verdict"], "DRIFT")

    def test_drift_on_invalid_plist(self):
        gd, rd = make_tree(
            self.root,
            {"com.freebuff.preview-leibniz2.plist": LEIBNIZ},
            {"com.freebuff.preview-leibniz2.plist": LEIBNIZ})
        # İçerik aynı ama yapısal geçersiz olması için render'ı boz
        bad = LEIBNIZ.replace("</dict></plist>", "</dict>")  # kapanış eksik
        with open(os.path.join(self.root, "render", "Library", "LaunchAgents",
                               "com.freebuff.preview-leibniz2.plist"), "w") as f:
            f.write(bad)
        results, drift, error = check(os.path.join(self.root, "render"), gd,
                                      DEFAULT_CANONICAL_HOME)
        # golden'ın kendisi geçerli değilse bile plist_is_valid RENDER'ı denetler
        # (burada render geçersiz → DRIFT); içerik farkı da ayrıca yakalanır.
        self.assertFalse(error)
        self.assertTrue(drift)

    def test_error_on_empty_golden(self):
        gd, rd = make_tree(self.root, {}, {})
        results, drift, error = check(os.path.join(self.root, "render"), gd,
                                      DEFAULT_CANONICAL_HOME)
        self.assertTrue(error)
        self.assertEqual(results, [])

    def test_normalize_home_in_render(self):
        # render-home'daki yol canonical'a normalize edilince golden ile eşleşmeli.
        render_home = os.path.join(self.root, "render")
        rendered = LEIBNIZ.replace("com.freebuff.preview-leibniz2",
                                   f"{render_home}/a/b/com.freebuff.preview-leibniz2")
        gd, _ = make_tree(
            self.root,
            {"com.freebuff.preview-leibniz2.plist":
                LEIBNIZ.replace("com.freebuff.preview-leibniz2",
                                f"{DEFAULT_CANONICAL_HOME}/a/b/com.freebuff.preview-leibniz2")},
            {"com.freebuff.preview-leibniz2.plist": rendered})
        results, drift, error = check(render_home, gd, DEFAULT_CANONICAL_HOME)
        self.assertFalse(error)
        self.assertFalse(drift)
        self.assertEqual(results[0]["verdict"], "PASS")


class TestPlistIsValid(unittest.TestCase):
    def test_valid(self):
        with tempfile.NamedTemporaryFile("w", suffix=".plist", delete=False) as f:
            f.write(LEIBNIZ)
            p = f.name
        self.addCleanup(os.unlink, p)
        self.assertTrue(plist_is_valid(p))

    def test_invalid(self):
        with tempfile.NamedTemporaryFile("w", suffix=".plist", delete=False) as f:
            f.write("not a plist at all")
            p = f.name
        self.addCleanup(os.unlink, p)
        self.assertFalse(plist_is_valid(p))


if __name__ == "__main__":
    unittest.main()
