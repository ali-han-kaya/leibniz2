#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_ci_trend.py — §9 CI trend tablosunu canlı gh verisiyle yeniden üretir.

ci_stats.py `--update-doc`'un changelog hook'una bağlanan ince sarmalayıcısı:
docs/PRE_PUSH_DENETIM_RAPORU.md §9 tablosunu (son 10 run + success rate +
ortalama süre satırı) canlı GitHub Actions verisiyle yeniden üretir.

Nerede koşar:
  - Her push'ta: update_changelog_hook.sh (pre-commit) üzerinden — changelog
    drift'iyle birlikte tablo da tazelenir ve stage edilir.
  - CI'da: ci-stats-doc-sync advisory job (doğrudan ci_stats --update-doc).

Exit kodları:
  0 — tablo güncellendi VEYA gh verisi alınamadı (advisory uyarı — commit
      bloke edilmez; bayat tabloyu CI ci-stats-doc-sync job'ı yakalar)
  1 — --strict ile gh hatası/doc bloğu yok (fail-closed)
  2 — kullanım hatası
"""
import argparse
import contextlib
import io
import sys
from pathlib import Path

CIKTI = Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import ci_stats  # noqa: E402

# repo kökü: _calisma/CIKTI/ → parents[0]=CIKTI, [1]=_calisma, [2]=repo kökü
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOC = REPO_ROOT / "docs" / "PRE_PUSH_DENETIM_RAPORU.md"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", default=str(DEFAULT_DOC),
                    help="§9 tablo dosyası (varsayılan: docs/PRE_PUSH_DENETIM_RAPORU.md)")
    ap.add_argument("--strict", action="store_true",
                    help="gh hatası/doc bloğu yoksa exit 1 (fail-closed; CI için)")
    ap.add_argument("--limit", type=int, default=None,
                    help="run sayısı (varsayılan: 10 — §9 sözleşmesi)")
    args = ap.parse_args(argv)

    cmd = ["--update-doc", args.doc]
    if args.limit is not None:
        cmd += ["--limit", str(args.limit)]

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = ci_stats.main(cmd)
        except SystemExit as e:  # pragma: no cover — güvenlik ağı
            rc = e.code if isinstance(e.code, int) else 1

    if rc == 0:
        print(f"§9 tablo canlı gh verisiyle güncellendi: {args.doc}")
        return 0

    detail = (err.getvalue() or out.getvalue() or "").strip().splitlines()
    detail = f" — {detail[0]}" if detail else ""
    msg = (f"UYARI: §9 tablo canlı veriyle güncellenemedi{detail} "
           f"({args.doc})")
    if args.strict:
        print(msg, file=sys.stderr)
        return 1
    print(msg, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
