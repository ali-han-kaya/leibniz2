#!/usr/bin/env python3
"""
gen_repro_manifest.py — reproducibility manifest üretici (tek kaynak).

GitHub Actions verify.yml'deki 'reproducibility' job'ının inline Python
mantığının standalone hali. Aynı kod hem CI'da hem yerelde (mock artifact'larla
simülasyon / doğrulama) çalışır → CI ile yerel arasında drift olmaz.

Çıktılar (--out-dir altına):
  manifest.txt    — insan-okur: FILE + SHA-256 tablosu
  manifest.json   — makine-okur: tool/generated/run/sha/ref/files{rel: sha256}
  + tüm artifact'ların kopyası (bundle)

Ortam değişkenleri (CI'da GitHub Actions set eder; yerelde override edilebilir):
  GITHUB_RUN_ID, GITHUB_SHA, GITHUB_REF, GITHUB_REPOSITORY, GITHUB_RUN_URL

Kullanım:
  python3 gen_repro_manifest.py --artifacts-dir all_artifacts --out-dir reproducibility
  GITHUB_RUN_ID=test-123 python3 gen_repro_manifest.py --artifacts-dir /tmp/mock ...
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import shutil


def sha256_file(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts-dir", default="all_artifacts",
                    help="artifact'ların bulunduğu dizin (CI'da download-artifact çıktısı)")
    ap.add_argument("--out-dir", default="reproducibility",
                    help="manifest + bundle çıktı dizini")
    args = ap.parse_args()

    run_id  = os.environ.get("GITHUB_RUN_ID", "local-sim")
    sha     = os.environ.get("GITHUB_SHA", "local-" + hashlib.sha256(b"mock").hexdigest()[:12])
    ref     = os.environ.get("GITHUB_REF", "refs/heads/local-sim")
    repo    = os.environ.get("GITHUB_REPOSITORY", "local/sim")
    run_url = os.environ.get("GITHUB_RUN_URL", f"https://example.local/runs/{run_id}")
    now     = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    root = pathlib.Path(args.artifacts_dir)
    if not root.is_dir():
        raise SystemExit(f"HATA: artifacts dizini yok: {root}")

    lines = [
        "=" * 72,
        "STOIC-HUME V5  —  REPRODUCIBILITY MANIFEST",
        f"generated: {now}",
        f"github_run_id: {run_id}",
        f"github_sha: {sha}",
        f"github_ref: {ref}",
        f"github_repository: {repo}",
        f"github_run_url: {run_url}",
        "=" * 72,
        "",
        f"{'FILE':<55} {'SHA-256'}",
        "-" * 72,
    ]

    file_hashes = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h = sha256_file(p)
            rel = str(p.relative_to(root))
            file_hashes[rel] = h
            lines.append(f"{rel:<55} {h}")

    lines += ["", "-" * 72, f"Total files: {len(file_hashes)}", ""]

    manifest_json = {
        "tool": "stoic-hume-v5-reproducibility",
        "generated": now,
        "github_run_id": run_id,
        "github_sha": sha,
        "github_ref": ref,
        "github_repository": repo,
        "github_run_url": run_url,
        "files": file_hashes,
    }

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)
    (out_dir / "manifest.txt").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest_json, indent=2, ensure_ascii=False), encoding="utf-8")

    # Artifact'ları bundle'a kopyala (manifest yanında)
    for child in root.iterdir():
        dest = out_dir / child.name
        if child.is_dir():
            shutil.copytree(child, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(child, dest)

    total_bytes = sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file())
    print(f"Manifest: {len(file_hashes)} files hashed, run_id={run_id}")
    print(f"Bundle size: {total_bytes} bytes")
    print(f"Output: {out_dir}/manifest.txt, {out_dir}/manifest.json")


if __name__ == "__main__":
    main()
