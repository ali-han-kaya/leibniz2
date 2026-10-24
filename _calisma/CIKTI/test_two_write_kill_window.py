#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_two_write_kill_window.py — kill-mid-window koşum takımı, diğer çift-yazım yollarında.

Referans vaka (zaten pinli): `test_preview_server_atomic.py`
`SigtermMidWriteRegressionTests` — `preview_server.persist_history`
(`history.jsonl` → `.sha256`) SIGTERM drain'iyle kapanır.

Bu modül aynı üç adımı depodaki DİĞER artifact+sidecar üreticilerine uygular:

  1. Üreticiyi tam birinci yazımdan SONRA öldür — ikinci yazım hiç olmaz.
  2. Çiftin gerçekten yırtık kaldığını ölç (hash ≠ sidecar).
  3. Çifti okuyan GERÇEK kapıyı koştur: yırtığı yakalıyor mu? Ardından
     üreticiyi yeniden koş: onarılıyor mu?

Kapsanan yollar ve kapıları:

  A. `backfill_history_layers.apply`        history.jsonl → .sha256       kapı: K15
  B. `gen_repro_manifest.main`              manifest.json → manifest.sha256 kapı: K10
  C. `repack_delivery.main`                 CIKTI/<zip> → .sha256         kapı: --verify
  D. `_calisma/video/scripts/fetch_live_data.sh` (cp) history → .sha256   kapı: K15

Bulgu (davranış, kaza değil): bu dört üreticinin HİÇBİRİ ikinci yazımı
birinciyle atomik bağlamaz — pencere gerçektir. Sözleşme "yırtık çift asla
PASS vermez" (fail-closed dedektör) üzerinedir; onarım yolu "üreticiyi
yeniden koş"tur. Referans vakadaki drain yalnız sunucunun kendi shutdown'ı
için vardır, diğer üreticilere genellenmemiştir.

Not: D, aynı `history.jsonl` çiftinin ÜÇÜNCÜ yazarıdır (sunucu, backfill,
fetch script) — çiftin tek yazıcısı yoktur, yalnız tek okuyucusu (K15) vardır.

KAPSAM DIŞI (bilinçli — kapı sözleşmesi farklı):

  - `ingiliz_empirizmi_v3.pdf.metadata.sha256`: yırtık/bayat çift GATED
    değildir; `verify_delivery` drift'i yalnız bilgi olarak raporlar
    (`drift_gated = False`) çünkü qpdf --remove-metadata aynı PDF'te bile
    farklı byte üretir. Fail-closed bir okuyucu yok → yırtığı "yakalamalı"
    diye assert edilemez.
  - `_calisma/REVIEW/*.pdf.sha256`: okuyucu VAR (`check_review_freshness`,
    bayat çifti zaten `test_check_review_freshness.py` pinliyor) ama üretici
    `build_review_pdf.sh` TeXLive ister; kill enjeksiyonu çevrimdışı
    kurulamıyor. Pencere aynı sınıftır (pdf → sidecar), guard'ı vardır.
  - `verify_checks.sh` sidecar'ı verdict kaydıdır (artifact+hash çifti değil).

stdlib-only, OFFLINE: `gh` stub'lanır; latex/qpdf/ağ gerekmez.
"""

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
for _p in (HERE, PARENT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import backfill_history_layers as bh  # noqa: E402
import gen_repro_manifest as gen  # noqa: E402
import verify_delivery as vd  # noqa: E402
# Repack sandbox'ı (MANIFEST_FILES sözleşmesi + tmp ağacı) TEK kaynaktan
# gelir; kopyalamak iki fixture'ı ayrı ayrı çürütürdü.
import test_repack_idempotence as repack_fixture  # noqa: E402

FETCH_SCRIPT = os.path.join(PARENT, "video", "scripts", "fetch_live_data.sh")


class SimulatedKill(BaseException):
    """SIGKILL benzetimi: süreç ölür, ikinci yazım hiç olmaz, cleanup koşmaz.

    BaseException (Exception değil) — üreticilerin `except Exception` ağları
    bunu yutamaz; gerçek kill gibi davranır.
    """


# ── ortak yardımcılar ────────────────────────────────────────────────────
def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha_in_sidecar(sidecar_path):
    try:
        with open(sidecar_path, encoding="utf-8") as f:
            raw = f.read().strip()
    except OSError:
        return ""
    return raw.split()[0] if raw else ""


def _sidecar_sha(path):
    return _sha_in_sidecar(path + ".sha256")


def gated_kill(real, nth):
    """`real`i nth çağrıya kadar koş, nth çağrıda süreci öldür (yazım olmaz)."""
    state = {"n": 0}

    def wrapper(*args, **kwargs):
        state["n"] += 1
        if state["n"] == nth:
            raise SimulatedKill("kill: %d. yazımdan önce" % nth)
        return real(*args, **kwargs)

    return wrapper


class WindowAssertions(unittest.TestCase):
    def assertTornPair(self, artifact, sidecar, msg=""):
        self.assertTrue(os.path.isfile(artifact), "artifact yok: %s" % artifact)
        self.assertTrue(os.path.isfile(sidecar), "sidecar yok: %s" % sidecar)
        self.assertNotEqual(
            _sha(artifact), _sha_in_sidecar(sidecar),
            "%s: çift yırtık DEĞİL (artifact ve sidecar aynı hash) — "
            "pencere kanıtlanmadı" % (msg or artifact))

    def assertConsistentPair(self, artifact, sidecar, msg=""):
        self.assertEqual(
            _sha(artifact), _sha_in_sidecar(sidecar),
            "%s: çift tutarsız (onarım başarısız)" % (msg or artifact))

    def assertTorn(self, path, msg=""):
        self.assertTornPair(path, path + ".sha256", msg)

    def assertConsistent(self, path, msg=""):
        self.assertConsistentPair(path, path + ".sha256", msg)

    def k15(self, history_path):
        findings = []
        ok, detail = vd.check_history_sidecar(
            history_path, lambda *a: findings.append(a))
        return ok, detail, findings


# ── A. backfill: history.jsonl → .sha256 (kapı K15) ──────────────────────
def _verify_blob(layers):
    return json.dumps({"verdict": "FAIL", "counts": {"P0": 1, "P1": 0},
                       "layers": layers})


class BackfillHistoryWindowTests(WindowAssertions):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.history = os.path.join(self._tmp.name, "history.jsonl")
        self.runs = os.path.join(self._tmp.name, "runs")
        os.makedirs(self.runs)

    def _write_pair(self):
        ts = "2026-10-06T03:22:47.220516+00:00"
        with open(self.history, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "verdict": "FAIL",
                                "exit_code": 1,
                                "status_board": "K0 K katmanlari"}) + "\n")
        with open(self.history + ".sha256", "w", encoding="utf-8") as f:
            f.write("%s  history.jsonl\n" % _sha(self.history))
        name = "run-%s.json" % ts.replace(":", "").replace(".", "").replace("+", "")
        with open(os.path.join(self.runs, name), "w", encoding="utf-8") as f:
            json.dump({"ts": ts, "exit_code": 1, "stderr": "",
                       "stdout": _verify_blob({"K0": {"status": "FAIL"},
                                               "K5": {"status": "PASS"}})}, f)
        return ts

    def _plan_rows(self):
        """`apply` girdisini doğrudan kur.

        NOT (önceden var olan, bu testin konusu olmayan kırık): `bh.plan()`
        `preview_server._normalize_layers`'a dayanır ama o fonksiyon HEAD'de
        hiç yok (0604960e merge'ünde de yoktu) — `test_backfill_history_layers`
        bu yüzden zaten kırmızı. Pencere `apply()`'ın iki yazımında; planlama
        yarısını taklit etmek yerine aynı sözleşmeyi taşıyan satırı kuruyoruz.
        """
        with open(self.history, encoding="utf-8") as f:
            raw = f.read().rstrip("\n")
        row = json.loads(raw)
        row["layers"] = {"K0": {"status": "FAIL"}}
        rows = [{"n": 1, "raw": raw, "row": row, "action": "fill"}]
        return rows, {"baseline_sha256": _sha(self.history)}

    def test_kill_between_history_and_sidecar_is_detected_by_k15_then_repaired(self):
        self._write_pair()
        rows, report = self._plan_rows()

        with mock.patch.object(bh, "_write_atomic",
                               gated_kill(bh._write_atomic, 2)):
            with self.assertRaises(SimulatedKill):
                bh.apply(self.history, rows, report)

        # 1. yazım düştü (layers eklendi), 2. yazım hiç olmadı (sidecar bayat).
        with open(self.history, encoding="utf-8") as f:
            self.assertIn("layers", f.read(),
                          "ilk yazım (history) düşmemiş — pencere yanlış yerde")
        self.assertTorn(self.history, "backfill history↔sidecar")

        # Gerçek kapı: K15 yırtığı yakalar (fail-closed).
        ok, detail, findings = self.k15(self.history)
        self.assertFalse(ok, "K15 yırtık çifti PASS saydı: %s" % detail)
        self.assertIn("uyuşmuyor", detail)
        self.assertTrue(findings, "K15 bulgu kaydı üretmedi")

        # Onarım: üretici yeniden koşar → çift tutarlı.
        rows, report = self._plan_rows()
        bh.apply(self.history, rows, report)
        self.assertConsistent(self.history, "backfill onarım")
        self.assertTrue(self.k15(self.history)[0])


# ── B. gen_repro_manifest: manifest.json → manifest.sha256 (kapı K10) ────
class ManifestWindowTests(WindowAssertions):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.artifacts = os.path.join(self._tmp.name, "all_artifacts")
        self.out = os.path.join(self._tmp.name, "reproducibility")
        os.makedirs(self.artifacts)
        self.manifest = os.path.join(self.out, "manifest.json")
        self.manifest_sidecar = os.path.join(self.out, "manifest.sha256")
        self._put(self.artifacts, "a.txt", b"a\n")

    @staticmethod
    def _put(directory, name, data):
        path = os.path.join(directory, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def _run(self, kill_sidecar=False):
        argv = ["gen_repro_manifest.py", "--artifacts-dir", self.artifacts,
                "--out-dir", self.out]
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(stdout):
            if kill_sidecar:
                real_replace = os.replace

                def killer(src, dst, *a, **k):
                    if str(dst).endswith("manifest.sha256"):
                        raise SimulatedKill(
                            "kill: manifest.sha256 replace'inden önce")
                    return real_replace(src, dst, *a, **k)

                with mock.patch.object(gen.os, "replace", killer):
                    gen.main()
            else:
                gen.main()

    def k10(self):
        findings = []
        ok, rows = vd._check_manifest_sidecar(
            self.manifest, lambda *a: findings.append(a),
            "K10-MANIFEST", "K10 manifest digest")
        return ok, rows, findings

    def test_kill_between_manifest_and_sidecar_is_detected_by_k10_then_repaired(self):
        self._run()  # taban: tutarlı çift
        self.assertTrue(self.k10()[0], "taban manifest K10'dan geçmedi")

        # Artifact kümesi değişir → manifest.sha256 zorunlu değişecek.
        self._put(self.artifacts, "b.txt", b"b\n")
        with self.assertRaises(SimulatedKill):
            self._run(kill_sidecar=True)

        with open(self.manifest, encoding="utf-8") as f:
            self.assertIn("b.txt", json.load(f)["files"],
                          "manifest.json yeni içerikle yazılmamış")
        self.assertTornPair(self.manifest, self.manifest_sidecar,
                            "manifest.json↔manifest.sha256")

        ok, rows, findings = self.k10()
        self.assertFalse(ok, "K10 yırtık çifti PASS saydı: %s" % rows)
        self.assertIn("hash uyuşmazlığı", rows)
        self.assertTrue(findings)

        self._run()  # onarım
        self.assertConsistentPair(self.manifest, self.manifest_sidecar,
                                  "manifest onarım")
        self.assertTrue(self.k10()[0])


# ── C. repack: CIKTI/<zip> → .sha256 (kapı --verify) ─────────────────────
class RepackCopyWindowTests(WindowAssertions):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.box = repack_fixture._Sandbox(
            os.path.join(self._tmp.name, "_calisma")).build()
        self.rd = self.box.import_repack()
        self._argv = sys.argv
        sys.argv = ["repack_delivery.py"]
        self.addCleanup(self._restore_argv)

    def _restore_argv(self):
        sys.argv = self._argv

    def _repack(self, kill_sidecar_copy=False):
        target = os.path.abspath(
            os.path.join(self.box.cikti, self.rd.INNER_ZIP + ".sha256"))
        stdout = io.StringIO()
        if kill_sidecar_copy:
            real_open = open

            def killer(path, mode="r", *a, **k):
                if "w" in mode and os.path.abspath(str(path)) == target:
                    raise SimulatedKill(
                        "kill: CIKTI/<zip>.sha256 kopyasından önce")
                return real_open(path, mode, *a, **k)

            with contextlib.redirect_stdout(stdout), \
                    mock.patch.object(self.rd, "open", killer, create=True):
                rc = self.rd.main()
        else:
            with contextlib.redirect_stdout(stdout):
                rc = self.rd.main()
        return rc

    def _verify(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.rd.verify_sidecars(self.box.cikti)

    def test_kill_between_zip_copy_and_sidecar_copy_is_detected_then_repaired(self):
        self.assertEqual(self._repack(), 0)
        self.assertTrue(self._verify(), "taban repack --verify yeşil değil")

        # Paket içeriği değişir → iç zip baytları değişecek.
        with open(os.path.join(self.box.pkg, "core_section.tex"),
                  "a", encoding="utf-8") as f:
            f.write("% degisiklik\n")

        with self.assertRaises(SimulatedKill):
            self._repack(kill_sidecar_copy=True)

        target = os.path.join(self.box.cikti, self.rd.INNER_ZIP)
        self.assertTorn(target, "repack CIKTI zip↔sidecar")
        self.assertFalse(self._verify(),
                         "--verify yırtık zip/sidecar çiftini PASS saydı")

        self.assertEqual(self._repack(), 0)
        self.assertConsistent(target, "repack onarım")
        self.assertTrue(self._verify())

    def test_truncated_zip_from_mid_build_kill_is_rejected(self):
        """build_zip doğrudan out_path'e yazar; yarıda ölüm yarım zip bırakır."""
        self.assertEqual(self._repack(), 0)
        target = os.path.join(self.box.cikti, self.rd.INNER_ZIP)
        with open(target, "rb") as f:
            data = f.read()
        with open(target, "wb") as f:
            f.write(data[: max(1, len(data) // 2)])
        self.assertFalse(self._verify(),
                         "--verify yarım zip'i (sidecar bayat) PASS saydı")


# ── D. fetch_live_data.sh: cp history → cp sidecar (kapı K15) ────────────
GH_STUB = """#!/usr/bin/env bash
# fetch_live_data.sh için offline `gh`: auth OK, tek koşu, iki artifact.
if [ "$1" = "auth" ] && [ "$2" = "status" ]; then exit 0; fi
if [ "$1" = "run" ] && [ "$2" = "list" ]; then
  case "$*" in
    *"--json databaseId "*|*"--json databaseId") echo 4242; exit 0 ;;
    *"--json databaseId,createdAt"*) printf '4242\\t2026-10-23T00:00:00Z\\n'; exit 0 ;;
  esac
  exit 1
fi
if [ "$1" = "run" ] && [ "$2" = "download" ]; then
  shift 2
  id="$1"; shift
  name=""; dir=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --name) name="$2"; shift 2 ;;
      --dir)  dir="$2"; shift 2 ;;
      *) shift ;;
    esac
  done
  mkdir -p "$dir"
  case "$name" in
    run-history)
      REAL_CP "$FIXTURE_DIR/history.jsonl" "$dir"/
      REAL_CP "$FIXTURE_DIR/history.jsonl.sha256" "$dir"/ ;;
    klayers)     REAL_CP "$FIXTURE_DIR/klayers.json" "$dir"/ ;;
    *) exit 1 ;;
  esac
  exit 0
fi
exit 1
"""

CP_KILLER = """#!/usr/bin/env bash
# Pencere: hedef *.sha256 ise kabuğu SIGKILL ile öldür (ikinci yazım olmaz).
for a in "$@"; do
  case "$a" in
    *.sha256) kill -KILL "$PPID"; exit 137 ;;  # kopya HİÇ yazılmaz
esac
done
exec REAL_CP "$@"
"""


class FetchLiveDataWindowTests(WindowAssertions):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.join(self._tmp.name, "repo")
        self.cikti = os.path.join(self.root, "_calisma", "CIKTI")
        scripts = os.path.join(self.root, "_calisma", "video", "scripts")
        os.makedirs(self.cikti)
        os.makedirs(scripts)
        self.script = os.path.join(scripts, "fetch_live_data.sh")
        shutil.copy2(FETCH_SCRIPT, self.script)

        self.fixture = os.path.join(self._tmp.name, "fixture")
        os.makedirs(self.fixture)
        self.bin = os.path.join(self._tmp.name, "bin")
        os.makedirs(self.bin)
        real_cp = shutil.which("cp") or "/bin/cp"
        self._script(os.path.join(self.bin, "gh"), GH_STUB.replace("REAL_CP", real_cp))
        self.kill_bin = os.path.join(self._tmp.name, "killbin")
        os.makedirs(self.kill_bin)
        self._script(os.path.join(self.kill_bin, "cp"),
                     CP_KILLER.replace("REAL_CP", real_cp))

        self.history = os.path.join(self.cikti, "history.jsonl")
        self.tmpdir = os.path.join(self._tmp.name, "tmp")
        os.makedirs(self.tmpdir)

    @staticmethod
    def _script(path, body):
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        os.chmod(path, 0o755)

    def _publish_artifact(self, rows):
        with open(os.path.join(self.fixture, "history.jsonl"), "w",
                  encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        with open(os.path.join(self.fixture, "history.jsonl.sha256"), "w",
                  encoding="utf-8") as f:
            f.write("%s  history.jsonl\n"
                    % _sha(os.path.join(self.fixture, "history.jsonl")))
        with open(os.path.join(self.fixture, "klayers.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"layers": {"K0": {"status": "PASS"}}}, f)

    def _fetch(self, kill_mid_window=False):
        env = dict(os.environ)
        path_parts = ([self.kill_bin] if kill_mid_window else []) + \
            [self.bin, env.get("PATH", "")]
        env.update({"PATH": os.pathsep.join(path_parts),
                    "FIXTURE_DIR": self.fixture, "TMPDIR": self.tmpdir})
        return subprocess.run(["bash", self.script], capture_output=True,
                              text=True, env=env, timeout=120)

    def test_kill_between_history_and_sidecar_copy_is_detected_then_repaired(self):
        row = {"ts": "2026-10-23T00:00:00+00:00", "verdict": "PASS",
               "exit_code": 0}
        self._publish_artifact([row])
        base = self._fetch()
        self.assertEqual(base.returncode, 0, base.stdout + base.stderr)
        self.assertConsistent(self.history, "fetch_live_data taban")

        # Daha zengin artifact: history değişecek, sidecar kopyası öldürülecek.
        row2 = dict(row, ts="2026-10-23T01:00:00+00:00")
        self._publish_artifact([row, row2])

        killed = self._fetch(kill_mid_window=True)
        self.assertEqual(killed.returncode, -9,
                         "cp kabuğu SIGKILL ile ölmedi: rc=%s\n%s"
                         % (killed.returncode, killed.stdout + killed.stderr))
        with open(self.history, encoding="utf-8") as f:
            self.assertEqual(len(f.read().splitlines()), 2,
                             "ilk kopya (history) düşmemiş")
        self.assertTorn(self.history, "fetch_live_data history↔sidecar")

        ok, detail, findings = self.k15(self.history)
        self.assertFalse(ok, "K15 yırtık çifti PASS saydı: %s" % detail)
        self.assertIn("uyuşmuyor", detail)
        self.assertTrue(findings)

        repaired = self._fetch()
        self.assertEqual(repaired.returncode, 0,
                         repaired.stdout + repaired.stderr)
        self.assertConsistent(self.history, "fetch_live_data onarım")
        self.assertTrue(self.k15(self.history)[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
