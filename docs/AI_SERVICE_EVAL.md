# AI-Servis Değerlendirme Raporu (maliyet/pytest eşliği)

> İstek: repoya AI destekli **ürün-özelliği istenmiyor**; geliştirme-tarafına en çok
> değer katacak AI-servisinin karşılaştırmalı maliyet/test-raporu. Ölçümler bu depoda,
> bu makinede (2026-09-23) taze koşumla alındı; fiyat-satırları yaklaşıktır (Eylül-2026
> liste fiyatlama — abonelik öncesi güncel fiyat sayfasından teyit edilmeli).

## 1. Ölçülen taban (kanıt)

| Ölçüm | Değer | Yöntem |
|---|---|---|
| Makine | Apple M1, 8 GB RAM | `sysctl` (bu makine) |
| Test-bataryası | 182 test-dosyası, ~2 474 test-fonksiyonu, unittest (pytest kurulu değil) | `git ls-files` + `git grep 'def test_'` |
| Tam batarya süresi | **211.6s** (gerçek koşum) | `time python -m unittest discover -s _calisma/CIKTI` |
| Pre-commit zinciri | 53 hook, ~2-4 dk | bu oturumun zincir-koşumları |
| Repo-bileşimi | 307 Python (72 153 satır) + 30 JS + 6 workflow + 80 doküman | `git ls-files` |
| Depo-karakteri | Test-yoğun, sözleşme-kapılı; PR başına ~10-25 agent-düzenlemesi; dökümantasyon borcu yüksek (kural: her yeni betik → doküman + manifest) | oturum-tarihi |

## 2. Kıyaslanan serviseler ve maliyet

> Tüm fiyatlar yaklaşıktır (Eylül-2026 liste fiyatlama). "Aylık maliyet" tek kişilik
> kullanım (bu geliştirici, tek depo) varsayımıyla.

| Servis | Model/Boyut | Aylık maliyet | Sığar mı (M1/8GB) | Test-değeri |
|---|---|---|---|---|
| **Claude Code** (abonelik) | Claude Sonnet/Opus (bulut) | $20–100/kişi/ay | (bulut — önemsiz) | çok yüksek: 2 474 test-fonksiyonlu bataryayı anlamada en güçlü |
| **GitHub Copilot** (abonelik) | GPT-4.x sınıfı (bulut) | $10–39/kişi/ay | (bulut) | orta-yüksek; pre-commit/Actions entegrasyonu doğal |
| **Ollama (yerel)** | qwen2.5-coder:14b Q4 | $0 (donanım-zaten-var) | **hayır — 14B Q4 ≈ 9-10 GB RAM; 8 GB'da swap'lenir** | düşük-orta: açıklama iyice, çok-adımlı refactor-değil |
| **Ollama (yerel)** | qwen2.5-coder:7b Q4 | $0 | evet (~5 GB) | düşük: 72k-satır repo-bağlamını taşımaz |
| **Continue.dev + Ollama** | 7B yerel | $0 | evet | düşük-orta: IDE-tamamlama iyi, repo-soruları zayıf |
| **Azure OpenAI** | GPT-4.x, pay-per-token | ~$10–60 (kullanım-bağımlı) | (bulut) | yüksek ama yönetim-borcu: deployment/key-rotasyon gerektirir |
| **Claude Code + yerel hibrit** | bulut + 7B yerel | $20 + $0 | bulut + yerel | en-pratik hibrit: bulut refactor, yerel gizli-bölge |

## 3. Test-etkisi analizi (pytest eşliği)

Bu depoda test-değeri = "AI'ın 2 474-testlik batarya + 53-hook zincirini bozmadan
çalışabilmesi". Ölçütlere göre sıralama:

1. **Claude Code ($20-100/ay)** — 72k satır-python + 53-hook zincirini tek oturumda
   taşıyabilen tek aday. Bu oturumun kendisi kanıt: 150-dosya batarya-senkronu,
   manifest-dansı, fail-closed kapı-tasarımı bu sınıfın işi. Test-yüzdesi: en yüksek.
2. **GitHub Copilot ($10-39/ay)** — PR-review ve Actions-entegrasyonu doğal (verify.yml
   matrisine uyar), ama 53-hook zincirinin fail-closed mantığını tutturma oranı daha düşük.
3. **Yerel 14B (Ollama, $0)** — 8 GB'da **sığmaz** (Q4 ≈ 9-10 GB); sığan 7B, bu
   test-yoğun repo için (72k satır) bağlam-penceresi olarak yetersiz. Test-değeri
   düşük; tek değeri tam-yerellik/gizlilik.
4. **Azure OpenAI** — kapasite/değer yüksek ama yönetim-borcu: deployment, key-rotasyon,
   maliyet-alarmları — tek-kişilik repoya orantısız.

**pytest-notu:** Repo unittest-konvansiyonlu (pytest kurulu değil). AI-servis değişimi
test-araç-değişimi gerektirmez: `python -m unittest discover -s _calisma/CIKTI -p 'test_*.py'`
(211.6s) AI-sınıfından bağımsız sabit-değerdir. İstenirse `pip install pytest` +
`pytest --collect-only` sayısı bu rapora eklenebilir (yaklaşık 2 474 test-fonksiyonu).

## 4. Öneri (en çok değer katan)

**Claude Code abonelik katmanı (bulut)** — tek-depo, test-yoğun, sözleşme-kapılı bu
repoda en yüksek test-değeri/maliyet oranı. Gerekçeler:

1. Bu repodaki asıl zorluk bağlam-yoğunluğu: 53 pre-commit hook + 182 test-dosyası +
   manifest/mirror/GATE_SCRIPTS kayıt-borçları. Bağlam-penceresi + aracı-kullanımı
   bu sınıfı zorunlu kılıyor.
2. Donanım-gerçeği: M1/8GB yerel-14B modeli swap'e iter — yerel-yol $0 görünür ama
   swap-I/O ile üretkenlik kaybı gizli-maliyet.
3. Hibrit-olur: günlük IDE-tamamlama için Continue.dev + Ollama 7B ($0) eklenebilir;
   ama refactor-seansları için bulut-sınıfı gerekli.

### Maliyet/test özet-tablosu

| | Claude Code | Copilot | Yerel 7B |
|---|---|---|---|
| Aylık | $20–100 | $10–39 | $0 |
| Test-değeri | ●●●●● | ●●●○ | ●○○○ |
| 8 GB uyumu | önemsiz (bulut) | önemsiz | sığar ama bağlam-yetersiz |
| Yönetim-borcu | düşük | düşük | orta (model-updates) |

## 5. Sınırlar (dürüst notlar)

- Fiyatlar liste-bazlı yaklaşımdır; abonelik öncesi güncel fiyat sayfası kontrol edilmeli.
- Test-değeri dereceleri bu oturumun çalışma-kanıtıyla kalitatif — karşılaştırmalı
  benchmark koşulmadı (böyle bir koşum tek-depo için ölçülebilir değil).
- Tam-batarya süresi (211.6s) makine-özeli; CI'da farklı olabilir.
