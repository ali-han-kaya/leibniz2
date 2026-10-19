#!/usr/bin/env python3
"""smoke_mcp.py — leibniz2_mcp için uçtan-uca MCP istemci testi.

Senaryo A (canlı-mock veya canlı sunucu): varsayılan olarak 127.0.0.1'de
    minimal bir mock preview_server çalıştırır; list_tools + **7 aracın
    hepsi** gerçek MCP stdio transport'uyla çağrılır ve her yanıtın PAYLOAD
    ŞEMASI doğrulanır. MCP_SMOKE_BASE_URL verilirse mock kalkar ve GERÇEK bir
    preview_server'a karşı çalışılır (o zaman değer yerine şekil iddiaları
    doğrulanır).
Senaryo B (kapalı-sunucu): arkada sunucu yokken araç çağrısının actioned
    hata payload'u döndürdüğünü doğrular (fail-closed, kibar mesaj).

Mock SADAKATİ (bu dosyanın en önemli kuralı): mock, gerçek preview_server'ın
sözleşmesini taklit eder, iyimser bir sürümünü değil. `?run=` kabul etmez,
`?ts=` yoksa 400 döner (gerçek serve_run_stdout gibi) — aksi hâlde MCP'deki
`?run=` sözleşme kırılması smoke'ta YEŞİL kalırdı (bu tam olarak bir kez
yaşandı). Aynı nedenle run-history ESKİDEN YENİYE döner, ISO damgası
`+00:00` taşır: ham `+` sorgu dizesinde boşluğa çözüldüğü için kaçırma
(URL-encoding) hatası da burada yakalanır.
"""
import asyncio
import http.server
import json
import os
import re
import socket
import sys
import threading
import urllib.parse

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = ["_calisma/mcp/.venv/bin/python", "_calisma/mcp/server.py"]

# Mock verisi — GERÇEK sunucu sözleşmesinin şekline göre.
TS_ISO = "2026-09-18T10:15:30Z"
TS_OFFSET = "2026-09-18T10:15:30+00:00"  # '+00:00' → sorguda %2B olmalı
RUNS = [  # load_run_logs sırası: ESKİDEN YENİYE
    {"ts": TS_ISO, "verdict": "PASS", "p0": 0, "p1": 1, "duration_s": 12.5},
    {"ts": TS_OFFSET, "verdict": "FAIL", "p0": 1, "p1": 0, "duration_s": 30.0},
]
TOOLS = ["leibniz2_health", "leibniz2_history", "leibniz2_latest",
         "leibniz2_refs_trend", "leibniz2_run_history",
         "leibniz2_run_stdout", "leibniz2_trend"]
VERDICTS = {"PASS", "FAIL", "ERROR", "UNKNOWN"}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _mock_server(port: int):
    """Sözleşmeye sadık mock; `seen` gerçek istek yollarını toplar."""
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            seen.append(self.path)
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)

            def send(code, body, ctype="application/json"):
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            # /api/health JSON DEĞİL, düz metin `ok` döndürür (gerçek sunucu).
            if parsed.path == "/api/health":
                return send(200, b"ok", "text/plain; charset=utf-8")
            if parsed.path == "/api/latest":
                return send(200, {
                    "verdict": "PASS", "ts": TS_ISO, "p0": 0, "p1": 0,
                    "stripped_sha256": "74b2" + "0" * 60,
                    "z3": {"pass": 12, "total": 12},
                })
            if parsed.path == "/api/trend":
                limit = (qs.get("limit") or [None])[0]
                return send(200, {
                    "history": RUNS,
                    "refs_trend": {"rows": [{"ts": TS_ISO}]},
                    "limit": int(limit) if limit else None,
                })
            if parsed.path == "/api/history":
                return send(200, [{"ts": TS_ISO, "verdict": "PASS", "p0": 0},
                                  {"ts": TS_OFFSET, "verdict": "FAIL", "p0": 1}])
            if parsed.path == "/api/refs-trend":
                return send(200, {"rows": [{"ts": TS_ISO, "refs_verified": 12,
                                           "refs_total": 12}]})
            if parsed.path == "/api/run-history":
                return send(200, RUNS)  # eski → yeni (gerçek sıra)
            if parsed.path == "/api/run-stdout":
                # Gerçek serve_run_stdout: `?ts=` yoksa 400, bilinmeyen ts 404.
                # `?run=` DESTEKLENMEZ — desteklenirse MCP'deki kırılma gizlenir.
                ts = (qs.get("ts") or [None])[0]
                if not ts:
                    return send(400, {"error": "?ts= gerekli"})
                if ts not in {r["ts"] for r in RUNS}:
                    return send(404, {"error": "run bulunamadı: " + ts})
                return send(200, {"ts": ts, "stdout": "verify stdout for " + ts,
                                  "stderr": ""})
            return send(404, {"error": "rota yok: " + parsed.path})

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


# ── payload şema doğrulayıcılar ─────────────────────────────────────────────

def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _nonempty_str(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _hex64(v) -> bool:
    return isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) is not None


def _shape(tool: str, p, mock: bool) -> list:
    """Araç payload'u için şema ihlalleri listesi (boş = geçerli).

    `mock=True` değer iddialarını da denetler; canlı modda yalnız ŞEKİL
    doğrulanır (gerçek koşumun verdict'i PASS olmak zorunda değildir).
    """
    if p is None:
        return ["yanıt JSON değil"]
    if isinstance(p, dict) and "error" in p:
        return ["hata payload'u (araç çökmedi, sözleşme karşılanmadı): %s"
                % str(p["error"])[:180]]
    bad = []
    if tool == "leibniz2_latest":
        if not isinstance(p, dict):
            return ["nesne değil: %r" % type(p).__name__]
        if p.get("verdict") not in VERDICTS:
            bad.append("verdict geçersiz: %r" % (p.get("verdict"),))
        if not _nonempty_str(p.get("ts")):
            bad.append("ts boş/eksik")
        for k in ("p0", "p1"):
            if not (_is_int(p.get(k)) or p.get(k) is None):
                bad.append("%s int değil: %r" % (k, p.get(k)))
        if mock:
            if p.get("verdict") != "PASS":
                bad.append("mock verdict PASS değil")
            z3 = p.get("z3")
            if not (isinstance(z3, dict) and _is_int(z3.get("pass"))
                    and _is_int(z3.get("total"))):
                bad.append("z3 {pass,total} int değil: %r" % (z3,))
    elif tool == "leibniz2_trend":
        if not isinstance(p, dict):
            return ["nesne değil: %r" % type(p).__name__]
        if not isinstance(p.get("history"), list):
            bad.append("history liste değil")
        rt = p.get("refs_trend")
        if not (isinstance(rt, dict) and isinstance(rt.get("rows"), list)):
            bad.append("refs_trend.rows liste değil")
        if mock:
            if p.get("limit") != 5:
                bad.append("limit yankısı 5 değil: %r" % (p.get("limit"),))
            if len(p.get("history") or []) != len(RUNS):
                bad.append("history satır sayısı %d değil" % len(RUNS))
    elif tool == "leibniz2_history":
        if not isinstance(p, list):
            return ["liste değil: %r" % type(p).__name__]
        if not all(isinstance(r, dict) for r in p):
            bad.append("satırlar nesne değil")
        if p and not all("ts" in r for r in p):
            bad.append("satırlarda ts alanı yok")
        if mock and len(p) != 2:
            bad.append("satır sayısı 2 değil: %d" % len(p))
    elif tool == "leibniz2_refs_trend":
        if not isinstance(p, dict):
            return ["nesne değil: %r" % type(p).__name__]
        if not isinstance(p.get("rows"), list):
            bad.append("rows liste değil")
        if mock:
            rows = p.get("rows") or []
            if not rows or rows[0].get("refs_total") != 12:
                bad.append("rows[0].refs_total 12 değil: %r" % (rows[:1],))
    elif tool == "leibniz2_run_history":
        if not isinstance(p, list):
            return ["liste değil: %r" % type(p).__name__]
        if not all(isinstance(r, dict) for r in p):
            bad.append("koşum satırları nesne değil")
        if p and not all("ts" in r for r in p):
            bad.append("koşum satırlarında ts alanı yok")
        if mock:
            got = [r.get("ts") for r in p]
            if got != [r["ts"] for r in RUNS]:
                bad.append("sıra eski→yeni değil: %r" % (got,))
    elif tool == "leibniz2_run_stdout":
        if not isinstance(p, dict):
            return ["nesne değil: %r" % type(p).__name__]
        for k, ok in (("ts", _nonempty_str), ("stdout", lambda v: isinstance(v, str)),
                      ("stderr", lambda v: isinstance(v, str))):
            if not ok(p.get(k)):
                bad.append("%s alanı geçersiz: %r" % (k, p.get(k)))
    else:
        bad.append("bilinmeyen araç: %s" % tool)
    return bad


def _report(tool: str, payload, mock: bool, extra_note: str = "") -> bool:
    bad = _shape(tool, payload, mock)
    if bad:
        print("FAIL %s: %s" % (tool, "; ".join(bad)))
        return False
    note = extra_note or ("şema geçerli (mock değerleri)" if mock
                          else "şema geçerli (canlı)")
    print("OK %s: %s" % (tool, note))
    return True


async def main() -> int:
    ok = True

    # ── Senaryo A: canlı sunucu (MCP_SMOKE_BASE_URL) veya mock ──
    live_base = os.environ.get("MCP_SMOKE_BASE_URL", "").strip()
    using_mock = not live_base
    if using_mock:
        port = _free_port()
        srv, seen = _mock_server(port)
        target = f"http://127.0.0.1:{port}"
        print(f"[senaryo A] mock sunucu: {target}")
    else:
        srv, seen = None, []
        target = live_base
        print(f"[senaryo A] canlı sunucu: {target}")
    params = StdioServerParameters(command=SERVER[0], args=[SERVER[1]],
                                   env={"LEIBNIZ2_MCP_BASE_URL": target})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            if names != TOOLS:
                print("FAIL list_tools:", names)
                ok = False
            else:
                print(f"OK list_tools: {len(names)} araç — salt-okuma seti birebir")

            # MCP 2.x istemci modelleri snake_case'dir (read_only_hint); camelCase
            # sürüklemesi (readOnlyHint) alanı sessizce None bırakır. Her araç
            # için alan açıkça True olmalı — eksik/None/False kapalı (fail-closed).
            ro_bad = [t.name for t in tools.tools
                      if getattr(t.annotations, "read_only_hint", None) is not True]
            if ro_bad:
                print("FAIL annotations.read_only_hint (snake_case):", ro_bad)
                ok = False
            else:
                print(f"OK annotations.read_only_hint: {len(tools.tools)} araç True (snake_case alan)")

            async def call(name, args=None):
                res = await session.call_tool(name, args or {})
                try:
                    return json.loads(res.content[0].text)
                except json.JSONDecodeError:
                    return None

            # 1) health — düz metin ucu MCP tarafından {reachable, body}'ye sarılır.
            hp = await call("leibniz2_health")
            if isinstance(hp, dict) and hp.get("reachable") is True \
                    and hp.get("body") == "ok":
                print("OK leibniz2_health: reachable=true, body=ok (düz metin ucu)")
            else:
                print("FAIL leibniz2_health:", hp)
                ok = False

            # 2) latest
            ok &= _report("leibniz2_latest", await call("leibniz2_latest"), using_mock,
                          "verdict=PASS, p0/p1 int, ts dolu, z3 12/12 (mock)"
                          if using_mock else "")

            # 3) trend (?limit= yankısı dahil)
            ok &= _report("leibniz2_trend", await call("leibniz2_trend", {"limit": 5}),
                          using_mock)

            # 4) history
            ok &= _report("leibniz2_history", await call("leibniz2_history", {"limit": 5}),
                          using_mock)

            # 5) refs-trend
            ok &= _report("leibniz2_refs_trend",
                          await call("leibniz2_refs_trend", {"limit": 5}), using_mock)

            # 6) run-history
            rh = await call("leibniz2_run_history", {"limit": 5})
            ok &= _report("leibniz2_run_history", rh, using_mock)

            # 7) run-stdout — SÖZLEŞME KIRILMASININ PİNİ: kimlik `ts`'tir.
            # Açık kimlik olarak EN ESKİ koşum seçilir: argüman yok sayılırsa
            # araç "en yeni"ye düşer ve bu sessiz düşüş yakalanır (aynı ts'i
            # seçmek testi kendi kendine doğrular hâle getirirdi).
            newest_ts = None
            if isinstance(rh, list) and rh and isinstance(rh[-1], dict):
                newest_ts = rh[-1].get("ts")
            oldest_ts = None
            if isinstance(rh, list) and rh and isinstance(rh[0], dict):
                oldest_ts = rh[0].get("ts")
            explicit_ts = TS_ISO if using_mock else oldest_ts
            if not _nonempty_str(explicit_ts):
                print("SKIP leibniz2_run_stdout: run geçmişinde kullanılabilir ts yok")
            else:
                rs = await call("leibniz2_run_stdout", {"ts": explicit_ts})
                good = _report("leibniz2_run_stdout", rs, using_mock,
                               "ts=%s ile okundu (açık kimlik, en eski koşum)"
                               % explicit_ts)
                if not isinstance(rs, dict) or rs.get("ts") != explicit_ts:
                    print("FAIL leibniz2_run_stdout: dönen ts istenen ts değil: %r"
                          % (rs.get("ts") if isinstance(rs, dict) else rs,))
                    good = False
                ok &= good

                # Argümansız çağrı = EN YENİ koşum. Sunucu run-history'yi
                # eskiden-yeniye döndürdüğü için en yeni = SON satır.
                newest = TS_OFFSET if using_mock else newest_ts
                rs0 = await call("leibniz2_run_stdout")
                good0 = _report("leibniz2_run_stdout", rs0, using_mock,
                                "argümansız → en yeni ts (%s)" % newest)
                if not isinstance(rs0, dict) or rs0.get("ts") != newest:
                    print("FAIL leibniz2_run_stdout (argümansız): en yeni ts "
                          "dönmedi: %r (beklenen %r)"
                          % (rs0.get("ts") if isinstance(rs0, dict) else rs0, newest))
                    good0 = False
                ok &= good0

            if using_mock:
                # İstek düzeyi pinler: `?ts=` kullanıldı, `?run=` YOK, ve
                # '+00:00' kaçırıldı (%2B) — ham '+' boşluğa çözülürdü.
                stdout_calls = [p for p in seen if p.startswith("/api/run-stdout")]
                if not stdout_calls or not all("ts=" in p for p in stdout_calls):
                    print("FAIL run-stdout istekleri ?ts= taşımıyor:", stdout_calls)
                    ok = False
                elif not any("%2B" in p for p in stdout_calls):
                    print("FAIL run-stdout '+00:00' kaçırılmadı (URL-encode yok):",
                          stdout_calls)
                    ok = False
                elif any("/api/run-stdout?run=" in p for p in seen):
                    print("FAIL run-stdout hâlâ ?run= gönderiyor")
                    ok = False
                else:
                    print("OK run-stdout istekleri: ?ts= URL-encoded ('+' → %2B) — "
                          "?run= yok")

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

    print("SONUÇ:", "TÜM SENARYOLAR YEŞİL (7/7 araç + şema)" if ok else "KIRMIZI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
