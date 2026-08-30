#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit + stdio integration tests for verify_mcp.

Three layers:
  1. Data-layer tests: record loading, summary curation, layer parsing.
  2. Tool tests: call the FastMCP tool functions directly against a fake
     preview dir (no MCP handshake), covering json and markdown formats.
  3. stdio smoke test: spawn the server binary and drive a real JSON-RPC
     session (initialize -> tools/list -> tools/call) over newline-delimited
     stdio, the same path an MCP client (e.g. the Inspector) uses.
"""

import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)

import server  # noqa: E402
SERVER_PY = os.path.join(SERVER_DIR, "server.py")

HISTORY_LINE = (
    '{"ts": "2026-08-25T09:00:00.123456", "verdict": "PASS", "exit_code": 0, '
    '"p0": 0, "p1": 0, "duration_s": 12.5, "budget_usd": 0.25, '
    '"budget_limit": 1.0, "budget_method": "weighted", "refs_verified": 61, '
    '"refs_total": 61, "layers": {"K1": {"label": "Dış zip sidecar", '
    '"status": "PASS", "ran": true}, "K8": {"label": "Z3", "status": "PASS", '
    '"ran": true}}, "cached": false}'
)

FULL_REC = {
    "ts": "2026-08-25T21:06:07.654321",
    "verdict": "FAIL",
    "exit_code": 1,
    "p0": 0,
    "p1": 2,
    "duration_s": 42.0,
    "stdout": "line1\nline2\nline3\n",
    "stderr": "",
    "layers": {
        "K1": {"label": "Dış zip sidecar", "status": "PASS", "ran": True},
        "K4": {"label": "Manifest 19/19", "status": "FAIL", "ran": True,
               "findings": [{"id": "M01", "priority": "P1"}]},
        "K9": {"label": "Lean reduct-invariance", "status": "SKIP", "ran": False},
    },
    "refs_verified": 59,
    "refs_total": 61,
    "refs_mismatch": 2,
    "z3_passed": 5,
    "z3_total": 5,
    "lean_ok": None,
    "mirror_sync": {"ok": True, "exit": 0, "stale_files": []},
    "pattern_drift": "PASS",
    "findings": [{"id": "F1", "priority": "P1", "label": "x"}],
    "cached": False,
}


def make_preview_dir(root):
    """Create a fake preview dir: history.jsonl + one full runs/ log."""
    preview = os.path.join(root, "preview")
    os.makedirs(os.path.join(preview, "runs"), exist_ok=True)
    with open(os.path.join(preview, "history.jsonl"), "w", encoding="utf-8") as f:
        f.write('{"ts": "2026-08-24T08:00:00", "verdict": "PASS", "exit_code": 0, '
                '"p0": 0, "p1": 0, "duration_s": 9.0}\n')
        f.write(HISTORY_LINE + "\n")
    safe = FULL_REC["ts"].replace(":", "").replace("+", "").replace(".", "")
    with open(os.path.join(preview, "runs", f"run-{safe}.json"), "w",
              encoding="utf-8") as f:
        json.dump(FULL_REC, f, ensure_ascii=False)
    return preview


class DataLayerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="vmcp-")
        self.addCleanup(self._tmp.cleanup)
        self._preview = make_preview_dir(self._tmp.name)
        self._old = server.PREVIEW_DIR
        server.PREVIEW_DIR = self._preview

    def tearDown(self):
        server.PREVIEW_DIR = self._old

    def test_latest_prefers_full_run_log(self):
        rec = server._latest_record()
        self.assertEqual(rec["ts"], FULL_REC["ts"])
        self.assertEqual(rec["verdict"], "FAIL")

    def test_history_oldest_to_newest(self):
        hist = server._load_history()
        self.assertEqual([r["ts"] for r in hist],
                         ["2026-08-24T08:00:00", "2026-08-25T09:00:00.123456"])

    def test_latest_falls_back_to_history_when_no_runs(self):
        os.remove(os.path.join(self._preview, "runs", os.listdir(
            os.path.join(self._preview, "runs"))[0]))
        rec = server._latest_record()
        self.assertEqual(rec["ts"], "2026-08-25T09:00:00.123456")

    def test_layer_counts(self):
        counts = server._layer_counts(FULL_REC["layers"])
        self.assertEqual(counts, {"PASS": 1, "FAIL": 1, "SKIP": 1})

    def test_klayers_sidecar_from_preview_dir(self):
        sidecar = {"layers": {"K1": {"status": "PASS", "label": "X"}}}
        with open(os.path.join(self._preview, "klayers.json"), "w",
                  encoding="utf-8") as f:
            json.dump(sidecar, f)
        layers = server._klayers_from_disk()
        self.assertEqual(layers["K1"]["status"], "PASS")

    def test_klayers_sidecar_ignores_bad_shape(self):
        with open(os.path.join(self._preview, "klayers.json"), "w",
                  encoding="utf-8") as f:
            f.write("not json")
        self.assertIsNone(server._klayers_from_disk())

    def test_layer_counts_tolerates_bad_shape(self):
        self.assertEqual(server._layer_counts(None),
                         {"PASS": 0, "FAIL": 0, "SKIP": 0})
        self.assertEqual(server._layer_counts({"K1": "PASS"}),
                         {"PASS": 0, "FAIL": 0, "SKIP": 0})

    def test_summarize_omits_none_and_stdout(self):
        s = server._summarize(FULL_REC)
        self.assertNotIn("stdout", s)
        self.assertNotIn("stderr", s)
        self.assertEqual(s["p1"], 2)
        self.assertEqual(s["layer_counts"]["FAIL"], 1)

    def test_sort_layers_numeric(self):
        self.assertEqual(
            server._sort_layers({"K10": {}, "K2": {}, "K1": {}}),
            ["K1", "K2", "K10"])

    def test_no_records_error_is_actionable(self):
        empty = tempfile.TemporaryDirectory(prefix="vmcp-empty-")
        self.addCleanup(empty.cleanup)
        server.PREVIEW_DIR = os.path.join(empty.name, "nowhere")
        with self.assertRaises(FileNotFoundError) as ctx:
            server._latest_record()
        self.assertIn("Start the dashboard once", str(ctx.exception))


class ToolTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="vmcp-")
        self.addCleanup(self._tmp.cleanup)
        self._preview = make_preview_dir(self._tmp.name)
        self._old = server.PREVIEW_DIR
        server.PREVIEW_DIR = self._preview

    def tearDown(self):
        server.PREVIEW_DIR = self._old

    def test_get_latest_markdown(self):
        out = asyncio.run(server.verify_get_latest(response_format="markdown"))
        self.assertIn("# Latest run", out)
        self.assertIn("**FAIL** (exit 1)", out)
        self.assertIn("1 FAIL", out)

    def test_get_latest_json_has_structured_fields(self):
        out = asyncio.run(server.verify_get_latest(response_format="json"))
        d = json.loads(out)
        self.assertEqual(d["verdict"], "FAIL")
        self.assertEqual(d["layer_counts"]["PASS"], 1)
        self.assertEqual(d["refs_total"], 61)

    def test_layer_status_markdown_orders_and_skips(self):
        out = asyncio.run(server.verify_get_layer_status(response_format="markdown"))
        self.assertIn("K1", out)
        self.assertIn("K9", out)
        self.assertIn("SKIP", out)
        self.assertLess(out.index("K1"), out.index("K9"))

    def test_layer_status_json_returns_raw_layers(self):
        out = asyncio.run(server.verify_get_layer_status(response_format="json"))
        d = json.loads(out)
        self.assertEqual(d["K4"]["status"], "FAIL")

    def test_layer_status_falls_back_to_sidecar(self):
        # Drop layers from the newest record (like real persisted runs), then
        # provide a klayers.json sidecar — the tool must use it.
        runs_dir = os.path.join(self._preview, "runs")
        for name in os.listdir(runs_dir):
            with open(os.path.join(runs_dir, name), "r+", encoding="utf-8") as f:
                rec = json.load(f)
                rec.pop("layers", None)
                f.seek(0)
                json.dump(rec, f, ensure_ascii=False)
                f.truncate()
        sidecar = {"layers": {"K9": {"status": "SKIP", "label": "Lean"},
                              "K8": {"status": "PASS", "label": "Z3"}}}
        with open(os.path.join(self._preview, "klayers.json"), "w",
                  encoding="utf-8") as f:
            json.dump(sidecar, f)
        out = asyncio.run(server.verify_get_layer_status(response_format="json"))
        d = json.loads(out)
        self.assertEqual(d["K9"]["status"], "SKIP")

    def test_layer_status_no_data_is_actionable(self):
        empty = tempfile.TemporaryDirectory(prefix="vmcp-empty-")
        self.addCleanup(empty.cleanup)
        preview = os.path.join(empty.name, "preview")
        os.makedirs(os.path.join(preview, "runs"), exist_ok=True)
        with open(os.path.join(preview, "history.jsonl"), "w",
                  encoding="utf-8") as f:
            f.write('{"ts": "2026-08-24T08:00:00", "verdict": "PASS", '
                    '"exit_code": 0, "z3_passed": 5, "z3_total": 5}\n')
        server.PREVIEW_DIR = preview
        out = asyncio.run(server.verify_get_layer_status())
        self.assertIn("Error: no per-layer status persisted", out)
        self.assertIn("klayers.json", out)

    def test_run_detail_exact_ts(self):
        out = asyncio.run(server.verify_get_run_detail(
            ts=FULL_REC["ts"], response_format="json"))
        d = json.loads(out)
        self.assertEqual(d["ts"], FULL_REC["ts"])
        self.assertIn("line2", d["stdout"])

    def test_run_detail_prefix_matches_newest(self):
        out = asyncio.run(server.verify_get_run_detail(
            ts="2026-08-25", response_format="json"))
        d = json.loads(out)
        self.assertEqual(d["ts"], FULL_REC["ts"])

    def test_run_detail_unknown_ts_lists_available(self):
        out = asyncio.run(server.verify_get_run_detail(ts="1999-01-01"))
        self.assertIn("Error: no run matches ts '1999-01-01'", out)
        self.assertIn(FULL_REC["ts"], out)

    def test_run_detail_markdown_truncates_stdout(self):
        long_ts = "2026-08-26T10:00:00.111111"
        rec = dict(FULL_REC, ts=long_ts, stdout="x" * 800)
        safe = long_ts.replace(":", "").replace("+", "").replace(".", "")
        with open(os.path.join(self._preview, "runs", f"run-{safe}.json"),
                  "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)
        out = asyncio.run(server.verify_get_run_detail(
            ts=long_ts, max_stdout_chars=500))
        self.assertIn("truncated at 500 chars", out)

    def test_history_pagination(self):
        out = asyncio.run(server.verify_list_run_history(
            limit=1, offset=0, response_format="json"))
        d = json.loads(out)
        self.assertEqual(d["total"], 2)
        self.assertEqual(d["count"], 1)
        self.assertTrue(d["has_more"])
        self.assertEqual(d["next_offset"], 1)
        # history.jsonl summaries only (FULL_REC lives in runs/, not history)
        self.assertEqual(d["items"][0]["ts"], "2026-08-25T09:00:00.123456")

    def test_history_offset_pages_past_end(self):
        out = asyncio.run(server.verify_list_run_history(
            limit=10, offset=10, response_format="json"))
        d = json.loads(out)
        self.assertEqual(d["count"], 0)
        self.assertFalse(d["has_more"])
        self.assertIsNone(d["next_offset"])

    def test_history_markdown(self):
        out = asyncio.run(server.verify_list_run_history(limit=5))
        self.assertIn("Run history (2 of 2)", out)
        self.assertIn("PASS", out)

    def test_mirror_check_reuses_checker(self):
        fake_report = {"ok": True, "missing": [], "dead": [], "unexpected": []}
        with mock.patch.object(server.cmc, "main") as m_main:
            def _fake_main(argv):
                sys.stdout.write(json.dumps(fake_report))
                return 0
            m_main.side_effect = _fake_main
            out = asyncio.run(server.verify_check_mirror(response_format="json"))
        d = json.loads(out)
        self.assertTrue(d["ok"])
        self.assertEqual(d["exit_code"], 0)
        m_main.assert_called_once()
        self.assertIn("--json", m_main.call_args[0][0])

    def test_mirror_check_failure_is_actionable(self):
        with mock.patch.object(server.cmc, "main") as m_main:
            m_main.side_effect = lambda argv: 2
            out = asyncio.run(server.verify_check_mirror())
        self.assertIn("Error: mirror check failed (exit 2)", out)


class StdioSmokeTests(unittest.TestCase):
    """Real JSON-RPC session over the server's stdio transport."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="vmcp-")
        self.addCleanup(self._tmp.cleanup)
        self._preview = make_preview_dir(self._tmp.name)
        self._proc = subprocess.Popen(
            [sys.executable, SERVER_PY, "--preview-dir", self._preview],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self.addCleanup(self._proc.kill)

    def _rpc(self, payload):
        line = json.dumps(payload)
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()
        resp = self._proc.stdout.readline()
        self.assertTrue(resp, "server exited without response")
        return json.loads(resp)

    def test_initialize_list_and_call(self):
        init = self._rpc({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "verify_mcp-test", "version": "0"},
            },
        })
        self.assertIn("result", init)

        listed = self._rpc({
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/list", "params": {},
        })
        tools = {t["name"]: t for t in listed["result"]["tools"]}
        self.assertEqual(
            set(tools),
            {"verify_get_latest", "verify_get_layer_status",
             "verify_get_run_detail", "verify_list_run_history",
             "verify_check_mirror"},
        )
        for name, t in tools.items():
            self.assertTrue(t["annotations"]["readOnlyHint"], name)
            self.assertFalse(t["annotations"]["destructiveHint"], name)

        called = self._rpc({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {
                "name": "verify_get_latest",
                "arguments": {"response_format": "json"},
            },
        })
        content = called["result"]["content"][0]["text"]
        d = json.loads(content)
        self.assertEqual(d["verdict"], "FAIL")
        self.assertEqual(d["ts"], FULL_REC["ts"])


if __name__ == "__main__":
    unittest.main()
