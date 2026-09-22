#!/usr/bin/env python3
"""deploy_evidence.py — kalıcı dağıtım/deploy kanıtı defteri (fail-closed).

Hattın son koşumlarını denetleyip çekirdek-workflow'ların main-dalı
son koşumlarını `docs/DEPLOY_EVIDENCE.md`'ye **append-only** yazar.
Defter repo-gelenekleriyle tek-kaynaklıdır: bu betik tek yazar;
`--check` bayat-kanıt korumasıdır (son satır HEAD'i ≠ origin/main ucu
→ rc=1; CI-daemon /api/latest'de görünür, rapor-devirleri bayat kanıt
taşıyamaz).

Çıkış-kodu: 0 = satır eklendi veya defter güncel; 1 = bayat (check);
2 = kullanım/ortam hatası (gh yok, gh-hata, HTTP-hata — sessiz-PASS yok).

    python3 _calisma/CIKTI/deploy_evidence.py            # ekle + yaz
    python3 _calisma/CIKTI/deploy_evidence.py --check    # bayat-mi?
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
LEDGER = os.path.join(REPO, "docs", "DEPLOY_EVIDENCE.md")

# Çekirdek teslim-hattı workflow'ları (defter-kolonları).
WORKFLOWS = ["verify.yml", "docker-security.yml", "test-smoke.yml",
             "determinism-trend.yml"]

LEDGER_HEADERS = ("| Tarih | HEAD (origin/main) | verify-delivery |"
                  " docker-security | test-smoke | determinism-trend |")
LEDGER_SEP = "|---|---|---|---|---|---|"


def _gh(argv):
    proc = subprocess.run(["gh"] + argv, capture_output=True, text=True)
    return proc.returncode, proc.stdout if proc.returncode == 0 else proc.stderr


# Test-enjeksiyonu için modül-global (gh_run_rca deseni).
GH = _gh


def collect(branch, gh):
    """(ev, hata) döner: ev=None → ortam-hatası (rc=2)."""
    rc, out = gh(["api", "repos/{owner}/{repo}/commits/main", "--jq",
                  ".sha"])
    if rc != 0:
        return None, f"origin/main okunamadı: {out.strip()[:160]}"
    out = out.strip()
    try:
        # GitHub-API ham-yapısı: tırnaklı JSON-string
        sha = json.loads(out)
    except json.JSONDecodeError:
        # gh --jq .sha çıktısı: bare-hex (JSON-değil) — gerçek-kanıt şekli
        sha = out
    if not (isinstance(sha, str) and len(sha) == 40
            and all(c in "0123456789abcdef" for c in sha)):
        return None, "beklenmeyen origin/main yanıtı"

    runs = {}
    for wf in WORKFLOWS:
        rc, out = gh(["run", "list", "--workflow", wf, "--branch", branch,
                      "--limit", "1", "--json",
                      "databaseId,conclusion,headSha,url"])
        if rc != 0:
            return None, f"{wf} koşum-listesi başarısız: {out.strip()[:120]}"
        try:
            arr = json.loads(out)
        except json.JSONDecodeError:
            return None, f"{wf} koşum-JSON parse edilemedi"
        runs[wf] = arr[0] if arr else None  # koşum-yok dürüstçe None
    return {"sha": sha, "runs": runs}, ""


def _cell(run):
    if run is None:
        return "koşum-yok"
    return f"[{run['conclusion']} #{run['databaseId']}]({run['url']})"


def append_entry(path, today, ev):
    """Deftere tek satır ekle (append-only; başlıklar yoksa kur)."""
    cells = [today, ev["sha"][:7]] + \
        [_cell(ev["runs"].get(wf)) for wf in WORKFLOWS]
    row = "| " + " | ".join(cells) + " |"
    lines = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as data:
            lines = data.read().splitlines()
    sep_i = next((i for i, ln in enumerate(lines) if ln == LEDGER_SEP), None)
    if sep_i is None:
        lines += ["## Kanıt-defteri", "", LEDGER_HEADERS, LEDGER_SEP]
    lines.append(row)
    content = "\n".join(lines) + "\n"
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def last_sha(path):
    """Defterin son kanıt-satırının HEAD'i (satır-yoksa '')."""
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        rows = [ln for ln in f if ln.startswith("| 2")]
    if not rows:
        return ""
    return rows[-1].split("|")[2].strip()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Çekirdek-workflow son-koşum kanıtını deftere işle")
    ap.add_argument("--check", action="store_true",
                    help="defter güncel mi (son HEAD == origin/main ucu)?")
    args = ap.parse_args(argv)

    if shutil.which("gh") is None:
        sys.stderr.write("deploy-evidence: gh CLI yok — rc=2 (fail-closed)\n")
        return 2

    branch = "main"
    ev, err = collect(branch, GH)
    if ev is None:
        sys.stderr.write(f"deploy-evidence: {err}\n")
        return 2

    if args.check:
        fresh = last_sha(LEDGER) == ev["sha"][:7]
        print(f"deploy-evidence: defter-HEAD={last_sha(LEDGER) or '(yok)'} "
              f"origin/main={ev['sha'][:7]} → "
              f"{'GUNCEL' if fresh else 'BAYAT'}")
        return 0 if fresh else 1

    # Aynı HEAD için mükerrer-satır önleme: son satır aynıysa ekleme-yapma.
    if last_sha(LEDGER) == ev["sha"][:7]:
        print("deploy-evidence: defter bu HEAD için güncel — ekleme-yok")
        return 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    append_entry(LEDGER, today, ev)
    print(f"deploy-evidence: satır eklendi (HEAD={ev['sha'][:7]}, "
          f"{len(WORKFLOWS)} workflow)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
