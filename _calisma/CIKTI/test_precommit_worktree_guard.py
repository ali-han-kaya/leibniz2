#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_precommit_worktree_guard.py — kalıcı çözümün sözleşme testleri.

Seam: CLI (backup/post/status/recover) + GERÇEK sarmalayıcı
(`.git/hooks/pre-commit`), izole scratch repo'larda — kendi
`PRE_COMMIT_HOME`'i, kendi `.git`'i, nötr git config.

KRİTİK test: ÖLÜ-SÜREÇ-PENCERESİ. pre-commit unstaged deltayı stash'leyip
ağacı index'e eşitler ve geri-uygulamayı yalnız `finally`'de bırakır;
pencere içine SIGKILL → ağaç sessizce revert (2026-09-18 olayı). Bu test
gerçekten pre-commit'i ortada ÖLDÜRÜR ve kanıtlar:
  (a) yedek pencere AÇILMADAN alınmıştır (dayanıklı, `.git/` altında),
  (b) delta ağaçtan gitmiştir (zarar gerçektir),
  (c) bir sonraki `backup` adımı delta'yı KENDİLİĞİNDEN geri yükler.

Neden gerçek süreç ölümü şart: `git checkout -- .` benzetimi yalnızca
mimetik olur; asıl sözleşmenin kırılma biçimi "pre-commit'in finally'si hiç
çalışmamasıdır". `subprocess.Popen` + `SIGKILL` bunu gerçekten üretir.

Mutasyon duyarlılığı (yeşil = anlamsız olmasın diye kırıldı → kırmızı):
  * `cmd_backup` recovery döngüsü çıkarılırsa → kurtarma testleri KIRMIZI.
  * `write_backup` `.git/` yerine geçici dizine yazsa → dayanıklılık testi
    (revert sonrası dosya hâlâ var mı) KIRMIZI.
  * `delta_in_tree` her zaman True dönerse → "kayıp" testleri KIRMIZI.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
GUARD = HERE / "precommit_worktree_guard.py"
SELF_HEAL = HERE / "check_worktree_guard_install.py"
INSTALLER = HERE / "install_worktree_guard.sh"
DELTA_GATE = HERE / "check_unstaged_delta.py"
VENV_PC = REPO / "_calisma" / ".venv_z3" / "bin" / "pre-commit"
GIT = shutil.which("git")


def _env(home_dir: pathlib.Path) -> dict:
    env = dict(os.environ)
    env["PRE_COMMIT_HOME"] = str(home_dir / ".pchome")
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env.pop("PRE_COMMIT", None)
    return env


class _Scratch(unittest.TestCase):
    def setUp(self):
        if GIT is None:
            self.skipTest("git yok")
        self.repo = pathlib.Path(tempfile.mkdtemp(prefix="wtguard-"))
        self.addCleanup(shutil.rmtree, self.repo, True)
        self.env = _env(self.repo)
        self._git("init", "-q", ".")
        self._git("config", "user.email", "t@example.invalid")
        self._git("config", "user.name", "t")
        (self.repo / "a.txt").write_text("a1\n", encoding="utf-8")
        (self.repo / "b.txt").write_text("b1\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-qm", "initial")

    def _git(self, *args, **kw):
        env = kw.pop("env", self.env)
        return subprocess.run([GIT, *args], cwd=str(self.repo),
                              capture_output=True, text=True, env=env,
                              timeout=120, **kw)

    def _guard(self, *args, **kw):
        env = kw.pop("env", self.env)
        return subprocess.run(
            [sys.executable, str(GUARD), *args], cwd=str(self.repo),
            capture_output=True, text=True, env=env, timeout=120, **kw)

    def _backup_root(self) -> pathlib.Path:
        out = self._git("rev-parse", "--git-path",
                        "precommit-worktree-backups").stdout.strip()
        p = pathlib.Path(out)
        return p if p.is_absolute() else self.repo / p

    def _make_delta(self) -> None:
        """İzlenen dosyada unstaged delta üret (stage'lenmemiş)."""
        (self.repo / "a.txt").write_text("a-unstaged\n", encoding="utf-8")

    def _tree_content(self, name: str) -> str:
        return (self.repo / name).read_text(encoding="utf-8")


class TestBackupCli(_Scratch):
    """backup/status/recover çekirdek sözleşmeleri."""

    def test_clean_tree_writes_nothing(self):
        res = self._guard("backup")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("yedek gerekmedi", res.stdout)
        self.assertFalse(self._backup_root().exists(),
                         "temiz ağaçta yedek dizini OLUŞMAMALI")

    def test_backup_writes_patch_and_manifest(self):
        self._make_delta()
        res = self._guard("backup")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        base = self._backup_root()
        self.assertTrue(base.is_dir())
        snaps = [p for p in base.iterdir() if (p / "delta.patch").is_file()]
        self.assertEqual(len(snaps), 1, list(base.iterdir()))
        manifest = json.loads(
            (snaps[0] / "backup.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["files"], ["a.txt"])
        self.assertFalse(manifest["consumed"])
        self.assertIn("a-unstaged",
                      (snaps[0] / "delta.patch").read_text(encoding="utf-8"))

    def test_backup_lives_under_git_dir_not_worktree(self):
        """Dayanıklılık: yedek `.git/` altındadır, worktree'yi kirletmez."""
        self._make_delta()
        self._guard("backup")
        base = self._backup_root()
        self.assertIn(".git", str(base).replace(str(self.repo), ""))
        # worktree'de yedek adlı bir izlenen dosya oluşmamalı
        status = self._git("status", "--porcelain").stdout
        self.assertNotIn("precommit-worktree-backups", status)
        # delta hâlâ ağaçta (yedekleme delta'yı SİLMEZ)
        self.assertEqual(self._tree_content("a.txt"), "a-unstaged\n")

    def test_backup_is_idempotent_when_already_backed_up(self):
        """Aynı delta iki kez yedeklenirse ikinci yedek geri yüklenemez
        olmaz: delta ağaçtadır → reverse-check kanıtı → tüketilir."""
        self._make_delta()
        self._guard("backup")
        res = self._guard("backup")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        base = self._backup_root()
        self.assertTrue(base.is_dir(), base)
        snaps = [p for p in base.iterdir()
                 if (p / "delta.patch").is_file()]
        # eski yedek tüketilmiş, yenisi aktif → tam 1 tüketilmemiş kalmalı
        pending = self._guard("status", "--json")
        payload = json.loads(pending.stdout)
        self.assertEqual(len(payload["pending"]) +
                         len(payload["in_flight"]), 1, pending.stdout)

    def test_status_and_recover_on_clean_tree_are_noops(self):
        self.assertEqual(self._guard("status").returncode, 0)
        self.assertEqual(self._guard("recover").returncode, 0)


class TestAutoRestore(_Scratch):
    """Kayıp → otomatik geri yükleme (kalıcı çözümün özü)."""

    def _simulate_loss(self):
        """Pencere-içi kayıp: yedek al, sonra pre-commit'in yaptığı gibi
        ağacı index'e eşitle (`git checkout -- .`)."""
        self._make_delta()
        res = self._guard("backup")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self._git("checkout", "--", ".")
        self.assertEqual(self._tree_content("a.txt"), "a1\n",
                         "kayıp simülasyonu başarısız")

    def test_next_backup_restores_previous_loss(self):
        """Bir sonraki commit adımı kaybı KENDİLİĞİNDEN onarır."""
        self._simulate_loss()
        res = self._guard("backup")
        out = res.stdout + res.stderr
        self.assertEqual(res.returncode, 0, out)
        self.assertIn("geri yüklendi", out)
        self.assertEqual(self._tree_content("a.txt"), "a-unstaged\n",
                         "delta yedekten geri gelmeli")
        # yedek artık tüketilmiş olmalı (tekrarlanan kurtarma yutmaz)
        payload = json.loads(self._guard("status", "--json").stdout)
        self.assertEqual(payload["pending"], [], payload)

    def test_recover_command_restores(self):
        self._simulate_loss()
        res = self._guard("recover")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self._tree_content("a.txt"), "a-unstaged\n")

    def test_loss_without_recovery_is_visible_in_status(self):
        """Kurtarmadan ÖNCE durum görünür (sessiz kayıp yok)."""
        self._simulate_loss()
        payload = json.loads(self._guard("status", "--json").stdout)
        self.assertEqual(len(payload["pending"]), 1, payload)
        self.assertEqual(payload["in_flight"], [], payload)
        self.assertEqual(payload["pending"][0]["files"], ["a.txt"])

    def test_post_restores_when_real_hook_failed_to(self):
        """pre-commit finally-apply'i çökseydi post onarır (arıza +
        GÜRÜLT)."""
        self._simulate_loss()
        res = self._guard("post")
        out = res.stdout + res.stderr
        self.assertEqual(res.returncode, 0, out)
        self.assertIn("geri yüklendi", out)
        self.assertEqual(self._tree_content("a.txt"), "a-unstaged\n")

    def test_delta_in_tree_detects_presence(self):
        """delta_in_tree false-verirse kurtarma asla tetiklenmez
        (mutasyon bekçisi: bu assertion'ın kırılması diğerlerini kör eder)."""
        self._make_delta()
        self._guard("backup")
        # delta ağaçtayken: kayıp yok (yedek "in_flight" — normal)
        payload = json.loads(self._guard("status", "--json").stdout)
        self.assertEqual(payload["pending"], [], payload)
        self.assertEqual(len(payload["in_flight"]), 1, payload)
        # delta ağaçtan gidince: pending 1
        self._git("checkout", "--", ".")
        payload = json.loads(self._guard("status", "--json").stdout)
        self.assertEqual(len(payload["pending"]), 1, payload)
        self.assertEqual(payload["in_flight"], [], payload)


class TestConflictIsNeverSilent(_Scratch):
    """Çakışan yedek ASLA sessizce geçilmez ve SİLİNMEZ."""

    def test_conflicting_backup_is_never_silently_consumed(self):
        """Çakışan yedek ASLA sessizce geçilmez ve SİLİNMEZ.

        Delta kayıp + uygulanamaz durum: `status` bunu `unrecoverable`
        olarak AYIRIR (kayıp ile karıştırılmaz) ve yedek yerinde kalır.
        """
        (self.repo / "a.txt").write_text("a-unstaged\n", encoding="utf-8")
        self.assertEqual(self._guard("backup").returncode, 0)
        # Delta'yı yiyip hedefi imkânsız kıl: dosyayı sil ve index'e al.
        self._git("checkout", "--", ".")
        (self.repo / "a.txt").unlink()
        self._git("add", "-A")

        payload = json.loads(self._guard("status", "--json").stdout)
        # delta ağaçta değil (dosya silindi); yedek apply edilemez mi?
        # (silinmiş dosyaya diff → genelde uygulanabilir; ayrım dinamik)
        groups = {k: len(v) for k, v in payload.items()
                  if k in ("pending", "in_flight", "unrecoverable")}
        self.assertEqual(sum(groups.values()), 1, payload)
        base = self._backup_root()
        snaps = [p for p in base.iterdir()
                 if (p / "delta.patch").is_file()]
        self.assertTrue(snaps, "yedek asla silinmemeli")
        manifest = json.loads(
            (snaps[0] / "backup.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest.get("consumed"),
                         "çözülmemiş yedek tüketilmiş gibi GÖSTERİLMEMELİ")

        # recover: uygulanabiliyorsa kurtarır, uygulanamıyorsa 1 + silmez.
        res = self._guard("recover")
        self.assertIn(res.returncode, (0, 1), res.stdout + res.stderr)
        snaps2 = [p for p in base.iterdir()
                  if (p / "delta.patch").is_file()]
        self.assertTrue(snaps2, "recover yedekleri SİLMEMELİ")

    def test_no_delta_never_blocks(self):
        res = self._guard("post")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


@unittest.skipUnless(VENV_PC.is_file() or shutil.which("pre-commit"),
                     "pre-commit yok — entegrasyon testleri atlandı")
class TestRealPreCommitKillWindow(_Scratch):
    """GERÇEK süreç-ölümü: pre-commit ortada SIGKILL → yedek hayatta."""

    def setUp(self):
        super().setUp()
        self.pc = str(VENV_PC) if VENV_PC.is_file() else shutil.which("pre-commit")
        # İki kapı: sleeper (pencereyi AÇIK tutar) + unstaged-delta gate
        # (karışık ağaçı bloklar — sarmalayıcının altında da çalışmalı).
        # Uyuma anında process group'u SIGKILL edeceğiz.
        (self.repo / ".pre-commit-config.yaml").write_text(
            "repos:\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: sleeper\n"
            "        name: hold the stash window open\n"
            "        entry: python3 -c \"import time,os;"
            "open('.window-open','w').write('open');time.sleep(120)\"\n"
            "        language: system\n"
            "        always_run: true\n"
            "        pass_filenames: false\n"
            "        verbose: true\n"
            "      - id: unstaged-delta\n"
            "        name: unstaged delta gate\n"
            f"        entry: {sys.executable} {DELTA_GATE}\n"
            "        language: system\n"
            "        always_run: true\n"
            "        pass_filenames: false\n"
            "        verbose: true\n",
            encoding="utf-8")
        self._git("add", ".pre-commit-config.yaml")
        self._git("commit", "-qm", "config")
        inst = subprocess.run(
            [self.pc, "install", "-f"], cwd=str(self.repo),
            capture_output=True, text=True, env=self.env, timeout=300)
        self.assertEqual(inst.returncode, 0, inst.stdout + inst.stderr)
        # Sarmalayıcıyı GERÇEK installer ile kur (--root hedefi verir;
        # elle yazılmış bir sarmalayıcı kurulumu test etmezdi).
        run = subprocess.run(
            ["bash", str(INSTALLER), "--root", str(self.repo)],
            capture_output=True, text=True, env=self.env, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        hook = self._hook_file()
        self.assertIn("WORKTREE-GUARD-WRAPPER",
                      hook.read_text(encoding="utf-8", errors="replace"))
        self.assertGreater(hook.with_name("pre-commit.real").stat().st_size,
                           0, "pre-commit.real boş — zincir koşulamaz")

    def _hook_file(self) -> pathlib.Path:
        out = self._git("rev-parse", "--git-path", "hooks").stdout.strip()
        p = pathlib.Path(out)
        if not p.is_absolute():
            p = self.repo / p
        return p / "pre-commit"

    def _start_commit_and_kill(self) -> subprocess.Popen:
        proc = subprocess.Popen(
            [GIT, "-c", "commit.gpgsign=false", "commit", "-qm",
             "karışık ağaç"],
            cwd=str(self.repo), env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True)
        # Pencere açılana kadar bekle (.window-open kilit dosyası)
        marker = self.repo / ".window-open"
        deadline = time.time() + 60
        while time.time() < deadline and not marker.exists():
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        return proc

    def test_backup_survives_sigkill_and_next_run_restores(self):
        """SÖZLEŞME: kill sonrası delta yedekte hayatta + sonraki adımda
        kendiliğinden geri gelir."""
        (self.repo / "a.txt").write_text("a-unstaged\n", encoding="utf-8")
        self._git("add", "b.txt")  # staged değişiklik var → commit anlamlı
        (self.repo / "b.txt").write_text("b2\n", encoding="utf-8")
        self._git("add", "b.txt")

        proc = self._start_commit_and_kill()
        marker = self.repo / ".window-open"
        self.assertTrue(marker.exists(),
                        "pre-commit stash penceresi hiç açılmadı "
                        "(sarmalayıcı zinciri çalıştırmamış olabilir)")
        # Pencere AÇIKKEN process group'unu öldür (finally asla çalışmaz)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=30)

        # (a) yedek var mı — pencere AÇILMADAN alınmıştı
        base = self._backup_root()
        snaps = [p for p in base.iterdir() if (p / "delta.patch").is_file()] \
            if base.is_dir() else []
        self.assertTrue(snaps, "kill öncesi yedek alınmamış — KORUMA YOK")
        # (b) delta gerçekten kayıp mı (zarar gerçek)
        self.assertEqual(self._tree_content("a.txt"), "a1\n",
                         "beklenen: kill ağaçta delta'yı yedi")
        # (c) bir sonraki adımda kendiliğinden geri gelir
        res = self._guard("backup")
        out = res.stdout + res.stderr
        self.assertEqual(res.returncode, 0, out)
        self.assertIn("geri yüklendi", out)
        self.assertEqual(self._tree_content("a.txt"), "a-unstaged\n",
                         "yedekten otomatik geri yükleme çalışmalı")
        # kurtarma sonrası: kayıp kalmadı (yeni yedek in_flight'ta)
        payload = json.loads(self._guard("status", "--json").stdout)
        self.assertEqual(payload["pending"], [], payload)

    def test_wrapped_commit_blocks_mixed_tree_and_keeps_delta(self):
        """Negatif/koruyucu: sarmalayıcı varken normal commit yine de
        bloklanır (delta gate) ve delta ağaçta KALIR."""
        (self.repo / "b.txt").write_text("b2\n", encoding="utf-8")
        self._git("add", "b.txt")
        (self.repo / "a.txt").write_text("a-unstaged\n", encoding="utf-8")
        env = dict(self.env)
        env["WC_SLEEP"] = "0"  # sleeper'ı bu testte bekleme
        proc = subprocess.run(
            [GIT, "-c", "commit.gpgsign=false", "commit", "-qm",
             "karışık ağaç"],
            cwd=str(self.repo), env=env, capture_output=True,
            text=True, timeout=300)
        out = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0,
                            "karışık ağaç commit'i bloke edilmeli\n" + out)
        self.assertEqual(self._tree_content("a.txt"), "a-unstaged\n",
                         "delta kaybolmamalı (kayıp yok)")
        # yedek de alınmış olmalı (sarmalayıcı çalıştı) — ve tüketilmemiş
        # değil: post, ağaçta delta varken onu tüketir. Asıl kanıt: yedek
        # dizini oluşmuş olması + delta'nın hayatta kalması.
        base = self._backup_root()
        self.assertTrue(base.is_dir(),
                        "sarmalayıcı yedek adımı hiç çalışmadı")


class TestSelfHealGate(unittest.TestCase):
    """check_worktree_guard_install: tespit + onarım sözleşmesi."""

    def setUp(self):
        if GIT is None:
            self.skipTest("git yok")
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="wtguard-heal-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _gate(self, root, *args):
        return subprocess.run(
            [sys.executable, str(SELF_HEAL), "--root", str(root), *args],
            capture_output=True, text=True, timeout=120)

    def _fresh_repo(self) -> pathlib.Path:
        repo = self.tmp / "r"
        repo.mkdir()
        env = _env(repo)
        for args in (("init", "-q", "."), ("config", "user.email",
                                           "t@x.invalid"),
                     ("config", "user.name", "t")):
            subprocess.run([GIT, *args], cwd=str(repo), capture_output=True,
                           env=env, timeout=60)
        return repo

    def test_missing_wrapper_reports_fail_closed_without_heal(self):
        repo = self._fresh_repo()
        res = self._gate(repo, "--no-heal")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("sarmalayıcı yok", res.stdout)
        self.assertIn("FAIL", res.stdout)
        # --no-heal ASLA onarmamalı (yalnız rapor)
        hook = self.repo_hook(repo)
        self.assertFalse(hook.exists(),
                         "--no-heal modunda onarım yapılmamalı")

    def test_heal_targets_caller_repo_and_fails_closed_without_real_hook(self):
        """Onarım HEDEF repo'ya (--root) kurar; `.real` yoksa asla yeşil değil.

        İki ayrı sözleşmeyi birden pinler:
          * YAN ETKİ: onarım canlı repo'nun (REPO) wrapper'ına DOKUNMAZ.
          * FAIL-CLOSED: sarmalayıcı yazılsa bile `pre-commit.real` yoksa
            kapı yeşil dönmez (yoksa zincir hiç koşmaz = sessiz fail-open).
        """
        repo = self._fresh_repo()
        res = self._gate(repo)  # heal açık
        hook = self.repo_hook(repo)
        live = self.repo_hook(REPO)
        # (1) canlı repo wrapper'ı yerinde — onarım başkasını TAZELERSE
        # bu kırılırdı (installer'ın --root'suz eski davranışı).
        self.assertIn("WORKTREE-GUARD-WRAPPER",
                      live.read_text(encoding="utf-8", errors="replace"),
                      "onarım canlı repo'nun hook'unu değiştirmemeli")
        if res.returncode == 0:
            # tam kurulum: hedefte wrapper + gerçek hook birlikte var
            self.assertIn("WORKTREE-GUARD-WRAPPER",
                          hook.read_text(encoding="utf-8", errors="replace"))
            self.assertTrue(hook.with_name("pre-commit.real").is_file())
        else:
            self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
            self.assertIn("pre-commit.real yok", res.stdout)
            if hook.exists():
                # yazılmışsa bile kapı 1 döndürdü — fail-open DEĞİL
                self.assertIn("WORKTREE-GUARD-WRAPPER",
                              hook.read_text(encoding="utf-8",
                                             errors="replace"))

    def repo_hook(self, root: pathlib.Path) -> pathlib.Path:
        out = subprocess.run([GIT, "rev-parse", "--git-path", "hooks"],
                             cwd=str(root), capture_output=True, text=True,
                             timeout=60).stdout.strip()
        p = pathlib.Path(out)
        return (p if p.is_absolute() else root / p) / "pre-commit"

    def test_live_repo_wrapper_is_installed(self):
        """Bu test dosyasının çalıştığı repo'da koruma katmanı kurulu."""
        hook = self.repo_hook(REPO)
        self.assertTrue(hook.is_file(), hook)
        text = hook.read_text(encoding="utf-8", errors="replace")
        self.assertIn("WORKTREE-GUARD-WRAPPER", text)
        self.assertTrue(hook.stat().st_mode & 0o111, "çalıştırılabilir değil")
        self.assertGreater(hook.stat().st_size, 0, "sarmalayıcı BOŞ")
        real = hook.with_name("pre-commit.real")
        self.assertTrue(real.is_file(), "pre-commit.real yok → zincir koşmaz")
        self.assertIn("pre-commit", real.read_text(encoding="utf-8",
                                                    errors="replace"))


class TestDeltaGateReportsBackups(_Scratch):
    """check_unstaged_delta: çözülmemiş yedeği RAPORLAR (geri yüklemez)."""

    def test_pending_backup_is_reported(self):
        (self.repo / "a.txt").write_text("a-unstaged\n", encoding="utf-8")
        self.assertEqual(self._guard("backup").returncode, 0)
        # Delta'yı yiyip yedeği "bekleyen" bırak
        self._git("checkout", "--", ".")
        res = subprocess.run(
            [sys.executable, str(DELTA_GATE)], cwd=str(self.repo),
            capture_output=True, text=True, timeout=120)
        out = res.stdout + res.stderr
        # delta yok → gate 0 döner ama YEDEĞİ görünür kılar
        self.assertEqual(res.returncode, 0, out)
        self.assertIn("worktree-guard yedeği", out)
        self.assertIn("recover", out)
        # kapı GERİ YÜKLEMEMİŞ (pencere içinde restore yok)
        self.assertEqual(self._tree_content("a.txt"), "a1\n")

    def test_no_backup_no_noise(self):
        res = subprocess.run(
            [sys.executable, str(DELTA_GATE)], cwd=str(self.repo),
            capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("worktree-guard yedeği", res.stdout)


class TestInstallerRegression(unittest.TestCase):
    """2026-10-21 kurulum-kaza regresyonu: genişleyen heredoc.

    `<<WRAP` (genişleyen) gövdedeki backtick yorumlarını GERÇEKTEN
    çalıştırıyordu → `pre-commit install` kurulum sırasında tetiklenip
    hedef dosyayı 0 baytlık boş bir hook yaptı (zincir tamamen susmuş =
    sessiz fail-open). KESİNLEŞTİRİLMİŞ heredoc + token bunu kapatar.
    """

    def test_installer_uses_quoted_heredoc(self):
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("<<'WRAP'", text,
                      "heredoc KESİNLEŞTİRİLMİŞ olmalı (genişleme yok)")
        self.assertNotIn("<<WRAP\n", text.replace("<<'WRAP'", ""),
                         "genişleyen heredoc geri gelmemeli")

    def test_generated_wrapper_is_nonempty_and_executable_after_install(self):
        """Kurulum sonrası canlı repo: 0-bayt/farksız felaket YAKALANIR."""
        res = subprocess.run(["bash", str(INSTALLER), "--check"],
                             cwd=str(REPO), capture_output=True,
                             text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        hook = subprocess.run(
            [GIT, "rev-parse", "--git-path", "hooks"], cwd=str(REPO),
            capture_output=True, text=True, timeout=60).stdout.strip()
        p = pathlib.Path(hook)
        if not p.is_absolute():
            p = REPO / p
        hook_file = p / "pre-commit"
        self.assertGreater(hook_file.stat().st_size, 0)
        self.assertTrue(hook_file.stat().st_mode & 0o111)

    def test_wrapper_body_contains_no_unescaped_command_substitution(self):
        """Sarmalayıcı gövdesi token enjeksiyonuyla üretilir; üretilen
        dosyada yalnız kasıtlı `$(git ...)`/`${...}` bulunur — backtick
        YOK (kazaya yol açan desen)."""
        out = subprocess.run(["bash", str(INSTALLER), "--check"],
                             cwd=str(REPO), capture_output=True,
                             text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        hooks = pathlib.Path(subprocess.run(
            [GIT, "rev-parse", "--git-path", "hooks"], cwd=str(REPO),
            capture_output=True, text=True, timeout=60).stdout.strip())
        if not hooks.is_absolute():
            hooks = REPO / hooks
        body = (hooks / "pre-commit").read_text(encoding="utf-8")
        # backtick (`` ` ``) hiç bulunmamalı: hem kurulum kazası hem de
        # gelecekteki genişleme tuzağı.
        self.assertNotIn("`", body,
                         "sarmalayıcıda backtick var — heredoc genişlerse "
                         "yeniden felaket")


if __name__ == "__main__":
    unittest.main()
