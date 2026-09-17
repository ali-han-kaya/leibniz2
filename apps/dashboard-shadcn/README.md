# Dashboard

Türkçe, fail-closed doğrulama görünümü; `preview_server.py` API sözleşmesini
kullanır.

```bash
npm install
npm run dev
# production bundle
npm run build
```

Development sırasında `/api/*` istekleri `127.0.0.1:8765` üzerindeki Python
sunucusuna proxy edilir. Uygulama `/api/latest` ile snapshot alır, `/api/run`
SSE kanalını dinler, `POST /api/run-now` ile manuel doğrulama başlatır, `POST /api/stop` ile yerel sunucuyu güvenli biçimde durdurur ve
çalışma geçmişini `/api/run-history` üzerinden gösterir. Snapshot yoksa
`UNKNOWN` gösterilir; UI başarı varsaymaz.
