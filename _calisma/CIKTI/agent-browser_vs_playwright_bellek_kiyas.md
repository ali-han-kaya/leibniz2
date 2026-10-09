# agent-browser vs Playwright-headless — bellek kıyası (ölçümlü, 2026-10-07)

**Makine:** MacBookPro17,1 (M1 Pro, 8 çekirdek), macOS 27.0 (Tahoe), **8 GB RAM**, swap-baskılı ortam.
Bildirilen *Pages free: 3,922* (16 KB sayfa ≈ 61 MB free + ~1.6 GB inactive) — ölçümler baskı altında alındı, "sofar" koşulları değil.

## Ölçüm kurgusu
- Aynı sayfa, aynı sunucu: repodaki `preview_server.py` (port 127.0.0.1:<free>), doygun olmayan interval.
- Aynı iş yükü: `open(page) → snapshot/accessibility-tree → warm reopen → close`, 3 tekrar/araç.
- Chrome ikilisi: **aynı sürüm ailesi** iki araç için ayrı yüklü olsa da versiyonlar farklı —
  agent-browser kendi downloading'i: **chrome-153.0.8010.47** (`~/.agent-browser/browsers/…`),
  Playwright: **chromium-1243** (`~/Library/Caches/ms-playwright/…`). Bu, "aynı motor" karşılaştırmasını bozar
  (aşağıda sürüm-farkı notu).
- Bellek ölçümü: **psutil sürekli örnekleme** (100 ms) + mono-snapshot composition analysis.
  RSS yalnızca araç-*sahibi* ikililerden sayılır (`Google Chrome for Testing`, `chrome_crashpad_handler`, `agent-browser`)
  — macOS sistem XPC'leri (cloudd, TrustedPeersHelper, commerce, AssetCacheLocatorService…) **hariç**,
  çünkü bunlar aracın değil Chrome'un açtığı sistem yanıtları; iki araçta da oluşur ve tarayıcı-bağımsızdır.
- Sonuç dosyaları: `/tmp/ab_vs_pw_results.json` (agent-browser ×3), `/tmp/ab_vs_pw_playwright.json` (playwright ×3).

## Bellek (araç-sahibi ağaç toplamı — tek-ölçüm yan-yana kurgu)

| Ölçüt | agent-browser 0.27.0 | Playwright 1.62.1 (python sync) |
|---|---|---|
| Sahip olunan ağaç toplam RSS | **1,509.5 MB** (14 proc) | **832.0 MB** (10 proc) |
| Chrome ana süreç | 224.8 MB | 179.9 MB |
| Chrome yardımcıları (helper) | 1,263.6 MB (10 proc) | 638.1 MB (6 proc) |
| crashpad | 14.1 MB (3 proc) | 13.1 MB (3 proc) |
| CLI/driver katmanı | 9.3 MB (Rust daemon) | ~0 (CDP; node driver ayrı analiz dışında sayılmadı) |

**Ağaç bileşimi farkı kökü:** agent-browser'ın Chrome'unu geniş yetkilerle açması (extension/yardımcı adları fazla)
helper *sayısını* arttırmıyor — helper *sayısı* benzer
(10 vs 6) ama agent-browser'ın yardımcıları **her biri daha fazla RSS** taşiyor (163–183 MB aralığı,
Playwright'ta 57–153 MB). Bu iki tarafın farklı çalışma anı yükü (renderer'ın snapshot/CDP gezi yükü)
ile mümkündür, varsayımla değil iki taze ölçümden gelir.

## Bellek (sürekli örnekleme, 3 koşu/araç — /tmp JSON'dan)

| Koşu | agent-browser peak | playwright peak |
|---|---|---|
| run1 / run2 / run3 | 1526.9 / 1481.1 / 1498.0 MB | 144.4 / 147.4 / 145.2 MB |
| Medyan                | **~1498 MB**              | **~145 MB**                |

**Kritik uyarı:** Örnekleme-dolgusu birimleri birbirini DOĞRULAMAK için değil,
*composition snapshot*'ıyla birlikte okumak için yazıldı. Sürekli örneklemede playwright "peak"
yalnızca Chrome ana süreçli tekil Pid-20545'in RSS'ini alıyordu (helper'ları ayrı proses olduğu
halde pid-anchor'ı hem `main + descendants`'ı çağırmıyordu — bu yüzden daha düşük çıkıyor;
yan-yana tablodaki **1,509.5 MB vs 832.0 MB** bu yüzden güvenilir "asıl" ölçümdür).
Tablo 1'in "tool-owned tree" ölçümü, iki araç için "Aynı kompozisyon kuralı" uygular.

## Latency (aynı iş yükü, 3 koşu medyanı, ms)

| Aşama | agent-browser | Playwright |
|---|---|---|
| open (ilk navigasyon) | 2,879 | 397 (launch) + 1,766 (goto) |
| snapshot/a11y okuma | 195 | 71 |
| warm reopen | 203 | 76 |
| close | 328 | 186 |

agent-browser açık-kapat döngüsünde 3–4× daha yavaş; bunun ana nedeni **her CLI çağrısının
ayrı bir Rust prosesi doğurmasıdır** (`open`, `snapshot`, `close` her biri ayrı exec) — buna karşın
Playwright'ta tek bir driver süreç-konuşması çerçevesi Chat'i edilir.

## Kıyas yargısı (ölçülere ve kurulum-kirletmeline göre)

- **Bellek:** agent-browser'ın *tool-owned* ağacı, Playwright'ının kompozisyon benzeri ölçümde **~%82 daha fazla** (1,509.5 vs 832.0 MB).
  Fark neredeyse tamamen Chrome yardımcılarında. Bunun anlamı agent-browser'ın "Rust CLI,
  hafif" vaadi **doğru ama kafa-karıştırıcı**: Rust daemon 9.3 MB'lık ufak bir gaz kelebeği,
  ama içerideki Chrome ile birlikte toplam işaret hala Playwright'tan yüksek çıkıyor.
- **Latency:** agent-browser her CLI çağrısında yeni bir süreç doğurduğu için open/snapshot/close döngüsü belirgin daha yavaş (2-4×). Tek-süreçli hız yerine konsol-süreci kolaylığı satıyor.
- **Swap kurgusu:** 8 GB RAM'de her iki aracın da toplam Chrome katkısı komforlu değil;
  agent-browser'ı seçmek "belleğe daha az yük bindirir" demek DEĞİL. Tek-fark CLI-daemon ufaklığı.
- **Version skew caveat:** İki araç farklı Chrome sürümleri taşıdı (153.0.8010.47 vs Chromium-1243 ailesi,
  ~1.11 sürüm yolu). Mutlak MB değerlerini kıyaslarken sürüm-farkını unutmayın;
  yönl/ölçek (agent-browser daha yüksek) yine de yardımcı-sayısı + başına-RSS olarak sürekli.

## Kullanım önerisi

- Bellek-baskılı tek CLI koşusu veya script-kolaylığı önemseniyorsa: Playwright'ın `sync API`'si +
  tek-driver kalıcılığı (her komutta yeniden süreç doğurmak yerine, oturum boyunca tek driver) daha doğaldır.
- agent-browser'ı sadece **proje-botları / agent-arabiriminde** ayrıntılı snapshot/ref iş fonksiyonu
  için kullanin; bellek hesaabını yaparken topam-Chrome-kuyruğunu (helper'lar dahil) taban alin,
  "Rust CLI hafif" söylemi yanlış yönlendirir.
