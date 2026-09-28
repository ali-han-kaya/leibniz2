#!/usr/bin/env python3
"""check_unstaged_delta.py — unstaged izlenen delta varken commit'i BLOKE eden kapı.

KURAL (findings.md / AGENTS.md): kapılar YALNIZ stage'li ağaç üzerinde
ölçüm yapmalıdır. Karışık ağaç (staged + unstaged) iki şeyi birden bozar:
  1) sonuç yanıltıcıdır — batarya doğrudan koşumda 14/14 verirken
     pre-commit içinde düşer (ölçüldü, 2026-09-19),
  2) pre-commit unstaged deltayı `patch<epoch>-<pid>` dosyasına stash'ler,
     `git checkout -- .` yapar ve yalnız finally'de `git apply` ile geri
     koyar. Pencere-içi süreç-ölümü → ağaç sessizce revert olur, delta
     yalnız patch dosyasında kalır (revert-olayı 2026-09-18; kurtarma
     kapısı: check_precommit_orphans.py).

NEDEN `git diff` TEK BAŞINA YETMEZ (ölçüldü, pre-commit 4.3.0):
`pre_commit/commands/run.py` → `stash = not args.all_files and not args.files`.
Gerçek `git commit` sırasında stash AÇIKTIR: kapı çalışırken ağaç index'e
eşitlenmiştir, `git diff --name-only` BOŞ döner — saf `git diff` kontrolü
karışık ağaçta sessizce PASS verir (ölçüldü: commit geçti). Bu yüzden sinyal
iki kaynaktan TOPLANIR:
  (a) `git diff --name-only` — stash'siz koşumlarda (manuel `--all-files` /
      `--files`, pre-commit dışı çağrı) gerçek deltayı verir;
  (b) bu koşumun stash patch'i — `patch<epoch>-<pid>`; <pid> pre-commit
      sürecidir ve kapının ATA zincirindedir. Patch YALNIZ unstaged delta
      varsa yazılır (`_unstaged_changes_cleared`: retcode 0 → erken dönüş).
Yetim patch'ler (ölmüş koşumlardan) aynı dizinde birikir ve pre-commit
onları ASLA silmez → ada göre değil ATA pid'e göre eşleştirilir; yabancı
pid'li patch'ler yok sayılır (yanlış-pozitif üretmez).

KAPSAM: yalnız İZLENEN (tracked) dosyalar. Untracked dosyalar stash'e girmez
ve bu kapının konusu değildir ("unstaged tracked changes").

Çıkış: 0 = temiz (unstaged izlenen delta yok), 1 = delta var (fail-closed),
2 = kullanım hatası. OFFLINE, stdlib-only, ~0.05s + ata-zinciri için birkaç
`ps` çağrısı.
"""
import os
import pathlib
import subprocess
import sys
from typing import List, Optional

PATCH_PREFIX = "patch"


def cache_dir() -> pathlib.Path:
    """pre-commit'in kendi override'ı varsa o, yoksa varsayılan cache."""
    home = os.environ.get("PRE_COMMIT_HOME")
    return pathlib.Path(home) if home else pathlib.Path.home() / ".cache" / "pre-commit"


def ancestor_pids() -> List[int]:
    """Bu sürecin ATA pid'leri (kendisi hariç), en yakın önce.

    pre-commit kapıları kendi süreçlerinden spawn ettiği için stash
    patch'inin adındaki pid zincirde bulunur.
    """
    pids: List[int] = []
    pid = os.getppid()
    seen = set()
    while pid and pid > 1 and pid not in seen:
        seen.add(pid)
        pids.append(pid)
        try:
            out = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(pid)],
                capture_output=True, text=True, check=False,
            ).stdout.strip()
        except OSError:
            break
        pid = int(out) if out.isdigit() else 0
    return pids


def stash_patch() -> Optional[pathlib.Path]:
    """Bu koşumun stash patch'i; yabancı (yetim) patch'ler eşleşmez."""
    base = cache_dir()
    if not base.is_dir():
        return None
    for pid in ancestor_pids():
        for candidate in sorted(base.glob(f"{PATCH_PREFIX}*-{pid}")):
            if candidate.is_file():
                return candidate
    return None


def patch_paths(patch: pathlib.Path) -> List[str]:
    """Patch'teki dosya yolları (`diff --git a/X b/Y` başlıklarından)."""
    try:
        text = patch.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    paths: List[str] = []
    for line in text.splitlines():
        if not line.startswith("diff --git "):
            continue
        head = line[len("diff --git "):].strip()
        left = head.split(" b/", 1)[0].strip().strip('"')
        if left.startswith("a/"):
            left = left[2:]
        if left and left not in paths:
            paths.append(left)
    return paths


def worktree_delta() -> List[str]:
    """`git diff --name-only` (worktree ↔ index): stash'siz koşumlarda gerçek delta."""
    try:
        res = subprocess.run(
            ["git", "diff", "--name-only"], capture_output=True, text=True,
            check=False,
        )
    except OSError:
        return []
    if res.returncode != 0:
        return []
    return [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print("check_unstaged_delta.py — unstaged izlenen delta varken commit'i bloke eder")
        print("kullanım: check_unstaged_delta.py   (bayrak yok)")
        return 0
    if args:
        print(f"kullanım hatası: bilinmeyen argüman: {' '.join(args)}", file=sys.stderr)
        return 2

    files: List[str] = []
    signals: List[str] = []

    visible = worktree_delta()
    if visible:
        files.extend(visible)
        signals.append("git diff --name-only")

    patch = stash_patch()
    if patch is not None:
        signals.append(f"stash patch {patch.name}")
        for rel in patch_paths(patch):
            if rel not in files:
                files.append(rel)

    if not files:
        print("OK — çalışma ağacı temiz: unstaged izlenen değişiklik yok")
        return 0

    print("COMMIT BLOKE — unstaged izlenen dosya değişikliği var (ağaç KİRLİ).")
    print("  bekleyen dosyalar:")
    for rel in files:
        print(f"    {rel}")
    print(f"  sinyal: {', '.join(signals)}")
    print(
        "\nNeden fail-closed: pre-commit unstaged deltayı `patch<epoch>-<pid>`\n"
        "dosyasına stash'ler, `git checkout -- .` yapar ve yalnız finally'de\n"
        "`git apply` ile geri koyar. Pencere-içi süreç-ölümü = sessiz revert\n"
        "(kurtarma yalnız patch'te kalır); ayrıca kapılar karışık ağaçta\n"
        "yanıltıcı sonuç üretir.\n"
        "\nÇözüm:\n"
        "  git add <dosyalar>                 # bu commit'e dahil et\n"
        "  ya da\n"
        "  git stash push -m wip <dosyalar>   # ayrı tut, sonra geri al\n"
        "sonra commit'i yeniden dene."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
