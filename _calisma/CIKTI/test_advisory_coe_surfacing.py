#!/usr/bin/env python3
"""Advisory continue-on-error surfacing contracts for verify.yml.

Audit (2026-09-11) classification of the 43 step-level continue-on-error
(coe) sites: a coe step can mask a real finding two ways —

  (A) its output file is never published (no upload covers it), so the
      finding dies in the runner workspace;
  (B) a LATER upload step in the same job lacks if: always(): with the
      default `if: success()`, a failed coe step marks the job red but a
      *non-coe* intermediate failure skips the upload — and any future
      edit that flips an intermediate step to outcome-gated silently
      drops the bundle.

Contracts pinned here (fail-closed, static regex — same style as
test_workflow_install_hardening.py):

  1. reports:        'Upload reports bundle' carries if: always()
  2. reproducibility:'Upload reproducibility bundle' carries if: always()
  3. verify:         the advisory commit-msg block-evidence step writes
                     into logs/ (covered by the always() logs/ upload) —
                     not the repo root, where nothing published reaches.
  4. Generalized guard: in ANY job containing a coe step, EVERY
     upload-artifact step must carry if: always().

stdlib unittest — no PyYAML requirement.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"


def job_block(text, job_id):
    m = re.search(rf"^  {re.escape(job_id)}:\n(.*?)(?=^  [a-z0-9_-]+:|\Z)",
                  text, re.M | re.S)
    return m.group(1) if m else None


def step_blocks(job_text):
    """Split a job body into (name, body) step chunks."""
    out = []
    for m in re.finditer(
            r"^      - name: ([^\n]*)\n(?P<body>[\s\S]*?)(?=^      - |\Z)",
            job_text, re.M):
        out.append((m.group(1).strip(), m.group("body")))
    return out


# ─── logs/*.json sidecar yüzeyleme sözleşmesi (coe A sınıfının ikinci yarısı) ──
#
# Adımın ürettiği her JSON sidecar bir YÜZEYE çıkmalı: ya bir upload-artifact
# path'i onu kapsamalı (artifact), ya bir parser onu okumalı (run summary /
# gate). Hiçbiri yoksa bulgu runner workspace'inde ölür — coe A sınıfının
# sidecar seviyesindeki hâli.
#
# Ayrıca TERS yön de denetlenir: workflow'da adı geçen (okunan/yazılan) bir
# logs/*.json yolu, gerçekten ÜRETİCİSİ olan bir yer tarafından yazılmalı.
# Bu hat 2026-09-12'de gerçek bir bulgu yakaladı:
# `logs/PRECOMMIT_RAPORU.schema.json` hiçbir üretici tarafından yazılmıyordu
# (takip edilen şema `_calisma/CIKTI/PRECOMMIT_RAPORU.schema.json`), bu yüzden
# CI'daki şema adımı her run'da FileNotFoundError → "schema: FAIL" satırı
# yazıp sessizce yutuyordu.

SIDECAR_DIR = "logs/"

# sidecar → (job_id, upload path girdisi) — yükleme yolunun sidecar'ı kapsaması
# gerekir ("logs/" öneki tüm logs/*.json'ları kapsar).
LOGS_SIDECAR_UPLOADS = {
    "logs/PRECOMMIT_RAPORU.json": ("verify", "logs/"),
    "logs/commit_msg_findings.json": ("verify", "logs/"),
    "logs/k12_repro_manifest.json": ("verify", "logs/"),
    "logs/k13_repro_manifest.json": ("verify", "logs/"),
    "logs/unstaged_deps_findings.json": ("verify", "logs/"),
    "logs/latex_surface_findings.json": ("verify", "logs/"),
}

# sidecar → (job_id, job içinde kopyalanan dosya adı) — sidecar job'da başka
# adla dışa aktarılır ve o ad upload path'inde bulunur (daemon test'i
# verify_dir/logs/OVERRIDE_RAPORU.json'u override_report.json olarak taşır).
LOGS_SIDECAR_EXPORTS = {
    "logs/OVERRIDE_RAPORU.json": ("daemon-http", "override_report.json"),
}

# sidecar → üretici referansları. "script:<yol>" dosya basename'i içermeli;
# "workflow:<job_id>" job'da bu yol için gerçek bir YAZMA deyimi bulunmalı.
LOGS_SIDECAR_PRODUCERS = {
    "logs/PRECOMMIT_RAPORU.json": ["script:gen_precommit_report.py"],
    "logs/commit_msg_findings.json": ["script:check_commit_messages.py"],
    # K12/K13 sidecar'ları workflow adımındaki inline python bloğunda üretilir.
    "logs/k12_repro_manifest.json": ["workflow:verify"],
    "logs/k13_repro_manifest.json": ["workflow:verify"],
    # latex_surface_findings.json: check_latex_surface.py yolu `--out`
    # ARGÜMANI olarak alır, kaynakta sabit yol bulunmaz → doğru beyan
    # "workflow:verify" (adımın yazma ifadesi); "script:" yanlış olurdu.
    "logs/unstaged_deps_findings.json": ["script:extract_unstaged_deps.py"],
    "logs/latex_surface_findings.json": ["workflow:verify"],
    "logs/OVERRIDE_RAPORU.json": ["script:preview_server.py"],
}

# sidecar → okuyucu script'ler (boş liste = yalnız upload kapsıyor).
LOGS_SIDECAR_PARSERS = {
    "logs/PRECOMMIT_RAPORU.json": [
        "run_summary_precommit.py",
        "consolidate_summary.py",
        "github_scripts/pr_status_comment.js",
    ],
    "logs/commit_msg_findings.json": [
        "github_scripts/commit_msg_gate.js",
        "gen_precommit_report.py",
    ],
    "logs/k12_repro_manifest.json": ["run_summary_k12.py", "consolidate_summary.py"],
    "logs/k13_repro_manifest.json": ["run_summary_k13.py", "consolidate_summary.py"],
    "logs/unstaged_deps_findings.json": [],
    "logs/latex_surface_findings.json": [],
    "logs/OVERRIDE_RAPORU.json": ["daemon_http_test.py"],
}

_LOGS_JSON_RE = re.compile(r"logs/[A-Za-z0-9_.-]+\.json")


def strip_comment_lines(text):
    """YAML yorum satırlarını atar — prose referansları sözleşmeye girmez."""
    return "\n".join(l for l in text.splitlines()
                     if not l.lstrip().startswith("#"))


def logs_sidecar_literals(text):
    """Yorum dışı satırlardaki logs/*.json referansları (tekilleştirilmiş)."""
    return sorted(set(_LOGS_JSON_RE.findall(strip_comment_lines(text))))


def undeclared_sidecars(text, declared):
    """Workflow'da geçen ama sözleşmede olmayan sidecar'lar (fail-closed)."""
    return sorted(set(logs_sidecar_literals(text)) - set(declared))


def upload_paths(text, job_id):
    """Job'ın upload-artifact adımlarındaki path girdileri (çok satırlı blok dahil)."""
    job = job_block(text, job_id)
    if job is None:
        return []
    entries = []
    for _name, body in step_blocks(job):
        if "upload-artifact" not in body:
            continue
        lines = body.splitlines()
        for i, line in enumerate(lines):
            m = re.match(r"\s*path:\s*(.*)$", line)
            if not m:
                continue
            inline = m.group(1).strip()
            if inline and inline not in ("|", ">", "|-"):
                entries.append(inline)
                continue
            base = len(line) - len(line.lstrip())
            for cont in lines[i + 1:]:
                if not cont.strip():
                    continue
                if (len(cont) - len(cont.lstrip())) <= base:
                    break
                entries.append(cont.strip())
    return entries


def upload_covers(sidecar, entry):
    """path girdisi sidecar'ı kapsıyor mu (aynı yol veya dizin öneki)."""
    entry = entry.strip()
    if entry == sidecar:
        return True
    return sidecar.startswith(entry.rstrip("/") + "/")


def read_text(path):
    """Script metni: önce _calisma/CIKTI altında, sonra repo kökünde aranır."""
    for base in (ROOT / "_calisma" / "CIKTI", ROOT):
        p = base / path
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return None


def referenced_in(text, name):
    """Workflow metni `name`'i (yol ya da basename) anıyor mu."""
    return name in text


def reachable_from_workflow(text, name):
    """`name` workflow'dan ≤1 atlamada erişilebilir mi.

    Doğrudan anılıyorsa ya da workflow'un andığı bir script onu import/
    çağrı ediyorsa (ör. consolidate_summary.py → run_summary_k12.py) erişilebilir.
    Yorum satırları sayılmaz — yalnız adı anan bir yorum, parser'ı WIRE etmez.
    """
    code = strip_comment_lines(text)
    if referenced_in(code, name):
        return True
    for m in re.finditer(r"([\w./-]+\.(?:py|sh|js))", code):
        src = read_text(m.group(1))
        if src and name in src:
            return True
    return False


class TestUploadAlwaysInCoeJobs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def _upload_steps(self, job_id):
        job = job_block(self.text, job_id)
        self.assertIsNotNone(job, f"job '{job_id}' yok")
        return [(n, b) for n, b in step_blocks(job)
                if "upload-artifact" in b]

    def test_reports_bundle_upload_is_always(self):
        ups = [b for n, b in self._upload_steps("reports")]
        self.assertTrue(ups, "reports job'unda upload yok")
        for body in ups:
            self.assertRegex(body, r"if:\s*always\(\)",
                             "reports bundle upload if: always() değil — "
                             "coe adım çöktüğünde bulgular yayınlanmaz")

    def test_reproducibility_bundle_upload_is_always(self):
        ups = [b for n, b in self._upload_steps("reproducibility")]
        self.assertTrue(ups, "reproducibility job'unda upload yok")
        for body in ups:
            self.assertRegex(body, r"if:\s*always\(\)",
                             "reproducibility bundle upload if: always() "
                             "değil — download coe zinciri kırılınca "
                             "manifest yayınlanmaz")

    def test_commit_msg_evidence_writes_into_logs(self):
        job = job_block(self.text, "verify")
        evid = [(n, b) for n, b in step_blocks(job)
                if "commit-msg block evidence" in n]
        self.assertTrue(evid, "commit-msg block evidence adımı yok")
        for _name, body in evid:
            self.assertIn("logs/COMMIT_MSG_BLOCK_EVIDENCE.md", body,
                          "block-evidence repo köküne yazılıyor — hiçbir "
                          "upload kapsamında değil (maskeli bulgu); "
                          "logs/ altına yazılmalı")

    def test_every_upload_in_coe_jobs_is_always(self):
        """Generalize: coe içeren her job'da her upload if: always()."""
        text = self.text
        current = None
        job_has_coe = {}
        job_uploads = {}
        for m in re.finditer(r"^  ([a-z0-9_-]+):\n([\s\S]*?)(?=^  [a-z0-9_-]+:|\Z)", text, re.M):
            jid, body = m.group(1), m.group(2)
            steps = step_blocks(body)
            job_has_coe[jid] = any(
                re.search(r"continue-on-error:\s*true", b) for _n, b in steps)
            job_uploads[jid] = [(n, b) for n, b in steps
                                if "upload-artifact" in b]
        offenders = []
        for jid, uploads in job_uploads.items():
            if not job_has_coe.get(jid):
                continue
            for n, b in uploads:
                if not re.search(r"if:\s*always\(\)", b):
                    offenders.append(f"{jid}:{n}")
        self.assertEqual(offenders, [],
                         "coe içeren job'larda if: always()'sız upload "
                         "adımları bulgu maskeler: " + ", ".join(offenders))


class TestLogsSidecarSurfacing(unittest.TestCase):
    """Her logs/*.json sidecar'ı ya bir upload path'i ya bir parser kapsamalı."""

    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.declared = (set(LOGS_SIDECAR_UPLOADS) | set(LOGS_SIDECAR_EXPORTS)
                        | set(LOGS_SIDECAR_PRODUCERS))

    def test_every_workflow_sidecar_is_declared(self):
        """Workflow'da geçen her logs/*.json sözleşmede bulunmalı."""
        undeclared = undeclared_sidecars(self.text, self.declared)
        self.assertEqual(undeclared, [],
                         "workflow'da geçen ama sözleşmede olmayan logs/*.json "
                         "sidecar'ları (yüzeyleme yolu tanımsız): "
                         + ", ".join(undeclared))

    def test_each_sidecar_is_claimed_or_parsed(self):
        """Asıl kural: upload/export claim'i VEYA en az bir parser olmalı."""
        orphans = []
        for sidecar in sorted(self.declared):
            claimed = (sidecar in LOGS_SIDECAR_UPLOADS
                       or sidecar in LOGS_SIDECAR_EXPORTS)
            parsed = bool(LOGS_SIDECAR_PARSERS.get(sidecar))
            if not (claimed or parsed):
                orphans.append(sidecar)
        self.assertEqual(orphans, [],
                         "hiçbir upload path'i kapsamayan ve hiçbir parser'ın "
                         "okumadığı sidecar'lar (bulgu runner'da ölür): "
                         + ", ".join(orphans))

    def test_upload_claims_are_real(self):
        """Beyan edilen upload claim'i gerçekten sidecar'ı kapsamalı."""
        for sidecar, (job, entry) in sorted(LOGS_SIDECAR_UPLOADS.items()):
            entries = upload_paths(self.text, job)
            self.assertTrue(entries, f"'{job}' job'unda upload path'i yok")
            self.assertTrue(any(upload_covers(sidecar, e) for e in entries),
                            f"{sidecar}: '{job}' job'ının upload path'leri onu "
                            f"kapsamıyor (path'ler: {entries})")

    def test_export_claims_are_real(self):
        """Job içinde kopyalanan ad, o job'un upload path'inde bulunmalı."""
        for sidecar, (job, exported) in sorted(LOGS_SIDECAR_EXPORTS.items()):
            entries = upload_paths(self.text, job)
            self.assertTrue(any(upload_covers(exported, e) or e == exported
                                for e in entries),
                            f"{sidecar}: '{job}' job'ı '{exported}' olarak dışa "
                            f"aktarmıyor (path'ler: {entries})")

    def test_parsers_exist_and_reference_the_sidecar(self):
        """Parser beyanı doğrulanır: dosya var + sidecar basename'ini anıyor."""
        for sidecar, parsers in sorted(LOGS_SIDECAR_PARSERS.items()):
            for parser in parsers:
                src = read_text(parser)
                self.assertIsNotNone(src, f"parser yok: {parser}")
                self.assertIn(sidecar.split("/")[-1], src,
                              f"{parser} {sidecar} sidecar'ını okumuyor "
                              "(bayat parser beyanı)")

    def test_parsers_are_wired_from_the_workflow(self):
        """Bir parser sidecar'ı okuyorsa workflow'dan erişilebilir olmalı."""
        for sidecar, parsers in sorted(LOGS_SIDECAR_PARSERS.items()):
            for parser in parsers:
                self.assertTrue(reachable_from_workflow(self.text, parser),
                                f"{parser} ({sidecar} parser'ı) workflow'dan "
                                "erişilemiyor — ölü parser")

    def test_producers_are_real(self):
        """Her beyan edilen üretici gerçekten o yolu yazmalı (ters yön)."""
        for sidecar, producers in sorted(LOGS_SIDECAR_PRODUCERS.items()):
            self.assertTrue(producers, f"{sidecar}: üretici beyanı boş")
            for ref in producers:
                kind, _, val = ref.partition(":")
                if kind == "script":
                    src = read_text(val)
                    self.assertIsNotNone(src, f"üretici script yok: {val}")
                    self.assertIn(sidecar.split("/")[-1], src,
                                  f"{val} {sidecar} sidecar'ını üretmiyor")
                elif kind == "workflow":
                    # Yazma deyimi: "<yol>", "w"   /  > <yol>  /  --out <yol>
                    idiom = re.search(
                        re.escape(sidecar) + "[\"']\\s*,\\s*[\"'][wa]",
                        self.text)
                    if idiom is None:
                        idiom = re.search(
                            r"(?:--out|>)\s*" + re.escape(sidecar) + r"\b",
                            self.text)
                    self.assertIsNotNone(
                        idiom,
                        f"'{val}' job'ında {sidecar} için yazma deyimi yok "
                        "(okunan ama üretilmeyen yol = sessiz FAIL)")
                else:
                    self.fail(f"bilinmeyen üretici türü: {ref}")


class TestLogsSidecarScannerSelfTest(unittest.TestCase):
    """Tarayıcının duyarlılığı (sentetik metinler, OFFLINE)."""

    def test_flags_undeclared_sidecar(self):
        fake = "\n".join([
            "jobs:",
            "  verify:",
            "    steps:",
            "      - run: |",
            "          echo x > logs/brand_new_findings.json",
        ])
        self.assertEqual(undeclared_sidecars(fake, {"logs/other.json"}),
                         ["logs/brand_new_findings.json"])

    def test_declared_sidecar_is_clean(self):
        fake = "\n".join([
            "      - run: |",
            "          python3 x.py --out logs/known.json",
        ])
        self.assertEqual(undeclared_sidecars(fake, {"logs/known.json"}), [])

    def test_comment_lines_are_ignored(self):
        fake = "\n".join([
            "      # logs/prose_only.json — yalnız yorumda geçiyor",
            "      - run: echo hi",
        ])
        self.assertEqual(logs_sidecar_literals(fake), [])

    def test_upload_covers_prefix_semantics(self):
        self.assertTrue(upload_covers("logs/a.json", "logs/"))
        self.assertTrue(upload_covers("logs/a.json", "logs/a.json"))
        self.assertFalse(upload_covers("logs/a.json", "other/"))
        self.assertFalse(upload_covers("logs/a.json", "logs/backup/"))

    def test_upload_paths_reads_multiline_block(self):
        fake = "\n".join([
            "  daemon-http:",
            "    steps:",
            "      - name: Upload bundle",
            "        uses: actions/upload-artifact@v6",
            "        with:",
            "          name: daemon-http",
            "          path: |",
            "            a_report.json",
            "            override_report.json",
        ])
        self.assertEqual(upload_paths(fake, "daemon-http"),
                         ["a_report.json", "override_report.json"])


if __name__ == "__main__":
    unittest.main()
