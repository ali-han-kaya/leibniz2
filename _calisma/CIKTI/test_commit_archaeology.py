#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_commit_archaeology.py — her commit AĞACININ kendi başına tutarlılığı.

Neden: kapılar yalnızca "şimdiki ağaç"ı denetliyordu. Bir commit serisi
ilerlerken tutarlılık sık sık *commit sınırını* aşar: job `verify.yml`'e
eklenir, doküman satırı bir sonraki commit'e kalır; bir test dosyası eklenir,
`check_unit_tests.list` kaydı unutulur; bir action yükseltilir, pin dosyası
geride kalır. O commit'ler kendi başına checkout edildiğinde kırmızıdır ama
seri başında hepsi yeşil görünür — bisect imkânsızlaşır.

Bu test serideki HER commit için ağacı ayrı bir `git worktree` olarak
materyalize eder ve O AĞACIN KENDİ kapılarını koşturur (host ağacının
kapılarını değil — tarihsel commit, tarihsel kapıyla ölçülür):

  1. workflow    — ağacın `test_doc_job_sync.py` + `test_workflow_contract.py`
                   süitleri: PASS ve SKIP'siz (SKIP'li yeşil, yeşil değildir).
  2. pin         — ağacın `check_action_pins.py` çıkışı 0 (downgrade/pin'siz
                   action yok).
  3. test kaydı  — ağacın `sync_check_unit_tests.py --check` çıkışı 0
                   (manifest ∪ HOOK_COVERAGE ∪ glob kapsamı o ağaçla uyumlu).

Fail-closed sözleşmeler:
  * Kapı dosyası ağaçta YOKSA o eksen FAIL'dir ("kapı yok" — denetlenemeyen
    ağaç yeşil sayılmaz; eski commit'ler bu yüzden kırmızı görünebilir, bu
    doğru sinyaldir).
  * `OK (skipped=N)` → FAIL: PyYAML'sız bir runner'da doc-job kapısı tümden
    SKIP edip sahte-PASS verebilirdi; burada SKIP sayısı sıfır olmalı.
  * `Ran 0 tests` → FAIL (Python 3.12 öncesi 0 test rc=0 dönerdi).
  * Seri boş çözümlenirse tip ağacına (`HEAD`), o da yoksa tek commit'e
    düşülür; hiçbir durumda "0 ağaç denetlendi" ile yeşil olunmaz.
  * `COMMIT_ARCHAEOLOGY_MAX_COMMITS` aşılırsa sessizce kırpılmaz — FAIL
    (kırpılmış seri, denetlenmemiş commit'leri yeşil gösterirdi).

Seri seçimi: `COMMIT_ARCHAEOLOGY_BASE` → `origin/main` → `main` sırasıyla
ilk çözümlenen ref'in `..HEAD` aralığı. Aralık boşsa `HEAD^..HEAD`.

SINIR (dürüst kapsam): commit henüz YOKKEN arkeoloji yapılamaz. Bu yüzden
pre-commit anında bu test o ana kadar YAZILMIŞ seriyi denetler; yeni commit'in
ağacı bir SONRAKİ koşumda denetlenir. Payda CI'dır: `verify` job'ı tam geçmişle
(`fetch-depth: 0`) checkout yapıp tüm seriyi tek turda ölçer.

stdlib-only; git + ağaç kapıları alt süreç olarak koşar.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
ROOT = CIKTI.parent.parent

PIN_GATE = "_calisma/CIKTI/check_action_pins.py"
RECORDS_GATE = "_calisma/CIKTI/sync_check_unit_tests.py"
WORKFLOW_SUITES = ("test_doc_job_sync.py", "test_workflow_contract.py")

GATE_TIMEOUT = int(os.environ.get("COMMIT_ARCHAEOLOGY_TIMEOUT", "300"))
MAX_COMMITS = int(os.environ.get("COMMIT_ARCHAEOLOGY_MAX_COMMITS", "40"))

_SKIP_RE = re.compile(r"^OK \(skipped=(\d+)", re.M)
_RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.M)


# ─────────────────────────────────────────────────────────────────────────────
# git yardımcıları
# ─────────────────────────────────────────────────────────────────────────────
def git(*args, cwd, timeout=120):
    """`git` çağır → (rc, stdout+stderr). Hata fırlatmaz: çağıran karar verir."""
    try:
        proc = subprocess.run(
            ["git"] + list(args), cwd=str(cwd), timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False, text=True, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "git çalıştırılamadı: %s" % exc
    return proc.returncode, proc.stdout or ""


def git_ok(*args, cwd):
    rc, out = git(*args, cwd=cwd)
    return out.strip() if rc == 0 else None


def resolve_series(root, base=None):
    """Denetlenecek commit listesini (eskiden yeniye) çözümle.

    Dönüş: (base_ref_or_None, [sha, ...]) — liste HER ZAMAN en az bir eleman
    içerir (HEAD), böylece test boş seriyle boş yere yeşil olamaz.
    """
    if git_ok("rev-parse", "--git-dir", cwd=root) is None:
        return None, []

    head = git_ok("rev-parse", "HEAD", cwd=root)
    if head is None:
        return None, []

    candidates = []
    if base:
        candidates.append(base)
    candidates.extend(["origin/main", "main"])

    for ref in candidates:
        sha = git_ok("rev-parse", "--verify", "--quiet", ref + "^{commit}",
                     cwd=root)
        if not sha or sha == head:
            continue
        out = git_ok("rev-list", "--reverse", "%s..%s" % (sha, head), cwd=root)
        if out:
            return ref, out.split()
        # Boş aralık (tip ile aynı ya da geride): sıradaki adaya geç.

    # Aralık yok (seri main'de ve ilerisi yok): tip ağacını yine denetle.
    parent = git_ok("rev-parse", "--verify", "--quiet", "HEAD^{commit}^",
                    cwd=root)
    if parent:
        out = git_ok("rev-list", "--reverse", "%s..%s" % (parent, head),
                     cwd=root)
        if out:
            return "HEAD^", out.split()
    return "HEAD", [head]


def commit_subject(root, sha):
    return git_ok("log", "-1", "--format=%s", sha, cwd=root) or "?"


# ─────────────────────────────────────────────────────────────────────────────
# Ağaç kapıları
# ─────────────────────────────────────────────────────────────────────────────
def _tail(text, lines=6):
    rows = [r for r in (text or "").splitlines() if r.strip()]
    return " | ".join(rows[-lines:]) if rows else "(çıktı yok)"


def _run_script(tree, rel, python):
    """Ağaçtaki bir kapı betiğini ağacın kökünden koştur."""
    path = tree / rel
    if not path.is_file():
        return None, "kapı yok: %s (bu ağaçta denetlenemez)" % rel
    try:
        proc = subprocess.run(
            [python, str(path)], cwd=str(tree), timeout=GATE_TIMEOUT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False, text=True, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return None, "%s: %.0f sn zaman aşımı" % (rel, GATE_TIMEOUT)
    except OSError as exc:
        return None, "%s: çalıştırılamadı (%s)" % (rel, exc)
    return proc.returncode, proc.stdout or ""


def _run_suite(tree, pattern, python):
    """Ağacın unittest süitini koştur → (findings, ran, skipped)."""
    findings = []
    path = tree / "_calisma" / "CIKTI" / pattern
    if not path.is_file():
        return ["workflow: süit yok: _calisma/CIKTI/%s" % pattern], 0, 0
    try:
        proc = subprocess.run(
            [python, "-m", "unittest", "discover",
             "-s", "_calisma/CIKTI", "-p", pattern],
            cwd=str(tree), timeout=GATE_TIMEOUT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False, text=True, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return ["workflow: %s zaman aşımı (%.0f sn)" % (pattern, GATE_TIMEOUT)], 0, 0
    except OSError as exc:
        return ["workflow: %s çalıştırılamadı (%s)" % (pattern, exc)], 0, 0

    out = proc.stdout or ""
    ran = int(m.group(1)) if (m := _RAN_RE.search(out)) else 0
    skipped = int(m.group(1)) if (m := _SKIP_RE.search(out)) else 0

    if proc.returncode != 0:
        findings.append("workflow: %s rc=%d — %s"
                        % (pattern, proc.returncode, _tail(out)))
    if ran == 0:
        findings.append("workflow: %s hiç test koşmadı (Ran 0 tests) — "
                        "boş süit yeşil sayılmaz" % pattern)
    if skipped:
        findings.append("workflow: %s %d test SKIP etti — SKIP'li yeşil "
                        "yeşil değildir (PyYAML/venv eksik olabilir)"
                        % (pattern, skipped))
    return findings, ran, skipped


def check_tree(tree, python=None):
    """Bir ağacın üç eksende kendi başına tutarlı olup olmadığını ölç.

    Dönüş: bulgu listesi (boş = tutarlı). Bulgular eksen adıyla başlar:
    `pin:`, `test kaydı:`, `workflow:`.
    """
    python = python or sys.executable
    tree = pathlib.Path(tree)
    findings = []

    rc, out = _run_script(tree, PIN_GATE, python)
    if rc is None:
        findings.append("pin: " + out)
    elif rc != 0:
        findings.append("pin: check_action_pins rc=%d — %s" % (rc, _tail(out)))

    rc, out = _run_script(tree, RECORDS_GATE, python)
    if rc is None:
        findings.append("test kaydı: " + out)
    elif rc != 0:
        findings.append("test kaydı: sync_check_unit_tests rc=%d — %s"
                        % (rc, _tail(out, lines=3)))

    for pattern in WORKFLOW_SUITES:
        suite_findings, _ran, _skipped = _run_suite(tree, pattern, python)
        findings.extend(suite_findings)

    return findings


# ─────────────────────────────────────────────────────────────────────────────
# Seri denetimi
# ─────────────────────────────────────────────────────────────────────────────
def materialize(root, sha, dest):
    """Commit ağacını ayrı worktree olarak aç (git meta verisi korunur —
    `sync_check_unit_tests.py`'nin git tabanlı bayat denetimi buna ihtiyaç
    duyar; `git archive` ile açılan ağaç sahte STALE bulguları üretir)."""
    rc, out = git("worktree", "add", "--detach", "--quiet", str(dest), sha,
                  cwd=root)
    if rc != 0:
        raise RuntimeError("worktree add başarısız (%s): %s" % (sha, _tail(out)))
    return pathlib.Path(dest)


def discard(root, dest):
    """Worktree'yi kaldır; başarısız olursa dizini sil ve prune et."""
    rc, _out = git("worktree", "remove", "--force", str(dest), cwd=root)
    if rc != 0 and pathlib.Path(dest).exists():
        shutil.rmtree(dest, ignore_errors=True)
    git("worktree", "prune", cwd=root)


def audit_series(root, base=None, python=None, max_commits=None):
    """Serideki her ağacı denetle → [(sha, subject, [bulgu...]), ...].

    Yalnızca kırmızı ağaçlar döner (boş liste = seri tutarlı).
    `max_commits` verilmezse modül sabiti (env ile ayarlanabilir) kullanılır.
    """
    cap = MAX_COMMITS if max_commits is None else max_commits
    _ref, shas = resolve_series(root, base=base)
    if not shas:
        return [("?", "(seri çözümlenemedi)", ["git geçmişi yok — denetim "
                                               "yapılamadı"])]
    if len(shas) > cap:
        return [("?", "(%d commit > MAX=%d)" % (len(shas), cap),
                 ["seri COMMIT_ARCHAEOLOGY_MAX_COMMITS=%d sınırını aşıyor; "
                  "kırpma sessiz yeşil üretirdi — sınırı yükseltin veya "
                  "COMMIT_ARCHAEOLOGY_BASE ile daraltın" % cap])]

    bad = []
    tmp_root = tempfile.mkdtemp(prefix="commit-arch-")
    try:
        for sha in shas:
            dest = pathlib.Path(tmp_root) / sha[:12]
            try:
                tree = materialize(root, sha, dest)
            except RuntimeError as exc:
                bad.append((sha, commit_subject(root, sha), [str(exc)]))
                continue
            try:
                findings = check_tree(tree, python=python)
            finally:
                discard(root, dest)
            if findings:
                bad.append((sha, commit_subject(root, sha), findings))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
        git("worktree", "prune", cwd=root)
    return bad


def format_problems(bad):
    lines = []
    for sha, subject, findings in bad:
        lines.append("%s  %s" % (sha[:12], subject))
        for item in findings:
            lines.append("    - %s" % item)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# GERÇEK SERİ
# ─────────────────────────────────────────────────────────────────────────────
class TestRealSeries(unittest.TestCase):
    """origin/main..HEAD serisindeki her ağaç kendi başına tutarlı olmalı."""

    def test_every_commit_tree_is_self_consistent(self):
        base = os.environ.get("COMMIT_ARCHAEOLOGY_BASE") or None
        _ref, shas = resolve_series(ROOT, base=base)
        if not shas:
            self.fail("seri çözümlenemedi: bu dizin bir git deposu değil ya "
                      "da hiç commit yok — arkeoloji denetimi koşamaz")
        self.assertGreaterEqual(
            len(shas), 1, "boş seri: denetlenecek ağaç yok")
        self.assertLessEqual(
            len(shas), MAX_COMMITS,
            "seri %d commit; COMMIT_ARCHAEOLOGY_MAX_COMMITS=%d"
            % (len(shas), MAX_COMMITS))

        bad = audit_series(ROOT, base=base)
        self.assertEqual(
            bad, [],
            "%d/%d commit ağacı kendi başına TUTARSIZ "
            "(workflow/pin/test kaydı):\n%s"
            % (len(bad), len(shas), format_problems(bad)))

    def test_series_resolution_never_empty(self):
        """Seri çözümü her durumda en az bir ağaç verir (boş yeşil yasak)."""
        _ref, shas = resolve_series(ROOT)
        self.assertTrue(shas, "resolve_series boş liste döndürdü")


# ─────────────────────────────────────────────────────────────────────────────
# HERMETİK: kurgusal repo — kırmızıyı gerçekten görebiliyor muyuz?
# ─────────────────────────────────────────────────────────────────────────────
_PIN_OK = "import sys\nsys.exit(0)\n"
_PIN_FAIL = "import sys\nprint('FAIL: checkout@v6 < pin v7')\nsys.exit(1)\n"
_RECORDS_OK = "import sys\nsys.exit(0)\n"
_RECORDS_FAIL = ("import sys\n"
                 "print('YENİ test dosyası listede YOK: test_yeni.py')\n"
                 "sys.exit(1)\n")
_SUITE_OK = (
    "import unittest\n"
    "\n"
    "class T(unittest.TestCase):\n"
    "    def test_ok(self):\n"
    "        self.assertTrue(True)\n"
)
_SUITE_SKIP = (
    "import unittest\n"
    "\n"
    "class T(unittest.TestCase):\n"
    "    @unittest.skip('PyYAML yok')\n"
    "    def test_skipped(self):\n"
    "        self.assertTrue(True)\n"
)
_SUITE_FAIL = (
    "import unittest\n"
    "\n"
    "class T(unittest.TestCase):\n"
    "    def test_bad(self):\n"
    "        self.fail('doc adı workflow name:\\'inde yok')\n"
)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_series_repo(spec):
    """Kurgusal repo kur: `spec` = her commit'te yazılacak dosya sözlüğü.

    Sözlükte `None` değeri o dosyayı SİLER (kapının kaybolduğu durumu
    kurgulamak için). Dosya yolu göreli; içerik metin.
    """
    root = pathlib.Path(tempfile.mkdtemp(prefix="arch-fixture-"))
    git_ok("init", "-q", "-b", "main", cwd=root)
    git_ok("config", "user.email", "arch@example.test", cwd=root)
    git_ok("config", "user.name", "arch fixture", cwd=root)
    shas = []
    for index, files in enumerate(spec, start=1):
        for rel, body in files.items():
            target = root / rel
            if body is None:
                if target.exists():
                    target.unlink()
            else:
                _write(target, body)
        git_ok("add", "-A", cwd=root)
        # --allow-empty: içerik değişmese de her adım AYRI commit olmalı;
        # arkeoloji testi commit sınırlarını değil AĞAÇLARI denetler.
        rc, out = git("commit", "-q", "--allow-empty",
                      "-m", "fixture commit %d" % index, cwd=root)
        if rc != 0:
            raise AssertionError("fixture commit %d başarısız: %s"
                                 % (index, _tail(out)))
        shas.append(git_ok("rev-parse", "HEAD", cwd=root))
    return root, shas


def base_files(pin=_PIN_OK, records=_RECORDS_OK, suite=_SUITE_OK):
    """Tutarlı bir ağacın iskeleti (üç eksenin kapıları + workflow)."""
    files = {
        PIN_GATE: pin,
        RECORDS_GATE: records,
        ".github/workflows/verify.yml":
            "name: verify\njobs:\n  verify:\n    runs-on: ubuntu-latest\n",
    }
    for pattern in WORKFLOW_SUITES:
        files["_calisma/CIKTI/" + pattern] = suite
    return files


class TestHermeticRedProof(unittest.TestCase):
    """Kurgusal seriler: dedektör gerçekten kırmızıya düşüyor mu?

    Bu sınıf olmadan "seri yeşil" iddiası boş olurdu — geçen bir denetçi
    bozuk ağacı da yeşil gösterebilir. Her senaryo tek bir ekseni bozar ve
    kırmızının O COMMIT'e, O EKSENE atfedildiğini doğrular.
    """

    def _audit(self, spec, cap=None):
        """Kurgusal seriyi kur ve denetle → (denetlenen sha'lar, kırmızılar).

        `spec[0]` SEED'dir: gerçek repodaki `origin/main` gibi aralığın
        tabanını temsil eder, kendisi denetlenmez (gerçek seri de tipin
        tabanının kendisini değil, tabandan SONRAKİ ağaçları denetler).
        Böylece denetlenen küme spec[1:] olur ve testler kaç commit'in
        gerçekten yüründüğünü sayıyla pinleyebilir.
        """
        root, shas = make_series_repo(spec)
        try:
            base = shas[0] if len(shas) > 1 else None
            if base:
                audited = resolve_series(root, base=base)[1]
            else:
                audited = resolve_series(root)[1]
            bad = audit_series(root, base=base, max_commits=cap)
            return audited, bad
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_consistent_series_is_green(self):
        audited, bad = self._audit([base_files(), base_files(), base_files()])
        self.assertEqual(len(audited), 2,
                         "seri yürünmedi (boş yeşil riski): %d ağaç"
                         % len(audited))
        self.assertEqual(bad, [], "tutarlı kurgusal seri kırmızı: %s"
                                  % format_problems(bad))

    def test_broken_pin_is_attributed_to_its_commit(self):
        audited, bad = self._audit([
            base_files(),
            base_files(),
            base_files(pin=_PIN_FAIL),
        ])
        self.assertEqual(len(audited), 2)
        self.assertEqual(len(bad), 1, format_problems(bad))
        sha, subject, findings = bad[0]
        self.assertEqual(sha, audited[1], "kırmızı YANLIŞ commit'e atfedildi")
        self.assertIn("fixture commit 3", subject)
        self.assertTrue(any(f.startswith("pin:") for f in findings),
                        findings)

    def test_broken_test_records_are_attributed(self):
        audited, bad = self._audit([
            base_files(),
            base_files(records=_RECORDS_FAIL),
        ])
        self.assertEqual(len(audited), 1)
        self.assertEqual(len(bad), 1, format_problems(bad))
        self.assertEqual(bad[0][0], audited[0])
        self.assertTrue(any(f.startswith("test kaydı:") for f in bad[0][2]),
                        bad[0][2])

    def test_missing_gate_file_fails_closed(self):
        files = base_files()
        files[PIN_GATE] = None  # kapı ağaçta yok
        _audited, bad = self._audit([base_files(), files])
        self.assertEqual(len(bad), 1, format_problems(bad))
        self.assertIn("kapı yok", " ".join(bad[0][2]))

    def test_skipped_workflow_suite_is_red(self):
        _audited, bad = self._audit([base_files(), base_files(suite=_SUITE_SKIP)])
        self.assertEqual(len(bad), 1, format_problems(bad))
        joined = " ".join(bad[0][2])
        self.assertIn("SKIP", joined,
                      "SKIP'li süit yeşil sayıldı (fail-open): %s" % joined)

    def test_failing_workflow_suite_is_red(self):
        _audited, bad = self._audit([base_files(), base_files(suite=_SUITE_FAIL)])
        self.assertEqual(len(bad), 1, format_problems(bad))
        self.assertIn("workflow:", " ".join(bad[0][2]))

    def test_repair_commit_does_not_retroactively_green_a_bad_tree(self):
        """Geçmiş DONMUŞTUR: sonraki commit bozuk ağacı yeşile çevirmez.

        Arkeolojinin amacı bu: kırık commit'te durup adını söylemek. Onarım
        commit'i yalnızca kendi ağacını temizler — komşu ağaçları da
        işaretlemeye başlarsa (kaskad yanlış-pozitif) bu test kırmızı olur.
        """
        audited, bad = self._audit([
            base_files(),
            base_files(),
            base_files(pin=_PIN_FAIL),
            base_files(),
        ])
        self.assertEqual(len(audited), 3, "aralık yürünmedi — boş yeşil riski")
        self.assertEqual([sha for sha, _s, _f in bad], [audited[1]],
                         "yalnızca bozuk ağaç işaretlenmeli:\n%s"
                         % format_problems(bad))

    def test_max_commits_cap_is_fail_closed(self):
        """Sınır aşılırsa sessiz kırpma değil, açık FAIL."""
        audited, bad = self._audit(
            [base_files(), base_files(), base_files(), base_files()], cap=2)
        self.assertEqual(len(audited), 3)
        self.assertEqual(len(bad), 1, format_problems(bad))
        self.assertIn("MAX", " ".join(bad[0][2]))


if __name__ == "__main__":
    unittest.main()
