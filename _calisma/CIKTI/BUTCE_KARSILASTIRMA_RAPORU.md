# Bütçe tahmini yöntem karşılaştırması — Stoic-Hume V5

**Amaç:** `verify_delivery.py` bütçe kalkanında dosya tipine göre ağırlıklı tahmin ile
evrensel `bytes/4` tahminini yan yana karşılaştırmak ve `budget_ratios`'un güncel
(8/8/100/100) değerleriyle farkı belgelemek.

> **V5l (2026-08-18) güncellemesi:** Bu rapor artık `budget_ratios = 8/8/100/100`
> üzerinden yeniden üretildi. Oranlar artık elle yazılmış sabitler (3/8/12/20)
> **değil**; `gen_config.py` tarafından paketin gerçek bayt karışımından
> otomatik türetiliyor. Bu, ağırlıklı tahminin yönünü ve büyüklüğünü kökten
> değiştirdi — ayrıntı §3'te.

## 1. İki yöntem

### (a) Evrensel (v3_verify.py H4) — bağımsız referans
Her dosya tipi için aynı oran:
```
token ≈ bytes / 4
cost   = token / 1_000_000 × $3.0 + $0.55
```

### (b) Ağırlıklı (dosya tipi bazlı) — otomatik türetilen oranlar
`budget_ratios` artık `gen_config.py` tarafından paketin GERÇEK bayt karışımından
hesaplanıyor (`compute_budget_ratios`, tek kaynak: `verify_delivery.py`
`compute_type_bytes` ile aynı kırılım). Formül (belgeli, deterministik):

```
pay_k   = bytes_k / total_bytes           (tip k'nın paketteki payı)
ratio_k = clamp(round(4 / pay_k), 1, 100)   (4 = evrensel bytes/token sabiti)
```

Yorum: pakette **baskın** tip (yüksek pay) düşük oran → daha çok token alır
(işin ana gövdesi); **marjinal** tip (düşük pay) yüksek oran → az token alır.
Sıfır baytlı tipler `ratio=100` (marjinal, token katkısı yok).

| Tip | Güncel ratio | Nereden geliyor |
|---|---|---|
| text | **8** | pay≈52.2% → round(4/0.522) = 8 |
| pdf | **8** | pay≈47.7% → round(4/0.477) = 8 |
| archive | **100** | 0 bayt → marjinal |
| binary | **100** | pay≈0.03% → clamp(4/0.0003)=14042 → 100 |

Karar yöntemi (`--budget-method` / config `budget_method`):
- `universal`: yalnız (a)
- `weighted`: yalnız (b)
- `both` (**varsayılan, fail-closed**): `max(universal, weighted)` — daha kötümser olan kazanır

## 2. Stoic-Hume V5 paketi üzerinde karşılaştırma

Gerçek teslim içeriği (`_calisma/CIKTI/TESLIM_V5_FINAL_2026-08-17.zip`, açılmış):

| Tip | Bayt | Pay | Token (evrensel) | Token (ağırlıklı) |
|---|---:|---:|---:|---:|
| text | 363 056 | 52.2 % | 90 764 | **45 382** (÷8) |
| pdf | 331 822 | 47.7 % | 82 955 | **41 477** (÷8) |
| archive | 0 | 0 % | 0 | 0 (÷100) |
| binary | 198 | 0.03 % | 49 | **1** (÷100) |
| **TOPLAM** | **695 076** | 100 % | **173 769** | **86 860** |

> Not: evrensel toplam `total_bytes // 4 = 173 769` olarak **bütün üzerinden**
> hesaplanır (kod davranışı); tip başına floor'ların toplamı 173 768'dir —
> aradaki 1-token farkı floor yuvarlaması artefaktıdır, anlamlı değildir.
> Ağırlıklı toplam tip başına floor'ların toplamıdır (45 382+41 477+0+1=86 860),
> birebir kod davranışı.

| Yöntem | Token | USD ($3/M + $0.55) |
|---|---:|---:|
| Evrensel (bytes/4) | 173 769 | **$1.07** |
| Ağırlıklı (tip bazlı, 8/8/100/100) | 86 860 | **$0.81** |
| **Fark** | **-86 909 (-50.0 %)** | **-$0.26** |

## 3. Yorum

- **Fark artık büyük ve yönü net:** eski rapor (oranlar 3/8/12/20) ağırlıklı
  tahmini `161 582` token ($1.03) veriyordu — evrensele göre yalnızca **-6.6 %**.
  Yeni otomatik oranlarla (8/8/100/100) ağırlıklı tahmin `86 860` token ($0.81) →
  **-50.0 %**. Bunun nedeni text oranının **3 → 8**'e çıkmasıdır: paketin en
  büyük sınıfı (text, %52) artık yarı yoğunlukta sayılıyor.
- **Neden text 8'e, pdf 8'e çıktı?** Eski 3/8/12/20 oranları *içerik
  yoğunluğu* sezgisini kodluyordu (text en yoğun, arşiv/binary en seyrek).
  Yeni formül ise *pay* sezgisini kodluyor: baskın tipler düşük oran, marjinal
  tipler yüksek oran. Paketimiz neredeyse eşit iki sınıftan oluştuğu için
  (text %52.2, pdf %47.7) ikisi de round(4/pay) ≈ 8'e oturdu → ağırlıklı
  tahmin kabaca `bytes/8` oldu, yani evrenselin yarısı.
- **`both` modu hâlâ fail-closed:** `max($1.07, $0.81) = $1.07` → kalkan
  evrenseli seçer. Yani raporlanan sınır **değişmedi** ($1.07 / limit $30);
  ağırlıklı tahmin yalnızca karşılaştırma ve analiz içindir.
- **Hangi yöntem doğru?** Bu artık bir ampirik/tokenizer sorusu. Pay-tabanlı
  formül, "ana gövde daha çok token almalı" ön kabulüne dayanır; içerik
  yoğunluğu (eski 3/8/12/20) ise "metin bayt başına daha çok token üretir"
  ön kabulüne. İkisi de literatür tahminidir, gerçek fatura değildir (§5).

## 4. Doğrulama

Komutlar (gerçekten çalıştırıldı, güncel sonuçlar):
```bash
python3 verify_delivery.py --dir _calisma/CIKTI --budget 30 --budget-out budget.json
python3 verify_delivery.py --dir _calisma/CIKTI --budget-method universal
python3 verify_delivery.py --dir _calisma/CIKTI --budget-method weighted
```

Çıktı kırılım satırı:
```
[BÜTÇE] ~173769 token → $1.07 (limit $30.0, içerik 695076 B, yöntem=both)
[BÜTÇE]   evrensel (bytes/4):  173769 tok → $1.07
[BÜTÇE]   ağırlıklı (tip bazlı): 86860 tok → $0.81
[BÜTÇE]   kırılım: text=363056B pdf=331822B archive=0B binary=198B
```

`--budget-out` ile yazılan sidecar tam `comparison` objesi içeriyor:
```json
{
  "comparison": {
    "universal": {"tokens": 173769, "usd": 1.07, "ratio": "bytes/4 (v3_verify.py H4)"},
    "weighted":  {"tokens": 86860, "usd": 0.81,
                  "ratios": {"text": 8, "pdf": 8, "archive": 100, "binary": 100},
                  "by_type": {"text": 363056, "pdf": 331822, "archive": 0, "binary": 198}}
  }
}
```

`gen_config.py --dry-run` (oranların tek kaynağı) doğrulaması:
```
budget_ratios     : {'text': 8, 'pdf': 8, 'archive': 100, 'binary': 100}
tip kırılımı      : {'text': 363056, 'pdf': 331822, 'archive': 0, 'binary': 198} (695076 B)
```

## 5. Şeffaflık

- Oranlar **literatür tahmini** değil, **paket payından türetilmiş** bir modeldir —
  gerçek faturalama değildir. Doğru token sayısı ancak gerçek tokenizer (ör.
  OpenAI/Anthropic) ile ölçülür.
- Pay-tabanlı formülün bir yan etkisi: küçük ama anlamlı bir tip (ör. %2'lik
  arşiv) `round(4/0.02)=200 → clamp 100` alır; yani çok küçük tipler her zaman
  100'e sıkışır ve token katkıları neredeyse sıfırlanır. Bu, "marjinal tipler
  az token alır" ön kabulünün bilinçli sonucudur.
- `budget_ratios` config'te override edilebilir; farklı tokenizasyon/tahmin
  varsayımı olan projeler oranları elle değiştirebilir — ancak `gen_config.py`
  (ve `update-config` pre-commit hook'u) bunları paket içeriğinden **yeniden
  türeteceği** için elle değişiklik commit'te geri döner. Kalıcı özel oranlar
  için `compute_budget_ratios` formülü değiştirilmelidir.
- Mevcut `v3_verify.py` mantığı korundu: `bytes/4` tahmini yan yana raporlanır,
  bağımsız doğrulanabilir referans olarak. `both` varsayılanı fail-closed'dur:
  iki yöntemden maliyet-yüksek olan kalkan sınırına girer.
