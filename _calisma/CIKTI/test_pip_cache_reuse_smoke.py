#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_pip_cache_reuse_smoke.py — pip cache reuse'ın STATİK sözleşmesi.

Neden statik: eski sürüm `/tmp/q1-{A,B,C2}.log` dosyalarına bağlıydı. O
dosyalar hiçbir zaman repoya girmedi (makineye özgü, uçucu), bu yüzden süit
temiz bir checkout'ta/CI'da her koşumda 0 satır okuyup kırmızıya düşüyordu —
ölçtüğü şey cache davranışı değil, o makinenin /tmp içeriğiydi.

Gerçek mekanizma Dockerfile'dadır: BuildKit `--mount=type=cache,
target=/root/.cache/pip,sharing=locked` mount'u ikinci build'e wheel'leri
cache'ten verir. `--no-cache-dir` ile BİRLİKTE kullanılırsa mount boşa
çıkar (pip cache'i kapatır) — eski logların gösterdiği "ikinci build 0
download / 4 cached" davranışı tam olarak bu mount'un sonucudur.

Bu dosya o sözleşmeyi metinden ölçer: mount kaldırılır ya da `--no-cache-dir`
geri gelirse test KIRMIZI olur. Tarayıcı/Docker/ağ gerekmez.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DOCKERFILE = ROOT / "Dockerfile"

PIP_MOUNT = "type=cache,target=/root/.cache/pip"
PIP_INSTALL_RE = re.compile(r"\bpip\s+install\b")


def instructions(text):
    """Dockerfile'ı mantıksal talimatlara böler (satır devamları birleşir)."""
    out, buf = [], []
    for line in text.splitlines():
        stripped = line.strip()
        if not buf and (not stripped or stripped.startswith("#")):
            continue
        if stripped.startswith("#") and buf:
            # Yorum, devam eden talimatın ortasında olamaz; ayır.
            out.append("\n".join(buf))
            buf = []
            continue
        buf.append(line)
        if not stripped.endswith("\\"):
            out.append("\n".join(buf))
            buf = []
    if buf:
        out.append("\n".join(buf))
    return out


class TestPipCacheMountContract(unittest.TestCase):
    """Dockerfile pip kurulumları cache mount'lu ve `--no-cache-dir`siz."""

    @classmethod
    def setUpClass(cls):
        cls.text = DOCKERFILE.read_text(encoding="utf-8")
        cls.units = [u for u in instructions(cls.text)
                     if PIP_INSTALL_RE.search(u)]

    def test_dockerfile_has_pip_installs(self):
        self.assertGreaterEqual(len(self.units), 2,
                                "Dockerfile'da pip install talimatı beklenmedik "
                                "azaldı — tarama kör mü?")

    def test_every_pip_install_uses_the_cache_mount(self):
        offenders = [u for u in self.units if PIP_MOUNT not in u]
        self.assertEqual(
            offenders, [],
            "pip install cache mount'suz — ikinci build wheel'leri yeniden "
            "indirir:\n" + "\n---\n".join(offenders))

    def test_mount_is_sharing_locked(self):
        for unit in self.units:
            self.assertIn(PIP_MOUNT + ",sharing=locked", unit,
                          "pip cache mount `sharing=locked` değil — eşzamanlı "
                          "build'ler aynı HTTP cache'ine yazıp bozabilir")

    def test_no_cache_dir_is_not_used_with_the_mount(self):
        offenders = [u for u in self.units if "--no-cache-dir" in u]
        self.assertEqual(
            offenders, [],
            "`--no-cache-dir` cache mount'u etkisizleştirir (pip cache'i "
            "kapatır):\n" + "\n---\n".join(offenders))

    def test_mount_does_not_persist_in_the_image_layer(self):
        # BuildKit cache mount KATMANA yazmaz; imaj boyutu hijyeni korunur.
        # Bu bir metin kanıtıdır: mount talimatı `RUN` ile aynı satırda.
        for unit in self.units:
            first = unit.lstrip().splitlines()[0]
            self.assertTrue(first.startswith("RUN --mount="),
                            "pip mount RUN talimatıyla aynı satırda değil: %r"
                            % first[:80])


if __name__ == "__main__":
    unittest.main()
