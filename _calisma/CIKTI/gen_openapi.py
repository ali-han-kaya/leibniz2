#!/usr/bin/env python3
"""gen_openapi.py — OpenAPI 3.1 şeması üretici (tek-kaynak: API_CONTRACT).

API_CONTRACT (test_api_method_contract'ta pinli tablo) → preview_server
yüzeyinin makine-okunur sözleşmesi. Üretim SAF ve DETERMİNİSTİKTİR
(anahtar-sıralı) — aynı sözleşme aynı baytları verir; test_openapi_schema
diskteki openapi.json ile üretilen şemayı birebir karşılaştırır (drift
fail-closed).

Kullanım:
  python3 gen_openapi.py            # openapi.json'ı üret + yaz
  python3 gen_openapi.py --check    # disk bayat mı? (drift → rc 1)

Deprecation politikası (docs/API_VERSIONING.md): deprecated işareti
x-deprecated-since + x-sunset İKİLİSİ olmadan konulamaz (şema-yapan
test kızarır). Şu an deprecated uç yok.
"""
import argparse
import json
import os
import pathlib
import sys

CIKTI = pathlib.Path(__file__).resolve().parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

from test_api_method_contract import API_CONTRACT, SSE_PATHS  # noqa: E402

HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch",
                          "options", "trace", "head"})

JSON_RESP = {"description": "JSON yanıt",
             "content": {"application/json": {"schema": {"type": "object"}}}}

# Endpoint-başına davranış-notları: 405/404/501 ayrımını OpenAPI'ye taşı.
# Anahtar: sözleşme-yolu; değer: operasyon-düzeyi description ekleri.
_BEHAVIOR = {
    "/api/run-now": "POST-only: GET → 405 + Allow: POST (tetikleme asla GET).",
    "/api/stop": "POST-only: GET → 405. Peer/Host kapıları: izinli-küme "
                 "dışı kaynak 403 (PREVIEW_STOP_ALLOWLIST ile genişler).",
    "/api/run": "SSE akışı: text/event-stream; bağlantı uzun ömürlü.",
    "/api/run-stream": "SSE akışı: text/event-stream.",
    "/api/run-stdout": "Veri-bağımlı: ts bulunamazsa alan-404 "
                       "(routing-404'ten farklı gövde).",
}


def generate():
    """Sözleşmeden OpenAPI 3.1 sözlüğü üretir (saf, deterministik)."""
    paths = {}
    for path in sorted(API_CONTRACT):
        methods = API_CONTRACT[path]
        item = {}
        for method in sorted(m.lower() for m in methods):
            op = {
                "summary": f"{method.upper()} {path}",
                "operationId": path.strip("/").replace("/", "_") + "_" + method,
                "responses": {},
            }
            if path in _BEHAVIOR:
                op["description"] = _BEHAVIOR[path]
            if path in SSE_PATHS and method == "get":
                op["responses"]["200"] = {
                    "description": "SSE akışı",
                    "content": {"text/event-stream": {"schema": {
                        "type": "string"}}},
                }
            else:
                ok = "202" if path == "/api/stop" else "200"
                op["responses"][ok] = dict(JSON_RESP)
                if path == "/api/run-now" and method == "post":
                    op["responses"]["409"] = dict(JSON_RESP)
                if path == "/api/stop" and method == "post":
                    op["responses"]["403"] = dict(JSON_RESP)
                    op["responses"]["503"] = dict(JSON_RESP)
                op["responses"]["404"] = dict(JSON_RESP)
            item[method] = op
        paths[path] = item

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "leibniz2 preview dashboard API",
            "version": "1.0.0",
            "description": (
                "Dashboard API sözleşmesi — tek kaynak "
                "test_api_method_contract.API_CONTRACT; bu şema ondan "
                "üretilir (python3 gen_openapi.py). Yöntem-sözleşmesi: "
                "405 = bilinçli metot-reddi (Allow başlığıyla), 404 = "
                "bilinmeyen yol / dağıtım-dışı POST, 501 = do_<METHOD> "
                "tanımsız (desteklenmeyen metot). Sürümleme ve "
                "deprecation: docs/API_VERSIONING.md; PREVIEW_API_VERSION "
                "env'i şema-sürümünü dışarıdan bildirir."
            ),
        },
        "servers": [{"url": "http://127.0.0.1:{port}",
                     "description": "preview_server (varsayılan bind "
                                    "loopback; sandbox-dışı ortamlar için "
                                    "PREVIEW_STOP_ALLOWLIST'e bakın)",
                     "variables": {"port": {"default": "8000"}}}],
        "paths": paths,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="OpenAPI şeması üretici")
    ap.add_argument("--check", action="store_true",
                    help="diskteki şema üretim-çıktısıyla aynı mı (drift rc=1)")
    ap.add_argument("--output", default=str(CIKTI / "openapi.json"))
    args = ap.parse_args(argv)

    spec = generate()
    rendered = json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.check:
        disk = pathlib.Path(args.output)
        if not disk.exists():
            print(f"ŞEMA YOK: {args.output} — üretin: python3 {__file__}")
            return 1
        if disk.read_text(encoding="utf-8") != rendered:
            print("ŞEMA BAYAT — API_CONTRACT ile yeniden üretin: "
                  f"python3 {__file__}")
            return 1
        print(f"openapi.json güncel ({len(spec['paths'])} yol)")
        return 0
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(rendered)
    print(f"openapi.json yazıldı ({len(spec['paths'])} yol): {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
