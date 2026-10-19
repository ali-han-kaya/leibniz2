# ADR: Dashboard denklem galerisi sekmesi — kontrast ve tema köprüsü sözleşmeleri

**Durum:** Kabul edildi (2026-10-15 — `_calisma/CIKTI/preview.html`,
`preview.js`, `preview_server.py`'de uygulandı; bu ADR yazıldığı an
worktree'dedir, commit edilmemiştir).

**Bağlam:**

- Denklem galerisi, Z3 galerisi desenıyla (`dash-tabs` + `hidden` view) mevcut
  preview dashboard'una üçüncü sekme olarak eklendi; veri tek kaynaktan:
  kanonik `equations/manifest.json` (16 id; title/meta/page kaynak-bağlı).
- Canlı E2E'de iki gerçek erişilebilirlik kusuru ölçüldü:
  1. **Hover kontrastı:** `button:hover{opacity:.85}` kuralı eq-card'ı da
     yakalıyordu; opaklık blend'i metni axe'ın ölçümünde **4.37:1**'e düşürüyordu
     (11px metin için4.5 gerekli) — sequence+hover ile reprod.
  2. **Light temada pasif sekme:** light `button` override'ı
     (`:root[data-theme="light"] button { color:var(--on-accent) }`,
     özgüllük 0,2,1) pasif sekme kuralını (0,2,0, `--fg-dimmed`) eziyordu;
     sonuç **1.12:1** (beyaz üzerine krem).
- HTML'e eklenen statik `/design-system/stripe-theme.css` +
  `vercel-theme.css` link'leri404/MIME hatası üretiyordu; tema döngüsü
  (dark→light→stripe→vercel) JS toggle'ındadır (`THEMES` dizisi).

**Karar:**

1. **Hover/focus'ta `opacity:1`:** Vurgu zaten box-shadow + outline ile
   sağlanır; opaklık düşüşü görsel bir tercih değil, kontrast kusuruydu.
2. **Light köprüsü:** `:root[data-theme="light"] .dash-tabs [role="tab"]`
   kuralı eklendi — `.rh-filter button` köprüsünün aynısı (override'ın
   ezmesini aynı özgüllükle geri alır). Pasif sekme rengi her iki temada AA
   olan `--fg-dimmed`'e çekildi (dark `#b6bec7` / light `#56504a`,
   tokens.css'in kendi AA notlarıyla uyumlu).
3. **Tema linkleri JS'e ait:** Statik stripe/vercel `<link>`'leri HTML'den
   kaldırıldı; gate'in tema yükleme sözleşmesi toggle'ın sorumluluğundadır.

**Sonuçlar:**

- Final E2E: `axe_violations: []` (her iki sekme), `console_errors: []`,
  responsive4→2 sütun; a11y gate dark+light **PASS/PASS** (CI komutuyla).
- Gelecekteki `.eq-card` alt stillerinde opaklık kalıntısı kontrast kusuru
  üretir — kapı: `test_equation_gallery_tab.py` + canlı axe E2E.

**Reddedilen alternatifler:**

- *`.eq-src` rengini koyulaştırmak:* Kaynak blend'i 4.37 yapmaya devam ederdi
  (sorun renk seçimi değil, katman opaklığıydı).
- *Light `button` override'ını genellemek:* Tüm sayfadaki düğmeleri etkilerdi;
  sorun yalnız pasif sekme etiketindeydi — en küçük köprü tercih edildi.

**Kapı bağı:** `_calisma/CIKTI/test_equation_gallery_tab.py` (12 test),
`a11y_gate.py` (dark+light matrisi, verify.yml).
