#!/usr/bin/env python3
"""a11y_gate.py — dashboard, görsel kılavuz ve landing için fail-closed erişilebilirlik kapısı.

Spec: docs/superpowers/specs/2026-09-17-a11y-gate-design.md
Plan: docs/superpowers/plans/2026-09-17-a11y-gate-implementation.md

Akış: konfig yükle/doğrula → axe bundle checksum kapısı → headless Chromium
(Playwright) ile config'te tanımlı sayfayı yükle ve witness metnini doğrula →
axe.run() → eşikleme (blocking/warn/report-only; bilinmeyen etki = blocking)
→ verdict + rapor.

Çıkış kodları: 0 = PASS · 1 = FAIL (fail-closed koşul dahil) · 2 = kullanım/
ortam hatası (argparse, playwright kurulu değil).

Rapor yüzeyleri (spec §Reporting): stdout (verdict + tablo) ve JSON
(CI artifact). Üçüncü yüzey (job summary) CI job'ının.
"""

import argparse
import hashlib
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

VALID_TOP_KEYS = {"blocking", "warn", "incomplete", "allowlist", "pages"}
VALID_ENTRY_KEYS = {"rule", "reason", "target"}
VALID_PAGE_KEYS = {"path", "witness"}
INCOMPLETE_POLICY = "report-only"
VALID_THEMES = ("dark", "light")


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

    pages = cfg["pages"]
    if not isinstance(pages, list) or not pages:
        raise ValueError("config: pages boş olmayan liste olmalı")
    seen_paths = set()
    for i, entry in enumerate(pages):
        if not isinstance(entry, dict):
            raise ValueError("config: pages[%d] sözlük olmalı" % i)
        unknown = set(entry) - VALID_PAGE_KEYS
        if unknown:
            raise ValueError("config: pages[%d] bilinmeyen anahtar: %s" % (
                i, sorted(unknown)))
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("config: pages[%d].path boş olamaz" % i)
        if (not path.startswith("/") or path.startswith("//") or
                "\\" in path or "?" in path or "#" in path or
                ".." in path.split("/")):
            raise ValueError("config: pages[%d].path same-origin olmalı: %s" % (
                i, path))
        if path in seen_paths:
            raise ValueError("config: yinelenen pages path: %s" % path)
        seen_paths.add(path)
        witness = entry.get("witness")
        if not isinstance(witness, str) or not witness:
            raise ValueError("config: pages[%d].witness boş olamaz" % i)

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


def select_page(cfg, page_path):
    """Config'te izin verilen sayfanın witness metnini döndürür.

    CLI --page ile keyfi URL taraması yapılamaz; her hedef config'te kanıt
    metniyle tanımlı olmalıdır. 404/yanlış mirror gibi durumlar witness
    eşleşmediği için tarama öncesi fail-closed hata verir.
    """
    for entry in cfg["pages"]:
        if entry["path"] == page_path:
            return entry["witness"]
    raise ValueError("config: --page %s kapsam dışı" % page_path)


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


def _incomplete_node_details(incomplete):
    """Incomplete axe node'larını target + outer HTML kanıtıyla koru.

    `nodes` alanı geriye uyumlu sayım olarak kalır; yeni alanlar inceleme
    sırasında hangi gerçek DOM düğümünün belirsiz kaldığını kanıtlar.
    """
    nodes = incomplete.get("nodes", [])
    return {
        "node_targets": [node.get("target", []) for node in nodes],
        "node_html": [node.get("html") for node in nodes],
    }


def _allowlisted_nodes(violation, allowlist):
    """Node-bazlı allowlist kararı → (eşleşen entry listesi, eşleşmeyen node sayısı)."""
    nodes = violation.get("nodes", [])
    matched = set()
    reasons = []
    for entry in allowlist:
        if entry["rule"] != violation.get("id"):
            continue
        target = entry.get("target")
        for index, node in enumerate(nodes):
            if target is not None and target not in _node_targets(node):
                continue
            # Aynı düğüm birden çok allowlist girdisiyle eşleşebilir; her
            # düğümü yalnız bir kez say ve ilk gerekçesini kaydet.
            if index in matched:
                continue
            matched.add(index)
            reasons.append(entry["reason"])
    # Aynı gerekçe birden çok mühür düğümünde tekrar edebilir.
    seen, uniq = set(), []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            uniq.append(reason)
    return uniq, len(nodes) - len(matched)


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
                         "level": "allowlisted", "nodes": 0,
                         "allowlisted_nodes": len(v.get("nodes", [])),
                         "reasons": reasons})
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
        # Incomplete policy report-only kalır; allowlist bunu gizlemez.
        # Yalnızca bilinçli/reason'lu SVG mühür düğümlerini görünür metadata
        # ile işaretler ve kalan düğüm sayısını korur.
        reasons, remaining = _allowlisted_nodes(inc, cfg["allowlist"])
        total_nodes = len(inc.get("nodes", []))
        row = {"rule": inc.get("id", "?"), "impact": inc.get("impact"),
               "level": "incomplete", "nodes": remaining}
        row.update(_incomplete_node_details(inc))
        if total_nodes != remaining:
            row["allowlisted_nodes"] = total_nodes - remaining
            row["reasons"] = reasons
        rows.append(row)
    return rows


def decide_verdict(rows):
    return "PASS" if not any(r["level"] == "blocking" for r in rows) else "FAIL"


# ----------------------------------------------------------------- scan

def _verify_witness(page, witness):
    """Render edilen gerçek sayfa witness'ı taşımalı; aksi halde FAIL."""
    if not witness:
        raise ValueError("sayfa witness metni zorunlu")
    body_text = page.locator("body").inner_text()
    if witness not in body_text:
        raise ValueError("sayfa witness metni bulunamadı: %s" % witness)


def _apply_theme(page, theme):
    """İstenen DOM tema witness'ını uygular; sayfa CSS'i bunu okur."""
    if theme not in VALID_THEMES:
        raise ValueError("tema dark|light olmalı")
    page.evaluate("(theme) => document.documentElement.dataset.theme = theme", theme)


def _verify_theme(page, theme):
    """DOM, tarama başında istenen tema witness'ını taşımalı."""
    actual = page.evaluate("() => document.documentElement.dataset.theme")
    if actual != theme:
        raise ValueError("tema witness uyuşmazlığı: DOM=%r, beklenen=%r" % (actual, theme))


def _new_themed_page(browser, theme, bypass_csp=False):
    """Navigation'dan önce tema attribute'ını yerleştiren context/page üretir."""
    if theme not in VALID_THEMES:
        raise ValueError("tema dark|light olmalı")
    context = browser.new_context(bypass_csp=bypass_csp)
    # tema enum ile validate edildiği için bu string güvenli bir init script'tir.
    context.add_init_script(
        script="document.documentElement.dataset.theme = %s;" % json.dumps(theme))
    return context.new_page()


def playwright_connect(base_url, axe_src, page_path="/preview.html", witness=None,
                       axe_url_path="/vendor/axe.min.js", theme="dark"):
    """Varsayılan sürücü: Playwright sync API. Lazy import — yoksa ImportError.

    Tema navigation öncesi same-origin DOM'a yazılır ve scan öncesi yeniden
    doğrulanır. CSP-sözleşmesi: script-src 'self' + nonce; bundle aynı-kökte
    /vendor/axe.min.js'ten 'self' ile yüklenir. Bu yol başarısızsa aynı tema
    witness'ı ile CSP-bypass context'inde inline enjeksiyon denenir.
    """
    from playwright.sync_api import sync_playwright  # noqa: PLC0415 (lazy)

    page_url = base_url.rstrip("/") + page_path
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = _new_themed_page(browser, theme)
            page.goto(page_url, wait_until="load")
            _verify_witness(page, witness)
            # Uygulama başlangıçta attribute'ı silebilir; scan öncesi yeniden
            # uygulayıp gerçek DOM witness'ı ile kilitleriz.
            _apply_theme(page, theme)
            _verify_theme(page, theme)
            results = page.evaluate(
                """async (axeUrl) => {
                    await new Promise((resolve, reject) => {
                        const s = document.createElement('script');
                        s.src = axeUrl;
                        s.onload = resolve;
                        s.onerror = () => reject(new Error('same-origin axe yüklenemedi'));
                        document.head.appendChild(s);
                    });
                    return await axe.run();
                }""", axe_url_path)
        except Exception:
            # Yedek (eski-daemon uyumu): CSP-bypass + inline enjeksiyon.
            page = _new_themed_page(browser, theme, bypass_csp=True)
            page.goto(page_url, wait_until="load")
            _verify_witness(page, witness)
            _apply_theme(page, theme)
            _verify_theme(page, theme)
            page.add_script_tag(content=axe_src)
            results = page.evaluate("() => axe.run()")
        finally:
            browser.close()
    return results, page_url


def collect(base_url, axe_src, page_path="/preview.html", witness=None, connect=None,
            theme="dark"):
    """Sürücüyü çalıştır; exception'ı yukarı fırlatır (main FAIL'e çevirir)."""
    if connect is None:
        connect = playwright_connect
    return connect(base_url, axe_src, page_path, witness, theme)


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
    ap.add_argument("--page", default="/preview.html",
                    help="config'te witness ile tanımlı same-origin sayfa")
    ap.add_argument("--output", default="a11y_report.json",
                    help="rapor JSON yolu (CI artifact)")
    ap.add_argument("--theme", default="dark",
                    help="tarama DOM teması (dark|light)")
    args = ap.parse_args(argv)

    report = {"verdict": "FAIL",  # fail-closed default: her arıza FAIL kalır
              "base_url": args.base_url, "page": args.page, "page_url": None,
              "theme": args.theme, "config": None, "violations": [],
              "summary": {}, "error": None}

    def fail(code):
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return code

    # 0) tema usage-policy; argparse'ın choices'i SystemExit ile rapor
    # yazmadan çıkar. Burada report + FAIL yazarak fail-closed sözleşmesini koru.
    if args.theme not in VALID_THEMES:
        report["error"] = "kullanım hatası: tema dark|light olmalı"
        print("verdict: FAIL")
        print("  [CONFIG] %s" % report["error"])
        return fail(1)

    # 1) config (geçersiz → FAIL; config-drift kapısı)
    try:
        cfg = load_config(args.config)
        witness = select_page(cfg, args.page)
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
        results, page_url = collect(args.base_url, axe_src, args.page, witness,
                                    theme=args.theme)
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

    report["verdict"] = verdict
    print("verdict: %s" % verdict)
    _print_table(rows)
    if report["summary"]["warn"] or report["summary"]["incomplete"]:
        print("(warn/incomplete raporlama seviyesidir; exit kodunu değiştirmez)")
    return fail(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    sys.exit(main())
