#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""precommit_patch_recover.py — pre-commit'in bıraktığı `patch*` dosyalarını
OKU, özetle ve (istenirse) dosya dosya ağaca geri uygula.

NEDEN
-----
`pre-commit` commit sırasında unstaged İZLENEN değişiklikleri
`~/.cache/pre-commit/patch<epoch>-<pid>` dosyasına stash'ler ve `finally`
içinde geri uygular. Süreç pencerede öldürülürse (SIGKILL, araç timeout'u)
patch cache'te KALIR, ağaç ise yarı-stash durumda kalabilir. Bu depoda üç kez
ölçüldü (2026-09/10 olayları; `~/.cache/pre-commit/orphans-archive-20261003`).

`check_precommit_orphans.py` bu kalıntıyı TESPİT eder ve çözümünü söyler;
`precommit_worktree_guard.py backup|restore` pencereyi SIGKILL'e dayanıklı
yapar. Eksik olan üçüncü adımdı: **patch'in içinde ne var, ağaçta hangisi
zaten var, hangisini geri alabilirim?** Bu yardımcı tam onu yapar:

  --list     (varsayılan) her patch için dosya listesi + satır sayıları +
             ağaçtaki durum (`zaten var` / `uygulanabilir` / `çakışma`)
  --diff     seçilen patch'in diff'i (--include ile süzülebilir)
  --restore  seçilen patch'i ağaca uygula (--include ile DOSYA DOSYA,
             --dry-run ile yazmadan sınama)

KANIT (neden ikinci bir kanıt katmanı gerekir)
----------------------------------------------
Bir dosyanın ağaçta olup olmadığı `git apply --reverse --check` ile
ÖLÇÜLÜR (patch'in sonrası durum ↔ ağaç). Uygulanabilirlik ise
`git apply --check`. İkisi de temiz değilse "çakışma" denir ve YAZILMAZ —
tahminle geri yükleme yapılmaz. Bu, AGENTS.md'deki "patch'leri silmeden önce
içeriği ters-uygulama ile doğrula" kuralının araç hâlidir.

GÜVENLİK SINIRLARI
------------------
* READ-ONLY varsayılan: `--list`/`--diff` hiçbir şeye yazmaz, patch'leri
  SİLMEZ, stage etmez.
* `--restore` yalnız çalışma ağacına yazar (`git apply`, `--index` YOK);
  `--dry-run` ile önce sınanır.
* Patch bozuk/boşsa ya da çalışma dizini bir git deposu değilse exit 2
  (sessiz "başarı" yok). Çakışan dosya varsa exit 1; uygulananlar raporlanır.
* `--include` verilmezse TÜM dosyalar seçilir; verilirse yalnız eşleşenler.

Kullanım
--------
  python3 _calisma/CIKTI/precommit_patch_recover.py
  python3 _calisma/CIKTI/precommit_patch_recover.py --dir ~/.cache/pre-commit/orphans-archive-20261003
  python3 _calisma/CIKTI/precommit_patch_recover.py --diff patch1790688666-52869 --include verify.yml
  python3 _calisma/CIKTI/precommit_patch_recover.py --restore patch1790688666-52869 \
      --include check_unit_tests.list,Dockerfile --dry-run
  python3 _calisma/CIKTI/precommit_patch_recover.py --list --json

`--include` tekrarlanabilir ya da virgülle ayrılabilir; desenler `fnmatch`
ile dosya yoluna ve dosya ADINA uygulanır (`verify.yml`, `*/SKILL.md` gibi).

Exit: 0 = liste/diff tamam ya da geri yükleme temiz; 1 = en az bir dosya
çakıştı/uygulanamadı; 2 = kullanım ya da ölçüm hatası (depo değil, patch yok
seçimi belirsiz, git yok).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_DIR = pathlib.Path(os.path.expanduser("~/.cache/pre-commit"))
PATCH_GLOB = "patch*"
# `check_precommit_orphans.py` ile aynı pencere: bu yaştan sonra kalıntı
# "bilinen olay" sınıfına girer (uyarı, engel değil).
STALE_HOURS = 7 * 24

STATE_ALREADY = "zaten-var"
STATE_APPLIES = "uygulanabilir"
STATE_CONFLICT = "cakisma"

KIND_MARKS = {
    "added": "A",
    "deleted": "D",
    "renamed": "R",
    "binary": "B",
    "modified": "M",
}


class RecoveryError(RuntimeError):
    """Ölçüm imkânsız / kullanım hatası (exit 2)."""


@dataclass
class PatchFile:
    path: str
    status: str          # added | deleted | renamed | binary | modified
    added: int
    deleted: int
    state: str           # zaten-var | uygulanabilir | cakisma
    section: str = field(repr=False, default="")

    @property
    def mark(self) -> str:
        return KIND_MARKS.get(self.status, "?")

    def as_dict(self) -> dict:
        return {"path": self.path, "status": self.status,
                "added": self.added, "deleted": self.deleted,
                "state": self.state, "mark": self.mark}


@dataclass
class Patch:
    name: str
    path: pathlib.Path
    size: int
    mtime: float
    sha256: str
    files: List[PatchFile] = field(default_factory=list)

    @property
    def age_hours(self) -> float:
        return max(0.0, (time.time() - self.mtime) / 3600.0)

    @property
    def stale(self) -> bool:
        return self.age_hours > STALE_HOURS

    def as_dict(self) -> dict:
        return {"name": self.name, "path": str(self.path), "size": self.size,
                "mtime": self.mtime, "age_hours": round(self.age_hours, 1),
                "sha256": self.sha256, "stale": self.stale,
                "files": [f.as_dict() for f in self.files]}


# ── git yardımcıları ────────────────────────────────────────────────────────
def _git(args: Sequence[str], cwd: Optional[pathlib.Path] = None,
         input_text: Optional[str] = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=None if cwd is None else str(cwd),
                              input=input_text, capture_output=True, text=True,
                              timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        raise RecoveryError("git çalıştırılamadı: %s" % exc) from exc


def repo_root(explicit: Optional[str]) -> pathlib.Path:
    if explicit:
        root = pathlib.Path(explicit).expanduser().resolve()
        if not (root / ".git").exists():
            raise RecoveryError("verilen --root bir git deposu değil: %s" % root)
        return root
    proc = _git(["rev-parse", "--show-toplevel"])
    if proc.returncode != 0:
        raise RecoveryError("çalışma dizini bir git deposu değil "
                           "(git rev-parse başarısız)")
    return pathlib.Path(proc.stdout.strip()).resolve()


# ── patch ayrıştırma ────────────────────────────────────────────────────────
def split_sections(text: str) -> List[str]:
    """Patch'i dosya bölümlerine ayır (`diff --git` sınırından)."""
    sections: List[str] = []
    current: List[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current:
                sections.append("".join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        sections.append("".join(current))
    return sections


def _numstat(section: str) -> Tuple[int, int, str]:
    """Tek bölüm için (eklenen, silinen, yol) — `git apply --numstat -z -`."""
    proc = _git(["apply", "--numstat", "-z", "-"], input_text=section)
    if proc.returncode != 0:
        raise RecoveryError("patch bölümü ayrıştırılamadı: %s"
                           % (proc.stderr.strip().splitlines() or [""])[-1])
    # `-z` kayıtları NUL ile ayırır, alanları TAB ile: `eklenen\tsilinen\tyol`.
    records = [r for r in proc.stdout.split("\0") if r.strip()]
    if not records:
        raise RecoveryError("numstat boş döndü")
    parts = records[0].split("\t", 2)
    if len(parts) != 3:
        raise RecoveryError("numstat beklenen 3 alan vermedi: %r" % parts)
    added, deleted, path = parts
    return (int(added) if added.isdigit() else 0,
            int(deleted) if deleted.isdigit() else 0,
            path)


def _kind(section: str) -> str:
    if "GIT binary patch" in section or "Binary files " in section:
        return "binary"
    if "new file mode" in section:
        return "added"
    if "deleted file mode" in section:
        return "deleted"
    if "rename from " in section or "rename to " in section:
        return "renamed"
    return "modified"


def _file_state(root: pathlib.Path, section: str) -> str:
    """Ağaçtaki durum: zaten-var | uygulanabilir | cakisma (ikisi de değil).

    `git apply --reverse --check` yeni-dosya bölümünde de dogru cevap verir
    (ölçüldü: `git add -N` girişi varken içerik eşleşiyorsa temiz döner).
    """
    reverse = _git(["apply", "--reverse", "--check", "-"], cwd=root,
                   input_text=section)
    if reverse.returncode == 0:
        return STATE_ALREADY
    forward = _git(["apply", "--check", "-"], cwd=root,
                   input_text=section)
    if forward.returncode == 0:
        return STATE_APPLIES
    return STATE_CONFLICT


def parse_patch(path: pathlib.Path, root: pathlib.Path) -> Patch:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RecoveryError("patch okunamadı: %s (%s)" % (path, exc)) from exc
    text = data.decode("utf-8", errors="replace")
    sections = split_sections(text)
    if not sections:
        raise RecoveryError("patch içinde `diff --git` bölümü yok: %s" % path)
    files: List[PatchFile] = []
    for section in sections:
        added, deleted, rel = _numstat(section)
        files.append(PatchFile(path=rel, status=_kind(section), added=added,
                               deleted=deleted,
                               state=_file_state(root, section),
                               section=section))
    return Patch(name=path.name, path=path, size=len(data),
                 mtime=path.stat().st_mtime,
                 sha256=hashlib.sha256(data).hexdigest(), files=files)


def discover_patches(directory: pathlib.Path,
                     root: pathlib.Path) -> List[Patch]:
    if not directory.is_dir():
        raise RecoveryError("patch dizini yok: %s" % directory)
    patches: List[Patch] = []
    for path in sorted(directory.glob(PATCH_GLOB)):
        if not path.is_file():
            continue
        patches.append(parse_patch(path, root))
    return patches


# ── seçim ───────────────────────────────────────────────────────────────────
def parse_includes(values: Optional[Iterable[str]]) -> List[str]:
    patterns: List[str] = []
    for raw in values or ():
        for part in str(raw).split(","):
            part = part.strip()
            if part:
                patterns.append(part)
    return patterns


def matches(path: str, patterns: Sequence[str]) -> bool:
    if not patterns:
        return True
    base = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(base, pat)
               or path == pat for pat in patterns)


def select_files(patch: Patch, patterns: Sequence[str]) -> List[PatchFile]:
    selected = [f for f in patch.files if matches(f.path, patterns)]
    if patterns and not selected:
        raise RecoveryError(
            "patch %s içinde --include desenleriyle eşleşen dosya yok: %s\n"
            "  mevcut dosyalar: %s"
            % (patch.name, ", ".join(patterns),
               ", ".join(f.path for f in patch.files)))
    return selected


def pick_patch(patches: List[Patch], name: str, directory: pathlib.Path,
               root: pathlib.Path) -> Patch:
    wanted = name.strip()
    for patch in patches:
        if patch.name == wanted:
            return patch
    candidate = pathlib.Path(wanted).expanduser()
    if candidate.is_file():
        return parse_patch(candidate, root)
    if not wanted:
        raise RecoveryError("patch adı boş")
    raise RecoveryError("patch bulunamadı: %s (dizin: %s)" % (wanted, directory))


# ── geri yükleme ────────────────────────────────────────────────────────────
def restore(root: pathlib.Path, patch: Patch, files: List[PatchFile],
            dry_run: bool) -> int:
    """Seçilen dosyaları ağaca uygula. Dönüş: 0 temiz, 1 çakışma/başarısız."""
    applied = 0
    already = 0
    conflicts: List[str] = []
    failed: List[Tuple[str, str]] = []

    for info in files:
        # Taze ölçüm: önceki dosyanın uygulanması sonraki dosyayı etkileyebilir.
        state = _file_state(root, info.section)
        info.state = state
        if state == STATE_ALREADY:
            already += 1
            print("  ATLA   %-50s ağaçta zaten var" % info.path)
            continue
        if state == STATE_CONFLICT:
            conflicts.append(info.path)
            print("  ÇAKIŞ  %-50s ne ileri ne geri uygulanıyor" % info.path)
            continue
        if dry_run:
            applied += 1
            print("  UYGULA %-50s (deneme — yazılmadı)" % info.path)
            continue
        proc = _git(["apply", "--whitespace=nowarn", "-"], cwd=root,
                    input_text=info.section)
        if proc.returncode != 0:
            failed.append((info.path, proc.stderr.strip().splitlines()[-1:][0]
                           if proc.stderr.strip() else "git apply rc=%d"
                           % proc.returncode))
            print("  HATA   %-50s %s" % (info.path, failed[-1][1]))
            continue
        applied += 1
        print("  GERİ   %-50s uygulandı" % info.path)

    print("\nSONUÇ: %s · %d uygulandı · %d zaten var · %d çakışma · %d hata"
          % (patch.name, applied, already, len(conflicts), len(failed)))
    if dry_run and applied:
        print("  --dry-run: hiçbir şey yazılmadı (geri almak için --dry-run'ı kaldır).")
    if conflicts or failed:
        print("  Çakışan dosyalar elle birleştirilmeli; patch SİLİNMEDİ.",
              file=sys.stderr)
        return 1
    return 0


# ── raporlama ───────────────────────────────────────────────────────────────
def _fmt_size(size: int) -> str:
    if size >= 1024 * 1024:
        return "%.1f MiB" % (size / (1024 * 1024))
    if size >= 1024:
        return "%.1f KiB" % (size / 1024)
    return "%d B" % size


def _fmt_age(hours: float) -> str:
    if hours < 1:
        return "%d dk" % int(hours * 60)
    if hours < 48:
        return "%d sa" % int(hours)
    return "%d gün" % int(hours // 24)


def print_list(patches: List[Patch], directory: pathlib.Path) -> int:
    print("PRECOMMIT PATCH KURTARMA — %s" % directory)
    if not patches:
        print("  kalıntı yok (patch* dosyası bulunamadı).")
        return 0
    by_hash: Dict[str, str] = {}
    for patch in patches:
        duplicate = by_hash.get(patch.sha256)
        if duplicate is None:
            by_hash[patch.sha256] = patch.name
        flag = "  [BAYAT >%dg]" % (STALE_HOURS // 24) if patch.stale else ""
        if duplicate:
            flag += "  [yinelenen: %s]" % duplicate
        print("\n  %s  %s  %s önce%s" % (patch.name, _fmt_size(patch.size),
                                        _fmt_age(patch.age_hours), flag))
        for info in patch.files:
            state = {"zaten-var": "ağaçta VAR",
                     "uygulanabilir": "uygulanabilir",
                     "cakisma": "ÇAKIŞMA"}[info.state]
            print("    %s  +%-5d -%-5d %-48s %s"
                  % (info.mark, info.added, info.deleted, info.path, state))
    total = len(patches)
    applied = sum(1 for p in patches for f in p.files
                  if f.state == STATE_APPLIES)
    print("\n  %d patch · %d dosya · %d dosya uygulanabilir"
          % (total, sum(len(p.files) for p in patches), applied))
    print("  Geri yükleme: --restore <patch> [--include desen,...] [--dry-run]")
    return 0


def print_diff(patch: Patch, files: List[PatchFile],
               patterns: Sequence[str]) -> int:
    print("# patch: %s (%s, %s önce)"
          % (patch.name, _fmt_size(patch.size), _fmt_age(patch.age_hours)))
    if patterns:
        print("# --include: %s" % ", ".join(patterns))
    for info in files:
        sys.stdout.write(info.section)
        if not info.section.endswith("\n"):
            sys.stdout.write("\n")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="pre-commit `patch*` kalıntılarını oku/özetle/geri yükle.")
    ap.add_argument("patch", nargs="?", default=None,
                    help="patch adı ya da dosya yolu (--diff/--restore için)")
    ap.add_argument("--dir", default=str(DEFAULT_DIR),
                    help="patch dizini (varsayılan: ~/.cache/pre-commit)")
    ap.add_argument("--root", default=None,
                    help="çalışma ağacı kökü (varsayılan: git rev-parse)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true",
                      help="özet tablo (varsayılan)")
    mode.add_argument("--diff", action="store_true",
                      help="seçilen patch'in diff'i")
    mode.add_argument("--restore", action="store_true",
                      help="seçilen patch'i ağaca uygula (stage ETMEZ)")
    ap.add_argument("--include", action="append", default=None,
                    metavar="DESEN[,DESEN]",
                    help="yalnız eşleşen dosyalar (fnmatch; yol ya da ad)")
    ap.add_argument("--dry-run", action="store_true",
                    help="--restore ile: yazmadan sına")
    ap.add_argument("--json", action="store_true",
                    help="makine-okunur çıktı (tek JSON belgesi)")
    args = ap.parse_args(argv)

    try:
        root = repo_root(args.root)
        directory = pathlib.Path(args.dir).expanduser()
        patterns = parse_includes(args.include)
        patches = discover_patches(directory, root)

        wanted = args.patch
        if (args.diff or args.restore) and not wanted:
            raise RecoveryError("--diff/--restore için patch adı gerekli")

        if args.restore:
            patch = pick_patch(patches, wanted, directory, root)
            files = select_files(patch, patterns)
            print("PRECOMMIT PATCH KURTARMA — geri yükleme (%s)"
                  % ("dry-run" if args.dry_run else "yazma"))
            print("  patch: %s" % patch.path)
            print("  ağaç : %s" % root)
            return restore(root, patch, files, args.dry_run)

        if args.diff:
            patch = pick_patch(patches, wanted, directory, root)
            files = select_files(patch, patterns)
            if args.json:
                print(json.dumps({"patch": patch.name,
                                  "files": [f.as_dict() for f in files]},
                                 ensure_ascii=False, indent=2))
                return 0
            return print_diff(patch, files, patterns)

        if args.json:
            print(json.dumps({"dir": str(directory), "root": str(root),
                              "patches": [p.as_dict() for p in patches]},
                             ensure_ascii=False, indent=2))
            return 0
        return print_list(patches, directory)
    except RecoveryError as exc:
        print("HATA: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
