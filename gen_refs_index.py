#!/usr/bin/env python3
"""refs-index.json üretici - artifact JSON"""
import json, pathlib, datetime
def gen(out="_calisma/CIKTI/refs-index.json"):
    p = pathlib.Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": datetime.datetime.utcnow().isoformat()+"Z",
        "refs": [],
        "source": "azure-search"
    }
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"WROTE {p}")
    return p
if __name__ == "__main__":
    gen()
