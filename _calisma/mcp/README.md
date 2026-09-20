# leibniz2 MCP — Stoic-Hume V5 doğrulama zinciri (salt-okuma)

`preview_server.py`'nin HTTP API'sini LLM araçlarına saran **stdio MCP sunucusu**.
Amaç: bir LLM istemcisi (Claude Desktop, VS Code Copilot MCP vb.) doğrulama
zincirinin verdict'ini, trendini ve koşum günlüklerini doğal dilde sorabilsin.

## Ne yapar

| Araç | Uç | Döndürür |
|---|---|---|
| `leibniz2_latest` | `/api/latest` | Son koşum verdict snapshot'ı (verdict, P0/P1, Z3, bütçe, stripped_sha256) |
| `leibniz2_trend` | `/api/trend?limit=N` | Son N koşumun trend kayıtları |
| `leibniz2_history` | `/api/history?limit=N` | Snapshot/verdict geçmişi |
| `leibniz2_refs_trend` | `/api/refs-trend?limit=N` | K6-REF referans-denetim trendi |
| `leibniz2_run_history` | `/api/run-history?limit=N` | Koşum kimlikleri ve sonuçları |
| `leibniz2_run_stdout` | `/api/run-stdout[?run=ID]` | Belirli koşumun ham stdout günlüğü |
| `leibniz2_health` | `/api/health` | Sunucu sağlığı / altyapı doğrulaması |

**Kapsam bilinçli salt-okuma:** `run-now`/`stop` (state-changing, POST-only) uçları
LLM'e açılmaz — bir asistan doğrulama koşumu tetikleyemez, yalnız okur.

## Kurulum

```bash
cd _calisma/mcp
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`mcp` SDK **`<2` pinn** (FastMCP yüzeyi 2.x'te `MCPServer`'a göç etti;
bkz. migration guide). Sunucu skill-rehberindeki v1 desenini izler.

## Sunucuyu başlatma (önkoşul)

MCP sunucusu, preview_server'a (varsayılan `127.0.0.1:8000`) bağlanır:

```bash
python3 _calisma/CIKTI/preview_server.py --preview-dir _calisma/CIKTI --port 8000
```

Sunucu kapalıyken araçlar **fail-closed** çalışır: kibar, actioned hata
payload'u döndürür (başlatma komutunu önerir).

## İstemciye bağlama

Örnek Claude Desktop `claude_desktop_config.json` parçası:

```json
{
  "mcpServers": {
    "leibniz2": {
      "command": "~/Desktop/leibniz2/_calisma/mcp/.venv/bin/python",
      "args": ["~/Desktop/leibniz2/_calisma/mcp/server.py"]
    }
  }
}
```

## Test

```bash
_calisma/mcp/.venv/bin/python _calisma/mcp/smoke_mcp.py
```

Üç senaryo: (A) mock sunucuya karşı gerçek MCP stdio istemcisiyle
`list_tools` + araç çağrıları, (B) `limit` parametresinin Pydantic
doğrulaması, (C) kapalı-sunucu actioned-hata sözleşmesi.

## Değerlendirme (Faz 4)

`evals.xml` — 10 bağımsız, salt-okuma, doğrulanabilir soru; LLM'in araç
setiyle gerçek soruları yanıtlayabilmesini ölçer.
