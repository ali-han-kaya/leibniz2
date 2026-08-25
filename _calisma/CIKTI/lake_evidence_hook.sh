#!/bin/sh
# check-lake-evidence: LEAN_ISPAT_RAPORU §6.3 lake build kanıtını her
# committe gerçekten yeniden üretir (fail-closed). lean/lake kurulu
# değilse testler SKIP eder (exit 0) — kapı yalnızca aracın var olduğu
# ortamda iddia üretir; leansiz CI koruması K9-LAKE (--full) içindedir.
set -e

PY=python3
[ -x _calisma/.venv_z3/bin/python ] && PY=_calisma/.venv_z3/bin/python

exec "$PY" -m unittest discover -s _calisma/CIKTI \
    -p "test_lake_evidence_smoke.py" -v
