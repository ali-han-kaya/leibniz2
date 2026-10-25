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

### Frontend notu (uygulandı — statik yüzey AYNI deployment'da)

`preview.html`/`preview.js` statik-yüzey olarak aynı deployment'ta sunulur;
JS'in `fetch("/api/...")` çağrıları aynı-origin `/api/*`'a düşer — adaptör
yolları yerel-uzayla aynı olduğu için **JS-değişikliği GEREKMEZ**.

| URL | Kaynak | Mekanizma |
|---|---|---|
| `/` | `_calisma/CIKTI/preview.html` | route (`^/$`) |
| `/preview.js` | `_calisma/CIKTI/preview.js` | route (`^/preview\.js$`) |
| `/sw.js` | `_calisma/CIKTI/sw.js` | route (preview.js register eder; 404 → JS `.catch` ile zarfsız devam) |
| `/design-system/tokens.css` | `design-system/tokens.css` | route YOK — URL == dosya-yolu (filesystem servisi) |
| `/design-system/stripe-theme.css` | `design-system/stripe/theme.css` | route (yerel mirror kopyası git'te yok) |
| `/slides_z3/<ad>` | `_calisma/CIKTI/slides_z3/<ad>` | route + `$1` (ad sınıfı `[A-Za-z0-9._-]+`) |
| `/api/*` | `api/*.py` | **hiçbir route'a yakalanmaz** → dosya-tabanlı fonksiyon |

Kurallar — süit `TestVercelStaticFrontendContract` (3 test) bunları sabitler:

- Tüm route `src`'leri açık-anchor'lı (`^...$`): Vercel'in implicit-anchor
  davranışı bilinmediğinden anchor'sız `"/"` deseni TÜM yolları yutup
  `/api/*`'i statik-HTML'e çökerdi → adaptör atlanır, JS değişmeden kırılır.
- `.vercelignore` negasyonları (upload'a giren çekirdek):
  `preview.html` / `preview.js` / `sw.js`, `slides_z3/**`,
  `design-system/tokens.css`, `design-system/stripe/theme.css`, tüm
  `api/*.py` + `docs/determinism_trend/determinism_trend.jsonl`.
  Dışarıda kalan: `design-system/*` geri kalanı (primer vb.) + stripe
  altındaki token/script yüzeyi → bundle küçük kalır.
- `design-system/stripe/theme.css` **üretilmiş/takipsiz** dosyadır:
  CLI-deploy worktree'den yükler; git-push ağacında yoksa
  stripe-tema-varyantı 404 (yerel mirror da aynı biçimde 404) —
  varsayılan-koyu tema `tokens.css`'ten etkilenmez.

Bilinçli degradasyonlar — JS'in `.catch`'leri zarif düşer (görsel hata
değil), HATA sayılmasın:

- `/api/a11y` → `renderA11y(null)` "kanıt yok" (CI-artifact'ları git-dışı),
- `/api/override-trend` → `renderOverrideTrend([])` boş rozet (git-dışı jsonl),
- `/api/run-stdout` → "Yüklenemedi" (yalnız-istek-üzerine).

SSE uçları (`/api/run`, `/api/run-stream`) bu kapsamda DEĞİLDİR: canlı-akış
yerel-daemon'un işi (serverless'ta kalıcı bağlantı yok); Vercel-preview'ı
okunur-anlık-görüntü sunar, canlı-yayın değil.

## 3. VCS-kapsam kararı (güncel: git-TAKİPLİ)

`api/` **git-takiplidir**: repo-based git-push deploy'un ön-şartı, Vercel'in
derlemeyi commitlenmiş-ağaçtan yapmasıdır. `git ls-files api/` 6 dosya;
süitte `test_api_dir_is_git_tracked` bunu sabitler. (Eski "izleme-dışı" kararı git-push otomasyon-hedefiyle çeliştiği için
tersine çevrildi.) Çalışma ağacında `git ls-files api/` hâlâ boş dönüyorsa
(örn. özellik-taşıma) git-push **fonksiyonsuz** deploy üretir — git-push'tan
ÖNCE `git add api/` zorunlu. Süit koşulu bilinçli olarak yalnız listeyi
DOLUYKEN zorlar (boş listede kırmızıya çevirmez — yanlış-ortam false-red
yok); yani bu kapı repo'da tek başına yeterli değil, deploy akışı
`git ls-files api/` kontrolünü kendi ön-şartı saymalı.

## 4. Test/kanıt

```bash
python3 -m pytest _calisma/CIKTI/test_vercel_adapter.py -q   # 11/11 (1 canlı-GH-API, ağ-koşullu)
```

| Süit-testi | Sözleşme |
|---|---|
| handlers_are_basehttprequesthandler_subclasses | 2026 handler-sözleşmesi (4 handler) |
| api_dir_is_git_tracked | `git ls-files api/` dolu (git-push deploy ön-şartı) |
| local_health_parity_via_real_http | 200 "ok" düz-metin (gerçek HTTP) |
| local_trend_parity_via_real_http | {history, refs_trend} yerel birebir |
| local_determinism_trend_via_real_http | badge + rows (gerçek trend-dosyası) |
| method_gating_405 | GET-dışı → 405 {"error":...} (health; 405 şablonu 4 handler'da ortak) |
| run_history_schema_parity | GH-türetimi yerel satır-şeması (+2 ek), ağ-koşullu |
| no_local_break_api_contract | yerel /api yüzeyi bozulmadı |
| routes_anchored_and_api_paths_fall_through | route'lar açık-anchor'lı; `/api/*` + filesystem yolları asla yakalanmaz; 5 dest doğru; slayt adları route sınıfında |
| static_assets_exist_and_survive_vercelignore | mutlak-varlıklar (tokens/stripe/sw/slides) .vercelignore'dan hariç; takipli ise deployment ağacında mevcut |
| vercelignore_separates_upload_from_bundle | `api/*.py` + canlı-veri jsonl yüklenebilir; `.env`/pptx/primer/stripe-token/node_modules dışarıda |

### Aylık canlı doğrulama job'ı (`vercel-deploy-check.yml`)

CI yeşilliği deploy'u garanti etmez — route/fonksiyon/hesap kendiliğinden
kırılabilir; `.github/workflows/vercel-deploy-check.yml` ayda bir canlı
deployment'ın /api uçlarını kapı script'iyle doğrular (`cron: "23 5 1 * *"`
— ayın 1'i 05:23 UTC;
`workflow_dispatch` + `base_url` girdisi elle tetikleme için):

- `/api/health` → birebir `ok` (boşluk-temizlikli),
- `/api/run-history` → JSON dizi + `{ts, verdict}` şema +
  `verdict ∈ {PASS, FAIL, ?}` — yalnız "200 + parse" değil, şema-parite
  de canlı uçta sınanır.

Fail-closed: herhangi bir uç FAIL → job kırmızı (`exit 1`); Base/UTC
künyesi + PASS/FAIL satırları **her** koşumda `$GITHUB_STEP_SUMMARY`'a
yazılır (sessiz PASS yok). URL çözümü: `base_url` girdisi →
`vars.VERCEL_PREVIEW_URL` → **en güncel READY preview**
(`_calisma/CIKTI/vercel_latest_preview.py`; Vercel API `v6/deployments`,
production-dışı + `readyState=READY` ilk kayıt). Üretim alias'ına
**düşülmez** — bu kapı preview yüzeyini denetler; çözüm başarısızsa adım
kırmızı (fail-closed) ve denetlenen kök `$GITHUB_STEP_SUMMARY`'a yazılır.

### Sabit preview alias'ı (`leibniz2-preview.vercel.app`)

2026-10-25'ten itibaren çözüm tek bir sabit ada dayanır:
`vars.VERCEL_PREVIEW_URL = https://leibniz2-preview.vercel.app`. Alias, her
preview deploy'unda `vercel-preview-deploy.yml`'in "Sabit preview alias"
adımında yeni deployment'a yönlendirilir; alias `/api/health` 200 dönmezse o
job kırmızı olur — aylık kapı eski bir deployment'ı "preview sağlıklı" diye
raporlayamaz (sessiz bayat alias yok).

- **Semantik:** alias **son preview deployment**'ı gösterir; branch ayrımı
  yoktur. Bir PR dalının deploy'u alias'ı ilerletir — kapı bilinçli olarak
  "en son yayınlanan preview yüzeyi"ni denetler.
- `vars.VERCEL_PROJECT_ID = prj_VOVl5odaNOAU9i4B3rMc8xIFC0yd` (2026-10-25'te
  ayarlandı; hardcoded fallback'e bağımlılık kalktı) yalnız fallback çözücü
  (`vercel_latest_preview.py`) için gereklidir; normal yolda API'ye hiç
  gidilmez.
- **Ölçüm (2026-10-25):** `vercel alias set` + `check_vercel_deploy.py
  --base-url https://leibniz2-preview.vercel.app` → `VERDICT: PASS`
  (health `ok`, run-history 15 satır, slayt PNG 5131 bayt); ardından
  `vercel-deploy-check` `workflow_dispatch` koşumu **success**, logda
  `VERDICT: PASS — https://leibniz2-preview.vercel.app` (repo variable yolu
  kullanıldı; API çözücü devreye girmedi).
- **Neden alias:** git-connect 400 nedeniyle Vercel'in kendi branch alias'ı
  (`leibniz2-git-<branch>-…vercel.app`) oluşmuyor; `leibniz2.vercel.app` ve
  `leibniz2-sarkis-env.vercel.app` ise 2026-09-23 prod deployment'ına bağlı
  (prod yüzeyi — bu kapı onlara bağlanmaz, prod fallback yasağı sürer).

K1 kapı-paritesi (`test_gated_schedules`):
akış YAML'da yeniden yazılmaz — job `actions/checkout@v7`
(`action_pins.json`'da kayıtlı major 7) ile iner ve
`_calisma/CIKTI/check_vercel_deploy.py`'i bir `run:` adımında çağırır;
aynı script lokalde `--base-url` ile birebir aynı kodu koşar. Uç
kontrolleri script yapar (stdlib urllib — sağlık = `ok` düz-metin,
run-history = JSON + şema-parite, slayt = 200 + PNG-magic statik-upload
kanıtı); bash gövdesi yalnız URL çözümü +
çağrı taşır (shellcheck `-s bash -S info`: 0 bulgu — SC2016 yüzeyi sıfır).

Yerel kanıt (2026-10-09): kapı script'i üç senaryoda doğrudan koşuldu —
canlı URL → `VERDICT: PASS` / RC=0 (health `ok`, run-history 15 satır, ilk
`2026-10-08T17:59:52Z PASS`); ölü URL → RC=1 + `VERDICT: FAIL` + ağ
hata-metni raporda; geçersiz şema → RC=1 (STEP_SUMMARY'ye FAIL satırıyla).
`test_check_vercel_deploy` gerçek-HTTP test sunucusuyla 10 senaryo (PASS,
bozuk-sağlık, eksik-şema, geçersiz-verdict, JSON-değil, boş-liste, uç-olu,
geçersiz-şema, slayt-404, slayt-PNG-değil — hepsi fail-closed). Kapılar yeşil: `test_gated_schedules`
K1-K7 + gate testleri 46 test OK; workflow pili (contract/triggers/timeouts/
install-hardening/action-pins/runtimes/actionlint-gate/python3-shell) 102
test OK; `check_python3_shell` PASS (7 workflow / 251 adım);
`summary_pattern_drift --json` PASS (stdout tek JSON).

Statik-upload tuzağı (2026-10-09, düzeltildi): Vercel CLI 59.x upload
tarayıcısı (`readdirRecursive`) her girişi **slash'sız** yol ile `ignore`
paketine test eder; dizin "ignored" çıkarsa tüm alt ağaç prune edilir ve
çocuklar hiç denenmez. Sonu `/` ile biten dir-only negasyon slash'sız dizin
yoluna eşleşmez → `!_calisma/CIKTI/slides_z3/` tek başına dizini
kurtaramıyordu; `/slides_z3/*` ve `/design-system/stripe-theme.css` **tüm**
deploy'larda 404'tü (git `check-ignore` bunu temiz gösteriyordu — takip
edilen dosya "girer" derken atas dizim prune ediliyordu: kapı yeşil, deploy
kırmızı). Düzeltme: slash'siz negasyonlar (`!_calisma/CIKTI/slides_z3`,
`!design-system/stripe`); offline model `test_vercel_adapter` →
`TestVercelUploadPruneSemantics` ile ölçüm-kilitli; canlı kanıt kapıya üçüncü
uç olarak eklendi (`/slides_z3/P1-a.png` → 200 + PNG magic — API'ler
yeşilken statik ağaç prune edilirse kapı kırmızı).

Not: workflow'lar HEAD'den koşar — job, commit + push edilmeden schedule'a
girmez; ilk tetikleme `workflow_dispatch` ile elle yapılabilir.

## 5. Git-push otomasyonu — fallback hattı (2026-10-09, uygulandı)

Orijinal tasarım native link üzerinedir: `vercel.json` →
`git.deploymentEnabled: {"main": true, "reword-working": true}` — push'ta
otomatik build (`git archive HEAD` = 13.1MB, upload-sınırının çok altında).

**Native link engelli ve dashboard sessiz-şekilde başarısız** (2026-10-09'da
yeniden ölçüldü; kanıt demeti 2026-09-23'tekinden geniş):

```
vercel git connect → 400 "You need to add a Login Connection to your GitHub
account first." (7 deneme; son 4'ü Authentication'dan disconnect +
yeniden-authorize'dan sonra)
GET /v9/projects/{id}/link → "Project Link not found." — dashboard connect
akışı "Connected" göstermesine rağmen link hiç oluşmadı (26×10s senkron
pencerede API'de iz yok; UI ile API çelişiyor).
Repo tarafında da iz yok: webhook yok; son başarılı git-deploy 2026-09-24
(34b6ea35 — protectionBypass'ın da kurulduğu dakika).
```

**Fallback (CI-üzerinden otomatik preview):**
`.github/workflows/vercel-preview-deploy.yml` — `main` hariç her push (ve
`workflow_dispatch`) → `vercel link` + `vercel deploy` (secret
`VERCEL_TOKEN`) → preview URL → **aylık `vercel-deploy-check` ile AYNI kapı
script'i** (`check_vercel_deploy.py --base-url`) + `trend` /
`determinism-trend` JSON sağlığı; hepsi fail-closed, URL
`$GITHUB_STEP_SUMMARY`a yazılır. Kapı-paritesi (K1): lokal `--base-url`
koşumu ile CI koşumu aynı kodu çalıştırır.

Kurulum: vercel.com/account/settings/tokens → token oluştur → repo
Settings → Secrets and variables → Actions → `VERCEL_TOKEN`. (API ile token
üretilemiyor: `POST /v2/user/tokens` → "Cannot create tokens for this app".)

### Token — hangi hesap, hangi scope (2026-10-25 ölçümü)

Token'ı **`sarkis-env` takımının üyesi olan hesaptan** oluştur ve token'ı o
takıma kapsamla. Proje `sarkis-env/leibniz2` altında; workflow sabit olarak
`--project leibniz2 --scope sarkis-env` kullanıyor.

| Adım | Değer |
|---|---|
| Hesap | `sarkis-env` üyesi (owner/member) olan Vercel kullanıcısı |
| Scope | `sarkis-env` · **All Projects** (daraltmak istersen yalnız `leibniz2`) |
| Secret | repo → Settings → Secrets and variables → Actions → `VERCEL_TOKEN` |
| Hedef | `✓ Linked sarkis-env/leibniz2` |

**Neden:** `--scope` yetki **vermez, seçer**. Erişimi token'ın kapsamı belirler;
Vercel üç kapsam tanır — Full Account (kişisel + üye olunan takımlar), Team
(tek takım), Project (tek proje; kullanıcı/takım uçlarına erişemez)
([access tokens](https://vercel.com/docs/accounts/access-tokens)). Token'ı
oluşturan hesap takımın üyesi değilse link adımı, token doğru olsa bile düşer.

### `scope-not-accessible` — belirti → teşhis

Düşen adımın logu birebir şu iki satırı verir:

```
Error: You do not have access to the specified account
Learn More: https://err.sh/vercel/scope-not-accessible
```

Resmî açıklama ([vercel/vercel errors](https://github.com/vercel/vercel/blob/main/errors/scope-not-accessible.md)):
`--scope` ile verilen takımın **üyesi değilsin**, sahibi olmadığın bir kullanıcı
hesabını gösterdin ya da token geçersiz/süresi geçmiş. Ayırt etme tablosu:

| Belirti | Anlamı | Kontrol |
|---|---|---|
| `scope-not-accessible` | scope üyeliği yok / token geçersiz | `vercel switch` çıktısında o scope **yok** → takım üyeliği |
| HTTP **401** | token geçersiz veya süresi dolmuş | `GET /v2/user` |
| HTTP **403** | token geçerli, kapsamı yetmiyor | `GET /v2/teams`, `GET /v10/projects?teamId=…` |
| `Project not found` | yanlış proje adı/ID'si veya yanlış takım | `--project` / `VERCEL_PROJECT_ID` eşleşmesi |
| `No project linked` | `.vercel/` bağı yok ve ID'ler verilmemiş | `vercel link` ya da iki ID ortam değişkeni |

Doğrulama — token'ı loga **yazmadan**:

```bash
vercel whoami && vercel teams ls && vercel switch
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $VERCEL_TOKEN" https://api.vercel.com/v2/teams
# 200: kapsam görünüyor · 403: kapsam yetmiyor · 401: token ölü
```

### Rotasyon — tam sıra

1. Doğru hesapta yeni token: Scope = `sarkis-env`, All Projects (veya yalnız
   `leibniz2`).
2. `gh secret set VERCEL_TOKEN` — değer stdin'den verilir; chat'e, commit'e,
   loga yazılmaz.
3. `gh workflow run vercel-preview-deploy.yml --ref main` — link adımı kapsamı
   da sınar (`main` push'a kapalı ama `workflow_dispatch` ile koşar).
4. Logda `✓ Linked sarkis-env/leibniz2` ve `VERDICT: PASS` görülmeli.
   Rotasyonun indiğini doğrula:
   `gh api repos/<owner>/<repo>/actions/secrets --jq '.secrets[]|select(.name=="VERCEL_TOKEN").updated_at'`.

**Tarihsel kayıt (bu bölümün nedeni):** 2026-10-24 00:16 koşumu
(`40044149599`) tam bu hatayla düştü — token vardı ama `sarkis-env`'e erişimi
yoktu. Aynı gece 00:40'ta secret doğru kapsamlı token'la değiştirildi; sonraki
16/16 koşum ve `main` ref'inde elle tetiklenen `40211379655` yeşil. Yani sorun
"Vercel hesap ayarı bekliyor" değil, **token'ın kapsamıydı**; belirtiyi
`scope-not-accessible` olarak okumak teşhisi tek adımda verir.

**Not:** workflow `--scope` sabitini kullanıyor; `vars.VERCEL_PROJECT_ID` yalnız
aylık `vercel-deploy-check` içindir. Env-var moduna geçilirse `VERCEL_ORG_ID` +
`VERCEL_PROJECT_ID` birlikte gerekir — bu **erişim sağlamaz**, yalnız `link`
adımını kaldırır.

**Proje env — `GITHUB_TOKEN` (2026-10-09):** `/api/run-history` GitHub
Actions API'sini çağırır; token'sız anonim quota **60 istek/saat** ve
Vercel'in paylasilan egress IP'lerinde tüm部署'larla ortaktır → ara sıra
429/502. `api/_adapter.py:_fetch` `GITHUB_TOKEN` env varını görünce
`Authorization: Bearer` ekler (5000/sa); yokken anonim kalır (public-repo
fail-open). Sözleşme pini: `test_vercel_adapter` →
`test_fetch_attaches_github_token_header` (token-varken başlık / yokken
başlık-yok — her iki yön de). Proje env'leri `sarkis-env/leibniz2`'ye
eklendi: **Production = Secret, Preview = sensitive** (API'nin
geri-okunamayan tipi; `secret` yalnız CLI'nin adı, v9/v10 API'si400
döner) — değerler asla repo'ya/disc'e yazılmadı (CLI stdin + API body ile
aktarıldı). Değer kaynağı: yerel `gh` oturum token'ı; daraltmak için
fine-grained, read-only `actions` PAT ile `vercel env rm` + yeniden
eklenebilir. Geçersiz token GitHub'a401 döndürür → adaptör502 (fail-loud,
sessiz-anonim yok). **Env değişiklikleri yalnız yeni deploy'larla geçerli
olur** — eski preview URL'leri hâlâ anonim çağırır.

Native link düzelirse (Authentication'da gerçek bağlantı + `vercel git
connect` yeşil): fallback workflow KALDIRILMALI — iki hat aynı push'a iki
preview üretir.

## 6. Sınırlar (dürüst notlar)

- `/api/run-history` CI-verisi log-özetleri taşımaz: `p0/p1/budget/refs/z3/lean`
  alanları CI'da `None` (dashboard "—" basar). Anlam-yitimi bilinçli —
  yerel-zengin veri yerel-daemon'un işi.
- SSE yok (serverless-kısıtı): canlı-yayın `EventSource` Vercel'de çalışmaz;
  Vercel-preview okunur-anlık-görüntü.
- `/api/trend` history boş-döner (git-dışı veri); gerçek-trend paneli
  yerel-daemon'la yaşar. Adaptör sözleşmeyi + boş-durumları korur.
- GH-API rate-limit (anonim 60/sa): `GITHUB_TOKEN` önerilir.
