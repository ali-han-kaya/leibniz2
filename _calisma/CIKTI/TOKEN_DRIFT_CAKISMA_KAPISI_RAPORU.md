# Token drift & çakışma kapısı — teslim raporu

Kapı: [`design-system/scripts/check_token_conflicts.py`](../../design-system/scripts/check_token_conflicts.py)
Roster (tek kaynak): [`design-system/scripts/token_layers.list`](../../design-system/scripts/token_layers.list)
Sözleşme testi: [`_calisma/CIKTI/test_check_token_conflicts.py`](../CIKTI/test_check_token_conflicts.py)

## Ölçülen boşluk

Katman **başına** drift kapıları vardı (`check_tokens.py` contract 1–9,
`check_<marka>_tokens.py`, `check_mirror_bridges.py`,
`report_vercel_dashboard_drift.py`) ama **katmanlar arası** çakışmayı ve
üretilmiş kopyanın sessiz kaymasını ölçen tek bir kapı yoktu:

* aynı ad iki dosyada aynı kapsamda **farklı** değerle tanımlıysa kazananı
  import sırası belirler (sessiz tema kayması) — hiçbir kapı bunu görmez;
* bir dosyada aynı blokta aynı ad iki kez farklı değerle geçerse sonuncusu
  sessizce kazanır;
* `_calisma/landing/landing.html` kanonik paletin **üretilmiş** kopyasıdır ve
  bağımsız kapıya bağlı değildi (bugün 106/106 birebir, ama pinlenmiyordu);
* yeni bir token dosyası açmak hiçbir kapıyı kırmaz (kapsam sessizce daralır);
* token kapılarının tamamı **advisory** pre-commit zincirinde yaşıyordu
  (`continue-on-error: true`) → token farkı merge'ü bloklamıyordu.

## Sözleşmeler (hepsi fail-closed)

| Kural | Ne ölçer |
|---|---|
| **K1** blok-içi tekrar | aynı dosya+kapsam+ad, >1 **farklı** değer (sonuncusu sessizce kazanır) |
| **K2** katman çakışması | `canonical\|bridge\|variant` biriminde aynı kapsam+ad ≥2 dosyada **farklı** değerle → kazananı import sırası belirler. Aynı değer serbesttir (üretilmiş kopyalar böyle çalışır) |
| **K3** varyant kapsamı | varyant yalnız kendi `:root[data-theme="<marka>"]` kapsamında tanım yapar (kapsam sızıntısı = global çakışma) |
| **K4** kopya drifti | `copy` katmanının `:root` + `light` kümeleri `tokens.css` ile ad/adet/değer olarak birebir |
| **K5** kayıtsız katman | token tanımlayan her dosya roster'da **ya da** gerekçeli `capture` satırında; roster'ın hiçbir dosyaya uymayan satırı da ölü kayıttır (iki yönlü kapsam) |
| **K6** tüketici gölgesi | `consumer` çıplak `:root`ta kendi yuva eşlemesini kurabilir, ama kanonik bir adı **farklı** değerle yeniden yazamaz |

Fail-closed ölçüm: roster yok/bozuk, kanonik referans `canonical` değil/yok,
ayrıştırılan tanımlar metindeki `--x: …;` çiftleriyle **uyuşmuyor** (kapsam
ataması güvenilmez) ya da tarama kümesi **boş** ise `rc=2` — kör kapı PASS
üretmez. Exit: `0` temiz, `1` bulgu, `2` kullanım/ölçüm hatası.
`--json` stdout'ta **tek** JSON belgesi (teşhis `stderr`'de), `--md-out`,
`--list`. READ-ONLY, OFFLINE, stdlib-only.

## Bağlama

* `.pre-commit-config.yaml` → `check-token-conflicts` hook'u (67 hook; doc
  envanteri `check_precommit_inventory.py` ile pinli).
* `skills/verify-chain/SKILL.md` → hook envanteri bloğuna eklendi.
* `_calisma/CIKTI/test_coverage_report.py` → `HOOK_COVERAGE` eşlemesi
  (`check-token-conflicts` → `test_check_token_conflicts.py`).
* `.github/workflows/verify.yml` → **"Design-token drift & collision gate
  (fail-closed)"** adımı: beş token kapısını (`check_tokens.py`,
  `check_brand_mirrors.py`, `check_mirror_bridges.py`,
  `report_vercel_dashboard_drift.py --check`, `check_token_conflicts.py`) tek
  çıkış kodunda toplar ve `--json` ile düz çağrının çıkış kodları ayrışırsa da
  kırmızıya düşer. Yeni artifact adı **açılmaz**: makine-okunur kopyalar
  mevcut `logs/` dizinine yazılır (ARTIFACT_JOBS/PUBLISH_SCENARIO
  sözleşmeleri değişmez).
* `design-system/README.md` → kapı bölümü.

## Doğrulama kanıtı

| Kontrol | Sonuç |
|---|---|
| `python3 design-system/scripts/check_token_conflicts.py` | rc=0 · 10 katman · 5103 tanım · 5 kapsam · K1..K6=0 |
| `--json` stdout | tek JSON belgesi (`status=ok`, `counts.total=0`), verdict `stderr`'de |
| `python3 -m unittest _calisma.CIKTI.test_check_token_conflicts` | **23/23 OK** (temiz pyc öneki ile) |
| Mutasyon kanıtı (K1..K6, her biri ayrı izole pyc öneki) | **6/6 KIRMIZI** → her kuralın iddiası non-vacuous; kaynak sha256 geri yüklemede birebir |
| CI adımı shell-sim (workflow'dan çıkarılan gövde, `bash -n` + gerçek koşum) | `bash -n` OK · rc=0 · `logs/token_gate_rows.txt` + `token_conflicts.json/md` üretildi · özet tablosu 5/5 `exit 0` |
| CI adımı fail-closed sim (bir kapı `false` ile düşürüldü) | **rc=1**, verdict `1` → toplu çıkış gerçekten bloke ediyor |
| Kapsam/kapı regresyonları | `test_check_design_tokens` 39/39 OK · `test_check_precommit_inventory` 27/27 OK · `check_precommit_inventory.py` rc=0 · `test_gate_coverage_sync` 4/4 · `test_gate_scripts_meta_guard` 15/15 · `test_ci_hygiene_gate` 9/9 · `test_doc_job_sync` 10/10 · `check_workflow_artifact_docs.py` rc=0 · `gen_verify_jobs_map.py --check` rc=0 |

## Ortam tuzağı (yerel doğrulamayı geçersiz kılan)

macOS `/usr/bin/python3` `sys.pycache_prefix`'i
`~/Library/Caches/com.apple.python` yapar. Bu dizindeki **bayat `.pyc`**
başlığı (mtime+size) güncel kaynakla **birebir çakıştığı için** Python
kaynağı hiç okumadan eski kodu yükledi: kapı dosyası 23/23 yeşil koşarken
sonradan `test_t2_k6…` kırmızı göründü — kod değişmemişti.

* Boyut/mtime çakışması olan bir `.py` düzenlendikten sonra yerel doğrulama
  yanıltıcıdır. Doğrulama şu iki yoldan biriyle yapılmalı:
  `rm ~/Library/Caches/com.apple.python/**/check_token_conflicts*.pyc`
  ya da `PYTHONPYCACHEPREFIX=/tmp/pyc-<tekil>` ile **izole** önbellek.
* Yukarıdaki mutasyon kanıtı bu yüzden her mutasyon için ayrı pyc önekiyle
  koşulmuştur (ilk harness, aynı saniye + aynı boyut çakışması yüzünden
  K2/K5'i yanlışlıkla "vakum" göstermişti — ölçüm hatasıydı, test hatası değil).
* CI'da etki yok: Linux, temiz checkout, `pycache_prefix` ayarsız.

## Bilinen kırmızılar (bu işten değil)

İkisi de **HEAD'de yeşil** (temiz `git worktree` ile doğrulandı); kırmızılar
paylaşılan çalışma ağacındaki **başka** yarım düzenlemelerden geliyor:

* `test_gated_schedules.test_scheduled_workflows_call_a_gate_script` →
  `.github/workflows/vercel-deploy-check.yml` (MM) kapı script'i çağırmıyor;
  aynı dosya HEAD'de de çağırmıyor ama HEAD'in test dosyası farklı (38 test
  yeşil). Çalışma ağacındaki `test_gated_schedules.py` 784 → 314 satıra
  inmiş (yabancı düzenleme).
* `test_coverage_report` → 8 test dosyası kapsamsız: 6'sı **untracked** (başka
  ajanların yeni dosyaları), 2'si (`test_security_cron_schedule.py`,
  `test_design_token_collision.py`) HEAD'de listeliyken çalışma ağacı
  diff'inde ~20 satırlık toplu silmeyle düşürülmüş; benim eklediğim satır
  (`check-token-conflicts` → `test_check_token_conflicts.py`) yerinde ve
  tabloda 23 testle görünüyor.

## Sınırlamalar / belirsizlik

* Gerçek CI koşulmadı (CI HEAD'i koşar; bu değişiklik commit'siz). Adım
  yerelde CI gövdesiyle simüle edildi.
* `actionlint` bu makinede **kurulu değil** → workflow YAML lint'i
  doğrulanamadı; adımın gövdesi `bash -n` ile doğrulandı ve YAML parse'ı
  `gen_verify_jobs_map.py --check` / `test_ci_hygiene_gate` ile dolaylı
  denetlendi.
* `audit_live_ci_sync.py`'nin "yerel ↔ canlı CI" karşılaştırması commit'siz
  değişiklikte anlamlı sonuç vermez (ayrıca bilinen yabancı kırmızılar var).
* Kapı **statik**tir: CSS değer çözümlemesi (var() zinciri, `color-mix`,
  hesaplanmış stil) yapmaz; `design-system/**`, `globals.css`,
  `_calisma/landing/*.html`, `_calisma/CIKTI/preview.html` kapsamındadır.
  Marka aynaları (`*/raw.css`, `*/tokens.css`, `*/tokens.json`) sözleşme
  gereği `capture`'dır — onları `check_<marka>_tokens.py` pinler.
* K2 "aynı değer serbest" kuralı bilinçlidir: üretilmiş kopyalar paylaşılan
  adları aynı değerle yazar; farklı değere izin vermemek sessiz kaymayı
  yakalayan asıl mekanizmadır.

## Öneriler (isteğe bağlı sertleştirme)

1. `.pyc` bayatlığı için CI dışı bir "temiz önbellek" hatırlatıcısı: yerel
   doğrulama betiklerinin başına `PYTHONPYCACHEPREFIX` izolasyonu.
2. `logs/token_conflicts.json`'u (mevcut `logs/` artifact'ı içinde) K-layers
   özetine bağlamak — ayrı artifact/`ARTIFACT_JOBS` sözleşmesi kararıdır.
3. K2'yi `landing`'in ürettiği kopya için K4 ile birlikte pin tutmaya devam
   etmek (landing yeniden üretilmezse bugün K4 kırmızıya düşer).
