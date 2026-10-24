#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_worktree_guard_install.py — worktree-guard sarmalayıcısı kurulu mu? (self-heal).

NEDEN: pre-commit'in unstaged-delta stash penceresine dayanıklı yedek/geri-
yükleme katmanı, `.git/hooks/pre-commit` sarmalayıcısında yaşar
(`install_worktree_guard.sh` kurar, `precommit_worktree_guard.py` işi yapar).
AMA `pre-commit install` her çalıştığında o sarmalayıcıyı SİLER: pre-commit
kendi hash'ini görmediği mevcut hook'u `.legacy`'e taşıyıp kendi script'ini
yazar. Sessiz kayıp bu yüzden mümkün: kurulum tazelendikçe koruma katmanı
kaybolur ve kimse fark etmez.

Bu kapı (auto-sync deseni — update-config / check-changelog-sync gibi):
* Sarmalayıcı yoksa VEYA `precommit_worktree_guard.py` yoksa → ONARIR
  (installer'ı çalıştırır) ve GÜRÜLTÜLÜ raporlar; commit'i engellemez
  çünkü onarım sonraki commit'ten itibaren koruma sağlar (bu commit'in
  stash'i çoktan açılmıştır — kapı iç-halkada olduğu için o pencereyi
  kapatamaz; bu sınır çıktıda AÇIKÇA yazılır).
* Onaramazsa (installer rc!=0 / hook dizini yazılamıyor) → exit 1
  (fail-closed: koruma katmanı olmadan commit sürüklenmesin).
* `.real` yoksa (pre-commit install henüz koşmadı ya da taşınma yarım
  kalmışsa) aynı onarım yolundan geçilir; yine de yoksa exit 1 —
  sarmalayıcı varken gerçek hook yoksa kapılar HİÇ KOŞMAZ (sessiz
  fail-open), o yüzden bu durum asla yeşil sayılmaz.

Sözleşme: yalnız `.git/hooks/` altına dokunur; worktree'ye YAZMAZ.
Çıkış: 0 = kurulu ya da onarıldı, 1 = onarılamadı (fail-closed),
2 = kullanım hatası.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
from typing import List, Optional

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
INSTALLER = HERE / "install_worktree_guard.sh"
GUARD_PY = HERE / "precommit_worktree_guard.py"
MARKER = "WORKTREE-GUARD-WRAPPER"


def _git(args: List[str], root: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root),
                          capture_output=True, text=True)


def hook_path(root: pathlib.Path) -> Optional[pathlib.Path]:
    proc = _git(["rev-parse", "--git-path", "hooks"], root)
    if proc.returncode != 0:
        return None
    raw = proc.stdout.strip()
    if not raw:
        return None
    path = pathlib.Path(raw)
    if not path.is_absolute():
        path = root / path
    return path / "pre-commit"


def state(root: pathlib.Path) -> dict:
    """Koruma katmanının gerçek durumu (dosyalara bakar, iddia kurmaz)."""
    hook = hook_path(root)
    if hook is None:
        return {"ok": False, "reason": "hooks-diziği çözülemedi",
                "hook": None, "wrapper": False, "guard_py": GUARD_PY.is_file(),
                "real": False}
    wrapper = hook.is_file() and MARKER in hook.read_text(
        encoding="utf-8", errors="replace")
    real = hook.with_name("pre-commit.real").is_file()
    guard_py = GUARD_PY.is_file()
    installer = INSTALLER.is_file()
    ok = bool(wrapper and real and guard_py and installer)
    reason = None
    if not guard_py:
        reason = "precommit_worktree_guard.py yok"
    elif not installer:
        reason = "install_worktree_guard.sh yok"
    elif not wrapper:
        reason = "sarmalayıcı yok (pre-commit install silmiş olabilir)"
    elif not real:
        reason = ("pre-commit.real yok — sarmalayıcı var ama zincir "
                  "KOŞMAZ (sessiz fail-open)")
    return {"ok": ok, "reason": reason, "hook": str(hook),
            "wrapper": wrapper, "guard_py": guard_py, "real": real,
            "installer": installer}


def heal(root: pathlib.Path) -> subprocess.CompletedProcess:
    # `--root` ZORUNLU: installer kendi dosya konumundan kök çıkarır; onarım
    # çağırana değil HEDEFE yazmalıdır (aksi halde scratch/worktree testi
    # sessizce gerçek reponun hook'unu tazeler — yan etki, onarım değil).
    return subprocess.run(
        ["bash", str(INSTALLER), "--root", str(root)], cwd=str(root),
        capture_output=True, text=True)


def run(root: pathlib.Path, do_heal: bool = True) -> tuple:
    """(rc, report). rc 0 = kurulu/onarıldı, 1 = fail-closed, 2 = ölçüm yok."""
    report = state(root)
    report["healed"] = False
    report["heal_output"] = ""
    if report["ok"]:
        return 0, report
    if not do_heal:
        return 1, report
    if not INSTALLER.is_file() or not GUARD_PY.is_file():
        # Onarım dosyalarının kendisi yok — çalıştırılamaz, raporla.
        return 1, report
    proc = heal(root)
    report["heal_output"] = (proc.stdout + proc.stderr).strip()
    after = state(root)
    report.update({k: after[k] for k in
                   ("ok", "reason", "wrapper", "real", "hook")})
    report["healed"] = proc.returncode == 0 and after["ok"]
    if report["healed"]:
        return 0, report
    return 1, report


def render(report: dict) -> List[str]:
    lines = ["WORKTREE-GUARD KURULUM KAPISI (self-heal)"]
    if report.get("hook"):
        lines.append("  hook   : %s" % report["hook"])
    lines.append("  sarmalayıcı: %s · guard.py: %s · pre-commit.real: %s"
                 % ("VAR" if report.get("wrapper") else "YOK",
                    "VAR" if report.get("guard_py") else "YOK",
                    "VAR" if report.get("real") else "YOK"))
    if report.get("ok"):
        lines.append("PASS: koruma katmanı kurulu (yedek + geri-yükleme aktif)")
        return lines
    if report.get("healed"):
        lines.append("ONARILDI: sarmalayıcı yeniden kuruldu — SONRAKİ commit'ten")
        lines.append("  itibaren unstaged-delta yedekleme/geri-yükleme aktif.")
        lines.append("  NOT: bu commit'in stash penceresi çoktan açıldı; kapı")
        lines.append("  iç-halkada olduğu için o pencereyi kapatamaz.")
        if report.get("heal_output"):
            lines.extend("  %s" % ln for ln in report["heal_output"].splitlines())
        return lines
    lines.append("FAIL: koruma katmanı kurulamadı — %s"
                 % (report.get("reason") or "bilinmeyen"))
    if report.get("heal_output"):
        lines.extend("  %s" % ln for ln in report["heal_output"].splitlines())
    lines.append("  çözüm: bash _calisma/CIKTI/install_worktree_guard.sh")
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="worktree-guard sarmalayıcısı kurulu mu? (yoksa onarır)")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--no-heal", action="store_true",
                        help="onarma yalnız raporla (fail-closed)")
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print("HATA: --root dizin değil: %s" % root, file=sys.stderr)
        return 2
    rc, report = run(root, do_heal=not args.no_heal)
    for line in render(report):
        print(line)
    return rc


if __name__ == "__main__":
    sys.exit(main())
