#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_build_artifact_overwrite.py — build kapısı: izlenen (tracked) teslim
artefaktının üzerine YEREL BİR BUILD tarafından yazılmasını fail-closed engeller.

Neden: `docs/Makefile.texlive pdf` ve `docs/Makefile.tectonic pdf` çıktıyı
BUILD_DIR'da üretip kanonik OUTPUT'a kopyalar. OUTPUT yanlışlıkla (ya da eski
bir alışkanlıkla) izlenen teslim PDF'i ise, tek bir `make pdf` gönderilmiş
dosyayı sessizce değiştirir; sidecar/ledger/repack güncellenmediği için
K2/K6/K14 kapıları sonradan ve BAŞKA bir hata gibi kırmızıya düşer. Bu kapı
o yazmayı build anında, kaynağında durdurur.

Sözleşme
  * Korumalı küme = `_calisma/` altında izlenen ve `.pdf`, `.zip`, `.sha256`
    ile biten yollar (git ls-files; untracked build çıktısı serbesttir).
    `.sha256` kapsamı zip sidecar'larını, `*.pdf.sha256` review sidecar'ını ve
    `*.pdf.metadata.sha256` metadata sidecar'ını birlikte korur.
  * `--snapshot PATH`  : build'den ÖNCE izlenen artefaktların sha256 kaydı.
  * `--verify PATH`    : build'den SONRA karşılaştır; izin verilmeyen her
    değişiklik/silinme → exit 1. `--allow PATH` yalnız AÇIKÇA bildirilen
    çıktıyı (dosya ya da dizin öneki) muaf tutar ve yine de uyarı basar;
    yollar repo-köklü (veya mutlak) verilir.
  * `--check-target PATH` : PRE-FLIGHT — build'in yazacağı hedef izlenen bir
    teslim artefaktıysa ve `--allow` verilmediyse build BAŞLAMADAN exit 1.
    Snapshot/verify ikinci katmandır; bu, gönderilmiş dosyanın hiç
    kirlenmemesini sağlar (boşa derleme de yapılmaz).
  * `--check`          : snapshot'sız, sonradan denetim — çalışma ağacındaki
    korumalı artefakt index'ten farklıysa (yani üzerine yazılmış ama henüz
    commit edilmemişse) exit 1. Bilinçli re-baseline staged ise temiz geçer.
  * `--list`           : korumalı kümeyi yazdır (denetim/teşhis).

Exit: 0 temiz, 1 drift (fail-closed), 2 ölçüm imkânsız (git yok, snapshot
bozuk, dosya okunamıyor, korumalı küme boş). Ölçüm hatası ASLA sessiz PASS
değildir; boş kapsam da sessiz no-op kapı olurdu, o yüzden hatadır.

Kullanım (Makefile'dan):
  python3 check_build_artifact_overwrite.py --repo . --snapshot snap.json
  python3 check_build_artifact_overwrite.py --repo . --verify snap.json \
      [--allow OUTPUT]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

SNAPSHOT_VERSION = 1
PROTECTED_PREFIX = "_calisma/"
PROTECTED_SUFFIXES = (".pdf", ".zip", ".sha256")
_CHUNK = 1 << 20
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

# Rapor okunabilirliği: testler bu etiketlere bağlanır.
TAG_FAIL = "FAIL"
TAG_OK = "OK"
TAG_ALLOW = "ALLOW"
TAG_WARN = "WARN"


class MeasurementError(RuntimeError):
    """Ölçüm imkânsız (exit 2) — sessiz PASS'a dönüşemez."""


def _git(root: pathlib.Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:  # pragma: no cover — git'siz ortam
        raise MeasurementError(f"git bulunamadı: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise MeasurementError(
            f"git {' '.join(args)} başarısız (rc={proc.returncode}): {detail}"
        )
    return proc.stdout


def resolve_repo(value: str | None) -> pathlib.Path:
    """--repo (veya cwd) → git çalışma ağacı kökü."""
    base = pathlib.Path(value or ".").resolve()
    if not base.is_dir():
        raise MeasurementError(f"repo dizini yok: {base}")
    out = _git(base, "rev-parse", "--show-toplevel")
    root = out.decode("utf-8", "surrogateescape").strip()
    if not root:
        raise MeasurementError(f"git kökü belirlenemedi: {base}")
    return pathlib.Path(root)


def is_protected(rel: str) -> bool:
    return rel.startswith(PROTECTED_PREFIX) and rel.lower().endswith(
        PROTECTED_SUFFIXES
    )


def protected_relpaths(root: pathlib.Path) -> list[str]:
    """İzlenen korumalı yollar — git ls-files (dosya sistemi taraması DEĞİL)."""
    raw = _git(root, "ls-files", "-z", "--", PROTECTED_PREFIX.rstrip("/"))
    paths = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        rel = item.decode("utf-8", "surrogateescape")
        if is_protected(rel):
            paths.append(rel)
    return sorted(set(paths))


def _digest(root: pathlib.Path, rel: str) -> tuple[str | None, int | None]:
    """sha256 + boyut; dosya yoksa (None, None). Okunamama = MeasurementError."""
    path = root / rel
    try:
        with path.open("rb") as fh:
            size = os.fstat(fh.fileno()).st_size
            digest = hashlib.sha256()
            for chunk in iter(lambda: fh.read(_CHUNK), b""):
                digest.update(chunk)
        return digest.hexdigest(), size
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        raise MeasurementError(f"korumalı dosya okunamadı: {rel}: {exc}") from exc


def _require_scope(root: pathlib.Path) -> list[str]:
    """Korumalı küme boşsa kapı sessiz no-op olur — fail-closed ölçüm hatası."""
    paths = protected_relpaths(root)
    if not paths:
        raise MeasurementError(
            f"korumalı artefakt bulunamadı ({PROTECTED_PREFIX} + "
            f"{', '.join(PROTECTED_SUFFIXES)}) — kapsam yanlış yapılandırılmış; "
            "sessiz PASS yok"
        )
    return paths


def write_snapshot(root: pathlib.Path, snapshot_path: pathlib.Path) -> int:
    artifacts: dict[str, dict[str, object]] = {}
    for rel in _require_scope(root):
        sha, size = _digest(root, rel)
        artifacts[rel] = {"sha256": sha, "size": size}
    payload = {
        "version": SNAPSHOT_VERSION,
        "artifacts": artifacts,
    }
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = snapshot_path.with_name(snapshot_path.name + ".tmp")
    # Atomik yazma: yarı yazılmış snapshot bir sonraki adımda "bozuk" diye
    # okunup ölçüm hatasına düşmesin (fail-closed yine de, ama gürültüsüz).
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, snapshot_path)
    print(f"{TAG_OK}: snapshot {len(artifacts)} izlenen teslim artefaktı → {snapshot_path}")
    return 0


def load_snapshot(snapshot_path: pathlib.Path) -> dict[str, dict[str, object]]:
    try:
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MeasurementError(
            f"snapshot yok: {snapshot_path} — build'den ÖNCE --snapshot koşmalı"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise MeasurementError(f"snapshot okunamadı/bozuk: {snapshot_path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != SNAPSHOT_VERSION:
        raise MeasurementError(
            f"snapshot sürümü desteklenmiyor (beklenen {SNAPSHOT_VERSION}): {snapshot_path}"
        )
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        raise MeasurementError(f"snapshot 'artifacts' eşlemesi değil: {snapshot_path}")
    for rel, entry in artifacts.items():
        if not isinstance(rel, str) or not isinstance(entry, dict):
            raise MeasurementError(f"snapshot kaydı bozuk: {rel!r}")
        sha = entry.get("sha256")
        size = entry.get("size")
        if sha is not None and not (isinstance(sha, str) and _SHA_RE.match(sha)):
            raise MeasurementError(f"snapshot sha256 geçersiz: {rel}")
        if size is not None and not (
            isinstance(size, int) and not isinstance(size, bool) and size >= 0
        ):
            raise MeasurementError(f"snapshot boyut geçersiz: {rel}")
        if (sha is None) != (size is None):
            raise MeasurementError(f"snapshot sha256/boyut tutarsız: {rel}")
    return artifacts


def _normalize(root: pathlib.Path, value: str) -> str:
    path = pathlib.Path(value)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(root.resolve())
        except ValueError:
            # Kök dışındaki bir yol asla korumalı kümeyle eşleşmez; yine de
            # sessizce yutma — normalize edilmiş hâlini tut.
            return str(path)
    rel = path.as_posix()
    while rel.startswith("./"):
        rel = rel[2:]
    rel = os.path.normpath(rel)
    if rel == ".":
        return ""
    return rel.rstrip("/")


def _is_allowed(rel: str, allowed: list[str]) -> bool:
    for item in allowed:
        if rel == item or rel.startswith(item + "/"):
            return True
    return False


def _describe(rel: str, old: dict[str, object], new_sha: str | None, new_size: int | None) -> str:
    old_sha = old.get("sha256")
    old_size = old.get("size")
    if new_sha is None:
        return f"  {rel}\n    SİLİNDİ (snapshot: {old_sha[:12]}…, {old_size} B)"
    if old_sha is None:
        return f"  {rel}\n    YENİ OLUŞTU (snapshot: yok) → {new_sha[:12]}…, {new_size} B"
    return (
        f"  {rel}\n"
        f"    {old_sha[:12]}… ({old_size} B) → {new_sha[:12]}… ({new_size} B)"
    )


def _remedy(trigger: str) -> str:
    return (
        f"{TAG_FAIL}: {trigger}\n"
        "  Build'in yazdığı çıktıyı at (izlenen hâle dön):\n"
        "    git checkout -- <path>\n"
        "  Bilinçli yeniden üretim (re-baseline) AÇIKÇA bildirilmeli:\n"
        "    make -f docs/Makefile.texlive pdf OVERWRITE=1   # veya tectonic ikizi\n"
        "  Ardından sha256 sidecar'ı / kabul defterini / repack'i güncelle;\n"
        "  aksi halde K2/K6/K14 kapıları bayat hash ile kırmızıya düşer."
    )


def check_target(root: pathlib.Path, targets: list[str], allow: list[str]) -> int:
    """Build ÖNCESİ: yazılacak hedef izlenen teslim artefaktı mı?"""
    _require_scope(root)
    allowed = [_normalize(root, a) for a in allow]
    blocked: list[str] = []
    for value in targets:
        rel = _normalize(root, value)
        if not rel or rel == ".":
            raise MeasurementError(f"--check-target geçersiz yol: {value!r}")
        if not is_protected(rel):
            print(f"{TAG_OK}: hedef kapsam dışı (izlenen teslim artefaktı değil): {rel}")
            continue
        raw = _git(root, "ls-files", "-z", "--", rel)
        tracked = rel in {
            item.decode("utf-8", "surrogateescape")
            for item in raw.split(b"\0")
            if item
        }
        if not tracked:
            print(f"{TAG_OK}: hedef izlenmiyor (untracked build çıktısı): {rel}")
            continue
        if _is_allowed(rel, allowed):
            print(f"{TAG_ALLOW}: hedef izlenen artefakt ama --allow ile AÇIKÇA izinli: {rel}")
            print("  → re-baseline sonrası sha256 sidecar / kabul defteri / repack güncellenmeli")
            continue
        blocked.append(rel)
    if blocked:
        print(f"{TAG_FAIL}: build hedefi izlenen teslim artefaktı (yazma engellendi):")
        for rel in blocked:
            print(f"  {rel}")
        print(_remedy(
            "build OUTPUT'u izlenen teslim artefaktı; gönderilmiş dosya "
            "korunuyor (fail-closed, build hiç başlamadı)."
        ))
        return 1
    print(f"{TAG_OK}: build hedefi güvenli ({len(targets)} yol denetlendi)")
    return 0


def verify(
    root: pathlib.Path,
    snapshot_path: pathlib.Path,
    allow: list[str],
) -> int:
    artifacts = load_snapshot(snapshot_path)
    allowed = [_normalize(root, a) for a in allow]
    drift: list[str] = []
    allowed_hits: list[str] = []
    for rel in sorted(artifacts):
        old = artifacts[rel]
        new_sha, new_size = _digest(root, rel)
        if new_sha == old.get("sha256") and new_size == old.get("size"):
            continue
        line = _describe(rel, old, new_sha, new_size)
        if _is_allowed(rel, allowed):
            allowed_hits.append(line)
        else:
            drift.append(line)
    for line in allowed_hits:
        print(f"{TAG_ALLOW}: bilinçli izin (--allow) kapsamında değişti:\n{line}")
    if allowed_hits:
        print("  → re-baseline sonrası sha256 sidecar / kabul defteri / repack güncellenmeli")
    if drift:
        print(f"{TAG_FAIL}: build sırasında izlenen teslim artefaktı değişti:")
        for line in drift:
            print(line)
        print(_remedy("izlenen artefakt build tarafından ezildi/silindi (fail-closed)."))
        return 1
    print(
        f"{TAG_OK}: {len(artifacts)} izlenen teslim artefaktı build boyunca korundu"
        + (f" ({len(allowed_hits)} bilinçli izin)" if allowed_hits else "")
    )
    return 0


def check_worktree(root: pathlib.Path) -> int:
    """Çalışma ağacı ↔ index karşılaştırması (snapshot gerektirmez)."""
    total = len(_require_scope(root))
    raw = _git(
        root,
        "diff",
        "--name-only",
        "-z",
        "--no-ext-diff",
        "--",
        PROTECTED_PREFIX.rstrip("/"),
    )
    changed = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        rel = item.decode("utf-8", "surrogateescape")
        if is_protected(rel):
            changed.append(rel)
    changed = sorted(set(changed))
    if changed:
        print(
            f"{TAG_FAIL}: çalışma ağacında izlenen teslim artefaktı index'ten farklı "
            "(üzerine yazılmış olabilir):"
        )
        for rel in changed:
            print(f"  {rel}")
        print(
            _remedy(
                "izlenen artefakt yerel build tarafından değiştirildi "
                "(worktree ≠ index; fail-closed)."
            )
        )
        return 1
    print(f"{TAG_OK}: {total} izlenen teslim artefaktı index ile birebir")
    return 0


def list_protected(root: pathlib.Path) -> int:
    paths = _require_scope(root)
    for rel in paths:
        print(rel)
    print(f"# {len(paths)} izlenen teslim artefaktı ({PROTECTED_PREFIX}, "
          f"{', '.join(PROTECTED_SUFFIXES)})", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="İzlenen teslim artefaktlarının build tarafından ezilmesini engelle."
    )
    parser.add_argument("--repo", default=".", help="git çalışma ağacı (varsayılan: cwd)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--snapshot", metavar="PATH", help="build ÖNCESİ sha256 kaydı yaz")
    mode.add_argument("--verify", metavar="PATH", help="snapshot'a göre build SONRASI denetle")
    mode.add_argument(
        "--check-target",
        metavar="PATH",
        action="append",
        help="build ÖNCESİ: yazılacak hedef izlenen artefakt mı? (tekrarlanabilir)",
    )
    mode.add_argument("--check", action="store_true", help="worktree ↔ index denetimi")
    mode.add_argument("--list", action="store_true", help="korumalı kümeyi yazdır")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="PATH",
        help="--verify için bilinçli izin (dosya veya dizin öneki; tekrarlanabilir)",
    )
    args = parser.parse_args(argv)

    if args.allow and not (args.verify or args.check_target):
        parser.error("--allow yalnız --verify / --check-target ile kullanılır")

    try:
        root = resolve_repo(args.repo)
        if args.snapshot:
            return write_snapshot(root, pathlib.Path(args.snapshot).resolve())
        if args.verify:
            return verify(root, pathlib.Path(args.verify).resolve(), args.allow)
        if args.check_target:
            return check_target(root, args.check_target, args.allow)
        if args.check:
            return check_worktree(root)
        return list_protected(root)
    except MeasurementError as exc:
        print(f"{TAG_FAIL}: ölçüm imkânsız — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
