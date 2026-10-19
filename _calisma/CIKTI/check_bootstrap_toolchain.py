#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_bootstrap_toolchain.py — pre-commit kapısı: araç-kümesi eksikse
commit'i fail-fast BLOKE eder, kurtarma komutunu birlikte basar.

Neden ayrı bir script (`--check`'i doğrudan `entry:` yapmak yerine):
`dev_bootstrap.sh --check` zaten fail-closed ve kurtarma komutunu içinde
yazıyor. Bu sarmalayıcı O TEK KAYNAĞI çağırır — unit listesini kopyalamaz,
kendi kopyası olamaz (pin ilkesinin bootstrap'taki hâli: sürüm/ünite
bilgisi tek yerde). Sarmalayıcının eklediği şey üç tanedir:

  1. KÖR KAPI (rc=2): bootstrap betiği yoksa/okunamıyorsa "araç-kümesi tam"
     diye PASS üretmek sessiz kapsam kaybıdır. Ölçülemeyen = yeşil değil.
  2. KURTARMA KOMUTU: blok mesajı, kopyala-yapıştırılabilir tek satır
     taşır; kullanıcı "ne yapayım?" diye araştırmak zorunda kalmaz.
  3. SINIR: yalnız `--check`. Bayraksız/`--full` çağrı birbirini besleyen
     bir döngü kurar (bu kapı → batarya → ... ) ve `--full` dakikalarca
     süren kurulumu commit sırasında yapar. Kurulum commit'in işi
     DEĞİLDİR: kapı ölçer, kurtarma komutunu söyler.

Kurulumu KENDİSİ tetiklemez (bilinçli): `npm ci` + `prisma generate` +
`next build` + ~150 MB chromium indirmesi commit'e gömülemez; bu bir ağ
ve disk yan etkisidir ve kullanıcının bilinçli kararı olmalıdır.

Çıkış kodu:
  0  araç-kümesi tam            (CHECK OK)
  1  araç-kümesi eksik/paritesiz → commit BLOKE, kurtarma komutu basılır
  2  kör kapı: probe edilemedi (betik yok/timeout/beklenmeyen rc)

stdlib-only, OFFLINE, ölçüldü ~1.3 s (9 unit: varlık+pin probe'ları ve
tek gerçek chromium açılışı). Test: test_check_bootstrap_toolchain.py.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_BOOTSTRAP = ROOT / "_calisma" / "dev_bootstrap.sh"
RECOVERY = "bash _calisma/dev_bootstrap.sh"

# `--check` birimi ilk eksik olanı yazıp DURUR (fail-fast); bu yüzden
# mesajda yalnız İLK ölçülen eksik unit adı geçer. Kalan unit'ler de
# eksik olabilir — kurtarma komutu tüm araç-kümesini onarır, bu yüzden
# eksik sayısını uydurmak yerine ölüleni söylüyoruz.
UNIT_RE = re.compile(r"^CHECK FAIL:\s*(\S+)", re.MULTILINE)
# Beklenmeyen rc'yi "eksik araç-kümesi" gibi göstermemek için probe
# hatasını ayrı tutuyoruz: 1 = ölçüldü ve eksik, diğer = ölçülemedi.
BLIND = 2
BLOCK = 1


def bootstrap_path() -> pathlib.Path:
    """Bootstrap betiğinin yolu.

    `LEIBNIZ2_BOOTSTRAP` dikişi testlerin hermetik olması için vardır
    (dev_bootstrap.sh'teki `LEIBNIZ2_BOOTSTRAP_BATTERY` dikişiyle aynı
    tür: ölçülebilirlik için injectable seam, üretimde kullanılmaz).
    """
    override = os.environ.get("LEIBNIZ2_BOOTSTRAP")
    return pathlib.Path(override) if override else DEFAULT_BOOTSTRAP


def run_check(script: pathlib.Path, timeout: int) -> tuple[int, str]:
    """`bash <script> --check` koştur → (rc, birleşik çıktı).

    Yalnız `--check` argümanı: bu kapının tek ve doğru çağrısı budur.
    stderr de birleştirilir — probe'un kendi hatası stdout'a değil
    stderr'a düşer ve kaybolursa kör kapı yanlışlıkla yeşil görünür.
    """
    proc = subprocess.run(
        ["bash", str(script), "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def evaluate(rc: int, output: str) -> tuple[int, dict]:
    """(rc, çıktı) → (çıkış kodu, makine-okunur rapor)."""
    if rc == 0:
        return 0, {"status": "ok", "missing_unit": None, "measured": output.strip()}
    if rc == 1:
        match = UNIT_RE.search(output)
        return BLOCK, {
            "status": "missing",
            "missing_unit": match.group(1) if match else None,
            "recovery": RECOVERY,
            "measured": output.strip(),
        }
    # 127 = bash yok, 2 = betik argüman hatası, 124 = timeout vb.
    # Bunlar "araç-kümesi eksik" DEĞİLDİR: probe'un kendisi bozuk.
    return BLIND, {
        "status": "blind",
        "missing_unit": None,
        "rc": rc,
        "measured": output.strip()[-2000:],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Araç-kümesi tamlık kapısı (dev_bootstrap.sh --check)."
    )
    parser.add_argument("--json", action="store_true", help="makine-okunur çıktı")
    parser.add_argument(
        "--timeout", type=int, default=300,
        help="probe zaman aşımı (saniye; ölçülen ~1.3 s)",
    )
    args = parser.parse_args(argv)

    script = bootstrap_path()
    if not script.is_file():
        report = {
            "status": "blind",
            "missing_unit": None,
            "rc": None,
            "measured": f"bootstrap betiği yok: {script}",
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print("check-bootstrap-toolchain: KÖR KAPI — bootstrap betiği "
                  f"bulunamadı: {script}", file=sys.stderr)
            print("  Bu kapı ölçemediği için 'tam' DEMEZ; commit yine de "
                  "bloke edilir.", file=sys.stderr)
        return BLIND

    try:
        rc, output = run_check(script, args.timeout)
    except subprocess.TimeoutExpired:
        report = {
            "status": "blind",
            "missing_unit": None,
            "rc": None,
            "measured": f"timeout: {args.timeout} s",
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print("check-bootstrap-toolchain: KÖR KAPI — "
                  f"dev_bootstrap.sh --check {args.timeout} s içinde "
                  "bitmedi.", file=sys.stderr)
        return BLIND

    code, report = evaluate(rc, output)
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
        return code

    if code == 0:
        print("check-bootstrap-toolchain: araç-kümesi tam (CHECK OK).")
        return 0
    if code == BLOCK:
        unit = report["missing_unit"]
        print("check-bootstrap-toolchain: ARAÇ-KÜMESİ EKSİK — commit "
              "BLOKE.", file=sys.stderr)
        if unit:
            print(f"  ilk eksik unit (ölçüldü): {unit}", file=sys.stderr)
        print(f"  kurtarma: {RECOVERY}", file=sys.stderr)
        # --check kendi satırını da basar; süzmeden aktarıyoruz ki
        # kapı çıktısı bootstrap'ın kendi kanıtıyla birebir okunsun.
        for line in report["measured"].splitlines():
            print(f"  | {line}", file=sys.stderr)
        return BLOCK
    print("check-bootstrap-toolchain: KÖR KAPI — probe beklenmeyen rc "
          f"verdi ({report.get('rc')}); bu 'eksik araç-kümesi' değil, "
          "kapının kendi hatası.", file=sys.stderr)
    return BLIND


if __name__ == "__main__":
    raise SystemExit(main())
