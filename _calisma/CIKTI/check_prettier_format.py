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
- `--diff` modu DEĞİŞİM FARKI yüzeyini denetler: (şu an stage'li dosyalar) ∪
  (merge-base..HEAD arası değişen dosyalar). Stage yalnız commit anını
  gördüğü için dalın önceki commit'inden gelen bozuk dosya sessizce geçerdi
  (ölçülen kök neden); birleşim iki yönlüdür.
- `--all` modu TÜM ağacı denetler (git ls-files). Borcun toplam sıfır
  kalmasını garanti eden tek mod; `--diff` yalnız değişim yüzeyini görür.
- .prettierignore'daki kod/veri ayrımı HER ÜÇ modda da geçerlidir.

OFFLINE, stdlib-only.
"""
import fnmatch
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PRETTIER = REPO / "apps" / "dashboard-next" / "node_modules" / ".bin" / "prettier"

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
    """.prettierignore desenleri (yorum satırları ve boşluklar atlanır).

    Yol REPO'dan ÇAĞRI ANINDA türetilir; modül sabiti değil. Kök
    değiştiğinde (test kancası, alt ağaç) sabit eski yerden okur ve
    kod/veri ayrımı sessizce yanlış yere uzanır.
    """
    ignore = REPO / ".prettierignore"
    if not ignore.is_file():
        return []
    out = []
    for line in ignore.read_text(encoding="utf-8").splitlines():
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


def _git_lines(args):
    """git komutu → satır listesi (hata/timeout'ta boş)."""
    try:
        r = subprocess.run(["git", "-C", str(REPO)] + list(args),
                           capture_output=True, text=True, timeout=30)
    except Exception:
        return []
    if r.returncode != 0:
        return []
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def _git_ok(args):
    try:
        r = subprocess.run(["git", "-C", str(REPO)] + list(args),
                           capture_output=True, text=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def collect_diff_files(base="HEAD~1"):
    """Değişim farkı yüzeyi: stage ∪ dal farkı (muaflar hariç).

    Neden iki kaynak birleşiyor:
      - `git diff --cached` → şu AN stage'li dosya (commit anı yüzeyi)
      - `git diff base...HEAD` → dalın commit'INDEN beri DEĞİŞTİĞİ her dosya
    Stage tek başına yetersiz: dalın önceki commit'inden gelen bozuk dosya
    commit anında stage'lenmiyorsa sessizce geçer (ölçülen kök neden).
    Üç-nokta (merge-base) farkı kullanılır: iki-nokta, dal tabandan ayrıldıysa
    yanlış yüzeyi verir.
    """
    staged = _git_lines(["diff", "--cached", "--name-only"])
    branch = _git_lines(["diff", "--name-only", f"{base}...HEAD"])
    patterns = load_ignore_patterns()
    seen = set()
    for f in list(staged) + list(branch):
        f = f.replace("\\", "/")
        if f and matches_glob(f) and not is_ignored(f, patterns):
            seen.add(f)
    return sorted(seen)


def _resolve_base(argv):
    """--base verilmişse onu, yoksa origin/main, o da yoksa HEAD~1."""
    if "--base" in argv:
        i = argv.index("--base")
        if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            return argv[i + 1]
    if _git_ok(["rev-parse", "--verify", "--quiet", "origin/main"]):
        return "origin/main"
    return "HEAD~1"


def main(argv):
    all_mode = "--all" in argv
    diff_mode = "--diff" in argv
    if all_mode:
        files, label = collect_all_files(), "tüm ağaç"
    elif diff_mode:
        base = _resolve_base(argv)
        files, label = collect_diff_files(base), f"değişim farkı ({base})"
    else:
        files = [f for f in argv if not f.startswith("-")
                 and Path(f).is_file()]
        label = "stage'li"
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
