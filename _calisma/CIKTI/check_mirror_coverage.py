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
    "daemon_http_test.py", "preview.html", "fresh_clone_setup.sh", "test_fresh_clone_setup.py",
    "update_preview.sh", "check_unit_tests.list", "check_unit_tests_hook.sh", "sync_check_unit_tests.py",
    "lake_evidence_hook.sh", "test_lake_evidence_smoke.py", "render_z3_slides.py", "test_render_z3_slides.py",
    "test_launchd_minimal_path.py", "../slides_z3/P1-a.png", "../slides_z3/P1-b.png", "../slides_z3/P2.png",
    "../slides_z3/P3-a.png", "../slides_z3/P3-b.png", "../slides_z3/P4-a.png", "../slides_z3/P4-b.png",
    "../slides_z3/P4-c.png", "../slides_z3/P4-d.png", "../slides_z3/P4-e.png", "../slides_z3/P5-note.png",
    "../slides_z3/P5.png",
)
PREVIEW_RUNTIME = ("preview_server.py", "_daemonize.py", "preview_prestart.py", "sw.js")
GUIDE_REL = "docs/branch-protection-guide/guide.html"
DOC_REL = "docs/HOOK_ENV_MATRIX.md"


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


def expected_repo_files(root, cikti, lean_src):
    expected = set()
    if os.path.isdir(cikti):
        expected.update("_calisma/CIKTI/" + n for n in os.listdir(cikti)
                        if n.endswith(".zip") or n.endswith(".zip.sha256"))
        gs = os.path.join(cikti, "github_scripts")
        if os.path.isdir(gs):
            expected.update("_calisma/CIKTI/github_scripts/" + n for n in os.listdir(gs)
                            if n.endswith(".js"))
    for name in RUNTIME_REQUIRED:
        if name.startswith("../"):
            expected.add("_calisma/slides_z3/" + name[len("../slides_z3/"):])
        else:
            expected.add("_calisma/CIKTI/" + name)
    expected.update("_calisma/CIKTI/" + n for n in PREVIEW_RUNTIME)
    expected.add(GUIDE_REL)
    expected.add(DOC_REL)
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
