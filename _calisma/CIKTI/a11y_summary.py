#!/usr/bin/env python3
"""a11y_summary.py — a11y job summary'si için allowlist'li incomplete kanıtı.

Spec: docs/superpowers/specs/2026-09-17-a11y-gate-design.md (§Reporting:
üç yüzey — stdout, JSON artifact, job summary). Bu modül üçüncü yüzeyin
kanıt bölümünü üretir; verify.yml'deki "Write a11y job summary" adımı
sonucu GITHUB_STEP_SUMMARY'ye ekler.

Sözleşme:
  * Özet YALNIZ allowlist'le eşleşen incomplete düğümlerin hedefini ve
    outer HTML kanıtını gösterir. Allowlist'siz incomplete düğümler
    gizlenmez ama özete taşınmaz: tam liste JSON artifact'ında kalır
    (a11y_gate.classify_violations `node_targets`/`node_html`).
  * Eşleşme kuralı tek kaynakta: a11y_gate.allowlisted_node_indices.
  * Kanıt SAYFADAN gelir (güvenilmez metin). Hiçbir değer ham markdown/HTML
    olarak yorumlanamaz: hedef/kural satır içi kod aralığında, HTML kanıtı
    içeriğindeki en uzun backtick dizisinden DAHA UZUN bir kod çiti içinde
    render edilir; düğüm sayısı ve kanıt uzunluğu sınırlanır.

CLI (yerel inceleme):
  python3 _calisma/CIKTI/a11y_summary.py \\
    --config _calisma/CIKTI/a11y_gate_config.json \\
    --report dark=a11y_dashboard_dark.json
"""
import argparse
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import a11y_gate  # noqa: E402

# Özet bir insan yüzeyi: kanıt kısaltılır ama gizlenmez. Sınırlar ölçüm
# değil, okunabilirlik kararıdır; kesilen/atlanan her şey açıkça yazılır.
MAX_NODES_PER_RULE = 8
MAX_EVIDENCE_CHARS = 240

_BACKTICK_RUN = re.compile(r"`+")


def _one_line(value):
    """Satır sonlarını/sekme ve çoklu boşlukları tek boşluğa indirger."""
    return " ".join(str(value if value is not None else "").split())


def _longest_backtick_run(text):
    return max((len(run) for run in _BACKTICK_RUN.findall(text)), default=0)


def code_span(value):
    """Değeri güvenli satır içi kod aralığına çevirir (kaçış, teslim).

    CommonMark: aralık, içeriğindeki en uzun backtick dizisinden uzun bir
    çitle sarılmalı; hem baştan hem sondan birer boşluk varsa biri kırpılır,
    bu yüzden kenarlarda boşluk/backtick varsa birer dolgu boşluğu eklenir.
    """
    text = _one_line(value)
    if not text:
        return "`(boş)`"
    fence = "`" * (_longest_backtick_run(text) + 1)
    pad = " " if (text[0] in "` " or text[-1] in "` ") else ""
    return "%s%s%s%s%s" % (fence, pad, text, pad, fence)


def fence_block(value, info="html"):
    """Kanıtı, içeriğinden uzun bir kod çiti içinde render eder (liste satırları).

    Çit uzunluğu içeriğe göre hesaplandığı için sayfadan gelen bir backtick
    dizisi çiti kapatamaz; blok dışına metin sızması (markdown/HTML enjeksiyonu)
    yapısal olarak mümkün değildir. Kanıt tek satıra indirgenir: özet yüzeyi
    okunur kalır, satır sonları ham markdown yapısı üretemez (birebir HTML
    artifact'ta durur, bkz. a11y_gate.classify_violations).
    """
    text = _one_line(value)
    fence = "`" * max(3, _longest_backtick_run(text) + 1)
    return ["%s%s" % (fence, info), text, fence]


def _clip(text):
    """Kanıtı okunur sınırda kes → (metin, kesildi_mi)."""
    if len(text) <= MAX_EVIDENCE_CHARS:
        return text, False
    return text[:MAX_EVIDENCE_CHARS], True


def _target_text(target):
    if isinstance(target, (list, tuple)):
        return " ".join(str(part) for part in target)
    return "" if target is None else str(target)


def allowlisted_incomplete_evidence(row, allowlist):
    """Rapor satırından YALNIZ allowlist'le eşleşen incomplete düğümleri seçer.

    Döner: [{"target": str, "html": str|None}] — satırdaki sırayla.
    """
    if row.get("level") != "incomplete":
        return []
    targets = list(row.get("node_targets") or [])
    htmls = list(row.get("node_html") or [])
    if not targets:
        return []
    probe = {"id": row.get("rule"), "nodes": [{"target": t} for t in targets]}
    indices, _reasons = a11y_gate.allowlisted_node_indices(probe, allowlist)
    evidence = []
    for index in indices:
        evidence.append({
            "target": _target_text(targets[index]),
            "html": htmls[index] if index < len(htmls) else None,
        })
    return evidence


def render_report(data, allowlist, label):
    """Bir a11y raporunun allowlist'li incomplete kanıt satırlarını üretir."""
    lines = []
    for row in data.get("violations") or []:
        evidence = allowlisted_incomplete_evidence(row, allowlist)
        if not evidence:
            continue
        shown = evidence[:MAX_NODES_PER_RULE]
        lines.append("- %s · %s: allowlist'li incomplete kanıtı (%d düğüm)%s" % (
            label, code_span(row.get("rule", "?")), len(evidence),
            "" if len(shown) == len(evidence)
            else " — ilk %d gösteriliyor" % len(shown)))
        for item in shown:
            text, clipped = _clip(_one_line(item["html"]))
            lines.append("  - hedef %s" % code_span(item["target"]))
            # Kod çiti, içeren maddenin içerik kolonuna (4 boşluk) hizalanır.
            lines.extend("    " + line for line in fence_block(text))
            if clipped:
                lines.append(
                    "  - kanıt %d karakterde kesildi; tamamı JSON artifact'ında"
                    % MAX_EVIDENCE_CHARS)
        if len(evidence) > len(shown):
            lines.append("  - %d düğüm daha; tam liste JSON artifact'ında"
                         % (len(evidence) - len(shown)))
    return lines


def render_reports(reports, allowlist):
    """[(label, report_dict)] → özet satırları (yalnız allowlist'li kanıt)."""
    lines = []
    for label, data in reports:
        lines.extend(render_report(data, allowlist, label))
    return lines


def render_allowlist_error(exc):
    """Allowlist okunamadıysa GÖRÜNÜR uyarı satırı (sessiz boş özet üretme)."""
    return "- allowlist okunamadı: %s — incomplete kanıtı gösterilemedi (%s)" % (
        code_span(exc), code_span("a11y_gate_config.json"))


def load_allowlist(path):
    """Konfigi yükle → (allowlist, hata). Eksik/bozuk dosya OSError/ValueError verir."""
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    allowlist = cfg["allowlist"]
    if not isinstance(allowlist, list):
        raise ValueError("allowlist liste değil")
    return allowlist


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, help="a11y_gate_config.json yolu")
    ap.add_argument("--report", action="append", default=[], metavar="LABEL=PATH",
                    help="a11y raporu (birden çok kez verilebilir)")
    args = ap.parse_args(argv)

    allowlist = load_allowlist(args.config)
    reports = []
    for spec in args.report:
        if "=" not in spec:
            ap.error("--report LABEL=PATH biçiminde olmalı: %s" % spec)
        label, path = spec.split("=", 1)
        with open(path, "r", encoding="utf-8") as f:
            reports.append((label, json.load(f)))
    for line in render_reports(reports, allowlist):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
