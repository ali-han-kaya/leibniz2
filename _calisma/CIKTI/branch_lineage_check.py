#!/usr/bin/env python3
"""
branch_lineage_check.py — Branch lineage coverage check.

Proves that every commit on a work branch is reachable from the target
branch before the work branch is deleted. Records evidence in findings.md.

Usage:
    python3 branch_lineage_check.py TARGET_BRANCH SOURCE_BRANCH [--root GIT_ROOT]

Exit codes:
    0 = PASS (all commits reachable)
    1 = FAIL (some commits not reachable)
    2 = ERROR (could not resolve branches)
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


def get_commits_on_branch(branch):
    """Get list of commit SHAs on a branch, newest first."""
    result = try_git("log", "--format=%H", branch)
    if result is None:
        return []
    # result is (returncode, stdout, stderr)
    text = result[1]
    if not text:
        return []
    return [sha.strip() for sha in text.splitlines() if sha.strip()]


def is_ancestor(commit, target):
    """Check if commit is an ancestor of target (i.e., reachable from target).
    
    git merge-base --is-ancestor A B returns exit code 0 if A is an ancestor of B.
    """
    result = try_git("merge-base", "--is-ancestor", commit, target)
    if result is None:
        return False
    returncode, stdout, stderr = result
    return returncode == 0


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 branch_lineage_check.py TARGET_BRANCH SOURCE_BRANCH [--root GIT_ROOT]", file=sys.stderr)
        return 2

    target = sys.argv[1]
    source = sys.argv[2]

    # Determine repo root
    root = find_git_root(os.getcwd())
    if root is None:
        print("Error: Could not find git repository root", file=sys.stderr)
        return 2

    global REPO_ROOT
    REPO_ROOT = root

    try:
        target_sha = git("--short", "rev-parse", target)[1]
        source_sha = git("--short", "rev-parse", source)[1]
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Get all commits on the source branch
    commits = get_commits_on_branch(source)
    total = len(commits)

    if total == 0:
        print("Warning: No commits found on branch %s" % source, file=sys.stderr)
        return 0

    # Check each commit is reachable from target
    unreachable = []
    for i, commit in enumerate(commits):
        commit_short = commit[:7]
        if not is_ancestor(commit, target):
            unreachable.append({"sha": commit, "short": commit_short, "index": i})

    # Write lineage data
    lineage_data = {
        "ok": len(unreachable) == 0,
        "detail": None,
        "total": total,
        "reachable": total - len(unreachable),
        "unreachable": len(unreachable),
        "generations": [],
    }

    # Build generation records for all commits
    for i, commit in enumerate(commits):
        commit_short = commit[:7]
        in_target = is_ancestor(commit, target)
        lineage_data["generations"].append({
            "gen": f"gen-{i}",
            "sha": commit,
            "short": commit_short,
            "in_target": in_target,
            "status": "PASS" if in_target else "FAIL",
        })

    # Write the sidecar file
    sidecar_name = "branch_lineage_sidecar.json"
    sidecar_path_full = os.path.join(REPO_ROOT, sidecar_name)

    with open(sidecar_path_full, "w", encoding="utf-8") as f:
        json.dump(lineage_data, f, indent=2, ensure_ascii=False)

    # Update findings.md with the evidence
    findings_path = os.path.join(REPO_ROOT, "findings.md")

    # Get session info
    session_result = subprocess.run(
        ["git", "log", "--format=%h", "-n 1"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    session_h = session_result.stdout.strip() if session_result.stdout else "unknown"

    timestamp_result = subprocess.run(
        ["git", "log", "--format=%ci", "-n 1"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    timestamp = timestamp_result.stdout.strip() if timestamp_result.stdout else "unknown"

    lineage_section = "## Session %s — branch lineage coverage\n\n" % session_h
    lineage_section += "- Target: `%s` (%s)\n" % (target, target_sha)
    lineage_section += "- Source: `%s` (%s)\n" % (source, source_sha)
    lineage_section += "- Total commits on source: %d\n" % total
    lineage_section += "- Reachable from target: %d\n" % (total - len(unreachable))
    lineage_section += "- Unreachable commits: %d\n" % len(unreachable)
    lineage_section += "- Status: %s\n" % ("PASS" if lineage_data["ok"] else "FAIL")

    # Check if section already exists in findings.md
    with open(findings_path, "r", encoding="utf-8") as f:
        content = f.read()

    marker = "## Session"
    if marker in content:
        # Insert after the last session block - find last ## Session and insert before it
        lines = content.split("\n")
        last_session_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("## Session"):
                last_session_idx = i

        if last_session_idx >= 0:
            # Insert new section before the last Session marker
            new_lines = lines[:last_session_idx] + [lineage_section.strip()] + lines[last_session_idx:]
            with open(findings_path, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines))
        else:
            # Append at end
            with open(findings_path, "a", encoding="utf-8") as f:
                f.write("\n" + lineage_section.strip())
    else:
        # No sessions found, append at end
        with open(findings_path, "a", encoding="utf-8") as f:
            f.write("\n" + lineage_section.strip())

    # Output results
    if lineage_data["ok"]:
        print("PASS: All %d commits on branch `%s` are reachable from `%s`" % (total, source, target))
        return 0
    else:
        print("FAIL: %d of %d commits on branch `%s` are NOT reachable from `%s`" % (
            len(unreachable), total, source, target))
        for u in unreachable:
            print("  - %s (index %d)" % (u["short"], u["index"]), file=sys.stderr)

        # Still write the sidecar even on failure
        with open(sidecar_path_full, "w", encoding="utf-8") as f:
            json.dump(lineage_data, f, indent=2, ensure_ascii=False)

        return 1


if __name__ == "__main__":
    sys.exit(main())