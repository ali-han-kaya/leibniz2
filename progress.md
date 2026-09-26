# Progress Log

## Session 2026-09-18 — multi-skill marathon (16 skill turu)

- Surfaces completed (all verified; recovery note below): landing page
  (a11y-gate PASS), leibniz2_mcp read-only MCP server (stdio smoke E2E),
  security headers + CSP nonce (contract tests), CLS fix 0.325→0.0005,
  load_history mtime+size cache (do_GET −63%, 5 coherence tests),
  test-isolation repairs via shuffle-audit (seeds 42/7/13 green),
  pptx pilot export (skill validate PASSED), trend-db Prisma-7 skeleton
  (42-col TrendRun incl. refsBySource; validate/generate PASS credential-free;
  drift-guard test), reproducible-PDF re-audit (verify PASS, repack reuse
  byte-identical in /tmp copy), security review (0 high-confidence,
  VERIFY-001 CSP-hover), ruflo/rust/remotion/requesting-code-review/
  receiving-code-review/release-candidate-check tours (findings only).
- Pre-commit tour (setup-pre-commit, user-approved adaptation): existing
  47-hook chain KEPT (Husky rejected — would seize core.hooksPath and bypass
  the chain); added local read-only fail-closed hooks 48/49:
  check-prettier-format (staged js/ts/tsx/json; --check; prettier-missing →
  SKIP) and check-dashboard-typecheck (tsc --noEmit; env-missing → SKIP).
  prettier@3.6.2 added to dashboard-next devDeps; .prettierrc (skill
  defaults) at repo root; JS/TS/JSON session surfaces normalized (dashboard,
  trend-db loader+config, pptx generator, package files); tsc baseline green;
  both gates proven live (OK / framework-FAIL / SKIP paths); config validated;
  .pre-commit-config.yaml + check_unit_tests.list STAGED (battery runs
  against staged state; staging is part of the gate contract, commit is user's).
- INCIDENT (recovery): out-of-session action reverted all tracked-file
  modifications to HEAD mid-tour (signature: only tracked files hit,
  untracked + staged intact; HEAD unchanged). Recovered selectively from
  /tmp/repack_reuse/calisma snapshot (taken post-session during reproducible-
  pdf tour): 6 files copied back, .gitignore entries re-applied, plan files
  re-written. Direct test runs 14/14 OK in touched modules. Full details in
  task_plan.md RECOVERY NOTE + findings.md. Battery "2 failed" during
  recovery was a staging-state artifact, not a regression.
- shadcn-ui tour: REAL DEFECT fixed — dashboard-next used Tailwind utility
  classes with no Tailwind (build CSS 279 B, zero utilities); Tailwind v4
  installed, postcss wired, build CSS now 9 KB with all consumed utilities.
  shadcn init (non-interactive -d, base-nova/Base-UI) produced components.json
  + button + cn() utils; init's :root hex-overwrite side-effect caught and
  reverted (app tokens preserved, shadcn namespace separate); first consumer
  wired (buttonVariants ghost links); live smoke 200 + classes in HTML;
  all gates green; battery 138 PASS. Note: tracked apps/dashboard-shadcn
  misnomer — semantic CSS, not shadcn.
- Blocked-on-user: commit authorization (recovered tree is fragile while
  uncommitted — commit ASAP), reviewer dispatch (codex quota resets Sep 22
  07:42 / claude login / ruflo API key), VERIFY-001 fix, Aday-1 grilling.

## Session 2026-09-04 — CI triage of PR #42 (head b82b412)
- (archived: root causes pinned in findings.md archive of that date;
  closed at 5ab5196.)

## Session 2026-08-30 (planning-with-files init)
- (archived: fresh start, PR #42 checks snapshot K1-K19 FAIL, plan created.)

## 2026-09-19 — stripe-best-practices tour
- Skill activation: payment domain has no surface in this repo (evidence:
  git-grep 6 hits all design-system/stripe, no sk_/rk_ keys, no SDK/CLI).
- No code written; audit-only turn. Tree stable after Freebuff restart
  (porcelain 29, staged 16, HEAD unchanged).
- Live audits: stripe mirror gate OK (710 tokens), linear OK (398), primer
  OK (2051); zero --hds-* consumers outside design-system/.
- findings.md updated with tour section; both files staged + battery.

## 2026-09-19 — supabase-postgres-best-practices tour
- Rule audit of apps/trend-db: 2 fixes (Timestamptz(6) + Decimal(10,2);
  batched createMany loader), 3 already-compliant rules noted.
- Gates: prisma validate/generate, tsc strict, drift-guard 8/8, battery
  138/138. Staged: schema.prisma + scripts/load.ts (generated/ ignored).

## 2026-09-19 — systematic-debugging tour
- 4-phase process completed on the 2026-09-18 revert incident: root cause
  = pre-commit stash-window process death (reproduced minimally with
  control group), prior other-thread hypothesis corrected in task_plan.
- Incident patches archived (_calisma/CIKTI/recovery_patches_20260918/);
  ~170 orphan patch files purged from ~/.cache/pre-commit.
- Scratch repro cleaned (probe hygiene).

## 2026-09-19 — tailwind-design-system tour
- dashboard-next wired to the token chain via the generated bridge;
  copied :root removed. Generator defect fixed (embedded tailwindcss
  import broke consumers); gate extended with contracts 5+6 (five proven
  paths incl. comment-mention trap). Build + live smoke + battery green.

## 2026-09-19 — tdd tour
- check_precommit_orphans.py built red→green at the approved CLI seam
  (6 contracts); wired as hook 19 + manifest; framework green/fail paths
  proven; battery 139/139.

## 2026-09-19 — test-driven-development tour
- Fingerprint slice red→green (8/8); incident patches sha256-verified
  against archive and removed from live cache (time-bomb defused).

## 2026-09-19 — typescript-advanced-types tour
- Loader escape hatches removed (as never[] → generated input type;
  json(): unknown → recursive type guard + DbNull decision). Gates green;
  battery 139/139.

## 2026-09-19 (worktree tour)
- Pruned 6 stale worktree records; .worktrees/ gitignored (line 48).
- commit 07e22aa: pre-commit chain 47→50 + recovery patches + plan files
- commit d1cbfb2: apps surfaces (dashboard-next, trend-db, landing, mcp, pptx) + contract tests
- 2 stash-window retries diagnosed; unstaged-delta rule enforced
- Next: .worktrees/work/2026-09-19 from HEAD, setup, baseline battery

## 2026-09-26 — LeibnizChain render + repoya taşıma
- `/npx remotion render` isteği: repoda **sıfır** video yüzeyi (`<Composition>`/
  `registerRoot`/`@remotion/player` yok, mp4 yok, bağımlılık yok); kompozisyon
  2026-09-18'de `/tmp/leibniz-chain-video` altında kurulmuş ve **silinmişti**
  (4 kanıt: ls/find/npm cache/_npx). Uydurma render yerine bulgu raporlandı.
- Kullanıcı kararıyla kayıttaki spesifikasyondan yeniden kuruldu ve render
  edildi: 1.893.303 B (1,81 MiB), 25,3870 sn kap / 25,3333 sn video, 760 kare
  @ 30 fps, 1280×720, avc1 CRF 20, 597 kbit/s, sha256 87f6101d…, 14,7 sn.
- İlk render'da iki gerçek yerleşim hatası bulundu (baskı(height) sıkıştırması,
  sıfır uzunluklu interpolate → siyah ilk kare); ikisi de düzeltilip kareler
  görsel olarak denetlendi (0/60/120/300/420/520/580/620/690/699).
- Taşıma: `_calisma/video/` (kaynak takip altında), `node_modules/ out/ .remotion/
  public/data/` ignore'da. Paket komutları kültüre bağlandı:
  `npm run data|typecheck|format|render|studio`.
- Kapılar: yeni `check-video-typecheck` pre-commit hook'u (dashboard ile aynı
  SKIP/OK/fail-closed sözleşmesi), prettier kapısı 9 dosyada geçti, iki yeni
  test (18 + 6), manifest + HOOK_COVERAGE senkron (165 → **167 dosya PASS**),
  `video-render` CI iş'i (advisory, fail-closed, kutu ayrıştırmalı ölçüm) +
  PUBLISH_SCENARIO tablo/artifact satırları + GATE_EXCLUDE + workflow_contract.
- Tüm doc/workflow kapıları yeşil: doc-job-sync 10/10, doc-artifact-sync 10/10,
  workflow-contract 12/12, workflow-artifact-docs PASS, actionlint RC=0,
  absolute-paths PASS (575 dosya), pattern-consistency PASS, config-sync PASS.

## 2026-09-26 — LeibnizChain'i preview sunucusuna göm (@remotion/player)
- Studio yerine tarayıcı-içi oynatma: Studio ayrı sunucu + webpack dev-cache
  ve harness child process'leri reap ediyor; `@remotion/player` esbuild ile tek
  statik pakete toplanıp preview sunucusundan servis ediliyor.
- Yeni rotalar: `/video.html` + `/video/{player.js,player.css,leibniz.json}`
  (3 adlık ACIK allowlist; 6/6 kaçış denemesi 404). Dist kökü repo checkout'unda
  (`VIDEO_DIST`), PREVIEW_DIR mirror'ından bağımsız → CI'da da çalışır.
- CSP uyumu: `default-src 'none'; script-src 'self' 'nonce-…'` → sayfada
  **inline script yok**, veri `data-src` niteliğiyle taşınıyor; paket harici.
- Tek sahne ağacı iki ortakta: `LeibnizChainView` (mp4 render `staticFile`,
  oynatma `dataUrl`). Kopya sahne yok.
- Ölçülen hata: `<Player>` bilesene özel propları `inputProps` ile geçiriyor;
  doğrudan geçilen `dataUrl` yutulup `staticFile` yedeğine düşüyordu
  ("leibniz.json 404"). `inputProps={{dataUrl}}` ile düzeldi.
- Tarayıcı doğrulaması (Chromium): gerçek veriyle başlık sahnesi, oynatma
  başladı, 3 sn'de 0:07 + sahne 2 → sahne 3 → 4 → döngü; konsol/ağ hatasız.
- Ortam kaybı notu: oturum ortasında `~/Library/Caches/ms-playwright/` tamamen
  silinmişti (aynı turda `/tmp` de). Üç dashboard testi fail-closed düştü ve
  commit'i blokladı; `playwright install chromium` ile onarıldı (92,4 MiB,
  v1223) ve üçü de yeşile döndü. `__dirlock` tuzağı ve kısmi-indirme
  davranışı findings.md'ye yazıldı.

## 2026-09-26 — LeibnizChain: verdict grafiği + kapı kırılma animasyonu
- Timeline sahnesine gerçek dağılım grafiği: VERDICT ve ÇIKIŞ KODU yığılmış
  çubukları (0–100% cetveli, `stage()` ile sırayla dolan segmentler) + P0/P1/
  bulgu/sapma/Z3/kapı telemetrisi şeridi. Hepsı `history.jsonl`'dan türetildi.
- Gates sahnesine kapı kırılma animasyonu: 16 kapı sırayla yanar, soldan
  sağa kırmızı tarama çizgisi geçer, ardından KIRILMA şeridi + `status_board`
  çipleri + "1 ✓ · 4 ⚠" sayacı. Kırılma **sayısı sabit değil**: `exit_code < 0`
  olan koşularla birebir eşleşir (ölçüldü: 7/7, −15 SIGTERM).
- Dürüstlük: tek sonuçlu dağılım tek renkli çizildi ve notla açıklandı; yeşil
  koşu/kırmızı kapı sayısı UYDURULMADI. `0` ile `null` ayrıldı (z3 0/0 ≠
  rapor), `K katmanları ⚠️` grup sinyali olarak ayrıldı (kapı numarası değil).
- Kare bütçesi 760'da korundu; kare, statik sahnelerden alındı
  (90/200/120/200/100/50). Yeniden render ölçüldü: 760 kare / 25,387 sn /
  1280×720 → `check_render` PASS.
- Doğrulama: tsc temiz, prettier uygulandı, 4 video testi yeşil
  (data-contract 30 test, render 20, preview 14, typecheck), 9 kare görsel
  denetimden geçti. Bulunan iki çizim hatası (süre etiketi binmesi, 58 px
  sütunda sarma) düzeltildi.
- Yol üstünde bulunan gerçek hata: `video-render` CI adımı sentinel bayrağı
  vermediği için üretici fail-closed çıkıyordu (adım yorumu bunun tersini
  söylüyordu) → `--allow-missing-data` ile düzeltildi.

## 2026-09-26 — VERIFY-001: CSP altında hover-tooltip kanıtlandı
- Handler'lar `preview.js` şablon stringlerindeydi (`svg.innerHTML` ile basılan
  hit-alanları); bulgunun gösterdiği `preview.js ~652` satırı doğru değildi.
  `design_preview.html` yalnız URETILMIŞ, bayat bir kopyaydı (14 inline
  handler) → yeniden üretildi.
- Kaynak `2fee44f`'te zaten `data-tip`+`data-i` ve SVG-düzeyi delegeye
  geçmişti; eksik olan **koruyan kapıydı**. İki kapı eklendi:
  - `test_preview_server.py → InlineEventHandlerContractTests` (6 test,
    statik): inline handler yok, sunucunun gerçek gönderdiği CSP sıkı, üç
    yüzey de delege haritasında, kapının kendisi sentetik ihlalle sınanır.
  - `test_preview_hover_tooltip.py` (8 test, Playwright + gerçek sunucu):
    CSP başlığı doğrulanır → `page.hover()` ile tooltip none→block, içerik
    hoverlanan sütunun verisi, çıkınca gizlenir, konsolda 0 CSP ihlali.
- Ters kanıt: `preview.js` `2fee44f^`'a çekildi → 7 hata / 0 skip; düzeltmeli
  sürüm 8/8 yeşil. İlk yazımdaki iki test skip ediyor, CSP-konsol testi
  boş geçiyordu; hit-alanı sayısı testin içinde zorlanarak kapatıldı.
- Yol üstünde ayrı hata bulundu ve düzeltildi: `connectStream()`'daki üç
  dinleyici kapsam dışı `el` kullanıyordu → her run özetinde
  ReferenceError "el is not defined" (18 kez ölçüldü), akış paneli
  güncellenmiyordu. Düzeltme sonrası kanıt: CSP ihlali 0, konsol 0, sayfa 0.
- Ön koşul: `check-prettier-format` `preview.js`'i HEAD'de de kırmızıydı
  (tek satır); turda `--write` ile düzeltildi.

---

## escapeHTML nitelik bağlamı için güçlendirildi + havuz tabanlı tarama kapısı

**Ne:** `escapeHTML` artık tırnakları da kaçırıyor (`& < > " '`, `&` ÖNCE),
`preview.js`'teki üç nitelik yuvası (`lean_detail` → `title`, `source` →
`class`, `ts` → `data-ts`) tek yola bağlandı. Yeni statik kapı **tüm
template literal havuzlarını** tarıyor (çok satırlı şablonlar dahil) ve
nitelik bağlamına kaçışsız veri girdiğini fail-closed reddediyor. Güvenli
sayılan yardımcı listesi de tanım bazında sınanıyor (ölü giriş yok).

**Ölçüm:** 135 havuz / 237 interpolasyon → nitelik bağlamında **0** kaçışsız
veri; 137'nin tamamı ya kaçırılmış ya da aritmetik sayı üretiyor. Kalan 8
veri türetli interpolasyon metin bağlamında.

**Doğrulama:** 6 mutasyonun hepsi kırmızıya düşüyor (tırnak kaçırma, yuva
kaçırma, tek satırlı ve çok satırlı enjeksiyon, `data-ts` elle kaçırma,
HTML parçasına kaçırma). Statik 164 test + gerçek tarayıcı enjeksiyon
testi 7/7 yeşil. Tam batarya **171 test dosyası PASS**, `check-video-typecheck`
OK, `preview.js` prettier-uyumlu.

**Yol üstünde bulunan ikinci açık:** ilk statik kapı satır tabanlıydı ve
çok satırlı nitelik enjeksiyonunu **kaçırıyordu** — yani kapının kendisi
körleşmişti. Havuz tabanlı tarama ile değiştirildi ve tarayıcısına öz
bir test eklendi ("satır kıran ihlali de görmeli").

**Not:** `preview.js` HEAD'de de prettier-kırmızıydı; bu turdaki hunk
prettier ile düzeltildi, dosya artık temiz. `test_budget_scan.js` ve
`github_scripts/*.js` de kırmızı ama **bu değişikliğe ait değil**, dokunulmadı.
