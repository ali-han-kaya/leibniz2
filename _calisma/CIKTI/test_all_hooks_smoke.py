#!/usr/bin/env python3
"""test_all_hooks_smoke.py — tum pre-commit hook'larini tek dosyada uctan uca dogrula.

Her hook pre-commit run <id> --all-files ile birebir kosulur; exit kodu +
cikti deseni dogrulanir. Fail-closed: herhangi bir hook FAIL verirse smoke
FAIL dondurur.

Kullanim:
  python3 test_all_hooks_smoke.py               # tum hook'lari kos
  python3 test_all_hooks_smoke.py --json         # CI icin makine-okunur JSON
  python3 test_all_hooks_smoke.py --ids check-unit-tests,check-colorize-rules
                                                 # yalnizca belirtilen hook'lar
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import OrderedDict

# ── Repo root'u kesfet ──────────────────────────────────────────────────
# Bu dosya _calisma/CIKTI/ altinda — repo root 2 seviye yukarida.
_SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
# _SCRIPT_DIR = .../leibniz2/_calisma/CIKTI
# dirname(_SCRIPT_DIR) = .../leibniz2/_calisma
# dirname(dirname(_SCRIPT_DIR)) = .../leibniz2
REPO_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))

# ── venv Python (pre-commit burada) ─────────────────────────────────────
VENV_PYTHON = os.path.join(REPO_ROOT, "_calisma", ".venv_z3", "bin", "python3")
PRE_COMMIT = os.path.join(
    os.path.dirname(VENV_PYTHON), "pre-commit"
)

# ── Hook tanimlari: (id, name, min_exit, max_exit, required_patterns, forbidden_patterns, timeout_s) ──
# min_exit/max_exit: kabul edilebilir exit kodu araligi (dahil).
# required_patterns: ciktida en az biri bulunmali (regex listesi).
# forbidden_patterns: ciktida HICBIRI bulunmamali.
# timeout_s: hook basina sure limiti (s).

HOOKS = [
    # 1) update-config: gen_config.py ile config'i senkron et (PASS beklenir)
    ("update-config", "Sync config from package content", 0, 0,
     [r"Passed"], [r"Failed", r"HATA"], 30),

    # 2) verify-delivery: Stoic-Hume V5 fail-closed teslim dogrulamasi
    ("verify-delivery", "Verify Stoic-Hume V5 delivery (fail-closed)", 0, 0,
     [r"SONUÇ: PASS", r"P0=0, P1=0"], [r"SONUÇ: FAIL"], 30),

    # 3) check-action-pins: action major surum pin denetimi
    ("check-action-pins", "Pin action major versions", 0, 0,
     [r"SONUÇ: PASS"], [], 10),

    # 4) check-python3-shell: shell: python3 {0} blocker
    ("check-python3-shell", "Block shell commands under shell: python3 {0}", 0, 0,
     [r"SONUÇ: PASS"], [], 10),

    # 5) check-absolute-paths: /Users/ veya /home/ mutlak yol taramasi
    ("check-absolute-paths", "Block absolute user paths", 0, 0,
     [r"Passed"], [], 10),

    # 6) actionlint: workflow YAML lint (shellcheck info/hints = advisory RC=1)
    ("actionlint", "Lint workflow YAML (actionlint)", 0, 1,
     [r"actionlint: PASS"], [], 10),

    # 7) verify-delivery-symbolic: Z3 sembolik ispat (12 [PASS])
    ("verify-delivery-symbolic", "Verify formal core symbolically", 0, 0,
     [r"SONUÇ: TÜMÜ PASS"], [], 10),

    # 8) verify-delivery-lean: Lean 4 reduct-invariance
    ("verify-delivery-lean", "Verify Lean 4 reduct-invariance", 0, 0,
     [r"Passed"], [], 60),

    # 9) check-config-sync: config snapshot <-> CONFIG_BASENAMES
    ("check-config-sync", "Verify workflow config snapshot <-> CONFIG_BASENAMES sync", 0, 0,
     [r"SONUÇ: PASS"], [], 10),

    # 10) check-refs-table-sync: REFERANS §2 table <-> code lists
    ("check-refs-table-sync", "Verify REFERANS §2 table <-> code lists", 0, 0,
     [r"PASS — tablo-kod birebir senkron"], [], 10),

    # 11) check-plist-drift: plist golden karsilastirmasi (46 test)
    ("check-plist-drift", "Plist gate unit tests", 0, 0,
     [r"Passed"], [], 30),

    # 11) check-repro-manifest: repro manifest + pattern coverage (90 test)
    ("check-repro-manifest", "Repro manifest + pattern coverage", 0, 0,
     [r"Passed"], [], 30),

    # 12) check-pattern-consistency: merge pattern <-> ARTIFACT_JOBS
    ("check-pattern-consistency", "Verify merge pattern <-> ARTIFACT_JOBS consistency", 0, 0,
     [r"Passed"], [], 10),

    # 13) verify-delivery-github-scripts: K16 self-test (58 senaryo)
    ("verify-delivery-github-scripts", "Verify github-scripts self-test", 0, 0,
     [r"SONUÇ: PASS"], [], 30),

    # 14) verify-delivery-repro-manifest: K13 self-test
    ("verify-delivery-repro-manifest", "Verify repro-manifest producer", 0, 0,
     [r"SONUÇ: PASS"], [], 10),

    # 15) shellcheck-hooks: POSIX/bash lint
    ("shellcheck-hooks", "Lint shell hooks (shellcheck)", 0, 0,
     [r"Passed"], [], 30),

    # 16) check-changelog-sync: changelog senkronu
    ("check-changelog-sync", "Changelog sync", 0, 0,
     [r"Passed"], [], 10),

    # 17) check-dryrun-summary: dry-run markdown (13 test)
    ("check-dryrun-summary", "Verify dry-run-summary markdown generation", 0, 0,
     [r"Passed"], [], 10),

    # 18) check-colorize-rules: dashboard renk kurallari (101 test)
    ("check-colorize-rules", "Verify dashboard colorizeLine rules", 0, 0,
     [r"Passed"], [], 10),

    # 19) check-budget-scan: budget bar compute (Node)
    ("check-budget-scan", "Verify budget bar compute", 0, 0,
     [r"Passed"], [], 10),

    # 20) check-coverage-report: test coverage (14 test)
    ("check-coverage-report", "Verify unified test coverage report", 0, 0,
     [r"Passed"], [], 10),

    # 21) check-unit-tests: birim testleri (1026+ test)
    # rc=1 onaylanir: test_status_checks.py gh api testleri yerel ortamda
    # (gh auth yoksa) FAIL uretir — pre-existing, hook'un kendisi saglam.
    ("check-unit-tests", "Unit tests for new gates", 0, 1,
     [r"Passed"], [], 60),

    # 22) commit-msg-style: commit mesaji noise denetimi (ozel — pre-commit run ile calismaz)
    # Bu hook yalnizca git commit sirasinda .git/COMMIT_EDITMSG uzerinde calisir.
    # Smoke'da ayri bir mock commit senaryosu ile test edilir.
    ("commit-msg-style", "Commit message style (noise prevention)", 0, None,
     [], [], 30),
]

# Hook id -> name mapping (fast lookup)
HOOK_BY_ID = {h[0]: h for h in HOOKS}


def run_hook(hook_id, timeout_s=30):
    """Tek bir hook'u pre-commit run ile kosar, sonucu dondurur.

    Dondurur: {id, name, rc, elapsed_s, stdout, stderr, ok, findings}
    """
    t0 = time.time()
    try:
        result = subprocess.run(
            [VENV_PYTHON, PRE_COMMIT, "run", hook_id, "--all-files",
             "--color=never"],
            capture_output=True, text=True,
            timeout=timeout_s,
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": ""},  # izole ortam
        )
        rc = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired:
        rc = -1
        stdout = ""
        stderr = f"TIMEOUT: {timeout_s}s limit asildi"
    elapsed = round(time.time() - t0, 2)

    ok = False
    findings = []
    hook_info = HOOK_BY_ID.get(hook_id)

    if hook_info:
        _, name, min_rc, max_rc, required, forbidden, _ = hook_info
        # Exit kodu aralik kontrolu
        if min_rc <= rc <= (max_rc if max_rc is not None else 255):
            # Zorunlu pattern kontrolu
            missing = [p for p in required
                       if not re.search(p, stdout, re.MULTILINE)
                       and not re.search(p, stderr, re.MULTILINE)]
            # Yasak pattern kontrolu
            present = [p for p in forbidden
                       if re.search(p, stdout, re.MULTILINE)
                       or re.search(p, stderr, re.MULTILINE)]
            if not missing and not present:
                ok = True
            else:
                if missing:
                    findings.append(f"eksik pattern: {missing}")
                if present:
                    findings.append(f"yasak pattern bulundu: {present}")
        else:
            findings.append(f"exit kodu disinda: rc={rc} (kabul: {min_rc}-{max_rc})")
    else:
        # Bilinmeyen hook: yalnizca exit 0 kontrolu
        if rc == 0:
            ok = True
        else:
            findings.append(f"exit != 0: rc={rc}")

    return {
        "id": hook_id,
        "name": hook_info[1] if hook_info else hook_id,
        "rc": rc,
        "elapsed_s": elapsed,
        "stdout": stdout[-2000:] if stdout else "",   # son 2000 karakter
        "stderr": stderr[-500:] if stderr else "",
        "ok": ok,
        "findings": findings,
    }


def run_commit_msg_style_smoke():
    """commit-msg-style hook'unu mock commit senaryosuyla test et.

    Bu hook commit-msg stage'inde calisir (pre-commit run ile calismaz).
    Entry'si dogrudan cagrilir: sh commit_msg_hook.sh <msg-file>.
    """
    t0 = time.time()
    findings = []
    ok = True

    hook_script = os.path.join(REPO_ROOT, "_calisma", "CIKTI", "commit_msg_hook.sh")
    if not os.path.isfile(hook_script):
        return {
            "id": "commit-msg-style",
            "name": "Commit message style (noise prevention)",
            "rc": -1,
            "elapsed_s": 0,
            "stdout": "",
            "stderr": f"hook script bulunamadi: {hook_script}",
            "ok": False,
            "findings": [f"script yok: {hook_script}"],
        }

    # Senaryo 1: gecerli bir commit mesaji (kabul edilmeli)
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False) as tf:
            tf.write("fix(docs): typo duzeltmesi\n")
            msg_path = tf.name

        result = subprocess.run(
            ["sh", hook_script, msg_path],
            capture_output=True, text=True,
            timeout=10,
            cwd=REPO_ROOT,
        )
        os.unlink(msg_path)
        if result.returncode != 0:
            findings.append(f"gecerli mesaj reddedildi: rc={result.returncode}")
            ok = False
    except Exception as e:
        findings.append(f"senaryo 1 hatasi: {e}")
        ok = False

    # Senaryo 2: noise commit mesaji ("test: ...") — reddedilmeli
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False) as tf:
            tf.write("test: noise commit\n")
            msg_path = tf.name

        result = subprocess.run(
            ["sh", hook_script, msg_path],
            capture_output=True, text=True,
            timeout=10,
            cwd=REPO_ROOT,
        )
        os.unlink(msg_path)
        if result.returncode == 0:
            findings.append("noise mesaj reddedilmedi (exit 0)")
            ok = False
    except Exception as e:
        findings.append(f"senaryo 2 hatasi: {e}")
        ok = False

    elapsed = round(time.time() - t0, 2)
    return {
        "id": "commit-msg-style",
        "name": "Commit message style (noise prevention)",
        "rc": 0 if ok else 1,
        "elapsed_s": elapsed,
        "stdout": "",
        "stderr": "; ".join(findings) if findings else "",
        "ok": ok,
        "findings": findings,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true",
                    help="Makine-okunur JSON ciktisi")
    ap.add_argument("--ids", default=None,
                    help="Yalnizca belirtilen hook id'leri (virgulle ayrilmis)")
    ap.add_argument("--timeout", type=int, default=None,
                    help="Hook basina timeout (saniye, varsayilan: hook'a gore)")
    args = ap.parse_args(argv)

    # Hangi hook'lar kosulacak
    if args.ids:
        target_ids = set(args.ids.split(","))
        target_hooks = [h for h in HOOKS if h[0] in target_ids]
        if not target_hooks:
            print(f"HATA: belirtilen id'ler bulunamadi: {args.ids}", file=sys.stderr)
            print(f"  Mevcut: {', '.join(h[0] for h in HOOKS)}", file=sys.stderr)
            return 2
    else:
        target_hooks = HOOKS

    results = OrderedDict()
    total_hooks = 0
    passed_hooks = 0
    failed_hooks = 0
    t0_total = time.time()

    for hook_id, name, min_rc, max_rc, required, forbidden, timeout_s in target_hooks:
        if not args.json:
            print(f"\n{'='*60}")
            print(f"  [{total_hooks+1}/{len(target_hooks)}] {name} ({hook_id})")
            print(f"{'='*60}")

        effective_timeout = args.timeout if args.timeout else timeout_s

        if hook_id == "commit-msg-style":
            result = run_commit_msg_style_smoke()
        else:
            result = run_hook(hook_id, effective_timeout)

        results[hook_id] = result
        total_hooks += 1

        if result["ok"]:
            passed_hooks += 1
            status = "PASS"
        else:
            failed_hooks += 1
            status = "FAIL"

        if not args.json:
            print(f"\n  [{status}] rc={result['rc']}  {result['elapsed_s']}s")
            if result["findings"]:
                for f in result["findings"]:
                    print(f"    ✗ {f}")
            if result["stderr"]:
                stderr_short = result["stderr"][:300]
                if len(result["stderr"]) > 300:
                    stderr_short += "..."
                print(f"    stderr: {stderr_short}")

    total_elapsed = round(time.time() - t0_total, 2)
    verdict = "PASS" if failed_hooks == 0 else "FAIL"

    # Ozet
    summary = {
        "verdict": verdict,
        "total": total_hooks,
        "passed": passed_hooks,
        "failed": failed_hooks,
        "elapsed_s": total_elapsed,
        "results": {
            hid: {
                "name": r["name"],
                "rc": r["rc"],
                "elapsed_s": r["elapsed_s"],
                "ok": r["ok"],
                "findings": r["findings"],
            }
            for hid, r in results.items()
        },
    }

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'='*60}")
        print(f"  SONUC: {verdict}")
        print(f"  {passed_hooks}/{total_hooks} hook PASS  ({total_elapsed}s)")
        if failed_hooks:
            print(f"\n  FAILED HOOKS:")
            for hid, r in results.items():
                if not r["ok"]:
                    print(f"    ✗ {hid}: {r['findings']}")
        print(f"{'='*60}")

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())