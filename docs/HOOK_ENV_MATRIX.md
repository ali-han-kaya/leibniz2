# Hook Env Sürüm Matrisi

verify_delivery.py'nin KOŞTUĞU araç sürümlerinin tek kaynağı. `probe_tool_versions()`
(`verify_delivery.py`) bu tablodaki her aracı aynı algılama komutuyla yakalar;
sürümler `history.jsonl` `hook_env` alanına yazılır ve dashboard'da zaman
serisi olarak gösterilir. Sürüm değişikliği = çevresel drift — matrix güncellenir.

CI doğrulaması: `check_hook_env_matrix.py` (hook-env-matrix advisory job'ı)
tablo yapısını fail-closed denetler (araç kümesi, pin'ler, algılama komutları)
ve canlı prob'u run summary'ye yazar.

## Sürüm Tablosu

| Anahtar | Araç | K katmanı | Beklenen pin | Son gözlem (yerel macOS) | Son gözlem (CI ubuntu) | Algılama komutu |
|---|---|---|---|---|---|---|
| `python` | Python | tümü (stdlib-only) | ≥3.9, yalnızca stdlib | 3.9.6 | 3.12 (setup-python) | `platform.python_version()` |
| `z3` | Z3 (z3-solver) | K8 | `z3-solver` pip pin'i | 5.1.0 | — | `python -c "import z3; print(z3.get_version_string())"` |
| `lean` | Lean 4 (elan) | K9 | lake toolchain `leanprover/lean4:v4.14.0` (Content.lean) | 4.33.1 (arm64, elan) | — | `lean --version` |
| `pre_commit` | pre-commit | hook zinciri | kurulu (venv veya PATH) | 4.3.0 | — | `pre-commit --version` |
| `pdfinfo` | poppler-utils | K6 | apt `poppler-utils` (CI) | 26.08.0 | apt kurulumu | `pdfinfo -v` |
| `qpdf` | qpdf | V5l determinizm deneyi | kurulu | 12.4.0 | — | `qpdf --version` |

Notlar:
- **`lean` pin'i iki katmanlıdır:** lake build (K9-LAKE) `leanprover/lean4:v4.14.0`
  toolchain'iyle Content.lean'ı derler (fail-closed — toolchain sürümü
  `lean-toolchain` dosyasından); yerelde kurulu lean binary'si (elan 4.33.1)
  K9 ön-kapılarını (sorry/axiom taraması, aksiyom analizi) çalıştırır. İkisi
  farklı sürümler olabilir — matrix her ikisini de ayırır.
- **`z3` tek kaynak:** K8'i koşan yorumlayıcı `sys.executable`'dır (`.venv_z3`);
  sürümü bu süreçten prob edilir.
- **Eksik araç → `None`** (advisory): probe hata vermez; matrix yine de yapısal
  denetimden geçer (satır kalır, değer "yok").
- CI'da lean/qpdf/pre-commit kurulu olmadığı için "Son gözlem (CI ubuntu)"
  sütunu `—` olabilir; hook-env-matrix job'ı her run'da canlı değerleri run
  summary'ye yazar (advisory — sürüm drift'i bloke etmez, yapısal drift eder).

## Doğrulama Komutları

- Yerel prob (matrix'i doldururken):
  ```bash
  python3 - <<'EOF'
  import sys; sys.path.insert(0, "_calisma/CIKTI")
  import verify_delivery as vd
  import json; print(json.dumps(vd.probe_tool_versions(), indent=2, ensure_ascii=False))
  EOF
  ```
- Yapısal denetim (fail-closed — araç kümesi/pin/komut drift'i exit 1):
  ```bash
  python3 _calisma/CIKTI/check_hook_env_matrix.py
  ```
- CI: `hook-env-matrix` advisory job'ı (verify.yml) — her push'ta koşar,
  bulguları `hook-env-matrix` artifact'ına ve run summary'ye yazar.
