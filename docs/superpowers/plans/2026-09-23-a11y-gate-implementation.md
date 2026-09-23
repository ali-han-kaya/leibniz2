# A11y-Gate Implementation Plan (2026-09-23 — kalan-kapsam, detaylı)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> (Bu ortamda subagent yok — inline execution.)

**Goal:** Onaylı a11y-gate spec'inde açık kalan üç kalemi kapat: (0) rapora
makine-okunur `verdict` alanı (yok — yeni keşif), (1) job-summary yüzeyi,
(2) yerel tarayıcı-E2E kanıtı; final doğrulaması + tek konu-commit.

**Architecture:** `a11y_report.json` bugün `verdict`'ı taşımıyor (yalnız stdout);
önce rapor-şemasına fail-closed default'la eklenir, sonra verify.yml'deki
`a11y-gate` job'una (verify.yml:2970) `GITHUB_STEP_SUMMARY` özet-adımı bağlanır —
adım raporu salt-okur render eder. E2E, repo-venv'ine pinned playwright
kurulup var-olan chromium-cache'iyle gerçek sunucuya karşı koşulur.

**Tech Stack:** Python 3.9+ unittest (repo konvansiyonu), Playwright 1.63.0 (pin),
axe-core 4.10.3 (vendored, sha256-pinned), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-17-a11y-gate-design.md` (Status: Approved)

## Global Constraints

- Yeni üçüncü-parti import → `try/except ImportError` + `skipUnless` (PyYAML
  loader-ERROR kazasının tekrarı yasak).
- Playwright **yalnız pinned** `1.63.0`; cache anahtarı `playwright-1.63.0`.
- Fail-closed: summary-adımı `if: always()`; rapor-verdict'in default'u `FAIL`.
- Exit-kod sözleşmesi sabit: 0 PASS · 1 FAIL · 2 usage/environment.
- Changlog/README satırları hook-otomatiğiyle düşer (elle README düzenlenmez).
- Kayıt-borcu: yeni/uyarı-adı değişen süit → `sync_check_unit_tests.py --update`.

## Mevcut-gerçek (uyum-denetimi 2026-09-23, kanıtlı)

- T1–T6 (09-17 planı) **uygulanmış**: vendor+sha256 (553KB), config-json,
  `a11y_gate.py` (checksum kapısı, config-validation, exit 0/1/2,
  lazy-playwright), `test_a11y_gate.py` **28/28 OK**, manifest-kayıt,
  verify.yml job (pinned install+cache+setsid health-poll+artifact-upload).
- **YENİ KEŞİF:** `a11y_report.json` üst-seviye `verdict` YOK — `a11y_gate.py:211`
  `report = {"base_url": ..., "page_url": None, "config": None, "violations": [],
  "summary": {}, "error": None}`; verdict yalnız `print()` (satır 272).
  Rapor-şeması gerçek alanlar: `violations[].{rule, impact, level, nodes,
  reasons?, allowlisted_nodes?}`, `summary.{blocking, warn, allowlisted,
  incomplete}`, `error`.
- a11y job'unda `GITHUB_STEP_SUMMARY` adımı yok (grep-kanıt: 2970–3060 aralığı).
- venv'de playwright modülü yok; `~/Library/Caches/ms-playwright`'ta
  chromium-1208/1223/1234 cache'i var.

## Tasks

### Task 1: Rapor-verdict sözleşmesi (KIRMIZI → YEŞİL)

**Files:**
- Modify: `_calisma/CIKTI/test_a11y_gate.py` (yeni test-sınıfı)
- Modify: `_calisma/CIKTI/a11y_gate.py:211` (init) ve `:271` (atama)

**Interfaces:**
- Consumes: `a11y_gate.main(argv)` (mevcut), geçersiz-config yolu (browser'sız
  FAIL-paths'e ulaşan tek gerçek akış).
- Produces: `report["verdict"] ∈ {"PASS", "FAIL"}` — init default `"FAIL"`
  (fail-closed), başarılı-scan sonunda hesaplanan değer.

- [ ] **Step 1.1: Kırmızı testleri yaz** (`test_a11y_gate.py`, `unittest.main()`
      öncesine):

```python
class TestReportVerdictField(unittest.TestCase):
    """a11y_report.json makine-okunur verdict taşımali (spec §Summary)."""

    def _run_invalid_config(self, tmpdir):
        cfg = pathlib.Path(tmpdir) / "bad.json"
        cfg.write_text(json.dumps({"blocking": ["critical", "YOK_BOYLE"]}),
                       encoding="utf-8")
        out = pathlib.Path(tmpdir) / "report.json"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ag.main(["--base-url", "http://127.0.0.1:1",
                          "--config", str(cfg), "--output", str(out)])
        return rc, json.loads(out.read_text(encoding="utf-8"))

    def test_error_path_report_carries_fail_verdict(self):
        with tempfile.TemporaryDirectory() as td:
            rc, report = self._run_invalid_config(td)
            self.assertEqual(rc, 1)
            self.assertEqual(report["verdict"], "FAIL")

    def test_report_verdict_only_pass_or_fail(self):
        # Sözleşme-pin: geçerli alan-kümesi yalnız PASS/FAIL (default-deny).
        src = pathlib.Path(ag.__file__).read_text(encoding="utf-8")
        self.assertIn('report["verdict"] = "FAIL"', src)
        self.assertIn('report["verdict"] = verdict', src)
```

Not: import bölümü `import contextlib` gerektirir; `ag` takma-adı mevcut
süit-import deseniyle (`import a11y_gate as ag` — mevcut dosyadaki gerçek
takma-ad neyse o kullanılır, Step 1.2 öncesi kontrol).

- [ ] **Step 1.2: Kırmızıyı kanıtla**

Run: `_calisma/.venv_z3/bin/python3 -m unittest _calisma.CIKTI.test_a11y_gate -k verdict 2>&1 | tail -3`
Expected: 2 FAIL — `KeyError: 'verdict'` ve source-pin eşleşmezliği.

- [ ] **Step 1.3: Yeşil yama** (a11y_gate.py, iki bölge):

```python
# satır 211 civarı — init:
report = {"verdict": "FAIL",  # fail-closed default: her arıza FAIL kalır
          "base_url": args.base_url, "page_url": None,
          "config": None, "violations": [], "summary": {}, "error": None}

# satır 271 civarı — hesaplanan verdict (fail() öncesi):
report["verdict"] = verdict
```

- [ ] **Step 1.4: Yeşili kanıtla**

Run: `_calisma/.venv_z3/bin/python3 -m unittest _calisma.CIKTI.test_a11y_gate 2>&1 | tail -3`
Expected: `Ran 30 tests ... OK`.

- [ ] **Step 1.5: Kayıt-borcu** — süit-uzadı: `python3
      _calisma/CIKTI/sync_check_unit_tests.py --update && … --check` (rc=0).

### Task 2: Job-summary sözleşme-testleri (KIRMIZI)

**Files:**
- Modify: `_calisma/CIKTI/test_a11y_gate.py` (yeni test-sınıfı)

**Interfaces:**
- Consumes: `.github/workflows/verify.yml` (metin), Task-1'in verdict alanı.
- Produces: `TestWorkflowSummaryStep` — adım-varlığı + always + verdict-okuma pini.

- [ ] **Step 2.1: Sınıfı yaz:**

```python
WORKFLOW = CIKTI.parent.parent / ".github" / "workflows" / "verify.yml"


class TestWorkflowSummaryStep(unittest.TestCase):
    """Spec §Reporting-3: job özeti GITHUB_STEP_SUMMARY'ye yazılmalı."""

    def _workflow(self):
        return WORKFLOW.read_text(encoding="utf-8")

    def test_summary_step_exists(self):
        self.assertIn("Write a11y job summary", self._workflow())

    def test_summary_step_always_and_writes_step_summary(self):
        text = self._workflow()
        a11y = text.split("a11y-gate:", 1)[1].split("\n  a11y", 1)[0] \
            if "a11y-gate:" in text else text
        self.assertIn("if: always()", a11y)
        self.assertIn("GITHUB_STEP_SUMMARY", a11y)

    def test_summary_step_reads_report_verdict(self):
        # Task-1 sözleşmesi: özet, rapordaki verdict alanını okumalı.
        self.assertIn("data.get(\"verdict\"", self._workflow())
```

- [ ] **Step 2.2: Kırmızıyı kanıtla**

Run: `_calisma/.venv_z3/bin/python3 -m unittest _calisma.CIKTI.test_a11y_gate -k summary 2>&1 | tail -3`
Expected: 3 FAIL (adım ve heredoc henüz yok).

### Task 3: Job-summary adımı (YEŞİL)

**Files:**
- Modify: `.github/workflows/verify.yml` — "Run a11y gate" adımı ile
  "Upload a11y report" adımı arası.

**Interfaces:**
- Consumes: `a11y_report.json` (`verdict`, `summary.*`, `violations[]`,
  `error` — Task 1 + mevcut şema).
- Produces: `$GITHUB_STEP_SUMMARY` markdown (spec §Reporting-3).

- [ ] **Step 3.1: Adımı ekle** (Upload'dan hemen önce):

```yaml
      - name: Write a11y job summary
        if: always()
        shell: bash
        run: |
          python3 - <<'PY'
          import json, os, pathlib
          report = pathlib.Path("a11y_report.json")
          lines = ["## a11y-gate özeti"]
          if report.exists():
              data = json.loads(report.read_text(encoding="utf-8"))
              lines.append("verdict: **%s**" % data.get("verdict", "BILINMIYOR"))
              s = data.get("summary") or {}
              lines.append("| seviye | sayı |")
              lines.append("|---|---|")
              for k in ("blocking", "warn", "allowlisted", "incomplete"):
                  lines.append("| %s | %s |" % (k, s.get(k, 0)))
              for v in data.get("violations", []):
                  extra = " (allowlisted: %s)" % v["allowlisted_nodes"] \
                      if v.get("allowlisted_nodes") else ""
                  lines.append("- `%s` %s → %s, %s düğüm%s" % (
                      v.get("rule", "?"), v.get("impact") or "-",
                      v.get("level"), v.get("nodes"), extra))
              if data.get("error"):
                  lines.append("- hata: %s" % data["error"])
          else:
              lines.append("a11y_report.json üretilmedi — gate adımına bak.")
          pathlib.Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(
              "\n".join(lines) + "\n", encoding="utf-8")
          PY
```

- [ ] **Step 3.2: Yeşili kanıtla**

Run: `_calisma/.venv_z3/bin/python3 -m unittest _calisma.CIKTI.test_a11y_gate 2>&1 | tail -3`
Expected: `Ran 33 tests ... OK`.

- [ ] **Step 3.3: YAML-sağlığı** — actionlint yerelde yoksa süit-yüzeyi:
      `_calisma/.venv_z3/bin/python3 -m unittest _calisma.CIKTI.test_check_python3_shell _calisma.CIKTI.test_ci_hygiene_gate 2>&1 | tail -2`
      Expected: OK (workflow-yaml kapıları; a11y job timeout/permissions
      zaten mevcut — hygiene-matris bozulmaz).

### Task 4: Yerel tarayıcı-E2E (spec §Testing — kanıt turu)

**Files:**
- Create (commit-dışı kanıt): `/tmp/a11y_e2e_report.json`
- Modify (tek kanıt-satırı): spec Status bölümü

- [ ] **Step 4.1:** `_calisma/.venv_z3/bin/pip install playwright==1.63.0 &&
      _calisma/.venv_z3/bin/python3 -m playwright install chromium`
      (cache-var → hızlı; başarısızsa spec fallback'ı: kanıtı CI'ya devret,
      Task 5'e geç).

- [ ] **Step 4.2:** Gerçek sunucu + tarama (ephemeral port, plan-3.2 şablonu):
      `a11y_gate.py --base-url … --output /tmp/a11y_e2e_report.json`; ardından
      `python3 -c "import json;d=json.load(open('/tmp/a11y_e2e_report.json'));print(d['verdict'], d['summary'])"`.
      Expected: verdict alanı mevcut; FAIL ise bulgular spec-akışıyla
      (allowlist+reason) işletilir — bypass yok.

- [ ] **Step 4.3:** Spec'e kanıt-satırı: gerçek verdict + tarih + "local E2E".

### Task 5: Final + kapanış

- [ ] **Step 5.1:** Tam-keşif: `python3 -m unittest discover -s _calisma/CIKTI
      -p 'test_*.py'` → yeni-hata YOK (~212s baseline).
- [ ] **Step 5.2:** pre-commit zinciri (staged-set) rc=0.
- [ ] **Step 5.3:** Spec `**Status:**` → `Implemented (2026-09-23; report
      verdict field, job summary, local E2E evidence complete)`.
- [ ] **Step 5.4:** Tek konu-commit: `feat(a11y): report verdict field + job
      summary surface` (a11y_gate.py, test_a11y_gate.py, verify.yml, spec) —
      commit-kararı kullanıcıya sorulur.

## Self-Review

- **Spec coverage:** §Summary makine-okunur-verdict → Task 1; §Reporting-3 →
  Task 2-3; §Testing E2E → Task 4; kapanış → Task 5. T1–T6 kanıtlı (uyum
  bölümü). YAGNI maddeleri dışarıda.
- **Placeholder scan:** Tüm kod-blok adımlar gerçek içerik; tek belirsizlik
  (süitteki gerçek import takma-adı) Step 1.1-notu ile bağlı kanıt-adımına
  koyuldu; rapor-şema alanları diskten doğrulandı (satır-kanıtlarıyla).
- **Type consistency:** `verdict` / `summary.blocking` / `violations[].level`
  / `GITHUB_STEP_SUMMARY` / `playwright==1.63.0` adları spec + üretim-kodu +
  job ile birebir aynı.

## Execution Handoff

Plan güncellendi (`docs/superpowers/plans/2026-09-23-a11y-gate-implementation.md`,
detaylı sürüm — eski sürüm git-geçmişinde). Onayla: inline execution Task 1
kırmızı-testiyle başlar.
