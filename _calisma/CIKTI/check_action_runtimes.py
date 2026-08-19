#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_action_runtimes.py — workflow action'larının Node runtime sürümünü doğrula.

Her `uses:` action için raw.githubusercontent.com'dan action.yml çeker ve
`runs.using` değerini hedef Node sürümüne (node24) karşı denetler. JavaScript
action'ları için node24 altı (node20/node16/node12) deprecated sayılır
(GitHub Actions deprecation uyarısı kaynağı); composite/docker action'ları
Node taşımadığından SKIP (kapsam dışı). action.yml çekilemezse (404/ağ)
fail-closed davranır: doğrulanamayan bir action PASS sayılmaz.

Kullanım:
  python3 check_action_runtimes.py [--workflow PATH] [--json] [--target node24]

Exit kodları:
  0 — tüm Node action'ları hedef sürümde (composite/docker SKIP sayılır)
  1 — deprecated Node bulundu VEYA bir action doğrulanamadı (fail-closed)
  2 — kullanım/ortam hatası (PyYAML yok, workflow okunamadı)

Yalnızca Python 3 standart kütüphanesi + PyYAML kullanır (workflow YAML
ayrıştırma için; status_checks.py ile aynı bağımlılık).
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

DEFAULT_WORKFLOW = ".github/workflows/verify.yml"
TARGET_NODE = "node24"  # hedef runtime (GitHub'ın güncel native Node sürümü)
_NODE_RE = re.compile(r"^node(\d+)$")
_USER_AGENT = "check_action_runtimes.py (Stoic-Hume V5 CI)"
_HTTP_TIMEOUT = 15
_HTTP_RETRIES = 2


def _load_yaml(text):
    """YAML metnini parse et — PyYAML lazy import (yoksa net ImportError).

    Modül import'unda yaml gerektirmez (test keşfi sistem python'da PyYAML
    olmadan da modülü içe aktarabilsin); yaml'a yalnızca gerçek parse
    gerektiğinde başvurulur.
    """
    try:
        import yaml
    except ImportError as e:
        raise ImportError("PyYAML gerekli — pip install pyyaml") from e
    return yaml.safe_load(text)

# node24 altındaki her nodeN → deprecated (FAIL).
_TARGET_MAJOR = int(TARGET_NODE[len("node"):])


def parse_uses(workflow_text):
    """workflow YAML metninden unique `uses:` değerlerini çıkar (sıralı).

    jobs.*.steps[*].uses taranır; owner/repo@ref biçimi korunur. YAML hataları
    (ValueError/yaml.YAMLError) çağırana yükselir — main exit 2 ile yakalar.
    """
    data = _load_yaml(workflow_text)
    uses = set()
    for job in (data.get("jobs") or {}).values():
        if not isinstance(job, dict):
            continue
        for step in (job.get("steps") or []):
            u = (step or {}).get("uses")
            if isinstance(u, str) and u.strip():
                uses.add(u.strip())
    return sorted(uses)


def fetch_action_yml(action, timeout=_HTTP_TIMEOUT, retries=_HTTP_RETRIES):
    """owner/repo@ref → (action.yml içeriği | None, hata | None).

    Lokal action'lar (`./...`) markette değildir — ("__local__", None) döner;
    çağıran SKIP sayar. 404 → ("__missing__" bilgisi hata dizesinde) hemen
    döner (retry yok); ağ/429/5xx geçici hatalar kısa backoff ile tekrarlanır.
    """
    if action.startswith("./") or action.startswith("../"):
        return None, "__local__"
    if "@" not in action or "/" not in action:
        return None, f"geçersiz uses biçimi: {action}"
    owner_repo, ref = action.split("@", 1)
    if not ref or not owner_repo or "/" not in owner_repo:
        return None, f"geçersiz uses biçimi: {action}"
    url = f"https://raw.githubusercontent.com/{owner_repo}/{ref}/action.yml"
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace"), None
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (401, 403, 404):
                break  # kalıcı — retry anlamsız
        except Exception as e:  # ağ/timeout
            last = f"{type(e).__name__}: {e}"
        if attempt < retries - 1:
            time.sleep(1.0 * (attempt + 1))
    return None, last or "ağ hatası"


def classify_using(using, target=TARGET_NODE):
    """runs.using → (verdict, note). verdict: PASS | FAIL | SKIP.

    - nodeN: N >= hedef → PASS (hedef veya daha yeni); N < hedef → FAIL
      (deprecated). node24 hedefinde node20/node16/node12 FAIL olur.
    - composite / docker → SKIP (Node tabanlı değil — kapsam dışı).
    - diğer (bilinmeyen) → PASS + "elle kontrol" notu (bloke etmez, görünür).
    """
    if using in ("composite", "docker"):
        return "SKIP", f"{using} (Node tabanlı değil — kapsam dışı)"
    m = _NODE_RE.match(using or "")
    if m:
        major = int(m.group(1))
        tgt = int(target[len("node"):]) if target.startswith("node") else _TARGET_MAJOR
        if major >= tgt:
            return "PASS", f"{using} (hedef {target} veya daha yeni)"
        return "FAIL", f"{using} (deprecated — {target} gerek)"
    return "PASS", f"{using or '?'} (bilinmeyen runtime — elle kontrol)"


def audit(workflow_text, fetcher=fetch_action_yml, target=TARGET_NODE):
    """Tüm action'ları denetle. Döndürür sonuç listesi (fail-closed).

    Her öğe: {action, using, verdict, note, error}. using/verdict, fetch
    başarısızsa None/"FAIL" (doğrulanamayan PASS sayılmaz).
    """
    rows = []
    for action in parse_uses(workflow_text):
        # Lokal action'lar markette değildir — fetcher hiç çağrılmadan atlanır
        # (fetcher'a değil audit'e ait bir özelliktir; özel fetcher da güvende).
        if action.startswith("./") or action.startswith("../"):
            rows.append({"action": action, "using": None, "verdict": "SKIP",
                         "note": "lokal action (markette değil)", "error": None})
            continue
        content, err = fetcher(action)
        if err == "__local__":
            rows.append({"action": action, "using": None, "verdict": "SKIP",
                         "note": "lokal action (markette değil)", "error": None})
            continue
        if err:
            rows.append({"action": action, "using": None, "verdict": "FAIL",
                         "note": "action.yml çekilemedi (doğrulanamadı)",
                         "error": err})
            continue
        try:
            meta = _load_yaml(content) or {}
            using = (meta.get("runs") or {}).get("using")
        except ImportError as e:
            rows.append({"action": action, "using": None, "verdict": "FAIL",
                         "note": "PyYAML yok — action.yml ayrıştırılamadı",
                         "error": str(e)})
            continue
        except Exception as e:  # yaml.YAMLError (bozuk action.yml)
            rows.append({"action": action, "using": None, "verdict": "FAIL",
                         "note": "action.yml YAML ayrıştırılamadı",
                         "error": str(e)})
            continue
        verdict, note = classify_using(using, target)
        rows.append({"action": action, "using": using, "verdict": verdict,
                     "note": note, "error": None})
    return rows


def _summary(rows):
    ok = sum(1 for r in rows if r["verdict"] == "PASS")
    fail = sum(1 for r in rows if r["verdict"] == "FAIL")
    skip = sum(1 for r in rows if r["verdict"] == "SKIP")
    return {"total": len(rows), "pass": ok, "fail": fail, "skip": skip}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workflow", default=DEFAULT_WORKFLOW,
                    help=f"workflow dosyası (varsayılan: {DEFAULT_WORKFLOW})")
    ap.add_argument("--json", action="store_true",
                    help="makine-okur JSON çıktısı (rapor sidecar için)")
    ap.add_argument("--target", default=TARGET_NODE,
                    help=f"hedef Node runtime (varsayılan: {TARGET_NODE})")
    ap.add_argument("--out", default=None,
                    help="raporu ayrıca bu JSON dosyasına yaz (CI artifact)")
    args = ap.parse_args(argv)

    if not args.target.startswith("node"):
        print(f"HATA: --target 'nodeN' biçiminde olmalı: {args.target}",
              file=sys.stderr)
        return 2

    try:
        with open(args.workflow, encoding="utf-8") as f:
            workflow_text = f.read()
    except OSError as e:
        print(f"HATA: workflow okunamadı ({args.workflow}): {e}", file=sys.stderr)
        return 2

    try:
        rows = audit(workflow_text, fetch_action_yml, args.target)
    except ImportError as e:
        print(f"HATA: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"HATA: workflow YAML ayrıştırılamadı ({args.workflow}): {e}",
              file=sys.stderr)
        return 2

    summary = _summary(rows)
    payload = {"workflow": args.workflow, "target": args.target,
               "summary": summary, "actions": rows}

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as of:
                json.dump(payload, of, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"HATA: rapor yazılamadı ({args.out}): {e}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Action runtime denetimi — hedef: {args.target} "
              f"(kaynak: {args.workflow})")
        for r in rows:
            tag = {"PASS": "OK  ", "FAIL": "FAIL", "SKIP": "SKIP"}[r["verdict"]]
            using = r["using"] or "?"
            extra = f" — {r['error']}" if r.get("error") else ""
            print(f"  [{tag}] {r['action']:<30} runs.using={using:<10} "
                  f"{r['note']}{extra}")
        print(f"\nSONUÇ: {'PASS' if summary['fail'] == 0 else 'FAIL'} — "
              f"{summary['pass']} PASS, {summary['fail']} FAIL, "
              f"{summary['skip']} SKIP (toplam {summary['total']} action)")

    # fail-closed: deprecated node VEYA doğrulanamayan action → exit 1
    return 1 if summary["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
