#!/usr/bin/env python3
"""consolidate_patches.py — Recovery patch arşivlerini tekilleştir ve sadeleştir.

53 patch dosyasını 28 benzersiz SHA256'e benzer.
Her benzersiz patch'i tek bir kopya ile _calisma/CIKTI/recovery_patches_20260918/
dizinine konsolide eder; geri kalanı redundant olarak silinir.

Kullanım: python3 _calisma/CIKTI/consolidate_patches.py
--dry-run: sadece raporla, dosya değiştirme.
--source DIR: patch'lerin bulunduğu kök klasör (varsayılan: _calisma/CIKTI).
--target DIR: tekil patch'ler için hedef klasör (varsayılan: _calisma/CIKTI/recovery_patches_20260918).
"""

import hashlib
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    if dry_run:
        args = [a for a in args if a != "--dry-run"]

    source_dir = Path("_calisma/CIKTI")
    target_dir = Path("_calisma/CIKTI/recovery_patches_20260918")

    # Allow overriding via args
    i = 0
    while i < len(args):
        if args[i] == "--source" and i + 1 < len(args):
            source_dir = Path(args[i + 1])
            i += 2
        elif args[i] == "--target" and i + 1 < len(args):
            target_dir = Path(args[i + 1])
            i += 2
        else:
            i += 1

    # Collect all patch files across all recovery_patches_* directories
    all_patches = []  # list of (patch_path, sha256, filename)
    patch_by_sha = defaultdict(list)  # sha256 -> [patch_path, ...]

    for root, dirs, files in os.walk(source_dir):
        for f in files:
            if f.startswith("patch") and f.count("-") >= 1:
                patch_path = Path(root) / f
                try:
                    content = patch_path.read_bytes()
                    sha256 = hashlib.sha256(content).hexdigest()
                    all_patches.append((patch_path, sha256, f))
                    patch_by_sha[sha256].append((patch_path, f))
                except OSError:
                    continue

    print(f"Toplam patch dosyası: {len(all_patches)}")
    unique_shas = set(sha for _, sha, _ in all_patches)
    print(f"Benzersiz SHA256: {len(unique_shas)}")

    # Group by SHA256 and find the "original" (earliest by date in path)
    sha_groups = defaultdict(list)
    for patch_path, sha256, filename in all_patches:
        sha_groups[sha256].append((patch_path, filename))

    # For each unique SHA, keep the first one found (by sort order) and remove rest
    kept = 0
    removed = 0
    # Move/copy unique patches to target, remove duplicates from other dirs

    # First, ensure target directory exists and is clean
    if target_dir.exists():
        # Count what's already there
        existing = list(target_dir.glob("patch*"))
        print(f"Target klasördeki mevcut patch: {len(existing)}")

    for sha256, patches in sha_groups.items():
        if len(patches) == 1:
            # Only one copy, ensure it's in target
            patch_path, filename = patches[0]
            target_path = target_dir / filename
            if not target_path.exists() or dry_run:
                if dry_run:
                    print(f"  [DRY] Would ensure: {filename} (SHA: {sha256[:8]}...)")
                else:
                    shutil.copy2(str(patch_path), str(target_path))
                    print(f"  Copied: {filename} (SHA: {sha256[:8]}...)")
                kept += 1
            else:
                print(f"  Already present: {filename} (SHA: {sha256[:8]}...)")
                kept += 1
        else:
            # Multiple copies with same SHA - keep first, remove rest
            # Sort by path to have deterministic behavior
            patches.sort(key=lambda x: x[0])
            # Keep the first one
            keep_path, keep_name = patches[0]
            target_path = target_dir / keep_name
            if not target_path.exists() or dry_run:
                if dry_run:
                    print(f"  [DRY] Would keep: {keep_name} (SHA: {sha256[:8]}...)")
                    for p, n in patches[1:]:
                        print(f"    Would remove: {n}")
                else:
                    # Ensure target has the kept version
                    shutil.copy2(str(keep_path), str(target_path))
                    print(f"  Kept: {keep_name} (SHA: {sha256[:8]}...)")
                    # Remove duplicates from other directories
                    for dup_path, dup_name in patches[1:]:
                        try:
                            dup_path.unlink()
                            print(f"    Removed: {dup_name}")
                        except OSError:
                            print(f"    Could not remove: {dup_name}")
                kept += 1
                removed += len(patches) - 1

    print(f"\nÖzet: {kept} benzersiz patch tutuldu, {removed} redundant dosya {removed} removed")
    if dry_run:
        print("(--dry-run kaldırıldıysa gerçek değişiklikler yapıldı)")


if __name__ == "__main__":
    main()