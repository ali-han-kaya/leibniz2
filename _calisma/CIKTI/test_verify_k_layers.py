#!/usr/bin/env python3
"""Focused contracts for the extracted K0-K7 verifier seams."""
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import types
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery as vd  # noqa: E402


def _core_args(**over):
    """Çekirdek seçeneklerini taşıyan asgari args (reuse sözleşmesi).

    `build_layers_summary` isteğe bağlı katman getter'larını çağırır; bu yüzden
    namespace'te TÜM katman bayrakları (varsayılan False) bulunur. Bayrak
    eklenirse burası da güncellenmeli — testin patlaması bilinçli.
    """
    args = types.SimpleNamespace(
        check_references=False, strict_determinism=False,
        k0_toolkit_tolerant=False,
        symbolic_proof=False, lean_proof=False, verify_manifest=None,
        check_config_drift=False, check_plist=None,
        check_repro_manifest=False, check_cleanup=False, check_history=None,
        check_github_scripts=False, check_mirror=False, check_daemon=False,
        coq_proof=False, check_launchd=False, check_sde=False)
    for key, value in over.items():
        setattr(args, key, value)
    return args


# Şema-zorunlu asgari config (validate_config: required + pozitif değerler).
_CONFIG = {
    "budget_usd": 30.0, "budget_method": "both", "duration_pct_warn": 10.0,
    "budget_ratios": {"text": 8, "pdf": 9, "archive": 100, "binary": 100},
    "expected_pages": 33, "expected_refs": 61, "expected_manifest": 21,
}


class TestK0Seam(unittest.TestCase):
    def test_check_k0_returns_records_and_writes_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            canonical = pathlib.Path(tmp) / "CIKTI"
            canonical.mkdir()
            stale = pathlib.Path(tmp) / "stale.zip"
            stale.write_bytes(b"stale")
            sidecar = pathlib.Path(tmp) / "k0.json"
            findings = []

            records = vd.check_k0(
                str(canonical),
                types.SimpleNamespace(
                    k0_toolkit_tolerant=False,
                    k0_out=str(sidecar),
                    json=True,
                ),
                lambda *finding: findings.append(finding),
            )

            self.assertEqual([record["rel"] for record in records], ["stale.zip"])
            self.assertEqual(findings[0][0:2], ("P1", "K0-STALE"))
            self.assertEqual(json.loads(sidecar.read_text())["count"], 1)


class TestLayerTimingTable(unittest.TestCase):
    """Ağır katman (K6/K8/K9) süre ölçümü ve tablo sözleşmesi."""

    def test_timing_add_uses_explicit_now(self):
        timings = {}
        vd._timing_add(timings, "K6", "referans denetimi", 10.0, now=12.5)
        self.assertEqual(
            timings["K6"],
            [{"phase": "referans denetimi", "seconds": 2.5}])

    def test_timing_add_clamps_negative_delta(self):
        """Saat geriye dönerse negatif süre tabloya sızmaz."""
        timings = {}
        vd._timing_add(timings, "K8", "Z3", 10.0, now=9.0)
        self.assertEqual(timings["K8"][0]["seconds"], 0.0)

    def test_build_layer_timings_orders_by_layer_and_sums_phases(self):
        timings = {}
        vd._timing_add(timings, "K9", "lake build", 0.0, now=40.0)
        vd._timing_add(timings, "K9", "statement gate", 0.0, now=0.5)
        vd._timing_add(timings, "K6", "referans denetimi", 0.0, now=11.25)

        rows = vd.build_layer_timings(timings)

        self.assertEqual([r["layer"] for r in rows], ["K6", "K9"])
        self.assertEqual(rows[0]["seconds"], 11.25)
        self.assertEqual(rows[1]["seconds"], 40.5)
        self.assertEqual(rows[1]["label"], vd.LAYER_LABELS["K9"])

    def test_total_phase_wins_and_is_not_a_detail_row(self):
        """K9 toplamı alt fazların toplamı değil, gerçek duvar saatidir."""
        # Faz adı SABİT yazılır (vd._TIMING_TOTAL_PHASE değil): sabiti
        # değiştiren bir mutasyon testi kırmızıya çevirmeli.
        self.assertEqual(vd._TIMING_TOTAL_PHASE, "toplam")
        timings = {}
        vd._timing_add(timings, "K9", "Lean ispatı", 0.0, now=2.0)
        vd._timing_add(timings, "K9", "toplam", 0.0, now=3.0)

        rows = vd.build_layer_timings(timings)

        self.assertEqual(rows[0]["seconds"], 3.0)
        self.assertEqual([p["phase"] for p in rows[0]["phases"]],
                         ["Lean ispatı"])

    def test_skipped_layers_have_no_row(self):
        """Yalnız koşan katman satır alır; atlanan katman tabloda görünmez."""
        self.assertEqual(vd.build_layer_timings({}), [])
        rows = vd.build_layer_timings(
            {"K8": [{"phase": "Z3", "seconds": 1.0}]})
        self.assertEqual([r["layer"] for r in rows], ["K8"])

    def test_format_table_names_layer_and_phases(self):
        rows = vd.build_layer_timings(
            {"K8": [{"phase": "Z3", "seconds": 2.5}]})

        lines = vd.format_layer_timing_table(rows)

        self.assertEqual(lines[0], "Ağır katman süreleri (duvar saati):")
        self.assertTrue(lines[1].startswith("  K8 "))
        self.assertIn("2.50s", lines[1])
        self.assertIn("Z3 2.50s", lines[1])

    def test_empty_table_renders_nothing(self):
        self.assertEqual(vd.format_layer_timing_table([]), [])


class TestCoreVerdictReuse(unittest.TestCase):
    """--core-verdict-out / --reuse-core-verdict sözleşmesi.

    Katman-özel çağrılar (K10/K12/K13/K15/K17/K21) aynı ağaç için K0-K7'yi
    TEKRAR koşmaz; ama reuse bir kısayol değil, doğrulanmış bir kaydın
    replay'idir: kimlik (ağaç/ortam/kod/seçenek) tutmazsa çekirdek koşar ve
    FAIL hiçbir koşulda PASS'a dönüşmez.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="core_verdict_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        root = os.path.join(self.tmp, "wt")   # --dir'in ÜSTÜ taranır (K0)
        self.d = os.path.join(root, "delivery")
        os.makedirs(self.d)
        self.zip = os.path.join(self.d, vd.KLASOR_ZIP)
        with open(self.zip, "wb") as fh:
            fh.write(b"PK\x03\x04 sentetik dis zip")
        with open(self.zip + ".sha256", "w", encoding="utf-8") as fh:
            fh.write("%s  %s\n" % (vd.sha256_file(self.zip), vd.KLASOR_ZIP))
        self.cfg = os.path.join(root, "cfg.json")
        with open(self.cfg, "w", encoding="utf-8") as fh:
            json.dump(_CONFIG, fh)
        self.args = _core_args()

    # ---- yardımcılar -------------------------------------------------
    def _state(self, **over):
        state = {"pages": 33, "refs": 61, "pdf_meta_report": None,
                 "total_bytes": 4096,
                 "type_bytes": {k: 1024 for k in vd.DEFAULT_BUDGET_RATIOS},
                 "skill_reuse": {"ok": True, "detail": "sentetik"},
                 "online_refs": [], "layer_timings": {}}
        state.update(over)
        return state

    def _write_record(self, findings=(), state=None, name="rec.json"):
        rec = vd.core_verdict_record(self.args, self.d, self.cfg,
                                     state or self._state(), list(findings))
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        return path, rec

    def _load(self, path, args=None):
        return vd.load_core_verdict(path, args or self.args, self.d, self.cfg)

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    # ---- kimlik bağı ------------------------------------------------
    def test_valid_record_loads(self):
        path, rec = self._write_record()
        loaded, reason = self._load(path)
        self.assertIsNotNone(loaded, reason)
        self.assertEqual(reason, "ok")
        self.assertEqual(loaded["tree_digest"], rec["tree_digest"])
        self.assertEqual(loaded["verdict"], "PASS")

    def test_tree_change_invalidates_record(self):
        path, _ = self._write_record()
        with open(self.zip, "ab") as fh:
            fh.write(b"!")
        loaded, reason = self._load(path)
        self.assertIsNone(loaded)
        self.assertIn("ağaç", reason)

    def test_stray_zip_invalidates_record(self):
        """K0'ın gördüğü başıboş zip kümesi de çekirdek girdisidir."""
        path, _ = self._write_record()
        with open(os.path.join(os.path.dirname(self.d), "stale.zip"),
                  "wb") as fh:
            fh.write(b"stale")
        loaded, reason = self._load(path)
        self.assertIsNone(loaded)
        self.assertIn("ağaç", reason)

    def test_sidecar_change_invalidates_record(self):
        path, _ = self._write_record()
        with open(self.zip + ".sha256", "w", encoding="utf-8") as fh:
            fh.write("deadbeef  %s\n" % vd.KLASOR_ZIP)
        loaded, reason = self._load(path)
        self.assertIsNone(loaded)
        self.assertIn("ağaç", reason)

    # ---- reddetme gerekçeleri (sessiz yutma yok) --------------------
    def test_other_tree_is_rejected(self):
        path, _ = self._write_record()
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        rec = self._read(path)
        rec["dir"] = other
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        loaded, reason = self._load(path)
        self.assertIsNone(loaded)
        self.assertIn("farklı ağaç", reason)

    def test_tampered_tool_fingerprint_is_rejected(self):
        path, _ = self._write_record()
        rec = self._read(path)
        rec["tool_sha256"] = "0" * 64
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        loaded, reason = self._load(path)
        self.assertIsNone(loaded)
        self.assertIn("değişmiş", reason)

    def test_env_change_is_rejected(self):
        path, _ = self._write_record()
        rec = self._read(path)
        rec["env"]["python"] = "0.0.0"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        loaded, reason = self._load(path)
        self.assertIsNone(loaded)
        self.assertIn("ortam", reason)

    def test_option_gap_is_rejected_with_flag_name(self):
        """Kayıt non-strict koştuysa strict isteyen çağrı onu kullanamaz."""
        path, _ = self._write_record()
        strict = _core_args(strict_determinism=True)
        loaded, reason = self._load(path, strict)
        self.assertIsNone(loaded)
        self.assertIn("--strict-determinism", reason)

    def test_superset_options_are_accepted(self):
        """Strict koşan kayıt, strict istemeyen çağrıyı da kapsar."""
        strict = _core_args(check_references=True, strict_determinism=True)
        rec = vd.core_verdict_record(strict, self.d, self.cfg,
                                     self._state(), [])
        path = os.path.join(self.tmp, "strict.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        loaded, reason = self._load(path)
        self.assertIsNotNone(loaded, reason)

    def test_missing_malformed_and_foreign_schema(self):
        missing, reason = self._load(os.path.join(self.tmp, "yok.json"))
        self.assertIsNone(missing)
        self.assertIn("yok", reason)

        bad = os.path.join(self.tmp, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        malformed, reason = self._load(bad)
        self.assertIsNone(malformed)
        self.assertIn("JSON", reason)

        foreign = os.path.join(self.tmp, "foreign.json")
        with open(foreign, "w", encoding="utf-8") as fh:
            json.dump({"schema": "core-verdict/0"}, fh)
        other, reason = self._load(foreign)
        self.assertIsNone(other)
        self.assertIn("şema", reason)

    # ---- kod parmak izi --------------------------------------------
    def test_fingerprint_covers_every_core_code_file(self):
        """id_canonical.py değişirse parmak izi DEĞİŞMELİ (tek dosya yetmez)."""
        sandbox = os.path.join(self.tmp, "code")
        os.makedirs(sandbox)
        for name in vd.CORE_CODE_FILES:
            with open(os.path.join(sandbox, name), "wb") as fh:
                fh.write(b"v1")
        original = vd.__file__
        vd.__file__ = os.path.join(sandbox, "verify_delivery.py")
        self.addCleanup(setattr, vd, "__file__", original)
        first = vd.core_tool_sha256()
        self.assertTrue(first)

        with open(os.path.join(sandbox, "id_canonical.py"), "wb") as fh:
            fh.write(b"v2")
        self.assertNotEqual(vd.core_tool_sha256(), first,
                            "id_canonical.py değişimi parmak izini "
                            "değiştirmeli")

    # ---- reuse FAIL'i PASS'a çeviremez ----------------------------
    def test_reused_fail_verdict_stays_fail(self):
        findings = [
            {"id": "K1-SIDECAR", "priority": "P0", "check": "K1 dış zip",
             "issue": "dış zip hash uyuşmuyor", "evidence": "e"},
            {"id": "K6-REFS", "priority": "P1", "check": "K6 refs",
             "issue": "unverified=2", "evidence": ""},
            {"id": "K7-HIYJEN", "priority": "INFO", "check": "K7",
             "issue": "advisory", "evidence": ""},
        ]
        path, rec = self._write_record(findings=findings)
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertEqual(rec["counts"], {"P0": 1, "P1": 1})

        loaded, reason = self._load(path)
        self.assertIsNotNone(loaded, reason)
        replayed = []

        def add(pri, cid, check, issue, evidence=""):
            replayed.append({"id": cid, "priority": pri, "check": check,
                             "issue": issue, "evidence": evidence})

        state = vd.core_state_from_verdict(loaded, add)
        self.assertEqual(state["pages"], 33)
        self.assertEqual([f["id"] for f in replayed],
                         ["K1-SIDECAR", "K6-REFS", "K7-HIYJEN"])

        layers = vd.build_layers_summary(self.args, replayed,
                                         core_source="reused",
                                         core_verdict_path=path)
        self.assertEqual(layers["K1"]["status"], "FAIL")
        self.assertEqual(layers["K6"]["status"], "FAIL")
        for layer in ("K0", "K2", "K3", "K4", "K5", "K7"):
            self.assertEqual(layers[layer]["status"], "PASS")
            self.assertEqual(layers[layer]["source"], "reused")
            self.assertEqual(layers[layer]["core_verdict"], path)

    def test_record_keeps_only_core_findings(self):
        findings = [
            {"id": "K2-FOLDER", "priority": "P0", "check": "K2",
             "issue": "x", "evidence": ""},
            {"id": "K13-SCENARIO", "priority": "P0", "check": "K13",
             "issue": "y", "evidence": ""},
            {"id": "CORE-VERDICT", "priority": "INFO", "check": "c",
             "issue": "z", "evidence": ""},
        ]
        _, rec = self._write_record(findings=findings)
        self.assertEqual([f["id"] for f in rec["findings"]], ["K2-FOLDER"])

    # ---- main(): çekirdek gerçekten koşmuyor -----------------------
    def _run_main(self, argv):
        import contextlib
        import io
        import unittest.mock as mock
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["verify_delivery.py"] + argv):
            with contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(err):
                rc = vd.main()
        return rc, out.getvalue(), err.getvalue()

    def _no_core(self):
        """Çekirdek çağrılırsa patlayan casuslar (reuse kanıtı)."""
        def boom(*_a, **_k):
            raise AssertionError("reuse edilmesine rağmen çekirdek koştu")
        return boom

    def test_main_reuses_core_and_skips_it(self):
        """PASS kaydı ile main(): K0-K7 casusları HİÇ çağrılmaz, rapor dürüst."""
        import unittest.mock as mock
        path, _ = self._write_record()
        with mock.patch.object(vd, "run_core_k0_k1", self._no_core()), \
                mock.patch.object(vd, "run_core_k2_k7", self._no_core()):
            rc, out, _err = self._run_main(
                ["--dir", self.d, "--config", self.cfg, "--json",
                 "--reuse-core-verdict", path])
        self.assertEqual(rc, 0)
        report = json.loads(out)
        self.assertEqual(report["core_verdict"]["source"], "reused")
        self.assertEqual(report["core_verdict"]["tree_digest"],
                         self._read(path)["tree_digest"])
        self.assertIn("K5", report["layers"])
        self.assertEqual(report["layers"]["K5"]["source"], "reused")
        self.assertEqual(report["layers"]["K5"]["status"], "PASS")

    def test_main_replay_of_fail_keeps_exit_1(self):
        import unittest.mock as mock
        path, _ = self._write_record(findings=[
            {"id": "K4-SCRIPT", "priority": "P0", "check": "K4 script",
             "issue": "byte uyuşmazlığı", "evidence": ""}])
        with mock.patch.object(vd, "run_core_k0_k1", self._no_core()), \
                mock.patch.object(vd, "run_core_k2_k7", self._no_core()):
            rc, out, _err = self._run_main(
                ["--dir", self.d, "--config", self.cfg, "--json",
                 "--reuse-core-verdict", path])
        self.assertEqual(rc, 1)
        report = json.loads(out)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["layers"]["K4"]["status"], "FAIL")

    def test_main_rejected_record_reruns_core_and_says_why(self):
        """Doğrulanamayan kayıt: çekirdek KOŞAR, gerekçe kayda geçer."""
        import unittest.mock as mock
        path, _ = self._write_record()
        calls = []

        def fake_k0(args, d, kzip, kside, add):
            calls.append("k0")

        def fake_k27(args, d, kzip, kside, add):
            calls.append("k2_k7")
            return self._state()

        with open(self.zip, "ab") as fh:      # ağacı kayıttan sonra boz
            fh.write(b"!")
        with mock.patch.object(vd, "run_core_k0_k1", fake_k0), \
                mock.patch.object(vd, "run_core_k2_k7", fake_k27):
            rc, out, err = self._run_main(
                ["--dir", self.d, "--config", self.cfg, "--json",
                 "--reuse-core-verdict", path])
        self.assertEqual(calls, ["k0", "k2_k7"])
        self.assertIn("ağaç", err)
        report = json.loads(out)
        self.assertEqual(report["core_verdict"]["source"], "ran")
        self.assertIn("ağaç", report["core_verdict"]["rejected_reason"])
        self.assertEqual(report["verdict"], "PASS")   # sahte çekirdek temiz
        self.assertEqual(rc, 0)

    def test_bare_core_verdict_out_writes_resolved_path(self):
        """`--core-verdict-out` (yolsuz) → $VERIFY_CORE_VERDICT yoluna yazar."""
        import unittest.mock as mock
        target = os.path.join(self.tmp, "cached", "verdict.json")
        os.makedirs(os.path.dirname(target))

        def fake_k27(args, d, kzip, kside, add):
            return self._state()

        with mock.patch.dict(os.environ, {vd.CORE_VERDICT_ENV: target}), \
                mock.patch.object(vd, "run_core_k0_k1", lambda *a: None), \
                mock.patch.object(vd, "run_core_k2_k7", fake_k27):
            rc, _out, err = self._run_main(
                ["--dir", self.d, "--config", self.cfg, "--core-verdict-out"])
            self.assertEqual(rc, 0, err)
            self.assertTrue(os.path.isfile(target), err)
            written = self._read(target)
            self.assertEqual(written["schema"], vd.CORE_VERDICT_SCHEMA)
            self.assertEqual(written["verdict"], "PASS")

            # İkinci çağrı: aynı ağaç → çekirdek koşmadan aynı kaydı okur.
            with mock.patch.object(vd, "run_core_k0_k1", self._no_core()), \
                    mock.patch.object(vd, "run_core_k2_k7", self._no_core()):
                rc2, out2, err2 = self._run_main(
                    ["--dir", self.d, "--config", self.cfg, "--json",
                     "--reuse-core-verdict"])
        self.assertEqual(rc2, 0, err2)
        self.assertEqual(json.loads(out2)["core_verdict"]["source"],
                         "reused")

    def test_reuse_refuses_outputs_it_cannot_produce(self):
        path, _ = self._write_record()
        k0 = os.path.join(self.tmp, "k0.json")
        rc, _out, err = self._run_main(
            ["--dir", self.d, "--config", self.cfg,
             "--reuse-core-verdict", path, "--k0-out", k0])
        self.assertEqual(rc, 2)
        self.assertIn("--k0-out", err)
        self.assertFalse(os.path.exists(k0))

        out_path = os.path.join(self.tmp, "new.json")
        rc, _out, err = self._run_main(
            ["--dir", self.d, "--config", self.cfg,
             "--reuse-core-verdict", path, "--core-verdict-out", out_path])
        self.assertEqual(rc, 2)
        self.assertIn("--core-verdict-out", err)
        self.assertFalse(os.path.exists(out_path))

    def test_reuse_budget_survives_truncated_type_bytes(self):
        """Kırpılmış type_bytes KeyError çökertmez (bütçe 0 bayt sayar)."""
        path, _ = self._write_record(state=self._state(type_bytes={}))
        rc, out, err = self._run_main(
            ["--dir", self.d, "--config", self.cfg, "--json",
             "--reuse-core-verdict", path])
        self.assertEqual(rc, 0, err)
        self.assertIsNotNone(json.loads(out)["budget"])


class TestRunScopedHashCache(unittest.TestCase):
    """sha256_file: aynı süreçte aynı dosya bir kez okunur.

    Önbellek dosya KİMLİĞİNE bağlıdır (dev/ino/boyut/mtime/ctime), yola
    değil: içerik değişirse veya dosya yeni bir inode'la değiştirilirse
    hash yeniden hesaplanır — bayat bir digest döndürme yolu yok.
    """

    def setUp(self):
        vd.reset_hash_cache()
        self.addCleanup(vd.reset_hash_cache)
        self.tmp = tempfile.mkdtemp(prefix="hashcache_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "a.bin")
        self.blob = b"x" * 4096
        with open(self.path, "wb") as fh:
            fh.write(self.blob)

    def test_repeat_call_reads_the_file_once(self):
        first = vd.sha256_file(self.path)
        second = vd.sha256_file(self.path)
        self.assertEqual(first, second)
        self.assertEqual(first, hashlib.sha256(self.blob).hexdigest())
        stats = vd.hash_cache_stats()
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["bytes_read"], len(self.blob))

    def test_different_paths_same_inode_share_entry(self):
        """Hardlink/rename: aynı inode → tek okuma, aynı digest."""
        alias = os.path.join(self.tmp, "b.bin")
        os.link(self.path, alias)
        self.assertEqual(vd.sha256_file(self.path), vd.sha256_file(alias))
        self.assertEqual(vd.hash_cache_stats()["misses"], 1)

    def test_same_content_different_inode_is_rehashed(self):
        """Kimlik anahtarı yol değil: kopya dosya ayrı girdi (aynı digest)."""
        copy = os.path.join(self.tmp, "copy.bin")
        with open(copy, "wb") as fh:
            fh.write(self.blob)
        self.assertEqual(vd.sha256_file(self.path), vd.sha256_file(copy))
        self.assertEqual(vd.hash_cache_stats()["misses"], 2)
        self.assertEqual(vd.hash_cache_stats()["bytes_read"], 2 * len(self.blob))

    def test_size_change_invalidates_entry(self):
        self.assertEqual(vd.sha256_file(self.path),
                         hashlib.sha256(self.blob).hexdigest())
        with open(self.path, "ab") as fh:
            fh.write(b"y")
        self.assertEqual(vd.sha256_file(self.path),
                         hashlib.sha256(self.blob + b"y").hexdigest())
        self.assertEqual(vd.hash_cache_stats()["misses"], 2)

    def test_replace_with_new_inode_invalidates_entry(self):
        vd.sha256_file(self.path)
        tmp = os.path.join(self.tmp, "new.bin")
        with open(tmp, "wb") as fh:
            fh.write(b"z" * 4096)      # AYNI boyut, farklı içerik + inode
        os.replace(tmp, self.path)
        self.assertEqual(vd.sha256_file(self.path),
                         hashlib.sha256(b"z" * 4096).hexdigest())
        self.assertEqual(vd.hash_cache_stats()["misses"], 2)

    def test_identity_is_the_cache_key(self):
        """Anahtar = (dev, ino, boyut, mtime_ns, ctime_ns); yol parçası değil."""
        ident = vd._file_identity(self.path)
        self.assertEqual(ident[2], len(self.blob))
        vd.sha256_file(self.path)
        self.assertIn(ident, vd._HASH_CACHE)

    def test_missing_file_raises_as_before(self):
        with self.assertRaises(FileNotFoundError):
            vd.sha256_file(os.path.join(self.tmp, "yok.bin"))

    def test_reset_clears_stats_and_entries(self):
        vd.sha256_file(self.path)
        vd.sha256_file(self.path)
        vd.reset_hash_cache()
        self.assertEqual(vd.hash_cache_stats(),
                         {"hits": 0, "misses": 0, "bytes_read": 0,
                          "entries": 0})


if __name__ == "__main__":
    unittest.main()
