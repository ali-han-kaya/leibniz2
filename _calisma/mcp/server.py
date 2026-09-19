#!/usr/bin/env python3
"""leibniz2_mcp — Stoic-Hume V5 doğrulama zinciri için salt-okuma MCP sunucusu.

preview_server.py'nin HTTP API'sini (127.0.0.1:8000) LLM dostu araçlara sarmalar.
Kapsam bilinçli olarak salt-okuma: run-now/stop gibi state-changing uçlar
bilinçli olarak dışarıda (LLM'e koşum tetikleme yetkisi verilmez).

Çalıştırma (stdio):
    _calisma/mcp/.venv/bin/python server.py

Uçlar (tümü GET, preview_server sözleşmesi):
    /api/latest, /api/trend, /api/history, /api/refs-trend,
    /api/run-history, /api/run-stdout, /api/health

İstemci yapılandırması (ör. Claude Desktop):
    "leibniz2": {
      "command": "~/Desktop/leibniz2/_calisma/mcp/.venv/bin/python",
      "args": ["~/Desktop/leibniz2/_calisma/mcp/server.py"]
    }
"""
import json
import os
import urllib.error
import urllib.request

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# Varsayılan hedef kararlı: localhost:8000. LEIBNIZ2_MCP_BASE_URL yalnızca
# test dikişidir (smoke_mcp.py mock sunucuyu bağlar); kullanıcı yüzeyi için
# sözleşme sabittir.
BASE_URL = os.environ.get("LEIBNIZ2_MCP_BASE_URL", "http://127.0.0.1:8000")

mcp = FastMCP("leibniz2_mcp")


# ── paylaşılan yardımcılar ──────────────────────────────────────────────────

class _ApiUpstreamError(Exception):
    """preview_server'a ulaşılamadı veya hata döndü."""


def _api_get(path: str, timeout: float = 10.0) -> dict:
    """preview_server'a GET; JSON bekler. Hatalar _ApiUpstreamError'a sarılır."""
    url = BASE_URL + path
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
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


# ── girdi modelleri ──────────────────────────────────────────────────────────

class _Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _RunStdoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run: str | None = Field(
        default=None, max_length=64,
        description="Koşum kimliği (ör. '20260918-101530'). Boşsa son koşumun "
                    "çıktısı döner. Geçerli kimlikler leibniz2_run_history ile listelenir.")


class _LimitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(
        default=20, ge=1, le=200,
        description="Döndürülecek azami kayıt sayısı (son N).")


# ── araçlar (params opsiyonel: argümansız çağrı MCP istemcileri için doğal) ──

@mcp.tool(
    name="leibniz2_latest",
    annotations={
        "title": "Son koşum verdict snapshot'ı",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": False,
    },
)
def leibniz2_latest(params: _Empty | None = None) -> str:
    """Son doğrulama koşumunun tam snapshot'ı: verdict (PASS/FAIL), P0/P1 bulguları,
    Z3 önerme sayıları, bütçe, deterministik PDF hash'i (stripped_sha256) ve katman
    durumları. Verdict'in neden PASS/FAIL olduğunu anlamak için ilk çağrılacak araç."""
    params = params or _Empty()
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
def leibniz2_trend(params: _LimitInput | None = None) -> str:
    """Son N koşumun trend kayıtları (P0/P1 sayıları, süre, bütçe, Z3 toplamları).
    Regression/bütçe-şişmesi analizinde kullanılır."""
    params = params or _LimitInput()
    try:
        data = _api_get(f"/api/trend?limit={params.limit}")
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
def leibniz2_history(params: _LimitInput | None = None) -> str:
    """Snapshot geçmişi: verdict'lerin zaman içindeki değişimi (son N)."""
    params = params or _LimitInput()
    try:
        data = _api_get(f"/api/history?limit={params.limit}")
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
def leibniz2_refs_trend(params: _LimitInput | None = None) -> str:
    """Referans denetimi (K6-REF) trend kayıtları — kaynak/kanıt hattındaki sapmalar."""
    params = params or _LimitInput()
    try:
        data = _api_get(f"/api/refs-trend?limit={params.limit}")
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
def leibniz2_run_history(params: _LimitInput | None = None) -> str:
    """Koşum kayıt listesi (kimlikler, zamanlar, sonuçlar). Belirli bir koşumun
    çıktısını okumak için önce buradan kimlik alın, sonra leibniz2_run_stdout kullanın."""
    params = params or _LimitInput()
    try:
        data = _api_get(f"/api/run-history?limit={params.limit}")
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
def leibniz2_run_stdout(params: _RunStdoutInput | None = None) -> str:
    """Belirli bir koşumun (veya sonuncunun) ham stdout çıktısı. Kapı kırılmalarının
    gerçek günlüklerini görmek için kullanılır; kimlik listesi için leibniz2_run_history."""
    params = params or _RunStdoutInput()
    q = f"?run={params.run}" if params.run else ""
    try:
        data = _api_get(f"/api/run-stdout{q}")
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
def leibniz2_health(params: _Empty | None = None) -> str:
    """preview_server sağlık ucu: bağlantı ve temel durum. Diğer araçlar hata
    verdiğinde altyapıyı doğrulamak için kullanılır."""
    params = params or _Empty()
    try:
        data = _api_get("/api/health")
    except _ApiUpstreamError as e:
        return _tool_error(str(e))
    return json.dumps(data, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
