# Recovery patches (2026-09-18) — köken ve kanıt

Bu dizindeki iki dosya **çalışma-anlık görüntüsü yamalarıdır**, uygulanmış
değişiklik değildir. Neden durdukları ve nasıl doğrulanacakları aşağıda.

| Dosya | Boyut | Dosya | Satır farkı | Üretim zamanı |
|---|---|---|---|---|
| `patch1789754982-84993` | 38 721 B | 10 | +433 / −49 | 2026-09-18 |
| `patch1789755439-10960` | 17 818 B | 7 | +163 / −19 | 2026-09-18 |

Dosya adı `<epoch>-<pid>` biçiminde: epoch üretim anını, ikinci kısım yamayı
üreten sürecin kimliğini taşır. İki yama da aynı anda değil, ~7,5 dakika
arayla üretilmiş (`1789754982` → `1789755439`).

## Ne içeriyorlar

Yedi dosya her ikisinde de ortak:

| Dosya | birinci (`…982`) | ikinci (`…439`) |
|---|---|---|
| `.gitignore` | +14 / −0 | +10 / −0 |
| `_calisma/CIKTI/check_unit_tests.list` | +3 / −0 | +2 / −2 |
| `_calisma/CIKTI/preview.html` | +20 / −12 | +20 / −12 |
| `_calisma/CIKTI/preview_server.py` | +91 / −3 | +91 / −3 |
| `_calisma/CIKTI/test_coordinator_loop.py` | +9 / −0 | +9 / −0 |
| `_calisma/CIKTI/test_preview_server.py` | +30 / −1 | +30 / −1 |
| `_calisma/CIKTI/test_z3_slide_gallery.py` | +1 / −1 | +1 / −1 |

Yalnızca **birincide** görünen üç dosya: `findings.md` (+152 / −0),
`progress.md` (+62 / −0), `task_plan.md` (+51 / −32).

Kesişim **tam** değil: ikinci yama birincisinden farklı bir `.gitignore`
satırı ekliyor (`index 07b221d..994269e` vs `index 07b221d..294ed14`), yani
ikisi aynı anda değil **ayrı ayrı** üretildi ve birbirinin yerine geçmez.
Birincisi `findings.md`/`progress.md`/`task_plan.md` kaydını da taşıyor
(birinci 10 dosya, ikinci 7 dosya — fark tam bu üçü); ikincisi yalnız
kod tarafını. İkisi birlikte okunmadan hikâye eksik kalır.

## Neden silinmiyorlar

Bunlar **geri-alma kanıtı (revert evidence)**. Bir şeyi geri almak için
önce neyin ne zaman değiştiğini bilmek gerekir; yamalar o anın tam
anlık görüntüsüdür ve commit geçmişi onları yeniden üretemez.

Ayrıca `check-precommit-orphans` kapısı bu dosyaları "bayat yama" olarak
işaretler. Kapının uyarısı **kasıtlı olarak** yok sayılmıyor, yalnızca
açıklanıyor: silmek kanıtı yok eder, kapıyı geçirmek kanıtı düzeltmez.

## Nasıl doğrulanır

Yamalar `git apply --check` ile **uygulanamaz** olmalıdır — zaten işlenmiş
değişikliklerdir. Uygulanabilir hâle gelirlerse, demek ki ilgili değişiklik
düşmüş ya da geri alınmış; o zaman inceleme gerekir.

```bash
git apply --check _calisma/CIKTI/recovery_patches_20260918/patch1789754982-84993
git apply --check _calisma/CIKTI/recovery_patches_20260918/patch1789755439-10960
```

Bir yamayı içeriğini görmek için `git apply --stat` güvenlidir (hiçbir şey
değiştirmez):

```bash
git apply --stat _calisma/CIKTI/recovery_patches_20260918/patch1789754982-84993
```

## Bu dizine yeni yama eklerken

1. Dosya adını `<epoch>-<pid>` bırak — üretim sırası tek kayıt.
2. Aynı değişikliğin ikinci bir yamasını üretme; yama **anlık görüntüdür**,
   canlı kayıt değil.
3. Neden üretildiğini bu README'ye bir satır ekle.
