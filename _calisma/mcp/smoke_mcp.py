#!/usr/bin/env python3
"""smoke_mcp.py — leibniz2_mcp için uçtan-uca MCP istemci testi.

Senaryo A (canlı-mock): 127.0.0.1:8000'de minimal bir mock preview_server
    çalıştırır; list_tools + leibniz2_latest/health/trend çağrılarını gerçek
    MCP stdio transport'uyla sınar.
Senaryo B (kapalı-sunucu): arkada sunucu yokken araç çağrısının actioned
    hata payload'u döndürdüğünü doğrular (fail-closed, kibar mesaj).
"""
import asyncio
import json
import sys
import threading
import functools
import http.server
import socket

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = ["_calisma/mcp/.venv/bin/python", "_calisma/mcp/server.py"]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _mock_server(port: int) -> http.server.ThreadingHTTPServer:
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps({
                "verdict": "PASS",
                "ts": "2026-09-18T10:15:30Z",
                "p0": 0, "p1": 0,
                "stripped_sha256": "74b2cdbdb18fafbf",
                "z3": {"pass": 12, "total": 12},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


async def main() -> int:
    ok = True

    # ── Senaryo A: canlı-mock ──
    port = _free_port()
    srv = _mock_server(port)
    params = StdioServerParameters(command=SERVER[0], args=[SERVER[1]],
                                   env={"LEIBNIZ2_MCP_BASE_URL": f"http://127.0.0.1:{port}"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            expected = {"leibniz2_health", "leibniz2_history", "leibniz2_latest",
                        "leibniz2_refs_trend", "leibniz2_run_history",
                        "leibniz2_run_stdout", "leibniz2_trend"}
            if set(names) != expected:
                print("FAIL list_tools:", names)
                ok = False
            else:
                print(f"OK list_tools: {len(names)} araç — salt-okuma seti birebir")

            res = await session.call_tool("leibniz2_latest", {})
            payload = json.loads(res.content[0].text)
            if payload.get("verdict") == "PASS" and payload.get("z3", {}).get("pass") == 12:
                print("OK leibniz2_latest: verdict=PASS, z3 12/12 (mock'tan)")
            else:
                print("FAIL leibniz2_latest:", payload)
                ok = False

            res = await session.call_tool("leibniz2_trend", {"limit": 5})
            payload = json.loads(res.content[0].text)
            if payload.get("verdict") == "PASS":
                print("OK leibniz2_trend: limit parametresi kabul, yanıt JSON")
            else:
                print("FAIL leibniz2_trend:", payload)
                ok = False

    srv.shutdown()

    # ── Senaryo B: kapalı-sunucu (actioned hata) ──
    dead = _free_port()
    params_dead = StdioServerParameters(
        command=SERVER[0], args=[SERVER[1]],
        env={"LEIBNIZ2_MCP_BASE_URL": f"http://127.0.0.1:{dead}"})
    async with stdio_client(params_dead) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool("leibniz2_latest", {})
            payload = json.loads(res.content[0].text)
            err = payload.get("error", "")
            if "ulaşılamadı" in err and "preview_server.py" in err:
                print("OK kapalı-sunucu: actioned hata (başlatma komutu öneriliyor)")
            else:
                print("FAIL kapalı-sunucu hata mesajı:", err[:160])
                ok = False

    print("SONUÇ:", "TÜM SENARYOLAR YEŞİL" if ok else "KIRMIZI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
