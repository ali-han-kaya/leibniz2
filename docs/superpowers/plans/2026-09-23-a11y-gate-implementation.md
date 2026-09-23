# A11y-Gate Implementation Plan (2026-09-23 — kalan-kapsam)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> (Subagent-driven değil — bu ortamda subagent yok; 09-17 planı ile aynı karar.)

**Goal:** Onaylı a11y-gate spec'inde hâlâ açık olan üç kalemi kapat: job-summary
yüzeyi, yerel tarayıcı-E2E kanıtı, tam-final doğrulaması.

**Architecture:** Mevcut `a11y-gate` job'una (verify.yml:2970) spec §Reporting-3'teki
job-summary adımı eklenir; `a11y_report.json` zaten tüm veriyi taşıdığı için özet
adımı salt-okur render'dır. E2E, repo-venv'ine **pinned** playwright kurulup
var-olan chromium-cache'iyle gerçek sunucuya karşı koşulur.

**Tech Stack:** Python 3.9+ unittest (repo konvansiyonu), Playwright 1.63.0 (pin),
axe-core 4.10.3 (vendored, sha256-pinned), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-17-a11y-gate-design.md` (Status: Approved;
bu plan spec'in "awaiting implementation" hedefini tamamlar)

## Global Constraints

- PyYAML-guard dersini tekrarlama: test-süitlerine eklenecek her yeni üçüncü-parti
  import `try/except ImportError` + `skipUnless` ile gelir (K-11c loader-ERROR kazası).
- Playwright **yalnız pinned** `1.63.0` (spec: no floating pins); cache anahtarı
  `playwright-1.63.0` ile uyumlu kalır.
- Fail-closed: summary-adımı `if: always()` — FAIL'te de özet yazılmalı.
- Yeni workflow-yaml testleri `actionlint`-temiz YAML üretir; repo-konvansiyon
  changelog-satırı hook-otomatiğiyle düşer (elle README düzenlenmez).
- Exit-kod sözleşmesi sabit: 0 PASS, 1 FAIL, 2 usage/environment (dokunulmaz).

## Mevcut-gerçek (uyum-denetimi 2026-09-23, kanıtlı)

- T1–T6 (09-17 planı) **uygulanmış**: `vendor/axe.min.js`+sha256 (553KB), config-json,
  `a11y_gate.py` (checksum kapısı, config-validation, exit 0/1/2, lazy-playwright),
  `test_a11y_gate.py` **28/28 OK** (unknown-impact default-deny + reason-enforcement
  dahil), manifest-kayıt, verify.yml job (pinned install+cache+health-poll+artifact).
- **Açık 1:** job'da `GITHUB_STEP_SUMMARY` adımı yok (spec §Reporting-3 boş).
- **Açık 2:** yerel tarayıcı-E2E kanıtı yok (venv'de playwright modülü eksik;
  `~/Library/Caches/ms-playwright` chromium-1208/1223/1234 cache'i mevcut).
- **Açık 3:** final tam-süit + actionlint + spec-Status güncellemesi yapılmadı.

## Tasks

### Task 1: Job-summary sözleşme-testleri (KIRMIZI)

**Files:**
- Modify: `_calisma/CIKTI/test_a11y_gate.py` (yeni test-sınıfı, dosya-sonu)

**Interfaces:**
- Consumes: `.github/workflows/verify.yml` (metin), mevcut süit-import deseni.
- Produces: `TestWorkflowSummaryStep` — job-summary adımını pinler.

- [ ] **Step 1.1: Sınıfı yaz** (dosya-sonuna, `unittest.main()` öncesi):

```python
WORKFLOW = CIKTI.parent.parent / ".github" / "workflows" / "verify.yml"


class TestWorkflowSummaryStep(unittest.TestCase):
    """Spec §Reporting-3: job özeti GITHUB_STEP_SUMMARY'ye yazılmalı (always)."""

    def _workflow(self):
        return WORKFLOW.read_text(encoding="utf-8")

    def test_gate_step_writes_report(self):
        self.assertIn("--output a11y_report.json", self._workflow())

    def test_summary_step_exists(self):
        text = self._workflow()
        self.assertIn("Write a11y job summary", text)

    def test_summary_step_writes_step_summary_and_always(self):
        text = self._workflow()
        self.assertIn("GITHUB_STEP_SUMMARY", text)
        # FAIL'te de özet: adım always()
        self.assertIn("if: always()", text)
```

- [ ] **Step 1.2: Kırmızıyı kanıtla**

Run: `python3 -m unittest _calisma.CIKTI.test_a11y_gate -k summary 2>&1 | tail -3`
Expected: 2 FAIL (`summary_step_exists`, `..._writes_step_summary_and_always`) —
`test_gate_step_writes_report` yeşil (adım zaten var).

### Task 2: Job-summary adımı (YEŞİL)

**Files:**
- Modify: `.github/workflows/verify.yml` (a11y-gate job, "Run a11y gate" adımı
  ile "Upload a11y report" arası)

**Interfaces:**
- Consumes: `a11y_report.json` (gate zaten yazar; `verdict` + `violations` alanları).
- Produces: `$GITHUB_STEP_SUMMARY` markdown özeti (spec §Reporting-3).

- [ ] **Step 2.1: Adımı ekle** ("Upload a11y report" adımının hemen üstüne):

```yaml
      - name: Write a11y job summary
        if: always()
        shell: bash
        run: |
          python3 - <<'PY'
          import json, pathlib
          report = pathlib.Path("a11y_report.json")
          lines = ["## a11y-gate özeti"]
          if report.exists():
              data = json.loads(report.read_text(encoding="utf-8"))
              lines.append(f"verdict: **{data.get('verdict', 'BILINMIYOR')}**")
              for v in data.get("violations", []):
                  lines.append(f"- `{v.get('rule', '?')}` "
                               f"({v.get('impact', '?')}): {v.get('nodes', '?')} düğüm")
          else:
              lines.append("a11y_report.json üretilmedi — gate adımına bak.")
          pathlib.Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(
              "\n".join(lines) + "\n", encoding="utf-8")
          PY
```

Not: `os` import'u heredoc başına `import json, os, pathlib` olarak yazılır
(yukarıdaki şablonda düzelt). `violations` alan- adları `a11y_gate.py`
rapor-şemasıyla birebir doğrulanmalı (Step 2.2).

- [ ] **Step 2.2: Şema-uyumunu doğrula**

Run: `grep -n '"violations"\|"rule"\|"impact"\|"nodes"' _calisma/CIKTI/a11y_gate.py | head -6`
Expected: rapor-şemasındaki gerçek alan-adları; uyuşmazlıkta adımı şemaya göre düzelt.

- [ ] **Step 2.3: Yeşili kanıtla**

Run: `python3 -m unittest _calisma.CIKTI.test_a11y_gate 2>&1 | tail -3`
Expected: `Ran 31 tests ... OK`.

### Task 3: Yerel tarayıcı-E2E (spec §Testing, "optional and manual" — kanıt turu)

**Files:**
- Create (kanıt-artifaktı, commit-dışı): `/tmp/a11y_e2e_report.json`
- Modify (yalnız kanıt satırı): `docs/superpowers/specs/2026-09-17-a11y-gate-design.md`

**Interfaces:**
- Consumes: gerçek `preview_server.py` (ephemeral port), pinned playwright.
- Produces: gerçek `verdict` + exit-kod eşleşmesi kanıtı; spec-Status güncellemesi.

- [ ] **Step 3.1: Pinned playwright'ı venv'e kur** (cache-var → hızlı):

```bash
_calisma/.venv_z3/bin/pip install playwright==1.63.0
_calisma/.venv_z3/bin/python3 -m playwright install chromium
```

Kurulum başarısızsa fallback: kanıtı CI-job'una devret (spec'in dokümante
fallback'ı) ve Task 4'e geç — browser-E2E engel değildir.

- [ ] **Step 3.2: Gerçek sunucu + gerçek tarama** (ephemeral port, in-process):

```bash
python3 - <<'PY'
import os, socket, subprocess, sys, time, urllib.request
HERE = os.path.abspath("_calisma/CIKTI")
s = socket.socket(); s.bind(("127.0.0.1", 0)); PORT = s.getsockname()[1]; s.close()
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "preview_server.py"),
                         "--dir", HERE, "--preview-dir", HERE, "--port", str(PORT)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    base = f"http://127.0.0.1:{PORT}"
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{base}/api/health", timeout=1); break
        except Exception:
            time.sleep(1)
    rc = subprocess.run([os.path.join(HERE, "..", ".venv_z3", "bin", "python3"),
                         os.path.join(HERE, "a11y_gate.py"),
                         "--base-url", base,
                         "--output", "/tmp/a11y_e2e_report.json"]).returncode
    print("E2E exit:", rc)
finally:
    proc.terminate()
PY
```

- [ ] **Step 3.3: Kanıtı doğrula**: `/tmp/a11y_e2e_report.json`'da `verdict`
      alanı mevcut; exit-kod = verdict (PASS→0, FAIL→1). FAIL ise: bulgular
      spec'in threshold/allowlist sözleşmesine göre değerlendirilir — gerçek
      critical/serious bulgu **borçtur, gate-borcu değil**; config-allowlist
      + reason akışı işletilir (spec-uyumlu), bypass yapılmaz.

- [ ] **Step 3.4: Spec'e kanıt-satırı** (Status bölümüne): gerçek verdict,
      tarih ve "local E2E evidence" notu tek satır.

### Task 4: Final doğrulama + kapanış

**Files:**
- Modify (Status satırı): `docs/superpowers/specs/2026-09-17-a11y-gate-design.md`

- [ ] **Step 4.1:** `python3 -m unittest discover -s _calisma/CIKTI -p 'test_*.py'`
      → yeni hata YOK (baseline: kırmızı-yok; süre ~212s).
- [ ] **Step 4.2:** pre-commit zinciri (staged-set): rc=0, tüm kapılar Passed.
- [ ] **Step 4.3:** Spec `**Status:**` satırı →
      `Implemented (2026-09-23; job-summary + local E2E evidence complete)`.
- [ ] **Step 4.4:** Değişiklik-setini (`test_a11y_gate.py`, `verify.yml`, spec)
      tek konu-commit'ine topla — commit-kararı kullanıcıya sorulur.

## Self-Review

- **Spec coverage:** §Reporting-3 → Task 1-2; §Testing E2E → Task 3; final
  doğrulama → Task 4. T1-T6 zaten kanıtlı (uyum-denetimi bölümü). YAGNI
  maddeleri (guide.html, trend, annotation, Lighthouse) plana alınmadı.
- **Placeholder scan:** kod-blok adımlar gerçek içerikli; alan-adları Step 2.2'de
  şemaya karşı doğrulanır (belirsizlik tek-nokta ve kanıt-adımıyla bağlı).
- **Type consistency:** `a11y_report.json` / `verdict` / `GITHUB_STEP_SUMMARY`
  / `playwright==1.63.0` adları spec ve mevcut-job ile birebir aynı.

## Execution Handoff

Plan `docs/superpowers/plans/2026-09-23-a11y-gate-implementation.md` kaydedildi.
Bu ortamda subagent yok — **inline execution** (superpowers:executing-plans)
önerilir; onayınızla başlarım.
