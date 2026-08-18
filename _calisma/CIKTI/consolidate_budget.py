#!/usr/bin/env python3
"""consolidate_budget.py — bütçe sidecar'larını budget/index.json'da topla.

verify.yml'deki 'Consolidate budget report' adımının inline Python mantığının
standalone hali. budget/*.json sidecar'larını okur, limiti aşanları failures
listesine koyar ve budget/index.json özetini üretir.

Kullanım (CI çalışma dizininden — budget/ altı dolu olmalı):
  python3 consolidate_budget.py
"""
import glob
import json
import sys


def main() -> None:
    rows = []
    for p in sorted(glob.glob("budget/*.json")):
        try:
            r = json.load(open(p))
            r["source"] = p.split("/")[-1]
            rows.append(r)
        except Exception as e:
            print(f"skip {p}: {e}", file=sys.stderr)
    failures = [
        {
            "source": r.get("source"),
            "limit": r.get("limit"),
            "estimated_usd": r.get("estimated_usd"),
            "tokens_est": r.get("tokens_est"),
            "method": r.get("method"),
        }
        for r in rows
        if r.get("verdict") != "OK"
    ]
    summary = {
        "tool": "verify_delivery.py bütçe kalkanı",
        "date": rows[0]["date"] if rows else None,
        "method": "v3_verify.py H4 (token ≈ bytes/4, $3/M token + $0.55)",
        "runs": rows,
        "any_fail": bool(failures),
        "failures": failures,
    }
    json.dump(summary, open("budget/index.json", "w"), indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
