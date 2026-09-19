# Lokal Doğrulama Rehberi

> **Diátaxis: How-to guide** — Problem-yönelimli. Amacı: CI'da kırmızı almadan
> *önce*, deponun kendi kapılarını lokalde aynı parametrelerle koşmak.
> Öğretici değil (yeni-gelen için bkz. README "Doğrulama" bölümü), referans da
> değil (kapı satır-içi sözlüğü için bkz. `docs/HOOK_ENV_MATRIX.md`).

## 0. Ön koşullar

- Repo kökünde olun: `cd $(git rev-parse --show-toplevel)`. Bu rehberdeki
  tüm göreli yollar köke göre yazılmıştır.
- Python 3.9+ (sistem python3 yeterli — kapılar stdlib-only tasarlanmıştır).
- `pre-commit` kurulu (`pip install pre-commit`); git hook'ları bağlanmış
  (`pre-commit install` — fresh-clone kurulumunun 3. adımı).
- Z3 yalnızca sembolik ispat kapısı için gerekir: `pip install z3-solver`
  (K9/K10 dışındaki kapılar Z3'süz koşar).

## 1. En hızlı döngü — tek komut

Commit'ten önce tek kapıyı koşmak için:

```bash
python3 _calisma/CIKTI/verify_delivery.py
```

Çıktının son satırı kapı dilidir: `verdict: PASS` ya da `verdict: FAIL` +
bulgular. Bu, CI'daki K1–K14 zincirinin lokal koşumudur (env bağımsız,
stdlib-only). Bütçe/referans gibi ağ gerektiren modüller parametreyle
açılır (`--budget 30`, `--refs-out …`); varsayılan koşum offline'dır.

## 2. Tam zincir — pre-commit'i commit'e kadar koşmak

Depodaki `.pre-commit-config.yaml` 40+ kapıyı sıralar (verify-delivery,
action-pins, actionlint, sync, mirror-coverage, plist-drift, repro-manifest…).
Lokalde birebir aynı zincir yalnızca gerçek bir commit anında koşar:

```bash
git add -A && git commit -m "test: lokal zincir koşumu"
```

Zincir kırmızıysa commit düşmez; hook çıktısındaki `hook id:` satırı hangi
kapının kırıldığını söyler. Düzeltip aynı komutu tekrarlayın.
(Not: bazı kapılar dosyaları otomatik düzenler — "Files were modified by this
hook" uyarısı alırsanız dosyaları tekrar `git add` edip commit'i yineleyin.)

## 3. CI'ı lokal simüle etmek

CI'da koşan işin aynısını lokalde üretmek için iki araç vardır:

```bash
# unit testler (CI'daki unittest discover ile aynı keşif)
python3 -m unittest discover -s _calisma/CIKTI -p "test_*.py"

# workflow sözdizimi + action pinleri + runtime gate
bash _calisma/CIKTI/lint_actionlint.sh
python3 _calisma/CIKTI/check_action_pins.py
python3 _calisma/CIKTI/check_action_runtimes.py
```

Ağaç senkronizasyonu (test listesi ↔ HOOK_COVERAGE tutarlılığı):

```bash
python3 _calisma/CIKTI/sync_check_unit_tests.py --check   # rc=0 gerekli
# bozuksa: --update ile liste yenilenir, sonra farkı gözden geçirin
```

## 4. Yaygın arızalar

| Belirti | Kök neden | Çözüm |
|---|---|---|
| `check-unit-tests: N/M test dosyası BAŞARISIZ` | Unstaged kaynak, hook'un stash'lediği ağaçta eski sürümle koşuldu | İlgili kaynak dosyayı stage edin (`git add`) ve commit'i tekrarlayın |
| `commit-msg: HATA — başlık N karakter (sınır: 72)` | Başlık 72 karakteri aştı | Konuyu kısaltın; kural `.gitmessage` içinde |
| `Changelog sync` dosyayı değiştirdi, commit düştü | Hook README changelog tablosunu otomatik güncelledi | `git add README.md` + commit'i yineleyin (repo deseni) |
| `sync --check` rc=1: "YENİ keşfedilen test dosyası" | Yeni `test_*.py` listeye alınmamış | `sync_check_unit_tests.py --update` |
| `verify-delivery` FAIL: K-bağımsız bulgu | ZIP/PDF/manifest gerçek veri sorunu | `verdict` satırındaki K-koduyla ilgili bölümü `docs/FINAL_RC_REPORT.md`'de arayın |
| actionlint FAIL: workflow sözdizimi | `.github/workflows/*.yml` düzenlendi | `bash _calisma/CIKTI/lint_actionlint.sh` çıktısındaki satırı düzeltin |

## 5. Kapı tablosu (başvuru)

Her kapının satır-içi açıklaması, gerekli araç sürümü ve env matrisi:
`docs/HOOK_ENV_MATRIX.md`. CI koşumlarının kök-neden triyajı için:
`docs/CI_GATE_TRIAGE.md`. Bu rehberdeki komutların CI karşılıkları
`.github/workflows/verify.yml` içinde ada göre eşleşir.
