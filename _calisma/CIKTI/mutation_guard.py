#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mutation_guard.py — kalıcı mutasyon-kanıt yardımcısı (fail-closed bekçiler).

Bir bekçinin gerçekten bir şey beklediğini kanıtlamanın dürüst yolu,
koruduğu artefaktı GEÇİCİ bir kopyada bilinçli olarak zayıflatmak ve
bekçinin KIRMIZI düştüğünü görmektir. Mutasyon kaçarsa (artefakt
zayıfladığı hâlde bekçi yeşil kalırsa) bu yardımcıyı kullanan test kırmızı
olur — böylece "fail-closed" iddiası prose'ta değil, her koşumda ölçülen
bir kanıt olarak durur (docs/adr/NEGATIVE_TEST_CONTRACTS.md §5 kural 3).

Sözleşme:

  * `apply_mutations` — her (old, new) çifti metinde TAM BİR kez geçmeli;
    geçmiyorsa `MutationNotApplicable`. Bayat mutasyon sessiz no-op olamaz:
    kaynak yeniden yazıldıysa kanıt da yenilenmek zorundadır.
  * `mutated_copy` — kaynak dosyayı temp dizine kopyalar, mutasyonu uygular.
  * `load_copy` / `unload` — mutant Python modülünü izole isimle yükler.
  * `run_script` — mutant betiği gerçek CLI gibi koşar (rc/stdout/stderr).

stdlib-only, ağ yok, repo dışına yazmaz.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


class MutationNotApplicable(AssertionError):
    """Mutasyon kaynak metne uymadı — bayat kanıt (test kırmızı olmalı)."""


def apply_mutations(text, mutations):
    """(old, new) çiftlerini sırayla uygula; her çift tam 1 kez eşleşmeli."""
    out = text
    for old, new in mutations:
        hits = out.count(old)
        if hits != 1:
            raise MutationNotApplicable(
                "mutasyon tam 1 kez eşleşmeli, %d bulundu: %r"
                % (hits, old[:80]))
        out = out.replace(old, new)
    return out


def mutated_text(path, mutations):
    """Dosya metninin mutasyonlu kopyası (dosyaya yazmaz)."""
    return apply_mutations(Path(path).read_text(encoding="utf-8"), mutations)


def mutated_copy(src, tmpdir, mutations, name=None):
    """Kaynağı temp dizine kopyala, mutasyonu kopyaya uygula."""
    src = Path(src)
    dst = Path(tmpdir) / (name or src.name)
    dst.write_text(
        apply_mutations(src.read_text(encoding="utf-8"), mutations),
        encoding="utf-8")
    return dst


def load_copy(path, module_name):
    """Mutant kopyayı `module_name` altında yükle (izole, sys.path'e dokunmaz)."""
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise MutationNotApplicable("modül yüklenemedi: %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def unload(module_name):
    """Yüklenen mutant modülü sys.modules'tan düşür."""
    sys.modules.pop(module_name, None)


def run_script(path, *args, cwd=None, env=None, timeout=120):
    """Mutant betiği gerçek giriş noktası gibi koş."""
    return subprocess.run(
        [sys.executable, str(path), *args],
        cwd=None if cwd is None else str(cwd),
        env=env, capture_output=True, text=True, timeout=timeout)
