#!/usr/bin/env python3
"""leibniz2_mcp — Stoic-Hume V5 doğrulama zinciri için salt-okuma MCP sunucusu.

preview_server.py'nin HTTP API'sini (127.0.0.1:8000) LLM dostu araçlara sarmalar.
Kapsam bilinçli olarak salt-okuma: run-now/stop gibi state-changing uçlar
bilinçli olarak dışarıda (LLM'e koşum tetikleme yetkisi verilmez).

Çalıştırma (stdio):
    _calisma/mcp/.venv/bin/python server.py

Uçlar (tümü GET, preview_server sözleşmesi):
    /api/latest, /api/trend, /api/history, /api/refs-trend,
    /api/run-history, /api/run-stdout?ts=<ISO>, /api/health

Koşum kimliği `ts`'tir (ISO zaman damgası): sunucu `run-<safe-ts>.json`
dosyalarını bu damgadan türetir, ayrı bir "run id" yoktur. Kimlikler
`leibniz2_run_history` çıktısının `ts` alanından gelir.

İstemci yapılandırması (ör. Claude Desktop):
    "leibniz2": {
      "command": "~/Desktop/leibniz2/_calisma/mcp/.venv/bin/python",
      "args": ["~/Desktop/leibniz2/_calisma/mcp/server.py"]
    }
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Annotated

from pydantic import Field
from mcp.server.mcpserver import MCPServer

# Varsayılan hedef kararlı: localhost:8000. LEIBNIZ2_MCP_BASE_URL yalnızca
# test dikişidir (smoke_mcp.py mock sunucuyu bağlar); kullanıcı yüzeyi için
# sözleşme sabittir.
BASE_URL = os.environ.get("LEIBNIZ2_MCP_BASE_URL", "http://127.0.0.1:8000")

mcp = MCPServer("leibniz2_mcp")


# ── paylaşılan yardımcılar ──────────────────────────────────────────────────

class _ApiUpstreamError(Exception):
    """preview_server'a ulaşılamadı veya hata döndü."""


def _api_get(path: str, timeout: float = 10.0, expect_json: bool = True) -> dict | str:
    """preview_server'a GET. Varsayılan JSON bekler; `expect_json=False` ham
    gövde metnini döndürür. Gerekçe: /api/health JSON DEĞİL, düz metin `ok`
    döndürüyor (ölçüldü: `Content-Type: text/plain; charset=utf-8`, gövde
    `ok`) — koşulsuz json.loads bu ucu canlı sunucuda her zaman hata
    payload'ına çeviriyordu. Hatalar _ApiUpstreamError'a sarılır."""
    url = BASE_URL + path
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if expect_json else raw
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise _ApiUpstreamError(
            f"HTTP {e.code} from {url}: {detail}. Rota sözleşmesini kontrol edin "
            f"(bkz. _calisma/CIKTI/preview_server.py _route)."
        ) from e
    except urllib.error.URLError as e:
        raise _ApiUpstreamError(
            f"preview_server'a ulaşılamadı ({url}): {e.reason}. Sunucu kapalı "
            f"olabilir — başlatmak için: python3 _calisma/CIKTI/preview_server.py "
            f"--preview-dir _calisma/CIKTI --port 8000"
        ) from e
    except json.JSONDecodeError as e:
        raise _ApiUpstreamError(
            f"{url} JSON döndürmedi: {e}. Uç bozulmuş olabilir; "
            f"leibniz2_health ile doğrulayın."
        ) from e


def _tool_error(msg: str) -> str:
    """Tek-şekilli hata payload'u; mesajlar actioned (sonraki adım önerir)."""
    return json.dumps({"error": msg}, ensure_ascii=False, indent=2)


def _latest_run_ts() -> str:
    """run-history'nin EN YENİ kaydının `ts` değeri.

    `serve_run_history` kayıtları ESKİDEN YENİYE döndürür (`load_run_logs`
    sırası korunur) — "son koşum" `data[-1]`dir; `data[0]` en ESKİ koşumdur.
    Bu ayrım yanlış tarafa düşerse araç sessizce eski bir koşumun günlüğünü
    "son koşum" diye döndürür.
    """
    data = _api_get("/api/run-history")
    if not isinstance(data, list) or not data:
        raise _ApiUpstreamError(
            "run geçmişi boş — hangi koşumun çıktısı istendiğini `ts` ile verin "
            "(kimlikler leibniz2_run_history çıktısındaki `ts` alanındadır).")
    newest = data[-1]
    ts = newest.get("ts") if isinstance(newest, dict) else None
    if not isinstance(ts, str) or not ts.strip():
        raise _ApiUpstreamError(
            "run geçmişindeki en yeni kayıtta `ts` yok — `ts` parametresiyle "
            "açık kimlik verin (leibniz2_run_history).")
    return ts


# ── girdi şeması ─────────────────────────────────────────────────────────────
#
# DÜZ argümanlar (iç içe `params` modeli DEĞİL): tek-model parametresi
# yayınlanan inputSchema'yı {"properties": {"params": {…}}} yapıyordu — LLM
# istemcileri doğal düz çağrıyı ({"limit": 5}) gönderince argüman sessizce
# YOK SAYILIYOR, araç varsayılana düşüyordu (ölçüldü: limit=5 → limit=20).
# Düz imza + Annotated/Field, doğrulamayı koruyup şemayı düzleştirir.
LimitArg = Annotated[int, Field(
    ge=1, le=200, description="Döndürülecek azami kayıt sayısı (son N).")]

RunStdoutArg = Annotated[str | None, Field(
    max_length=64,
    description="Koşum zaman damgası (ISO, ör. '2026-09-18T10:15:30+00:00'), "
                "leibniz2_run_history çıktısındaki `ts` alanı. Boşsa EN YENİ "
                "koşumun çıktısı döner.")]


# ── araçlar (params opsiyonel: argümansız çağrı MCP istemcileri için doğal) ──

@mcp.tool(
    name="leibniz2_latest",
    annotations={
        "title": "Son koşum verdict snapshot'ı",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": False,
    },
)
def leibniz2_latest() -> str:
    """Son doğrulama koşumunun tam snapshot'ı: verdict (PASS/FAIL), P0/P1 bulguları,
    Z3 önerme sayıları, bütçe, deterministik PDF hash'i (stripped_sha256) ve katman
    durumları. Verdict'in neden PASS/FAIL olduğunu anlamak için ilk çağrılacak araç."""
    try:
        data = _api_get("/api/latest")
    except _ApiUpstreamError as e:
        return _tool_error(str(e))
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool(
    name="leibniz2_trend",
    annotations={
        "title": "Koşum trendi",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": False,
    },
)
def leibniz2_trend(limit: LimitArg = 20) -> str:
    """Son N koşumun trend kayıtları (P0/P1 sayıları, süre, bütçe, Z3 toplamları).
    Regression/bütçe-şişmesi analizinde kullanılır."""
    try:
        data = _api_get(f"/api/trend?limit={limit}")
    except _ApiUpstreamError as e:
        return _tool_error(str(e))
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool(
    name="leibniz2_history",
    annotations={
        "title": "Snapshot geçmişi",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": False,
    },
)
def leibniz2_history(limit: LimitArg = 20) -> str:
    """Snapshot geçmişi: verdict'lerin zaman içindeki değişimi (son N)."""
    try:
        data = _api_get(f"/api/history?limit={limit}")
    except _ApiUpstreamError as e:
        return _tool_error(str(e))
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool(
    name="leibniz2_refs_trend",
    annotations={
        "title": "Referans-denetim trendi",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": False,
    },
)
def leibniz2_refs_trend(limit: LimitArg = 20) -> str:
    """Referans denetimi (K6-REF) trend kayıtları — kaynak/kanıt hattındaki sapmalar."""
    try:
        data = _api_get(f"/api/refs-trend?limit={limit}")
    except _ApiUpstreamError as e:
        return _tool_error(str(e))
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool(
    name="leibniz2_run_history",
    annotations={
        "title": "Koşum kayıtları",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": False,
    },
)
def leibniz2_run_history(limit: LimitArg = 20) -> str:
    """Koşum kayıt listesi (zaman damgaları, sonuçlar), ESKİDEN YENİYE. Belirli
    bir koşumun çıktısı için buradaki `ts` alanını leibniz2_run_stdout'a verin."""
    try:
        data = _api_get(f"/api/run-history?limit={limit}")
    except _ApiUpstreamError as e:
        return _tool_error(str(e))
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool(
    name="leibniz2_run_stdout",
    annotations={
        "title": "Koşum çıktısı",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": False,
    },
)
def leibniz2_run_stdout(ts: RunStdoutArg = None) -> str:
    """Belirli bir koşumun (veya EN YENİ koşumun) ham stdout/stderr çıktısı. Kapı
    kırılmalarının gerçek günlüklerini görmek için kullanılır; kimlik listesi
    leibniz2_run_history'nin `ts` alanıdır.

    Sunucu sözleşmesi `?ts=<ISO>` (bkz. serve_run_stdout); `?run=` sunucuda
    yoktur ve argümansız istek 400 döner. Değer URL-encode edilir: ISO
    damgaları `+00:00` taşır ve ham `+` sorgu dizesinde BOŞLUĞA çözülür —
    kodlanmazsa dosya adı eşleşmez (404).
    """
    try:
        ts = ts or _latest_run_ts()
        data = _api_get("/api/run-stdout?ts=" + urllib.parse.quote(ts, safe=""))
    except _ApiUpstreamError as e:
        return _tool_error(str(e))
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool(
    name="leibniz2_health",
    annotations={
        "title": "Sunucu sağlığı",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": False,
    },
)
def leibniz2_health() -> str:
    """preview_server sağlık ucu: bağlantı ve temel durum. Diğer araçlar hata
    verdiğinde altyapıyı doğrulamak için kullanılır.

    Uç JSON döndürmez, düz metin `ok` döndürür; bu yüzden gövde ham
    okunur (expect_json=False). Erişilebilirlik `reachable` alanıyla, ham
    gövde `body` alanıyla raporlanır — erişilemiyorsa _tool_error devreye
    girer, yani `reachable` ancak gerçekten bağlandığımızda true'dur.
    """
    try:
        body = _api_get("/api/health", expect_json=False)
    except _ApiUpstreamError as e:
        return _tool_error(str(e))
    return json.dumps({"reachable": True, "body": str(body).strip()},
                      ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
