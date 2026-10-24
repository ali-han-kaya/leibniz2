# Skill Turu Envanteri — Maraton (2026-09-18 → 2026-09-19)

<!-- ELLE YAZILMIŞ BELLEK. Kaynak: `findings.md` (skill-tur bölümleri).
     ÜRETİLMİŞ DEĞİLDİR — "sonuç" sütunu yargı gerektirir, mekanik
     türetilemez. Türevlenebilir kısım (tur sayısı) aşağıda doğrulanır. -->

Bu tablo **maratonda koşulan skill turlarının** kaydıdır: hangi beceri
ailesi koşuldu, hangi yüzeye baktı, ne çıktı.

**Bu, [`SKILL_SURFACE_INVENTORY.md`](SKILL_SURFACE_INVENTORY.md)'nin
tamamlayıcısıdır, yerine geçmez.** Ayrım önemli:

| | kapsam | eksen | üretim |
|---|---|---|---|
| `SKILL_SURFACE_INVENTORY.md` | beceri **alanı** ↔ repo yüzeyi | alan ↔ yol | **ÜRETİLİR** (`gen_skill_surface_inventory.py`, fail-closed) |
| bu doküman | koşulan **tur** ↔ yüzey ↔ sonuç | tur ↔ yüzey ↔ sonuç | elle, `findings.md`'den |

## Kapsam ve sayım

- **Kaynak**: `findings.md` (tüm tur kayıtları okundu; kanıt sütunu § başlığı
  verir, satır numarası vermez — çünkü dosya büyüdükçe satırlar kayar).
- **Tablo 1 — maraton (2026-09-18 → 09-19)**: 25 beceri ailesi / **26 tur
  kaydı**. (systematic-debugging iki kez görünüyor: 09-18'de olay kaydı,
  09-19'da kök neden kanıtı.)
- **Tablo 2 — maraton sonrası denetim turları (09-27 → 09-28)**: **8 kayıt**.
  Bunlar beceri adıyla değil kapı/denetim adıyla kaydedilmiş; "tüm" kapsamı
  gereği ayrı tabloya kondu, maraton tablosuna karıştırılmadı.
- **Toplam: 34 satır.**
- **Sonuç sınıfları**: düzeltme kapattı · kural gereği boş (sıfır-yüzey) ·
  inceleme-only · kapı/kural kurdu · ortam engeli · plan yürütme.
- **Tablo dışı (bilinçli)**: beceri adı taşımayan salt repo denetimleri —
  `Reproducible-PDF delivery chain re-audit`, `Security review of
  session-touched surfaces`, `Perf/testing facts (early tours)`,
  `Repo facts (2026-09-09)`. Bunlar tur değil, oturum denetimi; gizlice
  düşürülmedi, burada sayıldı.
- **Devam kayıtları** (ayrı tur değil, aynı turun sonrası):
  `Remotion pilot repoya taşındı` (2026-09-26), `worktree baseline` (Tablo 1
  #15 olarak sayıldı — aynı işin taze-worktree bacağı).

## Tur tablosu

| # | Skill (beceri) | Tarih | Yüzey — neye bakıldı | Sonuç | Kanıt (`findings.md` §) |
|---|---|---|---|---|---|
| 1 | `requesting-code-review` | 09-18 | Orca orkestrasyon + agent-CLI ile kod incelemesi gönderimi | **Ortam engeli** — gönderim kullanılamaz: Orca mutation katmanı kalıcı bozuk ("Mutation receipt ledger metadata is missing", `--retry` aynı hatayı veriyor); `claude -p` giriş yok, `codex exec` model/limit engeli. Brief yeniden kullanılabilir | Code-review dispatch feasibility |
| 2 | `ruflo` | 09-18 | Makine düzeyi `~/.ruflo`, repo içi ruflo yok | **Ortam engeli** — repo ruflo-free; "No API keys" ( reviewer gönderimi kimliksiz), plugin imza doğrulaması BAŞARISIZ → demo registry'ye düşüş; sürüm drift'i (skill 3.31.0, gerçek 3.42.4), komut drift'i (`discover-plugins`→`plugins list`) | Ruflo recon |
| 3 | `rust-async-patterns` | 09-18 | Rust yüzeyi: `.rs` / `Cargo.toml` / `rust-toolchain` | **Kural gereği boş** — üç kaynaktan sıfır: git-izlenen 0, disk taraması 0, `cargo/rustc/rustup` yok. Beceri yoklukla uygulanmadı (pinokio emsali) | Rust surface: zero |
| 4 | `remotion-best-practices` | 09-18 | `/tmp` pilotu: data-driven LeibnizChain videosu (1280×720@30, 760 kare, 6 sahne) | **Düzeltme kapattı** (yeniden inşa) — pilot kuruldu, tsc temiz, 5 still gerçek bundler'dan; sonra `/tmp` temizliğinde **kayboldu**, 2026-09-26'da kayıttan birebir yeniden inşa edildi. Görsel denetim iki kodu-göremez hatayı buldu (`rise()` yükseklik çökertme, `interpolate` siyah ilk kare) — tip kapısı ikisini de geçti | Remotion pilot (+ pilot repoya taşındı) |
| 5 | `systematic-debugging` (öncü kayıt) | 09-18 | Çalışma ağacı revert olayı + kurtarma | **Kapı/kural kurdu** — olay kaydı ve arşiv; asıl kök neden ertesi gün kanıtlandı (bkz. #9) | Working-tree revert incident |
| 6 | `shadcn-ui` | 09-18 | `apps/dashboard-next` | **Düzeltme kapattı** — Tailwind kurulmadan Tailwind utility sınıfları kullanılıyordu; derlenen CSS 279 B (utility yok, sayfalar aralıksız/çerçevesiz). `tailwindcss@4` + PostCSS ile 9021 B, tüketilen utility'ler mevcut. `shadcn init` yan etkisi yakalandı: `:root --muted/--accent/--border` hex'leri ezildi → geri alındı, shadcn namespace ayrı | shadcn-ui tour |
| 7 | `stripe-best-practices` | 09-19 | `design-system/stripe/` (ödeme değil, token aynası) | **Kural gereği boş** (beceri↔yüzey uyumsuzluğu) — ödeme yüzeyi sıfır (SDK/webhook/billing/`sk_` yok); ayna canlı ve sağlıklı (710 `--hds-*` token birebir). Gözlem: dört marka aynasının hiçbiri pre-commit zincirine bağlı değil (mevcut tasarım, bu turun getirmesi değil) | stripe-best-practices tour (2026-09-19) — domain mismatch, mirror audited instead |
| 8 | `supabase-postgres-best-practices` | 09-19 | `apps/trend-db` (Prisma 7 + Neon) | **Düzeltme kapattı** — ilk migration öncesi "ücretsiz pencere": `ts` → `Timestamptz(6)` (canlı veride offset'li mikrosaniye vardı, eski `timestamp(3)` hem offset'i düşürüyor hem kırpıyordu), `budget_usd/limit` → `Decimal(10,2)`, satır başına `upsert` → 500'lük `createMany` + `skipDuplicates`. 8/8, batarya 138/138 | supabase-postgres-best-practices tour |
| 9 | `systematic-debugging` | 09-19 | 09-18 revert olayının kök nedeni | **Kapı/kural kurdu** — önceki teşhis (dış aktör) çürütüldü: kök neden pre-commit `staged_files_only.py`'nin unstaged'ı patch'e stash'leyip `finally`'de `git apply` etmesi; süreç bu pencerede ölürse izlenen dosyalar INDEX'e dönüyor. Scratch repo'da faz-3 kanıtı + kontrol grubu; ~170 yetim patch; kalıcı süreç kuralı | systematic-debugging tour |
| 10 | `tailwind-design-system` | 09-19 | `design-system/tailwind.css` köprüsü + `check_tokens.py` | **Düzeltme kapattı** + kapı genişletildi — dashboard-next artık ÜRETİLEN köprüyü içe aktarıyor (kopyalanmış `:root` silindi); `check_tokens.py` sözleşme 5+6 eklendi (gerçek `@import` şart, gölge ismi yasak, köprü `:root` birebir eşit). Üreticide gerçek hata bulundu: köprü `tailwindcss`'i gömüyordu, README'nin iki-import sözleşmesini izleyen her tüketici build kırılıyordu | tailwind-design-system tour |
| 11 | `tdd` | 09-19 | `check-precommit-orphans` kapısı (CLI dikişi: rc + stdout) | **Düzeltme kapattı** (red→green) — yetim patch'i 24 saat sonra bloklayan kapı: 6/6, hook 19 (49→50). RED fazında harness kusuru: py3.9 union sözdizimi (testte düzeltildi) | tdd tour |
| 12 | `test-driven-development` | 09-19 | Aynı kapının bilinen-olay parmak-izi | **Düzeltme kapattı** (red→green) — arşivlenen 09-18 olay patch'iyle birebir aynı içerikteki yetim patch artık adı+`git apply` kurtarma yolunu söyleyen uyarı üretiyor; 8/8, bilinmeyen yetimler işaretlenmiyor (karşı-test) | test-driven-development tour |
| 13 | `typescript-advanced-types` | 09-19 | İki TS yüzeyi (dashboard-next, trend-db loader) | **Düzeltme kapattı** — loader'da iki kaçış yolu kaldırıldı: `as never[]` → üretilmiş `TrendRunCreateManyInput` (derleyici kırmızı→yeşil ile yapısal uyumluluk kanıtlandı), `json()` → **özyinelemeli tip nöbetçisi** (`isJsonInput`), kök-null → `Prisma.DbNull` | typescript-advanced-types tour (2026-09-19) — escape hatches → real types |
| 14 | `using-git-worktrees` | 09-19 | Worktree kurulumu ve commit ön koşulları | **Kapı/kural kurdu** — komutla Step-0 tespiti (6 bayat `/private/tmp` kaydı budandı); oturum işi branch'ten ÖNCE commit'lendi (`07e22aa`, `d1cbfb2`); pre-commit stash penceresi iki kez daha çalıştı → kural tekrar kanıtlandı. Yeni dosyalarda kapı gerçek kalıntı buldu (`/Users/...` mutlak yol, prettier uyumsuz JSON) | using-git-worktrees tour |
| 15 | `using-git-worktrees` (devam) | 09-19 | Taze worktree'de batarya | **Düzeltme kapattı** — klon tutarlılığı boşluğu: `test_pptx_export` modül seviyesinde çöküyordu (gitignore'lu `node_modules`); artık üretici hatası SKIP + sebep kaydı. Her iki yol kanıtlandı (npm öncesi SKIP, sonrası gerçek 160 kB pptx); worktree'de 139/139 | worktree baseline |
| 16 | `vercel-composition-patterns` | 09-19 | `dashboard-next` (React 19.2) | **Düzeltme kapattı** — boolean üçlü → `cva` varyantları (verdict/cell) ve token bağı: `app/` içindeki 10 hex sabitinin tamamı semantik utility'ye çevrildi, shadcn slotları repo token'larına bağlandı. 7/7 semantik utility derlendi, tsx'te 0 hex | vercel-composition-patterns tour |
| 17 | `vercel-react-best-practices` | 09-19 | `dashboard-next` (8 kategori tarama) | **Düzeltme kapattı** — `getLatest`/`getTrend` `React.cache()` ile sarıldı (`cache:no-store` isteklerde per-request dedup); gerekçe canlı kanıtlandı: iki tüketici, **1** upstream istek. Ayrıca koşullu render ternary'ye çevrildi | vercel-react-best-practices tour |
| 18 | `vercel-react-native-skills` | 09-19 | RN/Expo yüzeyi | **Kural gereği boş** (sıfır-yüzey) — modül-belirteç taraması 0, hiçbir package.json'da RN bağımlılığı, expo/metro/babel yapılandırması veya ios/android dizini yok. Ders: alt dize taraması 3 dosyada "export" ile yanlış alarm üretti. Uydurma iş yok | vercel-react-native-skills survey |
| 19 | `vercel-react-view-transitions` | 09-19 | Next 15.4/16 `ViewTransition` erişilebilirliği | **Düzeltme kapattı** (kapsam daraltma) — VT yalnız Next 15.5.4'ün vendored `react-experimental` kanalında; kararlı kanal 0 export (import build'i kırardı) → desenler Next 16'ya ertelendi. Adım-1 denetimi yine de karşılığını verdi: iç linkler ham `<a>` idi (tam sayfa yenileme) → `next/link`; soft-nav headless Chromium'da kanıtlandı (window marker 42→42) | vercel-react-view-transitions tour |
| 20 | `verify-chain` | 09-19 | Teslim zinciri kapıları (K0–K16) | **İnceleme-only / kapı doğrulandı** — beceri dokümanı bayat (19 kapı diyor, canlı 50); fail-closed üç noktada kanıtlandı: yanlış ortam (sistem python) → rc=1 P0, venv → rc=0 PASS (K8 12/12, K9 8 teorem, K16 58/58, K6 61/61), kurcalanmış girdi → FAIL | verify-chain audit |
| 21 | `web-design-guidelines` | 09-19 | `dashboard-next` app/ + `button.tsx` | **İnceleme-only** — 13 bulgu, 0 blocker: karanlık tema boşlukları, `animate-pulse` için `prefers-reduced-motion` yokluğu, `transition-all`, rol-süz `div`'de `aria-label` eksikliği, `h1` yokluğu, ham ts string (Intl yok), `tabular-nums` yokluğu, `role=alert` yokluğu. Düzeltmeler bu turda **uygulanmadı** | web-design-guidelines review |
| 22 | `webapp-testing` | 09-19 | `next :4321` + canlı Freebuff preview `:8000` (iki sunucu) | **Düzeltme kapattı** — E2E headless Chromium: verdict/4-istatistik pariteti, soft-nav, 0 konsol hatası. Bulunan gerçek hata: "Son 20 Koşum" başlığı altında **100** satır render ediliyordu (sunucu query string'i hiç okumuyor) → tüketici tarafı pencere (`slice(-20).reverse()`); Playwright kanıtı 100→20 | webapp-testing E2E |
| 23 | `workers-best-practices` | 09-19 | Cloudflare Workers yüzeyi | **Kural gereği boş** (sıfır-yüzey) — beş bağımsız kanıt: wrangler.toml yok, package.json envanterinde bağımlılık yok, `@cloudflare/` import 0, workflow'ta workers.dev/pages.dev deploy yok, worker giriş noktası/`new Worker(` yok | workers-best-practices surface audit |
| 24 | `wrangler` | 09-19 | wrangler CLI | **Kural gereği boş** — skill'in ilk adımı çalıştı: `wrangler --version` → yok. Kurulum **bilinçle atlandı**: yönetilecek komut yok (0 çağrı, sıfır Workers yüzeyi tekrar doğrulandı) → `-D` kurulumu tüketicisiz uydurma iş olurdu | wrangler skill turn |
| 25 | `writing-plans` | 09-19 | `docs/superpowers/plans/2026-09-19-dev-bootstrap.md` | **Düzeltme kapattı** — plan inline yürütüldü (bu harness'te dispatch yok, iki aşamalı inceleme yerine kapı kanıtı): `dev_bootstrap.sh` + 6 testlik sözleşme, red fazı doğru sebeple, gizli venv'de fail-closed kanıt, canlı `--check` rc=0. Zincir dersleri: kapsam kapısı ortada bir kez koştu (fail-closed tasarımı), 72 karakter başlık sınırı, harness heredoc'da kesme işareti bozar | writing-plans execution |
| 26 | `xlsx` | 09-19 | E-tablo yüzeyi | **Kural gereği boş** (sıfır-yüzey) — dört kanıt: xlsx/xlsm/csv/tsv dosyası 0, `openpyxl`/`pandas`/`xlsxwriter` importu 0, `csv` modülü kullanımı 0, boru hattında üretim/tüketim yok. Tetikleyici birincil girdi/çıktı olacak tablo ister; `history.jsonl` kullanıcı isteği olmadan onu saymıyor | xlsx surface audit |

## Maraton sonrası denetim turları (2026-09-27 → 09-28)

Beceri değil kapı/denetim ekseninde kaydedilmiş turlar. Aynı üç sütunlu
sözleşme, aynı kaynak.

| # | Tur | Tarih | Yüzey — neye bakıldı | Sonuç | Kanıt (`findings.md` §) |
|---|---|---|---|---|---|
| 27 | `gate-audit` | 09-27 | `check_precommit_orphans.py` arşiv parmak-izi kapsamı | **Düzeltme kapattı** — parmak-izi kaynağı `recovery_patches_20260918`'e SABİTLİYDİ; diskte 3 arşiv / 40 patch varken arşivlenen deltaların **38'i kapıya görünmüyordu** (aynı içerik yeniden yetim kalsa `KNOWN-INCIDENT` üretilemez). `ARCHIVE_GLOB` ile kendiliğinden genişledi; yeni sözleşme: taze tekrar `PRE-COMMIT PATCH RECURRENCE` basar, **bloklamaz** (exit 0). 8→13 test, 13/13. **Açık kalem:** 09-26 tarihli iki 185 kB patch 24 s penceresini 09-27 20:01'de aşıyor | gate-audit tour |
| 28 | `archive-audit` | 09-27 | Olay patch'i ↔ plan dosyaları ↔ bugünkü sürüm | **İnceleme-only** — dört sonuç: (1) hiç commit edilmemiş 247 satır (132'si teknik belirteç, **tamamı** bugün izlenebilir; 115'i belirteçsiz düzyazı, yalnız arşivde); (2) yeniden-yazım commit'inde (`07e22aa`) 109 teknik belirtecin tamamı dosyalarda yoktu ama **bugün başka yüzeylerde** yaşıyor → **kayıp 0**; (3) yalnız arşivde kalan tek dizgi Orca sürümü; (4) ters yön: patch'in sildiği hiçbir satır geri gelmemiş. Arşivin kurtarma değeri kanıtlı | archive-audit turu |
| 29 | `verify-001` | 09-27 | CSP altında hover + tıklama kanıtı | **Düzeltme kapattı** — kod yarısı zaten kapalıydı (inline `on*` 0, `data-tip` + SVG delege); canlı kanıt: hover 8/8, sıkı CSP, 0 ihlal. **Aynı sınıfın ikinci yarısı bulundu:** `test_dashboard_keyboard_nav` (14 canlı test) yalnız manifest'teydi, Playwright `a11y-gate`'te kurulu olduğu için `verify` adımında **modül seviyesinde sessizce skip** ediliyordu — üstelik süitte CSP ihlali sayacı yoktu. Çözüm: `check_security_browser.list` roster'ı (skip reddeden) + console/pageerror toplama + `_csp_violations()` + canlı DOM taraması + gerçek fare tıklaması. 14→18 test; hover 8/8, klavye 18/18 | verify-001 turu |
| 30 | `arbitrary-renk sızması` | 09-27 | `apps/dashboard-next` renk literalleri | **Kapı/kural kurdu** — ölçüm: arbitrary-hex utility **0**, ham hex/rgb/hsl **0**, Tailwind varsayılan paleti **0**. Taşıma zaten 09-19 tailwind turunda bitmişti; eksik olan **regresyon kapısıydı**. `check_tokens.py` sözleşme 8f: üç kural (arbitrary utility, ham literal, varsayılan palet) + meşru değerleri koruyan karşı-testler. Görsel QA: gerçek build'te hesaplanmış stiller token değerleriyle birebir, sayfada arbitrary sınıf 0; 66 renk-ailesi utility'nin tamamı derlenmiş CSS'te. 33→35 test | arbitrary-renk sızması turu |
| 31 | `mirror-@theme` | 09-27 | Dört marka aynasının kendi `@theme` köprüsü | **Düzeltme kapattı + yeni kapı** — 2243/3178 yuva üretildi; kapsam kuralı addan değil **DEĞERDEN** çözüldü (`--color-alpha: 255` renk sayılmıyor). linear 3 / primer 39 çakışma hakem kuralıyla çözüldü (`skip:key-collision`, değer dosyada kalıyor). Kapı B1–B7 fail-closed + `check-mirror-bridges` hook'u. Canlı doğrulama: gerçek Tailwind v4 derlemesinde 20/20 probe sınıfı, `bg-bg` DEĞİŞMEDİ. 25 test. **Yakalanan üretici hatası:** ilk üretimde `@theme` bloğu BOŞ çıktı (`split("-")[1]` `--color-…` adında boş) — sayım kilidi artık teste bağlı | mirror-@theme turu |
| 32 | `precommit-orphans` | 09-27 | Yetim patch'e çift parmak-izi + özel uyarı | **Düzeltme kapattı** — eşleşme gömülü satır olarak basılıyordu (scroll'lanıp geçilebilir) ve tek özet yalnız "birebir aynı" sorusuna cevap veriyordu. md5 **ikinci sinyal** olarak eklendi, oracle DEĞİL: etiket yalnız sha256 birebir eşleşmesinden doğar, çakışma ayrı tanı üretir (`ZAYIF-PARMAK-İZİ ÇAKIŞMASI`). Tek okuma-iki hesap (`Fingerprints`), eşleşme yokken gürültü yasağı, `usedforsecurity=False` (FIPS). 13→18 test, kırmızı önce | precommit-orphans turu |
| 33 | `trend-db loader TDD 2` | 09-27 | `--dry-run` prose → makine-okunur yüz + JS koşucusu | **Düzeltme kapattı** — `[DRY-RUN]` etiketi prose idi (insan metni); `--json` prose'in **yerine** geçiyor, sayılar `DryRunSummary`'de **bir kez** hesaplanıyor → ayrışma yapısal olarak imkânsız. `--json` tek başına exit 2, alan adı `insertAtMost`; `CliError` sınıfı. **Kapsam kaybı kapandı:** `.mjs` dosyaları keşfe de prettier'a da girmiyordu → yeni `test_trend_db_js_runner.py` fail-closed manifest'de (MIN_KURULU_VAKA eşiği). 11/11 JS · 18/18 Python · 3/3 sarmalayıcı. Ders: **aynı çıkış kodu iki farklı gerekçeyi karşılayabilir** — gerekçe de kilitlenmeli | trend-db loader TDD turu 2 |
| 34 | `trend-db loader TDD 3` | 09-28 | "eklenecek (en çok): 36" → kesin sayı | **Düzeltme kapattı** — rapor dili yanlış değildi ama karar için işe yaramıyordu: gerçek sayı **0**'dı (269 satırlık arşive karşı 36 satırlık pencere zaten yüklüydü). `--check-db` (salt-okunur DB) + `--keys-file` ile kapatıldı. Kırmızı önce 18 vaka, 12/29 → 29/29. Değişmezler sözleşmeye yazıldı (`insert ≤ insertAtMost` vb.). **İki sessiz yeşil yakalandı:** determinizm vakası iki koşunun aynı hatayı vermesini "eşit" sayıyordu; `liveCredentials()` tırnaklı `.env` değerini ham geçirip `P1001` veriyordu. Canlı ölçüm: 269 satır · 36 zaten var · **0 eklenecek** · 36 atlanacak; iki ardışık koşu aynı (yazmadığının kanıtı) | trend-db loader TDD turu 3 |

## Sonuç dağılımı

Tüm 34 satır için:

| Sınıf | Tur | Örnekler |
|---|---|---|
| **Düzeltme kapattı** | 18 | shadcn-ui, supabase-postgres, tailwind-design-system, tdd, test-driven-development, typescript-advanced-types, vercel-composition-patterns, vercel-react-best-practices, vercel-react-view-transitions, webapp-testing, remotion-best-practices, gate-audit, verify-001, mirror-@theme, precommit-orphans, trend-db TDD 2 ve 3, worktree baseline |
| **Kural gereği boş (sıfır-yüzey)** | 6 | rust-async-patterns, stripe-best-practices (beceri↔yüzey uyumsuzluğu), vercel-react-native-skills, workers-best-practices, wrangler, xlsx |
| **Kapı/kural kurdu** | 4 | systematic-debugging (×2), using-git-worktrees, arbitrary-renk sızması |
| **İnceleme-only** | 3 | verify-chain, web-design-guidelines, archive-audit |
| **Ortam engeli** | 2 | requesting-code-review, ruflo |
| **Uygulama (plan yürütme)** | 1 | writing-plans |

## Maratonun kalıcı bıraktığı izler

Beceri turlarının **yüzey etkisi repo kalıcılığıyla sınırlı**; kanıtın kendisi
iki yerde duruyor:

1. **Bu tablo** — tur → yüzey → sonuç (elle).
2. [`SKILL_SURFACE_INVENTORY.md`](SKILL_SURFACE_INVENTORY.md) — alan → kod
   yüzeyi (üretilir, fail-closed). Sıfır-yüzey alanları (`rn-expo`,
   `wrangler`, `xlsx`) buradaki 5 "kural gereği boş" satırının manifest
   karşılığıdır; kapı, listede yeni bir imza paketi görürse kırılır.

Maratonun en pahalı dersi tek satırda: **turların çoğu iş üretmedi, kanıt
üretti.** `rn-expo`/`wrangler`/`xlsx`/`rust` turlarında "uygulanacak hedef
yok" demek, iş uydurmamak ve bunu manifest'te iddia olarak sabitlemek demekti
— sıfır-yüzey kapısı bugün o iddiaları canlı ölçümle denetliyor.
