# Stoic-Hume V5 — Teslim ve Doğrulama Deposu

Bu repo, *What an Extensional First-Order Formalization Leaves
Underdetermined: Stoic Katalepsis and Humean Custom* (V5, 2026-08-17)
teslimini ve onu doğrulayan fail-closed araç zincirini içerir.

## İçerik

| Yol | İçerik |
|---|---|
| `.github/workflows/verify.yml` | GitHub Actions kapısı — her push'ta `verify` + `symbolic` job'ları; raporlar artifact olarak yüklenir |
| `_calisma/CIKTI/verify_delivery.py` | Tek komutluk doğrulama (K1–K8: sidecar → checksum → manifest → script → PDF/referans → hijyen → Z3 ispatı) + bütçe kalkanı + `--check-references` |
| `_calisma/CIKTI/symbolic_proof_z3.py` | Teoremlerin Z3 ile sembolik ispatı (12/12, P4-d/P4-e dahil) |
| `_calisma/CIKTI/*.zip` + `.sha256` | Ana taşıma birimi (`TESLIM_KLASOR…`) ve iç teslim (`TESLIM_V5_FINAL…`) |
| `_calisma/CIKTI/*.md` | Denetim raporları (M0 denetim, referans kanıt, sembolik ispat) |
| `_calisma/lean_reduct/` | reduct-invariance lemmasının Lean 4 formalizasyonu (derlenmiş, exit 0) |
| `_calisma/repack_delivery.py` · `sync_docs.py` | Zincir yeniden üretimi ve belge senkronu yardımcıları |
| `.pre-commit-config.yaml` | Commit öncesi fail-closed kapı |

## Doğrulama (tek komut)

```bash
# Bütünlük + içerik kapısı (stdlib-only)
python3 _calisma/CIKTI/verify_delivery.py --dir _calisma/CIKTI

# + Z3 sembolik ispat (z3-solver gerekir)
python3 _calisma/CIKTI/verify_delivery.py --dir _calisma/CIKTI --symbolic-proof
```

Exit kodu: `0` = PASS, `1` = FAIL (fail-closed), `2` = ortam hatası.
Çevrimiçi referans denetimi: `--check-references` (CrossRef/SEP).

## Reproducibility manifest — config artifact bölümü

`gen_repro_manifest.py` (CI `reproducibility` job'ı) artifact'ları hash'leyip
`manifest.json` + `manifest.txt` + `manifest.sha256` üretir. `config/` önekli
artifact'lar ayrıca bir **config bölümü** olarak işaretlenir; `combined_sha256`
bu dosyaların hangi sürümünün kullanıldığını tek hash ile özetler.

### manifest.json (config bölümü)

`config.files` anahtarları sıralıdır; değerler dosyaların tam SHA-256'sıdır.
Örnek (iki config dosyası: `effective_config.json` + `gen_config.json`):

```json
{
  "config": {
    "files": {
      "config/effective_config.json": "ddd95c59dea17217143690da01a992376573dc06a7dd5e998dc5347786f5cccb",
      "config/gen_config.json": "f741e59ac91662e4e738e3f7907b6dc20e5c4223c8f6aac35e7955fc5e66eada"
    },
    "combined_sha256": "ffcdf1aa8097b4442163a3609238ccbe8910e853900922cd3ea054e7053425ce"
  }
}
```

### combined_sha256 hesabı (deterministik)

Anahtarlar sıralanır, her girdi `"{rel}\0{sha256}\n"` olarak birleştirilir ve
SHA-256 alınır (formül `verify_delivery.py --verify-manifest` K10'da birebir
aynı şekilde **yeniden hesaplanarak** doğrulanır):

```python
import hashlib

config_files = {  # config.files (yukarıdaki örnek)
    "config/effective_config.json": "ddd95c59dea17217143690da01a992376573dc06a7dd5e998dc5347786f5cccb",
    "config/gen_config.json": "f741e59ac91662e4e738e3f7907b6dc20e5c4223c8f6aac35e7955fc5e66eada",
}
combined = hashlib.sha256(
    "".join(f"{rel}\0{config_files[rel]}\n" for rel in sorted(config_files)).encode()
).hexdigest()
# → ffcdf1aa8097b4442163a3609238ccbe8910e853900922cd3ea054e7053425ce
```

### manifest.txt (insan-okur bölüm)

```
========================================================================
CONFIG ARTIFACT (ayrı bölüm)
========================================================================
FILE                                                    SHA-256
------------------------------------------------------------------------
config/effective_config.json                            ddd95c59dea17217143690da01a992376573dc06a7dd5e998dc5347786f5cccb
config/gen_config.json                                  f741e59ac91662e4e738e3f7907b6dc20e5c4223c8f6aac35e7955fc5e66eada
------------------------------------------------------------------------
config_combined_sha256: ffcdf1aa8097b4442163a3609238ccbe8910e853900922cd3ea054e7053425ce
========================================================================
```

### Denetim (fail-closed)

`python3 _calisma/CIKTI/verify_delivery.py --verify-manifest reproducibility/manifest.json`
(K10) şunları denetler — uyuşmazlık P1 → exit 1:

- `files` içindeki her SHA-256 gerçek dosyayla yeniden hash'lenir.
- `config.files` girdileri `files` ile tutarlı olmalıdır.
- `config.combined_sha256`, `config.files`'tan yukarıdaki formülle yeniden
  hesaplanıp kayıtlı değerle eşleşmelidir.
- `effective_config.json`'un `cli_overrides` kaydı, aynı config bundle'ındaki
  `verify_delivery.config.json` ile tutarlı olmalıdır: `file_value` dosya
  değeriyle eşleşmeli, `override` bayrağı `cli_given and cli_value != file_value`
  olmalı ve `effective` (override varsa `cli_value`, yoksa `file_value`) ile
  uyuşmalıdır. İkisi de `combined_sha256` ile sabitlendiğinden bu denetim,
  cli_overrides'ın manifest'teki config.combined_sha256 ile tutarlılığını kanıtlar.

Teslim kaynak dizinleri (`_calisma/TESLIM/`, `_calisma/V5_ICERIK/`,
`_calisma/TOOLKIT/`) kasıtlı olarak commit edilmez — içerik zip'lerin
içindedir ve `unzip` ile yeniden üretilebilir.
