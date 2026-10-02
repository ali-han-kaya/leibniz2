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
- `--all` modu TÜM ağacı denetler (git ls-files). Ölçülen kök neden:
  `files:` filtresi yalnız stage'li dosyayı gördüğü için hiç yeniden
  stage olmayan dosyalar sessizce çürüdü; origin/main'de 40 dosya borçluydu
  ve borç ancak ağaç taranınca göründü. .prettierignore'daki kod/veri
  ayrımı her iki modda da geçerlidir.

OFFLINE, stdlib-only.
"""
import fnmatch
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PRETTIER = REPO / "apps" / "dashboard-next" / "node_modules" / ".bin" / "prettier"
PRETTIERIGNORE = REPO / ".prettierignore"

# Hook `files: \.(js|jsx|ts|tsx|json)$` sözleşmesi + package-lock exclude.
_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".json")


def matches_glob(path):
    """Prettier kapsamına giren dosya mı?

    Hook'un `files:`/`exclude:` filtreleriyle birebir aynı sözleşme:
    yalnız js/jsx/ts/tsx/json; package-lock.json ve node_modules dışarıda.
    """
    p = str(path).replace("\\", "/")
    if "node_modules/" in p:
        return False
    if p.endswith("package-lock.json"):
        return False
    return p.endswith(_SUFFIXES)


def load_ignore_patterns():
    """.prettierignore desenleri (yorum satırları ve boşluklar atlanır)."""
    if not PRETTIERIGNORE.is_file():
        return []
    out = []
    for line in PRETTIERIGNORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def is_ignored(path, patterns):
    """Prettier bu yolu muaf mı? (dizin deseni = önek eşleşmesi)"""
    p = str(path).replace("\\", "/")
    for pat in patterns:
        pat = pat.rstrip("/")
        if p == pat or p.startswith(pat + "/"):
            return True
        if fnmatch.fnmatch(p, pat):
            return True
        if fnmatch.fnmatch(p, pat + "/*"):
            return True
    return False


def collect_all_files():
    """git ls-files üzerinden tüm kapsam dosyaları (muaflar hariç).

    Yalnız stage'e bakmaz — kök neden bu. Untracked çürümeye bırakılmaz,
    çünkü borç tracked ağaçta birikir.
    """
    try:
        r = subprocess.run(["git", "-C", str(REPO), "ls-files"],
                           capture_output=True, text=True, timeout=30)
        listed = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:
        return []
    patterns = load_ignore_patterns()
    return [f for f in listed
            if matches_glob(f) and not is_ignored(f, patterns)]


def main(argv):
    all_mode = "--all" in argv
    files = (collect_all_files() if all_mode
             else [f for f in argv if not f.startswith("-")
                   and Path(f).is_file()])
    label = "tüm ağaç" if all_mode else "stage'li"
    if not files:
        print(f"check-prettier-format: eşleşen {label} dosya yok — SKIP")
        return 0
    if not PRETTIER.is_file():
        print(f"check-prettier-format: prettier yok ({PRETTIER.relative_to(REPO)}) — SKIP")
        return 0
    cmd = [str(PRETTIER), "--ignore-unknown", "--check", *files]
    result = subprocess.run(cmd, cwd=str(REPO))
    if result.returncode != 0:
        print(f"check-prettier-format: FAIL — biçim-uyumsuz dosyalar yukarıda;")
        print("  düzeltme: npx prettier --ignore-unknown --write <dosyalar>")
        return 1
    print(f"check-prettier-format: OK ({len(files)} dosya, {label})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
