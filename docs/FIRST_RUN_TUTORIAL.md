# İlk Koşum Öğreticisi — clone → ilk verify → ilk dashboard

> **Diátaxis: Tutorial** — Öğrenme-yönelimli. Amaç: depoyu tanımayan birinin
> **10 dakikada** doğrulama zincirini lokalde çalıştırıp `PASS` görmesi ve canlı
> dashboard'u açması.
> Problem-çözme rehberi değil (o: [`LOCAL_VERIFICATION_HOWTO.md`](LOCAL_VERIFICATION_HOWTO.md)),
> referans da değil (o: [`HOOK_ENV_MATRIX.md`](HOOK_ENV_MATRIX.md)).
> Buradaki her adımın **beklenen çıktısı** yazılıdır; farklı çıktı alırsanız §8'e bakın.

Bu öğretici 2026-09-24'te macOS + Python 3.9.6 + Node 22 üzerinde uçtan uca
koşuldu; alıntılanan çıktılar o koşumdan birebir alınmıştır. Token/bütçe
sayıları ve hash'ler içeriğe/ortama bağlıdır — aynı olmalarını beklemeyin.

---

## 0. Ön koşullar

| Gereksinim | Sürüm | Doğrulama |
|---|---|---|
| git | herhangi | `git --version` |
| Python | 3.9+ (sistem `python3` yeterli) | `python3 --version` |
| Node + npm | 18+ (yalnız araç-kümesi kurulumu için) | `node --version` |

Çekirdek doğrulama zinciri **stdlib-only**'dir: ilk iki adım için pip, npm ya da
sistem paketi gerekmez. `z3-solver` yalnız sembolik ispat kapısı (K8) içindir ve
yokluğunda dürüstçe SKIP'e düşer.

## 1. Klonla

```bash
git clone git@github.com:ali-han-kaya/leibniz2.git
cd leibniz2
```

Beklenen: depo kökünde `README.md`, `_calisma/`, `docs/`, `.github/` görünür.
Bu öğreticideki tüm yollar **repo köküne göre**dir:

```bash
cd "$(git rev-parse --show-toplevel)"
```

## 2. İlk doğrulama — tek komut

Araç kurmadan, doğrulama zincirini çalıştırın:

```bash
python3 _calisma/CIKTI/verify_delivery.py --dir _calisma/CIKTI
```

Beklenen çıktı (sayılar/hash'ler değişir, satırlar değişmez):

```
[BÜTÇE] ~176550 token → $1.08 (limit $30.0, içerik 706202 B, yöntem=both)
Bütçe: ~176550 token → $1.08 (limit $30.0)
=== Stoic-Hume V5 teslim doğrulaması ===

SONUÇ: PASS  (P0=0, P1=0)
PDF: 33 sayfa | References: 64
PDF hash: raw=74b2cdbdb18fafbf… metadata-stripped=…
Config: file ← …/verify_delivery.config.json (budget_usd=30.0, method=both, pages=33, refs=64, manifest=21)
```

Exit kodu `0` = PASS, `1` = FAIL (fail-closed), `2` = ortam hatası:

```bash
echo $?   # 0 beklenir
```

**Ne oldu?** K1–K14 zinciri koştu: sidecar → checksum → manifest → script →
PDF/referans tutarlılığı → hijyen → bütçe kalkanı. Bu, CI'daki `verify` job'ının
lokaldeki aynasıdır; ağ erişimi istemez (`--check-references` gibi modüller
parametreyle açılır).

## 3. Araç-kümesini kur (venv + npm paketleri)

Sembolik ispat ve hook zinciri için pinli araç-kümesi gerekir:

```bash
bash _calisma/dev_bootstrap.sh
```

Beklenen (ilk koşumda indirir; idempotenttir, kuruluya dokunmaz):

```
venv_z3: kuruluyor (pinned: z3-solver==5.1.0.0 PyYAML==6.0.3 pre_commit==4.3.0)
_calisma/pptx: npm ci
apps/dashboard-next: npm ci
BOOTSTRAP OK
```

Doğrulaması fail-closed'dur:

```bash
bash _calisma/dev_bootstrap.sh --check
# Beklenen: CHECK OK   (rc=0)
```

Kurulanlar: `_calisma/.venv_z3` (sürüm pinli venv), `_calisma/pptx/node_modules`,
`apps/dashboard-next/node_modules`. Bir araç eksik/paritesizse `--check` rc=1
döner ve eksik olanı adıyla söyler.

## 4. İkinci koşum — sembolik ispatla

z3 `venv_z3` içinde olduğu için bu adımda **venv python'unu** kullanın:

```bash
_calisma/.venv_z3/bin/python _calisma/CIKTI/verify_delivery.py \
  --dir _calisma/CIKTI --symbolic-proof
```

Beklenen (özet):

```
SEMBOLİK İSPAT — core_section.tex (Z3, tüm yapılar üzerinden)
        Karşı-model (Z3 tanığı) — ¬T2 tanığı aranıyor...
SONUÇ: TÜMÜ PASS
[K8] sembolik ispat (Z3): PASS — Z3 ispatı geçti (12/12)
…
SONUÇ: PASS  (P0=0, P1=0)
```

Sistem `python3`'ü ile koşarsanız z3 bulunamaz ve K8 **SKIP**'e düşer — bu bir
hata değil, sözleşmenin dürüst davranışıdır; 12/12 kanıtı yalnız venv ile alınır.

## 5. İlk dashboard

Sunucuyu başlatın (varsayılan port 8000):

```bash
python3 _calisma/CIKTI/preview_server.py \
  --dir _calisma/CIKTI \
  --preview-dir _calisma/CIKTI \
  --port 8000 --bind 127.0.0.1 --interval 60
```

`--preview-dir` yazılabilir olmalı ve `preview.html`'i içermeli; fresh clone'da
`_calisma/CIKTI` ikisini de sağlar. Port doluysa sunucu ham bir Python
traceback'i ile düşer (`OSError: [Errno 48] Address already in use`) ve başka
portu kendiliğinden denemez — `--port 8123` gibi bir port seçin.

Beklenen log:

```
[main] preview_server: serving …/_calisma/CIKTI on http://127.0.0.1:8000
[main] preview_server: verify loop interval=60s, dir=…/_calisma/CIKTI
```

Sağlık ve veri yüzeyini doğrulayın:

```bash
curl -s http://127.0.0.1:8000/api/health
# → ok

curl -s http://127.0.0.1:8000/api/latest | head -c 200
# → {"ts":"…","verdict":"…","duration_s":…,"p0":…,"p1":…,…}
```

Tarayıcıda açın: **http://127.0.0.1:8000/preview.html**
Sayfa başlığı: `Stoic-Hume V5 — Live CI Dashboard`.

Sunucu açılır açılmaz **ilk verify koşumunu hemen başlatır** (`[verify_loop]
started` → `[verify_loop] running verify...`); sonraki koşumlar `--interval`
aralığıyla tekrarlanır. Ek bir koşumu hemen tetiklemek isterseniz yerelde
token'sız:

```bash
curl -X POST http://127.0.0.1:8000/api/run-now
# → {"status":"started","ts":"…",…}
```

Durdurmak için terminalde `Ctrl+C`: sunucu sıralı kapanır (verify döngüsü durur
→ thread 30 sn'ye kadar beklenir → soket kapanır).

> Not: sunucu koşarken doğrulama durumunun lokaldeki kopyalarını
> (`history.jsonl`, `runs/`) günceller. Bu, aracın normal davranışıdır; bu
> dosyalar gitignore'ludur.

## 6. Ne elde ettiniz

- Doğrulama zincirini lokalde koştunuz ve `SONUÇ: PASS (P0=0, P1=0)` gördünüz.
- Z3 sembolik ispatını 12/12 ile geçirdiniz (K8).
- Sürüm pinli araç-kümesini kurdunuz ve `--check` ile fail-closed doğruladınız.
- Canlı dashboard'u açıp `/api/health` + `/api/latest` yüzeyini gördünüz.

## 7. Sonraki adımlar (Diátaxis kadranları)

| Ne istiyorsunuz | Kadran | Belge |
|---|---|---|
| Commit öncesi kapıları koşmak, arıza çözmek | How-to | [`LOCAL_VERIFICATION_HOWTO.md`](LOCAL_VERIFICATION_HOWTO.md) |
| Kapı satır-içi sözlüğü, env matrisi, araç sürümleri | Reference | [`HOOK_ENV_MATRIX.md`](HOOK_ENV_MATRIX.md) |
| Dashboard API yüzeyinin tamamı | Reference | [`RUN_DASHBOARD.md`](RUN_DASHBOARD.md) §API reference |
| PDF üretim hattı ve determinizm sözleşmesi | Explanation | [`TEX_RENDER_PIPELINE.md`](TEX_RENDER_PIPELINE.md) |
| Kırmızı CI koşumunun kök nedeni | Explanation | [`CI_GATE_TRIAGE.md`](CI_GATE_TRIAGE.md) |

Sıradaki doğal adım: bir commit atın — 40+ hook'luk zincir lokalde koşar ve
kırmızıysa commit düşmez (ayrıntı: how-to §2).

## 8. Takıldıysanız

| Belirti | Çözüm |
|---|---|
| `verify_delivery.py` FAIL | `SONUÇ` satırının altındaki K-kodunu `docs/FINAL_RC_REPORT.md`'de arayın |
| `[K8] sembolik ispat: SKIP` | Sistem `python3` yerine `_calisma/.venv_z3/bin/python` kullanın |
| `dev_bootstrap.sh` — `BOOTSTRAP FAIL: _calisma/pptx npm ci` | Node 18+ yok; npm'i kurun ya da yalnız §2/§4 adımlarıyla ilerleyin |
| `--check` → `CHECK FAIL: venv_z3 …` | `bash _calisma/dev_bootstrap.sh` ile yeniden kurun (idempotent) |
| `address already in use` | Port dolu (başka bir thread sunucusu olabilir) — `--port` ile değiştirin |
| Dashboard açıldı ama veri yok | İlk koşum `--interval` sonra başlar; `POST /api/run-now` ile hemen tetikleyin |

Daha geniş arıza tablosu: [`LOCAL_VERIFICATION_HOWTO.md`](LOCAL_VERIFICATION_HOWTO.md) §4.
