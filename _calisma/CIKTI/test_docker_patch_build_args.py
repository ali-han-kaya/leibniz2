#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_docker_patch_build_args.py — yama build-arg'larının override kapısı.

Sözleşme (docs/DOCKER_SECURITY_PATCHING.md · "Katkı sözleşmesi" madde 4):

  1) Çözümleyici (`docker_patch_build_args.sh`) floor'ları **Dockerfile ARG
     default'undan** okur; workflow'da ikinci bir kopya yaşamaz (drift
     imkânsız) — test bunu workflow metninde default literal'i ARAMAYARAK
     ve çözümleyicinin çıktısını Dockerfile'la karşılaştırarak pinler.
  2) Override env'i doluysa o kazanır; **boş değer default'u ezmez** (boş
     string yama katmanını sessizce kapatırdı: Dockerfile empty-guard
     "yama yok" kanıtı üretir).
  3) Default okunamazsa fail-closed (rc=1): sessizce floorsuz build yok.
  4) İki tüketici de aynı kapıdan geçer: CI image-scan build'i (`build-args:`)
     ve smoke script'inin build'i (`--build-arg=...`).

stdlib-only, OFFLINE; gerçek docker/CI çağrısı yok.
"""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HELPER = ROOT / "_calisma" / "CIKTI" / "docker_patch_build_args.sh"
DOCKERFILE = ROOT / "Dockerfile"
WORKFLOW = ROOT / ".github" / "workflows" / "docker-security.yml"
SMOKE = ROOT / "_calisma" / "CIKTI" / "docker_security_smoke.sh"

APT = "SECURITY_PATCH_PACKAGES"
PY = "PYTHON_SECURITY_PATCH_PACKAGES"
HELPER_NAME = "docker_patch_build_args.sh"


def dockerfile_default(name: str, path: Path = DOCKERFILE) -> str:
    """Dockerfile'daki `ARG NAME="..."` default'unu BAĞIMSIZ ayrıştırır — test
    tarafı kendi okumasını yapar ki çözümleyici ile aynı hatayı paylaşmasın."""
    text = path.read_text(encoding="utf-8")
    m = re.search(r'^ARG %s=(?:"([^"]*)"|([^\s#]+))' % re.escape(name),
                  text, re.M)
    if not m:
        return ""
    return m.group(1) if m.group(1) is not None else m.group(2)


def run_helper(mode="--github-output", env=None, cwd=None, dockerfile=None):
    e = dict(os.environ)
    for key in (APT, PY, "DOCKERFILE"):
        e.pop(key, None)
    e.update(env or {})
    if dockerfile is not None:
        e["DOCKERFILE"] = str(dockerfile)
    return subprocess.run(["bash", str(HELPER), mode],
                          capture_output=True, text=True, env=e,
                          cwd=str(cwd or ROOT))


def kv(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v
    return out


def step_block(text: str, step_name: str) -> str:
    """Workflow metninden bir adımın bloğunu çıkarır (sonraki adıma kadar)."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines)
                  if l.strip() == f"- name: {step_name}"), None)
    if start is None:
        raise AssertionError(f"adım bulunamadı: {step_name}")
    block = []
    for line in lines[start:]:
        if block and re.match(r"^\s{6}- name: ", line):
            break
        block.append(line)
    return "\n".join(block)


class TestPatchArgResolver(unittest.TestCase):
    """Çözümleyicinin davranışı (gerçek koşum, stub yok)."""

    def test_defaults_read_from_dockerfile(self):
        res = run_helper("--values")
        self.assertEqual(res.returncode, 0, res.stderr)
        values = kv(res.stdout)
        for name in (APT, PY):
            expected = dockerfile_default(name)
            self.assertTrue(expected, f"Dockerfile'da {name} default'u yok")
            self.assertEqual(values.get(name), expected,
                             f"{name} default'u Dockerfile'dan okunmalı")
        self.assertIn("apt_source=dockerfile-default", res.stderr)
        self.assertIn("python_source=dockerfile-default", res.stderr)

    def test_override_wins(self):
        res = run_helper("--values", env={APT: "libpcre2-8-0=99",
                                          PY: "setuptools>=999"})
        values = kv(res.stdout)
        self.assertEqual(values[APT], "libpcre2-8-0=99")
        self.assertEqual(values[PY], "setuptools>=999")
        self.assertIn("apt_source=override", res.stderr)
        self.assertIn("python_source=override", res.stderr)

    def test_empty_override_keeps_dockerfile_default(self):
        # KRİTİK: boş env "yamayı kapat" değildir. Boş string'i build-arg
        # olarak geçmek Python katmanını sessizce devre dışı bırakırdı.
        res = run_helper("--values", env={APT: "", PY: ""})
        values = kv(res.stdout)
        self.assertEqual(values[APT], dockerfile_default(APT))
        self.assertEqual(values[PY], dockerfile_default(PY))
        self.assertNotEqual(values[PY], "")
        self.assertIn("apt_source=dockerfile-default", res.stderr)

    def test_partial_override_keeps_other_default(self):
        res = run_helper("--values", env={APT: "pkg=1"})
        values = kv(res.stdout)
        self.assertEqual(values[APT], "pkg=1")
        self.assertEqual(values[PY], dockerfile_default(PY))
        self.assertIn("python_source=dockerfile-default", res.stderr)

    def test_github_output_mode_is_machine_readable(self):
        # stdout yalnız key=value (GITHUB_OUTPUT'a eklenir); kanıt satırları
        # stderr'e gider — aksi halde GITHUB_OUTPUT bozulurdu.
        for mode in ("--github-output",):
            res = run_helper(mode)
            self.assertEqual(res.returncode, 0, res.stderr)
            keys = [l.split("=", 1)[0] for l in res.stdout.splitlines()]
            self.assertEqual(keys, ["apt", "python"])
            self.assertNotIn("_source=", res.stdout)
            self.assertIn("apt_source=", res.stderr)

    def test_flags_mode_emits_docker_build_args(self):
        res = run_helper("--flags")
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = res.stdout.splitlines()
        self.assertEqual(len(lines), 2, lines)
        for line, name in zip(lines, (APT, PY)):
            self.assertTrue(line.startswith("--build-arg="), line)
            key, value = line[len("--build-arg="):].split("=", 1)
            self.assertEqual(key, name)
            self.assertEqual(value, dockerfile_default(name))

    def test_fails_closed_when_default_missing(self):
        with tempfile.TemporaryDirectory() as td:
            stub = Path(td) / "Dockerfile"
            stub.write_text("# yama katmanı yok\nFROM scratch\n",
                            encoding="utf-8")
            res = run_helper("--flags", dockerfile=stub)
            self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
            self.assertIn(APT, res.stderr)
            self.assertEqual(res.stdout, "",
                             "fail-closed'da build-arg ÜRETİLMEMELİ")

    def test_fails_closed_when_only_one_default_missing(self):
        # Her ARG'ın guard'ı BAĞIMSIZ olmalı: yalnız apt default'u eksikken
        # bile çözüm durur. (Yoksa pip guard'ı, silinen apt guard'ını
        # maskeler: apt sessizce boş build-arg olur → katman kapanır.)
        py_default = dockerfile_default(PY)
        self.assertTrue(py_default)
        with tempfile.TemporaryDirectory() as td:
            stub = Path(td) / "Dockerfile"
            stub.write_text(f'ARG {PY}="{py_default}"\nFROM scratch\n',
                            encoding="utf-8")
            res = run_helper("--flags", dockerfile=stub)
            self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
            self.assertEqual(res.stdout, "",
                             "apt default'u yokken hiçbir build-arg üretilmemeli")
            self.assertIn(APT, res.stderr)

    def test_fails_closed_when_dockerfile_missing(self):
        res = run_helper("--flags", dockerfile=Path("/nonexistent/Dockerfile"))
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)

    def test_unknown_mode_is_usage_error(self):
        res = run_helper("--nope")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)


class TestCiWorkflowWiring(unittest.TestCase):
    """CI build'i aynı override kapısını taşıyor mu (image-scan job'ı)."""

    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.build_step = step_block(cls.text, "Build image")
        cls.resolve_step = step_block(
            cls.text, "Resolve patch build-args (Dockerfile defaults + override)")

    def test_build_step_declares_both_build_args(self):
        args_block = self.build_step.split("build-args:", 1)[1]
        self.assertIn(f"{APT}=${{{{ steps.patch_args.outputs.apt }}}}",
                      args_block)
        self.assertIn(f"{PY}=${{{{ steps.patch_args.outputs.python }}}}",
                      args_block)

    def test_resolve_step_uses_the_single_resolver(self):
        self.assertIn(HELPER_NAME, self.resolve_step)
        self.assertIn("--github-output", self.resolve_step)
        self.assertIn("$GITHUB_OUTPUT", self.resolve_step)

    def test_workflow_does_not_restate_dockerfile_defaults(self):
        # Tek kaynak kuralı: floor'lar workflow'da ikinci kez yaşamaz.
        for name in (APT, PY):
            default = dockerfile_default(name)
            self.assertTrue(default)
            self.assertNotIn(default, self.text,
                             f"workflow Dockerfile default'unu tekrarlıyor: {name}")

    def test_build_args_come_from_resolver_not_raw_vars(self):
        # `vars.X` doğrudan build-arg'a bağlanırsa değişken boşken ARG boş
        # string'e çevrilir → yama katmanı sessizce kapanır.
        args_block = self.build_step.split("build-args:", 1)[1]
        self.assertNotIn("vars.", args_block)
        self.assertNotIn("inputs.", args_block)
        self.assertIn("steps.patch_args.outputs", args_block)

    def test_override_channel_precedence_and_dispatch_inputs(self):
        self.assertIn("github.event.inputs.security_patch_packages || "
                      "vars.SECURITY_PATCH_PACKAGES", self.text)
        self.assertIn("github.event.inputs.python_security_patch_packages || "
                      "vars.PYTHON_SECURITY_PATCH_PACKAGES", self.text)
        for input_name in ("security_patch_packages",
                           "python_security_patch_packages"):
            self.assertIn(f"{input_name}:", self.text)

    def test_resolve_step_reads_the_override_env_names(self):
        # Çözümleyici env adları ile workflow'un beslediği adlar aynı olmalı.
        step = self.resolve_step + self.text
        self.assertIn(f"{APT}: ${{{{ env.PATCH_ARG_APT_OVERRIDE }}}}", step)
        self.assertIn(f"{PY}: ${{{{ env.PATCH_ARG_PY_OVERRIDE }}}}", step)


class TestSmokeBuildWiring(unittest.TestCase):
    """Smoke build'i de aynı çözümleyiciden geçiyor mu."""

    @classmethod
    def setUpClass(cls):
        cls.text = SMOKE.read_text(encoding="utf-8")

    def test_smoke_build_uses_same_resolver(self):
        self.assertIn(HELPER_NAME, self.text)
        self.assertIn("--flags", self.text)

    def test_smoke_build_is_fail_closed(self):
        # Process substitution rc'yi yutar; bayraklar command substitution'la
        # alınıp hata açıkça yakalanmalı.
        self.assertRegex(self.text,
                         r'if ! patch_flags="\$\(bash "\$ROOT/_calisma/CIKTI/'
                         r'docker_patch_build_args\.sh" --flags\)"; then')
        self.assertIn("fail", self.text)

    def test_smoke_build_appends_flags_before_context(self):
        build = self.text.split("build_args=(build -t", 1)[1]
        build = build.split('log "platform=', 1)[0]
        # Tam-satır eşitliği: yorumlanmış/ölü `build_args+=(...)` satırı
        # substring kontrolünden kaçamaz (yorum = flag hiç eklenmez).
        lines = [l.strip() for l in build.splitlines()]
        self.assertIn('build_args+=("$flag")', lines,
                      "flag ekleme satırı gerçek bir komut olmalı")
        self.assertIn('build_args+=("$ROOT")', lines)
        self.assertLess(lines.index('build_args+=("$flag")'),
                        lines.index('build_args+=("$ROOT")'),
                        "build-arg'lar context'ten ÖNCE gelmeli (docker CLI)")
        # Bayraklar çözümleyicinin ÇIKTISINDAN gelmeli (kaynak bağı).
        self.assertIn('done <<< "$patch_flags"', lines)


if __name__ == "__main__":
    unittest.main()
