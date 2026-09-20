#!/usr/bin/env python3
"""check_prettier_format.py — stage'li JS/TS/JSON dosyalarında Prettier uyumu.

setup-pre-commit skill'inin "commit-anı format" hedefinin zincir-uyarlaması
(Husky yerine mevcut pre-commit zinciri):
- lint-staged katmanı yerine pre-commit `files:` filtresi: yalnız stage'li
  eşleşen dosyalar hook'a gelir (package-lock.json exclude).
- Hook READ-ONLY'dir (zincir-kültürü): yazmaz, fail-closed bloke eder;
  düzeltme geliştiricide `npx prettier --ignore-unknown --write` ile.
- Prettier bulunamazsa (node_modules kurulu değil) SKIP: exit 0 + uyarı —
  ortam-bağımlı kapı ortam yoksa bloke etmez (check-unit-tests SKIP deseni).
- Yapılandırma: her dosya için en-yakın .prettierrc (apps/dashboard-next'te
  skill-defaults var); konfigürasyonsuz ağaçta Prettier built-in defaults.

OFFLINE, stdlib-only.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PRETTIER = REPO / "apps" / "dashboard-next" / "node_modules" / ".bin" / "prettier"


def main(argv):
    files = [f for f in argv if Path(f).is_file()]
    if not files:
        print("check-prettier-format: eşleşen stage'li dosya yok — SKIP")
        return 0
    if not PRETTIER.is_file():
        print(f"check-prettier-format: prettier yok ({PRETTIER.relative_to(REPO)}) — SKIP")
        return 0
    cmd = [str(PRETTIER), "--ignore-unknown", "--check", *files]
    result = subprocess.run(cmd, cwd=str(REPO))
    if result.returncode != 0:
        print("check-prettier-format: FAIL — biçim-uyumsuz dosyalar yukarıda;")
        print("  düzeltme: npx prettier --ignore-unknown --write <dosyalar>")
        return 1
    print(f"check-prettier-format: OK ({len(files)} dosya)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
