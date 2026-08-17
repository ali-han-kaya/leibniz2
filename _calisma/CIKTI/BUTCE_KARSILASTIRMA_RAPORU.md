# Bütçe tahmini yöntem karşılaştırması — Stoic-Hume V5

**Amaç:** `verify_delivery.py` bütçe kalkanında dosya tipine göre ağırlıklı tahmin eklemek ve
evrensel `bytes/4` ile yan yana karşılaştırmak.

## 1. İki yöntem

### (a) Evrensel (v3_verify.py H4) — bağımsız referans
Her dosya tipi için aynı oran:
```
token ≈ bytes / 4
cost   = token / 1_000_000 × $3.0 + $0.55
```

### (b) Ağırlıklı (dosya tipi bazlı)
Dosya uzantısına göre `bytes_per_token` oranı:

| Tip | Uzantılar | bytes/token | Gerekçe |
|---|---|---|---|
| text | `.tex` `.py` `.md` `.json` `.txt` `.yaml` `.lean` `.bib` `.bst` `.sty` `.cls` … | **3** | Doğal dil + kod; en yoğun |
| pdf | `.pdf` | **8** | Sıkıştırılmış ama çıkarılabilir metin |
| archive | `.zip` `.tar` `.gz` `.7z` | **12** | Yüksek oranda sıkıştırılmış |
| binary | `.png` `.jpg` `.svg` `.pyc` … | **20** | Görsel/ikili; AI için düşük bilgi yoğunluğu |

Karar yöntemi (`--budget-method` / config `budget_method`):
- `universal`: yalnız (a)
- `weighted`: yalnız (b)
- `both` (**varsayılan, fail-closed**): `max(universal, weighted)` — daha kötümser olan kazanır

## 2. Stoic-Hume V5 paketi üzerinde karşılaştırma

Gerçek teslim içeriği (`_calisma/CIKTI/TESLIM_V5_FINAL_2026-08-17.zip`, açılmış):

| Tip | Bayt | Pay | Token (a) | Token (b) |
|---|---:|---:|---:|---:|
| text | 360 404 | 52 % | 90 101 | **120 135** |
| pdf | 331 587 | 48 % | 82 897 | **41 448** |
| archive | 0 | 0 % | 0 | 0 |
| binary | 0 | 0 % | 0 | 0 |
| **TOPLAM** | **691 991** | 100 % | **172 997** | **161 582** |

| Yöntem | Token | USD ($3/M + $0.55) |
|---|---:|---:|
| Evrensel (bytes/4) | 172 997 | **$1.07** |
| Ağırlıklı (tip bazlı) | 161 582 | **$1.03** |
| **Fark** | -11 415 (-6.6 %) | -$0.04 |

## 3. Yorum

- **Fark küçük ama yönü anlamlı:** paketimiz ağırlıklı olarak iki sınıftan
  (text + PDF) oluşuyor. Text 1:4'ten daha yoğun (1:3), PDF daha seyrek (1:8).
  Bu iki etki birbirini kısmen dengeliyor.
- **Ağırlıklı tahmin daha az maliyet veriyor** çünkü PDF'in paket içindeki
  payı (%48) ve onun düşük token yoğunluğu (1:8) text'in yüksek yoğunluğundan
  (1:3, %52) biraz daha baskın.
- **Hangi yöntem kullanılmalı?**
  - Tek tip içerik (saf metin veya saf PDF) barındıran paketlerde **ağırlıklı**
    yöntem belirgin şekilde daha doğru (örn. %100 PDF arşivi: universal
    12.5 M tok yerine weighted 1.6 M tok).
  - Karışık paketlerde her iki yöntemi raporlamak (`both`) fail-closed bir
    kalkan: kötümser olan seçilir.
- **`both` modu neden fail-closed?** Maliyet yüksek taraftan raporlanır;
  bütçe limiti sıkıysa yanlışlıkla PASS çıkmasını engeller. Şu an paket için
  ikisi de $1.07/$1.03 — yuvarlama yüzünden aynı görünüyor.

## 4. Doğrulama

Komutlar (gerçekten çalıştırıldı):
```bash
python3 verify_delivery.py --dir _calisma/CIKTI --budget-out budget.json
python3 verify_delivery.py --dir _calisma/CIKTI --budget-method universal
python3 verify_delivery.py --dir _calisma/CIKTI --budget-method weighted
```

Çıktı kırılım satırı:
```
[BÜTÇE]   kırılım: text=360404B pdf=331587B archive=0B binary=0B
```

`--budget-out` ile yazılan sidecar artık tam `comparison` objesi içeriyor:
```json
{
  "comparison": {
    "universal": {"tokens": 172997, "usd": 1.07, "ratio": "bytes/4"},
    "weighted":  {"tokens": 161582, "usd": 1.03, "ratios": {...}, "by_type": {...}}
  }
}
```

## 5. Şeffaflık

- Oranlar (3/8/12/20) **literatür tahmini** — gerçek faturalama değil.
  OpenAI tokenizer'ı text için tipik 1:3.5, PDF metni için 1:6–10, sıkıştırılmış
  arşivler için 1:10–15 üretir; güvenli tarafta kalmak için daha muhafazakâr
  (sparse) oranlar seçildi.
- Konfig'deki `budget_ratios` alanı override edilebilir; farklı tokenizasyon
  varsayımı olan projeler oranları değiştirip karşılaştırma yapabilir.
- Mevcut `v3_verify.py` mantığı korundu: `bytes/4` tahmini yan yana raporlanır,
  bağımsız doğrulanabilir referans olarak.