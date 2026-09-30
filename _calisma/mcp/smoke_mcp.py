#!/usr/bin/env python3
"""smoke_mcp.py — leibniz2_mcp için uçtan-uca MCP istemci testi.

Senaryo A (canlı-mock veya canlı sunucu): varsayılan olarak 127.0.0.1'de
    minimal bir mock preview_server çalıştırır; list_tools + health/latest/
    trend çağrılarını gerçek MCP stdio transport'uyla sınar. MCP_SMOKE_BASE_URL
    verilirse mock kalkar ve GERÇEK bir preview_server'a karşı çalışılır
    (o zaman değer yerine şekil iddiaları doğrulanır).
Senaryo B (kapalı-sunucu): arkada sunucu yokken araç çağrısının actioned
    hata payload'u döndürdüğünü doğrular (fail-closed, kibar mesaj).
"""
import asyncio
import json
import os
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
            # Sözleşme sadakati: gerçek preview_server /api/health ucu JSON
            # DEĞİL, düz metin `ok` döndürüyor (Content-Type: text/plain).
            # Mock her ucu JSON döndürürse, health aracının canlı sunucuda
            # bozuk olduğu (koşulsuz json.loads) smoke'da görünmezdi —
            # ölçüldü ve düzeltildi. Mock bilinçli olarak sadık kırıldı.
            if self.path.startswith("/api/health"):
                body = b"ok"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
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

    # ── Senaryo A: canlı sunucu (MCP_SMOKE_BASE_URL) veya mock ──
    # MCP_SMOKE_BASE_URL verilirse mock KALKAR ve gerçek bir preview_server'a
    # karşı çalışılır; o zaman değer iddiaları yerine ŞEKİL iddiaları
    # kullanılır (gerçek koşumun verdict'i PASS olmak zorunda değildir).
    # Verilmezse varsayılan hermetik mock yolu çalışır (CI kapısı).
    live_base = os.environ.get("MCP_SMOKE_BASE_URL", "").strip()
    using_mock = not live_base
    if using_mock:
        port = _free_port()
        srv = _mock_server(port)
        target = f"http://127.0.0.1:{port}"
        print(f"[senaryo A] mock sunucu: {target}")
    else:
        srv = None
        target = live_base
        print(f"[senaryo A] canlı sunucu: {target}")
    params = StdioServerParameters(command=SERVER[0], args=[SERVER[1]],
                                   env={"LEIBNIZ2_MCP_BASE_URL": target})
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

            # Health ucu: erişilebilir sunucuda reachable=true, gövde 'ok'.
            # (Mock ve canlı sunucu aynı sözleşmeyi paylaşır: düz metin.)
            res = await session.call_tool("leibniz2_health", {})
            hp = json.loads(res.content[0].text)
            if hp.get("reachable") is True and hp.get("body") == "ok":
                print("OK leibniz2_health: reachable=true, body=ok (düz metin ucu)")
            else:
                print("FAIL leibniz2_health:", hp)
                ok = False

            res = await session.call_tool("leibniz2_latest", {})
            payload = json.loads(res.content[0].text)
            if using_mock:
                latest_ok = (payload.get("verdict") == "PASS"
                             and payload.get("z3", {}).get("pass") == 12)
                latest_note = "verdict=PASS, z3 12/12 (mock'tan)"
            else:
                # Gerçek koşum: PASS olmak zorunda değil — sözleşme
                # (verdict kümesi + p0 alanı) doğrulanır.
                latest_ok = (payload.get("verdict") in {"PASS", "FAIL", "ERROR"}
                             and "p0" in payload)
                latest_note = (f"verdict={payload.get('verdict')!r} geçerli kümede, "
                               f"p0 alanı mevcut (canlı)")
            if latest_ok:
                print(f"OK leibniz2_latest: {latest_note}")
            else:
                print("FAIL leibniz2_latest:", payload)
                ok = False

            res = await session.call_tool("leibniz2_trend", {"limit": 5})
            payload = json.loads(res.content[0].text)
            if using_mock:
                trend_ok = payload.get("verdict") == "PASS"
                trend_note = "limit parametresi kabul, yanıt JSON (mock'tan)"
            else:
                trend_ok = "history" in payload or "rows" in payload
                trend_note = "limit parametresi kabul, yanıt liste/nesne (canlı)"
            if trend_ok:
                print(f"OK leibniz2_trend: {trend_note}")
            else:
                print("FAIL leibniz2_trend:", payload)
                ok = False

    if srv is not None:
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
