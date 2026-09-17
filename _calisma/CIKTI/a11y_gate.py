#!/usr/bin/env python3
"""a11y_gate.py — dashboard için fail-closed erişilebilirlik kapısı.

Spec: docs/superpowers/specs/2026-09-17-a11y-gate-design.md
Plan: docs/superpowers/plans/2026-09-17-a11y-gate-implementation.md

Akış: konfig yükle/doğrula → axe bundle checksum kapısı → headless Chromium
(Playwright) ile <base-url>/preview.html yükle → axe.run() → eşikleme
(blocking/warn/report-only; bilinmeyen etki = blocking) → verdict + rapor.

Çıkış kodları: 0 = PASS · 1 = FAIL (fail-closed koşul dahil) · 2 = kullanım/
ortam hatası (argparse, playwright kurulu değil).

Rapor yüzeyleri (spec §Reporting): stdout (verdict + tablo) ve
a11y_report.json (CI artifact). Üçüncü yüzey (job summary) CI job'ının.
"""

import argparse
import hashlib
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

VALID_TOP_KEYS = {"blocking", "warn", "incomplete", "allowlist"}
VALID_ENTRY_KEYS = {"rule", "reason", "target"}
INCOMPLETE_POLICY = "report-only"


# ---------------------------------------------------------------- config

def load_config(path):
    """Konfigi yükle ve doğrula. Geçersizse ValueError fırlatır (fail-closed)."""
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if not isinstance(cfg, dict):
        raise ValueError("config: üst seviye sözlük olmalı")
    unknown = set(cfg) - VALID_TOP_KEYS
    if unknown:
        raise ValueError("config: bilinmeyen anahtar(lar): %s" % sorted(unknown))
    missing = VALID_TOP_KEYS - set(cfg)
    if missing:
        raise ValueError("config: eksik anahtar(lar): %s" % sorted(missing))

    for key in ("blocking", "warn"):
        if not isinstance(cfg[key], list) or not all(isinstance(v, str) for v in cfg[key]):
            raise ValueError("config: %s string listesi olmalı" % key)
    overlap = set(cfg["blocking"]) & set(cfg["warn"])
    if overlap:
        raise ValueError("config: blocking/warn kesişimi: %s" % sorted(overlap))

    if cfg["incomplete"] != INCOMPLETE_POLICY:
        raise ValueError("config: incomplete yalnız '%s' olabilir" % INCOMPLETE_POLICY)

    if not isinstance(cfg["allowlist"], list):
        raise ValueError("config: allowlist liste olmalı")
    for i, entry in enumerate(cfg["allowlist"]):
        if not isinstance(entry, dict):
            raise ValueError("config: allowlist[%d] sözlük olmalı" % i)
        unknown = set(entry) - VALID_ENTRY_KEYS
        if unknown:
            raise ValueError("config: allowlist[%d] bilinmeyen anahtar: %s" % (i, sorted(unknown)))
        if not entry.get("rule"):
            raise ValueError("config: allowlist[%d].rule boş olamaz" % i)
        if not entry.get("reason"):
            raise ValueError("config: allowlist[%d].reason zorunlu (borç gizlenemez)" % i)
        if "target" in entry and not entry["target"]:
            raise ValueError("config: allowlist[%d].target boş olamaz" % i)
    return cfg


# -------------------------------------------------------------- checksum

def verify_checksum(axe_path):
    """axe bundle'ının sha256 pinini doğrula. Uyuşmazlıkta ValueError."""
    pin_path = axe_path + ".sha256"
    if not os.path.exists(pin_path):
        raise ValueError("checksum pini yok: %s" % pin_path)
    with open(pin_path, "r", encoding="utf-8") as f:
        expected = f.read().split()[0].strip().lower()
    h = hashlib.sha256()
    with open(axe_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        raise ValueError("axe bundle checksum uyuşmazlığı: %s != %s" % (actual, expected))


# ------------------------------------------------------------ threshold

def _node_targets(node):
    return " ".join(str(t) for t in node.get("target", []))


def _allowlisted_nodes(violation, allowlist):
    """Node-bazlı allowlist kararı → (eşleşen entry listesi, eşleşmeyen node sayısı)."""
    remaining = len(violation.get("nodes", []))
    reasons = []
    for entry in allowlist:
        if entry["rule"] != violation.get("id"):
            continue
        target = entry.get("target")
        for node in violation.get("nodes", []):
            if target is not None and target not in _node_targets(node):
                continue
            if _node_targets(node) is not None:
                reasons.append(entry["reason"])
                remaining -= 1
    # dedupe reasons (aynı entry birden çok node'u kapatırsa)
    seen, uniq = set(), []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq, max(remaining, 0)


def classify_violations(axe_results, cfg):
    """axe sonuçlarını satırlara eşikler. Bilinmeyen etki → blocking (default-deny).

    Döner: rows listesi — {rule, impact, level, nodes, reasons?, verdict_included}.
    level ∈ {blocking, warn, allowlisted, incomplete}.
    """
    blocking = set(cfg["blocking"])
    warn = set(cfg["warn"])
    rows = []

    for v in axe_results.get("violations", []):
        impact = v.get("impact")
        reasons, remaining = _allowlisted_nodes(v, cfg["allowlist"])
        if remaining == 0 and reasons:
            rows.append({"rule": v.get("id", "?"), "impact": impact,
                         "level": "allowlisted", "nodes": 0, "reasons": reasons})
            continue
        if impact in blocking or impact not in (blocking | warn):
            level = "blocking"  # bilinmeyen/None etki → default-deny
        elif impact in warn:
            level = "warn"
        else:
            level = "blocking"
        row = {"rule": v.get("id", "?"), "impact": impact,
               "level": level, "nodes": remaining}
        if reasons:
            row["allowlisted_nodes"] = len(v.get("nodes", [])) - remaining
            row["reasons"] = reasons
        rows.append(row)

    for inc in axe_results.get("incomplete", []):
        rows.append({"rule": inc.get("id", "?"), "impact": inc.get("impact"),
                     "level": "incomplete", "nodes": len(inc.get("nodes", []))})
    return rows


def decide_verdict(rows):
    return "PASS" if not any(r["level"] == "blocking" for r in rows) else "FAIL"


# ----------------------------------------------------------------- scan

def playwright_connect(base_url, axe_src):
    """Varsayılan sürücü: Playwright sync API. Lazy import — yoksa ImportError."""
    from playwright.sync_api import sync_playwright  # noqa: PLC0415 (lazy)

    page_url = base_url.rstrip("/") + "/preview.html"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(page_url, wait_until="load")
            page.add_script_tag(content=axe_src)
            results = page.evaluate("() => axe.run()")
        finally:
            browser.close()
    return results, page_url


def collect(base_url, axe_src, connect=None):
    """Sürücüyü çalıştır; exception'ı yukarı fırlatır (main FAIL'e çevirir)."""
    if connect is None:
        connect = playwright_connect
    return connect(base_url, axe_src)


# ----------------------------------------------------------------- main

def _print_table(rows):
    for r in rows:
        line = "  [%s] %s (impact: %s) nodes=%d" % (
            r["level"].upper(), r["rule"], r["impact"], r["nodes"])
        if r.get("reasons"):
            line += " reason=%s" % "; ".join(r["reasons"])
        print(line)


def main(argv=None):
    ap = argparse.ArgumentParser(description="a11y-gate: fail-closed axe-core kapısı")
    ap.add_argument("--base-url", required=True,
                    help="preview_server kök adresi (ör. http://127.0.0.1:PORT)")
    ap.add_argument("--config", default=os.path.join(SCRIPT_DIR, "a11y_gate_config.json"))
    ap.add_argument("--axe", default=os.path.join(SCRIPT_DIR, "vendor", "axe.min.js"))
    ap.add_argument("--output", default="a11y_report.json",
                    help="rapor JSON yolu (CI artifact)")
    args = ap.parse_args(argv)

    report = {"base_url": args.base_url, "page_url": None,
              "config": None, "violations": [], "summary": {}, "error": None}

    def fail(code):
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return code

    # 1) config (geçersiz → FAIL; config-drift kapısı)
    try:
        cfg = load_config(args.config)
    except (OSError, ValueError) as exc:
        report["error"] = "config hatası: %s" % exc
        print("verdict: FAIL")
        print("  [CONFIG] %s" % report["error"])
        return fail(1)
    report["config"] = cfg

    # 2) axe bundle + checksum kapısı
    try:
        verify_checksum(args.axe)
        with open(args.axe, "r", encoding="utf-8") as f:
            axe_src = f.read()
    except (OSError, ValueError) as exc:
        report["error"] = "axe bundle hatası: %s" % exc
        print("verdict: FAIL")
        print("  [AXE] %s" % report["error"])
        return fail(1)

    # 3) tarama (sunucu/tarayıcı arızası → FAIL; playwright yok → 2)
    try:
        results, page_url = collect(args.base_url, axe_src)
    except ImportError:
        print("playwright kurulu değil: pip install playwright && playwright install chromium")
        return 2
    except Exception as exc:  # noqa: BLE001 — fail-closed: her arıza FAIL'e dönüşür
        report["error"] = "tarama arızası: %s" % exc
        print("verdict: FAIL")
        print("  [SCAN] %s" % report["error"])
        return fail(1)

    if not isinstance(results, dict):
        report["error"] = "axe.run() sözlük döndürmedi (fail-closed)"
        print("verdict: FAIL")
        print("  [SCAN] %s" % report["error"])
        return fail(1)

    report["page_url"] = page_url
    report["raw"] = results
    rows = classify_violations(results, cfg)
    verdict = decide_verdict(rows)

    report["violations"] = rows
    report["summary"] = {
        "blocking": sum(1 for r in rows if r["level"] == "blocking"),
        "warn": sum(1 for r in rows if r["level"] == "warn"),
        "allowlisted": sum(1 for r in rows if r["level"] == "allowlisted"),
        "incomplete": sum(1 for r in rows if r["level"] == "incomplete"),
    }

    print("verdict: %s" % verdict)
    _print_table(rows)
    if report["summary"]["warn"] or report["summary"]["incomplete"]:
        print("(warn/incomplete raporlama seviyesidir; exit kodunu değiştirmez)")
    return fail(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    sys.exit(main())
