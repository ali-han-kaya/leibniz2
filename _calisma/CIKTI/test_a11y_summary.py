#!/usr/bin/env python3
"""test_a11y_summary.py — a11y job summary kanıt bloğu için odaklı testler.

Spec: docs/superpowers/specs/2026-09-17-a11y-gate-design.md (§Reporting-3:
job summary yüzeyi). Kapsam: (1) özet YALNIZ allowlist'le eşleşen incomplete
düğümleri gösterir, (2) sayfadan gelen kanıt kod çitinden kaçamaz (markdown/
HTML enjeksiyonu), (3) kanıt birebir korunur (kaçış için bozulmaz),
(4) kesme/atlama sınırları görünür biçimde yazılır.

Bu dosya tarayıcıya dokunmaz: girdi, a11y_gate'in ürettiği rapor satırıdır.
"""

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import a11y_gate  # noqa: E402
import a11y_summary  # noqa: E402

SEAL_CFG = {"allowlist": [
    {"rule": "color-contrast", "target": "#seal-ring-path",
     "reason": "SVG halka metni bilinçli imza katmanı"},
    {"rule": "color-contrast", "target": ".seal-verdict",
     "reason": "SVG merkez metni bilinçli imza katmanı"},
    {"rule": "color-contrast", "target": ".seal-hash",
     "reason": "SVG hash metni bilinçli imza katmanı"},
]}


def incomplete_row(nodes, rule="color-contrast"):
    """a11y_gate.classify_violations'ın ürettiği incomplete satırını kur."""
    results = {"violations": [], "incomplete": [
        {"id": rule, "impact": "serious", "nodes": nodes}]}
    cfg = dict(SEAL_CFG)
    cfg.update({"blocking": ["critical", "serious"], "warn": ["moderate", "minor"],
                "incomplete": "report-only", "pages": []})
    return a11y_gate.classify_violations(results, cfg)[0]


def seal_nodes(extra_html="<span id=\"unrelated\">other</span>"):
    return [
        {"target": ["#seal-ring-path"],
         "html": '<textPath id="seal-ring-path">VERIFIED • ABC</textPath>'},
        {"target": [".seal-verdict"], "html": '<text class="seal-verdict">VERIFIED</text>'},
        {"target": [".seal-hash"], "html": '<text class="seal-hash">ABC123…</text>'},
        {"target": ["#unrelated"], "html": extra_html},
    ]


def render(row, allowlist=None):
    data = {"verdict": "PASS", "violations": [row]}
    return a11y_summary.render_report(data, allowlist or SEAL_CFG["allowlist"], "Dashboard")


FENCE_RE = re.compile(r"^(`{3,})(.*)$")


def fenced_spans(lines):
    """(açılış_index, kapanış_index, çit_uzunluğu) üçlüleri.

    Açılış: en az 3 backtick + bilgi dizesi; kapanış: en az açılış kadar
    backtick'ten oluşan başka içeriksiz satır (CommonMark).
    """
    spans = []
    open_index = None
    open_len = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if open_index is None:
            match = FENCE_RE.match(stripped)
            if match:
                open_index, open_len = index, len(match.group(1))
            continue
        if stripped and set(stripped) == {"`"} and len(stripped) >= open_len:
            spans.append((open_index, index, open_len))
            open_index = None
    return spans


class SelectionTests(unittest.TestCase):
    def test_only_allowlisted_incomplete_nodes_are_rendered(self):
        lines = render(incomplete_row(seal_nodes()))
        text = "\n".join(lines)
        for target in ("#seal-ring-path", ".seal-verdict", ".seal-hash"):
            self.assertIn(target, text)
        # allowlist'siz düğümün kanıtı özete taşınmaz (artifact'ta kalır).
        self.assertNotIn("unrelated", text)
        self.assertNotIn("other", text)
        self.assertIn("3 düğüm", lines[0])

    def test_evidence_is_verbatim_not_escaped_into_uselessness(self):
        lines = render(incomplete_row(seal_nodes()))
        spans = fenced_spans(lines)
        self.assertEqual(len(spans), 3)
        for open_index, close_index, _ in spans:
            body = [line.strip() for line in lines[open_index + 1:close_index]]
            self.assertEqual(len(body), 1)
            self.assertTrue(body[0].startswith("<"), body)
        self.assertIn('<textPath id="seal-ring-path">VERIFIED • ABC</textPath>',
                      "\n".join(lines))

    def test_non_incomplete_rows_are_not_rendered(self):
        warn = {"rule": "region", "impact": "moderate", "level": "warn", "nodes": 3}
        blocking = {"rule": "image-alt", "impact": "critical", "level": "blocking", "nodes": 1}
        silent = {"rule": "color-contrast", "impact": "serious", "level": "allowlisted",
                  "nodes": 0, "allowlisted_nodes": 3, "reasons": ["borç"]}
        for row in (warn, blocking, silent):
            self.assertEqual(render(row), [], row["level"])

    def test_incomplete_without_allowlist_match_is_not_rendered(self):
        row = incomplete_row([{"target": ["#badges > span.badge"], "html": "<span class=badge>x</span>"}])
        self.assertEqual(row["level"], "incomplete")
        self.assertEqual(render(row), [])

    def test_evidence_uses_gate_row_shape(self):
        row = incomplete_row(seal_nodes())
        evidence = a11y_summary.allowlisted_incomplete_evidence(row, SEAL_CFG["allowlist"])
        self.assertEqual([e["target"] for e in evidence],
                         ["#seal-ring-path", ".seal-verdict", ".seal-hash"])


class SafetyTests(unittest.TestCase):
    HOSTILE = "```\n## enjekte başlık\n<img src=x onerror=alert(1)>\n```"

    def test_page_html_cannot_close_the_code_fence(self):
        lines = render(incomplete_row([
            {"target": ["#seal-ring-path"], "html": self.HOSTILE},
            {"target": [".seal-verdict"], "html": "<text>VERIFIED</text>"},
        ]))
        spans = fenced_spans(lines)
        self.assertEqual(len(spans), 2, lines)
        open_index, close_index, fence_len = spans[0]
        body = "\n".join(lines[open_index + 1:close_index])
        self.assertIn("onerror=alert(1)", body)
        self.assertIn("## enjekte", body)
        # Çit, içerikteki en uzun backtick dizisinden (3) uzun olmalı.
        self.assertGreater(fence_len, 3)
        # Kanıt ve enjeksiyon yükü ham (çitsiz) yüzeye çıkmaz: yalnız tek
        # satırda, çitin içinde görünür.
        hostile_lines = [i for i, line in enumerate(lines) if "onerror" in line]
        self.assertEqual(hostile_lines, [open_index + 1], lines)
        self.assertTrue(lines[open_index + 1].strip().startswith("```"))

    def test_evidence_containing_only_backticks_stays_fenced(self):
        payload = "`````"  # 5 backtick: tek başına satır olsa çiti kapatabilirdi
        row = incomplete_row([{"target": ["#seal-ring-path"], "html": payload}])
        lines = render(row)
        spans = fenced_spans(lines)
        self.assertEqual(len(spans), 1, lines)
        open_index, close_index, fence_len = spans[0]
        self.assertGreater(fence_len, len(payload))
        self.assertEqual(lines[open_index + 1].strip(), payload)

    def test_code_span_widens_for_backticks_and_collapses_newlines(self):
        self.assertEqual(a11y_summary.code_span("a`b"), "``a`b``")
        self.assertEqual(a11y_summary.code_span("#a\n#b"), "`#a #b`")
        self.assertEqual(a11y_summary.code_span(" `x` "), "`` `x` ``")

    def test_allowlist_error_line_is_single_safe_line(self):
        line = a11y_summary.render_allowlist_error("bozuk `dosya`\nsatır")
        self.assertNotIn("\n", line)
        self.assertTrue(line.startswith("- "))
        self.assertIn("``bozuk `dosya` satır``", line)


class LimitTests(unittest.TestCase):
    def test_long_evidence_is_clipped_and_marked(self):
        payload = "<span>" + ("x" * 400) + "</span>"
        lines = render(incomplete_row([{"target": ["#seal-ring-path"], "html": payload}]))
        text = "\n".join(lines)
        self.assertIn("kesildi", text)
        open_index, close_index, _ = fenced_spans(lines)[0]
        body = "".join(line.strip() for line in lines[open_index + 1:close_index])
        self.assertEqual(len(body), a11y_summary.MAX_EVIDENCE_CHARS)

    def test_node_cap_marks_the_remainder(self):
        nodes = [{"target": ["#seal-ring-path"], "html": "<text>%d</text>" % i}
                 for i in range(12)]
        lines = render(incomplete_row(nodes))
        text = "\n".join(lines)
        self.assertIn("12 düğüm", lines[0])
        self.assertIn("4 düğüm daha", text)
        self.assertEqual(len(fenced_spans(lines)), a11y_summary.MAX_NODES_PER_RULE)

    def test_missing_report_rows_render_nothing(self):
        self.assertEqual(a11y_summary.render_reports([("Dashboard", {})], SEAL_CFG["allowlist"]), [])


class CliTests(unittest.TestCase):
    def test_cli_renders_the_allowlisted_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = os.path.join(tmp, "a11y_gate_config.json")
            report = os.path.join(tmp, "a11y_dashboard_dark.json")
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump(SEAL_CFG, f)
            with open(report, "w", encoding="utf-8") as f:
                json.dump({"verdict": "PASS", "violations": [incomplete_row(seal_nodes())]}, f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = a11y_summary.main(["--config", cfg,
                                        "--report", "Dashboard=%s" % report])
            self.assertEqual(rc, 0)
            self.assertIn("#seal-ring-path", buf.getvalue())
            self.assertNotIn("unrelated", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
