#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_paper_statements.py — canonical kâğıt statement kapısı (fail-closed).

Canonical makalenin (``core_section.tex``) gerçek proposition/lemma envanteri,
K9 ile **aynı** fail-closed LaTeX parser mekanizmasına bağlanır: ortak
``_strip_latex_comments`` / ``_scan_latex_environments`` / ``_parse_labels``
alt katmanı ``check_lean_statements`` modülünden import edilir (tek kaynak;
parser burada kopyalanmaz).

Sözleşme üç katman:

1. **YAPI** — her formal environment (theorem/lemma/proposition/corollary)
   tam olarak bir ``\\label{prop:NAME}`` / ``\\label{lem:NAME}`` etiketi ve
   etiket dışında boş olmayan bir statement gövdesi içermelidir; formal
   environmentlar iç içe geçemez.
2. **ETİKET** — proposition → ``prop:``, lemma → ``lem:`` ön eki zorunludur;
   etiket adı ``[a-z0-9-]+`` ile sınırlıdır; yinelenen etiket ve formal
   environment dışındaki her ``prop:``/``lem:`` etiketi (kaçak etiket)
   bulgudur.
3. **ENVANTER** — ``CANONICAL_LABELS`` (frozen) ile birebir eşleşme: eksik,
   fazla veya yeniden adlandırılmış her statement bulgudur.  Envanter
   kaynak metinden ** türetilmez**; bilinçli bir sözleşme kararıdır.

Kaynak yoksa / okunamazsa / parse edilemezse asla PASS verilmez.  CI'da
``lean-reduct`` işinde K9 adımının hemen ardından ``--json`` ile koşar.

Exit: 0 = uyumlu / 1 = bulgu / 2 = CLI veya dosya hatası.
Usage:
    python3 check_paper_statements.py [--paper-file PATH] [--json] [--exit-0]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_lean_statements as _k9  # noqa: E402  (aynı parser mekanizması)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PAPER = os.path.normpath(os.path.join(
    HERE, "..", "V5_ICERIK", "TESLIM_V5_FINAL_2026-08-17",
    "stoic_hume_package", "Stoic_Hume_Formal_Section_2026-08-17",
    "core_section.tex"))

# Frozen canonical envanter — kaynak metinden türetilmez, sözleşme kararıdır.
# Altı statement'ın Lean tarafı `_calisma/lean_reduct/ReductInvariance.lean`
# içinde formalize edilir (bkz. LEAN_ISPAT_RAPORU.md); K9 (`Content.lean.tex`)
# ise Content.lean'ın forget*/historical_pair_* sözleşmesini kapsar — bu iki
# envanter bilerek ayrıdır.
CANONICAL_LABELS = (
    "lem:reduct-invariance",
    "prop:bridge-collapse",
    "prop:definability",
    "prop:stability",
    "prop:strength",
    "prop:underdet",
)

# formal environment türü → zorunlu etiket ön eki
_PREFIX_BY_ENV = {
    "proposition": "prop",
    "lemma": "lem",
    "theorem": "thm",
    "corollary": "cor",
}
_LABEL_PREFIXES = frozenset(_PREFIX_BY_ENV.values())
LABEL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_LABEL_CMD_RE = re.compile(r"\\label\s*\{[^{}]*\}")


def parse_paper_statements(latex_text):
    """Parse the canonical paper's formal environments fail-closed.

    Returns ``({label: statement_body}, findings)``.  The function never
    guesses a missing or malformed statement: a partial dictionary is
    accompanied by one or more findings.  Uses the exact scanner/label/
    comment machinery of the K9 gate (``check_lean_statements``).
    """
    findings = []
    text = _k9._strip_latex_comments(latex_text)
    records, syntax_error = _k9._scan_latex_environments(text)
    if syntax_error:
        return {}, [{"kind": "latex_syntax", "detail": syntax_error}]

    formal_records = [record for record in records
                      if record["name"] in _k9.FORMAL_ENVS]
    if not formal_records:
        findings.append({
            "kind": "contract_missing",
            "detail": ("LaTeX kaynağında theorem/lemma/proposition/corollary "
                       "environment bulunamadı"),
        })

    # Global label taraması: yinelenen / kaçak prop:-lem: etiketleri.
    all_labels = _k9._parse_labels(text, findings)
    positions_by_value = {}
    for position, value, _close in all_labels:
        prefix, sep, name = value.partition(":")
        if not sep or prefix not in _LABEL_PREFIXES:
            continue
        if not LABEL_NAME_RE.fullmatch(name):
            findings.append({
                "kind": "label_invalid",
                "name": value,
                "detail": f"geçersiz statement etiketi: {value}",
            })
            continue
        positions_by_value.setdefault(value, []).append(position)
    for value, positions in sorted(positions_by_value.items()):
        if len(positions) > 1:
            findings.append({
                "kind": "duplicate_label",
                "name": value,
                "detail": f"yinelenen statement etiketi: {value}",
            })

    contract = {}
    bound_labels = set()
    for record in formal_records:
        parent = _k9._enclosing_record(records, record["token_start"])
        if parent is not None and parent["name"] in _k9.FORMAL_ENVS:
            findings.append({
                "kind": "latex_syntax",
                "detail": ("formal statement environment başka bir formal "
                           "environment içine yerleştirilemez"),
            })

        body = text[record["content_start"]:record["content_end"]]
        offset = record["content_start"]
        expected_prefix = _PREFIX_BY_ENV[record["name"]]

        labels = []
        for match in _k9._LABEL_RE.finditer(body):
            owner = _k9._enclosing_record(records, offset + match.start())
            if owner is None or owner["token_start"] != record["token_start"]:
                continue  # alt environmenta bağlı etiket burada sayılmaz
            parsed = _k9._braced_argument(body, match.end() - 1)
            if parsed is None:
                continue  # global parser zaten bildirdi
            value = parsed[0].strip()
            prefix, sep, name = value.partition(":")
            if sep and prefix in _LABEL_PREFIXES:
                labels.append((value, prefix, name))

        if not labels:
            findings.append({
                "kind": "label_missing",
                "detail": ("formal statement environment içinde "
                           "\\label{prop:NAME} veya \\label{lem:NAME} yok"),
            })
            continue
        if len(labels) > 1:
            findings.append({
                "kind": "label_count",
                "name": labels[0][0],
                "detail": (f"formal statement environment içinde {len(labels)} "
                           "statement etiketi var; tam olarak bir tane olmalı"),
            })
            continue

        value, prefix, name = labels[0]
        bound_labels.add(value)
        if not LABEL_NAME_RE.fullmatch(name):
            findings.append({
                "kind": "label_invalid",
                "name": value,
                "detail": f"geçersiz statement etiketi: {value}",
            })
            continue
        if prefix != expected_prefix:
            findings.append({
                "kind": "label_prefix",
                "name": value,
                "detail": (f"{record['name']} environmentı '{expected_prefix}:' "
                           f"etiketi bekler, '{prefix}:' bulundu: {value}"),
            })

        statement = _LABEL_CMD_RE.sub(" ", body)
        statement = re.sub(r"\s+", " ", statement).strip()
        if not statement:
            findings.append({
                "kind": "statement_missing",
                "name": value,
                "detail": ("formal statement environment içinde etiket dışı "
                           "boş olmayan statement gövdesi yok"),
            })
            continue
        contract[value] = statement

    # Etiketi olan ama formal environment'a bağlanmayan her label bulgudur.
    for value in sorted(set(positions_by_value) - bound_labels):
        findings.append({
            "kind": "unbound_label",
            "name": value,
            "detail": f"statement etiketi formal environmenta bağlı değil: {value}",
        })

    # Deterministik sıra için tekilleştirme (K9 ile aynı desen).
    unique = []
    seen = set()
    for finding in findings:
        key = (finding.get("kind"), finding.get("name"), finding.get("detail"))
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return contract, unique


def _read_text(path, label):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read(), None
    except (OSError, UnicodeError) as exc:
        return None, {"kind": "source_error", "name": label,
                      "detail": f"{label} okunamadı: {exc}"}


def check_paper(paper_file):
    """Compare the canonical paper against the frozen statement inventory.

    Returns ``(ok, findings, contract)``.  Source and parse errors are
    findings; callers must not infer PASS from an empty or partial parse.
    """
    text, error = _read_text(paper_file, "paper")
    if error:
        return False, [error], {}

    contract, findings = parse_paper_statements(text)
    found = set(contract)
    expected = set(CANONICAL_LABELS)
    for name in sorted(expected - found):
        findings.append({
            "kind": "inventory_missing",
            "name": name,
            "detail": f"canonical envanterdeki statement kâğıtta yok: {name}",
        })
    for name in sorted(found - expected):
        findings.append({
            "kind": "inventory_extra",
            "name": name,
            "detail": f"kâğıtta envanter dışı statement var: {name}",
        })

    unique = []
    seen = set()
    for finding in findings:
        key = (finding.get("kind"), finding.get("name"), finding.get("detail"))
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return not unique, unique, contract


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-file", default=DEFAULT_PAPER,
                        help="canonical LaTeX paper "
                             "(default: V5 core_section.tex)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--exit-0", action="store_true",
                        help="bulgu olsa bile exit 0 (advisory)")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.paper_file):
        print("HATA: canonical paper statement kaynağı yok", file=sys.stderr)
        return 2

    ok, findings, contract = check_paper(args.paper_file)
    if args.json:
        print(json.dumps({
            "gate": "paper-statements",
            "ok": ok,
            "canonical_file": args.paper_file,
            "labels": sorted(contract),
            "expected": list(CANONICAL_LABELS),
            "findings": findings,
        }, ensure_ascii=False))
    else:
        print(f"check-paper-statements: {args.paper_file}")
        for finding in findings:
            name = f" {finding['name']}" if finding.get("name") else ""
            print(f"  {finding['kind'].upper()}{name} — {finding['detail']}")
        if findings:
            print(f"SONUÇ: {len(findings)} bulgu — fail-closed")
        else:
            print("SONUÇ: uyumlu — kâğıt statement envanteri frozen "
                  "sözleşmeyle eşleşti")
    return 1 if findings and not args.exit_0 else 0


if __name__ == "__main__":
    sys.exit(main())
