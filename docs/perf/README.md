# docs/perf/ — performans iddialarının kalıcı harness'ı

> **Amaç:** `findings.md`'deki performans cümlelerini "bir kez ölçülmüş sayı"
> olmaktan çıkarıp **tekrar koşulabilir ölçüm** hâline getirmek. Her harness
> üç parçadan oluşur: betik, ham çıktı, ve iddiayı taşıyan belgedeki repro
> satırı. Sayı makineye göre kayar; kaymayan şey betiğin kendisidir.

## `load_history` önbelleği

| Dosya                      | Ne                                                                                                                                                                                      |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `profile_load_history.py`  | Ölçüm betiği: gerçek `preview_server.Handler.do_GET` yolunu, gerçek `history.jsonl` üzerinde, önbellek-açık ve önbellek-kapalı olarak aynı süreçte koşar (`cProfile` + `perf_counter`). |
| `load_history_profile.txt` | Son koşunun ham stdout'u (tablo + tek JSON bloğu).                                                                                                                                      |

```bash
python3 docs/perf/profile_load_history.py
# farklı veriyle / daha uzun pencere:
python3 docs/perf/profile_load_history.py --history ~/yol/history.jsonl --requests 30
```

**Ne ölçülüyor**

- `do_GET` cumtime (cProfile) — `/api/history` isteğinin tamamı: rota, DNS-
  rebinding kapısı, `serve_history`, `load_history`, JSON üretimi.
- İstek başına duvar süresi (medyan / ortalama / ilk istek). İlk istek
  önbellek boşken parse maliyetini taşır.
- `json.loads` çağrı sayısı — önbellek isabetinin doğrudan kanıtı.
- **Doğruluk kalkanı:** iki modun yanıt gövdeleri birebir aynı değilse araç
  `rc=1` döner. Önbellek içeriği değiştiriyorsa ölçüm anlamsızdır.

**"Önbellek-kapalı" ne demek:** her istekten önce `preview_server._history_cache`
boşaltılır. Gerçek kod yolu korunur (parse, `HISTORY_MAX` kırpması, JSON
üretimi aynı), yalnız anahtar eşleşmesi engellenir — yani önbellek-öncesi
davranışın en kötü hâli.

**Gerçek veri zorunlu:** varsayılan kaynak preview server'ın HOME cache'indeki
`history.jsonl`'dır. Dosya yoksa araç `rc=2` ile durur ve sentetik fixture
**üretmez** — sentetik satırlarla ölçülen gecikme gerçek kaydın gecikmesi
değildir. Ham çıktı, kullanılan dosyanın boyutunu, sha256'sını ve satır
sayısını taşır ki sayı hangi veriye ait olduğu bilinmeden okunmasın.

**Sınırlar:** mutlak saniyeler makine yüküne, Python sürümüne ve dosya
boyutuna bağlıdır; koşular arasında birkaç puan oynar. İddia edilen şey
**oran** ve `json.loads` sayısıdır (0'a iner), mutlak süre değil.
