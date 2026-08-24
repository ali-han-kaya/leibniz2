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
            # GÜNCEL → bayat dosya listesi boş (dashboard paneli verisi).
            self.assertEqual(d.get("stale_files"), [])

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
            # BAYAT → bayat dosya listesi bozulan dosyayı içermeli (dashboard
            # paneli bu listeden BAYAT/EKSİK dosyaları gösterir).
            self.assertIn("verify_delivery.py", d.get("stale_files", []))

    def test_k17_kaynak_yok_p1(self):
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            empty = os.path.join(work, "empty-root")
            os.makedirs(empty)
            env = dict(os.environ)
            env["ROOT"] = empty
            r = run(env, sys.executable, VERIFY_DELIVERY, "--check-mirror")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("[P1] K17 mirror sync", r.stdout)

    def test_k17_tcc_route_skips_not_fail(self):
        # TCC rotası: launchd GUI agent ~/Desktop'ı okuyamaz — bash exit 126
        # + "Operation not permitted". K17 sahte FAIL üretmemeli: SKIP notu
        # (ok=True, exit=None, bulgu yok) — verdict etkilenmez.
        sys.path.insert(0, HERE)
        import verify_delivery as vd  # noqa: E402
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            fake = mock.Mock()
            fake.returncode = 126
            fake.stdout = ""
            fake.stderr = ("bash: /Users/alikaya/Desktop/leibniz2/_calisma/"
                           "CIKTI/sync_verify_mirror.sh: Operation not "
                           "permitted\n")
            with mock.patch.object(vd.subprocess, "run", return_value=fake):
                findings = []
                add = lambda prio, cid, label, issue, evidence="": findings.append(
                    {"priority": prio, "check": cid, "issue": issue,
                     "evidence": evidence})
                ok, detail, rc, txt, meta = vd.check_mirror_sync(add)
            self.assertTrue(ok)          # SKIP — FAIL değil
            self.assertIsNone(rc)
            self.assertIn("TCC rotası", detail)
            self.assertIn("Operation not permitted", txt)
            # Bulgu ÜRETİLMEMELİ (P1 yok → K17 PASS, verdict etkilenmez).
            self.assertEqual(findings, [])

    def test_k17_script_yok_p1(self):
        # check_mirror_sync, script yolunu __file__'a göre sabit hesaplar;
        # os.path.isfile'i patch'leyerek script-yok dalını uyarırız.
        sys.path.insert(0, HERE)
        import verify_delivery as vd  # noqa: E402
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            script = os.path.join(HERE, "sync_verify_mirror.sh")
            real_isfile = os.path.isfile  # patch'ten önce yakala (recursion yok)

            def fake_isfile(p):
                if p == script:
                    return False
                return real_isfile(p)

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


def _mirror_section(text, name):
    """sync_verify_mirror.sh'te `<name>=(...)` bloğunun gövdesini döndür."""
    m = re.search(r"%s=\(\n(.*?)\n\)" % re.escape(name), text, re.S)
    return m.group(1) if m else ""


def _listed_sources(section):
    """Bir bölümdeki kaynak|dest satırlarının kaynak kısmı (set)."""
    out = set()
    for ln in section.splitlines():
        ln = ln.strip().strip('"')
        if "|" in ln:
            out.add(ln.split("|", 1)[0])
    return out


class TestMirrorFileCoverage(unittest.TestCase):
    """Mirror FILES listesi repo'daki tüm runtime dosyalarını kapsar.

    Regresyon: launchd rotasında K16 battery github_scripts/*.js'i mirror'dan
    koşar; eksik bir script (ör. label_gate_p1.js) K16'yı P0/FAIL'e düşürürdü
    (gerçek bir canlı hataydı). Bu test, github_scripts DIŞINDAKİ runtime
    dosyalarını da fail-closed denetler: teslim zip'leri (+ .sha256), core
    runtime/config dosyaları ve K9 lean projesinin tüm kaynakları — her biri
    kendi bölümünde (FILES / LEAN_FILES) listelenmiş olmalı.
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

    def test_all_zips_in_mirror_files(self):
        # Teslim zip'leri + .sha256 sidecar'ları: repo'ya yeni bir zip girerse
        # FILES'a da eklenmeli (yoksa mirror'da eksik → reproducibility kırılır).
        with open(SYNC_MIRROR, encoding="utf-8") as f:
            text = f.read()
        listed = _listed_sources(_mirror_section(text, "FILES"))
        repo_zips = {n for n in os.listdir(HERE)
                     if n.endswith(".zip") or n.endswith(".zip.sha256")}
        missing = repo_zips - listed
        self.assertEqual(missing, set(),
                         f"FILES listesinde eksik zip: {missing}")

    def test_runtime_config_files_listed(self):
        # Core runtime dosyaları (script'ler + config'ler): mirror'da eksikse
        # launchd rotası K1-K18'i çalıştıramaz → her biri FILES'ta olmalı.
        with open(SYNC_MIRROR, encoding="utf-8") as f:
            text = f.read()
        listed = _listed_sources(_mirror_section(text, "FILES"))
        required = [
            "verify_delivery.py", "verify_delivery.config.json",
            "verify_delivery.config.schema.json", "symbolic_proof_z3.py",
            "verify_lean.sh", "zip_lineage.json", "gen_repro_manifest.py",
            "gen_config.py", "cleanup_log.json", "github_scripts_battery.py",
            "github_scripts_selftest.js", "daemon_http_test.py",
            "preview.html",
            "fresh_clone_setup.sh", "test_fresh_clone_setup.py",
            "update_preview.sh",
        ]
        missing = [n for n in required if n not in listed]
        self.assertEqual(missing, [],
                         f"FILES listesinde eksik runtime dosyası: {missing}")

    def test_all_lean_sources_in_mirror_files(self):
        # K9 lake projesi: repo'daki her kaynak (.lean + lean-toolchain +
        # lakefile.toml) LEAN_FILES'te olmalı — eksik kaynak mirror rotasında
        # K9-LAKE P0 üretir (yalnızca ReductInvariance.lean'ın senkronlanması
        # canlı dashboard'ı FAIL'e düşürmüştü). .lake build dizini ve
        # lake-manifest.json kaynak değildir, sayılmaz.
        lean_src = os.path.abspath(os.path.join(HERE, "..", "lean_reduct"))
        self.assertTrue(os.path.isdir(lean_src), "lean_reduct yok: %s" % lean_src)
        repo = set()
        for root, dirs, files in os.walk(lean_src):
            dirs[:] = [d for d in dirs if d != ".lake"]
            for fn in files:
                rel = os.path.relpath(os.path.join(root, fn), lean_src)
                if rel.endswith(".lean") or rel in ("lean-toolchain",
                                                     "lakefile.toml"):
                    repo.add(rel)
        with open(SYNC_MIRROR, encoding="utf-8") as f:
            text = f.read()
        listed = _listed_sources(_mirror_section(text, "LEAN_FILES"))
        missing = repo - listed
        self.assertEqual(missing, set(),
                         f"LEAN_FILES'te eksik lean kaynağı: {missing}")

    def test_lean_mirror_files_listed(self):
        with open(SYNC_MIRROR, encoding="utf-8") as f:
            text = f.read()
        # LEAN_FILES ReductInvariance.lean'ı içermeli (K9 launchd rotası).
        self.assertIn("ReductInvariance.lean", text)

    def test_preview_files_listed(self):
        with open(SYNC_MIRROR, encoding="utf-8") as f:
            text = f.read()
        # PREVIEW_FILES (adım 2) preview_server.py + _daemonize.py + prestart
        # içermeli — adım 2+4 tek komutta senkron edilir (launchd çalıştırıcısı
        # + PreStart kontrolü; eksik runtime dosyası K17 BAYAT'a düşer).
        self.assertIn("preview_server.py|preview_server.py", text)
        self.assertIn("_daemonize.py|_daemonize.py", text)
        self.assertIn("preview_prestart.py|preview_prestart.py", text)

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

    def test_k17_layer_catches_preview_runtime_drift(self):
        """K17 kapsamı (mirror-bayatlık düzeltmesi): preview_server.py +
        _daemonize.py bayatlığı yalnızca FILES listesinde değil, K17
        KATMANINDAN da yakalanır — sync --check BAYAT → verify_delivery.py
        --check-mirror exit 1 + P1 + stale_files'a preview/ önekiyle girer
        (dashboard mirror paneli bu listeden BAYAT dosyaları gösterir)."""
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            syn = run(env, "bash", SYNC_MIRROR)
            self.assertEqual(syn.returncode, 0, syn.stderr)
            preview_mirror = env["PREVIEW_MIRROR"]
            for name in ("preview_server.py", "_daemonize.py"):
                p = os.path.join(preview_mirror, name)
                self.assertTrue(os.path.isfile(p),
                                "%s mirror'da olmalı" % name)
                with open(p, "a", encoding="utf-8") as f:
                    f.write("\n# drift\n")
            out = os.path.join(work, "mirror_report.json")
            r = run(env, sys.executable, VERIFY_DELIVERY, "--check-mirror",
                    "--mirror-out", out)
            # Her iki runtime dosyası da BAYAT → P1 (fail-closed).
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("[P1] K17 mirror sync", r.stdout)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            self.assertFalse(d["ok"])
            self.assertEqual(d["exit"], 1)
            stale = d.get("stale_files", [])
            self.assertIn("preview/preview_server.py", stale)
            self.assertIn("preview/_daemonize.py", stale)


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


class TestK17InFullChain(unittest.TestCase):
    """--full, K17'yi mirror-kurulum semantiğiyle aktifleştirir."""

    def test_full_enables_k17_with_auto_sync(self):
        sys.path.insert(0, HERE)
        import verify_delivery as vd  # noqa: E402
        import types
        args = types.SimpleNamespace(
            full=True, check_references=False, symbolic_proof=False,
            lean_proof=False, check_lineage=False, check_repro_manifest=False,
            check_config_drift=False, check_cleanup=False,
            check_github_scripts=False, check_mirror=False,
            mirror_auto_sync=False)
        out = vd.apply_full_flags(args)
        self.assertTrue(out.check_mirror)
        self.assertTrue(out.mirror_auto_sync)
        self.assertTrue(out.check_github_scripts)

    def test_without_full_keeps_flags(self):
        sys.path.insert(0, HERE)
        import verify_delivery as vd  # noqa: E402
        import types
        args = types.SimpleNamespace(full=False, check_mirror=False,
                                     mirror_auto_sync=False)
        out = vd.apply_full_flags(args)
        self.assertFalse(out.check_mirror)
        self.assertFalse(out.mirror_auto_sync)

    def test_full_auto_sync_no_validation_error(self):
        """--full, check_mirror + mirror_auto_sync'i BİRLİKTE açar — doğrulama
        (auto_sync yalnızca check_mirror ile) exit 2 vermez."""
        sys.path.insert(0, HERE)
        import verify_delivery as vd  # noqa: E402
        import types
        args = types.SimpleNamespace(full=True, check_mirror=False,
                                     mirror_auto_sync=False)
        out = vd.apply_full_flags(args)
        # --full sonrası her ikisi de açık → geçerli kombinasyon.
        self.assertTrue(out.check_mirror and out.mirror_auto_sync)

    def test_auto_sync_without_check_mirror_exits_2_after_full_block(self):
        """--full olmadan --mirror-auto-sync → exit 2 (fail-closed, --full
        bloğu sonrası doğrulama)."""
        sys.path.insert(0, HERE)
        import verify_delivery as vd  # noqa: E402
        with tempfile.TemporaryDirectory(prefix="mirror-k17-") as work:
            env = sync_env(work)
            r = run(env, sys.executable, VERIFY_DELIVERY, "--mirror-auto-sync")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("HATA", r.stderr)


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
