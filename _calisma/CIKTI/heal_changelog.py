#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""heal_changelog.py — squash-merge artığı ÖLÜ changelog hash'lerini temizler
VE tabloda eksik kalan (lag-one) merge satırlarını ekler.

SORUN 1 — ÖLÜ HASH (ölçüldü, 2026-10-24): changelog satırı commit hash'iyle
anahtarlanır ve `update_changelog_hook.sh` satırı DALIN kendi commit'i için
yazar. Squash-merge o commit'i main geçmişinden düşürür → satır "ölü hash"
olur ve `test_every_readme_changelog_hash_resolves_to_live_commit` kırmızıya
döner. Bu, her squash-merge'de tekrar eden bir kırmızıdır (PR #55, #90, #93,
#108).

SORUN 2 — LAG-ONE EKSİK SATIR: tablo, HER commit'ten sonra tam olarak bir
commit geride kalır — satırın hash'i ancak commit OLUŞTUKTAN SONRA bilinir
(bkz. `update_changelog_hook.sh`). Bu yapısal gecikme elle `gen_changelog.py
--update` + `chore(changelog)` PR'ı ile kapatılıyordu (PR #123). Bu script o
adımı da otomatikleştirir: eksik satır varsa `--prune` ile ekler ve aynı bot
PR'ına koyar.

ÇÖZÜM: merge SONRASI otomatik iyileştirme. `.github/workflows/changelog-heal.yml`
main push'unda bu script'i koşar; ölü satır ve/veya eksik satır varsa
`gen_changelog.py --prune` (stale sil + missing ekle) ile düzeltir ve bot dalı
+ PR (auto-merge) ile main'e indirir — çünkü main branch-protection'lıdır, bare
push GH006 ile reddedilir (determinism-trend ile aynı kayıt yolu).

DÖNGÜ KIRICI (zorunlu): heal'in kendi commit'i de bir commit'tir; hash'i kendi
satırında olamaz. Bot commit'leri bu yüzden `chore(changelog): [bot]` prefix'i
ile yazılır ve ölçüm onları META commit sayar (gen_changelog.META_COMMIT_PREFIX,
`find_missing_commits` içinde dışlanır). Aksi halde her bot PR'ı yeni bir eksik
commit üretir ve heal sonsuz PR açar. Bu, kanıt-defterindeki DEFAULT_GAP_EXEMPT
ile aynı gerekçedir: kaydı yazan adım, kaydın geride kaldığı adımdır.

ÖLÇÜT — ölü hash gate ile BİREBİR aynı (`test_gen_changelog._reachable_hashes`):
`origin/main` ∪ `HEAD` üzerinden erişilebilir kısa (7 karakter) hash'ler.
Tabloda olup bu kümede olmayan hash = ölü.

Modlar:
  --check   Ölü hash ve/veya eksik satır var mı?
            (0 = temiz · 1 = ölü/eksik var · 2 = ölçülemedi)
  --apply   `--prune` ile temizle/ekle, sonra yeniden ölç
            (0 = temiz · 1 = hâlâ kirli · 2 = ölçülemedi)

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


def missing_hashes(repo: Path, readme: Path):
    """Tabloda satırı OLMAYAN (tablodaki en yeniden yeni) commit'lerin listesi.

    `gen_changelog.find_missing_commits` sözleşmesi birebir kullanılır: yalnızca
    tablodaki en yeni satırdan sonra gelen commit'ler; META commit'ler (heal
    botunun `chore(changelog): [bot]` commit'leri) sayılmaz — aksi halde her
    bot PR'ı yeni bir eksik commit üretip döngüyü kapatmaz.

    Returns: list[str] (yeni→eski) veya ölçülemiyorsa None.
    """
    sys.path.insert(0, str(SCRIPT_DIR))
    import gen_changelog as gc  # noqa: E402  (aynı dizindeki kardeş modül)

    try:
        commits = gc.get_git_log(repo=str(repo))
    except (subprocess.CalledProcessError, OSError):
        return None
    return [ci.short_hash for ci in gc.find_missing_commits(commits, table_hashes(readme))]


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


def _measure(repo: Path, readme: Path):
    """(dead, missing) — biri bile ölçülemiyorsa (None, None)."""
    dead = dead_hashes(repo, readme)
    missing = missing_hashes(repo, readme)
    if dead is None or missing is None:
        return None, None
    return dead, missing


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                      help="ölü hash / eksik satır var mı? (0 temiz, 1 kirli, 2 ölçülemedi)")
    mode.add_argument("--apply", action="store_true",
                      help="prune ile temizle/ekle ve yeniden ölç")
    ap.add_argument("--repo", default=".", help="git deposu kökü (varsayılan: .)")
    ap.add_argument("--readme", default="README.md", help="README yolu")
    ap.add_argument("--json", action="store_true",
                    help="makine-okur tek JSON belgesi (stdout)")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    readme = Path(args.readme)
    if not readme.is_absolute():
        readme = (repo / readme).resolve()

    before_dead, before_missing = _measure(repo, readme)
    if before_dead is None or before_missing is None:
        payload = {"status": "unmeasurable", "dead": None, "missing": None,
                   "healed": [], "added": []}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            sys.stderr.write("ÖLÇÜLEMEDİ: origin/main yok veya git erişilemedi\n")
        return 2

    healed: list[str] = []
    added: list[str] = []
    if args.apply and (before_dead or before_missing):
        prune_rc = apply_prune(repo, readme)
        if prune_rc != 0:
            payload = {"status": "prune_failed", "dead": before_dead,
                       "missing": before_missing, "healed": [], "added": [],
                       "prune_exit": prune_rc}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            return 1
        after_dead, after_missing = _measure(repo, readme)
        if after_dead is None or after_missing is None:
            return 2
        healed = sorted(set(before_dead) - set(after_dead))
        added = [h for h in before_missing if h not in set(after_missing)]
        rc = 0 if not after_dead and not after_missing else 1
        payload = {"status": "healed" if rc == 0 else "still_dirty",
                   "dead": before_dead, "missing": before_missing,
                   "healed": healed, "added": added,
                   "remaining": after_dead, "remaining_missing": after_missing}
    else:
        rc = 0 if not before_dead and not before_missing else 1
        payload = {"status": "clean" if rc == 0 else "dirty",
                   "dead": before_dead, "missing": before_missing,
                   "healed": [], "added": [],
                   "remaining": before_dead,
                   "remaining_missing": before_missing}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if payload["status"] == "clean":
            print("PASS: changelog'da ölü hash ve eksik satır yok")
        elif payload["status"] == "dirty":
            print("KİRLİ: %d ölü satır, %d eksik satır (prune gerekli):"
                  % (len(before_dead), len(before_missing)))
            for h in before_dead[:10]:
                print("  - %s" % h)
            for h in before_missing[:10]:
                print("  + %s" % h)
        elif payload["status"] == "healed":
            print("HEALED: %d ölü satır temizlendi, %d eksik satır eklendi"
                  % (len(healed), len(added)))
            for h in healed[:10]:
                print("  - %s" % h)
            for h in added[:10]:
                print("  + %s" % h)
        else:
            print("HÂLÂ KİRLİ: %d ölü satır, %d eksik satır kaldı"
                  % (len(payload["remaining"]), len(payload["remaining_missing"])))
            for h in payload["remaining"][:10]:
                print("  - %s" % h)
            for h in payload["remaining_missing"][:10]:
                print("  + %s" % h)
    return rc


if __name__ == "__main__":
    sys.exit(main())
