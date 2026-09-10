#!/usr/bin/env python3
"""orchestrate_k_dag.py birim testleri.

Mock modda (--mock) opencode çağrılmaz; task komutu gerçekten koşar ve
script_rc'den deterministik worker_done sidecar'ı üretilir. Bu sayede:
- DAG sırası (deps) doğrulanır,
- worker_done birleştirme sözleşmesi sabitlenir,
- fail-closed rapor (herhangi bir FAIL → exit 1) test edilir,
- ağ/model gerektirmez (CI güvenli).
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orchestrate_k_dag as okd  # noqa: E402


def _run_main(worktree, done_dir, **kw):
    """main()'i mock olarak koşar → (rc, report_json)."""
    argv = ["--worktree", worktree, "--done-dir", done_dir, "--mock"]
    for k, v in kw.items():
        argv += ["--%s" % k.replace("_", "-"), str(v)]
    rc = okd.main(argv)
    with open(os.path.join(done_dir, okd.RAPOR_JSON), encoding="utf-8") as f:
        rep = json.load(f)
    return rc, rep


def _knum(s):
    """'K10' → 10 (doğal sıralama)."""
    return int("".join(ch for ch in s if ch.isdigit()) or 0)


class TestStdinClosed(unittest.TestCase):
    def test_worker_invocation_closes_stdin(self):
        task = okd.task_map()["K1"]
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(okd, "run_command", return_value=(0, "ok")), \
             mock.patch.object(okd, "_locate_opencode", return_value="opencode", create=True), \
             mock.patch.object(okd.subprocess, "run", return_value=mock.Mock(stdout="")) as run:
            # Worker sidecar is absent, so this exercises the opencode call and
            # its fail-closed fallback without invoking a real model.
            okd.opencode_worker(task, str(self) if False else td, td, None, 5, mock=False)
        calls = [c for c in run.call_args_list if c.args and c.args[0][:2] == ["opencode", "run"]]
        self.assertTrue(calls)
        self.assertIs(calls[0].kwargs["stdin"], okd.subprocess.DEVNULL)


class TestTaskMap(unittest.TestCase):
    def test_twelve_tasks_k1_k12(self):
        tm = okd.task_map()
        self.assertEqual(sorted(tm, key=_knum), ["K%d" % i for i in range(1, 13)])

    def test_deps_only_existing_tasks(self):
        tm = okd.task_map()
        for t in tm.values():
            for d in t["deps"]:
                self.assertIn(d, tm, "K%s bilinmeyen dep: %s" % (t["id"], d))

    def test_dag_acyclic(self):
        # topolojik seviye üretimi döngüyü RuntimeError ile yakalar
        levels = okd.topological_levels(okd.task_map())
        seen = set()
        for lv in levels:
            for t in lv:
                for d in t["deps"]:
                    self.assertIn(d, seen,
                                  "K%s dep K%s aynı/sonraki seviyede" % (t["id"], d))
                seen.add(t["id"])
        self.assertEqual(len(seen), 12)


ORIG_TASKS = list(okd.TASKS)


class TestMockFlow(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.wt = pathlib.Path(self.td.name, "wt")
        self.wt.mkdir()
        self.done = pathlib.Path(self.td.name, "done")

    def tearDown(self):
        okd.TASKS[:] = ORIG_TASKS  # test mutasyonunu geri al
        self.td.cleanup()

    def _ok_cmd(self, ids):
        """Seçilen task'ların komutunu geçerli bir no-op'a çevirir."""
        for i, (tid, label, _cmd, deps) in enumerate(okd.TASKS):
            if tid in ids:
                okd.TASKS[i] = (tid, label, "echo theorem th1", deps)

    def test_all_pass_returns_zero(self):
        self._ok_cmd(set(okd.task_map()))
        rc, rep = _run_main(str(self.wt), str(self.done))
        self.assertEqual(rc, 0)
        self.assertEqual(rep["verdict"], "PASS")
        self.assertEqual(rep["failures"], [])
        self.assertEqual(len(rep["tasks"]), 12)
        for r in rep["tasks"].values():
            self.assertEqual(r["status"], "PASS")

    def test_fail_closed_single_failure(self):
        self._ok_cmd(set(okd.task_map()) - {"K6"})  # K6 gerçek audit koşar → fail
        rc, rep = _run_main(str(self.wt), str(self.done))
        self.assertEqual(rc, 1)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertIn("K6", rep["failures"])
        self.assertEqual(rep["tasks"]["K6"]["status"], "FAIL")

    def test_dep_blocked_task_skipped(self):
        # K7 komutunu bilerek bozuk yap; K8 (K7'ye bağımlı) SKIP olmalı.
        for i, (tid, label, _cmd, deps) in enumerate(okd.TASKS):
            if tid in ("K7", "K8"):
                cmd = "false" if tid == "K7" else "echo ok"
                okd.TASKS[i] = (tid, label, cmd, deps)
        tm = okd.task_map()
        rc, rep = _run_main(str(self.wt), str(self.done))
        self.assertEqual(rc, 1)
        self.assertEqual(rep["tasks"]["K7"]["status"], "FAIL")
        self.assertEqual(rep["tasks"]["K8"]["status"], "SKIP")
        self.assertIn("K8", rep["failures"])  # SKIP de fail-closed sayılır
        self.assertIn("dep başarısız: K7", rep["tasks"]["K8"]["summary"])

    def test_worker_done_sidecar_files_written(self):
        self._ok_cmd(set(okd.task_map()))
        _run_main(str(self.wt), str(self.done))
        files = sorted((p.name for p in self.done.iterdir()
                        if p.name.startswith("worker_done_")), key=_knum)
        self.assertEqual(files,
                         ["worker_done_K%d.json" % i for i in range(1, 13)])
        # sidecar sözleşmesi
        s = json.loads((self.done / "worker_done_K1.json").read_text())
        for key in ("task", "label", "status", "rc", "summary", "detail"):
            self.assertIn(key, s)
        self.assertEqual(s["task"], "K1")

    def test_report_files_written(self):
        self._ok_cmd(set(okd.task_map()))
        _run_main(str(self.wt), str(self.done))
        md = (self.done / okd.RAPOR_MD).read_text()
        self.assertIn("# K1-K12 Orchestration Raporu", md)
        self.assertIn("| K1 | PASS |", md)
        self.assertIn("**PASS**", md)
        self.assertTrue((self.done / okd.RAPOR_JSON).is_file())

    def test_only_subset(self):
        self._ok_cmd({"K1", "K2"})
        rc, rep = _run_main(str(self.wt), str(self.done), only="K1,K2")
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(rep["tasks"]), ["K1", "K2"])


if __name__ == "__main__":
    unittest.main()
