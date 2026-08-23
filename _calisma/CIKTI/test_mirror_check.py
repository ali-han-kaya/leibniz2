#!/usr/bin/env python3
"""K17 (verify mirror sync) kapısının birim testleri.

İki kapı birlikte test edilir — her ikisi de fake MIRROR_DIR/LEAN_MIRROR_DIR
altında koşar (gerçek ~/Library/Caches/com.freebuff'a DOKUNMAZ, bu yüzden
Linux CI'da da çalışır):

  1) sync_verify_mirror.sh --check (K17 kapısının sözleşmesi):
       0 = GÜNCEL  (repo ↔ mirror birebir)
       1 = BAYAT   (en az bir dosya farklı/eksik)
       2 = hata    (kaynak dosyalardan biri yok / kullanım hatası)

  2) verify_delivery.py --check-mirror (K17 katmanı):
       exit 0 + GÜNCEL → PASS; BAYAT/hata → P1 bulgu (fail-closed);
       --mirror-out ham çıktı + K17 raporunu tek sidecar JSON'a yazar.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SYNC_MIRROR = os.path.join(HERE, "sync_verify_mirror.sh")
VERIFY_DELIVERY = os.path.join(HERE, "verify_delivery.py")


def run(env_extra, *args):
    """Belirtilen env override'larıyla komutu koş; CompletedProcess döner."""
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(list(args), env=env, capture_output=True,
                          text=True, timeout=300)


def make_mirror(work):
    """Fake mirror dizinleri kurar; (mirror_dir, lean_mirror_dir) döner."""
    mirror_dir = os.path.join(work, "verify-mirror")
    lean_mirror_dir = os.path.join(work, "lean-mirror")
    return mirror_dir, lean_mirror_dir


def sync_env(work):
    """sync_verify_mirror.sh'i fake mirror'a yönlendiren env sözlüğü.

    PREVIEW_MIRROR da fake'e yönlendirilir — aksi halde senkron gerçek
    ~/Library/Caches/com.freebuff/preview'a dokunur (adım 2+4 tek komutta).
    """
    mirror_dir, lean_mirror_dir = make_mirror(work)
    preview_mirror = os.path.join(work, "preview-mirror")
    return {"PREVIEW_MIRROR": preview_mirror,
            "MIRROR_DIR": mirror_dir,
            "LEAN_MIRROR_DIR": lean_mirror_dir}


class TestSyncMirrorCheckExitCodes(unittest.TestCase):
    """sync_verify_mirror.sh --check → 0=GÜNCEL / 1=BAYAT / 2=hata."""

    def test_exit_0_guncel(self):
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            # Senkron et → mirror repo ile birebir olur.
            syn = run(env, "bash", SYNC_MIRROR)
            self.assertEqual(syn.returncode, 0, syn.stderr)
            chk = run(env, "bash", SYNC_MIRROR, "--check")
            self.assertEqual(chk.returncode, 0, chk.stdout + chk.stderr)
            self.assertIn("SONUÇ: mirror güncel", chk.stdout)

    def test_exit_1_bayat(self):
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            syn = run(env, "bash", SYNC_MIRROR)
            self.assertEqual(syn.returncode, 0, syn.stderr)
            # Mirror'daki bir dosyayı boz (içerik repo'dan farklı olsun).
            mirror_dir, _ = make_mirror(work)
            target = os.path.join(mirror_dir, "verify_delivery.py")
            self.assertTrue(os.path.isfile(target), target)
            with open(target, "a", encoding="utf-8") as f:
                f.write("\n# mirror drift\n")
            chk = run(env, "bash", SYNC_MIRROR, "--check")
            self.assertEqual(chk.returncode, 1, chk.stdout + chk.stderr)
            self.assertIn("BAYAT", chk.stdout)

    def test_exit_2_kaynak_yok(self):
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            # ROOT'u boş bir dizine çevir → CIKTI kaynak dosyaları yok.
            empty = os.path.join(work, "empty-root")
            os.makedirs(empty)
            env = dict(os.environ)
            env["ROOT"] = empty
            chk = run(env, "bash", SYNC_MIRROR, "--check")
            self.assertEqual(chk.returncode, 2, chk.stdout + chk.stderr)
            self.assertIn("HATA", chk.stderr)

    def test_exit_2_bilinmeyen_mod(self):
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            chk = run(sync_env(work), "bash", SYNC_MIRROR, "--nope")
            self.assertEqual(chk.returncode, 2, chk.stdout + chk.stderr)
            self.assertIn("bilinmeyen mod", chk.stderr)


class TestVerifyDeliveryK17(unittest.TestCase):
    """verify_delivery.py --check-mirror → K17 P1 (fail-closed) + sidecar."""

    def test_k17_guncel_pass(self):
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            syn = run(env, "bash", SYNC_MIRROR)
            self.assertEqual(syn.returncode, 0, syn.stderr)
            out = os.path.join(work, "mirror_report.json")
            r = run(env, sys.executable, VERIFY_DELIVERY, "--check-mirror",
                    "--mirror-out", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("[K17] mirror sync: PASS", r.stdout)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            self.assertEqual(d["layer"], "K17")
            self.assertTrue(d["ok"])
            self.assertEqual(d["exit"], 0)

    def test_k17_bayat_p1_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            syn = run(env, "bash", SYNC_MIRROR)
            self.assertEqual(syn.returncode, 0, syn.stderr)
            mirror_dir, _ = make_mirror(work)
            target = os.path.join(mirror_dir, "verify_delivery.py")
            with open(target, "a", encoding="utf-8") as f:
                f.write("\n# mirror drift\n")
            out = os.path.join(work, "mirror_report.json")
            r = run(env, sys.executable, VERIFY_DELIVERY, "--check-mirror",
                    "--mirror-out", out)
            # P1 bulgu → genel exit 1 (fail-closed).
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("[P1] K17 mirror sync", r.stdout)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            self.assertFalse(d["ok"])
            self.assertEqual(d["exit"], 1)
            self.assertIn("BAYAT", d["detail"])

    def test_k17_kaynak_yok_p1(self):
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            empty = os.path.join(work, "empty-root")
            os.makedirs(empty)
            env = dict(os.environ)
            env["ROOT"] = empty
            r = run(env, sys.executable, VERIFY_DELIVERY, "--check-mirror")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("[P1] K17 mirror sync", r.stdout)

    def test_k17_script_yok_p1(self):
        # check_mirror_sync, script yolunu __file__'a göre sabit hesaplar;
        # os.path.isfile'i patch'leyerek script-yok dalını uyarırız.
        sys.path.insert(0, HERE)
        import verify_delivery as vd  # noqa: E402
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            script = os.path.join(HERE, "sync_verify_mirror.sh")

            def fake_isfile(p):
                if p == script:
                    return False
                return os.path.isfile(p)

            with mock.patch.object(vd.os.path, "isfile", side_effect=fake_isfile):
                findings = []
                add = lambda prio, cid, label, issue, evidence="": findings.append(
                    {"priority": prio, "check": cid, "issue": issue,
                     "evidence": evidence})
                ok, detail, rc, txt, meta = vd.check_mirror_sync(add)
            self.assertFalse(ok)
            self.assertEqual(rc, None)
            self.assertIn("sync_verify_mirror.sh yok", detail)
            self.assertFalse(meta["auto_synced"])
            self.assertTrue(any(f["check"] == "K17-MIRROR" for f in findings))


class TestMirrorFileCoverage(unittest.TestCase):
    """Mirror FILES listesi repo'daki tüm runtime dosyalarını kapsar.

    Regresyon: launchd rotasında K16 battery github_scripts/*.js'i mirror'dan
    koşar; eksik bir script (ör. label_gate_p1.js) K16'yı P0/FAIL'e düşürürdü
    (gerçek bir canlı hataydı). Bu test, repo'daki her github_script'in mirror
    FILES listesinde olduğunu fail-closed doğrular.
    """

    def test_all_github_scripts_in_mirror_files(self):
        with open(SYNC_MIRROR, encoding="utf-8") as f:
            text = f.read()
        # FILES listesindeki github_scripts girdileri (kaynak|dest formatı).
        listed = set(re.findall(r"github_scripts/[a-z0-9_]+\.js", text))
        # Repo'daki gerçek script dosyaları.
        scripts_dir = os.path.join(HERE, "github_scripts")
        repo_scripts = {f"github_scripts/{n}" for n in os.listdir(scripts_dir)
                        if n.endswith(".js")}
        missing = repo_scripts - listed
        self.assertEqual(missing, set(),
                         f"mirror FILES listesinde eksik script'ler: {missing}")

    def test_lean_mirror_files_listed(self):
        with open(SYNC_MIRROR, encoding="utf-8") as f:
            text = f.read()
        # LEAN_FILES ReductInvariance.lean'ı içermeli (K9 launchd rotası).
        self.assertIn("ReductInvariance.lean", text)

    def test_preview_files_listed(self):
        with open(SYNC_MIRROR, encoding="utf-8") as f:
            text = f.read()
        # PREVIEW_FILES (adım 2) preview_server.py + _daemonize.py içermeli
        # — adım 2+4 tek komutta senkron edilir (launchd çalıştırıcısı).
        self.assertIn("preview_server.py|preview_server.py", text)
        self.assertIn("_daemonize.py|_daemonize.py", text)

    def test_guide_files_listed_and_synced(self):
        # GUIDE_FILES (adım 2) branch protection kılavuzunu preview mirror'a
        # taşır — sunucu /guide.html rotasında oradan servis eder.
        with open(SYNC_MIRROR, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("docs/branch-protection-guide/guide.html|guide.html",
                      text)
        with tempfile.TemporaryDirectory(prefix="mirror-guide-") as work:
            env = sync_env(work)
            syn = run(env, "bash", SYNC_MIRROR)
            self.assertEqual(syn.returncode, 0, syn.stderr)
            guide = os.path.join(env["PREVIEW_MIRROR"], "guide.html")
            self.assertTrue(os.path.isfile(guide), guide)
            # Drift: kaynak değişirse --check BAYAT döner (K17 fail-closed).
            src = os.path.join(HERE, "..", "..",
                               "docs", "branch-protection-guide",
                               "guide.html")
            self.assertTrue(os.path.isfile(src), src)

    def test_preview_mirror_synced_in_single_command(self):
        # Adım 2+4 tek komut: sync, preview mirror'ı da kurar; --check onu
        # da denetler. PREVIEW_MIRROR fake'e yönlendirilir (gerçek cache'e
        # dokunmaz).
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            syn = run(env, "bash", SYNC_MIRROR)
            self.assertEqual(syn.returncode, 0, syn.stderr)
            preview_server = os.path.join(env["PREVIEW_MIRROR"],
                                          "preview_server.py")
            self.assertTrue(os.path.isfile(preview_server), preview_server)
            self.assertTrue(os.path.isfile(
                os.path.join(env["PREVIEW_MIRROR"], "_daemonize.py")))
            # --check: preview dosyası bozulursa BAYAT (exit 1) → K17 fail.
            with open(preview_server, "a", encoding="utf-8") as f:
                f.write("\n# drift\n")
            chk = run(env, "bash", SYNC_MIRROR, "--check")
            self.assertEqual(chk.returncode, 1, chk.stdout + chk.stderr)
            self.assertIn("BAYAT/EKSİK: preview/preview_server.py", chk.stdout)


class TestMirrorAutoSync(unittest.TestCase):
    """--mirror-auto-sync: BAYAT → otomatik sync + sidecar'da iz."""

    def test_auto_sync_fixes_bayat_and_marks_sidecar(self):
        """Uçtan uca: drift → --check-mirror --mirror-auto-sync → GÜNCEL,
        sidecar auto_synced=True + before/after exit izi."""
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            syn = run(env, "bash", SYNC_MIRROR)
            self.assertEqual(syn.returncode, 0, syn.stderr)
            mirror_dir, _ = make_mirror(work)
            target = os.path.join(mirror_dir, "verify_delivery.py")
            with open(target, "a", encoding="utf-8") as f:
                f.write("\n# mirror drift\n")
            out = os.path.join(work, "mirror_report.json")
            r = run(env, sys.executable, VERIFY_DELIVERY, "--check-mirror",
                    "--mirror-auto-sync", "--mirror-out", out)
            # Otomatik sync drift'i giderdi → exit 0 (P1 yok).
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("[K17] mirror sync: PASS", r.stdout)
            self.assertIn("AUTO-SYNC", r.stdout)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            self.assertTrue(d["ok"])
            self.assertEqual(d["exit"], 0)
            self.assertTrue(d["auto_synced"])
            self.assertEqual(d["before_exit"], 1)
            self.assertEqual(d["after_exit"], 0)
            self.assertEqual(d["sync_rc"], 0)

    def test_auto_sync_sync_failure_p1(self):
        """Otomatik sync BAŞARISIZ (exit≠0) → P1 fail-closed + iz."""
        sys.path.insert(0, HERE)
        import verify_delivery as vd  # noqa: E402

        # --check → 1 (BAYAT), sync → 2 (hata), ikinci --check yok.
        class R:
            def __init__(self, rc, out):
                self.returncode = rc
                self.stdout = out
                self.stderr = ""

        seq = [R(1, "BAYAT: x"), R(2, "sync hata")]
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return seq.pop(0)

        findings = []
        add = lambda prio, cid, label, issue, evidence="": findings.append(
            {"priority": prio, "check": cid, "issue": issue,
             "evidence": evidence})
        with mock.patch.object(vd.subprocess, "run", side_effect=fake_run):
            ok, detail, rc, txt, meta = vd.check_mirror_sync(add, auto_sync=True)
        self.assertFalse(ok)
        self.assertIn("otomatik sync BAŞARISIZ", detail)
        self.assertTrue(meta["auto_synced"])
        self.assertEqual(meta["before_exit"], 1)
        self.assertEqual(meta["sync_rc"], 2)
        self.assertEqual(meta["after_exit"], None)
        self.assertTrue(any("otomatik sync başarısız" in f["issue"]
                            for f in findings))
        # Sıra: --check, sync (ikinci --check yok).
        self.assertTrue("--check" in calls[0])
        self.assertNotIn("--check", calls[1])

    def test_auto_sync_still_bayat_after_sync_p1(self):
        """Sync başarılı ama yeniden --check hâlâ BAYAT → P1 + after_exit=1."""
        sys.path.insert(0, HERE)
        import verify_delivery as vd  # noqa: E402

        class R:
            def __init__(self, rc, out):
                self.returncode = rc
                self.stdout = out
                self.stderr = ""

        # --check → 1, sync → 0, ikinci --check → 1.
        seq = [R(1, "BAYAT: x"), R(0, "ÖZET: sync"), R(1, "BAYAT: x")]
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return seq.pop(0)

        findings = []
        add = lambda prio, cid, label, issue, evidence="": findings.append(
            {"priority": prio, "check": cid, "issue": issue,
             "evidence": evidence})
        with mock.patch.object(vd.subprocess, "run", side_effect=fake_run):
            ok, detail, rc, txt, meta = vd.check_mirror_sync(add, auto_sync=True)
        self.assertFalse(ok)
        self.assertIn("hâlâ bayat", detail)
        self.assertTrue(meta["auto_synced"])
        self.assertEqual(meta["before_exit"], 1)
        self.assertEqual(meta["after_exit"], 1)
        self.assertEqual(meta["sync_rc"], 0)
        self.assertTrue(any("hâlâ bayat" in f["issue"] for f in findings))

    def test_flag_without_check_mirror_exits_2(self):
        """--mirror-auto-sync tek başına → exit 2 (fail-closed)."""
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            r = run(env, sys.executable, VERIFY_DELIVERY, "--mirror-auto-sync")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("HATA", r.stderr)

    def test_no_auto_sync_keeps_bayat_p1(self):
        """Bayraksız koşumda BAYAT → P1 (auto_sync izi yok)."""
        sys.path.insert(0, HERE)
        import verify_delivery as vd  # noqa: E402

        class R:
            def __init__(self, rc, out):
                self.returncode = rc
                self.stdout = out
                self.stderr = ""

        seq = [R(1, "BAYAT: x")]

        def fake_run(cmd, **kw):
            return seq.pop(0)

        findings = []
        add = lambda prio, cid, label, issue, evidence="": findings.append(
            {"priority": prio, "check": cid, "issue": issue,
             "evidence": evidence})
        with mock.patch.object(vd.subprocess, "run", side_effect=fake_run):
            ok, detail, rc, txt, meta = vd.check_mirror_sync(add, auto_sync=False)
        self.assertFalse(ok)
        self.assertFalse(meta["auto_synced"])
        self.assertIsNone(meta["after_exit"])
        self.assertEqual(meta["before_exit"], 1)


class TestMirrorOutSidecar(unittest.TestCase):
    """--mirror-out: --check-mirror ham çıktısı + K17 raporu tek JSON'da."""

    def test_sidecar_contains_output_and_report(self):
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            syn = run(env, "bash", SYNC_MIRROR)
            self.assertEqual(syn.returncode, 0, syn.stderr)
            out = os.path.join(work, "mirror_report.json")
            r = run(env, sys.executable, VERIFY_DELIVERY, "--check-mirror",
                    "--mirror-out", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            # K17 raporu (layer + ok + exit + detail) VE ham --check çıktısı
            # (SONUÇ satırı) sidecar'da olmalı.
            self.assertEqual(d["layer"], "K17")
            self.assertTrue(d["ok"])
            self.assertIn("SONUÇ: mirror güncel", d["output"])


if __name__ == "__main__":
    unittest.main()
