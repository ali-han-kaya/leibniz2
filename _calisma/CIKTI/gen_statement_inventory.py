#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_statement_inventory.py — statement envanteri + drift raporu yayını (CI).

LaTeX↔Lean statement sözleşmesinin İKİ yüzeyini tek envanterde toplar:

  * K9 — ``Content.lean`` ↔ ``Content.lean.tex`` (check_lean_statements)
  * Canonical kâğıt — ``core_section.tex`` ↔ frozen ``CANONICAL_LABELS``
    (check_paper_statements; parser mekanizması K9 ile paylaşıldır)

Ürettiği yayın (deterministik — zaman damgası YOK, aynı kaynaklar → bayt-bayt
aynı çıktı; koşumlar arası diff'lenebilir):

  statement-inventory.json  — makine-okunur envanter: statement adları +
                              ifadeler, bulgular, kaynak SHA-256 provenance'ı,
                              birleşik hüküm.
  statement-inventory.md    — insan-okunur drift raporu: hüküm bandı +
                              kaynak-bazlı tablolar + bulgu listesi.

Çıkış sözleşmesi (fail-closed):
  0 = rapor yazıldı, drift yok
  1 = rapor yazıldı, DRIFT bulgusu var (kapı adımlarıyla AYNI hüküm —
      raporlayıcı bir adım asla kapıdan bağımsız PASS veremez)
  2 = kaynak okunamadı / rapor yazılamadı (boş raporla sessiz PASS yok)

CI'da ``lake-proof`` işinde iki gate adımından sonra ``if: always()``
koşuluyla koşar (drift anında teşhis raporu da yayınlanmış olur); ``.md``
ayrıca ``$GITHUB_STEP_SUMMARY``'a yazılır ve her iki dosya
``statement-inventory`` artifact'i olarak yüklenir (retention 30 gün —
ci_hygiene_gate tanı sınıfı).

Usage:
    python3 gen_statement_inventory.py [--out-dir DIR]
                                       [--lean-file PATH] [--latex-file PATH]
                                       [--paper-file PATH]
"""
import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_lean_statements as k9  # noqa: E402
import check_paper_statements as paper  # noqa: E402

JSON_NAME = "statement-inventory.json"
MD_NAME = "statement-inventory.md"
GENERATOR = "gen_statement_inventory.py"


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read(path, label):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read(), None
    except (OSError, UnicodeError) as exc:
        return None, f"{label} okunamadı: {exc}"


def collect_inventory(lean_file, latex_file, paper_file):
    """Run both statement gates and collect the combined inventory.

    Returns ``(inventory, source_error)``.  ``source_error`` is a message when
    any required source is missing/unreadable — callers must not publish a
    partial inventory (fail-closed).
    """
    sources = {}
    for key, path in (("lean", lean_file), ("latex", latex_file),
                      ("paper", paper_file)):
        if not os.path.isfile(path):
            return None, f"kaynak yok: {key} ({path})"
        sources[key] = {"path": path, "sha256": _sha256(path)}

    latex_text, error = _read(latex_file, "K9 LaTeX")
    if error:
        return None, error
    paper_text, error = _read(paper_file, "canonical kâğıt")
    if error:
        return None, error

    # K9 yüzeyi: verdict+findings kapıdan (check_statements parse bulgularını
    # da içerir — ayrı parse yalnız tablo sözleşmesi için kullanılır).
    k9_ok, k9_findings = k9.check_statements(lean_file, latex_file)
    k9_contract, _k9_parse_findings = k9.parse_latex_statements(latex_text)
    k9_entries = [{"name": name, "expression": k9_contract[name]}
                  for name in sorted(k9_contract)]

    # Kâğıt yüzeyi: yapı + frozen envanter kapısından.
    paper_ok, paper_findings, paper_contract = paper.check_paper(paper_file)
    paper_entries = [{"label": label, "statement": paper_contract[label]}
                     for label in sorted(paper_contract)]

    total_findings = len(k9_findings) + len(paper_findings)
    ok = k9_ok and paper_ok  # her iki kapı da bulgu-ücretsiz → PASS
    inventory = {
        "gate": "statement-inventory",
        "generator": GENERATOR,
        "ok": ok,
        "verdict": "PASS" if ok else "DRIFT",
        "total_findings": total_findings,
        "sources": sources,
        "k9": {
            "ok": k9_ok,
            "lean_file": lean_file,
            "latex_file": latex_file,
            "statements": k9_entries,
            "findings": k9_findings,
        },
        "paper": {
            "ok": paper_ok,
            "paper_file": paper_file,
            "expected_labels": list(paper.CANONICAL_LABELS),
            "statements": paper_entries,
            "findings": paper_findings,
        },
    }
    return inventory, None


def _md_escape(text):
    return re.sub(r"\s+", " ", text).strip().replace("|", "\\|")


def _preview(text, limit=110):
    flat = _md_escape(text)
    return flat if len(flat) <= limit else flat[:limit - 1] + "…"


def _findings_block(findings):
    if not findings:
        return "Bulgu yok."
    lines = []
    for finding in findings:
        name = f" `{finding['name']}`" if finding.get("name") else ""
        lines.append(f"- **{finding['kind'].upper()}**{name} — "
                     f"{finding['detail']}")
    return "\n".join(lines)


def render_markdown(inventory):
    """Human-readable drift report (deterministic — no timestamps)."""
    total = inventory["total_findings"]
    if inventory["ok"]:
        verdict = "**Hüküm:** PASS — statement envanteri drift'siz."
    else:
        verdict = (f"**Hüküm:** DRIFT — {total} bulgu. Gate adımları "
                   "(K9 + paper-statements) aynı hükümde kırmızıdır.")
    lines = [
        "# LaTeX↔Lean statement envanteri — drift raporu",
        "",
        verdict,
        "",
        "Kaynaklar (SHA-256 provenance):",
    ]
    for key in ("lean", "latex", "paper"):
        source = inventory["sources"][key]
        lines.append(f"- `{key}`: `{source['path']}` — "
                     f"`{source['sha256']}`")
    lines += ["", "## K9 — Content.lean ↔ Content.lean.tex", ""]
    k9c = inventory["k9"]
    lines.append("**Hüküm:** " + ("PASS" if k9c["ok"] else "DRIFT"))
    lines += ["", "| Statement | İfade |", "|---|---|"]
    for entry in k9c["statements"]:
        lines.append(f"| `{entry['name']}` | {_preview(entry['expression'])} |")
    if not k9c["statements"]:
        lines.append("| — | (sözleşme boş — fail-closed, bulgulara bakın) |")
    lines += ["", "**K9 bulguları:**", _findings_block(k9c["findings"]), ""]

    lines += ["## Canonical kâğıt — core_section.tex ↔ frozen envanter", ""]
    pc = inventory["paper"]
    lines.append("**Hüküm:** " + ("PASS" if pc["ok"] else "DRIFT"))
    lines += ["", "| Etiket | Statement gövdesi |", "|---|---|"]
    for entry in pc["statements"]:
        lines.append(f"| `{entry['label']}` | {_preview(entry['statement'])} |")
    if not pc["statements"]:
        lines.append("| — | (envanter boş — fail-closed, bulgulara bakın) |")
    lines += ["", "**Kâğıt bulguları:**", _findings_block(pc["findings"]), ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="statement-inventory",
                        help="çıktı dizini (default: statement-inventory)")
    parser.add_argument("--lean-file", default=k9.DEFAULT_LEAN)
    parser.add_argument("--latex-file", default=k9.DEFAULT_LATEX)
    parser.add_argument("--paper-file", default=paper.DEFAULT_PAPER)
    args = parser.parse_args(argv)

    inventory, error = collect_inventory(
        args.lean_file, args.latex_file, args.paper_file)
    if error:
        print(f"HATA: {error}", file=sys.stderr)
        return 2

    try:
        os.makedirs(args.out_dir, exist_ok=True)
        json_path = os.path.join(args.out_dir, JSON_NAME)
        md_path = os.path.join(args.out_dir, MD_NAME)
        with open(json_path, "w", encoding="utf-8") as handle:
            json.dump(inventory, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)
            handle.write("\n")
        with open(md_path, "w", encoding="utf-8") as handle:
            handle.write(render_markdown(inventory))
    except OSError as exc:
        print(f"HATA: rapor yazılamadı: {exc}", file=sys.stderr)
        return 2

    print(f"statement-inventory: {inventory['verdict']} — "
          f"K9 {len(inventory['k9']['statements'])} statement, "
          f"kâğıt {len(inventory['paper']['statements'])} etiket → "
          f"{json_path} + {md_path}")
    return 0 if inventory["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
