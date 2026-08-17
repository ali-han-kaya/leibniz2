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

Teslim kaynak dizinleri (`_calisma/TESLIM/`, `_calisma/V5_ICERIK/`,
`_calisma/TOOLKIT/`) kasıtlı olarak commit edilmez — içerik zip'lerin
içindedir ve `unzip` ile yeniden üretilebilir.
