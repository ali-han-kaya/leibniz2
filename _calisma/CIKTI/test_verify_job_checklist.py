#!/usr/bin/env python3
"""verify.yml job-creation checklist meta-guard (fail-closed).

`docs/VERIFY_JOB_CHECKLIST.md` bir *süreç* belgesidir: bir job eklerken elle
tutulması gereken yüzeyleri ve her birini hangi kapının yakaladığını listeler.
Belge tek başına bir kapı değildir — bu test onu kapıya çevirir, böylece
checklist sessizce çürüyemez (2026-09-12'de coe denetim tablosu tam olarak
böyle çürüdü: doc'ta vardı, hiçbir yerde pin'li değildi).

Fail-closed kurallar
--------------------
1. **Yol bütünlüğü** — belgede adı geçen her repo yolu gerçekten var olmalı.
   Bir script/test yeniden adlandırılırsa belge kırmızı olur.
2. **Kapı bütünlüğü** — belgenin adını verdiği her test modülü diskte olmalı
   *ve* bir hook'a kayıtlı olmalı (manifest ya da HOOK_COVERAGE). Kaydı düşen
   bir kapı belgede "yeşil" görünürken gerçekte hiç koşmuyor olabilir.
3. **Sembol bütünlüğü** — belgenin atıf yaptığı her sınıf/metot/modül-seviyesi
   küme gerçekten tanımlı olmalı (belge "factual" kalır, süs olmaz).
4. **Ters yön (kendini bakımlayan kısım)** — `workflow_contract.py`'daki her
   modül-seviyesi karar kümesi belgede anılmalı. Yeni bir karar kümesi ekleyip
   belgeyi güncellememek **kırmızı** olur.
5. **Yüzey envanteri** — SURFACES tablosundaki her kayıt yüzeyi hem belgede
   anılmalı hem de iddia ettiği dosyada gerçekten var olmalı.
6. **§2 başlıkları sabit** — bölüm silinemez/yeniden adlandırılamaz.

stdlib-only (PyYAML gerekmez): dosyalar metin olarak okunur, YAML parse
edilmez. Bu bilinçli — kapı, venv'siz sistem python3'ünde de koşabilmelidir.
"""

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CIKTI = REPO_ROOT / "_calisma" / "CIKTI"
DOC_REL = "docs/VERIFY_JOB_CHECKLIST.md"
DOC = REPO_ROOT / DOC_REL


# ═══════════════════════════════════════════════════════════════════════════
# YÜZEY ENVANTERİ: bir job kaydının dokunduğu her yer.
#   (etiket, anchor yolu, (tür, sembol), [belgede geçmesi gereken token])
#   tür: "assign" = modül-seviyesi atama, "symbol" = class/def,
#        "text"   = serbest metin (doc çapası), "file" = yalnız var olmalı
# ═══════════════════════════════════════════════════════════════════════════
SURFACES = [
    ("job gövdesi",
     ".github/workflows/verify.yml", ("text", "jobs:"),
     [".github/workflows/verify.yml"]),
    ("job timeout",
     ".github/workflows/verify.yml", ("text", "timeout-minutes"),
     ["timeout-minutes"]),
    ("action pin kaydı",
     "_calisma/CIKTI/action_pins.json", ("text", "actions"),
     ["action_pins.json"]),
    ("artifact → job haritası",
     "_calisma/CIKTI/gen_repro_manifest.py", ("assign", "ARTIFACT_JOBS"),
     ["ARTIFACT_JOBS"]),
    ("required/advisory kararı",
     "_calisma/CIKTI/workflow_contract.py", ("assign", "GATE_EXCLUDE"),
     ["GATE_EXCLUDE"]),
    ("merge-pattern istisnaları",
     "_calisma/CIKTI/workflow_contract.py", ("assign", "MERGE_PATTERN_EXCLUDED"),
     ["MERGE_PATTERN_EXCLUDED"]),
    ("doc-only advisory",
     "_calisma/CIKTI/workflow_contract.py", ("assign", "DOC_ONLY_ADVISORY"),
     ["DOC_ONLY_ADVISORY"]),
    ("upload istisnaları",
     "_calisma/CIKTI/workflow_contract.py", ("assign", "UPLOAD_EXCEPTIONS"),
     ["UPLOAD_EXCEPTIONS"]),
    ("doc artifact listesi",
     "docs/PUBLISH_SCENARIO.md", ("text", "Artifact listesi"),
     ["Artifact listesi"]),
    ("doc job tablosu",
     "docs/PUBLISH_SCENARIO.md", ("text", "Job kategorileri"),
     ["Job kategorileri"]),
    ("required set pin'i",
     "_calisma/CIKTI/test_status_checks.py", ("symbol", "TestGateJobs"),
     ["test_status_checks.py"]),
    ("birim test manifesti",
     "_calisma/CIKTI/check_unit_tests.list", ("file", None),
     ["check_unit_tests.list"]),
    ("manifest senkronu",
     "_calisma/CIKTI/sync_check_unit_tests.py", ("text", "--update"),
     ["sync_check_unit_tests.py"]),
    ("hook kapsam haritası",
     "_calisma/CIKTI/test_coverage_report.py", ("assign", "HOOK_COVERAGE"),
     ["HOOK_COVERAGE"]),
    ("birim test hook sarmalayıcısı",
     "_calisma/CIKTI/check_unit_tests_hook.sh", ("file", None),
     ["check_unit_tests_hook.sh"]),
    ("sidecar wiring sözleşmesi",
     "_calisma/CIKTI/test_ci_sidecar_wiring.py", ("assign", "DELIVERIES"),
     ["test_ci_sidecar_wiring.py"]),
    ("logs sidecar sözleşmesi",
     "_calisma/CIKTI/test_advisory_coe_surfacing.py",
     ("assign", "LOGS_SIDECAR_UPLOADS"),
     ["LOGS_SIDECAR_UPLOADS"]),
]

# Belgenin adını verdiği kapı test modülleri. İkisi de doğrulanır:
# (a) belgede anılıyor, (b) diskte var VE bir hook'a kayıtlı.
GATE_TESTS = [
    "test_workflow_timeouts.py",
    "test_workflow_install_hardening.py",
    "test_actionlint_gate.py",
    "test_doc_job_sync.py",
    "test_doc_artifact_sync.py",
    "test_status_checks.py",
    "test_gen_repro_manifest.py",
    "test_ci_sidecar_wiring.py",
    "test_advisory_coe_surfacing.py",
    "test_audit_live_ci_sync.py",
    "test_workflow_contract.py",
    "test_gate_coverage_sync.py",
    "test_test_coverage_report.py",
    "test_verify_job_checklist.py",
]

# (modül, sembol) — belgenin atıf yaptığı sınıf/metot gerçekten var olmalı.
GATE_SYMBOLS = [
    ("test_status_checks.py", "TestGateJobs"),
    ("test_status_checks.py", "test_gate_jobs_exact_set_includes_label_gate"),
    ("test_status_checks.py", "test_count_matches_workflow_minus_excludes"),
    ("test_workflow_timeouts.py", "test_every_named_job_has_timeout"),
    ("test_workflow_install_hardening.py", "test_verify_k_gate_installs_carry_if_always"),
    ("test_ci_sidecar_wiring.py", "DELIVERIES"),
    ("test_ci_sidecar_wiring.py", "test_deliveries_precede_evaluation"),
    ("test_ci_sidecar_wiring.py", "TestRequiredGateVerdictBinding"),
    ("test_advisory_coe_surfacing.py", "TestUploadAlwaysInCoeJobs"),
    ("test_advisory_coe_surfacing.py", "test_every_upload_in_coe_jobs_is_always"),
    ("test_advisory_coe_surfacing.py", "TestLogsSidecarSurfacing"),
    ("test_advisory_coe_surfacing.py", "test_every_workflow_sidecar_is_declared"),
    ("test_gen_repro_manifest.py", "TestWorkflowPatternCoverage"),
    ("test_audit_live_ci_sync.py", "TestE2EArtifactDocSync"),
]

# §2 bölüm başlıkları — silinemez/yeniden adlandırılamaz.
REQUIRED_SECTIONS = [
    "### 2.1 Job'un kendisi",
    "### 2.2 Üretilen artifact",
    "### 2.3 Job'un dokümanı",
    "### 2.4 Required seti",
    "### 2.5 Sidecar tüketen kapı",
    "### 2.6 `logs/*.json` sidecar'ı",
    "### 2.7 Advisory job",
    "### 2.8 Sıra / bağımlılık uyarısı",
    "### 2.9 Yeni test dosyası / hook kapsamı",
]

# Belgenin pin'lediği §3 komut seti bu testi içermeli (aksi halde belge
# kendi kapısını anmaz ve okuyucu onu koşmaz).
SELF_REFERENCE = "test_verify_job_checklist"

_PATH_EXT = (".py", ".sh", ".json", ".list", ".md", ".yml", ".yaml",
             ".jsonl", ".js", ".css", ".png")

# Repo içi kök dizinler: bunlarla başlayan bir token yol sayılır.
_REPO_PREFIXES = ("_calisma/", "docs/", ".github/", "skills/",
                  "design-system/", "scripts/", "config/")

# Temiz checkout'ta BULUNMAYAN yollar: bunlar doğrulanamaz (venv, build cache).
_SKIP_PATH_PARTS = (".venv", "node_modules", ".lake", ".build",
                    "__pycache__")


def read(path):
    return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")


def symbol_defined(text, kind, symbol):
    """`symbol` anchor dosyasında tanımlı mı? Giriş satırı olabilir (indent serbest)."""
    if kind == "file":
        return True
    if kind == "assign":
        return re.search(rf"^{re.escape(symbol)}\s*[:=]", text, re.M) is not None
    if kind == "symbol":
        return re.search(rf"^\s*(class|def)\s+{re.escape(symbol)}\b", text, re.M) is not None
    if kind == "text":
        return symbol in text
    raise AssertionError(f"bilinmeyen tür: {kind}")


def doc_backticked_tokens(doc_text):
    """Belgedeki `...` token'ları (satır bazlı; çok satırlı blok yok)."""
    return re.findall(r"`([^`\n]+)`", doc_text)


def path_like(token):
    """Token gerçek bir repo yolu mu (glob/şablon/mutlak yol/seçenek değil)?"""
    if not token or " " in token or "\t" in token:
        return False
    if any(s in token for s in _SKIP_PATH_PARTS):
        return False
    if token.startswith("/") or token.startswith("-"):
        return False
    if "*" in token or token.count("``"):
        return False
    if token.startswith("http://") or token.startswith("https://"):
        return False
    if "/" in token:
        # `actions/download-artifact` gibi action adları yol değildir:
        # ya bilinen bir uzantı ya da repo kök dizini öneki gerekir.
        return token.endswith(_PATH_EXT) or token.startswith(_REPO_PREFIXES)
    return token.endswith(_PATH_EXT)


def fenced_tokens(text):
    """``` fensleri içindeki shell token'ları.

    Belgenin en operasyonel kısmı burada yaşar (§3 komut seti), ve o satırlar
    backtick'sizdir — yalnız backtick taramak bu yolları doğrulamaz. Bir yol
    yeniden adlandırıldığında belge bayat kalırdı.
    """
    out = []
    for block in re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S):
        for raw in block.split():
            tok = raw.strip("\\;\"'`|&()")
            if not tok or "=" in tok:
                # `VAR=değer` biçimini değere indir (ör. PY=_calisma/.venv_z3/...)
                if "=" in tok and not tok.startswith("=") and tok.count("=") == 1:
                    tok = tok.split("=", 1)[1].strip("\\;\"'`|&()")
                else:
                    continue
            out.append(tok)
    return out


def token_in_doc(body, token):
    """Belge `token`'ı anıyor mu?

    `.py` token'ları için stem de kabul edilir: belge çoğu yerde modül adını
    uzantısız yazar (`test_doc_job_sync`), §3 komut bloğunda ise
    `_calisma.CIKTI.test_doc_job_sync` biçimini kullanır. Rename/deletion
    tespiti bu fonksiyona değil, GATE_TESTS ↔ disk karşılaştırmasına dayanır;
    burada amaç yalnızca "belge bu kapıyı hâlâ anıyor mu".
    """
    if token in body:
        return True
    if token.endswith(".py"):
        stem = token[:-3]
        # `.` ile önü açık: §3'teki `_calisma.CIKTI.test_doc_job_sync` biçimi
        # de bir anma sayılır. Kelime karakteriyle bitişik olmak saymaz
        # (`test_doc_job_sync_golden` eşleşmez).
        return re.search(rf"(?<!\w){re.escape(stem)}(?!\w)", body) is not None
    return False


def repo_path_index():
    """Her repo-relative yolu (ve basename'leri) bir kez indeksle."""
    rels = set()
    base = {}
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file():
            continue
        s = str(p)
        if "/.git/" in s or "/node_modules/" in s or "/.lake/" in s:
            continue
        if "/.venv" in s or "/__pycache__/" in s:
            continue
        r = p.relative_to(REPO_ROOT).as_posix()
        rels.add(r)
        base.setdefault(p.name, []).append(r)
    return rels, base


_RELS, _BASE = repo_path_index()


class TestDocExists(unittest.TestCase):
    def test_checklist_doc_present_and_non_trivial(self):
        self.assertTrue(DOC.is_file(), f"{DOC_REL} yok — checklist silinmiş olamaz")
        body = read(DOC)
        self.assertGreater(len(body.splitlines()), 120,
                           f"{DOC_REL} beklenenden kısa — içerik boşaltılmış olabilir")

    def test_doc_is_reachable_from_the_doc_it_pins(self):
        """Belge kendi meta-kapısını §3 komut setinde anmalı."""
        self.assertIn(SELF_REFERENCE, read(DOC),
                      "checklist §3 kendi kapısını (test_verify_job_checklist) anmıyor")


class TestSectionsStable(unittest.TestCase):
    """§2 başlıkları sabit — bölüm silinirse kırmızı."""

    def test_required_section_headings_exist(self):
        body = read(DOC)
        missing = [s for s in REQUIRED_SECTIONS if s not in body]
        self.assertEqual([], missing, f"belgede eksik bölüm başlıkları: {missing}")


class TestSurfaces(unittest.TestCase):
    """Her kayıt yüzeyi: belgede anılır VE iddia ettiği anchor'da gerçekten var."""

    def test_surfaces_are_named_in_doc(self):
        body = read(DOC)
        missing = []
        for label, _path, _check, doc_tokens in SURFACES:
            for tok in doc_tokens:
                if not token_in_doc(body, tok):
                    missing.append(f"{label} → {tok}")
        self.assertEqual([], missing,
                         f"belgede anılmayan yüzeyler: {missing}")

    def test_surfaces_exist_with_claimed_symbol(self):
        problems = []
        for label, path, (kind, symbol), _doc in SURFACES:
            f = REPO_ROOT / path
            if not f.is_file():
                problems.append(f"{label}: {path} yok")
                continue
            if not symbol_defined(read(f), kind, symbol):
                problems.append(f"{label}: {path} içinde {symbol!r} tanımlı değil")
        self.assertEqual([], problems,
                         f"yüzey iddiası gerçekle uyuşmuyor: {problems}")

    def test_surface_anchors_are_unique_paths(self):
        """Aynı yüzey iki kez farklı sembolle yazılmasın (kopya drift'i)."""
        seen = {}
        for label, path, (kind, symbol), _doc in SURFACES:
            key = (path, kind, symbol)
            self.assertNotIn(key, seen,
                             f"kopya yüzey kaydı: {label} / {seen.get(key)}")
            seen[key] = label


class TestGateFamily(unittest.TestCase):
    """Belgenin adını verdiği kapılar gerçek, kayıtlı ve diskte."""

    @staticmethod
    def _manifest_entries():
        f = CIKTI / "check_unit_tests.list"
        out = set()
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    out.add(line)
        return out

    @staticmethod
    def _hook_coverage_entries():
        t = read(CIKTI / "test_coverage_report.py")
        return set(re.findall(r'"([A-Za-z0-9_]+\.(?:py|js))"', t))

    def test_gate_tests_are_named_in_doc(self):
        body = read(DOC)
        missing = [g for g in GATE_TESTS if not token_in_doc(body, g)]
        self.assertEqual([], missing,
                         f"belgede anılmayan kapılar: {missing}")

    def test_gate_tests_exist_on_disk(self):
        missing = [g for g in GATE_TESTS if not (CIKTI / g).is_file()]
        self.assertEqual([], missing, f"diskte olmayan kapı modülleri: {missing}")

    def test_gate_tests_are_registered_with_a_hook(self):
        """Kaydı düşen kapı belgede yeşil görünüp hiç koşmayabilir."""
        listed = self._manifest_entries()
        covered = self._hook_coverage_entries()
        unregistered = [g for g in GATE_TESTS if g not in listed and g not in covered]
        self.assertEqual(
            [], unregistered,
            "hiçbir hook'a kayıtlı olmayan kapı(lar): "
            f"{unregistered} — check_unit_tests.list ya da HOOK_COVERAGE'a ekleyin")

    def test_documented_gate_symbols_exist(self):
        problems = []
        for module, symbol in GATE_SYMBOLS:
            f = CIKTI / module
            if not f.is_file():
                problems.append(f"{module} yok")
                continue
            kind = ("assign" if re.fullmatch(r"[A-Z][A-Z0-9_]*", symbol)
                    else "symbol")
            if not symbol_defined(read(f), kind, symbol):
                problems.append(f"{module}::{symbol} tanımlı değil")
        self.assertEqual([], problems,
                         f"belgede atıf yapılan sembol yok: {problems}")


class TestReverseContractSetsDocumented(unittest.TestCase):
    """Ters yön: workflow_contract.py'daki her karar kümesi belgede anılmalı.

    Bu kural kendini bakımlar — yeni bir karar kümesi eklenip belge
    güncellenmezse kırmızı olur (fail-closed'ın asıl kısmı).
    """

    def test_every_contract_set_is_documented(self):
        text = read(CIKTI / "workflow_contract.py")
        sets = re.findall(r"^([A-Z][A-Z0-9_]*)\s*[:=]", text, re.M)
        self.assertTrue(sets, "workflow_contract.py'da karar kümesi bulunamadı "
                              "(regex bozulmuş olabilir)")
        body = read(DOC)
        undocumented = [s for s in sets if s not in body]
        self.assertEqual([], undocumented,
                         "belgede anılmayan karar kümesi/kümeleri: "
                         f"{undocumented} — docs/VERIFY_JOB_CHECKLIST.md'yi güncelleyin")


class TestDocPathsResolve(unittest.TestCase):
    """Belgede adı geçen her repo yolu gerçekten var olmalı (rename → kırmızı)."""

    def test_all_named_paths_exist(self):
        body = read(DOC)
        candidates = doc_backticked_tokens(body) + fenced_tokens(body)
        dangling = []
        for tok in candidates:
            if not path_like(tok):
                continue
            if tok in _RELS:
                continue
            if tok in _BASE:          # basename ile çözülür (ör. action_pins.json)
                continue
            dangling.append(tok)
        self.assertEqual([], sorted(set(dangling)),
                         f"{DOC_REL} var olmayan yol(lar)a atıf yapıyor: "
                         f"{sorted(set(dangling))}")

    def test_fence_scan_sees_the_command_block(self):
        """§3 komut setindeki yollar gerçekten taranıyor (M3 regresyonu)."""
        toks = fenced_tokens(read(DOC))
        self.assertIn("_calisma/CIKTI/check_unit_tests_hook.sh", toks)
        self.assertIn("_calisma/CIKTI/status_checks.py", toks)
        self.assertNotIn("$PY", [t for t in toks if path_like(t)],
                         "$PY yol sayılmamalı")


class TestScannerSelfTests(unittest.TestCase):
    """Tarayıcının kendi mantığını pin'le (yanlış-yeşil imkânsız olsun)."""

    def test_path_like_accepts_paths_and_rejects_prose(self):
        for ok in ["docs/PUBLISH_SCENARIO.md", "_calisma/CIKTI/workflow_contract.py",
                   "action_pins.json", "check_unit_tests.list"]:
            self.assertTrue(path_like(ok), f"yol sayılmalıydı: {ok}")
        for bad in ["git push origin --delete test/x", "/tmp/whatever",
                    "logs/*.json", "continue-on-error: true", "--update",
                    "**Artifact listesi (N):**", "https://example.com/x.py",
                    "artifact → job", "actions/download-artifact",
                    "uses: some/action@main", "doc/artifact/job",
                    "_calisma/.venv_z3/bin/python",
                    "_calisma.CIKTI.test_doc_job_sync"]:
            self.assertFalse(path_like(bad), f"prose sayılmalıydı: {bad}")

    def test_symbol_defined_detects_all_forms(self):
        self.assertTrue(symbol_defined("HOOK_COVERAGE = {", "assign", "HOOK_COVERAGE"))
        self.assertTrue(symbol_defined("    def test_x(self):", "symbol", "test_x"))
        self.assertTrue(symbol_defined("class TestGateJobs:", "symbol", "TestGateJobs"))
        self.assertTrue(symbol_defined("Artifact listesi (12):", "text", "Artifact listesi"))
        self.assertTrue(symbol_defined("", "file", None))
        self.assertFalse(symbol_defined("HOOK_COVERAGE_X = {", "assign", "HOOK_COVERAGE"))
        self.assertFalse(symbol_defined("# def test_x", "symbol", "test_x"))
        self.assertFalse(symbol_defined("", "text", "yok"))

    def test_fenced_token_normalisation(self):
        body = "```bash\nPY=_calisma/.venv_z3/bin/python\n\"$PY\" -m unittest \\\n  x/y.py\n```"
        toks = fenced_tokens(body)
        self.assertIn("_calisma/.venv_z3/bin/python", toks)
        self.assertIn("$PY", toks)
        self.assertIn("x/y.py", toks)

    def test_reverse_rule_has_teeth(self):
        """Kuralı bir mutasyonla doğrula: kurgusal bir küme belgede yoksa yakalanır."""
        body = read(DOC)
        fake = "TOTALLY_FAKE_DECISION_SET"
        self.assertNotIn(fake, body)
        self.assertTrue(re.search(r"^([A-Z][A-Z0-9_]*)\s*[:=]",
                                  f"{fake} = frozenset()", re.M))

    def test_token_in_doc_accepts_stem_but_not_substring(self):
        body = "### 2.3 Job'un dokümanı\n**Kapı:** `test_doc_job_sync`"
        self.assertTrue(token_in_doc(body, "test_doc_job_sync.py"))
        self.assertTrue(token_in_doc(body, "test_doc_job_sync"))
        self.assertFalse(token_in_doc(body, "test_doc_job_sync_golden.py"))
        self.assertFalse(token_in_doc(body, "test_absent_module.py"))


if __name__ == "__main__":
    unittest.main()
