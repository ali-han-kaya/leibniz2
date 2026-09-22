#!/usr/bin/env python3
"""gh_run_rca.py — GitHub Actions kırmızı-koşum kök-neden analizi (RCA).

Amaç: kırmızı koşumun `gh run view <id> --log-failed` çıktısını kural-
tablosuyla sınıflandırıp insan-okur bir kök-neden tablosu üretmek
(RULE, JOB, STEP, KÖK-NEDEN KANITI, REMEDY). Akış otomasyonu:

    # son kırmızı koşumun RCA'sı:
    python3 _calisma/CIKTI/gh_run_rca.py --branch "$(git branch --show-current)"
    python3 _calisma/CIKTI/gh_run_rca.py --run <run-id> --out rca.md
    # hazır log üstünde (gh'siz):
    python3 _calisma/CIKTI/gh_run_rca.py --log-file failed.log

Çıkış-kodu: 0 = koşum kırmızı değil/analiz-gereksiz, 1 = kırmızı (tablo
üretildi + hedefli remedy), 2 = kullanım/ortam hatası (gh yok, log-okunamaz
— fail-closed: sessiz-çözümleme yok).

Sınıflandırma RULES'tadır (özel → genel): manifest-drift < octokit < trivy
< timeout < unittest < failure_summary < hook < exit-code. İlk eşleşen
kural kazanır; hiçbiri eşleşmezse fail-closed değil — exit-code kanonu
genel yakalayıcıdır, o da yoksa koşum log'da kırmızı-kanıt taşımıyordur.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (ad, desen, remedy) — ÖZELDEN GENERELE sıralı; test sıra-sözleşmesi pinli.
RULES = [
    ("manifest-drift",
     r"manifest/HOOK_COVERAGE drift",
     "python3 _calisma/CIKTI/sync_check_unit_tests.py --update (sonra zinciri tekrar koş)"),
    ("octokit",
     r"bilinmeyen Octokit metodu",
     "Script'i izinli Octokit-metot listesiyle sınırla (audit_octokit_names kanonu)"),
    ("trivy",
     r"Trivy.*SARIF.*(bulunamadı|bozuk)|Scan image with Trivy.*Failed",
     "docker-security SARIF-adımını + image-ref'i doğrula; bozuk SARIF fail-closed'tur"),
    ("timeout",
     r"exceeded the maximum execution time",
     "workflow'da timeout-minutes'u yükselt veya job'u böl"),
    ("unittest",
     r"^(?:FAIL|ERROR): \S+|FAILED \((?:failures|errors)=\d+\)",
     "Başarısız testi tekil koş: python3 -m unittest <modul>.<Test>.<test_adı>"),
    ("failure_summary",
     r"\bFAILED\b",
     "FAILED satırındaki bileşenin kendi sözleşme-süitini yerelde koş"),
    ("hook",
     r"- hook id: \S+",
     "pre-commit run --all-files ile yerelde yeniden üret"),
    ("exit-code",
     r"##\[error\]|Process completed with exit code \d+",
     "Adım-log'unu satır-bazında incele (gh run view --log-failed)"),
]

COLUMNS = ["RULE", "JOB", "STEP", "KÖK-NEDEN KANITI", "REMEDY"]
_EVIDENCE_MAX = 160


def _gh(argv):
    """Gerçek gh çağırımı — testler rca.GH'yi değiştirerek mock'lar."""
    proc = subprocess.run(["gh"] + argv, capture_output=True, text=True)
    return proc.returncode, proc.stdout if proc.returncode == 0 else proc.stderr


# Test-enjeksiyonu için modül-global: main() bunu kullanır.
GH = _gh


def analyze_log(text):
    """Log-metnini RULES'e göre sınıflandır.

    Döner: (kanıt-satırları, kural-adı|None). Kanıt: eşleşen satırlar
    (uzunluk-kırpılmış). Birden çok kural eşleşirse EN ÖZEL kazanır
    (RULES sırası); eşleşme yoksa ([], None).
    """
    lines = text.splitlines()
    for name, pattern, _remedy in RULES:
        rx = re.compile(pattern, re.MULTILINE)
        ev = []
        for ln in lines:
            if rx.search(ln):
                ev.append(ln.strip()[:_EVIDENCE_MAX])
        if ev:
            return ev, name
    return [], None


def _remedy(rule):
    for name, _pattern, remedy in RULES:
        if name == rule:
            return remedy
    return ""


def build_table(findings):
    """Bulgu-dict'lerinden deterministik tablo-satırları üret.

    Sıralama: (RULE, JOB, STEP) — kolon-adlarından bağımsız sabit-key
    (kolon-adı Türkçe; sort kolon-değerlerinde, adlarda değil).
    """
    rows = []
    for f in findings:
        rows.append({
            "RULE": f["rule"],
            "JOB": f.get("job") or "-",
            "STEP": f.get("step") or "-",
            "KÖK-NEDEN KANITI": (f.get("err") or "").replace("|", "\\|"),
            "REMEDY": _remedy(f["rule"]).replace("|", "\\|"),
        })
    rows.sort(key=lambda r: (r["RULE"], r["JOB"], r["STEP"]))
    return rows


def _fetch_failed_log(run_id, gh):
    """gh run view: önce jobs-JSON (JOB/STEP çözümü), sonra --log-failed."""
    rc, out = gh(["run", "view", str(run_id), "--json", "jobs"])
    if rc != 0:
        return None, None, out
    try:
        meta = json.loads(out)
    except json.JSONDecodeError:
        return None, None, "jobs-JSON parse edilemedi"
    failed_steps, failed_jobs = [], []
    for job in meta.get("jobs", []):
        if job.get("conclusion") == "failure":
            failed_jobs.append(job.get("name") or "")
            for st in job.get("steps", []):
                if st.get("conclusion") == "failure":
                    failed_steps.append(st.get("name") or "")
    rc, out = gh(["run", "view", str(run_id), "--log-failed"])
    if rc != 0:
        return None, failed_jobs, out
    return out, failed_jobs or failed_steps, ""


def _render(rows, meta, dest):
    """Markdown rapor: meta-başlık + tablo (dosyaya veya stdout)."""
    head = ["# GH-Run Kök-Neden Analizi", ""]
    for k, v in meta.items():
        head.append(f"- **{k}:** {v}")
    head += ["", "| " + " | ".join(COLUMNS) + " |",
             "|" + "|".join(["---"] * len(COLUMNS)) + "|"]
    for r in rows:
        head.append("| " + " | ".join(r[c] for c in COLUMNS) + " |")
    body = "\n".join(head) + "\n"
    if dest:
        with open(dest, "w", encoding="utf-8") as f:
            f.write(body)
    else:
        sys.stdout.write(body)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Kırmızı GH-koşumu kök-neden tablosuna dök (fail-closed)")
    ap.add_argument("--run", help="gh run id (gh CLI ister)")
    ap.add_argument("--branch", help="dalın son kırmızı koşumunu bul (gh ister)")
    ap.add_argument("--log-file", help="hazır --log-failed çıktısı (gh'siz)")
    ap.add_argument("--out", help="raporu bu yola yaz (default: stdout)")
    args = ap.parse_args(argv)

    job_label, step_label, meta = "-", "-", {}

    if args.log_file:
        try:
            with open(args.log_file, encoding="utf-8") as f:
                log = f.read()
        except OSError as e:
            sys.stderr.write(f"RCA: log okunamadı: {e}\n")
            return 2
        meta["kaynak"] = args.log_file
    elif args.run or args.branch:
        if GH is None or shutil.which("gh") is None and GH is _gh:
            sys.stderr.write("RCA: gh CLI yok — rc=2 (fail-closed)\n")
            return 2
        if args.branch:
            rc, out = GH(["run", "list", "--branch", args.branch,
                          "--status", "failure", "--limit", "1",
                          "--json", "databaseId"])
            if rc != 0 or not out.strip().startswith("["):
                sys.stderr.write(f"RCA: koşum-bulma başarısız: {out[:200]}\n")
                return 2
            try:
                runs = json.loads(out)
            except json.JSONDecodeError:
                return 2
            if not runs:
                sys.stdout.write("RCA: dalda kırmızı koşum yok — rc=0\n")
                return 0
            args.run = runs[0]["databaseId"]
        log, failed_labels, err = _fetch_failed_log(args.run, GH)
        if log is None:
            sys.stderr.write(f"RCA: gh run view başarısız: {err[:200]}\n")
            return 2
        if failed_labels:
            job_label = failed_labels[0]
            step_label = failed_labels[0] if len(failed_labels) == 1 \
                else f"{len(failed_labels)} adım/job"
        meta["run"] = args.run
    else:
        ap.error("--run, --branch veya --log-file gerekli")

    meta["tarih"] = os.environ.get("RCA_DATE", "")
    ev, rule = analyze_log(log)
    if not rule:
        sys.stdout.write("RCA: log'da kırmızı-kanıt deseni yok — rc=0\n")
        return 0
    findings = [{"rule": rule, "job": job_label, "step": step_label,
                 "err": ev[0] if ev else ""}]
    _render(build_table(findings), meta, args.out)
    return 1


if __name__ == "__main__":
    sys.exit(main())
