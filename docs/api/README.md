# docs/api — yayınlanmış API referansı

Bu klasördeki `index.html` **ÜRETİLMİŞ** bir dosyadır: elle düzenlenmez.

```
API_CONTRACT (test_api_method_contract.py)
  → _calisma/CIKTI/gen_openapi.py      → _calisma/CIKTI/openapi.json
  → _calisma/CIKTI/gen_openapi_docs.py → docs/api/index.html
  → sync_verify_mirror.sh              → PREVIEW_DIR/api-docs.html
  → preview_server /api-docs.html
```

## Yeniden üretim

```bash
python3 _calisma/CIKTI/gen_openapi.py        # sözleşme → openapi.json
python3 _calisma/CIKTI/gen_openapi_docs.py  # şema → bu sayfa
```

İkinci komut `openapi.json`'ı okur; sıra tersine çevrilirse sayfa bayat kalır.

## Kapılar

| kapı | neyi bloklar |
|---|---|
| `check-openapi-drift` | `openapi.json` bayat (sözleşmeyle ayrışmış) |
| `check-openapi-docs` | bu sayfa bayat (şemayla ayrışmış) |

İkisi ayrıdır: yalnız şema kapısı, sayfa yeniden üretilmeden commit'i
geçirirdi — yayınlanan referans sessizce eski kalırdı.

## Render notları

- **Redoc CE v2.0.0**, `cdn.redoc.ly`'den **sürüm sabitli** çekilir
  (`latest` kullanılmaz: render commit'ler arasında sessizce kayardı).
- Şemanın kendisi sayfaya **gömülüdür**; CDN'den yalnız render bundle'ı
  gelir. Sayfa çevrimdışı açıldığında Redoc yüklenmez, `<noscript>` bloğu
  kaynak şemayı gösterir.
- Gömülü JSON'da `</` → `<\/` kaçışı uygulanır; aksi hâlde bir
  description'a `</script>` girdiğinde script bloğu erken kapanırdı.
- `Redoc.init` **nesne** alır (`JSON.parse(...)`): string verilirse Redoc
  onu fetch edilecek URL sanıp "Failed to load" basar.

## Görüntüleme

```bash
python3 _calisma/CIKTI/preview_server.py     # daemon yoksa doğrudan
# → http://127.0.0.1:8000/api-docs.html
```
