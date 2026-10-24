#!/usr/bin/env python3
"""test_vercel_latest_preview.py — en guncel preview cozucu sozlesmesi.

Ag-dis: Vercel API'si `urllib.request.urlopen` mock'lanir. Sozlesme:
  * liste yeniden-eskiye — READY + production-disi ILK kayit kazanir,
  * BUILDING/ERROR/QUEUED ve production atlanir (yayinda olmayan URL
    "en guncel" diye dondurulmez),
  * semasiz `url` alanina https:// eklenir,
  * token/ project id yoksa exit 2, READY yoksa exit 1, HTTP hatasi exit 3,
  * token ciktiya SIZMAZ (stdout+stderr uzerinde dogrulanir).
"""
import contextlib
import importlib.util
import io
import json
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "vercel_latest_preview", HERE / "vercel_latest_preview.py")
VLP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(VLP)

TOKEN = "tok_test_ABC123"
PID = "prj_test"


class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _dep(url, target=None, state="READY", created=0):
    return {"url": url, "target": target, "readyState": state, "createdAt": created}


class TestPickLatestPreview(unittest.TestCase):
    def test_newest_ready_preview_wins(self):
        dep = VLP.pick_latest_preview([
            _dep("leibniz2-new-sarkis-env.vercel.app", created=3),
            _dep("leibniz2-old-sarkis-env.vercel.app", created=2),
            _dep("leibniz2.vercel.app", target="production", created=1),
        ])
        self.assertEqual(dep["url"], "https://leibniz2-new-sarkis-env.vercel.app")

    def test_skips_production_building_error(self):
        dep = VLP.pick_latest_preview([
            _dep("prod.vercel.app", target="production"),
            _dep("building.vercel.app", state="BUILDING"),
            _dep("error.vercel.app", state="ERROR"),
            _dep("ready.vercel.app", created=1),
        ])
        self.assertEqual(dep["url"], "https://ready.vercel.app")

    def test_adds_scheme_when_missing(self):
        dep = VLP.pick_latest_preview([_dep("bare.vercel.app")])
        self.assertEqual(dep["url"], "https://bare.vercel.app")

    def test_keeps_existing_scheme(self):
        dep = VLP.pick_latest_preview([_dep("http://local.test")])
        self.assertEqual(dep["url"], "http://local.test")

    def test_none_when_only_production(self):
        self.assertIsNone(VLP.pick_latest_preview([
            _dep("prod.vercel.app", target="production"),
        ]))

    def test_none_on_empty_and_garbage(self):
        self.assertIsNone(VLP.pick_latest_preview([]))
        self.assertIsNone(VLP.pick_latest_preview(None))
        self.assertIsNone(VLP.pick_latest_preview(["nope", _dep("", state="READY")]))


class TestCli(unittest.TestCase):
    def _run(self, argv, payload=None, exc=None, env=None):
        ctx = mock.patch.dict("os.environ", env or {}, clear=False)
        out, err = io.StringIO(), io.StringIO()
        with ctx, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if exc is not None:
                patcher = mock.patch.object(VLP.urllib.request, "urlopen", side_effect=exc)
            else:
                patcher = mock.patch.object(
                    VLP.urllib.request, "urlopen", return_value=_Resp(payload or {}))
            with patcher:
                rc = VLP.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_returns_url_and_exit_zero(self):
        rc, out, err = self._run(
            ["--project-id", PID, "--token", TOKEN],
            payload={"deployments": [
                _dep("prod.vercel.app", target="production"),
                _dep("leibniz2-abc-sarkis-env.vercel.app", created=9),
            ]})
        self.assertEqual(rc, 0, err)
        self.assertEqual(out.strip(), "https://leibniz2-abc-sarkis-env.vercel.app")

    def test_json_output_shape(self):
        rc, out, err = self._run(
            ["--project-id", PID, "--token", TOKEN, "--json"],
            payload={"deployments": [_dep("leibniz2-abc-sarkis-env.vercel.app",
                                          created=9)]})
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        self.assertEqual(data["url"], "https://leibniz2-abc-sarkis-env.vercel.app")
        self.assertEqual(data["project_id"], PID)
        self.assertEqual(set(data), {"url", "target", "readyState", "createdAt", "project_id"})

    def test_missing_token_exits_two(self):
        rc, out, err = self._run(["--project-id", PID], env={"VERCEL_TOKEN": ""})
        self.assertEqual(rc, 2)
        self.assertIn("VERCEL_TOKEN", err)
        self.assertEqual(out, "")

    def test_missing_project_id_exits_two(self):
        rc, out, err = self._run(["--token", TOKEN], env={"VERCEL_PROJECT_ID": ""})
        self.assertEqual(rc, 2)
        self.assertIn("project id", err)

    def test_env_fallback_for_inputs(self):
        rc, out, err = self._run(
            [], payload={"deployments": [_dep("leibniz2-env.vercel.app")]},
            env={"VERCEL_TOKEN": TOKEN, "VERCEL_PROJECT_ID": PID})
        self.assertEqual(rc, 0, err)
        self.assertEqual(out.strip(), "https://leibniz2-env.vercel.app")

    def test_no_ready_preview_exits_one(self):
        rc, out, err = self._run(
            ["--project-id", PID, "--token", TOKEN],
            payload={"deployments": [_dep("prod.vercel.app", target="production")]})
        self.assertEqual(rc, 1)
        self.assertIn("READY preview", err)
        self.assertEqual(out, "")

    def test_http_error_exits_three(self):
        exc = urllib.error.HTTPError(
            "https://api.vercel.com/x", 403, "Forbidden", {}, io.BytesIO(b'{"error":"nope"}'))
        rc, out, err = self._run(["--project-id", PID, "--token", TOKEN], exc=exc)
        self.assertEqual(rc, 3)
        self.assertIn("403", err)
        self.assertEqual(out, "")

    def test_token_never_leaks(self):
        for argv, payload, exc in (
            (["--project-id", PID, "--token", TOKEN],
             {"deployments": [_dep("leibniz2-abc-sarkis-env.vercel.app")]}, None),
            (["--project-id", PID, "--token", TOKEN], {"deployments": []}, None),
            (["--project-id", PID, "--token", TOKEN], None,
             urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b"x"))),
        ):
            rc, out, err = self._run(argv, payload=payload, exc=exc)
            self.assertNotIn(TOKEN, out + err, "token ciktiya sizmamali")


if __name__ == "__main__":
    unittest.main()
