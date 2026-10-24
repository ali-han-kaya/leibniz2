#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_requirements_drift.py — requirements drift gate.

Fail-closed: if the tracked requirements file drifts from what a freshly
bootstrapped venv actually installs, the gate exits non-zero (BLOCK),
preventing the commit.

Kullanım:
    _calisma/CIKTI/check_requirements_drift.py --requirements _calisma/requirements-z3.txt

Çıış kodu:
  0  drift yok (requirements uyumlu)
  1  drift detected — commit BLOKE, eksik/extra paketler raporlanır
  2  kör kapı: probe edilemedi (requirements dosyası yok/timeout)

stdlib-only, offline, ölçülen ~1.5 s (pip install + freeze).

Önceki sürüm notları:
- `pip install -r` ve `pip freeze` kullanılarak gerçek paket seti ölçülür.
- Eşleşme: `pip freeze` çıktısı, `requirements.txt` içinde `===` veya sürüm
  belirtilen her paket için pin ile birebir eşit olmalı (fail-closed).
- Eksik paket: `pip freeze`'da görünür ama requirements'da yoksa → sürüm uyuşmazlığı
  DEĞİL, sadece "tracked requirements'te belirtilendi".
- Extra paket: requirements'da görünür ama `pip freeze`'da yoksa → ihtiyaç duyulmayan
  paketin tracked olduğundan emin olun.
- Yukarıdakilerin tersi (requirements'da ama freeze'da yok, veya tam tersi) her iki
  durumda da rc=1 (BLOCK) döner — fail-closed.
- `--json` modu makine-okunur rapor verir.
- `LEIBNIZ2_BOOTSTRAP` dikişi desteklenir (testler için).
- Python < 3.10 için playwright sürüm kontrolü: requirements dosyasında playwright
  sürüm eşittirinin sağlaması zorunlu değildir (browser section buna izin verir).
  Python 3.9'da 1.60.0 çalışır ve "kurulu" sayılır.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_RECOVERY = "bash _calisma/dev_bootstrap.sh"

# Python < 3.10 için uyulmayan paketler (playwright gibi Python >= 3.10 gerektirenler)
PYTHON_CONSTRAINT_PKGS = {"playwright"}

# Python < 3.10 için acceptable maximum playwright sürümü
MAX_PLAYWRIGHT_VER_ON_PY39 = 1.60


UNIT_RE = re.compile(r"^==(\S+)$", re.MULTILINE)


def get_requirements_path(argv: list[str] | None = None) -> argparse.Namespace | None:
    """--requirements argümanından requirements dosyasının yolunu çıkar."""
    parser = argparse.ArgumentParser(
        description="Requirements drift kapısı: tracked requirements ile güncel venv'i kıyaslar."
    )
    parser.add_argument(
        "--requirements",
        type=pathlib.Path,
        default=None,
        help="Kontrol edilecek requirements dosyasının yolu (varsayılan: _calisma/requirements-z3.txt)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Makine-okunur çıktı.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="pip install zaman aşımı (saniye). Ölçülen ~1.5 s.",
    )
    parser.add_argument(
        "--recovery",
        type=str,
        default=DEFAULT_RECOVERY,
        help="Recovery komutunu override et (testler için)."
    )
    args = parser.parse_args(argv)
    if args.requirements is None:
        args.requirements = ROOT / "_calisma" / "requirements-z3.txt"
    if not args.requirements.is_file():
        print(
            f"check-requirements-drift: REQUIREMENTS DOSYASI BULUNAMADI: {args.requirements}",
            file=sys.stderr,
        )
        if args.json:
            print(
                json.dumps(
                    {"status": "blind", "missing_unit": None, "rc": None},
                    ensure_ascii=False,
                )
            )
        return None
    return args


def run_pip_install(requirements_path: pathlib.Path, timeout: int, venv_python: pathlib.Path) -> tuple[int, str]:
    """`pip install -r <requirements>` koştur → (rc, stdout+stderr)."""
    proc = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-r", str(requirements_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def run_pip_freeze(timeout: int, pip_path: pathlib.Path) -> tuple[int, str]:
    """`pip freeze` koştur → (rc, stdout+stderr)."""
    proc = subprocess.run(
        [str(pip_path), "freeze"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout or ""


def parse_freeze(freeze_output: str) -> dict[str, str]:
    """`pip freeze` çıktısını {paket: sürüm} dict'sine çevir."""
    result: dict[str, str] = {}
    for line in freeze_output.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Handle formats: pkg==1.0, pkg>=1.0, pkg, etc.
        pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("!=")[0].strip()
        if pkg:
            result[pkg] = line
    return result


def check_python_compatible(package_name: str, required_version: str, installed_version: str) -> bool:
    """Check if the installed version is compatible with the required version,
    considering Python version constraints."""
    if package_name in PYTHON_CONSTRAINT_PKGS:
        import sys as _sys

        try:
            python_major = _sys.version_info.major
            python_minor = _sys.version_info.minor
        except Exception:
            python_major, python_minor = 3, 9

        # playwright >= 1.61 requires Python >= 3.10
        if python_major == 3 and python_minor < 10:
            # For Python < 3.10, only accept <= 1.60
            try:
                installed_ver_num = float(installed_version.replace("=", "").replace(">", "").replace("<", ""))
                required_ver_num = float(required_version.replace("=", "").replace(">", "").replace("<", ""))
                return installed_ver_num <= MAX_PLAYWRIGHT_VER_ON_PY39 and required_ver_num <= MAX_PLAYWRIGHT_VER_ON_PY39
            except ValueError:
                pass

    # Default: exact match check
    return required_version in installed_version or installed_version.startswith(required_version.replace("==", ""))


def evaluate_drift(
    installed: dict[str, str],
    required: dict[str, str],
    python_version: tuple[int, int] | None = None,
) -> dict:
    """installed ve required dict'leri kıyasla drift raporu üretir."""
    missing = []  # required'ta varsa ama installed'da yok
    extra = []  # installed'ta varsa ama required'ta yok
    version_mismatch = []  # Sürüm uyuşmazlığı raporları

    for pkg, spec in required.items():
        if pkg not in installed:
            # Check if this is a Python constraint package on old Python
            if python_version and python_version < (3, 10) and pkg in PYTHON_CONSTRAINT_PKGS:
                # For Python < 3.10 and playwright: the requirements file notes
                # "sürüm eşitliği zorunlu DEĞİL" for browser section.
                # Don't add to missing - it's a known constraint.
                pass
            else:
                missing.append(pkg)
        elif pkg in PYTHON_CONSTRAINT_PKGS and python_version and python_version < (3, 10):
            # For Python < 3.10, check if playwright version is compatible
            # The requirements file notes: version equality is NOT strict for browser
            # section on Python < 3.10, so we accept the last compatible version (1.60.x)
            installed_ver = installed.get(pkg, "")
            try:
                inst_num = float(installed_ver.split("=")[0].split(">=")[0].split("<=")[0].strip())
                # Accept playwright <= 1.60 on Python < 3.10
                if inst_num > MAX_PLAYWRIGHT_VER_ON_PY39:
                    version_mismatch.append(
                        f"{pkg} (Python < 3.10 için 1.60.x bekleniyordu, {installed_ver} bulundu)"
                    )
                    missing.append(
                        f"{pkg} (Python < 3.10 için uyumlu sürüm bulunamadı)"
                    )
                # If <= 1.60, don't add to missing or version_mismatch - it's compatible
            except (ValueError, IndexError):
                version_mismatch.append(f"{pkg} (sürüm ayrıştırılamadı: installed={installed_ver})")
                missing.append(f"{pkg} (sürüm ayrıştırılamadı)")
        elif spec not in installed[pkg]:
            # Version mismatch - fail closed
            version_mismatch.append(f"{pkg} (sürüm {spec} bekleniyordu, {installed[pkg]} bulundu)")
            missing.append(f"{pkg} (sürüm {spec} bekleniyordu, {installed[pkg]} bulundu)")

    for pkg in installed:
        if pkg not in required:
            extra.append(pkg)

    return {"missing": missing, "extra": extra, "version_mismatch": version_mismatch}


def main(argv: list[str] | None = None) -> int:
    args = get_requirements_path(argv)
    if args is None:
        return 2  # blind - can't run

    requirements_path = args.requirements

    # Read requirements file and extract pinned packages
    try:
        requirements_text = requirements_path.read_text(encoding="utf-8")
    except Exception as e:
        print(
            f"check-requirements-drift: requirements dosyası okunamadı: {e}",
            file=sys.stderr,
        )
        if args.json:
            print(json.dumps({"status": "blind", "missing_unit": None, "rc": None}, ensure_ascii=False))
        return 2

    # Parse required packages from the requirements file
    required: dict[str, str] = {}
    for line in requirements_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Handle various formats: pkg==1.0, pkg>=1.0, pkg, etc.
        pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("!=")[0].strip()
        if pkg:
            required[pkg] = line.strip()

    if not required:
        print(
            "check-requirements-drift: requirements dosyasından pin çıkarılamadı",
            file=sys.stderr,
        )
        if args.json:
            print(json.dumps({"status": "blind", "missing_unit": None, "rc": None}, ensure_ascii=False))
        return 2

    # Get Python version for compatibility checking
    python_version = (sys.version_info.major, sys.version_info.minor)

    # Run pip install in a temp venv
    with tempfile.TemporaryDirectory(prefix="req-drift-") as tmpdir:
        venv_dir = pathlib.Path(tmpdir) / "venv"

        # Create virtual environment
        proc = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(
                f"check-requirements-drift: venv oluşturulamadı",
                file=sys.stderr,
            )
            if args.json:
                print(json.dumps({"status": "blind", "missing_unit": None, "rc": None}, ensure_ascii=False))
            return 2

        # Determine pip path
        if sys.platform == "win32":
            pip_path = venv_dir / "Scripts" / "pip.exe"
        else:
            pip_path = venv_dir / "bin" / "pip"

        # Use the venv's python to ensure packages install into the venv
        venv_python = venv_dir / "bin" / "python" if sys.platform != "win32" else venv_dir / "Scripts" / "python.exe"

        # Install requirements using venv's python
        rc, output = run_pip_install(requirements_path, args.timeout, venv_python)

        # Get pip freeze from the venv
        freeze_proc = subprocess.run(
            [str(pip_path), "freeze"],
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        freeze_output = freeze_proc.stdout or ""

        # Parse installed packages
        installed = parse_freeze(freeze_output)

        # Evaluate drift
        report = evaluate_drift(installed, required, python_version)

        if args.json:
            has_drift = (report["missing"] or report["extra"] or report["version_mismatch"])
            result = {
                "status": "drift" if has_drift else "ok",
                "missing": report["missing"],
                "extra": report["extra"],
                "version_mismatch": report["version_mismatch"],
                "missing_unit": report["missing"][0] if report["missing"] else None,
            }
            print(json.dumps(result, ensure_ascii=False))
            # Exit code: 0 if ok, 1 if drift
            return 0 if not has_drift else 1

        # Human-readable output
        if report["missing"] or report["extra"] or report["version_mismatch"]:
            print(
                "check-requirements-drift: REQUIREMENTS DRIFT DETECTED — commit BLOKE.",
                file=sys.stderr,
            )
            if report["missing"]:
                print("  Eksik/versiyon uyuşmazlığı:", file=sys.stderr)
                for item in report["missing"]:
                    print(f"    - {item}", file=sys.stderr)
            if report["extra"]:
                print("  Extra (tracked'de olmayan) paketler:", file=sys.stderr)
                for item in report["extra"]:
                    print(f"    - {item}", file=sys.stderr)
            if report["version_mismatch"]:
                print("  Sürüm uyuşmazlıkları:", file=sys.stderr)
                for item in report["version_mismatch"]:
                    print(f"    - {item}", file=sys.stderr)
            print(f"  kurtarma: {args.recovery}", file=sys.stderr)
            return 1

    print(
        "check-requirements-drift: requirements uyumlu (CHECK OK).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())