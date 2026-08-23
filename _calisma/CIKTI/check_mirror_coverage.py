#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_mirror_coverage.py — sync_verify_mirror.sh --list ↔ repo dosya kümesi.

Mirror eksikliği regresyonunu CI'da yakalar: repo'ya bir runtime dosyası
eklenir ama sync_verify_mirror.sh'in FILES/LEAN_FILES/PREVIEW_FILES/GUIDE_FILES
listelerine işlenmezse, launchd rotası (TCC-safe mirror) o dosyayı hiç
göremez → K9/K16/K17/K18 kırılır. Bu script GERÇEK senkron kapsamını
(`sync_verify_mirror.sh --list` çıktısı — listedeki her `kaynak -> hedef`
satırı) repo dosya kümesiyle karşılaştırır:

  - İleri (mirror eksikliği): beklenen her runtime dosyası listede olmalı.
  - Ters (bayat girdi): listedeki her kaynak repo'da VAR olmalı ve beklenen
    kümede olmalı (beklenmeyen girdi → kapsam tanımı bayat, fail-closed).

Beklenen küme (test_mirror_check.py TestMirrorFileCoverage ile aynı sözleşme):
  github_scripts/*.js, teslim zip'leri + .sha256, RUNTIME_REQUIRED core
  dosyaları, PREVIEW_RUNTIME, lean_reduct kaynakları, guide.html.

Exit: 0 = kapsam tam / 1 = eksik veya bayat girdi / 2 = hata (script yok).
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Core runtime dosyaları — mirror'da eksikse launchd rotası K1-K18'i
# çalıştıramaz (FILES bölümü; test_mirror_check ile tek sözleşme).
RUNTIME_REQUIRED = (
    "verify_delivery.py", "verify_delivery.config.json",
    "verify_delivery.config.schema.json", "symbolic_proof_z3.py",
    "verify_lean.sh", "zip_lineage.json", "gen_repro_manifest.py",
    "gen_config.py", "cleanup_log.json", "github_scripts_battery.py",
    "github_scripts_selftest.js", "daemon_http_test.py", "preview.html",
)
# Preview mirror runtime'ı (PREVIEW_FILES — launchd çalıştırıcısı + PreStart).
PREVIEW_RUNTIME = ("preview_server.py", "_daemonize.py", "preview_prestart.py")
# Branch protection kılavuzu (GUIDE_FILES — /guide.html rotası).
GUIDE_REL = "docs/branch-protection-guide/guide.html"

EXIT_OK = 0
EXIT_COVERAGE = 1
EXIT_ERROR = 2


def run_list(script):
    """`bash <script> --list` çalıştır; (rc, çıktı) döner."""
    r = subprocess.run(["bash", script, "--list"],
                       capture_output=True, text=True, timeout=60)
    return r.returncode, (r.stdout + r.stderr)


def parse_list(out, root, cikti, lean_src):
    """--list çıktısındaki `kaynak -> hedef` satırlarını repo-göreli yolla topla."""
    root = os.path.abspath(root)
    cikti = os.path.abspath(cikti)
    lean_src = os.path.abspath(lean_src)
    listed = set()
    for ln in out.splitlines():
        if " -> " not in ln:
            continue
        src = ln.split(" -> ", 1)[0].strip()
        if not src:
            continue
        abs_src = os.path.abspath(src)
        if abs_src.startswith(cikti + os.sep):
            listed.add("_calisma/CIKTI/" +
                       os.path.relpath(abs_src, cikti))
        elif abs_src.startswith(lean_src + os.sep):
            listed.add("_calisma/lean_reduct/" +
                       os.path.relpath(abs_src, lean_src))
        elif abs_src.startswith(root + os.sep):
            listed.add(os.path.relpath(abs_src, root))
        # Başka yerdeki kaynak (ör. sistem yolu) — repo dışı, kapsam dışı.
    return listed


def expected_repo_files(root, cikti, lean_src):
    """Repo'daki beklenen runtime dosya kümesi (repo-göreli yollar)."""
    exp = set()
    # CIKTI kökündeki teslim zip'leri + .sha256 (top-level .js BİLEREK yok:
    # budget_scan.js gibi dashboard/pre-commit asset'leri launchd rotasında
    # çalışmaz — runtime .js'ler RUNTIME_REQUIRED'da açıkça listelenir).
    if os.path.isdir(cikti):
        for n in os.listdir(cikti):
            if n.endswith(".zip") or n.endswith(".zip.sha256"):
                exp.add("_calisma/CIKTI/" + n)
        # github_scripts/*.js
        gs = os.path.join(cikti, "github_scripts")
        if os.path.isdir(gs):
            for n in os.listdir(gs):
                if n.endswith(".js"):
                    exp.add("_calisma/CIKTI/github_scripts/" + n)
    # Core runtime + preview runtime.
    for n in RUNTIME_REQUIRED:
        exp.add("_calisma/CIKTI/" + n)
    for n in PREVIEW_RUNTIME:
        exp.add("_calisma/CIKTI/" + n)
    # Guide.
    exp.add(GUIDE_REL)
    # Lean kaynakları (.lean + toolchain + lakefile; .lake build dizini hariç).
    if os.path.isdir(lean_src):
        for dirpath, dirnames, filenames in os.walk(lean_src):
            dirnames[:] = [d for d in dirnames if d != ".lake"]
            for fn in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fn), lean_src)
                if rel.endswith(".lean") or rel in ("lean-toolchain",
                                                    "lakefile.toml"):
                    exp.add("_calisma/lean_reduct/" + rel)
    return exp


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sync-script",
                    default=os.path.join(HERE, "sync_verify_mirror.sh"))
    ap.add_argument("--root", default=None,
                    help="repo kökü (vars. script'in ../..)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    script = args.sync_script
    if not os.path.isfile(script):
        print(f"HATA: sync_verify_mirror.sh yok: {script}", file=sys.stderr)
        return EXIT_ERROR
    root = os.path.abspath(args.root or
                           os.path.join(os.path.dirname(script), "..", ".."))
    cikti = os.path.join(root, "_calisma", "CIKTI")
    lean_src = os.path.join(root, "_calisma", "lean_reduct")

    rc, out = run_list(script)
    if rc != 0:
        print(f"HATA: sync_verify_mirror.sh --list çalışmadı (exit {rc})",
              file=sys.stderr)
        print(out, file=sys.stderr)
        return EXIT_ERROR

    listed = parse_list(out, root, cikti, lean_src)
    expected = expected_repo_files(root, cikti, lean_src)

    # İleri: mirror eksikliği — beklenen dosya listede yok.
    missing = sorted(expected - listed)
    # Ters 1: bayat girdi — listedeki kaynak repo'da yok.
    dead = sorted(s for s in listed if not os.path.isfile(
        os.path.join(root, s)))
    # Ters 2: beklenmeyen girdi — listede var ama beklenen kümede yok.
    unexpected = sorted(listed - expected)

    report = {"ok": not (missing or dead or unexpected),
              "missing": missing, "dead": dead, "unexpected": unexpected}
    if args.json:
        print(__import__("json").dumps(report, ensure_ascii=False))
    else:
        print(f"listelenen: {len(listed)} | beklenen: {len(expected)}")
        for m in missing:
            print(f"EKSİK (mirror'da yok): {m} — FILES/LEAN_FILES'a ekleyin")
        for d in dead:
            print(f"BAYAT (repo'da yok): {d} — listeden kaldırın")
        for u in unexpected:
            print(f"BEKLENMEYEN: {u} — kapsam tanımı bayat (check_mirror_coverage.py)")
        if missing or dead or unexpected:
            print("SONUÇ: KAPSAM EKSİK (exit 1)", file=sys.stderr)
            return EXIT_COVERAGE
        print("SONUÇ: KAPSAM TAM — mirror listesi repo runtime kümesini kapsıyor (exit 0)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
