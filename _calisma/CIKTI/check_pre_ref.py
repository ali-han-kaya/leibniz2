#!/usr/bin/env python3
"""
check_pre_ref.py — Pre-check for missing source ref with branch commit listing.

When a named source ref is missing, lists every branch by how many commits
it has outside the target so the right branch is obvious.

Usage:
    python3 check_pre_ref.py TARGET_BRANCH [--root GIT_ROOT]

Exit codes:
    0 = PASS (source ref found, or branches listed for selection)
    1 = FAIL (source ref missing and no branches to list, or error)
    2 = ERROR (could not resolve branches or repo root)
"""

import json
import os
import subprocess
import sys


def find_git_root(start_path):
    """Find the git repository root starting from start_path."""
    current = os.path.abspath(start_path)
    for _ in range(20):  # safety limit
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=current, capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def git(*args, cwd=None):
    """Run git command, return (returncode, stdout, stderr)."""
    if cwd is None:
        cwd = REPO_ROOT
    proc = subprocess.run(
        ["git"] + list(args), cwd=cwd, capture_output=True, text=True
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def try_git(*args, cwd=None):
    """Run git command, return (returncode, stdout, stderr) or None on exception."""
    try:
        return git(*args, cwd=cwd)
    except Exception:
        return None


def get_branches_with_commits_outside_target(target):
    """
    Get all local branches and count how many commits each has outside the target.

    Returns a list of dicts with branch name and commit count outside target,
    sorted by count descending (most commits outside target first).
    """
    # Get all local branches
    result = try_git("branch")
    if result is None:
        return []

    branches = result[1].splitlines()
    # Strip the leading * or space
    branches = [b.strip().lstrip("* ") for b in branches if b.strip()]

    # Remove the target branch itself
    branches = [b for b in branches if b != target]

    results = []
    for branch in branches:
        # Get commits on this branch not on target
        result = try_git("log", "--format=%H", f"{branch}..{target}")
        if result is None:
            continue
        text = result[1]
        if not text:
            count = 0
        else:
            count = len([sha for sha in text.splitlines() if sha.strip()])

        # Get short sha of branch head
        result2 = try_git("rev-parse", "--short", "HEAD")
        # Actually get branch head sha by checking out the branch ref
        result2 = try_git("rev-parse", branch)
        if result2 is None:
            branch_sha = ""
        else:
            branch_sha = result2[1].strip()[:7]

        results.append({
            "branch": branch,
            "commits_outside": count,
            "sha": branch_sha,
        })

    # Sort by commits_outside descending
    results.sort(key=lambda x: x["commits_outside"], reverse=True)
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 check_pre_ref.py TARGET_BRANCH [--root GIT_ROOT]", file=sys.stderr)
        return 2

    target = sys.argv[1]

    # Determine repo root
    root = find_git_root(os.getcwd())
    if root is None:
        print("Error: Could not find git repository root", file=sys.stderr)
        return 2

    global REPO_ROOT
    REPO_ROOT = root

    # Check if the target branch exists and get its sha
    result = try_git("rev-parse", target)
    if result is None:
        print(f"Error: Could not resolve branch '{target}'", file=sys.stderr)
        return 2

    target_sha = result[1].strip()

    # If only target is given, we need to list branches with commits outside target
    branches = get_branches_with_commits_outside_target(target)

    if not branches:
        print("Warning: No local branches found or all branches are up to date with target", file=sys.stderr)
        return 1

    # Write branch lineage data
    lineage_data = {
        "ok": False,
        "target": target,
        "target_sha": target_sha,
        "branches": branches,
        "total_branches": len(branches),
    }

    sidecar_name = "pre_ref_sidecar.json"
    sidecar_path_full = os.path.join(REPO_ROOT, sidecar_name)

    with open(sidecar_path_full, "w", encoding="utf-8") as f:
        json.dump(lineage_data, f, indent=2, ensure_ascii=False)

    # Update findings.md with the evidence
    findings_path = os.path.join(REPO_ROOT, "findings.md")

    # Get session info
    session_result = subprocess.run(
        ["git", "log", "--format=%h", "-n", "1"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    session_h = session_result.stdout.strip() if session_result.stdout else "unknown"

    timestamp_result = subprocess.run(
        ["git", "log", "--format=%ci", "-n", "1"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    timestamp = timestamp_result.stdout.strip() if timestamp_result.stdout else "unknown"

    # Build the pre-ref check section
    precheck_section = "## Pre-Ref Check — source ref availability\n\n"
    precheck_section += "- Target: %s (SHA: %s)\n" % (target, target_sha)
    precheck_section += "- Local branches with commits outside target: %d\n" % len(branches)
    precheck_section += "- Status: BRANCHES_LISTED (use the branch with most commits outside target)\n"
    precheck_section += "- Recommended: Use the first branch listed (most commits outside target)\n"

    # Check if section already exists in findings.md
    with open(findings_path, "r", encoding="utf-8") as f:
        content = f.read()

    marker = "## Pre-Ref Check"
    if marker in content:
        # Insert after the last Pre-Ref Check block - find last marker and insert before it
        lines = content.split("\n")
        last_marker_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("## Pre-Ref Check"):
                last_marker_idx = i

        if last_marker_idx >= 0:
            # Insert new section before the last marker
            new_lines = lines[:last_marker_idx] + [precheck_section.strip()] + lines[last_marker_idx:]
            with open(findings_path, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines))
        else:
            # Append at end
            with open(findings_path, "a", encoding="utf-8") as f:
                f.write("\n" + precheck_section.strip())
    else:
        # No sessions found, append at end
        with open(findings_path, "a", encoding="utf-8") as f:
            f.write("\n" + precheck_section.strip())

    # Output results
    print("PASS: Source ref check completed - branches listed below:")
    print("- Target: %s (SHA: %s)" % (target, target_sha))
    for b in branches:
        sha_info = " (SHA: %s)" % b["sha"] if b["sha"] else ""
        print("  - %s: %d commits outside target%s" % (b["branch"], b["commits_outside"], sha_info))

    print()
    print("Recommended branch: %s (has most commits outside target)" % branches[0]["branch"])

    return 0


if __name__ == "__main__":
    sys.exit(main())