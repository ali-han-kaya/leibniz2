#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generated_surfaces.py — commit dışı ÜRETİLMİŞ yüzeylerin tek envanteri.

NEDEN
-----
Bazı yüzeyler repoda yaşamaz (`.gitignore`): demo artifact'ı, video paketi,
dashboard derlemesi, CI sidecar'ları, canlı runtime verisi. Bunları denetleyen
kapı/tests "dosya yoksa SKIP" derse, taze klonda ve CI'da kanıt SESSİZCE
kaybolur — `design_preview.html` tam bu sınıftı (statik kapı yalnız yerel
kopyaya bakıyordu; 2026-10-21'de "her koşuda üret + tara"ya çevrildi).

Bu modül iki şeyi tek yerde tutar:

1. **BUILD yüzeyleri** — burada ÜRETİCİ + ÇIKTI + TARAYICI vardır;
   `check_generated_surfaces.py` onları geçici/üretim yoluna GERÇEKTEN üretip
   tarar. Üretim ya da tarama başarısızsa kapı kırmızıdır (SKIP değil).
2. **SINIFLANDIRILMIŞ yüzeyler** — üretimi bu kapının işi olmayan (CI adımı,
   canlı runtime, toolchain) yüzeyler. "Yok sayıldı" değiller: her biri
   `owner` (üreten adım/kod) ve `scan_owner` (tarayan kapı/test) alanlarıyla
   BEYAN edilir; kapı bu beyanların gerçekten var olduğunu doğrular
   (AGENTS.md "hayalet kapsam kaydı" dersi: kayıt var, yürütme yok = fail-open).

KAPSAM KURALI (sınıf garantisi)
-------------------------------
`check_generated_surfaces.py --audit`, kapı/test kaynaklarındaki
`.gitignore`'lu yol literallerini tarar ve her birinin bu envanterde
sınıflandırılmış olmasını ister. Yeni bir üretilmiş yüzey eklenip
envantere yazılmazsa `--audit` kırmızıya düşer → "design_preview.html
boşluğu" tek örnek olarak kalamaz.

OFFLINE, stdlib-only. Üretim yalnız `{out}` yer tutucusuna ya da beyan
edilmiş çıktı yollarına yazar (ikisi de `.gitignore`'lu).
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]

# design_preview.html'in tek üreticisi (statik kapı da bunu çağırır).
BUILD_DESIGN_PREVIEW = HERE / "build_design_preview.py"


@dataclass(frozen=True)
class Surface:
    """Bu kapının ÜRETİP TARADIĞI yüzey."""

    id: str
    generator: Tuple[str, ...]      # argv; "{out}" yer tutucusu destekler
    cwd: pathlib.Path
    outputs: Tuple[str, ...]        # "{out}" ya da cwd'ye göreli yollar
    scan: str                       # SCANS anahtarı
    requires: Tuple[str, ...] = ()  # araç gereksinimleri (toolchain vb.)
    fast: bool = True               # pre-commit hızlı yolu
    note: str = ""


@dataclass(frozen=True)
class Classified:
    """Bu kapının yeniden üretmediği ama SINIFLANDIRDIĞI yüzey."""

    id: str
    kind: str                       # ci-step | runtime | toolchain
    paths: Tuple[str, ...]          # repo-göreli önekler (dizin ya da dosya)
    owner_file: str                 # üreticiyi içeren dosya (repo-göreli)
    owner_snippet: str              # o dosyada GEÇMEK ZORUNDA
    scan_file: str                  # tarayan kapı/test
    scan_snippet: str               # orada GEÇMEK ZORUNDA
    note: str = ""


# ── BUILD yüzeyleri ─────────────────────────────────────────────────────────
BUILD: Tuple[Surface, ...] = (
    Surface(
        id="design_preview_html",
        generator=(sys.executable, str(BUILD_DESIGN_PREVIEW), "{out}"),
        cwd=HERE,
        outputs=("{out}",),
        scan="design_preview",
        fast=True,
        note="frontend-design demo artifact'ı (CSP altında hover tooltip kanıtı "
             "ayrıca test_design_preview_hover_csp.py'de, tarayıcı tier'i)",
    ),
    Surface(
        id="video_player_bundle",
        generator=("npm", "run", "build:player:ci"),
        cwd=HERE.parent / "video",
        outputs=("dist/player.js", "dist/player.html", "dist/player.css",
                 "dist/leibniz.json"),
        scan="video_player_bundle",
        requires=("node", "npm", "_calisma/video/node_modules"),
        fast=False,
        note="LeibnizChain tarayıcı-içi oynatıcı; /video/* rotası bu çıktıyı "
             "servis eder, CSP notu player.html'de yazılı",
    ),
)

# ── SINIFLANDIRILMIŞ yüzeyler ───────────────────────────────────────────────
CLASSIFIED: Tuple[Classified, ...] = (
    Classified(
        id="dashboard_next_build",
        kind="ci-step",
        paths=("apps/dashboard-next/.next/",),
        owner_file=".github/workflows/verify.yml",
        owner_snippet="npm run build --prefix apps/dashboard-next",
        scan_file="_calisma/CIKTI/test_surface_cwv_report.py",
        scan_snippet=".next",
        note="next build çıktısı (BUILD_ID/build-manifest) tipcheck+build "
             "adımında üretilir; surface_cwv kapısı BUILD_ID'yi kimlik olarak "
             "kullanır",
    ),
    Classified(
        id="ci_log_sidecars",
        kind="ci-step",
        paths=("logs/",),
        owner_file=".github/workflows/verify.yml",
        owner_snippet="logs/k12_repro_manifest.json",
        scan_file="_calisma/CIKTI/test_m0_k12_sidecar_sync.py",
        scan_snippet="k12_repro_manifest.json",
        note="K12/K13 manifestleri ve kapı findings sidecar'ları (üretici = "
             "workflow adımı ya da kapının kendisi); test_m0_* sidecar'ı "
             "okur, yoksa SKIP — bu yüzden tarafı CI'da DOLU olmalı",
    ),
    Classified(
        id="summary_klayers_sidecar",
        kind="ci-step",
        paths=("_calisma/CIKTI/klayers.json",),
        owner_file="_calisma/CIKTI/verify_delivery.py",
        owner_snippet="--klayers-out",
        scan_file="_calisma/CIKTI/test_run_summary_klayers.py",
        scan_snippet="klayers.json",
        note="katman özeti sidecar'ı (verify_delivery --klayers-out / runtime "
             "dizini); consolidate_summary onu okur, preview panosu işaretleri "
             "buradan türetir — dört okuyucusu var, temiz klonda yoktur",
    ),
    Classified(
        id="preview_runtime_data",
        kind="runtime",
        paths=("_calisma/CIKTI/history.jsonl", "_calisma/CIKTI/runs/",
               "_calisma/CIKTI/logs/", "_calisma/CIKTI/trend_sync.json",
               "_calisma/CIKTI/a11y_report", "player_routes.json",
               "trend_sync.json"),
        owner_file="_calisma/CIKTI/preview_server.py",
        owner_snippet="persist_history",
        scan_file="_calisma/CIKTI/test_preview_runtime_isolation.py",
        scan_snippet="runtime",
        note="canlı sunucunun/sidecar üreticilerinin yazdığı çalışma-zamanı "
             "verisi (history, trend_sync, player_routes, a11y_*.json); testler "
             "fixture ya da geçici runtime-dir kullanır — temiz klonda yok "
             "olması BEKLENEN davranış",
    ),
    Classified(
        id="toolchain_trees",
        kind="toolchain",
        paths=("_calisma/pptx/node_modules/", "_calisma/docx/node_modules/",
               "_calisma/video/node_modules/", "apps/dashboard-next/node_modules/",
               "apps/trend-db/node_modules/"),
        owner_file="_calisma/dev_bootstrap.sh",
        owner_snippet="npm ci",
        scan_file="_calisma/CIKTI/test_check_bootstrap_toolchain.py",
        scan_snippet="node_modules",
        note="gitignored bağımlılık ağaçları; dev_bootstrap --check kurar, "
             "eksikse araç-kümesi kapısı kırmızı (sessiz SKIP değil)",
    ),
)

# ── araç gereksinimi ────────────────────────────────────────────────────────
def unmet_requirements(surface: Surface) -> List[str]:
    """Karşılanmayan araçlar; boş liste = üretime hazır."""
    missing: List[str] = []
    for req in surface.requires:
        if req in ("node", "npm"):
            if shutil.which(req) is None:
                missing.append(req)
        elif req.endswith("node_modules"):
            if not (REPO / req).is_dir():
                missing.append(req)
        else:
            if not (REPO / req).exists():
                missing.append(req)
    return missing


def _expand(surface: Surface, out: Optional[pathlib.Path]) -> List[str]:
    argv: List[str] = []
    for token in surface.generator:
        if token == "{out}":
            if out is None:
                raise ValueError("%s: {out} için hedef yol gerekli" % surface.id)
            argv.append(str(out))
        else:
            argv.append(str(token))
    return argv


def output_paths(surface: Surface, out: Optional[pathlib.Path]) -> Dict[str, pathlib.Path]:
    """Beyan edilen çıktıların gerçek yolları (göreli anahtar → mutlak yol)."""
    paths: Dict[str, pathlib.Path] = {}
    for spec in surface.outputs:
        if spec == "{out}":
            if out is None:
                raise ValueError("%s: {out} çıktısı için hedef gerekli"
                                 % surface.id)
            paths[out.name] = out
        else:
            paths[spec] = surface.cwd / spec
    return paths


def generate(surface: Surface, out: Optional[pathlib.Path] = None,
             timeout: int = 300) -> subprocess.CompletedProcess:
    """Üreticiyi koşar (çıktı yolları .gitignore'lu). Hata → kapı kırmızı."""
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        _expand(surface, out), cwd=str(surface.cwd), capture_output=True,
        text=True, timeout=timeout)


# ── tarayıcılar ─────────────────────────────────────────────────────────────
def _scan_design_preview(paths: Dict[str, pathlib.Path]) -> List[str]:
    import preview_inline_audit as audit

    path = next(iter(paths.values()))
    if not path.is_file():
        return ["design_preview.html üretilmedi: %s" % path]
    html = path.read_text(encoding="utf-8")
    problems: List[str] = []
    hits = audit.count_inline_handlers(html)
    if hits:
        problems.append("inline event-handler sayacı %d (CSP altında SESSİZ "
                        "ölür): %r" % (len(hits), hits[:6]))
    if len(html) < 50_000:
        problems.append("artifact beklenmedik derecede küçük: %d bayt"
                        % len(html))
    for needle in ("addEventListener", "data-tip", "<script"):
        if needle not in html:
            problems.append("artifact %r içermiyor — şablon değişmiş olabilir"
                            % needle)
    return problems


def _scan_video_player_bundle(paths: Dict[str, pathlib.Path]) -> List[str]:
    problems: List[str] = []
    for name, path in paths.items():
        if not path.is_file():
            problems.append("%s üretilmedi: %s" % (name, path))
        elif path.stat().st_size == 0:
            problems.append("%s BOŞ (0 bayt)" % name)
    if problems:
        return problems
    html = paths["dist/player.html"].read_text(encoding="utf-8")
    if "/video/player.js" not in html:
        problems.append("player.html oynatıcı script'ini referans etmiyor")
    if "<main" not in html:
        problems.append("player.html <main> landmark'ı taşımıyor "
                        "(a11y_gate /video.html'i tarar)")
    # CSP sözleşmesi: inline script YOK (nonce gerekmesin); harici dosya.
    inline = [tag for tag in html.split("<script")[1:]
              if "src=" not in tag.split(">", 1)[0]]
    if inline:
        problems.append("player.html inline <script> taşıyor (%d) — CSP "
                        "altında nonce gerekir" % len(inline))
    js = paths["dist/player.js"]
    if js.stat().st_size < 100_000:
        problems.append("dist/player.js beklenmedik derecede küçük: %d bayt"
                        % js.stat().st_size)
    try:
        data = json.loads(paths["dist/leibniz.json"].read_text(encoding="utf-8"))
    except ValueError as exc:
        problems.append("dist/leibniz.json çözülemedi: %s" % exc)
    else:
        missing = {"meta", "runs", "gates", "seal"} - set(data)
        if missing:
            problems.append("dist/leibniz.json alanları eksik: %s"
                            % sorted(missing))
    return problems


SCANS = {
    "design_preview": _scan_design_preview,
    "video_player_bundle": _scan_video_player_bundle,
}


def scan(surface: Surface, paths: Dict[str, pathlib.Path]) -> List[str]:
    fn = SCANS.get(surface.scan)
    if fn is None:
        return ["%s: bilinmeyen tarayıcı %r" % (surface.id, surface.scan)]
    return list(fn(paths))


# ── sınıflandırma doğrulaması ───────────────────────────────────────────────
def verify_classified(entry: Classified) -> List[str]:
    """Beyan edilen üretici/tarayıcı gerçekten var mı? (hayalet kayıt yasağı)"""
    problems: List[str] = []
    owner = REPO / entry.owner_file
    scan_file = REPO / entry.scan_file
    if not owner.is_file():
        problems.append("%s: üretici dosyası yok: %s" % (entry.id, entry.owner_file))
    elif entry.owner_snippet not in owner.read_text(encoding="utf-8", errors="replace"):
        problems.append("%s: üretici beyanı %r %s içinde YOK (hayalet kayıt)"
                        % (entry.id, entry.owner_snippet, entry.owner_file))
    if not scan_file.is_file():
        problems.append("%s: tarayıcı dosyası yok: %s" % (entry.id, entry.scan_file))
    elif entry.scan_snippet not in scan_file.read_text(encoding="utf-8", errors="replace"):
        problems.append("%s: tarayıcı beyanı %r %s içinde YOK (hayalet kayıt)"
                        % (entry.id, entry.scan_snippet, entry.scan_file))
    return problems


# ── kapsam denetimi (sınıf garantisi) ───────────────────────────────────────
# Bilinen gitignore'lu üretilmiş yüzey ADLARI (reporöreli yol taşımayan
# literaller): `HERE / "<ad>"` biçiminde kullanılırlar.
KNOWN_NAMES = ("design_preview.html", "history.jsonl", "player_routes.json",
               "trend_sync.json")

# Aile (glob) yüzeyleri: a11y_gate.py `a11y_<page>_<theme>.json` yazar, kök
# `.gitignore` `/a11y_*.json` ile kapatır — tek tek ad yazmak yerine aile öneki.
KNOWN_PREFIXES = ("a11y_",)

# Regex/şablon literal'leri: gerçek yol değil, desen (denetim dışı).
TEMPLATE_LITERALS = ("logs/[A-Za-z0-9_.-]+\\.json",)

_PREFIX = ("_calisma/", "logs/", "apps/", "docs/", "history.jsonl",
           "runs/", "dist/", ".next")


def classified_paths() -> List[str]:
    paths: List[str] = []
    for surface in BUILD:
        for spec in surface.outputs:
            paths.append(spec if spec != "{out}" else "design_preview.html")
    for entry in CLASSIFIED:
        paths.extend(entry.paths)
    return paths


def covers(path: str) -> bool:
    """Bu yol envanterde sınıflandırılmış mı?"""
    for surface in BUILD:
        for spec in surface.outputs:
            if spec == "{out}" and path.endswith("design_preview.html"):
                return True
            if spec == path:
                return True
    for entry in CLASSIFIED:
        for prefix in entry.paths:
            if path == prefix or path.startswith(prefix):
                return True
            if path.rstrip("/") == prefix.rstrip("/"):
                return True
    # Aile yüzeyleri (a11y_<page>_<theme>.json): önek tabanlı değil, AD
    # tabanlı eşleşme — "a11y_" öneki her yolu yutmasın. Takip edilen
    # `a11y_gate_config.json` aynı öneki paylaşır; kapsam iddiası yalnız
    # denetim içindir, dosya yine izlenir.
    base = path.rstrip("/").rsplit("/", 1)[-1]
    if base.endswith(".json") and base.startswith(KNOWN_PREFIXES):
        return True
    return False


_SUFFIX_RE = None


def _suffix_re():
    global _SUFFIX_RE
    if _SUFFIX_RE is None:
        import re

        _SUFFIX_RE = re.compile(r"\.(json|jsonl|html|js|png|pdf|log|yml|yaml|css|"
                                r"pptx|txt)$|/$")
    return _SUFFIX_RE


def _consider(value: str) -> bool:
    """Bir literal "yol adayı" mi? (boşluk/uzunluk/şablon/önek/sonek)."""
    value = value.strip()
    if not value or " " in value or len(value) > 120:
        return False
    if value in TEMPLATE_LITERALS:
        return False
    if value in KNOWN_NAMES:
        return True
    if value.endswith(".json") and value.startswith(KNOWN_PREFIXES):
        return True
    if not value.startswith(_PREFIX):
        return False
    return bool(_suffix_re().search(value))


def candidate_literals(text: str) -> List[str]:
    """Python kaynak metnindeki gitignore'lu olabilecek yol literalleri."""
    import ast

    out: List[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if _consider(node.value):
            out.append(node.value.strip())
    return out


def candidate_literals_js(text: str) -> List[str]:
    """JS kapı/test kaynaklarındaki yol literalleri (aynı filtre).

    Sınıf garantisi yalnız Python'u tararsa `.js` tarafındaki yeni bir
    üretilmiş yüzey görünmez kalırdı; tarama yüzeyi geniş tutulur.
    """
    import re

    out: List[str] = []
    for match in re.finditer(r"['\"`]([^'\"`\n]{3,120})['\"`]", text):
        value = match.group(1)
        if _consider(value):
            out.append(value.strip())
    return out


def _ignored_paths(repo_root: pathlib.Path,
                   probes: Sequence[str]) -> set:
    """`git check-ignore --stdin -z` TEK çağrıda: ölçülen kaynaklar.

    Literal başına ayrı süreç (~200 literal → ~4.9 s) yerine tek süreç;
    aynı soru, aynı yanıt (AGENTS.md: ölçüm gerçek yoldan yapılır).
    """
    import subprocess

    if not probes:
        return set()
    proc = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"],
        cwd=str(repo_root), input="\0".join(probes) + "\0",
        capture_output=True, text=True)
    if proc.returncode not in (0, 1):  # 0 = en az biri yok sayılı, 1 = hiçbiri
        raise RuntimeError("git check-ignore ölçülemedi (rc=%d): %s"
                           % (proc.returncode, proc.stderr.strip()[:300]))
    return {p for p in proc.stdout.split("\0") if p}


def audit_unclassified(repo_root: pathlib.Path = REPO) -> List[Tuple[str, str]]:
    """Sınıflandırılmamış gitignore'lu literaller: (yol, kaynak dosya)."""
    found: List[Tuple[str, str]] = []
    ci = repo_root / "_calisma" / "CIKTI"
    sources = sorted(ci.glob("*.py")) + sorted(ci.glob("*.js"))
    for path in sources:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        literals = (candidate_literals(text) if path.suffix == ".py"
                    else candidate_literals_js(text))
        for literal in literals:
            found.append((literal, path.name))
    if not found:
        return []
    ignored = _ignored_paths(repo_root,
                             [lit.rstrip("/") for lit, _ in found])
    problems: List[Tuple[str, str]] = []
    for literal, source in found:
        # izlenen ya da hiç var olmayan yol → bu sınıf değil
        if literal.rstrip("/") in ignored and not covers(literal):
            problems.append((literal, source))
    return problems
