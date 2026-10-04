# K katmanı hattı — mimari

`klayers.json` sözleşmesinin kimin tanımladığı, kimin ürettiği, kimin
okuduğu. Kod okunurken görünmeyen kararlar burada.

## Sahiplik

| Sorumluluk                                              | Sahibi                                                                                                                                                      |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Katman kümesi, etiketler, çekirdek/işteğe-bağlı ayrımı  | `klayers_contract.py`                                                                                                                                       |
| "Bu run bloklanır mı" verdict'i                         | `klayers_contract.run_verdict()` → sidecar `run_status`                                                                                                     |
| Hangi katman koştu (`ran`), bulguların kovaya bölünmesi | `verify_delivery.py` (elinde `args` var)                                                                                                                    |
| Markdown bölümleri                                      | `run_summary_klayers.py`                                                                                                                                    |
| Bölüm SIRASI                                            | `consolidate_summary.py` (veri okumaz)                                                                                                                      |
| Dashboard durum panosu                                  | `preview_server.py` — K katmanları hücresi `run_status`'ı okur, kendi listesini tutmaz (Pre-commit hücresi K1-K7'yi hâlâ `layers`'dan sayar; ayrı bir soru) |

## Verdict neden veride taşınır

Tüketiciler hangi katmanı göstereceğine kendi karar verir (run summary 16
katman, dashboard başka bir alt küme) ve bu kümeler zamanla ayrışır. Ayrışma
sessiz ve kötü yöne çalışır: bir yüzey kayıt dışı `UNREGISTERED` kovasını
görmezse CI kırmızı derken o yüzey yeşil der. Verdict veride taşındığı için
hangi alt küneyi gösterdikleri önemli olmaz.

Kural: `run_verdict` elle güncellenmez — `presentation_order()` üzerinden
türetilir, yani yüzey listeleriyle birlikte evrilir.

## Yeni katman ekleme

`skills/verify-chain/gen_k_layer.py --name check_x --label "..."` iki dosyaya
yazar:

- **`klayers_contract.py`** → `LAYER_LABELS` + `OPTIONAL_LAYERS` (sözleşme)
- **`verify_delivery.py`** → docstring satırı, argparse bayrağı,
  `apply_full_flags`, `main()` çağrısı, `check_x()` iskeleti (koşum)

`--dry-run` hiçbir dosyaya dokunmaz. Anchor bulunamazsa blok atlanır ve log
satırı **hedef dosyayı sayar** (`!! labels: … (klayers_contract.py)`) —
sessiz yarım katman olmasın diye.

Elle gerekenler: `SKILL.md` haritası, `M0_TOOLKIT_DENETIM_RAPORU.md` §6.2
tablosu. `test_skill_layer_sync.py` / `test_m0_k_table_sync.py` çapraz
denetler.

## Bilinen ayrışmalar

**Yüzey listeleri bilinçli olarak ayrışır.** `preview.js`'in `K_ALL` rozet
listesi kendi kopyasını taşır; yalnızca gösterim sırası üretir, verdict'i
etkilemez. JS tüketiciler Python sözleşmesini import edemediği için
`KLAYER_KEYS`'i metin olarak taşır (`pr_status_comment.js` ile
`run_summary_status.js` birbirinden kopyalar — farklı çıktı yaşam döngüleri
olan iki script). Her biri tek yerde tanımlı; asıl risk iki okuyucu
ayrışmasıydı, kapı (`hasKlayersFail`) ve rozet döngüsü.

**Diğer bölümün `evidence` göstermemesi.** `run_summary_klayers.render()`
Other kovasında `evidence` göstermez, katman bölümleri gösterir. Ayrışma
kova bloğu ayrı yazıldığından beri var; çıktıyı değiştirmemek için
birleştirilmedi.

**PR yorumu raporlar, bloklamaz.** `pr_status_comment.js` hiçbir yerde
`core.setFailed` çağırmaz. Kayıtsız P0'yi yorumda kırmızı göstermek
raporlama davranışıdır; PR'ı _düşürmek_ ayrı bir ürün kararıdır.
