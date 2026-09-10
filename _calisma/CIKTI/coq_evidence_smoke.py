#!/usr/bin/env python3
"""K19 smoke: coq-version + Content.v derlemesini yeniden üret."""
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from check_coq_axioms import scan_coq_dir
from tool_fallback import find_tool

ROOT = pathlib.Path(__file__).resolve().parent.parent
COQ_DIR = ROOT / "coq_reduct"


def main():
    version_file = COQ_DIR / "coq-version"
    source = COQ_DIR / "Content.v"
    if not version_file.is_file() or not source.is_file():
        print("K19 FAIL: coq-version veya Content.v eksik", file=sys.stderr)
        return 1
    expected = version_file.read_text(encoding="utf-8").strip()
    clean, findings = scan_coq_dir(str(COQ_DIR))
    if not clean:
        print(f"K19 FAIL: proof-gap ön-kapısı — {findings[0]}", file=sys.stderr)
        return 1
    coqtop = find_tool("coqtop")
    if not coqtop:
        print("K19 SKIP: coqtop kurulu değil")
        return 0
    version = subprocess.run([coqtop, "--version"], capture_output=True,
                             text=True, check=False, timeout=30)
    if expected not in version.stdout + version.stderr:
        print(f"K19 FAIL: coqtop sürüm uyuşmuyor (beklenen {expected})",
              file=sys.stderr)
        return 1
    # Coq 8.18'de coqtop -compile yok; derleme coqc ile yapılır.
    result = subprocess.run(["coqc", "-q", "-o", str(COQ_DIR / "Content.vo"),
                             str(source)], cwd=str(COQ_DIR),
                            capture_output=True, text=True, check=False,
                            timeout=300)
    if result.returncode:
        print(result.stdout + result.stderr, file=sys.stderr)
        return result.returncode or 1
    print(f"K19 PASS: coq-version {expected}; Content.v coqc başarılı")
    return 0


if __name__ == "__main__":
    sys.exit(main())
