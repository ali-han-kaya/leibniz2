#!/usr/bin/env python3
"""repack→verify→manifest→CI coordinator loop — opencode decision-gate zinciri.

Dört kapı sırayla açılır; her kapı yalnızca bir önceki açıksa denenir
(fail-closed decision-gate zinciri):

  Gate 1 REPACK  — repack_delivery.py --verify (zip + SHA-256 sidecar bütünlüğü)
  Gate 2 VERIFY  — verify_delivery.py --full (K1-K14, verdict PASS)
  Gate 3 MANIFEST— gen_repro_manifest.py + verify_delivery.py --verify-manifest (K10)
  Gate 4 CI      — GitHub Actions: workflow run + run watch (--live-ci) veya
                   salt-okunur `gh run list` sağlık kontrolü (varsayılan)

Her kapıda:
  1. komut çalıştırılır (script_rc = zemin gerçeği),
  2. opencode worker çıktıyı inceler ve gate_done_{GATE}.json'a
     {gate, status: PASS|FAIL, rationale} yazar (stdin DEVNULL —
     docs/OPENCODE_RUN_HANG.md workaround'u),
  3. script_rc != 0 ise worker ne derse desin kapı FAIL (fail-closed).

Loop: CI kapısı FAIL olursa --iterations'a kadar başa dönülür (düzeltme
döngüsü). Tüm kapılar açılırsa → PASS, exit 0. Herhangi bir kapı kapanırsa
ve iterasyon bittiyse → exit 1.

Kullanım:
  python3 coordinator_loop.py [--worktree PATH] [--done-dir PATH] [--model M]
                              [--mock] [--iterations N] [--timeout S] [--live-ci]
"""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

GATE_ORDER = ["REPACK", "VERIFY", "MANIFEST", "CI"]

GATES = {
    "REPACK": {
        "label": "Deterministik yeniden paketleme + zip bütünlüğü",
        "command": "python3 _calisma/repack_delivery.py --verify",
    },
    "VERIFY": {
        "label": "K1-K14 doğrulama zinciri (verdict PASS)",
        "command": "python3 _calisma/CIKTI/verify_delivery.py --full",
    },
    "MANIFEST": {
        "label": "Reproducibility manifest + K10 --verify-manifest",
        "command": ("python3 _calisma/CIKTI/gen_repro_manifest.py && "
                    "python3 _calisma/CIKTI/verify_delivery.py --verify-manifest"),
    },
    "CI": {
        "label": "GitHub Actions CI (workflow run + watch)",
        # Varsayılan salt-okunur: dış dünyaya push/trigger YOK. --live-ci ile
        # gerçek dispatch + watch yapılır.
        "command_readonly": "gh run list --limit 1 --json databaseId,status,conclusion",
        "command_live": "gh workflow run verify.yml && "
                        "gh run watch --exit-status --interval 10",
    },
}

DONE_FILENAME = "gate_done_{gate}.json"
RAPOR_MD = "COORDINATOR_RAPORU.md"
RAPOR_JSON = "coordinator_report.json"


def _ts():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def run_command(cmd, cwd, timeout):
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out[-4000:]
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or "")[-4000:]


def _invoke_opencode(bin_path, prompt, cwd, timeout):
    try:
        p = subprocess.run([bin_path, "run", prompt], cwd=cwd,
                           stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=timeout)
        return p.stdout or ""
    except subprocess.TimeoutExpired:
        return ""


def _locate_opencode():
    # PATH'te ara (mutlak yol hardcode etme — check-absolute-paths).
    return shutil.which("opencode")


def decide_gate(gate, worktree, done_dir, model, timeout, mock, live_ci):
    """Bir kapıyı çalıştırır ve worker kararıyla birleştirir → sidecar."""
    spec = GATES[gate]
    if gate == "CI":
        cmd = spec["command_live"] if live_ci else spec["command_readonly"]
    else:
        cmd = spec["command"]
    done_path = pathlib.Path(done_dir) / DONE_FILENAME.format(gate=gate)

    rc, out = run_command(cmd, worktree, timeout)
    script_ok = (rc == 0)

    if mock:
        sidecar = {"gate": gate, "label": spec["label"], "status":
                   "PASS" if script_ok else "FAIL",
                   "rc": rc, "rationale": "komut rc=%d" % rc,
                   "detail": out[-800:], "started_at": _ts(),
                   "finished_at": _ts(), "duration_s": 0.0, "worker": "mock"}
        done_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        return sidecar

    payload = json.dumps({"gate": gate, "label": spec["label"],
                          "status": "PASS|FAIL", "rationale": "tek cümle",
                          "rc": rc}, ensure_ascii=False)
    prompt = (
        f"Sen {gate} kapısının decision-gate inceleyicisisin. Şu komut koştu:\n"
        f"  {cmd}\nExit rc={rc}.\n--- ÇIKTI (tail) ---\n{out}\n--- GÖREV ---\n"
        f"Şu dosyayı OLUŞTUR (kesinlikle cevap olarak JSON yazma): {done_path}\n"
        f"İçerik (geçerli JSON): {payload}\n"
        f"status: rc=0 ise genelde PASS; çıktıda bariz hata/verdict FAIL "
        f"görüyorsan FAIL yaz. Başka değer yazma. Yazdıktan sonra 'done' yaz."
    )

    t0 = time.time()
    oc_bin = _locate_opencode()
    oc_out = _invoke_opencode(oc_bin, prompt, worktree, timeout) if oc_bin else ""
    dt = time.time() - t0

    def _parse():
        if done_path.is_file():
            try:
                s = json.loads(done_path.read_text(encoding="utf-8"))
                if isinstance(s, dict) and "status" in s:
                    return s
            except (ValueError, OSError):
                pass
        if oc_out:
            a, b = oc_out.find("{"), oc_out.rfind("}")
            if 0 <= a < b:
                try:
                    cand = json.loads(oc_out[a:b + 1])
                    if isinstance(cand, dict) and "status" in cand:
                        return cand
                except ValueError:
                    pass
        return None

    sidecar = _parse()
    if sidecar is None and oc_bin and dt < timeout - 5:
        retry = json.dumps({"gate": gate, "label": spec["label"],
                            "status": "FAIL" if rc else "PASS",
                            "rationale": "komut rc=%d" % rc, "rc": rc},
                           ensure_ascii=False)
        t1 = time.time()
        oc_out2 = _invoke_opencode(oc_bin, (
            f"SORU SORMA, karar verilmiş: status "
            f"'{'FAIL' if rc else 'PASS'}'. Dosyayı OLUŞTUR: {done_path}\n"
            f"İçerik: {retry}\nYazdıktan sonra 'done' yaz."), worktree, timeout)
        dt += time.time() - t1
        sidecar = _parse()

    if sidecar is None:
        sidecar = {"gate": gate, "label": spec["label"], "status": "ERROR",
                   "rc": rc, "rationale": "worker yanıt vermedi",
                   "detail": (oc_out or out)[-800:], "started_at": _ts(),
                   "finished_at": _ts(), "duration_s": round(dt, 2),
                   "worker": "opencode"}
        done_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        return sidecar

    # Fail-closed: script rc zemin gerçeğidir
    if rc != 0:
        sidecar["status"] = "FAIL"
        sidecar["rationale"] = (sidecar.get("rationale", "") +
                                " [script rc=%d → FAIL]" % rc)
    sidecar.setdefault("duration_s", round(dt, 2))
    sidecar.setdefault("started_at", _ts())
    sidecar.setdefault("finished_at", _ts())
    sidecar.setdefault("worker", "opencode")
    done_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return sidecar


def main(argv=None):
    ap = argparse.ArgumentParser(description="repack→verify→manifest→CI loop")
    ap.add_argument("--worktree", default=os.getcwd())
    ap.add_argument("--done-dir", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--iterations", type=int, default=1,
                    help="CI başarısızsa başa dönme sayısı")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--live-ci", action="store_true",
                    help="CI kapısında gerçek gh workflow run + watch")
    args = ap.parse_args(argv)

    worktree = str(pathlib.Path(args.worktree).resolve())
    done_dir = args.done_dir or os.path.join(worktree, ".coordinator")
    os.makedirs(done_dir, exist_ok=True)

    all_iterations = []
    final_rc = 1
    for it in range(1, args.iterations + 1):
        results, opened, closed = {}, [], []
        for gate in GATE_ORDER:
            sidecar = decide_gate(gate, worktree, done_dir, args.model,
                                  args.timeout, args.mock, args.live_ci)
            results[gate] = sidecar
            if sidecar.get("status") == "PASS":
                opened.append(gate)
            else:
                closed.append(gate)
                break  # decision-gate zinciri: ilk kapalı kapıda dur
        iter_rec = {"iteration": it, "gates": results,
                    "opened": opened, "closed": closed,
                    "verdict": "PASS" if not closed else "FAIL"}
        all_iterations.append(iter_rec)
        if not closed:
            final_rc = 0
            break  # tüm kapılar açıldı → döngü bitti
        print("Iterasyon %d: kapı kapandı %s → başa dön" %
              (it, ",".join(closed)), file=sys.stderr)

    # ── Rapor ─────────────────────────────────────────────────────────
    lines = [
        "# Coordinator Raporu (repack→verify→manifest→CI)",
        "",
        "- Tarih: %s" % _ts(),
        "- Worktree: `%s`" % worktree,
        "- Worker: %s" % ("mock (stub)" if args.mock
                          else "opencode (%s)" % (args.model or "varsayılan")),
        "- CI modu: %s" % ("LIVE (workflow run + watch)" if args.live_ci
                           else "readonly (gh run list)"),
        "- Iterasyonlar: %d" % len(all_iterations),
        "- Sonuç: **%s**" % ("PASS" if final_rc == 0 else "FAIL"),
        "",
        "| İterasyon | Kapı | Durum | rc | Gerekçe |",
        "|---|---|---|---|---|",
    ]
    for rec in all_iterations:
        for gate in GATE_ORDER:
            if gate not in rec["gates"]:
                continue
            s = rec["gates"][gate]
            rat = (s.get("rationale") or "").replace("|", "/").replace("\n", " ")
            lines.append("| %d | %s | %s | %s | %s |" %
                         (rec["iteration"], gate, s.get("status"), s.get("rc"),
                          rat[:90]))
    report = "\n".join(lines) + "\n"
    with open(os.path.join(done_dir, RAPOR_MD), "w", encoding="utf-8") as f:
        f.write(report)
    with open(os.path.join(done_dir, RAPOR_JSON), "w", encoding="utf-8") as f:
        json.dump({"verdict": "PASS" if final_rc == 0 else "FAIL",
                   "run_at": _ts(), "worktree": worktree,
                   "mock": args.mock, "live_ci": args.live_ci,
                   "iterations": all_iterations}, f,
                  ensure_ascii=False, indent=2)

    print(report)
    return final_rc


if __name__ == "__main__":
    sys.exit(main())
