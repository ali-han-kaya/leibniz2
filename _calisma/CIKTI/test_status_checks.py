#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_status_checks.py — branch protection smoke kapısı.

status_checks.py'nin pure mantığını deterministik doğrular: gate_jobs
(required adayları), merge_block_smoke (strict/enforce_admins/force-push/
deletions) ve evaluate_protection (ad eşleşmesi + enforcement). Ayrıca
--gh entegrasyonu mock'lanmış run_gh ile (canlı ağ yok) doğrulanır.

PyYAML gerektirir (status_checks.py modül-seviyesi import). CI birim test
adımında pyyaml yoksa bu dosya bütünüyle SKIP olur (test_check_action_runtimes.py
ile aynı desen).
"""
import contextlib
import io
import json
import os
import pathlib
import sys
import unittest
from unittest import mock

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

if HAVE_YAML:
    CIKTI = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(CIKTI))
    import status_checks as sc  # noqa: E402

    # gate_jobs WORKFLOW yolunu okur — testler CIKTI'dan da repo kökünden de
    # koşulabilsin diye mutlak yola çöz (hook CIKTI cwd'sinde koşar).
    _WORKFLOW = CIKTI.parent.parent / ".github" / "workflows" / "verify.yml"


def _protection(contexts=None, strict=True, enforce_admins=True,
                force_pushes=False, deletions=False, pr_reviews=False):
    """Koruma nesnesi. `pr_reviews=True` → PR zorunlu (strict uygulanır)."""
    return {
        "required_status_checks": {
            "contexts": contexts or [],
            "strict": strict,
        },
        "enforce_admins": {"enabled": enforce_admins},
        "allow_force_pushes": {"enabled": force_pushes},
        "allow_deletions": {"enabled": deletions},
        "required_pull_request_reviews": (
            {"required_approving_review_count": 1} if pr_reviews else None),
    }


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestGateJobs(unittest.TestCase):
    def test_excludes_gates_and_advisory(self):
        gates = sc.gate_jobs()
        self.assertNotIn("manifest-comment", gates)
        self.assertNotIn("precheck", gates)
        self.assertIn("label-gate", gates)           # BİLEREK required (P0 gate)
        self.assertNotIn("label-gate-p1", gates)     # PR-only (opsiyonel)
        self.assertIn("commit-msg-gate", gates)      # PR-only ama required (2026-08-23)
        self.assertNotIn("plist-check", gates)       # macOS-advisory
        self.assertNotIn("mirror-check", gates)      # macOS fail-closed (advisory)
        self.assertNotIn("daemon-http", gates)       # advisory smoke
        self.assertIn("ci-simulate", gates)          # required: tam replay kapısı
        self.assertIn("config-sync", gates)          # required: üçlü senkron kapısı
        self.assertNotIn("audit-refs-trend", gates)  # advisory denetim
        self.assertNotIn("changelog-drift", gates)   # advisory: changelog drift
        # 2026-10-25: macOS smoke'ları adlarında "advisory" taşır ve canlı
        # protected sette YOK; dashboard-smoke ise canlı protected sette var
        # ve fail-closed koşar → required.
        self.assertNotIn("preview-reload-smoke", gates)
        self.assertNotIn("webkit-smoke", gates)
        self.assertIn("dashboard-smoke", gates)
        # Node 24 yükseltmesiyle eklenen job required aday olmalı.
        self.assertIn("action-runtimes", gates)
        self.assertEqual(gates["action-runtimes"],
                         "Action runtime check (node24)")

    def test_count_matches_workflow_minus_excludes(self):
        # 32 job − 16 hariç = 16 required (tek kaynak: workflow).
        # 2026-10-25: webkit-smoke ve preview-reload-smoke adlarında "advisory"
        # taşıdıkları ve canlı protected sette olmadıkları için exclude edildi;
        # dashboard-smoke ve plist-p1 canlı protected sette required oldukları
        # için required kümededir. Türetilen 16 ad canlı branch protection
        # context listesiyle birebir aynı
        # (ölçüm: `gh api .../branches/main/protection/required_status_checks`).
        self.assertEqual(len(sc.gate_jobs()), 16)

    def test_gate_jobs_exact_set_includes_label_gate(self):
        """gate_jobs() tam id kümesini birebir sabitler (fail-closed).

        Workflow'a yeni bir gate job eklenir/çıkarılır/rename edilirse bu
        test BİLİNÇLİ olarak kırılır — branch protection required setiyle
        senkron kararı insana bırakılır (yanlış-PASS yok). label-gate
        BİLEREK bu kümededir: P0 label kapısı required'dır.

        NOT: Kapsam 14 değil 15'tir — 14, a11y-gate eklenmeden önceki
        sayıydı; texlive-accept (R3 kabulü) ile 15'e büyüdü.
        """
        self.assertEqual(
            set(sc.gate_jobs()),
            {
                "verify",
                "action-runtimes",
                "budget",
                "label-gate",
                "commit-msg-gate",
                "reports",
                "reproducibility",
                "config-drift",
                "config-sync",
                "repack-verify",
                "refs-trend",
                "dashboard-smoke",
                "plist-p1",
                "ci-simulate",
                "a11y-gate",
                "texlive-accept",
            },
        )
        # label-gate P0 kapısı required aday olmalı (özel vurgu).
        self.assertIn("label-gate", sc.gate_jobs())
        self.assertEqual(sc.gate_jobs()["label-gate"],
                         "Pre-commit P0 label gate")

    def test_advisory_decision_2026_09_04(self):
        """2026-09-04 required/advisory denetimi (GitHub required setiyle
        birebir doğrulandı): reports/reproducibility/refs-trend REQUIRED —
        hiçbiri fail-open değil (tüketim job içinde bağlı / K10 set -e
        fail-closed / in-job üretim); lake-proof ADVISORY — ayrı-step K9,
        verify --full bağımsız koşar.
        """
        gates = set(sc.gate_jobs())
        for jid in ("reports", "reproducibility", "refs-trend"):
            self.assertIn(jid, gates, f"{jid} required kalmalı")
        self.assertNotIn("lake-proof", gates,
                         "lake-proof advisory kalmalı (exclude'da)")
        self.assertIn("lake-proof", sc.GATE_EXCLUDE)


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestAdvisoryContract(unittest.TestCase):
    """Advisory kontratı: plist-check ve tüm exclude'lar required DEĞİL."""

    def test_real_workflow_passes(self):
        c = sc.advisory_contract()
        self.assertTrue(c["ok"], c["issues"])
        self.assertTrue(c["plist_check"]["ok"])
        self.assertEqual(c["plist_check"]["name"],
                         "Plist drift check (macOS, advisory)")
        self.assertFalse(c["plist_check"]["required"])
        self.assertIn("Plist drift check (macOS, advisory)", c["advisory"])
        # Fark = tüm adlar − required adlar; her exclude job advisory'de.
        self.assertEqual(len(c["advisory"]), len(sc.GATE_EXCLUDE))
        for jid in sc.GATE_EXCLUDE:
            self.assertNotIn(c["all_jobs"][jid], c["required"])

    def test_plist_check_required_fails(self):
        # GATE_EXCLUDE'dan plist-check düşerse (required'a girer) kontrat FAIL.
        with mock.patch.object(sc, "GATE_EXCLUDE",
                               sc.GATE_EXCLUDE - {"plist-check"}):
            c = sc.advisory_contract()
        self.assertFalse(c["ok"])
        self.assertFalse(c["plist_check"]["ok"])
        self.assertTrue(c["plist_check"]["required"])
        self.assertTrue(any("plist-check" in i for i in c["issues"]))

    def test_stale_exclude_fails(self):
        # Exclude edilen job workflow'dan silinirse bayat exclude → FAIL.
        data = {"jobs": {
            "verify": {"name": "Delivery verification — K1-K14 (single entry point)"}}}
        c = sc.advisory_contract(data)
        self.assertFalse(c["ok"])
        self.assertTrue(any("yok" in i for i in c["issues"]))
        self.assertFalse(c["plist_check"]["ok"])

    def test_name_collision_fails(self):
        # Required job, exclude edilen job'la AYNI ada sahipse → çakışma FAIL.
        data = {"jobs": {
            "plist-check": {"name": "Plist drift check (macOS, advisory)"},
            "other": {"name": "Plist drift check (macOS, advisory)"},
        }}
        c = sc.advisory_contract(data)
        self.assertFalse(c["ok"])
        self.assertTrue(any("çakışma" in i for i in c["issues"]))
        self.assertTrue(c["plist_check"]["required"])

    def test_main_exits_1_when_contract_broken(self):
        # main() fail-closed: kontrat ihlalinde JSON modunda da exit 1.
        with mock.patch.object(sc, "advisory_contract") as m:
            m.return_value = {
                "ok": False,
                "all_jobs": {"plist-check": "Plist drift check (macOS, advisory)"},
                "required": ["Plist drift check (macOS, advisory)"],
                "advisory": [],
                "plist_check": {"job_id": "plist-check",
                                 "name": "Plist drift check (macOS, advisory)",
                                 "required": True, "ok": False},
                "issues": ["'plist-check' required sette — advisory olmalı"],
            }
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--json"])
        self.assertEqual(cm.exception.code, 1)


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestMergeBlockSmoke(unittest.TestCase):
    def _row(self, smoke, label="required_status_checks.strict"):
        return next(r for r in smoke if r[0] == label)

    def test_all_pass_when_fully_enforced(self):
        smoke = sc.merge_block_smoke(
            _protection(["a"], strict=True, enforce_admins=True,
                        force_pushes=False, deletions=False, pr_reviews=True))
        self.assertTrue(all(ok for (_l, ok, _n) in smoke))
        self.assertEqual(len(smoke), 4)

    def test_all_fail_when_bypass_open(self):
        # strict eksik + diğer bypass'lar açık → tümü FAIL.
        prot = _protection(["a"], enforce_admins=False,
                           force_pushes=True, deletions=True, pr_reviews=True)
        prot["required_status_checks"]["strict"] = None
        smoke = sc.merge_block_smoke(prot)
        self.assertFalse(any(ok for (_l, ok, _n) in smoke))

    def test_strict_off_is_red_when_pr_required(self):
        """Asıl açık: strict=False PR-akışında FAIL etmeli (varlık yetmez)."""
        smoke = sc.merge_block_smoke(_protection(["a"], strict=False,
                                                 pr_reviews=True))
        label, ok, note = self._row(smoke)
        self.assertFalse(ok, "strict kapalı PR-akışında yakalanmalı")
        self.assertIn("strict kapalı", note)

    def test_strict_off_is_green_for_direct_push(self):
        """Direct-push: PR dalı yok → strict yok/False meşru, kırmızıya düşmez."""
        for strict in (False, None):
            smoke = sc.merge_block_smoke(_protection(["a"], strict=strict))
            label, ok, note = self._row(smoke)
            self.assertTrue(ok, "direct-push %r: %s" % (strict, note))
            self.assertIn("direct-push", note)

    def test_pr_flow_override_beats_inference(self):
        # Akışı bilen çağıran tahmini ezer: reviews yok ama pr_flow=True.
        label, ok, _n = self._row(sc.merge_block_smoke(
            _protection(["a"], strict=False), pr_flow=True))
        self.assertFalse(ok)
        # reviews var ama pr_flow=False → strict uygulanmaz.
        label, ok, _n = self._row(sc.merge_block_smoke(
            _protection(["a"], strict=False, pr_reviews=True), pr_flow=False))
        self.assertTrue(ok)

    def test_missing_status_checks_still_fails_closed(self):
        # required_status_checks hiç yok: strict'in uygulanabilirliği kanıtsız.
        prot = _protection(["a"], pr_reviews=True)
        prot["required_status_checks"] = None
        label, ok, note = self._row(sc.merge_block_smoke(prot))
        self.assertFalse(ok)
        self.assertIn("required_status_checks yok", note)

    def test_empty_protection_fails_closed(self):
        # Alanlar eksikse enforcement KANITLANAMAZ → FAIL (yanlış PASS yok).
        smoke = sc.merge_block_smoke({})
        self.assertFalse(any(ok for (_l, ok, _n) in smoke))

    def test_labels_distinguish_merge_block(self):
        labels = [l for (l, _ok, _n) in sc.merge_block_smoke({})]
        self.assertIn("required_status_checks.strict", labels)
        self.assertIn("enforce_admins.enabled (admin bypass kapalı)", labels)


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestEvaluateProtection(unittest.TestCase):
    def test_names_and_enforcement_both_pass(self):
        r = sc.evaluate_protection(["a", "b"],
                                   _protection(["a", "b"]))
        self.assertTrue(r["names_ok"])
        self.assertTrue(r["enforcement_ok"])
        self.assertEqual(r["missing"], [])
        self.assertEqual(r["extra"], [])

    def test_names_drift_detected(self):
        r = sc.evaluate_protection(["a", "b", "c"],
                                   _protection(["a", "b"]))
        self.assertFalse(r["names_ok"])
        self.assertEqual(r["missing"], ["c"])
        self.assertEqual(r["extra"], [])

    def test_extra_check_detected(self):
        r = sc.evaluate_protection(["a"], _protection(["a", "b"]))
        self.assertFalse(r["names_ok"])
        self.assertEqual(r["extra"], ["b"])

    def test_enforcement_fail_when_strict_missing(self):
        # PR-akışında strict alan tanımlı değilse enforcement FAIL.
        r = sc.evaluate_protection(["a"], {
            "required_status_checks": {"contexts": ["a"]},
            "enforce_admins": {"enabled": True},
            "allow_force_pushes": {"enabled": False},
            "allow_deletions": {"enabled": False},
            "required_pull_request_reviews": {"required_approving_review_count": 1},
        })
        self.assertTrue(r["names_ok"])
        self.assertFalse(r["enforcement_ok"])
        self.assertIs(r["pr_flow"], True)

    def test_strict_false_is_valid_for_direct_push(self):
        # strict=False: PR yolu yok — doğrudan push akışında geçerli.
        r = sc.evaluate_protection(["a"], _protection(["a"], strict=False))
        self.assertTrue(r["names_ok"])
        self.assertTrue(r["enforcement_ok"])
        self.assertIs(r["pr_flow"], False)

    def test_strict_false_is_invalid_for_pr_flow(self):
        # Aynı koruma PR zorunluyken: strict kapalı → enforcement FAIL.
        r = sc.evaluate_protection(
            ["a"], _protection(["a"], strict=False, pr_reviews=True))
        self.assertTrue(r["names_ok"])
        self.assertFalse(r["enforcement_ok"])
        self.assertIs(r["pr_flow"], True)

    def test_pr_flow_override_in_evaluate(self):
        # reviews yok ama akış PR: açık override ile strict yakalanır.
        r = sc.evaluate_protection(["a"], _protection(["a"], strict=False),
                                   pr_flow=True)
        self.assertFalse(r["enforcement_ok"])
        self.assertIs(r["pr_flow"], True)

    def test_null_contexts_treated_as_empty(self):
        p = _protection(None)
        p["required_status_checks"]["contexts"] = None
        r = sc.evaluate_protection(["a"], p)
        self.assertEqual(r["configured"], [])
        self.assertFalse(r["names_ok"])


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestGhIntegration(unittest.TestCase):
    """--gh yolunu mock'lanmış run_gh ile test eder (canlı ağ yok)."""

    def _run_main(self, protection_obj):
        with mock.patch.object(sc, "run_gh",
                               return_value=json.dumps(protection_obj)):
            return sc.main(["--gh", "--repo", "owner/name"])

    def test_full_pass_returns_none(self):
        # Beklenen 12 ad + tam enforcement → exit 0 (return None, SystemExit yok).
        checks = list(sc.gate_jobs().values())
        rc = self._run_main(_protection(checks))
        self.assertIsNone(rc)

    def test_names_drift_exits_1(self):
        with mock.patch.object(sc, "run_gh",
                               return_value=json.dumps(_protection(["x"]))):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name"])
        self.assertEqual(cm.exception.code, 1)

    def test_enforcement_fail_exits_1(self):
        checks = list(sc.gate_jobs().values())
        bad = _protection(checks, strict=False, enforce_admins=False)
        with mock.patch.object(sc, "run_gh",
                               return_value=json.dumps(bad)):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name"])
        self.assertEqual(cm.exception.code, 1)

    def test_gh_strict_off_with_pr_flow_exits_1(self):
        """Regresyon: PR-akışlı repoda strict kapatılınca --gh KIRMIZI olmalı."""
        checks = list(sc.gate_jobs().values())
        bad = _protection(checks, strict=False, pr_reviews=True)
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh", return_value=json.dumps(bad)), \
                mock.patch.object(sys, "stdout", new=buf):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertEqual(cm.exception.code, 1)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "FAIL")
        self.assertIs(d["pr_flow"], True)
        row = next(r for r in d["smoke"]
                   if r["label"] == "required_status_checks.strict")
        self.assertFalse(row["ok"])
        self.assertIn("strict kapalı", row["note"])

    def test_gh_direct_push_repo_without_strict_passes(self):
        """Aynı ayar direct-push deposunda yeşil kalmalı (yanlış-kırmızı yok)."""
        checks = list(sc.gate_jobs().values())
        ok = _protection(checks, strict=False)  # reviews yok → direct-push
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh", return_value=json.dumps(ok)), \
                mock.patch.object(sys, "stdout", new=buf):
            rc = sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertIsNone(rc)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "PASS")
        self.assertIs(d["pr_flow"], False)
        row = next(r for r in d["smoke"]
                   if r["label"] == "required_status_checks.strict")
        self.assertTrue(row["ok"])
        self.assertIn("direct-push", row["note"])

    def test_no_protection_exits_1(self):
        # run_gh RuntimeError → "branch protection kurulu değil" → exit 1 (fail-closed).
        with mock.patch.object(sc, "run_gh",
                               side_effect=RuntimeError("Branch not protected")), \
                mock.patch.object(sys, "stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name"])
        self.assertEqual(cm.exception.code, 1)

    def test_gh_json_pass(self):
        checks = list(sc.gate_jobs().values())
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh",
                               return_value=json.dumps(_protection(checks))), \
                mock.patch.object(sys, "stdout", new=buf):
            rc = sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertIsNone(rc)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "PASS")
        self.assertTrue(d["names_ok"])
        self.assertTrue(d["enforcement_ok"])
        # Advisory kontratı OFFLINE hesaplanır ve --gh --json çıktısında da
        # taşınır — precheck job'ı advisory_contract.ok'ı buradan denetler.
        ac = d.get("advisory_contract") or {}
        self.assertIs(ac.get("ok"), True)
        self.assertIn("plist_check", ac)
        self.assertIs(ac["plist_check"]["ok"], True)

    def test_gh_json_fail_exits_1(self):
        checks = list(sc.gate_jobs().values())
        bad = _protection(checks, enforce_admins=False)
        bad["required_status_checks"]["strict"] = None
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh",
                               return_value=json.dumps(bad)), \
                mock.patch.object(sys, "stdout", new=buf):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertEqual(cm.exception.code, 1)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "FAIL")
        self.assertFalse(d["enforcement_ok"])
        # FAIL yolunda da advisory_contract JSON'da mevcut olmalı (kapı okuyabilmeli).
        self.assertIn("advisory_contract", d)
        self.assertIs(d["advisory_contract"]["ok"], True)  # offline kontrat bozulmamış

    def test_gh_json_unreadable_still_carries_advisory_contract(self):
        # UNREADABLE (403 yetki yok) yolunda script exit 1 eder ama JSON'da
        # advisory_contract.ok OFFLINE olarak hesaplanıp taşınmalı — CI'daki
        # precheck adımı GitHub'a erişemese de kontratı denetleyebilsin.
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh",
                               side_effect=RuntimeError(
                                   "HTTP 403: Resource not accessible by "
                                   "integration")), \
                mock.patch.object(sys, "stdout", new=buf):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertEqual(cm.exception.code, 1)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "UNREADABLE")
        ac = d.get("advisory_contract") or {}
        self.assertIs(ac.get("ok"), True, "offline kontrat UNREADABLE'da da okunabilmeli")

    def test_gh_json_not_set_up_exits_1(self):
        # Protection kurulu değilken (gh api 404) --gh exit 1 (fail-closed)
        # ve verdict NOT_SET_UP kalır.
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh",
                               side_effect=RuntimeError(
                                   "HTTP 404: Not Found — branch not protected")), \
                mock.patch.object(sys, "stdout", new=buf):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertEqual(cm.exception.code, 1)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "NOT_SET_UP")

    def test_gh_json_unreadable_not_set_up_same_verdict_exit(self):
        # 404 içermeyen hata (403 yetki yok / ağ) da fail-closed exit 1;
        # verdict UNREADABLE — "kurulu değil" ile karıştırılmaz.
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh",
                               side_effect=RuntimeError(
                                   "HTTP 403: Resource not accessible by "
                                   "integration")), \
                mock.patch.object(sys, "stdout", new=buf):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name", "--json"])
        self.assertEqual(cm.exception.code, 1)
        d = json.loads(buf.getvalue())
        self.assertEqual(d["verdict"], "UNREADABLE")
        self.assertNotEqual(d["verdict"], "NOT_SET_UP")

    def test_gh_text_not_set_up_exits_1(self):
        # Text modunda da protection kurulu değilken exit 1.
        buf = io.StringIO()
        with mock.patch.object(sc, "run_gh",
                               side_effect=RuntimeError(
                                   "HTTP 404: Not Found — branch not protected")), \
                mock.patch.object(sys, "stdout", new=buf), \
                mock.patch.object(sys, "stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                sc.main(["--gh", "--repo", "owner/name"])
        self.assertEqual(cm.exception.code, 1)



@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestScopedProtectionToken(unittest.TestCase):
    """Kapsamlı okuma token'ı — CI'da UNREADABLE'ı gerçek okumaya çevirir.

    Tarihsel kök-neden (2026-10-26): `GITHUB_TOKEN` branch protection
    okuyamaz (`administration` izni Actions `permissions:` bloğunda
    GEÇERSİZ — eklenirse workflow 0 job üretir). Bu yüzden `status_checks
    --gh` CI'da her koşumda UNREADABLE dönüyordu: pre-commit
    `check-status-check-names` yalnız yerelde (gh auth) doğrulayabiliyordu.

    Sözleşme:
      1) `PROTECTION_PAT` (tercih) / `GH_ADMIN_TOKEN` (yedek) okunur;
         boş/boşluklu değer token SAYILMAZ (kurulmamış secret boş string'dir).
      2) Token YALNIZ `gh api .../protection` çağrısına GH_TOKEN olarak
         geçer — repo çözümlemesi/alert gibi diğer çağrılar ambient kimlikle
         kalır (admin token'ı gereksiz yere geniş kullanılmaz).
      3) Token yokken davranış DEĞİŞMEZ (UNREADABLE + exit 1); token varken
         okuma reddedilirse UYARI bunu ayrıca söyler (bayat PAT "token yok"
         gibi okunmaz).
    """

    ENVS = ("PROTECTION_PAT", "GH_ADMIN_TOKEN")

    @contextlib.contextmanager
    def _only_env(self, **values):
        """Yalnız verilen token env'leri set olsun (diğerleri temizlenir)."""
        saved = {k: os.environ.get(k) for k in self.ENVS}
        for k in self.ENVS:
            os.environ.pop(k, None)
        os.environ.update({k: v for k, v in values.items() if v is not None})
        try:
            yield
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_prefers_protection_pat_and_ignores_blank_values(self):
        self.assertEqual(
            sc.protection_token({"PROTECTION_PAT": "pat-1",
                                 "GH_ADMIN_TOKEN": "admin-1"}), "pat-1")
        self.assertEqual(sc.protection_token({"GH_ADMIN_TOKEN": "admin-1"}),
                         "admin-1")
        for blank in ("", "   ", None):
            with self.subTest(blank=blank):
                self.assertIsNone(
                    sc.protection_token({"PROTECTION_PAT": blank,
                                         "GH_ADMIN_TOKEN": ""}))
        self.assertIsNone(sc.protection_token({}))

    def test_run_gh_injects_token_only_when_given(self):
        done = mock.Mock(returncode=0, stdout="{}\n", stderr="")
        with mock.patch.object(sc.subprocess, "run", return_value=done) as run:
            sc.run_gh(["gh", "api", "repos/o/r/branches/main/protection"],
                      token="pat-1")
            kwargs = run.call_args.kwargs
            self.assertEqual(kwargs["env"]["GH_TOKEN"], "pat-1")
            # Ambient ortam korunur (PATH vb.) — yalnız GH_TOKEN ezer.
            self.assertIn("PATH", kwargs["env"])
            run.reset_mock()
            sc.run_gh(["gh", "api", "user"])
            self.assertNotIn("env", run.call_args.kwargs,
                             "token verilmediğinde ambient kimlik korunmalı")

    def _run_main(self, argv):
        buf = io.StringIO()
        with mock.patch.object(sys, "stdout", new=buf):
            try:
                sc.main(argv)
            except SystemExit as exc:
                code = exc.code
            else:
                code = 0
        return code, buf.getvalue()

    def test_protection_read_uses_the_scoped_token(self):
        protection = _protection(contexts=list(sc.gate_jobs().values()))
        with self._only_env(PROTECTION_PAT="pat-1"), \
                mock.patch.object(sc, "run_gh",
                                  return_value=json.dumps(protection)) as run:
            code, out = self._run_main(
                ["--gh", "--repo", "owner/name", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["verdict"], "PASS")
        self.assertEqual(run.call_count, 1,
                         "--repo verildiğinde tek gh çağrısı beklenir")
        self.assertEqual(run.call_args.kwargs.get("token"), "pat-1")

    def test_without_token_the_call_is_unchanged(self):
        with self._only_env(), \
                mock.patch.object(sc, "run_gh",
                                  return_value=json.dumps(_protection())) as run:
            self._run_main(["--gh", "--repo", "owner/name", "--json"])
        self.assertIn(run.call_args.kwargs.get("token"), (None,),
                      "token yokken koruma okuması ambient kimlikle kalmalı")

    def test_rejected_scoped_token_is_called_out_in_the_warning(self):
        with self._only_env(PROTECTION_PAT="expired-pat"), \
                mock.patch.object(sc, "run_gh",
                                  side_effect=RuntimeError(
                                      "HTTP 403: Resource not accessible")):
            code, out = self._run_main(
                ["--gh", "--repo", "owner/name", "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["verdict"], "UNREADABLE")
        self.assertIn("scoped token denendi", payload["warning"],
                      "bayat/reddedilmiş PAT, 'token yok' gibi okunmamalı")

    def test_no_token_warning_stays_plain(self):
        with self._only_env(), \
                mock.patch.object(sc, "run_gh",
                                  side_effect=RuntimeError(
                                      "HTTP 403: Resource not accessible")):
            code, out = self._run_main(
                ["--gh", "--repo", "owner/name", "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["verdict"], "UNREADABLE")
        self.assertNotIn("scoped token denendi", payload["warning"])


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli")
class TestCiWiringOfTheScopedToken(unittest.TestCase):
    """verify.yml, kapsamlı token'ı `gh` çağrısını yapan adımlara verir.

    Token'ı yalnız kodda desteklemek yetmez: CI'da secret env'e girmezse
    `check-status-check-names` yine UNREADABLE döner. Bu yüzden iki adım da
    (precheck script'i + sidecar kanıtı) `secrets.PROTECTION_PAT` taşımalı.
    """

    @classmethod
    def setUpClass(cls):
        cls.text = _WORKFLOW.read_text(encoding="utf-8")

    def _step(self, name):
        blocks = self.text.split("\n      - name: ")
        for block in blocks:
            if block.startswith(name):
                return block
        self.fail(f"adım yok: {name}")

    def test_both_status_check_steps_get_the_scoped_secret(self):
        for name in ("Run status_checks --gh --json (sidecar kanıt)",
                     "Run AŞAMA 0 precheck (publish_precheck.sh)"):
            with self.subTest(step=name):
                block = self._step(name)
                self.assertIn("PROTECTION_PAT: ${{ secrets.PROTECTION_PAT }}",
                              block,
                              f"{name}: kapsamlı token CI'da env'e girmiyor "
                              "→ koruma yine UNREADABLE döner")

    def test_steps_keep_the_repo_token_for_other_gh_calls(self):
        # Ambient gh kimliği (repo çözümleme/alert) korunmalı: kapsamlı token
        # YALNIZ koruma okumasına geçer.
        block = self._step("Run status_checks --gh --json (sidecar kanıt)")
        self.assertIn("GH_TOKEN: ${{ github.token }}", block)

    def test_no_workflow_declares_the_invalid_administration_permission(self):
        wf_dir = _WORKFLOW.parent
        for path in sorted(wf_dir.glob("*.yml")):
            for line in path.read_text(encoding="utf-8").splitlines():
                self.assertFalse(
                    line.strip().startswith("administration:"),
                    f"{path.name}: `administration` Actions'ta GEÇERSİZ — "
                    "eklenirse workflow 0 job üretir (kapsamlı token kullanın)")

if __name__ == "__main__":
    unittest.main()
