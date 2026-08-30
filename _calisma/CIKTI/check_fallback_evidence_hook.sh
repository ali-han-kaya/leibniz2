#!/bin/sh
# check-fallback-evidence: REFERANS_KANIT_DENETIMI.md §5.3 kanıtını
# deterministik/offline yeniden üretir. 5/5 PASS değilse commit bloke edilir.
set -eu

PY=python3
if [ -x "_calisma/.venv_z3/bin/python" ]; then
  PY=_calisma/.venv_z3/bin/python
fi

out="$($PY _calisma/CIKTI/ia_ol_fallback_evidence.py --offline)"
printf '%s\n' "$out"

printf '%s\n' "$out" | grep -Eq 'SONUÇ:[[:space:]]*PASS[[:space:]]+—[[:space:]]+5/5 kaynak' || {
  echo "FAIL: ia_ol_fallback_evidence.py §5.3 kapısı 5/5 PASS değil" >&2
  exit 1
}
