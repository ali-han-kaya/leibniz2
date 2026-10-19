#!/usr/bin/env python3
"""deploy_evidence.py — kalıcı dağıtım/deploy kanıtı defteri (fail-closed).

Hattın son koşumlarını denetleyip çekirdek-workflow'ların main-dalı
son koşumlarını `docs/DEPLOY_EVIDENCE.md`'ye **append-only** yazar.
İkinci kanıt-kolonu Azure resource-health'tir: dağıtılan Container App'in
canlı durumu `az rest` ile Microsoft.ResourceHealth/availabilityStatuses
ucundan okunur (kaynak: infra/main.bicep → `app-${name}`).

Azure hücresi sessiz-PASS üretmez — okunamayan her durum damgalanır:
`az-yok` (CLI yok), `rg-yok` (resource-group verilmedi), `oturum-yok`
(`az login` yok), `kaynak-yok` (Container App/RG yok), `hata` (diğer;
neden stderr'e yazılır). Gerçek okuma `[Available](portal-link)` biçimidir;
`--check --require-azure` son satırda bu kanıtı şart koşar (fail-closed).

Defter repo-gelenekleriyle tek-kaynaklıdır: bu betik tek yazar;
`--check` bayat-kanıt korumasıdır (son satır HEAD'i ≠ origin/main ucu
→ rc=1; CI-daemon /api/latest'de görünür, rapor-devirleri bayat kanıt
taşıyamaz).

Çıkış-kodu: 0 = satır eklendi veya defter güncel; 1 = bayat (check) veya
`--require-azure` ile eksik Azure kanıtı; 2 = kullanım/ortam hatası
(gh yok, gh-hata, HTTP-hata — sessiz-PASS yok).

    python3 _calisma/CIKTI/deploy_evidence.py            # ekle + yaz
    python3 _calisma/CIKTI/deploy_evidence.py --check    # bayat-mi?
    python3 _calisma/CIKTI/deploy_evidence.py --check --require-azure
                                                         # + Azure kanıtı şart
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

# Azure kanıt-kolonu: infra/main.bicep `app-${name}` (name=verify-dashboard).
AZURE_APP = "app-verify-dashboard"
AZURE_HEALTH_API = "2022-10-01"

# Okunamayan-durum damgaları: hiçbiri sessiz-PASS değildir.
AZURE_MARKERS = ("az-yok", "rg-yok", "oturum-yok", "kaynak-yok", "hata",
                 "ölçülmedi")

LEDGER_HEADERS = ("| Tarih | HEAD (origin/main) | verify-delivery |"
                  " docker-security | test-smoke | determinism-trend |"
                  " azure-health |")
LEDGER_SEP = "|---|---|---|---|---|---|---|"
# Kanıt-satırındaki hücre sayısı (başlıktan türetilir — tek kaynak).
LEDGER_COLUMNS = len(LEDGER_HEADERS.split("|")) - 2


def _gh(argv):
    proc = subprocess.run(["gh"] + argv, capture_output=True, text=True)
    return proc.returncode, proc.stdout if proc.returncode == 0 else proc.stderr


def _az(argv):
    proc = subprocess.run(["az"] + argv, capture_output=True, text=True)
    return proc.returncode, proc.stdout if proc.returncode == 0 else proc.stderr


# Test-enjeksiyonu için modül-global (gh_run_rca deseni).
GH = _gh
AZ = _az


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


def _subscription(az, subscription):
    """(abonelik, neden) — argüman → AZURE_SUBSCRIPTION_ID → az oturumu."""
    if subscription and subscription.strip():
        return subscription.strip(), ""
    env_sub = os.environ.get("AZURE_SUBSCRIPTION_ID", "").strip()
    if env_sub:
        return env_sub, ""
    rc, out = az(["account", "show", "--query", "id", "-o", "tsv"])
    if rc != 0:
        return "", out.strip()[:160]
    sub = out.strip()
    if not sub:
        return "", "abonelik kimliği boş döndü"
    return sub, ""


def collect_azure(az, resource_group, app=AZURE_APP, subscription=None):
    """Azure resource-health hücresi (tek kolon).

    Döner: {"cell": <defter-hücresi>[, "state": <availabilityState>,
    "note": <stderr-notu>]}. Sessiz-PASS yok: her başarısızlık hücreye
    açık damga olarak yazılır (AZURE_MARKERS).
    """
    if not (resource_group or "").strip():
        return {"cell": "rg-yok"}
    sub, why = _subscription(az, subscription)
    if not sub:
        return {"cell": "oturum-yok", "note": why}
    url = ("https://management.azure.com/subscriptions/{sub}"
           "/resourceGroups/{rg}/providers/Microsoft.App/containerApps/{app}"
           "/providers/Microsoft.ResourceHealth/availabilityStatuses/current"
           "?api-version={api}").format(sub=sub, rg=resource_group.strip(),
                                        app=app, api=AZURE_HEALTH_API)
    rc, out = az(["rest", "--method", "get", "--url", url])
    if rc != 0:
        low = out.lower()
        if "notfound" in low or "not found" in low or "404" in low:
            return {"cell": "kaynak-yok"}
        return {"cell": "hata", "note": out.strip()[:160]}
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {"cell": "hata", "note": "availabilityStatuses JSON parse edilemedi"}
    state = ((data.get("properties") or {})
             .get("availabilityState") or "").strip()
    if not state:
        return {"cell": "hata", "note": "availabilityState alanı yok"}
    rid = (data.get("id") or "").strip()
    if not rid:
        return {"cell": state, "state": state}
    link = f"https://portal.azure.com/#resource{rid}/overview"
    return {"cell": f"[{state}]({link})", "state": state}


def azure_proven(cell):
    """Hücrede gerçek okuma mı var, yoksa dürüst-durum damgası mı?

    Boş hücre de kanıt DEĞİLDİR: kolon-öncesi satırlar (eski kolon-seti)
    kanıt taşımaz — `--require-azure` bunları yeşile çeviremez.
    """
    text = cell.strip()
    return bool(text) and text not in AZURE_MARKERS


def append_entry(path, today, ev):
    """Deftere tek satır ekle (append-only; başlık eksik/eskiyse tazele)."""
    azure = ev.get("azure") or {}
    cells = [today, ev["sha"][:7]] + \
        [_cell(ev["runs"].get(wf)) for wf in WORKFLOWS] + \
        [azure.get("cell", "ölçülmedi")]
    row = "| " + " | ".join(cells) + " |"
    lines = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as data:
            lines = data.read().splitlines()
    sep_i = next((i for i, ln in enumerate(lines)
                  if ln.startswith("|---")), None)
    if sep_i is None:
        lines += ["## Kanıt-defteri", "", LEDGER_HEADERS, LEDGER_SEP]
    else:
        # Kolon-seti bu betiğin sözleşmesidir: başlık/ayraç tazelenir.
        # Veri satırlarına dokunulmaz (append-only invariant).
        lines[sep_i] = LEDGER_SEP
        if sep_i:
            lines[sep_i - 1] = LEDGER_HEADERS
        else:
            lines.insert(0, LEDGER_HEADERS)
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


def last_cell(path):
    """Son kanıt-satırının son hücresi (satır-yoksa/kolon-öncesiyse '').

    Kolon-seti uymayan satırda '' döner: eski 6-kolonlu satırın son hücresi
    determinism-trend'dir, azure-health sanılamaz (fail-closed).
    """
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        rows = [ln for ln in f if ln.startswith("| 2")]
    if not rows:
        return ""
    cells = rows[-1].split("|")
    if len(cells) - 2 != LEDGER_COLUMNS:
        return ""
    return cells[-2].strip()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Çekirdek-workflow son-koşum kanıtını deftere işle")
    ap.add_argument("--check", action="store_true",
                    help="defter güncel mi (son HEAD == origin/main ucu)?")
    ap.add_argument("--resource-group",
                    default=os.environ.get("AZURE_RESOURCE_GROUP", ""),
                    help="Azure resource-group (yoksa AZURE_RESOURCE_GROUP)")
    ap.add_argument("--app", default=AZURE_APP,
                    help=f"Container App adı (varsayılan: {AZURE_APP})")
    ap.add_argument("--subscription", default="",
                    help="abonelik kimliği (yoksa AZURE_SUBSCRIPTION_ID → az oturumu)")
    ap.add_argument("--require-azure", action="store_true",
                    help="--check ile: son satırda gerçek Azure okuması şart")
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
        azure_cell = last_cell(LEDGER)
        if fresh and args.require_azure and not azure_proven(azure_cell):
            print(f"deploy-evidence: defter GUNCEL ama azure-health="
                  f"{azure_cell or '(yok)'} → AZURE-KANITI-YOK")
            return 1
        print(f"deploy-evidence: defter-HEAD={last_sha(LEDGER) or '(yok)'} "
              f"origin/main={ev['sha'][:7]} "
              f"azure-health={azure_cell or '(yok)'} → "
              f"{'GUNCEL' if fresh else 'BAYAT'}")
        return 0 if fresh else 1

    # Aynı HEAD için mükerrer-satır önleme: son satır aynıysa ekleme-yapma.
    if last_sha(LEDGER) == ev["sha"][:7]:
        print("deploy-evidence: defter bu HEAD için güncel — ekleme-yok")
        return 0
    azure = {"cell": "az-yok"}
    if shutil.which("az") is not None:
        azure = collect_azure(AZ, args.resource_group, args.app,
                              args.subscription)
    if azure.get("note"):
        sys.stderr.write(f"deploy-evidence: azure: {azure['note']}\n")
    ev["azure"] = azure

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    append_entry(LEDGER, today, ev)
    print(f"deploy-evidence: satır eklendi (HEAD={ev['sha'][:7]}, "
          f"{len(WORKFLOWS)} workflow, azure-health={azure['cell']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
