# a11y Preview Taraması — axe-core (2026-09-24)

Araç: `a11y_gate.py` (axe-core pinli bundle `vendor/axe.min.js`, sha256-kapılı;
Playwright headless Chromium). Eşik: critical/serious = **blocking**,
moderate/minor = warn, incomplete = report-only (`a11y_gate_config.json`).

## Tarama-matrisi

| Hedef | Sonuç | Bulgu |
|---|---|---|
| Yerel canlı-daemon `:8000` (önce) | **FAIL** | `scrollable-region-focusable` (serious, blocking) nodes=2 + `color-contrast` incomplete ×130 |
| Vercel `https://leibniz2.vercel.app` | **taranamaz** | Frontend deploy-dışı: `/` ve `/preview.html` 404 (yalnız `/api/*` fonksiyonları) — DOM yok |
| Yerel canlı-daemon `:8000` (fix-sonrası) | **PASS** | `color-contrast` incomplete ×49 (report-only, exit-kodunu değiştirmez) |
| Taze-daemon (repo-CIKTI, cached-run, fix-öncesi) | **PASS** | `color-contrast` incomplete ×13 |
| Taze-daemon (fix-sonrası) | **PASS** | `color-contrast` incomplete ×13 |

Rapor artefaktları (`_calisma/CIKTI/`): `a11y_report_live.json` (canlı,
fix-öncesi FAIL), `a11y_report_live_after.json` (canlı, fix-sonrası PASS),
`a11y_report_local.json` (taze-daemon, fix-öncesi PASS),
`a11y_report_fresh_after.json` (taze-daemon, fix-sonrası PASS).

## Bulgu ve fix

- Kural: `scrollable-region-focusable` — hedef `#stdout`
  (`<pre id="stdout">`, canlı-log paneli). CSS `overflow:auto` kaydırılabilir-
  bölge yapıyor; odaklanabilir-içerik/`tabindex` yoktu → axe serious.
- Fix: `<pre id="stdout" tabindex="0">` (klavye-erişilebilir kaydırma;
  A-seti sözleşmelerini bozmaz — DOM-yapısı korunur).
- Yayılım: repo-kaynağı → `update_preview.sh` build-stamp'li mirror-yazımı →
  canlı-daemon restart'sız yeni HTML (stamp `git e7401b9`).

## Tarama-altyapısı notu (CSP-temiz yol)

preview_server nonce-CSP'si (`script-src 'self' + nonce`) inline axe
enjeksiyonunu bloklar. Yeni sözleşme: sunucu `/vendor/axe.min.js` route'u
(PREVIEW_DIR/vendor altından, fail-closed 404) → gate bundle'ı same-origin
`<script src>` ile yükler; CSP-bypass enjeksiyonu yalnız eski-daemon yedeği.
Mirror-paritesi: `sync_verify_mirror.sh` PREVIEW_FILES'a
`vendor/axe.min.js` girdisi eklendi.

## Yan-bulgu (kapatıldı)

`serve_preview` çıplak `open()` ile mirror'da HTML-yokken daemon-thread'ini
öldürüyordu (verify-mirror sunucusu `/preview.html`'de "empty reply" —
ölçüldü). Fail-closed 404 eklendi; `test_preview_server` route-testi
`vendor_axe` ile genişletildi (171/171 yeşil).

## Sınırlar

- `color-contrast` incomplete: axe opaklık/kaplama-belirsizliğini kesinleştir-
  emez; report-only politika. Sayı, sayfa-durumuna göre değişir (cached-run
  içeriği: 52/49 canlı, 13 taze).
- Vercel'de tarama ancak statik-dashboard yayınlanınca anlamlı olur
  (bkz. docs/VERCEL_DEPLOYMENT.md §Frontend notu) — aynı gate `--base-url
  https://…` ile koşar.
