#!/usr/bin/env python3
"""test_docker_security_smoke.py — docker_security_smoke.sh davranış kapısı.

docker_security_smoke.sh (tek komutluk Docker/Trivy güvenlik smoke'u)
sözleşmelerini OFFLINE ve deterministik doğrular:

  1) docker yok → SKIP (exit 0) — ortam yokluğu kod hatası değildir;
     kanıt üretmeden iddia edilmez (SKIP/fail-closed deseni).
  2) daemon açılmıyor + colima var → colima start DENER; yine de açılmazsa
     SKIP — başlatma yolu çalışır, sessizce atlanmaz.
  3) Trivy bulgu üretirse (CRITICAL/HIGH) → exit 1 ve kanıta verdict=FAIL
     yazar (fail-closed; CI'daki exit-code 1 gate'inin yerel karşılığı).
  4) Tam akış (build + trivy temiz + health HTTP 200) → exit 0 ve kanıta
     verdict=PASS yazar; /api/health doğrulaması GERÇEK curl + yerel HTTP
     sunucusuyla yapılır (host→konteyner kanıt zincirinin yerel ikamesi).

Stub araçlar (docker/colima/trivy) PATH üzerinden binir; curl gerçek
/usr/bin/curl'dür. Gerçek image build/trivy taraması yapmaz — onların
kanıtı canlı koşumdadır (docs/ci_simulate/docker_security_smoke/).

stdlib-only, OFFLINE.
"""
import http.server
import os
import re
import shutil
import socketserver
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "_calisma" / "CIKTI" / "docker_security_smoke.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "docker-security.yml"
PR_COMMENT = (ROOT / "_calisma" / "CIKTI" / "github_scripts" /
              "trivy_sarif_pr_comment.js")

# Kapı girdileri — docker-security.yml workflow-env'inden beklenen değerler.
# Tek kaynak orası; script'in varsayılanları bunlarla birebir tutulur.
GATE_ENV_EXPECTED = {"TRIVY_GATE_SEVERITY": "CRITICAL,HIGH",
                     "TRIVY_GATE_IGNORE_UNFIXED": "true"}
ENV_EXPR_SEVERITY = "${{ env.TRIVY_GATE_SEVERITY }}"
ENV_EXPR_IGNORE_UNFIXED = "${{ env.TRIVY_GATE_IGNORE_UNFIXED }}"

EMPTY_PATH = "/usr/bin:/bin"  # stub yok — docker/trivy/colima bulunamaz

# Stub docker: alt komuta göre davranır; info başarısı DOCKER_STUB_INFO_OK ile
# kontrol edilir (daemon açılmama senaryosu için), health inspect her zaman
# healthy der, port eşlemesi STUB_HEALTH_PORT'a işaret eder.
DOCKER_STUB = """#!/bin/sh
cmd="$1"; shift || true
case "$cmd" in
  version) printf 'client=stub\\nserver=stub\\n' ;;
  info)
    if [ "${DOCKER_STUB_INFO_OK:-0}" = "1" ]; then exit 0; else exit 1; fi ;;
  build) echo "Successfully built stub" ;;
  image) echo "sha256:stub-image-id" ;;
  run) printf 'cid-stub-1234\\n' ;;
  port) printf '0.0.0.0:%s\\n' "$STUB_HEALTH_PORT" ;;
  inspect) echo "healthy" ;;
  rm) exit 0 ;;
  *) echo "docker stub: unknown cmd $cmd" >&2; exit 1 ;;
esac
"""

COLIMA_STUB = """#!/bin/sh
case "$1" in
  start) echo "colima stub: started" ;;
  status) exit 0 ;;
  *) exit 0 ;;
esac
"""

TRIVY_STUB = """#!/bin/sh
echo "trivy stub scan"
exit ${TRIVY_STUB_RC:-0}
"""


class TestDockerSecuritySmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="docker-smoke-test-")
        cls._bin = Path(cls._tmp) / "bin"
        cls._bin.mkdir()
        for name, body in (("docker", DOCKER_STUB),
                           ("colima", COLIMA_STUB),
                           ("trivy", TRIVY_STUB)):
            p = cls._bin / name
            p.write_text(body, encoding="utf-8")
            p.chmod(0o755)
        cls._out = Path(cls._tmp) / "evidence.txt"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _run(self, extra_env=None, with_stubs=True):
        env = dict(os.environ)
        env["DOCKER_SMOKE_OUT"] = str(self._out)
        if with_stubs:
            env["PATH"] = f"{self._bin}:{EMPTY_PATH}"
        else:
            env["PATH"] = EMPTY_PATH
        if extra_env:
            env.update(extra_env)
        return subprocess.run(["bash", str(SCRIPT)],
                              capture_output=True, text=True, env=env)

    def test_skip_when_docker_missing(self):
        # PATH'te docker yok → SKIP, exit 0 (araç yokluğu kod hatası değil).
        r = self._run(with_stubs=False)
        self.assertEqual(r.returncode, 0,
                         f"docker'sız ortam bloke etmemeli:\n{r.stdout}\n{r.stderr}")
        self.assertIn("SKIP", r.stdout + r.stderr)
        self.assertNotIn("verdict=PASS", self._out.read_text(encoding="utf-8"))

    def test_colima_start_attempted_then_skip(self):
        # Daemon açılmıyor (info fail) + colima var → start denenir; stub daemon
        # yine açılmaz → SKIP. Başlatma yolunun gerçekten tetiklendiği log'dan
        # kanıtlanır (sessiz atlama yasak).
        r = self._run({"DOCKER_STUB_INFO_OK": "0"})
        self.assertEqual(r.returncode, 0,
                         f"daemon açılmayan ortam SKIP olmalı:\n{r.stdout}\n{r.stderr}")
        self.assertIn("SKIP", r.stdout + r.stderr)
        self.assertIn("colima=starting", r.stdout + r.stderr)

    def test_fail_closed_when_trivy_finding(self):
        # Trivy bulgu üretir (rc=1) → script exit 1 + kanıta verdict=FAIL.
        r = self._run({"DOCKER_STUB_INFO_OK": "1", "TRIVY_STUB_RC": "1"})
        self.assertEqual(r.returncode, 1, "trivy bulgusu fail-closed olmalı")
        self.assertIn("Trivy gate", r.stdout + r.stderr)
        self.assertIn("verdict=FAIL", self._out.read_text(encoding="utf-8"))

    def test_full_pass_path_with_real_health_check(self):
        # Tam akış: build ok + trivy ok + GERÇEK curl /api/health 200 +
        # HEALTHCHECK healthy → exit 0, kanıtta verdict=PASS.
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"ok"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            r = self._run({"DOCKER_STUB_INFO_OK": "1",
                           "STUB_HEALTH_PORT": str(httpd.server_address[1])})
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertEqual(r.returncode, 0,
                         f"tam akış PASS olmalı:\n{r.stdout}\n{r.stderr}")
        self.assertIn("PASS:", r.stdout + r.stderr)
        evidence = self._out.read_text(encoding="utf-8")
        self.assertIn("verdict=PASS", evidence)
        self.assertIn("health_http=200", evidence)
        self.assertIn("health_body=ok", evidence)
        self.assertIn("trivy_clean=Clean", evidence)


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli (docker-security.yml ayrıştırma)")
class TestTrivyCommentGateWiring(unittest.TestCase):
    """Zorlayıcı Trivy adımı ↔ PR yorum script'i tek kapı eşiği paylaşır.

    Sözleşme: severity/ignore-unfixed girdileri workflow-env'te TEK kez
    tanımlanır, zorlayıcı tabela adımı ile SARIF adımı oradan okur, yorum
    script'i de process.env üzerinden aynısını görür. `severityOf` düşüşü
    sessiz HIGH değil açık 'bilinmiyor'dur (fail-closed).
    """

    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.wf = yaml.safe_load(cls.text)
        cls.src = PR_COMMENT.read_text(encoding="utf-8")

    @staticmethod
    def _step(job, name_marker):
        for step in job["steps"]:
            if name_marker in str(step.get("name", "")):
                return step
        return None

    def test_gate_env_declares_enforcing_inputs_once(self):
        env = self.wf.get("env") or {}
        for key, want in GATE_ENV_EXPECTED.items():
            self.assertEqual(env.get(key), want,
                             f"workflow-env {key} beklenen değer değil")
        # Tek kaynak: bu değişken workflow-env'te AYNI anda hard-coded
        # ikinci bir kopyası olmamalı (adım-içi literal drift'i).
        steps_text = self.text.split("jobs:", 1)[-1]
        self.assertNotIn("severity: CRITICAL,HIGH", steps_text,
                         "zorlayıcı/SARIF adımı literal severity taşımamalı — "
                         "kapı eşiği workflow-env'ten gelmeli")
        self.assertNotIn("ignore-unfixed: true", steps_text,
                         "zorlayıcı/SARIF adımı literal ignore-unfixed "
                         "taşımamalı — kapı eşiği workflow-env'ten gelmeli")

    def test_both_trivy_steps_read_gate_env(self):
        # Zorlayıcı tabela adımı ve SARIF adımı AYNI girdileri paylaşmalı:
        # SARIF'i üreten filtre, kapı kararıyla çelişemez.
        job = self.wf["jobs"]["image-scan"]
        for marker in ("Scan image with Trivy (SARIF)",
                       "Scan image with Trivy (table"):
            step = self._step(job, marker)
            self.assertIsNotNone(step, f"adım bulunamadı: {marker}")
            with_ = step.get("with") or {}
            self.assertEqual(with_.get("severity"), ENV_EXPR_SEVERITY,
                             f"{marker}: severity gate-env'i okumuyor")
            self.assertEqual(with_.get("ignore-unfixed"),
                             ENV_EXPR_IGNORE_UNFIXED,
                             f"{marker}: ignore-unfixed gate-env'i okumuyor")
            self.assertEqual(str(with_.get("exit-code")), "1",
                             f"{marker}: fail-closed exit-code 1 zorunlu")

    def test_comment_step_is_gated_and_reads_script(self):
        step = self._step(self.wf["jobs"]["image-scan"],
                          "Annotate PR with Trivy findings")
        self.assertIsNotNone(step, "PR yorum adımı yok")
        # always() — gate kırmızıyken de kanıt yorumu düşmeli; PR dışı olayda
        # yorum yazılmaz.
        self.assertIn("github.event_name == 'pull_request'",
                      str(step.get("if")))
        script = str((step.get("with") or {}).get("script", ""))
        self.assertIn("trivy_sarif_pr_comment.js", script)
        # workflow-env her adıma otomatik aktarılır — adımla ek env GEREKMEZ;
        # yine de script'in kapı değişkenlerini okuduğunu pin'le.
        used = set(re.findall(r"process\.env\.([A-Z0-9_]+)", self.src))
        for key in GATE_ENV_EXPECTED:
            self.assertIn(key, used,
                          f"script {key} okumuyor — kapı eşiği kaynaktan kopuk")

    def test_script_fallback_is_explicit_unknown_not_high(self):
        # severityOf düşüşü: sessiz HIGH YOK; açık 'UNKNOWN' (yorumda
        # 'bilinmiyor') + fail-closed setFailed.
        self.assertRegex(self.src, r"return\s+UNKNOWN\s*;",
                         "severityOf düşüşü UNKNOWN olmalı")
        self.assertNotRegex(self.src, r"return\s+'HIGH'\s*;",
                            "severityOf sessiz HIGH döndüremez — kapı eşiği "
                            "TRIVY_GATE_SEVERITY'den gelir")
        self.assertIn("bilinmiyor", self.src,
                      "bilinmeyen seviye yorumda açıkça işaretlenmeli")
        self.assertIn("TRIVY_GATE_SEVERITY", self.src)
        self.assertIn("TRIVY_GATE_IGNORE_UNFIXED", self.src)

    def test_workflow_still_triggers_on_pull_request(self):
        # PR kapısı varlığı — yorum adımı bu olaya bağlı. (PyYAML 1.1'de
        # `on` anahtarı True'ya çözülür — iki anahtar da denenir.)
        on_block = self.wf.get("on", self.wf.get(True))
        self.assertIsNotNone(on_block, "workflow `on:` bloğu yok")
        self.assertIn("pull_request", on_block)


if __name__ == "__main__":
    unittest.main()
