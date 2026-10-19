#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_lean_statements.py — K9 LaTeX↔Lean statement gate (fail-closed).

``Content.lean`` declarations are compared with the independent, machine-readable
LaTeX contract in ``Content.lean.tex``.  The LaTeX file is the statement source;
``MAP.md`` remains only the legacy Z3↔Lean name map and is not read here.

The gate is inventory-driven: there is no frozen theorem count or name list.
Every Lean ``theorem``/``lemma`` must have exactly one formal LaTeX environment,
and every formal environment must have exactly one Lean declaration.  A formal
environment consists of one ``\\label{lean:NAME}`` and one directly nested
``leanstatement`` environment.  The latter contains a restricted, canonical
LaTeX rendering of the Lean proposition; unsupported LaTeX is rejected rather
than guessed.

Fail-closed findings include malformed/unbalanced environments, comments,
unbound or duplicate labels, missing/duplicate statements, unsupported LaTeX,
duplicate Lean declarations, and Lean/LaTeX inventory drift.

Exit: 0 = compatible / 1 = drift or invalid source / 2 = CLI/file error.
Usage:
    python3 check_lean_statements.py [--lean-file PATH] [--latex-file PATH]
                                      [--json] [--exit-0]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LEAN = os.path.normpath(
    os.path.join(HERE, "..", "lean_reduct", "Content.lean"))
DEFAULT_LATEX = os.path.normpath(
    os.path.join(HERE, "..", "lean_reduct", "Content.lean.tex"))

FORMAL_ENVS = frozenset({"theorem", "lemma", "proposition", "corollary"})
STATEMENT_ENV = "leanstatement"
LEAN_NAME_RE = re.compile(r"^[^\W\d]\w*(?:'\w+)*$", re.UNICODE)
_ENV_RE = re.compile(r"\\(begin|end)\s*\{([A-Za-z][A-Za-z0-9*]*)\}")
_LABEL_RE = re.compile(r"\\label\s*\{")

# ── Lean bildirim başlığı dilbilgisi (AST tarzı tarayıcı) ─────────────────
# Sözleşmeye GİREN teorem eşdeğerleri.  Diğer bildirim anahtar kelimeleri
# tarayıcı tarafından sınıflanır ama statement envanterine girmez (adları
# teorem gövdesi değildir / adları yoktur).
STATEMENT_KEYWORDS = frozenset({"theorem", "lemma"})
# Bildirim öncesi tanımlayıcılar — başlık zincirinin parçası olarak tüketilir
# (`private theorem`, `@[simp] protected theorem ...`).
_MODIFIER_KEYWORDS = frozenset({
    "private", "protected", "noncomputable", "partial", "unsafe",
    "local", "scoped",
})
# Sözleşme DIŞI bildirimler: sınıflanır (kind=anahtar kelime), envantere
# girmez.  `example` ad taşımaz; `def`/`instance`/… teorem gövdesi değildir.
_OTHER_DECL_KEYWORDS = frozenset({
    "def", "abbrev", "instance", "structure", "inductive", "class",
    "example", "axiom", "opaque", "notation", "macro", "elab", "syntax",
})
_IDENT_START_RE = re.compile(r"[^\W\d]", re.UNICODE)
_IDENT_CHARS_RE = re.compile(r"[\w']", re.UNICODE)

# Restricted, explicit translation.  Unknown commands are errors; silently
# deleting an unsupported command could make two different propositions compare
# equal and would violate the fail-closed contract.
_LATEX_GROUP_COMMANDS = frozenset({
    "mathsf", "mathit", "mathrm", "mathbf", "mathtt", "operatorname",
})
_LATEX_SYMBOLS = {
    "lnot": "¬", "neg": "¬",
    "ne": "≠", "neq": "≠",
    "to": "→", "rightarrow": "→", "longrightarrow": "→", "Rightarrow": "→",
    "leftarrow": "←", "gets": "←",
    "leftrightarrow": "↔", "iff": "↔",
    "land": "∧", "wedge": "∧",
    "lor": "∨", "vee": "∨",
    "forall": "∀", "exists": "∃",
    "le": "≤", "leq": "≤",
    "ge": "≥", "geq": "≥",
    "langle": "⟨", "rangle": "⟩",
    "mid": "|",
    "colon": ":",
    "quad": " ", "qquad": " ", ",": " ", ";": " ", "!": " ",
    " ": " ",
}


def _is_escaped(text, index):
    """True when text[index] is preceded by an odd backslash run."""
    count = 0
    i = index - 1
    while i >= 0 and text[i] == "\\":
        count += 1
        i -= 1
    return count % 2 == 1


def _mask_lean_comments(text):
    """Mask Lean comments and string contents while preserving offsets/newlines.

    Header discovery must not see a commented-out ``theorem`` or text inside a
    string literal.  The original text is used separately for proposition
    extraction, so string-valued propositions remain lossless.
    """
    out = list(text)
    i = 0
    state = "code"
    block_depth = 0
    while i < len(text):
        ch = text[i]
        if state == "line":
            if ch == "\n":
                state = "code"
            else:
                out[i] = " "
            i += 1
            continue
        if state == "block":
            if text.startswith("/-", i):
                out[i] = out[i + 1] = " "
                block_depth += 1
                i += 2
            elif text.startswith("-/", i):
                out[i] = out[i + 1] = " "
                block_depth -= 1
                i += 2
                if block_depth == 0:
                    state = "code"
            else:
                if ch != "\n":
                    out[i] = " "
                i += 1
            continue
        if state == "string":
            if ch == "\\" and i + 1 < len(text):
                out[i] = " "
                if text[i + 1] != "\n":
                    out[i + 1] = " "
                i += 2
            elif ch == '"':
                state = "code"
                i += 1
            else:
                if ch != "\n":
                    out[i] = " "
                i += 1
            continue

        if text.startswith("--", i):
            out[i] = out[i + 1] = " "
            state = "line"
            i += 2
        elif text.startswith("/-", i):
            out[i] = out[i + 1] = " "
            block_depth = 1
            state = "block"
            i += 2
        elif ch == '"':
            state = "string"
            i += 1
        else:
            i += 1
    return "".join(out)


def _lean_statement_fragment(text, start):
    """Return (normalized statement, found_assignment) before a real ``:=``.

    Comments and string literals are respected.  This prevents ``:=`` in a
    string from terminating the signature and lets a block comment occur in a
    multiline proposition without corrupting the comparison.
    """
    out = []
    i = start
    state = "code"
    block_depth = 0
    while i < len(text):
        ch = text[i]
        if state == "line":
            if ch == "\n":
                out.append("\n")
                state = "code"
            else:
                out.append(" ")
            i += 1
            continue
        if state == "block":
            if text.startswith("/-", i):
                out.append("  ")
                block_depth += 1
                i += 2
            elif text.startswith("-/", i):
                out.append("  ")
                block_depth -= 1
                i += 2
                if block_depth == 0:
                    state = "code"
            else:
                out.append("\n" if ch == "\n" else " ")
                i += 1
            continue
        if state == "string":
            out.append(ch)
            if ch == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
            else:
                if ch == '"':
                    state = "code"
                i += 1
            continue

        if text.startswith("--", i):
            out.append(" ")
            state = "line"
            i += 1
        elif text.startswith("/-", i):
            out.append("  ")
            block_depth = 1
            state = "block"
            i += 2
        elif text.startswith(":=", i):
            return _normalize_lean_expression("".join(out)), True
        elif ch == '"':
            out.append(ch)
            state = "string"
            i += 1
        else:
            out.append(ch)
            i += 1
    return _normalize_lean_expression("".join(out)), False


def _normalize_lean_expression(expression):
    """Collapse whitespace outside string literals, preserving string contents."""
    out = []
    pending_space = False
    in_string = False
    i = 0
    while i < len(expression):
        ch = expression[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < len(expression):
                out.append(expression[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch.isspace():
            pending_space = bool(out)
            i += 1
            continue
        if pending_space:
            out.append(" ")
            pending_space = False
        out.append(ch)
        if ch == '"':
            in_string = True
        i += 1
    return "".join(out).strip()


def _read_ident(text, index):
    """Read one Unicode identifier (with prime suffixes) at ``index``."""
    if index >= len(text) or not _IDENT_START_RE.match(text[index]):
        return None, index
    end = index + 1
    while end < len(text) and _IDENT_CHARS_RE.match(text[end]):
        end += 1
    return text[index:end], end


def _read_name_segment(text, index):
    """Read one name segment: ``«quoted name»`` or a plain identifier."""
    if index < len(text) and text[index] == "«":
        close = text.find("»", index + 1)
        if close == -1:
            return None, index
        return text[index + 1:close], close + 1
    return _read_ident(text, index)


def _read_declaration_name(text, index):
    """Read a hierarchical Lean name ``(_root_.)? seg (. seg)*``.

    Returns ``(name, next_index, ok)``.  ``_root_`` is a namespace escape and
    is dropped from the reported name; quoted segments (``«a b»``) keep their
    inner text verbatim.
    """
    start = index
    if text.startswith("_root_.", index):
        index += len("_root_.")
    segment, index = _read_name_segment(text, index)
    if segment is None:
        return None, start, False
    parts = [segment]
    while index < len(text) and text[index] == ".":
        segment, nxt = _read_name_segment(text, index + 1)
        if segment is None:
            return None, start, False
        parts.append(segment)
        index = nxt
    return ".".join(parts), index, True


def _skip_attribute(text, index):
    """Skip a ``@[...]`` attribute (balanced brackets).  ``None`` = malformed."""
    if not text.startswith("@[", index):
        return index
    depth = 0
    i = index + 1
    while i < len(text):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def parse_lean_declarations(lean_text):
    """AST-style scanner for Lean declaration heads.

    Returns ``(declarations, findings)``.  Run on comment/string-masked text
    (offsets preserved).  Each declaration is ``{"keyword", "kind", "name",
    "colon_end", "line"}`` where ``kind`` is ``"theorem"``/``"lemma"`` for
    contract members and the raw keyword for classified non-statements
    (``def``/``instance``/``example``/…).

    Grammar per head (line-initial, indentation allowed):
        ``(@[...] | modifier)* (theorem|lemma|other) name? ':'``
    Name grammar: hierarchical ``a.b.c`` with optional ``_root_.`` prefix and
    ``«quoted»`` segments.  A ``theorem``/``lemma`` whose name or ``:`` cannot
    is a fail-closed finding — the scanner never silently drops a statement
    head.
    """
    declarations = []
    findings = []
    text = lean_text
    length = len(text)
    i = 0
    line = 1
    while i < length:
        line += text.count("\n", i, i + 1)
        # Head candidates start at the first non-blank character of a line.
        j = i
        while j < length and text[j] in " \t":
            j += 1
        if j >= length or text[j] == "\n":
            i = j + 1 if j < length else length
            continue
        # Consume the head chain: attributes + modifiers, then a keyword.
        keyword, index, ok = None, j, True
        for _ in range(12):  # zincir uzunluğu sınırı (pathological girdi)
            if text.startswith("@[", index):
                nxt = _skip_attribute(text, index)
                if nxt is None:
                    ok = False
                    break
                index = nxt
                while index < length and text[index] in " \t":
                    index += 1
                continue
            word, nxt = _read_ident(text, index)
            if word in _MODIFIER_KEYWORDS:
                index = nxt
                while index < length and text[index] in " \t\n":
                    index += 1
                continue
            keyword = word
            index = nxt
            break
        if not ok or keyword is None:
            i = text.find("\n", j)
            i = length if i == -1 else i + 1
            continue
        if keyword not in STATEMENT_KEYWORDS and \
                keyword not in _OTHER_DECL_KEYWORDS:
            i = text.find("\n", j)
            i = length if i == -1 else i + 1
            continue
        # Statement heads: name + ':' are contractual; failures are findings.
        if keyword in STATEMENT_KEYWORDS:
            while index < length and text[index] in " \t\n":
                index += 1
            name, index2, named = _read_declaration_name(text, index)
            if not named:
                snippet = text[index:index + 40].split("\n", 1)[0].strip()
                findings.append({
                    "kind": "declaration_name_invalid",
                    "name": snippet,
                    "detail": ("Lean teorem bildiriminin adı çözülemedi: "
                               f"{snippet!r}"),
                })
                i = text.find("\n", j)
                i = length if i == -1 else i + 1
                continue
            probe = index2
            while probe < length and text[probe] in " \t\n":
                probe += 1
            # ":=" atama operatörüdür, tip ayracı DEĞİL — "theorem x := ..."
            # geçerli bir statement bildirimi değildir (fail-closed).
            if probe >= length or text[probe] != ":" or \
                    text.startswith(":=", probe):
                findings.append({
                    "kind": "declaration_malformed",
                    "name": name,
                    "detail": (f"Lean teorem bildiriminde ':' bekleniyordu: "
                               f"{name}"),
                })
                i = text.find("\n", j)
                i = length if i == -1 else i + 1
                continue
            declarations.append({
                "keyword": keyword, "kind": keyword, "name": name,
                "colon_end": probe + 1, "line": line,
            })
            i = text.find("\n", j)
            i = length if i == -1 else i + 1
            continue
        # Non-statement declaration: classify, never enter the inventory.
        name, _nxt, _named = _read_declaration_name(text, index)
        declarations.append({
            "keyword": keyword, "kind": keyword, "name": name,
            "colon_end": None, "line": line,
        })
        i = text.find("\n", j)
        i = length if i == -1 else i + 1
    return declarations, findings


def extract_signatures(lean_text, findings=None):
    """Extract all Lean ``theorem``/``lemma`` names and proposition types.

    Uses the AST-style declaration scanner (``parse_lean_declarations``), so
    modifier/attribute-prefixed heads, hierarchical (``a.b``) and quoted
    (``«a b»``) names, and indented heads are inventoried.  Non-statement
    declarations (``def``/``instance``/``example``/…) are classified and
    ignored.  The optional ``findings`` list receives fail-closed source
    diagnostics such as duplicate declarations, missing ``:=`` boundaries,
    unparseable theorem names and missing ``:``.  The historical dictionary
    return type is retained for callers that only need the inventory.
    """
    signatures = {}
    seen_names = set()
    masked = _mask_lean_comments(lean_text)
    declarations, scan_findings = parse_lean_declarations(masked)
    if findings is not None:
        findings.extend(scan_findings)
    for declaration in declarations:
        if declaration["kind"] not in STATEMENT_KEYWORDS:
            continue
        name = declaration["name"]
        duplicate = name in seen_names
        seen_names.add(name)
        expression, terminated = _lean_statement_fragment(
            lean_text, declaration["colon_end"])
        if findings is not None:
            if not terminated:
                findings.append({
                    "kind": "statement_unterminated",
                    "name": name,
                    "detail": f"Lean bildiriminde ':=' sınırı bulunamadı: {name}",
                })
            if not expression:
                findings.append({
                    "kind": "statement_empty",
                    "name": name,
                    "detail": f"Lean teorem ifadesi boş: {name}",
                })
            if duplicate:
                findings.append({
                    "kind": "duplicate_theorem",
                    "name": name,
                    "detail": f"Lean kaynağında yinelenen teorem bildirimi: {name}",
                })
        # Keep the first declaration visible for diagnostics, but never allow a
        # duplicate to overwrite it and create a false PASS.
        if name not in signatures and expression:
            signatures[name] = expression
    return signatures


def _strip_latex_comments(text):
    """Remove unescaped LaTeX comments while preserving byte offsets/newlines."""
    out = []
    i = 0
    while i < len(text):
        if text[i] == "%" and not _is_escaped(text, i):
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _braced_argument(text, open_index):
    """Return (content, close_index) for a balanced ``{...}`` group.

    ``None`` means malformed/unclosed input.  Nested command arguments such as
    ``\\mathsf{forgetTopic}`` are supported; escaped braces are literal.
    """
    if open_index >= len(text) or text[open_index] != "{":
        return None
    depth = 0
    i = open_index
    while i < len(text):
        ch = text[i]
        if ch == "{" and not _is_escaped(text, i):
            depth += 1
        elif ch == "}" and not _is_escaped(text, i):
            depth -= 1
            if depth == 0:
                return text[open_index + 1:i], i
        i += 1
    return None


def _scan_latex_environments(text):
    """Return balanced environment records or a syntax error string."""
    stack = []
    records = []
    for match in _ENV_RE.finditer(text):
        kind = match.group(1)
        name = match.group(2).lower()
        if kind == "begin":
            parent = stack[-1]["name"] if stack else None
            stack.append({
                "name": name,
                "parent": parent,
                "content_start": match.end(),
                "token_start": match.start(),
            })
            continue
        if not stack:
            return None, f"\\end{{{name}}} eşleşen \\begin yok"
        opened = stack.pop()
        if opened["name"] != name:
            return None, (f"\\begin{{{opened['name']}}} ile "
                          f"\\end{{{name}}} çapraz eşleşiyor")
        records.append({
            "name": name,
            "parent": opened["parent"],
            "content_start": opened["content_start"],
            "content_end": match.start(),
            "token_start": opened["token_start"],
            "token_end": match.end(),
        })
    if stack:
        names = ", ".join(item["name"] for item in stack)
        return None, f"kapanmamış LaTeX environment: {names}"
    return records, None


def _enclosing_record(records, position):
    """Return the innermost environment record containing a source position."""
    candidates = [record for record in records
                  if record["content_start"] <= position < record["content_end"]]
    if not candidates:
        return None
    return max(candidates, key=lambda record: record["content_start"])


def _parse_labels(text, findings):
    """Parse every label command and return ``(position, value)`` pairs."""
    labels = []
    for match in _LABEL_RE.finditer(text):
        parsed = _braced_argument(text, match.end() - 1)
        if parsed is None:
            findings.append({
                "kind": "latex_syntax",
                "detail": "LaTeX \\label argümanı kapanmamış",
            })
            continue
        value, _close = parsed
        labels.append((match.start(), value.strip(), _close))
    return labels


def _normalize_latex_statement(raw):
    """Translate the restricted statement grammar to canonical Lean notation."""
    out = []
    brace_depth = 0
    i = 0
    while i < len(raw):
        if raw.startswith(r"\(", i) or raw.startswith(r"\[", i):
            i += 2
            continue
        if raw.startswith(r"\)", i) or raw.startswith(r"\]", i):
            i += 2
            continue
        ch = raw[i]
        if ch == "$":
            i += 1
            continue
        if raw.startswith(r"\{", i) or raw.startswith(r"\}", i):
            out.append(raw[i + 1])
            i += 2
            continue
        if raw.startswith(r"\%", i) or raw.startswith(r"\_", i) or \
                raw.startswith(r"\&", i) or raw.startswith(r"\#", i):
            out.append(raw[i + 1])
            i += 2
            continue
        if ch == "\\":
            # Spacing controls such as ``\,`` have no alphabetic name.
            spacing = {" ": " ", ",": " ", ";": " ", "!": " "}
            if i + 1 < len(raw) and raw[i + 1] in spacing:
                out.append(spacing[raw[i + 1]])
                i += 2
                continue
            match = re.match(r"\\([A-Za-z]+)", raw[i:])
            if not match:
                raise ValueError(f"desteklenmeyen LaTeX control sequence: \\{raw[i + 1]}")
            command = match.group(1)
            i += match.end()
            if command in _LATEX_GROUP_COMMANDS:
                while i < len(raw) and raw[i].isspace():
                    i += 1
                if i >= len(raw) or raw[i] != "{":
                    raise ValueError(f"\\{command} için braced argüman yok")
                parsed = _braced_argument(raw, i)
                if parsed is None:
                    raise ValueError(f"\\{command} argümanı kapanmamış")
                value, close = parsed
                value = value.strip()
                if not LEAN_NAME_RE.fullmatch(value):
                    raise ValueError(
                        f"\\{command} yalnız Lean identifier kabul eder: {value!r}")
                out.append(value)
                i = close + 1
                continue
            if command not in _LATEX_SYMBOLS:
                raise ValueError(f"desteklenmeyen LaTeX komutu: \\{command}")
            out.append(_LATEX_SYMBOLS[command])
            continue
        if ch == "{":
            brace_depth += 1
            out.append(" ")
            i += 1
            continue
        if ch == "}":
            if brace_depth == 0:
                raise ValueError("fazla '}'")
            brace_depth -= 1
            out.append(" ")
            i += 1
            continue
        if ch == "~":
            out.append(" ")
            i += 1
            continue
        out.append(ch)
        i += 1
    if brace_depth:
        raise ValueError("kapanmamış '{'")
    normalized = re.sub(r"\s+", " ", "".join(out)).strip()
    if not normalized:
        raise ValueError("LaTeX ifadesi boş")
    if re.search(r"\\[A-Za-z]+", normalized):
        raise ValueError("LaTeX ifadesi normalize edilemedi")
    return normalized


def parse_latex_statements(latex_text):
    """Parse all formal LaTeX theorem/lemma statements.

    Returns ``({name: proposition}, findings)``.  The function never guesses a
    missing or malformed statement: a partial dictionary is accompanied by one
    or more fail-closed findings.
    """
    findings = []
    text = _strip_latex_comments(latex_text)
    records, syntax_error = _scan_latex_environments(text)
    if syntax_error:
        return {}, [{"kind": "latex_syntax", "detail": syntax_error}]

    formal_records = [record for record in records
                      if record["name"] in FORMAL_ENVS]
    if not formal_records:
        findings.append({
            "kind": "contract_missing",
            "detail": ("LaTeX kaynağında theorem/lemma/proposition/corollary "
                       "environment bulunamadı"),
        })

    all_labels = _parse_labels(text, findings)
    valid_lean_labels = {}
    bound_labels = set()
    for position, value, _ in all_labels:
        if not value.startswith("lean:"):
            continue
        name = value[len("lean:"):].strip()
        if not LEAN_NAME_RE.fullmatch(name):
            findings.append({
                "kind": "label_invalid",
                "name": name,
                "detail": f"geçersiz Lean label: {value}",
            })
            continue
        valid_lean_labels.setdefault(name, []).append(position)

    for name, positions in sorted(valid_lean_labels.items()):
        if len(positions) > 1:
            findings.append({
                "kind": "duplicate_label",
                "name": name,
                "detail": f"yinelenen LaTeX label: lean:{name}",
            })

    contract = {}
    for record in formal_records:
        parent = _enclosing_record(records, record["token_start"])
        if parent is not None and parent["name"] in FORMAL_ENVS:
            findings.append({
                "kind": "latex_syntax",
                "detail": ("formal theorem/lemma environment başka bir formal "
                           "environment içine yerleştirilemez"),
            })

        body = text[record["content_start"]:record["content_end"]]
        body_offset = record["content_start"]
        labels = []
        for match in _LABEL_RE.finditer(body):
            owner = _enclosing_record(records, body_offset + match.start())
            if owner is None or owner["token_start"] != record["token_start"]:
                continue  # label nested in another environment is not bound here
            parsed = _braced_argument(body, match.end() - 1)
            if parsed is None:
                continue  # already reported by the global parser
            value = parsed[0].strip()
            if value.startswith("lean:"):
                labels.append(value[len("lean:"):].strip())

        if not labels:
            findings.append({
                "kind": "label_missing",
                "detail": ("formal LaTeX environment içinde "
                           "\\label{lean:NAME} yok"),
            })
        elif len(labels) > 1:
            findings.append({
                "kind": "label_count",
                "name": labels[0],
                "detail": (f"formal LaTeX environment içinde {len(labels)} "
                           "Lean label var; tam olarak bir tane olmalı"),
            })

        name = next((item for item in labels
                     if LEAN_NAME_RE.fullmatch(item)), None)
        if name is not None:
            bound_labels.add(name)

        statements = [item for item in records
                      if item["name"] == STATEMENT_ENV
                      and item["parent"] == record["name"]
                      and record["content_start"] <= item["token_start"]
                      < record["content_end"]]
        for item in records:
            if (item["name"] == STATEMENT_ENV
                    and item["parent"] not in FORMAL_ENVS):
                findings.append({
                    "kind": "unbound_statement",
                    "detail": ("leanstatement environment formal "
                               "theorem/lemma dışında"),
                })

        if not statements:
            findings.append({
                "kind": "statement_missing",
                "name": name or "",
                "detail": ("formal LaTeX environment içinde doğrudan "
                           "leanstatement environment yok"),
            })
            continue
        if len(statements) > 1:
            findings.append({
                "kind": "statement_duplicate",
                "name": name or "",
                "detail": (f"formal LaTeX environment içinde {len(statements)} "
                           "leanstatement var; tam olarak bir tane olmalı"),
            })
            continue
        raw = text[statements[0]["content_start"]:
                   statements[0]["content_end"]]
        try:
            expression = _normalize_latex_statement(raw)
        except ValueError as exc:
            findings.append({
                "kind": "statement_syntax",
                "name": name or "",
                "detail": f"LaTeX ifadesi parse edilemedi: {exc}",
            })
            continue
        if name is not None and len(valid_lean_labels.get(name, [])) == 1:
            contract[name] = expression

    # Only labels actually parsed inside a formal environment are bound.  This
    # catches a typo/stray ``\label{lean:...}`` instead of silently ignoring it.
    for name in sorted(set(valid_lean_labels) - bound_labels):
        findings.append({
            "kind": "unbound_label",
            "name": name,
            "detail": f"label biçimsel theorem/lemma environmentına bağlı değil: lean:{name}",
        })

    # A malformed formal environment should not accidentally become a source of
    # truth.  Deduplicate while preserving deterministic order.
    unique = []
    seen = set()
    for finding in findings:
        key = (finding.get("kind"), finding.get("name"),
               finding.get("detail"))
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


def check_statements(lean_file, latex_file):
    """Compare Lean declarations with the canonical LaTeX contract.

    Returns ``(ok, findings)``.  All source and inventory errors are findings;
    callers should not infer PASS from an empty or partial parse.
    """
    findings = []
    lean_text, error = _read_text(lean_file, "Lean")
    if error:
        return False, [error]
    latex_text, error = _read_text(latex_file, "LaTeX")
    if error:
        return False, [error]

    signatures = extract_signatures(lean_text, findings)
    contract, latex_findings = parse_latex_statements(latex_text)
    findings.extend(latex_findings)

    for name, expression in sorted(contract.items()):
        if name not in signatures:
            findings.append({
                "kind": "missing", "name": name,
                "detail": f"teorem Content.lean'da yok: {name}",
            })
        elif signatures[name] != expression:
            findings.append({
                "kind": "changed", "name": name,
                "detail": (f"ifade değişti: {name}\n"
                           f"  Content.lean : {signatures[name]}\n"
                           f"  LaTeX         : {expression}"),
            })
    for name in sorted(signatures):
        if name not in contract:
            findings.append({
                "kind": "extra", "name": name,
                "detail": f"Content.lean'daki teorem LaTeX sözleşmesinde yok: {name}",
            })
    return not findings, findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lean-file", default=DEFAULT_LEAN,
                        help="Lean source (default: ../lean_reduct/Content.lean)")
    parser.add_argument("--latex-file", default=DEFAULT_LATEX,
                        help="canonical LaTeX contract (default: ../lean_reduct/Content.lean.tex)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--exit-0", action="store_true",
                        help="drift olsa bile exit 0 (advisory)")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.lean_file) or not os.path.isfile(args.latex_file):
        print("HATA: Lean veya LaTeX statement kaynağı yok", file=sys.stderr)
        return 2

    ok, findings = check_statements(args.lean_file, args.latex_file)
    if args.json:
        print(json.dumps({
            "ok": ok,
            "findings": findings,
            "lean_file": args.lean_file,
            "latex_file": args.latex_file,
            # Explicitly null: MAP.md is retained as a legacy Z3 name map, not
            # consulted as a statement contract.
            "map_file": None,
        }, ensure_ascii=False))
    else:
        print(f"check-lean-statements: {args.lean_file}")
        print(f"LaTeX source: {args.latex_file}")
        for finding in findings:
            name = f" {finding['name']}" if finding.get("name") else ""
            print(f"  {finding['kind'].upper()}{name} — {finding['detail']}")
        if findings:
            print(f"SONUÇ: {len(findings)} bulgu — fail-closed")
        else:
            print("SONUÇ: uyumlu — tüm Lean ifadeleri LaTeX sözleşmesiyle eşleşti")
    return 1 if findings and not args.exit_0 else 0


if __name__ == "__main__":
    sys.exit(main())
