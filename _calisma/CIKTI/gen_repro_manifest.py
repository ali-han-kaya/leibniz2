#!/usr/bin/env python3
"""
gen_repro_manifest.py — reproducibility manifest üretici (tek kaynak).

GitHub Actions verify.yml'deki 'reproducibility' job'ının inline Python
mantığının standalone hali. Aynı kod hem CI'da hem yerelde (mock artifact'larla
simülasyon / doğrulama) çalışır → CI ile yerel arasında drift olmaz.

Çıktılar (--out-dir altına):
  manifest.txt    — insan-okur: FILE + SHA-256 tablosu + CONFIG bölümü
  manifest.json   — makine-okur: tool/generated/run/sha/ref/files{rel: sha256}
                    + config{files, combined_sha256}
  manifest.sha256 — manifest.json'un kendi SHA-256'sı (sha256sum formatı;
                    kurcalanma / yeniden üretim farkı tek hash ile denetlenir)
  + tüm artifact'ların kopyası (bundle)

CONFIG bölümü: artifacts-dir altındaki config/ önekiyle dosyalar ayrıca
hash'lenir (FILE tablosunda zaten var — bu ayrı bölüm denetlenebilirliği
artırır). combined_sha256 = tüm config dosyalarının (rel\0hash\n sıralı
birleşiminin) SHA-256'sı — deterministik, config'in hangi sürümünün
kullanıldığını tek hash ile özetler.

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


# Artifact → üreten job eşlemesi. verify.yml'deki her job'ın
# upload-artifact `name` alanının aynasıdır (TEK KAYNAK kuralı: bu tablo ile
# verify.yml birlikte değiştirilmelidir). merge-multiple indirmeleri
# artifact adını köke düzleştirdiği için bu eşleme, bir dosyanın hangi
# job'dan geldiğini denetlenebilir kılar. REPRO_ARTIFACT_JOBS env'i (JSON)
# geçersiz kılma sağlar.
ARTIFACT_JOBS = {
    "verify-report": "verify",
    "budget-verify": "verify",
    "config": "verify",
    "k0-findings": "verify",
    "refs-online": "verify",
    "run-history": "verify",
    "precommit-logs": "verify",
    "budget": "budget",
    "reports": "reports",
    "config-drift": "config-drift",
    "repack-verify": "repack-verify",
    "reproducibility": "reproducibility",
}


def _load_artifact_jobs() -> dict:
    """ARTIFACT_JOBS'ı env override ile birleştir (REPRO_ARTIFACT_JOBS JSON)."""
    jobs = dict(ARTIFACT_JOBS)
    raw = os.environ.get("REPRO_ARTIFACT_JOBS")
    if raw:
        try:
            override = json.loads(raw)
        except json.JSONDecodeError:
            return jobs
        if isinstance(override, dict):
            jobs.update(override)
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts-dir", default="all_artifacts",
                    help="artifact'ların bulunduğu dizin (CI'da download-artifact çıktısı)")
    ap.add_argument("--out-dir", default="reproducibility",
                    help="manifest + bundle çıktı dizini")
    args = ap.parse_args()
    artifact_jobs = _load_artifact_jobs()

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

    # ── CONFIG bölümü: config/ önekli dosyalar ayrıca işaretlenir ──────────
    config_hashes = {rel: h for rel, h in file_hashes.items()
                     if rel.startswith("config/")}
    config_combined = None
    if config_hashes:
        sorted_rel = sorted(config_hashes)
        config_combined = hashlib.sha256(
            "".join(f"{rel}\0{config_hashes[rel]}\n" for rel in sorted_rel).encode()
        ).hexdigest()
        cfg_block = [
            "",
            "=" * 72,
            "CONFIG ARTIFACT (ayrı bölüm)",
            "=" * 72,
            f"{'FILE':<55} {'SHA-256'}",
            "-" * 72,
        ]
        cfg_block += [f"{rel:<55} {config_hashes[rel]}" for rel in sorted_rel]
        cfg_block += ["-" * 72,
                      f"config_combined_sha256: {config_combined}",
                      "=" * 72]
        lines += cfg_block

    # ── PROVENANCE bölümü: artifact → üreten job (denetim izi) ──────────────
    # Her artifact hangi job'da üretildi — tek bakışta kaynak. Prefixed
    # indirilenler (config/, precommit-logs/) bundle'da kendi adı altındadır;
    # merge ile indirilenler köke düzleştiği için yalnızca eşleme üzerinden
    # işaretlenir (dosya bazlı değil, artifact bazlı).
    present = {}
    for rel in file_hashes:
        top = rel.split("/", 1)[0]
        if top in artifact_jobs:
            present.setdefault(top, []).append(rel)
    prov_block = [
        "",
        "=" * 72,
        "PROVENANCE (artifact → job kaynağı)",
        "=" * 72,
        f"{'ARTIFACT':<20} {'JOB':<22} BUNDLE",
        "-" * 72,
    ]
    for art in sorted(artifact_jobs):
        job = artifact_jobs[art]
        files = present.get(art)
        if files:
            note = f"prefixed ({len(files)} dosya)"
        elif art in ("config", "precommit-logs"):
            note = "YOK (indirilmedi)"
        else:
            note = "merge (köke düzleştirildi)"
        prov_block.append(f"{art:<20} {job:<22} {note}")
    prov_block.append("=" * 72)
    lines += prov_block

    manifest_json = {
        "tool": "stoic-hume-v5-reproducibility",
        "generated": now,
        "github_run_id": run_id,
        "github_sha": sha,
        "github_ref": ref,
        "github_repository": repo,
        "github_run_url": run_url,
        "files": file_hashes,
        "provenance": {"artifact_jobs": dict(sorted(artifact_jobs.items()))},
    }
    if config_hashes:
        manifest_json["config"] = {
            "files": dict(sorted(config_hashes.items())),
            "combined_sha256": config_combined,
        }

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)
    (out_dir / "manifest.txt").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest_json, indent=2, ensure_ascii=False), encoding="utf-8")

    # manifest.json'un kendi SHA-256'sı — sidecar (sha256sum formatı).
    # manifest.json içeriği değişirse sidecar artık eşleşmez; böylece
    # manifest'in kendisi (dosya hash'lerinin listesi) tek hash ile denetlenir.
    manifest_sha = sha256_file(out_dir / "manifest.json")
    (out_dir / "manifest.sha256").write_text(
        f"{manifest_sha}  manifest.json\n", encoding="utf-8")

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
    print(f"Output: {out_dir}/manifest.txt, {out_dir}/manifest.json, "
          f"{out_dir}/manifest.sha256")


if __name__ == "__main__":
    main()
