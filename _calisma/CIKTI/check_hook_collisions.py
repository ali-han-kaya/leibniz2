#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_hook_collisions.py — yazan hook ↔ unstaged delta çakışma kapısı.

SORUN (ölçüldü, AGENTS.md)
--------------------------
Zincirdeki üç hook dosyayı YENİDEN YAZAR ve `git add` eder:
`update-config`, `check-changelog-sync`, `check-skills-index`. Aynı dosyada
UNSTAGED bir düzenleme varsa `git commit` şu sırayı izler:

  1) pre-commit unstaged deltayı `~/.cache/pre-commit/patch<epoch>-<pid>`
     dosyasına stash'ler ve ağacı INDEX'e eşitler,
  2) yazan hook dosyayı ESKİ (stage'li) hâliyle okur, üzerine YAZAR ve
     `git add` eder,
  3) pre-commit `finally` içinde patch'i `git apply` ile geri koymaya çalışır
     → çakışır; süreç pencere içinde ölürse delta yalnız cache'te kalır.

Sonuç: kullanıcının unstaged düzenlemesi sessizce düşer ve hata ancak
zincirin sonunda görünür. Bu kapı o sınıfı zincirin BAŞINDA, hiçbir hook
yazmadan, dosya→hook eşleşmesiyle adıyla söyler (fail-fast).

KAPSAM (bilinçli, çakışma sınıfı)
---------------------------------
Yalnız YAZAN hook'ların hedef dosyaları ölçülür; hedef-dışı unstaged deltayı
`check-unstaged-delta` kapısı (hemen ardından) zaten bloke eder. İki kapı
birbirinin yerine geçmez: bu kapı TEŞHİS eder ("hangi hook bu dosyayı
ezer"), ikincisi GENEL kuralı uygular. Sıra bu yüzdendir: çakışma varsa
ilk, en açıklayıcı hata görünür.

ÖLÇÜMÜ TEKRAR İCAT ETMEZ
-------------------------
* Delta: `check_unstaged_delta.unstaged_files()` — `git diff --name-only` ∪
  bu koşumun ata-pid'li stash patch'i (pencere içinde `git diff` BOŞ döner).
* Hook kümesi: `.pre-commit-config.yaml` (`check_precommit_inventory`'nin
  stdlib ayrıştırıcısı) — PyYAML bağımlılığı yok.

FAIL-CLOSED (sessiz PASS yok)
-----------------------------
* Yardımcı modül import edilemez / config okunamaz / `repos:` yoksa → exit 2
  ("ÖLÇÜLEMEDİ"); kapı ölçemediği şeyi yeşil saymaz.
* Kayıttaki bir hook id config'te YOKSA ya da hedef dosya İZLENMİYORSA →
  exit 2 ("registry bayat"): yazan küme yeniden adlandırılmışsa kapı kör
  kalmasın (hayalet kayıt = fail-open ailesi).

YAZMAZ: bu kapı hiçbir dosyaya dokunmaz, hiçbir şeyi stage etmez.

Exit: 0 = çakışma yok, 1 = çakışma (bloke), 2 = ölçüm/registry/kullanım
hatası. `--json` makine-okunur çıktı verir. OFFLINE, stdlib-only, ~0.1s.
"""
import argparse
import json
import pathlib
import subprocess
import sys
from typing import Dict, Iterable, List, Sequence, Tuple

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
DEFAULT_CONFIG = REPO / ".pre-commit-config.yaml"

# ────────────────────────────────────────────────────────────────────────────
# YAZAN HOOK KÜMESİ — .pre-commit-config.yaml başlığındaki sözleşmeyle aynı
# üç hook. Değer: (hedef yollar, ne yazdığı). Yeni bir yazan hook eklenirse
# BURAYA da eklenmeli; registry bayatsa kapı exit 2 verir (sessiz kapsam
# kaybı yok).
# ────────────────────────────────────────────────────────────────────────────
WRITERS: Dict[str, Tuple[Tuple[str, ...], str]] = {
    "update-config": (
        ("_calisma/CIKTI/verify_delivery.config.json",),
        "gen_config.py (expected_pages/refs/manifest)",
    ),
    "check-changelog-sync": (
        ("README.md", "docs/PUBLISH_SCENARIO.md"),
        "gen_changelog.py --prune (changelog tabloları)",
    ),
    "check-skills-index": (
        ("README.md",),
        "sync_skills_index.py --update (skills tablosu)",
    ),
}


def _delta_mod():
    """Delta ölçümü TEK KAYNAKTAN: check_unstaged_delta (import hatası → çağıran 2)."""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import check_unstaged_delta  # noqa: E402 — yol enjekte edildikten sonra

    return check_unstaged_delta


def config_hook_ids(config_path: pathlib.Path) -> List[str]:
    """Config'teki hook id'leri (stdlib ayrıştırıcı, tek kaynak)."""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import check_precommit_inventory  # noqa: E402

    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("config okunamadı: %s (%s)" % (config_path, exc))
    ids = check_precommit_inventory.config_hook_ids(text)
    if not ids:
        raise RuntimeError("`repos:` bölümü veya hook id'si yok: %s" % config_path)
    return ids


def tracked_paths(paths: Sequence[str]) -> set:
    """İZLENEN yollar (git ls-files). Ölçüm imkânsızsa RuntimeError."""
    if not paths:
        return set()
    try:
        res = subprocess.run(
            ["git", "ls-files", "-z", "--", *paths],
            capture_output=True, text=True, check=False,
        )
    except OSError as exc:
        raise RuntimeError("git ls-files çalışmadı (%s)" % exc)
    if res.returncode != 0:
        raise RuntimeError("git ls-files rc=%d: %s"
                           % (res.returncode, (res.stderr or "").strip()[:200]))
    return {p for p in res.stdout.split("\0") if p}


def target_map() -> Dict[str, List[Tuple[str, str]]]:
    """ters indeks: hedef dosya → [(hook id, ne yazdığı)] (sıra deterministik)."""
    out: Dict[str, List[Tuple[str, str]]] = {}
    for hook in sorted(WRITERS):
        paths, what = WRITERS[hook]
        for rel in paths:
            out.setdefault(rel, []).append((hook, what))
    return out


def collisions(files: Iterable[str]) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """Unstaged dosyalarla yazan-hook hedeflerinin kesişimi (saf fonksiyon)."""
    targets = target_map()
    hit = []
    for rel in files:
        hooks = targets.get(rel)
        if hooks:
            hit.append((rel, hooks))
    return sorted(hit, key=lambda row: row[0])


def validate_registry(config_path: pathlib.Path) -> List[str]:
    """Registry ↔ config ↔ index tutarlılığı; sorun listesi (boş = sağlıklı)."""
    problems: List[str] = []
    if not WRITERS:
        problems.append("yazan hook kümesi boş — kapı körleşti")
        return problems
    try:
        ids = set(config_hook_ids(config_path))
    except RuntimeError as exc:
        return ["%s" % exc]
    for hook in sorted(WRITERS):
        if hook not in ids:
            problems.append("registry bayat: `%s` config'te yok" % hook)
    all_paths = [rel for paths, _ in WRITERS.values() for rel in paths]
    try:
        tracked = tracked_paths(all_paths)
    except RuntimeError as exc:
        return ["%s" % exc]
    for rel in sorted(set(all_paths)):
        if rel not in tracked:
            problems.append("registry bayat: `%s` izlenen dosya değil" % rel)
    return problems


def run(config_path: pathlib.Path = DEFAULT_CONFIG) -> Tuple[int, dict]:
    """Ölçüm. Döner (rc, report). rc 0/1/2 — sözleşme modül başlığında."""
    report = {
        "config_path": str(config_path),
        "writers": {k: list(v[0]) for k, v in WRITERS.items()},
        "unstaged": [],
        "signals": [],
        "collisions": [],
        "problems": [],
        "ok": False,
    }
    problems = validate_registry(config_path)
    report["problems"] = problems
    if problems:
        return 2, report

    try:
        delta = _delta_mod()
        files, signals = delta.unstaged_files()
    except Exception as exc:  # import/ölçüm imkânsız → fail-closed
        report["problems"] = ["delta ölçümü ÖLÇÜLEMEDİ: %r" % (exc,)]
        return 2, report

    report["unstaged"] = list(files)
    report["signals"] = list(signals)
    hits = collisions(files)
    report["collisions"] = [
        {"path": rel, "hooks": [{"id": h, "writes": w} for h, w in hooks]}
        for rel, hooks in hits
    ]
    report["ok"] = not hits
    return (1 if hits else 0), report


def render(report: dict) -> List[str]:
    """İnsan-okunur çıktı (stdout)."""
    lines: List[str] = []
    if report["problems"]:
        lines.append("HOOK ÇAKIŞMA KAPISI ÖLÇÜLEMEDİ — fail-closed (sessiz PASS yok).")
        for problem in report["problems"]:
            lines.append("  %s" % problem)
        lines.append("  çözüm: `check_hook_collisions.WRITERS` ile "
                     ".pre-commit-config.yaml/index'i hizalayın.")
        return lines

    if not report["collisions"]:
        hooks = len(report["writers"])
        paths = len({rel for paths_, _ in WRITERS.values() for rel in paths_})
        lines.append("OK — yazan hook hedeflerinde unstaged delta yok "
                     "(%d hook, %d hedef dosya izlendi)" % (hooks, paths))
        return lines

    lines.append("HOOK ÇAKIŞMASI — commit bloke (fail-fast; hiçbir hook henüz koşmadı).")
    for row in report["collisions"]:
        lines.append("  %s" % row["path"])
        for hook in row["hooks"]:
            lines.append("    ← %s: %s" % (hook["id"], hook["writes"]))
    lines.append("  sinyal: %s" % (", ".join(report["signals"]) or "?"))
    lines.append(
        "\nNeden bloke: bu dosyalarda UNSTAGED düzenleme var ve listelenen\n"
        "hook(lar) dosyayı YENİDEN YAZAR. pre-commit pencere içinde ağacı\n"
        "index'e eşitler: hook dosyayı ESKİ (stage'li) hâliyle okur, üzerine\n"
        "yazar ve `git add` eder — unstaged düzenleme sessizce düşer\n"
        "(AGENTS.md: auto-editing hook ↔ stash reapply çakışması).\n"
        "\nÇözüm (biri):"
    )
    for row in report["collisions"]:
        lines.append("  git add %s" % row["path"])
    lines.append("  ya da")
    for row in report["collisions"]:
        lines.append("  git stash push -m wip -- %s" % row["path"])
    lines.append("sonra commit'i yeniden dene. Bu kapı hiçbir dosya YAZMADI.")
    return lines


def main(argv: Sequence[str] = None) -> int:  # type: ignore[assignment]
    ap = argparse.ArgumentParser(
        description="Yazan pre-commit hook'ları ile unstaged delta çakışmasını "
                    "zincirin başında bloke eder (fail-closed).")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG),
                    help="pre-commit config yolu")
    ap.add_argument("--json", action="store_true", help="makine-okunur JSON")
    args = ap.parse_args(argv)

    rc, report = run(pathlib.Path(args.config))
    if args.json:
        payload = dict(report)
        payload["rc"] = rc
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in render(report):
            print(line)
    return rc


if __name__ == "__main__":
    sys.exit(main())
