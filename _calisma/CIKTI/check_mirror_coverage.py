#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME_REQUIRED = (
    "verify_delivery.py", "verify_delivery.config.json", "verify_delivery.config.schema.json",
    "symbolic_proof_z3.py", "verify_lean.sh", "zip_lineage.json", "gen_repro_manifest.py",
    "gen_config.py", "cleanup_log.json", "github_scripts_battery.py", "github_scripts_selftest.js",
    "daemon_http_test.py", "preview.html", "preview.js", "fresh_clone_setup.sh", "test_fresh_clone_setup.py",
    "update_preview.sh", "check_unit_tests.list", "check_unit_tests_hook.sh", "sync_check_unit_tests.py",
    "lake_evidence_hook.sh", "test_lake_evidence_smoke.py", "render_z3_slides.py", "test_render_z3_slides.py",
    # Run-summary modülleri + konsolidatör (K13 ayrı-step sidecar özetleri)
    "run_summary_budget.py", "run_summary_changelog.py", "run_summary_k0.py",
    "run_summary_k12.py", "run_summary_k13.py", "run_summary_klayers.py",
    "run_summary_lineage.py", "run_summary_precommit.py", "run_summary_refs_trend.py",
    "consolidate_summary.py",
)
PREVIEW_RUNTIME = ("preview_server.py", "_daemonize.py", "preview_prestart.py", "sw.js")
GUIDE_REL = "docs/branch-protection-guide/guide.html"
DOC_REL = "docs/HOOK_ENV_MATRIX.md"
# design-system token sheet — preview.html /design-system/tokens.css import
# eder; sync_verify_mirror.sh GUIDE_FILES bloğu bunu PREVIEW_DIR'e
# design-system-tokens.css olarak mirror'lar. Tek kaynak:
# <repo>/design-system/tokens.css — kapsam tanımı bunu beklemeli (yoksa
# fail-closed coverage CI'da "BEKLENMEYEN: design-system/tokens.css" ile kırılır).
DESIGN_TOKENS_REL = "design-system/tokens.css"


def run_list(script):
    r = subprocess.run(["bash", script, "--list"], capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr


def parse_list(out, root, cikti, lean_src):
    roots = ((os.path.abspath(cikti), "_calisma/CIKTI"),
             (os.path.abspath(lean_src), "_calisma/lean_reduct"),
             (os.path.abspath(root), ""))
    listed = set()
    for line in out.splitlines():
        if " -> " not in line:
            continue
        source = os.path.abspath(line.split(" -> ", 1)[0].strip())
        for base, prefix in roots:
            if source == base or source.startswith(base + os.sep):
                rel = os.path.relpath(source, base)
                listed.add(os.path.join(prefix, rel).replace(os.sep, "/").lstrip("/"))
                break
    return listed


def _git_tracked_files(root, prefix):
    """Return git ls-files output for prefix, or None if not a git checkout or git fails.

    Clone-safe: untracked/generated files (e.g. a stray github_scripts/*.js
    dropped in a dirty worktree) are NOT returned, so they can never flip the
    expected set. Fake-repo tests use a temp dir without .git and fall back
    to the filesystem scan below.
    """
    if not os.path.exists(os.path.join(root, ".git")):
        return None
    try:
        r = subprocess.run(["git", "-C", root, "ls-files", "--", prefix],
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:
        return None


def expected_repo_files(root, cikti, lean_src):
    expected = set()
    tracked = _git_tracked_files(root, "_calisma/CIKTI")
    if tracked is not None:
        for p in tracked:
            if not p.startswith("_calisma/CIKTI/"):
                continue
            rel = p[len("_calisma/CIKTI/"):]
            if "/" not in rel and (rel.endswith(".zip") or rel.endswith(".zip.sha256")):
                expected.add(p)
            elif rel.startswith("github_scripts/") and rel.endswith(".js") and rel.count("/") == 1:
                expected.add(p)
    elif os.path.isdir(cikti):
        expected.update("_calisma/CIKTI/" + n for n in os.listdir(cikti)
                        if n.endswith(".zip") or n.endswith(".zip.sha256"))
        gs = os.path.join(cikti, "github_scripts")
        if os.path.isdir(gs):
            expected.update("_calisma/CIKTI/github_scripts/" + n for n in os.listdir(gs)
                            if n.endswith(".js"))
    for name in RUNTIME_REQUIRED:
        expected.add("_calisma/CIKTI/" + name)
    expected.update("_calisma/CIKTI/" + n for n in PREVIEW_RUNTIME)
    expected.add(GUIDE_REL)
    expected.add(DOC_REL)
    expected.add(DESIGN_TOKENS_REL)
    if os.path.isdir(lean_src):
        for directory, dirs, files in os.walk(lean_src):
            dirs[:] = [d for d in dirs if d != ".lake"]
            for name in files:
                rel = os.path.relpath(os.path.join(directory, name), lean_src)
                if rel.endswith(".lean") or rel in {"lean-toolchain", "lakefile.toml"}:
                    expected.add("_calisma/lean_reduct/" + rel)
    return expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync-script", default=os.path.join(HERE, "sync_verify_mirror.sh"))
    parser.add_argument("--root", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not os.path.isfile(args.sync_script):
        print(f"HATA: sync_verify_mirror.sh yok: {args.sync_script}", file=sys.stderr)
        return 2
    root = os.path.abspath(args.root or os.path.join(os.path.dirname(args.sync_script), "..", ".."))
    cikti, lean_src = os.path.join(root, "_calisma/CIKTI"), os.path.join(root, "_calisma/lean_reduct")
    rc, output = run_list(args.sync_script)
    if rc:
        print(output, file=sys.stderr)
        return 2
    listed = parse_list(output, root, cikti, lean_src)
    expected = expected_repo_files(root, cikti, lean_src)
    missing = sorted(expected - listed)
    dead = sorted(path for path in listed if not os.path.isfile(os.path.join(root, path)))
    unexpected = sorted(listed - expected)
    report = {"ok": not (missing or dead or unexpected), "missing": missing,
              "dead": dead, "unexpected": unexpected}
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"listelenen: {len(listed)} | beklenen: {len(expected)}")
        for label, paths in (("EKSİK", missing), ("BAYAT", dead), ("BEKLENMEYEN", unexpected)):
            for path in paths:
                print(f"{label}: {path}")
        if not report["ok"]:
            print("SONUÇ: KAPSAM EKSİK (exit 1)", file=sys.stderr)
            return 1
        print("SONUÇ: KAPSAM TAM — mirror listesi repo runtime kümesini kapsıyor (exit 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
