#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_ci_rate_limit_resilience.py — GitHub API kotası dayanıklılığı.

Kontrat: CI'da kurulum kotası (403 "API rate limit exceeded for installation")
tükendiğinde kapılar NE yanlış-kırmızı NE de sessizce yeşil olmalı:

  1. refs_trend.py — kota ayrı bir sinyal (`RateLimited`) olarak yakalanır,
     geçici hatalar (429/5xx/ağ) sınırlı retry ile aşılır, kota kalıcıysa
     refs-trend.md'ye `VERDICT: INDETERMINATE-QUOTA` yazılır ve exit 3 döner.
     Workflow kapısı bu kararı OKUYUP uyarı vererek geçer (kör PASS değil).
  2. label_gate(.p1).js — etiketler olay yükünden okunur (0 REST çağrısı);
     yük yoksa REST'e düşer, REST de patlarsa FAIL-CLOSED setFailed.
  3. audit_live_ci_sync.run_gh — geçici/kota hatasında 3 deneme.
  4. Advisory job adımları (audit-live-ci, manifest PR yorumu) job'u
     kırmızıya çevirmez (continue-on-error).

stdlib unittest + YAML (varsa) — koşum ağı kullanmaz.
"""
import io
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import refs_trend as rt          # noqa: E402
import audit_live_ci_sync as als  # noqa: E402

WORKFLOW = CIKTI.parent.parent / ".github" / "workflows" / "verify.yml"
SCRIPTS = CIKTI / "github_scripts"


def _http_error(code, body=b"", headers=None):
    return urllib.error.HTTPError(
        "https://api.github.com/x", code, "boom", headers or {},
        io.BytesIO(body))


class TestRateLimitDetection(unittest.TestCase):
    """Hangi yanıt kota sayılır? (yanlış sınıflama sessiz fail-open üretir)"""

    def test_403_with_zero_remaining_is_rate_limited(self):
        self.assertTrue(rt._is_rate_limited(
            403, {"x-ratelimit-remaining": "0"}, b""))

    def test_403_with_installation_message_is_rate_limited(self):
        self.assertTrue(rt._is_rate_limited(
            403, {}, b'{"message":"API rate limit exceeded for installation 1"}'))

    def test_429_is_rate_limited(self):
        self.assertTrue(rt._is_rate_limited(429, {}, b""))

    def test_403_permission_denied_is_not_rate_limit(self):
        # Yetki hatası kota DEĞİL — exit 1 yolu (gerçek arıza) korunur.
        self.assertFalse(rt._is_rate_limited(
            403, {"x-ratelimit-remaining": "4999"},
            b'{"message":"Resource not accessible by integration"}'))

    def test_500_is_not_rate_limit(self):
        self.assertFalse(rt._is_rate_limited(500, {}, b""))


class TestApiGetRetry(unittest.TestCase):
    """Geçici hata retry'ı ve kotanın retry EDİLMEMESİ."""

    def _run(self, http_get, delays=(0, 0, 0)):
        with mock.patch.object(rt, "_http_get", side_effect=http_get) as m:
            try:
                out = rt.api_get("/x", token="t", delays=delays)
            except Exception as e:  # noqa: BLE001 — çağıran sınıflar test edilir
                return e, m.call_count
        return out, m.call_count

    def test_transient_503_is_retried_then_succeeds(self):
        calls = {"n": 0}

        def http_get(req, binary):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(503, b"upstream")
            return {"ok": True}

        out, n = self._run(http_get)
        self.assertEqual(out, {"ok": True})
        self.assertEqual(n, 2, "503 tek denemede pes etmemeli")

    def test_rate_limit_is_not_retried(self):
        err = _http_error(
            403, b'{"message":"API rate limit exceeded for installation"}',
            {"x-ratelimit-remaining": "0"})
        exc, n = self._run(lambda req, binary: (_ for _ in ()).throw(err))
        self.assertIsInstance(exc, rt.RateLimited)
        self.assertEqual(n, 1, "kota tükenmesi retry ile düzelmez — hemen yüksel")

    def test_not_found_raises_immediately(self):
        err = _http_error(404, b'{"message":"Not Found"}')
        exc, n = self._run(lambda req, binary: (_ for _ in ()).throw(err))
        self.assertIsInstance(exc, RuntimeError)
        self.assertNotIsInstance(exc, rt.RateLimited)
        self.assertEqual(n, 1)


class TestQuotaDegradedReport(unittest.TestCase):
    """Kota → md/json KARAR dosyası + exit 3 (sessiz boş tablo yok)."""

    def test_writer_emits_machine_readable_verdict(self):
        with tempfile.TemporaryDirectory() as td:
            md = rt.write_quota_degraded(td, "o/r", "2026-10-24T00:00:00+00:00",
                                         "HTTP 403: rate limit")
            text = pathlib.Path(md).read_text(encoding="utf-8")
            self.assertIn(rt.QUOTA_MARKER, text)
            self.assertIn(rt.QUOTA_MARKER, text.split("```")[1])
            data = json.loads((pathlib.Path(td) / "refs-trend.json")
                              .read_text(encoding="utf-8"))
            self.assertEqual(data["verdict"], "INDETERMINATE-QUOTA")
            self.assertEqual(data["rows"], [])

    def test_main_exits_three_and_writes_marker(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(rt, "fetch_refs_online_artifacts",
                                   side_effect=rt.RateLimited("HTTP 403")), \
                 mock.patch.object(sys, "argv",
                                   ["refs_trend.py", "--repo", "o/r",
                                    "--out-dir", td]), \
                 mock.patch("sys.stderr", new=io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    rt.main()
            self.assertEqual(cm.exception.code, 3)
            text = (pathlib.Path(td) / "refs-trend.md").read_text(encoding="utf-8")
            self.assertIn(rt.QUOTA_MARKER, text)

    def test_default_download_budget_is_bounded(self):
        # Her zip = 1 API çağrısı; tek kaynak sabit 25 (kota koruması).
        self.assertEqual(rt.DEFAULT_MAX_DOWNLOADS, 25)
        src = pathlib.Path(rt.__file__).read_text(encoding="utf-8")
        self.assertIn("default=DEFAULT_MAX_DOWNLOADS", src)


class TestWorkflowQuotaGate(unittest.TestCase):
    """Kapı, kararı OKUR; kör PASS vermez, kör FAIL de vermez."""

    def _text(self):
        return WORKFLOW.read_text(encoding="utf-8")

    def test_gate_reads_indeterminate_marker(self):
        text = self._text()
        self.assertIn('grep -q "VERDICT: INDETERMINATE-QUOTA"', text)

    def test_gate_warns_instead_of_silent_pass(self):
        text = self._text()
        i = text.index('grep -q "VERDICT: INDETERMINATE-QUOTA"')
        block = text[i:i + 400]
        self.assertIn("::warning", block)
        self.assertIn("exit 0", block)

    def test_missing_table_still_fail_closed(self):
        text = self._text()
        i = text.index("REFS-TREND P0: refs-trend.md üretilmedi")
        self.assertIn("exit 1", text[i:i + 300])

    def test_download_budget_passed_to_script(self):
        self.assertIn("--max-downloads 25", self._text())

    def test_advisory_steps_do_not_break_build(self):
        try:
            import yaml
        except ImportError:  # pragma: no cover
            self.skipTest("PyYAML yok — metin kontratı testleri yukarıda")
        doc = yaml.safe_load(self._text())
        jobs = doc["jobs"]

        def step(job, needle):
            for st in jobs[job]["steps"]:
                if needle in (st.get("name") or ""):
                    return st
            raise AssertionError(f"{job}: adım bulunamadı: {needle}")

        self.assertIs(step("audit-live-ci",
                           "Run live CI audit").get("continue-on-error"), True)
        self.assertIs(step("manifest-comment",
                           "Upsert manifest + config-diff PR comments")
                      .get("continue-on-error"), True)
        # Bloke eden REQUIRED kapılar advisory'e DÖNÜŞMEMELİ.
        self.assertIsNone(step("label-gate",
                               "Fail if precommit-p0 label is present")
                          .get("continue-on-error"))


class TestLabelGatePayloadFirst(unittest.TestCase):
    """Etiketler olay yükünden; REST yalnız yedek; hata → FAIL-CLOSED."""

    def _src(self, name):
        return (SCRIPTS / name).read_text(encoding="utf-8")

    def test_reads_labels_from_payload_first(self):
        for name in ("label_gate.js", "label_gate_p1.js"):
            src = self._src(name)
            self.assertIn("context.payload.pull_request", src, name)
            self.assertIn("Array.isArray(pr.labels)", src, name)
            # Payload okuması, REST çağrısından ÖNCE olmalı.
            self.assertLess(src.index("labelsFromPayload()"),
                            src.index("github.rest.issues.listLabelsOnIssue"),
                            f"{name}: payload yolu önce gelmeli")

    def test_api_failure_is_fail_closed(self):
        for name in ("label_gate.js", "label_gate_p1.js"):
            src = self._src(name)
            self.assertIn("FAIL-CLOSED", src, name)
            self.assertIn("core.setFailed", src, name)

    def test_battery_covers_quota_paths(self):
        text = (CIKTI / "github_scripts_battery.py").read_text(encoding="utf-8")
        self.assertIn("etiketler olay yükünde", text)
        self.assertIn("FAIL-CLOSED setFailed", text)
        self.assertIn("mock_api_error.json", text)


class TestAuditRunGhRetry(unittest.TestCase):
    """gh çağrısı: geçici/kota hatasında 3 deneme, gerçek hatada hemen."""

    def test_retries_rate_limit_then_succeeds(self):
        calls = {"n": 0}

        def fake(args, capture_output=True, text=True):
            calls["n"] += 1
            if calls["n"] < 3:
                return mock.Mock(returncode=1,
                                 stderr="HTTP 403: API rate limit exceeded",
                                 stdout="")
            return mock.Mock(returncode=0, stderr="", stdout="ok\n")

        with mock.patch.object(als, "RETRY_DELAYS", (0, 0, 0)), \
             mock.patch.object(als.subprocess, "run", side_effect=fake):
            self.assertEqual(als.run_gh(["gh", "run", "list"]), "ok")
        self.assertEqual(calls["n"], 3)

    def test_non_retryable_error_raises_once(self):
        calls = {"n": 0}

        def fake(args, capture_output=True, text=True):
            calls["n"] += 1
            return mock.Mock(returncode=1, stderr="run not found", stdout="")

        with mock.patch.object(als, "RETRY_DELAYS", (0, 0, 0)), \
             mock.patch.object(als.subprocess, "run", side_effect=fake):
            with self.assertRaises(RuntimeError) as cm:
                als.run_gh(["gh", "run", "view", "1"])
        self.assertIn("run not found", str(cm.exception))
        self.assertEqual(calls["n"], 1)

    def test_exhausted_retries_raise_loudly(self):
        def fake(args, capture_output=True, text=True):
            return mock.Mock(returncode=1,
                             stderr="HTTP 503: server error", stdout="")

        with mock.patch.object(als, "RETRY_DELAYS", (0, 0, 0)), \
             mock.patch.object(als.subprocess, "run", side_effect=fake):
            with self.assertRaises(RuntimeError):
                als.run_gh(["gh", "api", "x"])


if __name__ == "__main__":
    unittest.main()
