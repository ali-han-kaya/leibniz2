#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_action_runtimes.py — action runtime denetimi kapısı.

check_action_runtimes.py'nin pure mantığını (parse_uses / classify_using /
audit) ve fetch_action_yml'in ağsız yollarını (URL üretimi + lokal/geçersiz
uses) deterministik doğrular. stdlib unittest + mock — canlı ağ çağrısı yok.
"""
import io
import sys
import unittest
import urllib.error
from unittest import mock

import pathlib
CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import check_action_runtimes as car  # noqa: E402

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


def _wf(*uses):
    steps = "".join(f"      - uses: {u}\n" for u in uses)
    return f"jobs:\n  a:\n    steps:\n{steps}"


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestParseUses(unittest.TestCase):
    def test_extracts_unique_sorted(self):
        txt = ("jobs:\n"
               "  a:\n"
               "    steps:\n"
               "      - uses: actions/checkout@v7\n"
               "      - uses: actions/setup-python@v6\n"
               "  b:\n"
               "    steps:\n"
               "      - uses: actions/checkout@v7\n"  # duplicate
               "      - uses: actions/cache@v5\n")
        self.assertEqual(car.parse_uses(txt), [
            "actions/cache@v5", "actions/checkout@v7",
            "actions/setup-python@v6"])

    def test_on_key_and_no_steps(self):
        # `on:` YAML 1.1'de boolean olur — yalnızca jobs okunduğundan sorun yok.
        txt = "on:\n  push:\njobs:\n  a:\n    name: x\n"
        self.assertEqual(car.parse_uses(txt), [])

    def test_uses_with_comment_whitespace_ok(self):
        txt = _wf("actions/checkout@v7 ")
        self.assertEqual(car.parse_uses(txt), ["actions/checkout@v7"])


class TestClassifyUsing(unittest.TestCase):
    def test_target_node_pass(self):
        self.assertEqual(car.classify_using("node24"), ("PASS", mock.ANY))

    def test_newer_node_pass(self):
        v, _ = car.classify_using("node26")
        self.assertEqual(v, "PASS")

    def test_node20_fail(self):
        v, note = car.classify_using("node20")
        self.assertEqual(v, "FAIL")
        self.assertIn("deprecated", note)

    def test_node16_fail(self):
        self.assertEqual(car.classify_using("node16")[0], "FAIL")

    def test_composite_and_docker_skip(self):
        self.assertEqual(car.classify_using("composite")[0], "SKIP")
        self.assertEqual(car.classify_using("docker")[0], "SKIP")

    def test_unknown_runtime_pass_with_note(self):
        v, note = car.classify_using("python3")
        self.assertEqual(v, "PASS")
        self.assertIn("elle kontrol", note)

    def test_custom_target(self):
        # hedef node26 iken node24 deprecated sayılır
        v, _ = car.classify_using("node24", target="node26")
        self.assertEqual(v, "FAIL")


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestAudit(unittest.TestCase):
    def test_all_pass(self):
        rows = car.audit(_wf("actions/checkout@v7"),
                         fetcher=lambda a: ("runs:\n  using: node24\n", None))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verdict"], "PASS")
        self.assertEqual(rows[0]["using"], "node24")

    def test_deprecated_fail(self):
        rows = car.audit(_wf("actions/checkout@v4"),
                         fetcher=lambda a: ("runs:\n  using: node20\n", None))
        self.assertEqual(rows[0]["verdict"], "FAIL")

    def test_fetch_error_fail_closed(self):
        rows = car.audit(_wf("actions/x@v1"),
                         fetcher=lambda a: (None, "HTTP 404"))
        self.assertEqual(rows[0]["verdict"], "FAIL")
        self.assertEqual(rows[0]["error"], "HTTP 404")

    def test_local_action_skip_not_fetched(self):
        def fetcher(a):
            raise AssertionError("lokal action fetch edilmemeli")
        rows = car.audit(_wf("./.github/actions/foo"), fetcher=fetcher)
        self.assertEqual(rows[0]["verdict"], "SKIP")

    def test_composite_skip(self):
        rows = car.audit(_wf("actions/x@v1"),
                         fetcher=lambda a: ("runs:\n  using: composite\n", None))
        self.assertEqual(rows[0]["verdict"], "SKIP")

    def test_bad_action_yml_fail(self):
        rows = car.audit(_wf("actions/x@v1"),
                         fetcher=lambda a: ("runs: [", None))
        self.assertEqual(rows[0]["verdict"], "FAIL")
        self.assertIn("YAML", rows[0]["note"])

    def test_summary_counts(self):
        rows = car.audit(
            "jobs:\n  a:\n    steps:\n"
            "      - uses: a/ok@v1\n      - uses: b/bad@v1\n"
            "      - uses: c/skip@v1\n",
            fetcher=lambda a: (
                {"a/ok@v1": ("runs:\n  using: node24\n", None),
                 "b/bad@v1": ("runs:\n  using: node20\n", None),
                 "c/skip@v1": ("runs:\n  using: composite\n", None)}[a]))
        s = car._summary(rows)
        self.assertEqual(s, {"total": 3, "pass": 1, "fail": 1, "skip": 1})


class TestFetchActionYml(unittest.TestCase):
    def test_local_and_invalid_uses_no_network(self):
        self.assertEqual(car.fetch_action_yml("./x"), (None, "__local__"))
        self.assertEqual(car.fetch_action_yml("noref"), (None, mock.ANY))
        self.assertEqual(car.fetch_action_yml("norepo"), (None, mock.ANY))

    def test_url_construction_and_404(self):
        def urlopen(req, timeout):
            self.assertEqual(
                req.full_url,
                "https://raw.githubusercontent.com/actions/checkout/v7/action.yml")
            raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)

        with mock.patch.object(car.urllib.request, "urlopen",
                               side_effect=urlopen):
            content, err = car.fetch_action_yml("actions/checkout@v7")
        self.assertIsNone(content)
        self.assertEqual(err, "HTTP 404")

    def test_retry_then_success(self):
        calls = []

        def urlopen(req, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.URLError("geçici")
            return io.BytesIO(b"runs:\n  using: node24\n")

        with mock.patch.object(car.urllib.request, "urlopen",
                               side_effect=urlopen), \
                mock.patch.object(car.time, "sleep"):
            content, err = car.fetch_action_yml("actions/checkout@v7")
        self.assertIsNone(err)
        self.assertIn("node24", content)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
