#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""heal_changelog.py — squash-merge artığı ÖLÜ changelog hash'lerini temizler.

SORUN (ölçüldü, 2026-10-24): changelog satırı commit hash'iyle anahtarlanır ve
`update_changelog_hook.sh` satırı DALIN kendi commit'i için yazar. Squash-merge
o commit'i main geçmişinden düşürür → satır "ölü hash" olur ve
`test_every_readme_changelog_hash_resolves_to_live_commit` kırmızıya döner.
Bu, her squash-merge'de tekrar eden bir kırmızıdır (PR #55, #90, #93, #108).

ÇÖZÜM: merge SONRASI otomatik prune. `.github/workflows/changelog-heal.yml`
main push'unda bu script'i koşar; ölü satır varsa `gen_changelog.py --prune`
ile temizler ve bot dalı + PR (auto-merge) ile main'e indirir — çünkü main
branch-protection'lıdır, bare push GH006 ile reddedilir (determinism-trend ile
aynı kayıt yolu).

ÖLÇÜT — gate ile BİREBİR aynı (`test_gen_changelog._reachable_hashes`):
`origin/main` ∪ `HEAD` üzerinden erişilebilir kısa (7 karakter) hash'ler.
Tabloda olup bu kümede olmayan hash = ölü.

Modlar:
  --check   Ölü hash var mı? (0 = temiz · 1 = ölü var · 2 = ölçülemedi)
  --apply   `--prune` ile temizle, sonra yeniden ölç (0 = temiz · 1 = hâlâ kirli
            · 2 = ölçülemedi)

Kullanım:
  python3 _calisma/CIKTI/heal_changelog.py --check
  python3 _calisma/CIKTI/heal_changelog.py --apply
  python3 _calisma/CIKTI/heal_changelog.py --check --json     # makine-okur
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SECTION = "## Değişiklik Geçmişi"
SHORT = 7
BASE_REF = "origin/main"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True, check=False)


def reachable_short_hashes(repo: Path, refs: tuple[str, ...] = (BASE_REF, "HEAD")):
    """`refs` üzerinden erişilebilir commit'lerin 7 karakterlik kısa hash'leri.

    Gate (`test_gen_changelog._reachable_hashes`) ile aynı sözleşme: iki ucun
    BİRLEŞİMİ kullanılır — PR merge sonrası tablodaki eski satırlar merge
    öncesi commit'lere işaret eder ve origin/main üzerinde yaşamaya devam eder.

    Returns: set[str] veya ölçülemiyorsa None (origin/main yok / git erişilemedi).
    """
    refs = tuple(r for r in refs if r)
    if not refs:
        return None
    # origin/main çözülemiyorsa ölçüm yapılamaz — sessiz "temiz" demeyelim.
    if BASE_REF in refs and _git(repo, "rev-parse", "--verify", BASE_REF).returncode != 0:
        return None
    proc = _git(repo, "rev-list", "--abbrev-commit", "--abbrev=%d" % SHORT, *refs)
    if proc.returncode != 0:
        return None
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def table_hashes(readme: Path) -> set[str]:
    """README changelog tablosundaki commit hash'leri (7 karakter, set)."""
    if not readme.exists():
        return set()
    sys.path.insert(0, str(SCRIPT_DIR))
    import gen_changelog as gc  # noqa: E402  (aynı dizindeki kardeş modül)

    return gc.extract_hashes_from_table(
        readme.read_text(encoding="utf-8"), gc._README_ROW_RE, SECTION)


def dead_hashes(repo: Path, readme: Path):
    """Ölü hash'lerin sıralı listesi; ölçülemiyorsa None."""
    reachable = reachable_short_hashes(repo)
    if reachable is None:
        return None
    return sorted(table_hashes(readme) - reachable)


def apply_prune(repo: Path, readme: Path) -> int:
    """`gen_changelog.py --prune` koşar (stale sil + missing ekle)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "gen_changelog.py"), "--prune",
         "--readme", str(readme)],
        cwd=str(repo), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
    return proc.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                      help="ölü hash var mı? (0 temiz, 1 ölü, 2 ölçülemedi)")
    mode.add_argument("--apply", action="store_true",
                      help="prune ile temizle ve yeniden ölç")
    ap.add_argument("--repo", default=".", help="git deposu kökü (varsayılan: .)")
    ap.add_argument("--readme", default="README.md", help="README yolu")
    ap.add_argument("--json", action="store_true",
                    help="makine-okur tek JSON belgesi (stdout)")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    readme = Path(args.readme)
    if not readme.is_absolute():
        readme = (repo / readme).resolve()

    before = dead_hashes(repo, readme)
    if before is None:
        payload = {"status": "unmeasurable", "dead": None, "healed": []}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            sys.stderr.write("ÖLÇÜLEMEDİ: origin/main yok veya git erişilemedi\n")
        return 2

    healed: list[str] = []
    rc = 0
    if args.apply and before:
        prune_rc = apply_prune(repo, readme)
        if prune_rc != 0:
            payload = {"status": "prune_failed", "dead": before, "healed": [],
                       "prune_exit": prune_rc}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            return 1
        after = dead_hashes(repo, readme)
        if after is None:
            return 2
        healed = sorted(set(before) - set(after))
        remaining = after
        rc = 0 if not after else 1
        payload = {"status": "healed" if not after else "still_dirty",
                   "dead": before, "healed": healed, "remaining": remaining}
    else:
        remaining = before
        rc = 0 if not before else 1
        payload = {"status": "clean" if not before else "dirty",
                   "dead": before, "healed": [], "remaining": remaining}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if payload["status"] == "clean":
            print("PASS: changelog'da ölü hash yok")
        elif payload["status"] == "dirty":
            print("ÖLÜ HASH: %d satır (prune gerekli):" % len(before))
            for h in before[:10]:
                print("  - %s" % h)
        elif payload["status"] == "healed":
            print("HEALED: %d ölü satır temizlendi" % len(healed))
            for h in healed[:10]:
                print("  - %s" % h)
        else:
            print("HÂLÂ KİRLİ: %d ölü satır kaldı" % len(remaining))
            for h in remaining[:10]:
                print("  - %s" % h)
    return rc


if __name__ == "__main__":
    sys.exit(main())
