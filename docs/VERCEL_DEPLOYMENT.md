# Vercel Deployment — Live CI Dashboard (serverless /api adaptörü)

> Amaç: yerel daemon'un (`_calisma/CIKTI/preview_server.py`) `/api` yüzeyini
> Vercel'in `/api` dizini dosya-tabanlı Python-runtime'ına taşımak —
> **şema-parite ile** (dashboard JS'i değişmeden çalışır). Bu doküman
> `api/_adapter.py` modülünün kardeşidir.

## 1. Tasarım

```
Vercel Edge/Serverless
  api/health.py            → 200 "ok" (düz-metin; yerel birebir)
  api/trend.py             → {history, refs_trend} (yerel serve_trend birebir)
  api/run-history.py       → GitHub Actions API türetimi (yerel satır-şeması)
  api/determinism-trend.py → badge + rows (git'teki GERÇEK trend-verisi)
  api/_adapter.py          → ortak gövde: yol-bootstrap + tek-kaynak import'lar
                             + JSON/405 sözleşmeleri
```

Kural: yerel-yüzeyi taklit etmek yerine repo'nun **tek-kaynak yardımcılarını
import et** (preview_server.load_history/_project_history_record);
determinism-trend ucu da aynı yolla (determinism_trend_badge) bağlanabilir.

### Veri-gerçeği (ölçülmüş, 2026-09-23)

| Veri | Konum | Vercel-checkout'unda |
|---|---|---|
| determinism_trend.jsonl | `docs/determinism_trend/` — **git'te** (bot haftalık commitler) | VAR |
| history.jsonl | `_calisma/CIKTI/` — git-DIŞI (yerel çalışma-ürünü) | YOK |
| runs/ (stdout kayıtları) | `_calisma/CIKTI/runs/` — git-DIŞI | YOK |
| refs_trend.json | `_calisma/CIKTI/` — git-DIŞI | YOK |

Bu yüzden:
- `/api/run-history` → **GitHub Actions API** (public repo, anonim yetiyor;
  `GITHUB_TOKEN` verilirse rate-limit rahatlar) — canlı koşum-verisi.
- `/api/trend` → yerel birebir sözleşme; git-dışı veri yokken boş-durum
  fallback'leri (yerel serve_trend'in dosya-yok dallarıyla aynı şekil).
- `/api/health` → 200 "ok".

### Şema-parite kanıtı

GitHub-türetimi, yerel `serve_run_history` satır-şemasının TAM
anahtar-kümesini üretir: `{ts, verdict, p0, p1, budget_usd, budget_limit,
budget_method, duration_s, refs_verified, refs_total, pdf_pages, z3_passed,
z3_total, lean_ok, lean_detail}` **+ 2 bilinçli ek** (`workflow`, `url`).
Dashboard JS'i bilinmeyen anahtarı yok-sayar; `verdict` Actions
`conclusion`'dan: success → PASS, failure → FAIL, aksi `?`.

Canlı-şema-kanıtı (2026-09-23, `gh api repos/ali-han-kaya/leibniz2/actions/runs?per_page=3`):

```
{"conclusion":"success","created_at":"2026-09-23T01:28:59Z","name":"test-smoke"}
{"conclusion":"success","created_at":"2026-09-23T01:28:59Z","name":"verify-delivery"}
{"conclusion":"success","created_at":"2026-09-23T01:28:59Z","name":"docker-security"}
```

## 2. Deploy yolu (2026 runtime-gerekleriyle)

Vercel CLI **59.10.0**. 2026 dosya-tabanlı Python-handler sözleşmesi: her
`api/*.py` ayrı fonksiyon; dosya top-level `handler` adını
**BaseHTTPRequestHandler alt-sınıfı** olarak tanımlamalıdır — eski
`handler(request)` fonksiyon-biçemi builder'da statik sanılır ve canlı-
deploy'da NOT_FOUND verir (ölçüldü). Python-sürümü `api/.python-version`
(3.12); bağımlılıklar `api/uv.lock`'tan kurulur (stdlib-only → boş liste).

Bundle-küçültme kaldıracı: `vercel.json` →
`functions["api/*.py"].excludeFiles` — STRING olmalı (brace-expansion:
`"{a/**,b/**}"`; array → şema-hatası). Ağır-dizinler (.worktrees, apps,
_calisma/.venv_z3, _calisma/mcp) ve env-dosyaları dışarı: 397.62MB →
**656K**. `.vercelignore` yalnız UPLOAD adımını süzer; lokal `vercel build`
workPath'i doğrudan okur — asıl kaldıraç excludeFiles'tır.

### Import-yolu dersi (canlı-deploy'da ölçüldü)

Runtime handler'ı **DOSYA-YOLUNDAN** exec eder: `api/` sys.path'DE DEĞİLDİR.
`from _adapter import ...` → `ModuleNotFoundError` (canlı-log: `could not
import "api/trend.py"`; health etkilenmez çünkü import'u yok).

Çare (uygulandı): handler'larda 2 satırlık köprü —
`sys.path.append(os.path.dirname(os.path.abspath(__file__)))`; gerçek
bootstrap TEK-KAYNAK olarak `_adapter.py`'de: kendi-dizini +
`_calisma/CIKTI` **SONA** append (index'ler önce kalır → stdlib ve kendi
modüllerimiz gölgelenmez; CIKTI'da stdlib-gölge adı yok — denetlendi).
`REPO_ROOT` da CWD yerine file-anchored: `os.path.dirname(_HERE)`.

### Canlı-üretim kanıtı (2026-09-23, https://leibniz2.vercel.app)

`vercel deploy --prod` → Ready in 44s, alias `leibniz2.vercel.app`:

```
/api/health            → "ok"
/api/trend             → {"history":[],"refs_trend":{"rows":[],"duration_budget":{"rows":[]}}}
/api/determinism-trend → {"badge":{"cls":"ok","text":"✓ DETERMİNİZM PASS · 3 ölçüm"},"rows":[...]}
/api/run-history       → [{"ts":"2026-09-23T01:28:59Z","verdict":"PASS","workflow":"test-smoke",...},...]
```

```bash
# İlk bağlantı (etkileşimli; scope seçimi)
vercel link

# Preview deploy (PR-mimarisi: her push preview URL üretir)
vercel                    # veya: vercel --prod (üretim)

# Doğrulama (deploy sonrası)
curl -s https://<deployment>.vercel.app/api/health            # "ok"
curl -s https://<deployment>.vercel.app/api/run-history | head -c 400
curl -s https://<deployment>.vercel.app/api/trend | head -c 200
```

Ortam-değişkeni (opsiyonel): `GITHUB_TOKEN` — GH-API rate-limit için
(`vercel env add GITHUB_TOKEN`).

### Frontend notu

`preview.html`/`preview.js` statik-yüzey olarak Vercel'e kopyalanabilir
(`vercel.json` routes ile `/` → preview.html); JS'in `fetch("/api/...")`
çağrıları aynı-origin `/api/*`'a düşer — adaptör yolları yerel-uzayla aynı
olduğu için JS-değişikliği GEREKMEZ. SSE uçları (`/api/run`,
`/api/run-stream`) bu kapsamda DEĞİLDİR: canlı-akış yerel-daemon'un işi
(serverless'ta kalıcı bağlantı yok); Vercel-preview'ı okunur-anlık-görüntü
sunar, canlı-yayın değil.

## 3. VCS-kapsam kararı (güncel: git-TAKİPLİ)

`api/` **git-takiplidir**: repo-based git-push deploy'un ön-şartı, Vercel'in
derlemeyi commitlenmiş-ağaçtan yapmasıdır. `git ls-files api/` 6 dosya;
süitte `test_api_dir_is_git_tracked` bunu sabitler. (Eski "izleme-dışı"
kararı git-push otomasyon-hedefiyle çeliştiği için tersine çevrildi.)

## 4. Test/kanıt

```bash
python3 -m pytest _calisma/CIKTI/test_vercel_adapter.py -q   # 8/8 (1 canlı-GH-API, ağ-koşullu)
```

| Süit-testi | Sözleşme |
|---|---|
| handlers_are_basehttprequesthandler_subclasses | 2026 handler-sözleşmesi (4 handler) |
| api_dir_is_git_tracked | `git ls-files api/` dolu (git-push deploy ön-şartı) |
| local_health_parity_via_real_http | 200 "ok" düz-metin (gerçek HTTP) |
| local_trend_parity_via_real_http | {history, refs_trend} yerel birebir |
| local_determinism_trend_via_real_http | badge + rows (gerçek trend-dosyası) |
| method_gating_405 | GET-dışı → 405 {"error":...} (3 handler) |
| run_history_schema_parity | GH-türetimi yerel satır-şeması (+2 ek), ağ-koşullu |
| no_local_break_api_contract | yerel /api yüzeyi bozulmadı |

## 5. Git-push otomasyonu (repo-based) — kalan tek manuel adım

`vercel.json` → `git.deploymentEnabled: {"main": true, "reword-working":
true}`: git-push'ta otomatik build (git-tek-gerçek ödemesi — çalışma-dizini
kayması yok; `git archive HEAD` = 13.1MB, 250MB upload-sınırının çok altında).

Engel (hesap-düzeyi; CLI'dan çözülemez — 2 kez ölçüldü, 2026-09-23):

```
vercel git connect https://github.com/ali-han-kaya/leibniz2 --yes
→ Error: Failed to link ali-han-kaya/leibniz2. You need to add a Login
  Connection to your GitHub account first. (400)
```

Manuel adım (yalnız dashboard'tan): Vercel → **Account Settings → Login
Methods & Connections → GitHub Login Connection** ekle; sonrasında aynı
`vercel git connect` komutunu tekrar çalıştır (GitHub-uygulaması onayı
istenebilir). Bu adımdan sonra her push otomatik preview üretir.

## 6. Sınırlar (dürüst notlar)

- `/api/run-history` CI-verisi log-özetleri taşımaz: `p0/p1/budget/refs/z3/lean`
  alanları CI'da `None` (dashboard "—" basar). Anlam-yitimi bilinçli —
  yerel-zengin veri yerel-daemon'un işi.
- SSE yok (serverless-kısıtı): canlı-yayın `EventSource` Vercel'de çalışmaz;
  Vercel-preview okunur-anlık-görüntü.
- `/api/trend` history boş-döner (git-dışı veri); gerçek-trend paneli
  yerel-daemon'la yaşar. Adaptör sözleşmeyi + boş-durumları korur.
- GH-API rate-limit (anonim 60/sa): `GITHUB_TOKEN` önerilir.
