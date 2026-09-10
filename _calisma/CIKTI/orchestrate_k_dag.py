#!/usr/bin/env python3
"""K1-K12 task DAG orchestration — opencode worker'ları ile (fail-closed).

Her DAG düğümü (K1..K12) bir "worker task"tır. Orkestratör:
  1. task'ın gerçek komutunu çalıştırır (script_rc = zemin gerçeği),
  2. çıktıyı opencode worker'a (non-interactive `run`, stdin kapalı) gönderir;
     worker `worker_done.json` sidecar'ına {status, summary} yazar,
  3. script_rc + worker görüşünü BİRLEŞTİRİR — ikisi de PASS değilse task FAIL,
  4. tüm sidecar'ları DAG sırasında toplayıp fail-closed rapor üretir.

Exit sözleşmesi: herhangi bir task FAIL/ERROR → exit 1; hepsi PASS → exit 0.

worker_done birleştirme: done_dir/worker_K{n}.json dosyaları okunur; eksik
sidecar → ERROR (fail-closed — worker yanıt vermeden akış tamamlanmaz).

Kullanım:
  python3 orchestrate_k_dag.py [--worktree PATH] [--done-dir PATH] [--model M]
                               [--mock] [--parallel N] [--timeout S]
"""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────────────────────────────
# K1-K12 task DAG — her düğüm: gerçek komut + opencode worker prompt'u.
# Bağımlılıklar: bir task ancak tüm deps'i PASS olduktan sonra koşar.
# ─────────────────────────────────────────────────────────────────────
TASKS = [
    # (id, label, command, deps)
    ("K1",  "Mirror/çalışma ağacı bütünlüğü",
     "python3 _calisma/CIKTI/check_mirror_coverage.py", []),
    ("K2",  "Python3-shell denetimi",
     "python3 _calisma/CIKTI/check_python3_shell.py", ["K1"]),
    ("K3",  "Action pin denetimi",
     "python3 _calisma/CIKTI/check_action_pins.py", ["K2"]),
    ("K4",  "Status checks / branch protection",
     "python3 _calisma/CIKTI/status_checks.py", ["K3"]),
    ("K5",  "Doc↔workflow senkronu",
     "python3 _calisma/CIKTI/check_doc_wrapper_sync.py", []),
    ("K6",  "Referans kanıtı (refs)",
     "python3 _calisma/CIKTI/audit_refs_trend.py --offline", []),
    ("K7",  "Lean reduct çekirdeği",
     "grep -n '^theorem' _calisma/lean_reduct/Content.lean", []),
    ("K8",  "Z3 sembolik ispat",
     "python3 _calisma/CIKTI/symbolic_proof_z3.py --check", ["K7"]),
    ("K9",  "Lean ispat (lake build)",
     "python3 _calisma/CIKTI/verify_delivery.py --check-lean-proof", ["K8"]),
    ("K10", "Reproducibility manifest",
     "python3 _calisma/CIKTI/verify_delivery.py --verify-manifest", ["K1", "K5"]),
    ("K11", "Soy hattı (lineage)",
     "python3 _calisma/CIKTI/verify_delivery.py --check-lineage", ["K10"]),
    ("K12", "Plist drift kapısı",
     "python3 _calisma/CIKTI/check_plist_drift.py", ["K1"]),
]

DONE_FILENAME = "worker_done_{task}.json"
RAPOR_MD = "ORCHESTRATION_RAPORU.md"
RAPOR_JSON = "orchestration_report.json"


def task_map():
    return {t[0]: {"id": t[0], "label": t[1], "command": t[2], "deps": t[3]}
            for t in TASKS}


def _ts():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def run_command(cmd, cwd, timeout):
    """Gerçek task komutunu koşar → (rc, stdout_tail)."""
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out[-4000:]
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or "")[-4000:]


def _locate_opencode():
    # PATH'te ara (mutlak yol hardcode etme — check-absolute-paths).
    return shutil.which("opencode")


def opencode_worker(task, worktree, done_dir, model, timeout, mock=False):
    """Bir task'ı opencode worker'a gönderir; worker_done sidecar'ı yazar.

    - mock=False: `opencode run` (stdin DEVNULL — docs/OPENCODE_RUN_HANG.md
      kök neden workaround'u) çalıştırılır; worker çıktıya bakıp
      done_dir/worker_done_K{n}.json yazar.
    - mock=True : opencode çağrılmaz; script_rc'den deterministik sidecar
      üretilir (birim testler / ağsız ortam).
    """
    tid = task["id"]
    done_path = pathlib.Path(done_dir) / DONE_FILENAME.format(task=tid)

    # 1) Zemin gerçeği: task komutu
    rc, out = run_command(task["command"], worktree, timeout)
    script_ok = (rc == 0)

    if mock:
        status = "PASS" if script_ok else "FAIL"
        sidecar = {
            "task": tid, "label": task["label"], "status": status,
            "rc": rc, "summary": ("komut rc=%d" % rc),
            "detail": out[-800:], "started_at": _ts(), "finished_at": _ts(),
            "duration_s": 0.0, "worker": "mock",
        }
        done_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        return sidecar

    # 2) opencode worker çağrısı — prompt, komut çıktısı + sidecar yazma
    #    talimatını içerir. rc=0 olsa bile script rc'si ayrıca birleştirilir
    #    (fail-closed: worker yanlış PASS dese bile script_rc!=0 → FAIL).
    payload = json.dumps({'task': tid, 'label': task['label'],
                         'status': 'PASS|FAIL', 'summary': 'tek cümle',
                         'rc': rc}, ensure_ascii=False)
    prompt = (
        f"Sen K{tid} worker'sın. Handoff worktree'sinde şu komutu çalıştırdım:\n"
        f"  {task['command']}\n"
        f"Exit rc={rc}.\n--- ÇIKTI (tail) ---\n{out}\n--- GÖREV ---\n"
        f"Şu dosyayı OLUŞTUR (kesinlikle cevap olarak JSON yazma, dosyayı yaz):\n"
        f"  {done_path}\n"
        f"Dosya içeriği şu geçerli JSON olsun:\n{payload}\n"
        f"status: script rc=0 ise genelde PASS, ama çıktıda bariz hata "
        f"görüyorsan FAIL yaz. PASS veya FAIL'dan başka değer yazma. "
        f"Dosyayı yazdıktan sonra yalnızca 'done' yaz."
    )

    def _invoke(opencode_bin, prompt_text):
        try:
            p = subprocess.run([opencode_bin, "run", prompt_text], cwd=worktree,
                               stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, timeout=timeout)
            return p.stdout or ""
        except subprocess.TimeoutExpired:
            return ""

    t0 = time.time()
    oc_out = ""
    oc_bin = _locate_opencode()
    if oc_bin:
        oc_out = _invoke(oc_bin, prompt)
    dt = time.time() - t0

    # 3) worker_done birleştirme. Öncelik: (a) dosya yazıldıysa oku,
    #    (b) dosya yoksa opencode stdout'undan JSON bloğu çıkar,
    #    (c) o da yoksa TEK RETRY: model soru sorduysa (non-interactive'te
    #    yanıt alamaz) kesin talimatla tekrar dene,
    #    (d) yine yoksa ERROR (fail-closed) — worker yanıt vermedi.
    def _parse_sidecar(out_text):
        if done_path.is_file():
            try:
                s = json.loads(done_path.read_text(encoding="utf-8"))
                if isinstance(s, dict) and "status" in s:
                    return s
            except (ValueError, OSError):
                pass
        if out_text:
            start, end = out_text.find("{"), out_text.rfind("}")
            if 0 <= start < end:
                try:
                    cand = json.loads(out_text[start:end + 1])
                    if isinstance(cand, dict) and "status" in cand:
                        return cand
                except ValueError:
                    pass
        return None

    sidecar = _parse_sidecar(oc_out)
    if sidecar is None and oc_bin and dt < timeout - 5:
        # Retry: rc'den status'ü biz belirleriz; modele yalnızca dosyayı
        # yazması kalır — soru sorma ihtimali yok.
        retry_payload = json.dumps(
            {'task': tid, 'label': task['label'],
             'status': 'FAIL' if rc != 0 else 'PASS',
             'summary': 'komut rc=%d' % rc, 'rc': rc}, ensure_ascii=False)
        retry_prompt = (
            f"SORU SORMA, karar verilmiş: status '{'FAIL' if rc != 0 else 'PASS'}'.\n"
            f"Şu dosyayı OLUŞTUR (geçerli JSON içerikle): {done_path}\n"
            f"İçerik: {retry_payload}\nDosyayı yazdıktan sonra 'done' yaz."
        )
        t1 = time.time()
        oc_out2 = _invoke(oc_bin, retry_prompt)
        dt += time.time() - t1
        sidecar = _parse_sidecar(oc_out2)

    if sidecar is None:
        sidecar = {
            "task": tid, "label": task["label"], "status": "ERROR",
            "rc": rc, "summary": "worker_done sidecar'ı yazılmadı (worker yanıt vermedi)",
            "detail": (oc_out or out)[-800:], "started_at": _ts(),
            "finished_at": _ts(), "duration_s": round(dt, 2),
            "worker": "opencode",
        }
        done_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        return sidecar

    # Fail-closed birleştirme: script rc'si zemin gerçeğidir — worker
    # yanlış PASS dese bile script rc!=0 ise task FAIL sayılır.
    if rc != 0:
        sidecar["status"] = "FAIL"
        sidecar["summary"] = (sidecar.get("summary", "") +
                              " [script rc=%d → FAIL]" % rc)
    sidecar.setdefault("duration_s", round(dt, 2))
    sidecar.setdefault("started_at", _ts())
    sidecar.setdefault("finished_at", _ts())
    sidecar.setdefault("worker", "opencode")
    # Birleştirilmiş sidecar'ı dosyaya geri yaz (artifact tek kaynak)
    done_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return sidecar


def topological_levels(tm):
    """DAG'i seviyelere böler: aynı seviyedekiler paralel koşabilir."""
    done, levels = set(), []
    while len(done) < len(tm):
        level = [t for t in tm.values()
                 if t["id"] not in done and all(d in done for d in t["deps"])]
        if not level:
            raise RuntimeError("DAG döngüsü var — kalan: %s"
                               % sorted(set(tm) - done))
        levels.append(level)
        done |= {t["id"] for t in level}
    return levels


def main(argv=None):
    ap = argparse.ArgumentParser(description="K1-K12 task DAG orchestration")
    ap.add_argument("--worktree", default=os.getcwd(),
                    help="handoff worktree yolu (varsayılan: cwd)")
    ap.add_argument("--done-dir", default=None,
                    help="worker_done sidecar dizini (varsayılan: worktree/.orchestration)")
    ap.add_argument("--model", default=None, help="opencode model adı")
    ap.add_argument("--mock", action="store_true",
                    help="opencode yerine deterministik stub worker (test)")
    ap.add_argument("--parallel", type=int, default=2,
                    help="aynı seviyede paralel worker sayısı")
    ap.add_argument("--timeout", type=int, default=120, help="worker zaman aşımı (sn)")
    ap.add_argument("--only", default=None,
                    help="yalnızca şu task'ları koş (virgüllü, örn: K1,K2)")
    args = ap.parse_args(argv)

    worktree = str(pathlib.Path(args.worktree).resolve())
    done_dir = args.done_dir or os.path.join(worktree, ".orchestration")
    os.makedirs(done_dir, exist_ok=True)

    tm = task_map()
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        tm = {k: v for k, v in tm.items() if k in wanted}
    # Bağımlılık tutarlılığı: wanted dışı dep → o task'ı da al
    for tid, t in list(tm.items()):
        for d in t["deps"]:
            if d not in tm and d in task_map():
                tm[d] = task_map()[d]

    results = {}
    failures = []
    levels = topological_levels(tm)
    for level in levels:
        # Fail-closed: dep'i FAIL/ERROR/SKIP olan task'lar worker'a
        # gönderilmez (bozuk girdiyle çalıştırmanın anlamı yok) → SKIP.
        runnable = []
        for t in level:
            bad_deps = [d for d in t["deps"]
                        if results.get(d, {}).get("status") != "PASS"]
            if bad_deps:
                sidecar = {
                    "task": t["id"], "label": t["label"], "status": "SKIP",
                    "rc": None, "summary": "dep başarısız: %s" % ",".join(bad_deps),
                    "started_at": _ts(), "finished_at": _ts(),
                    "duration_s": 0.0, "worker": "orkestratör",
                }
                sp = os.path.join(done_dir, DONE_FILENAME.format(task=t["id"]))
                with open(sp, "w", encoding="utf-8") as f:
                    json.dump(sidecar, f, ensure_ascii=False, indent=2)
                results[t["id"]] = sidecar
                failures.append(t["id"])
            else:
                runnable.append(t)
        with ThreadPoolExecutor(max_workers=min(args.parallel, len(runnable) or 1)) as ex:
            futs = {ex.submit(opencode_worker, t, worktree, done_dir,
                              args.model, args.timeout, args.mock): t["id"]
                    for t in runnable}
            for fut in as_completed(futs):
                tid = futs[fut]
                try:
                    sidecar = fut.result()
                except Exception as e:  # noqa: BLE001 — fail-closed
                    sidecar = {"task": tid, "status": "ERROR",
                               "summary": "worker istisnası: %r" % e}
                results[tid] = sidecar
                if sidecar.get("status") != "PASS":
                    failures.append(tid)

    # ── Fail-closed rapor ────────────────────────────────────────────
    order = [t["id"] for lv in levels for t in lv]
    lines = [
        "# K1-K12 Orchestration Raporu",
        "",
        "- Tarih: %s" % _ts(),
        "- Worktree: `%s`" % worktree,
        "- Worker: %s" % ("mock (stub)" if args.mock
                          else ("opencode (%s)" % (args.model or "varsayılan"))),
        "- Sonuç: **%s**" % ("PASS" if not failures else "FAIL"),
        "",
        "| Task | Durum | rc | Özet |",
        "|---|---|---|---|",
    ]
    for tid in order:
        r = results.get(tid, {})
        st = r.get("status", "MISSING")
        rc = r.get("rc", "—")
        summary = (r.get("summary") or "").replace("|", "/").replace("\n", " ")
        lines.append("| %s | %s | %s | %s |" % (tid, st, rc, summary[:100]))

    report = "\n".join(lines) + "\n"
    md_path = os.path.join(done_dir, RAPOR_MD)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report)

    json_path = os.path.join(done_dir, RAPOR_JSON)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "verdict": "PASS" if not failures else "FAIL",
            "run_at": _ts(), "worktree": worktree,
            "mock": args.mock, "model": args.model,
            "tasks": {tid: results.get(tid, {"status": "MISSING"})
                      for tid in order},
            "failures": failures,
        }, f, ensure_ascii=False, indent=2)

    print(report)
    if failures:
        print("FAIL-CLOSED: başarısız task'lar: %s" % ", ".join(failures),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
