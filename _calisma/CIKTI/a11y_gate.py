#!/usr/bin/env python3
"""a11y_gate.py — dashboard için fail-closed erişilebilirlik kapısı.

Spec: docs/superpowers/specs/2026-09-17-a11y-gate-design.md
Plan: docs/superpowers/plans/2026-09-17-a11y-gate-implementation.md

Akış: konfig yükle/doğrula → axe bundle checksum kapısı → config'de ilan edilen
HER sayfa için headless Chromium (Playwright) ile <base-url><path> yükle →
axe.run() → eşikleme (blocking/warn/report-only; bilinmeyen etki = blocking) →
verdict + rapor.

KAPSAM ACIKÇA ILAN EDILIR: taranacak yüzeyler config'in `pages` listesidir
(ölcüm 2026-10-02: preview_server yalnız /preview.html ve /guide.html servis
eder; slides yalnız .png kabul eder, dashboard-shadcn/landing servis edilmez).
Bir sayfa yüklenemezse kapı FAIL verir — sessizce atlanan sayfa, kapsam
genişletilmiş gibi görünmez.

Çıkış kodları: 0 = PASS · 1 = FAIL (fail-closed koşul dahil) · 2 = kullanım/
ortam hatası (argparse, playwright kurulu değil).

Rapor yüzeyleri (spec §Reporting): stdout (verdict + sayfa satırları) ve
a11y_report.json (CI artifact). Üçüncü yüzey (job summary) CI job'ının.
"""

import argparse
import hashlib
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

VALID_TOP_KEYS = {"blocking", "warn", "incomplete", "pages", "allowlist"}
VALID_ENTRY_KEYS = {"rule", "reason", "target", "page"}
VALID_PAGE_KEYS = {"path", "blocking", "warn", "incomplete"}
INCOMPLETE_POLICY = "report-only"


class PageLoadError(RuntimeError):
    """Sayfa sunucudan gelmedi (404/5xx) — fail-closed: tarama yapılmadı."""


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

    # --- sayfa listesi: kapsam ilanı zorunlu (fail-closed) --------------
    if not isinstance(cfg["pages"], list) or not cfg["pages"]:
        raise ValueError("config: pages boş olamaz — taranan yüzeyler ilan edilir")
    paths = set()
    for i, page in enumerate(cfg["pages"]):
        if not isinstance(page, dict):
            raise ValueError("config: pages[%d] sözlük olmalı" % i)
        unknown = set(page) - VALID_PAGE_KEYS
        if unknown:
            raise ValueError("config: pages[%d] bilinmeyen anahtar: %s" % (i, sorted(unknown)))
        path = page.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError("config: pages[%d].path mutlak rota olmalı (ör. /guide.html)" % i)
        if ".." in path.split("/"):
            raise ValueError("config: pages[%d].path '..' içeremez: %s" % (i, path))
        if path in paths:
            raise ValueError("config: pages[%d].path yineleniyor: %s" % (i, path))
        paths.add(path)
        for key in ("blocking", "warn"):
            if key in page and (not isinstance(page[key], list)
                                or not all(isinstance(v, str) for v in page[key])):
                raise ValueError("config: pages[%d].%s string listesi olmalı" % (i, key))
        overlap = (set(page.get("blocking", cfg["blocking"]))
                   & set(page.get("warn", cfg["warn"])))
        if overlap:
            raise ValueError("config: pages[%d] blocking/warn kesişimi: %s" % (i, sorted(overlap)))
        if "incomplete" in page and page["incomplete"] != INCOMPLETE_POLICY:
            raise ValueError("config: pages[%d].incomplete yalnız '%s' olabilir"
                             % (i, INCOMPLETE_POLICY))

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
        if "page" in entry and entry["page"] not in paths:
            # Taranmayan sayfaya kayıt = ölü konfig (görünür ama etkisiz).
            raise ValueError("config: allowlist[%d].page pages listesinde değil: %r"
                             % (i, entry["page"]))
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


def _allowlisted_nodes(violation, allowlist, page_path=None):
    """Node-bazlı allowlist kararı → (eşleşen entry listesi, eşleşmeyen node sayısı).

    `page_path` verildiğinde yalnız o sayfanın kayıtları geçerlidir: `page`
    anahtarı olmayan entry tüm sayfalarda, `page` anahtarı olan yalnız
    eşleştiği sayfada uygulanır. Böylece bir sayfanın gerekçeli kaydı
    başka sayfada gerekçesiz susturmaya dönüşmez.
    """
    remaining = len(violation.get("nodes", []))
    reasons = []
    for entry in allowlist:
        if entry["rule"] != violation.get("id"):
            continue
        scope = entry.get("page")
        if page_path is not None and scope is not None and scope != page_path:
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


def thresholds_for(cfg, page_path):
    """Sayfanın eşikleri: `pages[path]` override'ı, yoksa üst seviye varsayılan."""
    for page in cfg["pages"]:
        if page["path"] == page_path:
            return (set(page.get("blocking", cfg["blocking"])),
                    set(page.get("warn", cfg["warn"])))
    raise ValueError("config: sayfa taranmıyor: %s" % page_path)


def _summary(rows):
    """level → sayım. Her level'in ES ADIYLA kovası var (sözleşme testi sabitler)."""
    return {
        "blocking": sum(1 for r in rows if r["level"] == "blocking"),
        "warn": sum(1 for r in rows if r["level"] == "warn"),
        "allowlisted": sum(1 for r in rows if r["level"] == "allowlisted"),
        "incomplete": sum(1 for r in rows if r["level"] == "incomplete"),
        "incomplete_allowlisted": sum(
            1 for r in rows if r["level"] == "incomplete_allowlisted"),
    }


def classify_violations(axe_results, cfg, page_path=None):
    """axe sonuçlarını satırlara eşikler. Bilinmeyen etki → blocking (default-deny).

    `page_path` verilirse o sayfanın eşikleri ve allowlist kapsamı kullanılır;
    verilmezse üst seviye varsayılanlar ve tüm kayıtlar geçerlidir.

    Döner: rows listesi — {rule, impact, level, nodes, reasons?, allowlisted_nodes?}.
    level ∈ {blocking, warn, allowlisted, incomplete, incomplete_allowlisted}.

    KURAL: her level'in summary'de ES ADIYLA bir kovasi olmalidir. Aksi halde
    sayim sessizce yutulur ( satir raporda gorunur, ozette olmaz).
    """
    if page_path is None:
        blocking = set(cfg["blocking"])
        warn = set(cfg["warn"])
    else:
        blocking, warn = thresholds_for(cfg, page_path)
    rows = []

    for v in axe_results.get("violations", []):
        impact = v.get("impact")
        reasons, remaining = _allowlisted_nodes(v, cfg["allowlist"], page_path)
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

    # incomplete de allowlist'e uyar. Bu satir olmadan gerekceli bir kayit
    # KAYIT GIBI GORUNUR AMA HIC BIR SEY YAPMAZDI (bkz. incomplete dongusunun
    # _allowlisted_nodes'i cagrirmamasi) — yani borc defterde yazar, kapida
    # ayni sekilde raporlanmaya devam ederdi. Kabul: kayit gerekcesiyle
    # gorunur kalir, silinmez (borc gizlenemez), verdict'i etkilemez.
    for inc in axe_results.get("incomplete", []):
        reasons, remaining = _allowlisted_nodes(inc, cfg["allowlist"], page_path)
        if remaining == 0 and reasons:
            rows.append({"rule": inc.get("id", "?"), "impact": inc.get("impact"),
                         "level": "incomplete_allowlisted", "nodes": 0,
                         "reasons": reasons})
            continue
        row = {"rule": inc.get("id", "?"), "impact": inc.get("impact"),
               "level": "incomplete", "nodes": remaining}
        if reasons:
            row["allowlisted_nodes"] = len(inc.get("nodes", [])) - remaining
            row["reasons"] = reasons
        rows.append(row)
    return rows


def decide_verdict(rows):
    return "PASS" if not any(r["level"] == "blocking" for r in rows) else "FAIL"


# ----------------------------------------------------------------- scan

def playwright_connect(base_url, axe_src, page_path):
    """Varsayılan sürücü: Playwright sync API. Lazy import — yoksa ImportError.

    Fail-closed: HTTP >= 400 veya yanıt yoksa PageLoadError fırlatır. Playwright
    `goto` 404'te exception atmaz (status yalnız response nesnesinde), dolayısıyla
    status kontrolü kapının kendisinde olmalı — aksi halde 404 sayfasının boş
    `<body>`'si taranır ve kapı "0 ihlal" diye yeşil görünür.
    """
    from playwright.sync_api import sync_playwright  # noqa: PLC0415 (lazy)

    page_url = base_url.rstrip("/") + page_path
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            # preview_server nonce-CSP'si inline axe injection'ı bloklar —
            # tarama-connect'i CSP-bypass'lı context'te aç (yalnız kapı-scan'i).
            context = browser.new_context(bypass_csp=True)
            page = context.new_page()
            response = page.goto(page_url, wait_until="load")
            status = getattr(response, "status", None) if response is not None else None
            if status is None or status >= 400:
                raise PageLoadError("%s → HTTP %s" % (page_path, status))
            page.add_script_tag(content=axe_src)
            results = page.evaluate("() => axe.run()")
        finally:
            browser.close()
    return results, page_url


def collect(base_url, axe_src, page_path, connect=None):
    """Sürücüyü çalıştır; exception'ı yukarı fırlatır (main FAIL'e çevirir)."""
    if connect is None:
        connect = playwright_connect
    return connect(base_url, axe_src, page_path)


# ----------------------------------------------------------------- main

def _print_table(rows, indent="  "):
    for r in rows:
        line = "%s[%s] %s (impact: %s) nodes=%d" % (
            indent, r["level"].upper(), r["rule"], r["impact"], r["nodes"])
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

    report = {"base_url": args.base_url, "config": None,
              "pages": [], "violations": [], "summary": {}, "error": None}

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

    # 3) sayfa sayfa tarama (yarınlanamayan sayfa → FAIL, fail-closed)
    for page in cfg["pages"]:
        path = page["path"]
        entry = {"path": path, "url": args.base_url.rstrip("/") + path,
                 "verdict": None, "error": None,
                 "violations": [], "summary": {}, "raw": None}
        try:
            results, _url = collect(args.base_url, axe_src, path)
        except ImportError:
            print("playwright kurulu değil: pip install playwright && playwright install chromium")
            return 2
        except PageLoadError as exc:
            entry["error"] = "sayfa yüklenemedi: %s" % exc
            entry["verdict"] = "FAIL"
            report["pages"].append(entry)
            continue
        except Exception as exc:  # noqa: BLE001 — fail-closed: her arıza FAIL
            entry["error"] = "tarama arızası: %s" % exc
            entry["verdict"] = "FAIL"
            report["pages"].append(entry)
            continue

        if not isinstance(results, dict):
            entry["error"] = "axe.run() sözlük döndürmedi (fail-closed)"
            entry["verdict"] = "FAIL"
            report["pages"].append(entry)
            continue

        entry["raw"] = results
        rows = classify_violations(results, cfg, path)
        for row in rows:
            row["page"] = path
        entry["violations"] = rows
        entry["verdict"] = decide_verdict(rows)
        entry["summary"] = _summary(rows)
        report["pages"].append(entry)
        report["violations"].extend(rows)

    report["summary"] = _summary(report["violations"])
    verdict = ("FAIL" if any(p["verdict"] != "PASS" for p in report["pages"])
               else "PASS")

    print("verdict: %s" % verdict)
    for p in report["pages"]:
        print("  %-4s %s" % (p["verdict"], p["path"]))
        if p["error"]:
            print("    [ERROR] %s" % p["error"])
        _print_table(p["violations"], indent="    ")
    if (report["summary"]["warn"] or report["summary"]["incomplete"]
            or report["summary"]["incomplete_allowlisted"]):
        print("(warn/incomplete raporlama seviyesidir; exit kodunu değiştirmez)")
    return fail(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    sys.exit(main())
