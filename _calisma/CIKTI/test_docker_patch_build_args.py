#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_docker_patch_build_args.py — yama build-arg'larının override kapısı.

Sözleşme (docs/DOCKER_SECURITY_PATCHING.md · "Katkı sözleşmesi" madde 4):
floor'lar Dockerfile ARG default'undan okunur (workflow'da ikinci kopya yok);
dolu override kazanır; BOŞ override default'u ezmez (boş string yama katmanını
sessizce kapatırdı); default okunamazsa fail-closed; iki tüketici de aynı
çözümleyiciden geçer (CI build-args + smoke --flags).

Mimari — TEK TABLO, İKİ KATMAN: apt ve pip aynı sözleşmeye tabidir, katmana
bağlı satırlar LAYER_SCENES'te bir kez yazılır ve her satır iki katmanda da
koşar (subTest: layer=apt/pip); katman başına kopya test yok (kopya = drift).
Mod/ortam sözleşmeleri ve workflow+smoke wiring'i de satır tablolarıdır.

stdlib-only, OFFLINE; gerçek docker/CI çağrısı yok.
"""
import os
import re
import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HELPER = ROOT / "_calisma" / "CIKTI" / "docker_patch_build_args.sh"
DOCKERFILE = ROOT / "Dockerfile"
WORKFLOW = ROOT / ".github" / "workflows" / "docker-security.yml"
SMOKE = ROOT / "_calisma" / "CIKTI" / "docker_security_smoke.sh"

APT = "SECURITY_PATCH_PACKAGES"
PY = "PYTHON_SECURITY_PATCH_PACKAGES"
HELPER_NAME = "docker_patch_build_args.sh"
RESOLVE_STEP = "Resolve patch build-args (Dockerfile defaults + override)"


def dockerfile_default(name, path=None):
    """`ARG NAME="..."` default'unu BAĞIMSIZ ayrıştırır (test kendi okumasını
    yapar ki çözümleyiciyle aynı hatayı paylaşmasın)."""
    text = (path or DOCKERFILE).read_text(encoding="utf-8")
    m = re.search(r'^ARG %s=(?:"([^"]*)"|([^\s#]+))' % re.escape(name), text, re.M)
    return "" if not m else (m.group(1) if m.group(1) is not None else m.group(2))


def run_helper(mode="--github-output", env=None, dockerfile=None):
    e = {k: v for k, v in os.environ.items() if k not in (APT, PY, "DOCKERFILE")}
    e.update(env or {})
    if dockerfile is not None:
        e["DOCKERFILE"] = str(dockerfile)
    return subprocess.run(["bash", str(HELPER), mode], capture_output=True,
                          text=True, env=e, cwd=str(ROOT))


def kv(text):
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def step_block(text, name):
    """Workflow metninden bir adımın bloğu (sonraki adıma kadar)."""
    lines = text.splitlines()
    i = next(i for i, l in enumerate(lines) if l.strip() == f"- name: {name}")
    block = []
    for line in lines[i:]:
        if block and re.match(r"^\s{6}- name: ", line):
            break
        block.append(line)
    return "\n".join(block)


@dataclass(frozen=True)
class Layer:
    key: str      # tablo ekseni: apt / pip
    name: str     # env + Dockerfile ARG adı
    output: str   # --github-output anahtarı = steps.patch_args.outputs.*
    source: str   # stderr kaynak-kanıtı anahtarı
    ci_env: str   # workflow override kanalı env'i
    input: str    # workflow_dispatch input adı


LAYERS = (
    Layer("apt", APT, "apt", "apt_source", "PATCH_ARG_APT_OVERRIDE",
          "security_patch_packages"),
    Layer("pip", PY, "python", "python_source", "PATCH_ARG_PY_OVERRIDE",
          "python_security_patch_packages"),
)
PEERS = {LAYERS[0].key: LAYERS[1], LAYERS[1].key: LAYERS[0]}
DEFAULTS = {l.key: dockerfile_default(l.name) for l in LAYERS}


@dataclass(frozen=True)
class Scene:
    """Katman sözleşmesinin tek satırı — apt ve pip'te AYNI koşar."""
    name: str
    env: object = None         # bu katmanın override env değeri; None = verilmez
    value: str = "default"     # beklenen değer: "default" | kalıp ({key} doldurulur)
    source: str = "dockerfile-default"
    peer_value: str = "default"
    peer_source: str = "dockerfile-default"
    rc: int = 0
    flags: bool = False        # --flags modunda koş (fail-closed satırı)
    peer_only_stub: bool = False  # stub'da YALNIZ karşı katmanın ARG'ı var


LAYER_SCENES = (
    Scene("default Dockerfile ARG'ından okunur"),
    Scene("dolu override kazanır; karşı katman default'ta kalır",
          env="override-{key}=1", value="override-{key}=1", source="override"),
    Scene("boş override default'u EZMEZ (yama katmanı açık kalır)", env=""),
    Scene("bu katmanın ARG'ı yoksa fail-closed (build-arg üretilmez)",
          rc=1, flags=True, peer_only_stub=True),
)


def scene_problems(scene, layer, out):
    """Satırı bir katman için doğrular; ihlalleri döner (boş = geçti)."""
    peer = PEERS[layer.key]

    def expect(spec, l):
        return DEFAULTS[l.key] if spec == "default" else spec.format(key=l.key)

    bad = []
    if out.returncode != scene.rc:
        bad.append(f"rc={out.returncode} ≠ {scene.rc}: {out.stderr.strip()}")
    if scene.rc != 0:
        if out.stdout:
            bad.append(f"fail-closed'da build-arg üretilmemeli: {out.stdout!r}")
        if layer.name not in out.stderr:
            bad.append("eksik ARG stderr'de adıyla geçmeli")
        return bad
    values, sources = kv(out.stdout), kv(out.stderr)
    for l, value, source in ((layer, scene.value, scene.source),
                             (peer, scene.peer_value, scene.peer_source)):
        if values.get(l.name) != expect(value, l):
            bad.append(f"{l.name}={values.get(l.name)!r} ≠ {expect(value, l)!r}")
        if sources.get(l.source) != source:
            bad.append(f"{l.source}={sources.get(l.source)!r} ≠ {source!r}")
    return bad


class TestPatchArgGate(unittest.TestCase):
    """Çözümleyici sözleşmesi: tek tablo, iki katman."""

    def test_layer_scene_table(self):
        self.assertEqual([l.key for l in LAYERS if not DEFAULTS[l.key]], [],
                         "her katmanın Dockerfile default'u olmalı — tablo bu "
                         "tohumla kurulur")
        for scene in LAYER_SCENES:
            for layer in LAYERS:
                with self.subTest(scenario=scene.name, layer=layer.key):
                    env, tmp = {}, None
                    if scene.env is not None:
                        env[layer.name] = scene.env.format(key=layer.key)
                    kwargs = {}
                    if scene.peer_only_stub:
                        peer = PEERS[layer.key]
                        tmp = tempfile.TemporaryDirectory()
                        stub = Path(tmp.name) / "Dockerfile"
                        stub.write_text(
                            f'ARG {peer.name}="{DEFAULTS[peer.key]}"\nFROM scratch\n',
                            encoding="utf-8")
                        kwargs["dockerfile"] = stub
                    try:
                        out = run_helper("--flags" if scene.flags else "--values",
                                         env=env, **kwargs)
                    finally:
                        if tmp is not None:
                            tmp.cleanup()
                    bad = scene_problems(scene, layer, out)
                    self.assertEqual(
                        bad, [],
                        f"[{scene.name} · {layer.key}] {'; '.join(bad)}\n"
                        f"  stdout={out.stdout!r} stderr={out.stderr!r}")

    def test_tool_contracts(self):
        """Mod şekilleri + ortam fail-closed'ları (katmandan bağımsız)."""
        flags = run_helper("--flags")
        self.assertEqual(flags.returncode, 0, flags.stderr)
        self.assertEqual(flags.stdout.splitlines(),
                         [f"--build-arg={l.name}={DEFAULTS[l.key]}"
                          for l in LAYERS])
        gh = run_helper("--github-output")
        self.assertEqual(gh.returncode, 0, gh.stderr)
        self.assertEqual([x.split("=", 1)[0] for x in gh.stdout.splitlines()],
                         [l.output for l in LAYERS])
        self.assertNotIn("_source=", gh.stdout)
        self.assertTrue(all(l.source in gh.stderr for l in LAYERS))
        self.assertEqual(run_helper("--nope").returncode, 2)
        gone = run_helper("--flags", dockerfile="/nonexistent/Dockerfile")
        self.assertEqual((gone.returncode, gone.stdout), (1, ""))
        with tempfile.TemporaryDirectory() as td:
            stub = Path(td) / "Dockerfile"
            stub.write_text("# yama katmanı yok\nFROM scratch\n", encoding="utf-8")
            empty = run_helper("--flags", dockerfile=stub)
        self.assertEqual((empty.returncode, empty.stdout), (1, ""))
        self.assertIn(APT, empty.stderr)


class TestWiring(unittest.TestCase):
    """Aynı kapı iki tüketicide: CI image-scan build'i ve smoke build'i."""

    def _rows(self, rows):
        for name, ok in rows:
            with self.subTest(contract=name):
                self.assertTrue(ok, name)

    def test_workflow_contract_rows(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        args = step_block(text, "Build image").split("build-args:", 1)[1]
        resolve = step_block(text, RESOLVE_STEP)
        self._rows([
            ("build-arg · her katman çözümleyici çıktısından",
             all(f"{l.name}=${{{{ steps.patch_args.outputs.{l.output} }}}}"
                 in args for l in LAYERS)),
            ("build-args ham vars./inputs. taşımaz",
             "steps.patch_args.outputs" in args and "vars." not in args
             and "inputs." not in args),
            ("resolve adımı tek çözümleyiciyi $GITHUB_OUTPUT'a yazar",
             HELPER_NAME in resolve and "--github-output" in resolve
             and "$GITHUB_OUTPUT" in resolve),
            ("workflow Dockerfile default'unu tekrarlamaz",
             all(dockerfile_default(l.name) not in text for l in LAYERS)),
            ("override önceliği · dispatch input > vars.",
             all(f"github.event.inputs.{l.input} || vars.{l.name}" in text
                 for l in LAYERS)),
            ("workflow_dispatch input'ları tanımlı",
             all(re.search(rf"^\s+{l.input}:$", text, re.M) for l in LAYERS)),
            ("resolve adımı kanal env'lerini besler",
             all(f"{l.name}: ${{{{ env.{l.ci_env} }}}}" in resolve for l in LAYERS)),
        ])

    def test_smoke_contract_rows(self):
        text = SMOKE.read_text(encoding="utf-8")
        build = text.split("build_args=(build -t", 1)[1].split('log "platform=', 1)[0]
        lines = [l.strip() for l in build.splitlines()]
        self._rows([
            ("smoke build'i aynı çözümleyiciyi --flags ile çağırır",
             f'"$ROOT/_calisma/CIKTI/{HELPER_NAME}" --flags' in text),
            ("smoke build'i fail-closed (rc yutulmaz, fail çağrısı aynı kapıda)",
             re.search(r'if ! patch_flags="\$\(bash "\$ROOT/_calisma/CIKTI/'
                       r'docker_patch_build_args\.sh" --flags\)"; then\s*\n\s*fail "',
                       text) is not None),
            ("çözümleyici çıktısı flag flag build'e eklenir",
             'build_args+=("$flag")' in lines),
            ("bayraklar context'ten ÖNCE gelir",
             'build_args+=("$flag")' in lines
             and 'build_args+=("$ROOT")' in lines
             and lines.index('build_args+=("$flag")')
             < lines.index('build_args+=("$ROOT")')),
            ("bayraklar çözümleyici ÇIKTISINDAN gelir (kaynak bağı)",
             'done <<< "$patch_flags"' in lines),
        ])


if __name__ == "__main__":
    unittest.main()
