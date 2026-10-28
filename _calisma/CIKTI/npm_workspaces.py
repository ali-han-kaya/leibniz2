#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""npm_workspaces.py — npm bağımlılık yüzeyi kayıt defteri (TEK KAYNAK).

Neden ayrı modül: iki tüketici aynı kümeye bakmak zorunda —

  * `test_dockerfile_security_patching.py` — floor/hijyen sözleşmesi (offline,
    commit-anı kapısı),
  * `npm_audit_gate.py` — zorlayıcı `npm audit` eşik kapısı (CI).

Küme iki yerde yazılsaydı biri (ör. gate) yeni bir çalışma alanını sessizce
atlar, sözleşme ise onu denetliyor görünürdü: "kapsandı" sanılan ama taranmayan
bir yüzey — fail-open. Bu yüzden kapsam burada beyan edilir, iki taraf da
buradan okur.

Kayıt alanları (sözleşme detayı: docs/DOCKER_SECURITY_PATCHING.md):

  "overrides"   geçişli bağımlılık floor'u (package.json `overrides` bloğu)
  "direct"      doğrudan bağımlılık floor'u (dependencies/devDependencies)
  "scratch"     çalışma alanının ürettiği, .dockerignore'da SATIR olarak
                yaşaması gereken artefakt yüzeyleri
  "advisories"  floor'u doğuran advisory kimlikleri (doküman defteriyle eş)
  "optional"    bugün repoda olmayan (land edilmemiş) çalışma alanı

stdlib-only, OFFLINE — bu modül hiçbir şey çalıştırmaz.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Keşif sırasında inilmeyecek hijyen dizinleri (üretim artefaktı / venv).
# .dockerignore kurallarıyla aynı sınıf.
HYGIENE_DIRS = frozenset({
    ".git", ".worktrees", ".next", ".vercel", "node_modules",
    ".venv", ".venv_z3", "__pycache__",
})

NPM_WORKSPACES = {
    "apps/dashboard-next": {
        "direct": {"next": "15.5.28"},
        "overrides": {"postcss": "8.5.18", "sharp": "0.35.5",
                      "source-map-js": "1.2.2", "undici": "7.30.1",
                      "body-parser": "2.3.1", "fast-uri": "3.1.9",
                      "zod": "4.6.6", "@modelcontextprotocol/sdk": "1.31.1",
                      "hono": "4.13.11", "ip-address": "10.7.4"},
        "scratch": ("**/node_modules", "**/.next"),
        "advisories": ("CVE-2026-45623", "CVE-2026-73646",
                       "GHSA-f88m-g3jw-g9cj", "GHSA-rgj7-g3m4-5g8c",
                       "GHSA-mwv6-3258-q52c", "GHSA-8h8q-6873-q5fj",
                       "GHSA-wq5f-xc86-pv6w", "GHSA-68fv-2mgg-jv7q",
                       "GHSA-4w7w-5xrc-9h26", "GHSA-27r3-jxmh-p828",
                       "GHSA-w74x-v6f9-j3xg", "GHSA-6qxp-vccf-f47h",
                       "GHSA-5r4p-p66f-jhc7", "GHSA-rxp7-6hxx-x8q5",
                       "GHSA-mrhx-c7xc-m3w5", "GHSA-p293-qw3h-jr36",
                       "GHSA-2xp9-vwfh-vxw4", "GHSA-2464-fhr4-w9xw"),
    },
    "apps/dashboard-shadcn": {
        "direct": {"vite": "8.3.5"},
        "overrides": {"source-map-js": "1.2.2"},
        "scratch": ("**/node_modules", "**/dist", "**/.vite",
                    "**/tsconfig.tsbuildinfo"),
        "advisories": ("GHSA-68fv-2mgg-jv7q", "GHSA-698v-4r3x-3vcv"),
    },
    "apps/trend-db": {
        "direct": {"prisma": "7.10.1", "@prisma/client": "7.10.1",
                   "@prisma/adapter-pg": "7.10.1"},
        "overrides": {"@prisma/config": "7.10.1", "deepmerge-ts": "8.0.0",
                      "fast-uri": "3.1.9", "mysql2": "3.23.1"},
        "scratch": ("**/node_modules", "apps/trend-db/generated"),
        "advisories": ("GHSA-ggr8-5vv4-36mx", "GHSA-3f6p-5ww8-9rcr",
                       "GHSA-w74x-v6f9-j3xg"),
    },
    "_calisma/pptx": {
        "direct": {},
        "overrides": {"image-size": "2.0.3"},
        "scratch": ("**/node_modules", "**/*.pptx"),
        "advisories": ("GHSA-5p2g-fcmc-qvqq", "GHSA-w3rx-r6r6-pgpr"),
    },
    # docx export çalışma alanı bugün main'de YOK: yalnız land edilmemiş
    # dallarda (fix/branch-red-jobs, #54 soyu) duruyor. Kayıt bilinçli olarak
    # burada: dal land ettiği gün (package.json göründüğü an) aynı sözleşme
    # ona da uygulanır, ayrı bir tur gerekmez. 2026-10-28 ölçümü: docx 9.7.2
    # `npm audit` 0 bulgu → floor gerekmiyor.
    "_calisma/docx": {
        "direct": {"docx": "9.7.2"},
        "overrides": {},
        "scratch": ("**/node_modules",),
        "advisories": (),
        "optional": True,
    },
}

# Repoda package.json taşıyan ama bu sözleşmenin kapsamına BİLİNÇLİ olarak
# alınmayan çalışma alanı. Gerekçe zorunlu: keşif guard'ı bu anahtarı da
# denetler, gerekçesiz kayıt FAIL eder.
NPM_OUT_OF_SCOPE = {
    "_calisma/video":
        "Remotion 4.0.530 advisory'lerinin yamalı sürümü yok — npm audit'in "
        "tek 'fix'i 4.0.277'ye downgrade öneriyor (isSemVerMajor); floor "
        "yazılamaz, downgrade kaynak/yeteneksel davranışı bozar. "
        "Yeniden ölçülecek: Remotion yamalı sürüm yayımladığında.",
}


def repo_npm_workspaces():
    """Repo yüzeyindeki package.json dizinleri (hijyen dizinleri hariç), sıralı."""
    found = []
    for base, dirs, files in os.walk(str(ROOT), followlinks=False):
        dirs[:] = [d for d in dirs if d not in HYGIENE_DIRS]
        if "package.json" in files:
            found.append(Path(base).relative_to(ROOT).as_posix())
    return sorted(found)


def present_workspaces():
    """Kayıtta olup BUGÜN repoda duran çalışma alanları (lockfile zorunlu).

    `optional` işaretli kayıt (land edilmemiş dal) yoksa sessizce atlanır;
    `optional` olmayan bir kayıt yoksa bu bir kapsam kaybıdır ve çağıran
    taraf (test) FAIL eder — gate ise yalnız var olanı tarar.
    """
    return sorted(ws for ws in NPM_WORKSPACES
                  if (ROOT / ws / "package.json").is_file())


def load_package(rel):
    return json.loads((ROOT / rel / "package.json").read_text(encoding="utf-8"))


def load_lock(rel):
    return json.loads((ROOT / rel / "package-lock.json").read_text(encoding="utf-8"))
