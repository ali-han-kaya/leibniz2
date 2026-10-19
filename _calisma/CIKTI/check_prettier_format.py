#!/usr/bin/env python3
"""check_prettier_format.py — JS/TS/JSON dosyalarında Prettier uyumu.

İki çağıran, TEK kapsam tanımı:

  1) pre-commit `check-prettier-format` hook'u — dosyaları ARGÜMAN olarak
     verir (yalnız stage'li olanlar). Prettier bulunamazsa SKIP: ortam-bağımlı
     kapı ortam yoksa bloke etmez (check-unit-tests SKIP deseni).
  2) Haftalık `prettier-drift.yml` job'ı — `--all-tracked` ile TÜM takipli
     yüzeyi tarar. Neden gerekli: hook yalnız stage'li dosyaları görür, yani
     hiç dokunulmayan bir dosya sonsuza dek biçim-dışı kalabilir
     (grandfather drift). Burada prettier YOKSA `--require-prettier` ile
     rc=2 verilir: aksi hâlde job yeşil görünüp HİÇBİR ŞEY ölçmezdi
     (sessiz kanıt kaybı).

Kapsam hook'un `files:` filtresiyle birebir aynıdır: `.js/.jsx/.ts/.tsx/.json`,
`package-lock.json` hariç. Muafiyetler `.prettierignore`'dan gelir (tek
kaynak) — Prettier onu hem glob hem AÇIK argüman için uygular (ölçüldü
2026-09-30, prettier 3.6.2: repo kökündeki ignore ile explicit dosya rc=0).

Biçimlendirme YAPMAZ (read-only, zincir-kültürü): `--write` kullanıcının işi.
Prettier sürümü CI'da `apps/dashboard-next/package-lock.json`'dan okunur;
`PRETTIER_BIN` ile geçersiz kılınabilir.

OFFLINE, stdlib-only.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PRETTIER = REPO / "apps" / "dashboard-next" / "node_modules" / ".bin" / "prettier"

# Hook'un `files:`/`exclude:` filtresiyle TEK kaynak olması gereken kapsam.
INCLUDED_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".json")
EXCLUDED_NAMES = ("package-lock.json",)

# Prettier `[warn] <yol>` satırlarıyla biçim-uyumsuz dosyaları bildirir.
_WARN_RE = re.compile(r"^\[warn\]\s+(.+?)\s*$")

# Komut satırı uzunluğu (ARG_MAX) ilerideki bir büyümeyle aşılmasın:
# 119 dosya bugün tek çağrıya sığıyor, ama sınır repo büyüklüğüne bağlı
# olmamalı. Parçalar hâlinde koşulur, sonuç birleştirilir.
CHUNK = 200


def resolve_prettier(env=None):
    """Prettier ikilisini bul: PRETTIER_BIN > dashboard-next node_modules."""
    env = os.environ if env is None else env
    override = env.get("PRETTIER_BIN")
    if override and override.strip():
        p = Path(override.strip())
        return p if p.is_file() else None
    return PRETTIER if PRETTIER.is_file() else None


def tracked_targets(repo=REPO):
    """Takipli js/jsx/ts/tsx/json dosyaları (package-lock hariç), sıralı.

    NUL ayraçlı `git ls-files -z`: repo'da ASCII olmayan adlar var ve
    `core.quotePath` açıkken düz `ls-files` onları tırnaklar/kaçışlar.
    """
    r = subprocess.run(["git", "ls-files", "-z"], cwd=str(repo),
                       capture_output=True, text=True)
    if r.returncode != 0:
        return []
    out = []
    for name in r.stdout.split("\0"):
        if not name:
            continue
        if not name.endswith(INCLUDED_SUFFIXES):
            continue
        if os.path.basename(name) in EXCLUDED_NAMES:
            continue
        out.append(name)
    return sorted(out)


def run_check(prettier, files, repo=REPO):
    """Prettier'ı parçalar hâlinde koşar → (rc, [biçim-uyumsuz dosyalar])."""
    bad = []
    rc = 0
    for i in range(0, len(files), CHUNK):
        chunk = files[i:i + CHUNK]
        result = subprocess.run(
            [str(prettier), "--ignore-unknown", "--check", *chunk],
            cwd=str(repo), capture_output=True, text=True)
        if result.returncode != 0:
            rc = result.returncode
        for line in (result.stderr or "").splitlines():
            m = _WARN_RE.match(line)
            if m and (repo / m.group(1)).is_file():
                bad.append(m.group(1))
    return rc, sorted(set(bad))


def main(argv):
    ap = argparse.ArgumentParser(
        description="Prettier uyum denetimi (pre-commit: dosya listesi, "
                    "CI: --all-tracked).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="denetlenecek dosyalar")
    ap.add_argument("--all-tracked", action="store_true",
                    help="TÜM takipli js/jsx/ts/tsx/json yüzeyini tara "
                         "(package-lock.json hariç)")
    ap.add_argument("--require-prettier", action="store_true",
                    help="prettier yoksa SKIP yerine rc=2 (fail-closed). "
                         "CI bunu kullanır: kurulmamış bir job yeşil görünüp "
                         "hiçbir şey ölçmemeli.")
    args = ap.parse_args(argv)

    if args.all_tracked:
        files = tracked_targets()
        scope = "takipli js/jsx/ts/tsx/json"
    else:
        files = [f for f in args.files if Path(f).is_file()]
        scope = "verilen"

    if not files:
        if args.all_tracked:
            # Takipli js/jsx/ts/tsx/json sıfır olamaz: ya git okunamadı ya
            # desen bozuldu. "0 dosya, temiz" demek kapıyı işlevsiz kılardı.
            print("check-prettier-format: HATA — takipli js/jsx/ts/tsx/json "
                  "listesi BOŞ döndü (git ls-files okunamadı veya kapsam "
                  "deseni bozuk); denetim yapılamaz (fail-closed).",
                  file=sys.stderr)
            return 2
        print("check-prettier-format: eşleşen stage'li dosya yok — SKIP")
        return 0

    prettier = resolve_prettier()
    if prettier is None:
        if args.require_prettier:
            print("check-prettier-format: HATA — prettier bulunamadı ve "
                  "--require-prettier verildi; kurulmadan denetim "
                  "YAPILAMAZ (fail-closed). Beklenen yol: %s ; PRETTIER_BIN "
                  "ile geçersiz kılınabilir."
                  % PRETTIER.relative_to(REPO), file=sys.stderr)
            return 2
        try:
            rel = PRETTIER.relative_to(REPO)
        except ValueError:              # repo dışı bir yol — olduğu gibi yaz
            rel = PRETTIER
        print("check-prettier-format: prettier yok (%s) — SKIP" % rel)
        return 0

    rc, bad = run_check(prettier, files)
    if rc != 0:
        print("check-prettier-format: %d/%d %s dosya biçim-uyumsuz"
              % (len(bad), len(files), scope))
        for name in bad:
            print("  [warn] %s" % name)
        print("check-prettier-format: FAIL — biçim-uyumsuz dosyalar yukarıda;")
        print("  düzeltme: npx prettier --ignore-unknown --write <dosyalar>")
        return 1
    print("check-prettier-format: OK (%d dosya)" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
