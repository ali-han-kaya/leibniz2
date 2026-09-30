# A11y-Gate Implementation Plan (2026-09-24 — kalan kapsam, bugünkü gerçekle doğrulandı)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> (Bu ortamda subagent yok — inline execution.)

**Goal:** Onaylı a11y-gate spec'inin (09-17) henüz uygulanmamış üç kalemini
kapat: (1) `a11y_report.json`'a makine-okunur `verdict` alanı (spec §Summary),
(2) job-summary yüzeyi (spec §Reporting-3), (3) yerel tarayıcı-E2E kanıtı
(spec §Testing); final doğrulaması ve tek konu-commit.

**Architecture:** `a11y_report.json` bugün `verdict` taşımıyor — alan
`a11y_gate.py` `main()` init'ine fail-closed default `FAIL` ile eklenir,
başarılı taramada hesaplanan değerle ezilir. verify.yml'deki `a11y-gate` job'ına
(verify.yml:2970) "Run a11y gate" ile "Upload a11y report" arasına `if: always()`
bir `GITHUB_STEP_SUMMARY` adımı bağlanır; adım raporu salt-okur render eder
(verdict + summary sayacı + violation satırları + error). E2E, venv'de kurulu
playwright ve ms-playwright cache'iyle gerçek preview_server'a karşı koşulur.

**Tech Stack:** Python 3.9+ unittest (repo konvansiyonu), Playwright
(venv'de 1.60.0 kurulu; CI pin'i 1.63.0 — yerel E2E için venv sürümü kullanılır,
pin değişmez), axe-core 4.10.3 (vendored, sha256-pinned), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-17-a11y-gate-design.md` (Status: Approved)

## Global Constraints

- Yeni üçüncü-parti import → `try/except ImportError` + `skipUnless` deseni
  (PyYAML loader-ERROR kazasının tekrarı yasak). Bu planda yeni import yok.
- Fail-closed: rapor-verdict default'u `FAIL`; summary adımı `if: always()`.
- Exit-kod sözleşmesi sabit: 0 PASS · 1 FAIL · 2 usage/environment. `warn`
  hiçbir zaman exit kodu değiştirmez.
- Prettier/başlık kuralları: commit konusu ≤72 karakter, `<scope>: <action>`.
- Kayıt-borcu: süit uzarsa `sync_check_unit_tests.py --check` (rc=0 kalmalı;
  test_a11y_gate zaten kayıtlı — dosya-uzunluğu değişimi kayıt gerektirmez).
- Changelog/README satırları hook-otomatiğiyle düşer (elle README düzenlenmez).

## Mevcut-gerçek (uyum-denetimi 2026-09-24, ölçülmüş — 09-23 planının günceli)

- T1–T6 (09-17 planı) uygulanmış: vendor+sha256 (axe.min.js 553KB), config-json,
  `a11y_gate.py` (checksum kapısı, config-validation, exit 0/1/2,
  lazy-playwright), `test_a11y_gate.py` **28 test**, manifest-kayıt, verify.yml
  job (pinned install + cache + setsid health-poll + artifact-upload).
- **report-verdict hâlâ YOK** (grep-kanıt: `a11y_gate.py`'de `"verdict"` yok;
  init satır 229: `report = {"base_url": ..., "page_url": None, "config": None,
  "violations": [], "summary": {}, "error": None}`; verdict yalnız `print()`.
  Başarı-yolunda `fail(0 if verdict == "PASS" else 1)` — yani rapor yazımı
  `fail()` içinde tek noktada; `verdict` değişkeni satır ~273'te hesaplanıyor).
- a11y job'ında `GITHUB_STEP_SUMMARY` adımı yok (grep-kanıt: job bloğu
  verify.yml:2970–3030; en yakın summary adımları diğer job'larda).
- **GÜNCEL (09-23'ten farklı):** venv'de playwright **var — 1.60.0**
  (`_calisma/.venv_z3/bin/python3 -c "import playwright"` OK);
  `~/Library/Caches/ms-playwright`'ta chromium-1208/1223/1234/1243 cache'i mevcut
  (Task 4 artık kurulum-değil, doğrudan koşum).
- Süit gerçeği: `test_a11y_gate.py` takma-ad yok (`import a11y_gate`), satır 15
  `import contextlib` zaten var, `run_gate(argv, connect=None)` yardımcısı
  mock.patch ile `collect`'i değiştirir ve `(rc, stdout, report)` döner;
  `unittest.main()` öncesi son satır 375. Geçersiz-config yolu
  (`load_config` → ValueError → FAIL) tarayıcısız rapor-yazan tek gerçek akış.

## Tasks

### Task 1: Rapor-verdict sözleşmesi (KIRMIZI → YEŞİL)

**Files:**
- Modify: `_calisma/CIKTI/test_a11y_gate.py` (yeni test-sınıfı)
- Modify: `_calisma/CIKTI/a11y_gate.py` (init satır ~229 ve başarı-yolu ~273)

**Interfaces:**
- Consumes: `a11y_gate.main(argv)` (mevcut), geçersiz-config yolu (browser'sız
  FAIL-paths'e ulaşan tek gerçek akış).
- Produces: `report["verdict"] ∈ {"PASS", "FAIL"}` — init default `"FAIL"`
  (fail-closed), başarılı-scan sonunda hesaplanan değerle ezilir.

- [x] **Step 1.1: Kırmızı testleri yaz** (`test_a11y_gate.py`, `unittest.main()`
      öncesine):

```python
class TestReportVerdictField(unittest.TestCase):
    """a11y_report.json makine-okunur verdict taşımali (spec §Summary)."""

    def test_error_path_report_carries_fail_verdict(self):
        # Geçersiz config: tarayicisiz FAIL-path'e ulasan tek gercek akis.
        with tempfile.TemporaryDirectory() as td:
            cfg = os.path.join(td, "bad.json")
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump({"blocking": ["critical", "YOK_BOYLE"]}, f)
            rc, out, report = self-run-gate-benzeri-akis(cfg)
            self.assertEqual(rc, 1)
            self.assertEqual(report["verdict"], "FAIL")
```

(Not: Yukarıdaki kod iskelettir; gerçek yazımda mevcut `run_gate` yardımcısı
kullanılır — `rc, out, report = self.run_gate([... "--config", cfg])` — ve ikinci
test kaynak-pin'i (aşağıda) eklenir. Kırmızı kanıt: `-k verdict`.)

```python
    def test_report_verdict_only_pass_or_fail(self):
        # Sozlesme-pin: rapor-verdict yalniz PASS/FAIL (default-deny).
        src = open(a11y_gate.__file__, encoding="utf-8").read()
        self.assertIn('report["verdict"] = "FAIL"', src)
        self.assertIn('report["verdict"] = verdict', src)
```

- [x] **Step 1.2: Kırmızıyı kanıtla**
Run: `_calisma/.venv_z3/bin/python3 -m unittest _calisma.CIKTI.test_a11y_gate -k verdict 2>&1 | tail -3`
Expected: 2 FAIL — `KeyError: 'verdict'` ve source-pin eşleşmezliği.

- [x] **Step 1.3: Yeşil yama** (a11y_gate.py, iki bölge):

```python
# satır ~229 — init:
report = {"verdict": "FAIL",  # fail-closed default: her arıza FAIL kalır
          "base_url": args.base_url, "page_url": None,
          "config": None, "violations": [], "summary": {}, "error": None}

# satır ~273 — hesaplanan verdict (print("verdict: %s") ÖNCESİ):
report["verdict"] = verdict
```

- [x] **Step 1.4: Yeşili kanıtla**
Run: `_calisma/.venv_z3/bin/python3 -m unittest _calisma.CIKTI.test_a11y_gate 2>&1 | tail -3`
Expected: `Ran 30 tests ... OK` (28 + 2).

- [x] **Step 1.5: Kayıt-borcu** — `sync_check_unit_tests.py --check` rc=0 (dosya
      zaten kayıtlı; yeni dosya açılmadığı için `--update` beklenmez).

### Task 2: Job-summary sözleşme-testleri (KIRMIZI)

**Files:**
- Modify: `_calisma/CIKTI/test_a11y_gate.py` (yeni test-sınıfı)

**Interfaces:**
- Consumes: `.github/workflows/verify.yml` (metin).
- Produces: `TestWorkflowSummaryStep` — adım-varlığı + always + rapor-verdict
  okuma pini.

- [x] **Step 2.1: Sınıfı yaz** (`unittest.main()` öncesine; workflow-blok
      ayıklama `a11y-gate:`'ten sonraki `  <ad>:` sınırıyla):

```python
WORKFLOW = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), ".github", "workflows", "verify.yml")


class TestWorkflowSummaryStep(unittest.TestCase):
    """Spec §Reporting-3: job özeti GITHUB_STEP_SUMMARY'ye yazılmalı."""

    def _a11y_block(self):
        text = open(WORKFLOW, encoding="utf-8").read()
        block = text.split("  a11y-gate:", 1)[1]
        return block.split("\n  changelog-drift:", 1)[0]

    def test_summary_step_exists(self):
        self.assertIn("Write a11y job summary", self._a11y_block())

    def test_summary_step_always_and_writes_step_summary(self):
        block = self._a11y_block()
        self.assertIn("if: always()", block)
        self.assertIn("GITHUB_STEP_SUMMARY", block)

    def test_summary_step_reads_report_verdict(self):
        # Task-1 sözleşmesi: özet, rapordaki verdict alanını okumali.
        self.assertIn('data.get("verdict"', self._a11y_block())
```

- [x] **Step 2.2: Kırmızıyı kanıtla**
Run: `_calisma/.venv_z3/bin/python3 -m unittest _calisma. CIKTI.test_a11y_gate -k summary 2>&1 | tail -3`
Expected: 3 FAIL (adım henüz yok).

### Task 3: Job-summary adımı (YEŞİL)

**Files:**
- Modify: `.github/workflows/verify.yml` — "Run a11y gate" ile
  "Upload a11y report" arası.

**Interfaces:**
- Consumes: `a11y_report.json` (`verdict`, `summary.*`, `violations[].{rule,
  impact, level, nodes, allowlisted_nodes?}`, `error` — Task 1 + mevcut şema).
- Produces: `$GITHUB_STEP_SUMMARY` markdown (spec §Reporting-3).

- [x] **Step 3.1: Adımı ekle** (Upload'dan hemen önce):

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
              lines.append("")
              lines.append("| seviye | sayı |")
              lines.append("|---|---|")
              for k in ("blocking", "warn", "allowlisted", "incomplete"):
                  lines.append("| %s | %s |" % (k, s.get(k, 0)))
              for v in data.get("violations", []):
                  extra = " (allowlisted: %s düğüm)" % v["allowlisted_nodes"] \
                      if v.get("allowlisted_nodes") else ""
                  lines.append("- `%s` %s → %s, %s düğüm%s" % (
                      v.get("rule", "?"), v.get("impact") or "-",
                      v.get("level"), v.get("nodes"), extra))
              if data.get("error"):
                  lines.append("- hata: %s" % data["error"])
          else:
              lines.append("a11y_report.json üretilmedi — gate adımına bak.")
          pathlib.Path(os.environ["GITHUB Step_SUMMARY"]).write_text(
              "\n".join(lines) + "\n", encoding="utf-8")
          PY
```

(Not: işaretlemenin kopyalanmasında oluşan `GITHUB Step_SUMMARY` boşluk-hatası
yazımda düzeltilir — gerçek adımda `GITHUB_STEP_SUMMARY`.)

- [x] **Step 3.2: Yeşili kanıtla**
Run: `_calisma/.venv_z3/bin/python3 -m unittest _calisma.CIKTI.test_a11y_gate 2>&1 | tail -3`
Expected: `Ran 33 tests ... OK` (30 + 3).

- [x] **Step 3.3: YAML-sağlığı** — actionlint yerelde yoksa süit-yüzeyi:
      `bash _calisma/CIKTI/check_unit_tests_hook.sh` (Task 5'te tek koşum) +
      `python3 _calisma/CIKTI/check_ci_hygiene.py` (varsa; yoksa süit yeterli).
      Ayrıca YAML-parse: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/verify.yml'))"`.

### Task 4: Yerel tarayıcı-E2E (spec §Testing — kanıt turu)

**Files:**
- Create (commit-dışı kanıt): `/tmp/a11y_e2e_report.json`
- Modify (tek kanıt-satırı): spec Status bölümü (Task 5 ile birlikte)

- [x] **Step 4.1:** Playwright hazırlığı — venv'de 1.60.0 kurulu (ölçüldü);
      cache revizyonları mevcut (chromium-1208…1243). Koşum öncesi tek kontrol:
      `_calisma/.venv_z3/bin/python3 -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop(); print('chromium OK')"` —
      başarısızsa fallback: `_calisma/.venv_z3/bin/pip install playwright==1.63.0 && _calisma/.venv_z3/bin/python3 -m playwright install chromium` (cache'e göre hızlı); o da olmazsa kanıt CI'ya devredilir (09-23 planındaki fallback) ve Task 5'e geçilir.

- [x] **Step 4.2:** Gerçek sunucu + tarama — ephemeral port (a11y job'ının
      health-poll deseni, plan-3.2 şablonu). Sunucu başlatma:

```bash
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
cp design-system/tokens.css _calisma/CIKTI/design-system-tokens.css
( setsid _calisma/.venv_z3/bin/python3 _calisma/CIKTI/preview_server.py \
    --dir _calisma/CIKTI --preview-dir _calisma/CIKTI \
    --bind 127.0.0.1 --port "$port" --interval 3600 >/tmp/a11y_e2e_server.log 2>&1 & )
echo "$port" > /tmp/a11y_e2e_port
```

  Health-poll 30×1s (`curl /api/health` → `ok`), ardından:
  `_calisma/.venv_z3/bin/python3 _calisma/CIKTI/a11y_gate.py --base-url "http://127.0.0.1:$port" --output /tmp/a11y_e2e_report.json`
  ve doğrulama: `python3 -c "import json; d=json.load(open('/tmp/a11y_e2e_report.json')); print(d['verdict'], d['summary'])"`.
  Expected: verdict alanı mevcut; FAIL ise bulgular spec-akışıyla
  (allowlist+reason) işletilir — bypass yok.

- [x] **Step 4.3:** Sunucu temizliği (setsid-PID kaydı) ve kanıt-satırı
      verileri: gerçek verdict + tarih + "local E2E".

### Task 5: Final + kapanış

- [x] **Step 5.1:** Tam-keşif: `bash _calisma/CIKTI/check_unit_tests_hook.sh`
      (yerel doğru koşucu; `unittest discover` ImportError verir) → yeni-hata
      YOK (baseline 158 test dosyası PASS).
- [ ] **Step 5.2:** pre-commit zinciri commit'te rc=0 olmalı (Task 5.3 sonrası
      staged-set ile koşar).
- [x] **Step 5.3:** Spec `**Status:**` → `Implemented (2026-09-24; report
      verdict field, job summary, local E2E evidence complete)` (+ kanıt
      satırı: gerçek verdict/tarih).
- [ ] **Step 5.4:** Tek konu-commit: `feat(a11y): report verdict field + job summary surface`
      (a11y_gate.py, test_a11y_gate.py, verify.yml, spec) — 47 karakter.
      Commit-kararı kullanıcıya sorulur.

## Self-Review

- **Spec coverage:** §Summary makine-okunur-verdict → Task 1; §Reporting-3 →
  Task 2-3; §Testing E2E → Task 4; kapanış → Task 5. T1–T6 kanıtlı (uyum
  bölümü). YAGNI maddeleri (guide.html, trend, annotation bot) dışarıda.
- **Placeholder scan:** Step 1.1 iskelet açıkça "gerçek yazımda run_gate
  kullanılır" notuyla bağlı; Step 3.1'in kopyalama-kusuru (GITHUB Step_SUMMARY)
  yazım-notuyla düzeltildi; diğer tüm kod-blok adımlar gerçek içerik.
- **Type consistency:** `verdict` / `summary.blocking` / `violations[].level` /
  `GITHUB_STEP_SUMMARY` / playwright sürümleri (venv 1.60.0 yerel-E2E; CI pin
  1.63.0 değişmez) spec + üretim-kodu + job ile birebir aynı.
- **Bugünkü-gerçek farkları (09-23 planına göre):** playwright venv'de VAR
  (1.60.0, cache 1208–1243) → Task 4 kurulum-adımı kontrol-e-dönüştü; job bloğu
  2970'de ve 60 satır okundu → Task 2/3 blok-sınırı `changelog-drift:` ile
  pinlendi; süit takma-adı yok → örnekler `a11y_gate` düz-adıyla.
